"""TRIAGE.md check 2.8: Ionescu et al. 2013's published EEM models, reproduced from Table S1.

    uv run --no-sync python benchmarks/charges/models/ionescu_eem_check.py [--models N] [--samples N]

Reads the supporting information from Sci Downloads (structures and per-atom charges are accompanying
files, not in the repository) and the two committed fixtures, `table_s1.csv` and `table_s2.csv`.

This is an IMPLEMENTATION REPRODUCTION in the domain of protein fragments: the source's own EEM charges,
from its own parameters, structures and reference data. It says nothing about small molecules, and it
shares no code with the shipped EEM (which carries Bultinck's parameters and no k).

Only the E models run. The EX models need maximum bond multiplicity per atom, so they need bond-order
perception from a PDB; 2.8 records them BLOCKED on typing rather than comparing a best-effort typing.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
SI = pathlib.Path(r"D:\Xaero Stuff\Documents\Sci Downloads\ionescu2013_si")
FIXTURES = ROOT / "tests" / "fixtures" / "charges" / "ionescu2013"
STRUCTURES = {"training_set": "training_set.pdb", "insulin": "test_insulin_3E7Y.pdb", "ubiquitin": "test_ubiquitin_1UBQ.pdb"}
CHARGES = {"training_set": "QM_EEM_q_training_set.csv", "insulin": "QM_EEM_q_insulin.csv", "ubiquitin": "QM_EEM_q_ubiquitin.csv"}
#: 2.8: printed decimals per Table S1 parameter, for the rounding half-unit.
DECIMALS = {"A": 6, "B": 6, "kappa": 3}
CSV_HALF_UNIT = 5e-7  # the charge CSVs print 6 decimals
BOHR_PER_ANGSTROM = 1.0 / 0.529177210903
SAMPLE_SEED = 20260915


def _rows(path: pathlib.Path, delimiter: str = ","):
    text = "".join(line for line in path.read_text(encoding="utf-8").splitlines(keepends=True) if not line.startswith("#"))
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


# --- source data ----------------------------------------------------------------------------------


def table_s1() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in _rows(FIXTURES / "table_s1.csv"):
        model = out.setdefault(row["model"], {"kappa": float(row["kappa"]), "types": {}})
        model["types"][row["atom_type"]] = (float(row["A"]), float(row["B"]))
    return out


def table_s2() -> dict[tuple[str, str, str, str], float]:
    return {(r["model"], r["qm_scheme"], r["dataset"], r["metric"]): float(r["value"]) for r in _rows(FIXTURES / "table_s2.csv")}


def pdb_models(path: pathlib.Path) -> list[list[tuple[str, float, float, float]]]:
    """Every MODEL's atoms, in file order.

    The files carry no element column (each line stops at 54 characters), so the element is read as:
    a HETATM whose residue is CA is calcium -- " CA " in an ATOM record is an alpha carbon -- and
    otherwise the atom name's first letter after any leading digit ("2HB" is a hydrogen). That rule
    reproduces the paper's Table 1 element counts exactly, which is the check that it is right.
    """
    models, current = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MODEL"):
            current = []
        elif line.startswith(("ATOM", "HETATM")):
            name, residue = line[12:16].strip(), line[17:20].strip()
            element = "Ca" if (line.startswith("HETATM") and residue == "CA") else name.lstrip("0123456789")[0]
            atom = (element, float(line[30:38]), float(line[38:46]), float(line[46:54]))
            if current is None:  # the single-structure files carry no MODEL record
                current = []
            current.append(atom)
        elif line.startswith("ENDMDL"):
            models.append(current)
            current = None
    if current:
        models.append(current)
    return models


def charge_tables(path: pathlib.Path) -> list[dict]:
    """The molecules of one charge CSV: id, elements, QM charges per scheme and EEM charges per model.

    THE TWO LAYOUTS ARE DIFFERENT, and both are read here rather than assumed. The training set is
    written as 12 stacked blocks, one per QM scheme, each with its own molecule sections and three value
    columns (QM, E-EEM, EX-EEM). The two test proteins are one wide table instead: a row per atom, with
    12 QM columns and all 24 model columns named in the header.
    """
    reader = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t"))
    if reader and reader[0] and reader[0][0] == "Nr":  # the wide layout
        header = reader[0]
        molecule = {"id": path.stem, "order": 0, "elements": [], "qm": collections.defaultdict(list),
                    "eem": collections.defaultdict(list)}
        for row in reader[1:]:
            if len(row) != len(header) or not row[0].isdigit():
                continue
            molecule["elements"].append(row[1])
            for column, name in enumerate(header[2:], start=2):
                target = "eem" if name.startswith(("E-", "EX-")) else "qm"
                molecule[target][name].append(float(row[column]))
        return [molecule]

    # KEYED BY NSC ID, NOT BY POSITION: three scheme blocks are short (40, 40, 38 of 41 molecules), so
    # aligning blocks by index would silently pair one molecule's charges with another's structure.
    molecules: dict[str, dict] = {}
    scheme, current = None, None
    for row in reader:
        if not row:
            continue
        if row[0] == "QM scheme":
            scheme, current = row[1], None
        elif row[0] == "NSC":
            current = molecules.setdefault(row[1], {"id": row[1], "order": len(molecules), "elements": [],
                                                    "qm": collections.defaultdict(list), "eem": collections.defaultdict(list)})
        elif scheme is not None and current is not None and len(row) > 5 and row[1].isdigit() and row[2]:
            if len(current["elements"]) < int(row[1]):
                current["elements"].append(row[2])
            current["qm"][scheme].append(float(row[3]))
            current["eem"][f"E-{scheme}"].append(float(row[4]))
            current["eem"][f"EX-{scheme}"].append(float(row[5]))
    return [molecules[key] for key in sorted(molecules, key=lambda k: molecules[k]["order"])]


# --- the model ------------------------------------------------------------------------------------


def eem_system(elements, coords, parameters: dict, reading: str) -> tuple[np.ndarray, np.ndarray]:
    """Paper eqs 2-3 with equalisation: B_i q_i + k sum_j q_j/r_ij - X = -A_i, plus sum q_i = Q.

    X (the molecular electronegativity) is an unknown of this system, never an input: the harmonic mean
    of Pauling electronegativities belongs to the parametrisation step, which is not reproduced here.
    """
    coords = np.asarray(coords, dtype=float)
    scale = 1.0 if reading == "R_angstrom" else BOHR_PER_ANGSTROM
    n = len(elements)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1) * scale
    np.fill_diagonal(distance, np.inf)
    matrix = np.zeros((n + 1, n + 1))
    matrix[:n, :n] = parameters["kappa"] / distance
    matrix[np.diag_indices(n)] = [parameters["types"][e][1] for e in elements]
    matrix[:n, n] = -1.0
    matrix[n, :n] = 1.0
    rhs = np.zeros(n + 1)
    rhs[:n] = [-parameters["types"][e][0] for e in elements]
    return matrix, rhs


def eem_charges(elements, coords, total_charge: float, parameters: dict, reading: str = "R_angstrom") -> np.ndarray:
    matrix, rhs = eem_system(elements, coords, parameters, reading)
    rhs[len(elements)] = total_charge
    return np.linalg.solve(matrix, rhs)[:len(elements)]


def sensitivities(elements, coords, total_charge: float, parameters: dict, reading: str) -> dict[tuple[str, str], np.ndarray]:
    """Exact dq/dp for every Table S1 parameter, from one factorisation with many right-hand sides.

    M q = b, so dq/dp = M^-1 (db/dp - dM/dp q). Finite differences would cost two solves per parameter
    and carry their own step error; a test checks these against central differences anyway.
    """
    n = len(elements)
    matrix, rhs = eem_system(elements, coords, parameters, reading)
    rhs[n] = total_charge
    solution = np.linalg.solve(matrix, rhs)
    q = solution[:n]
    scale = 1.0 if reading == "R_angstrom" else BOHR_PER_ANGSTROM
    coords = np.asarray(coords, dtype=float)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1) * scale
    np.fill_diagonal(distance, np.inf)
    columns, keys = [], []
    for atom_type in parameters["types"]:
        mask = np.array([e == atom_type for e in elements], dtype=float)
        # d/dA: only the right-hand side moves (rhs_i = -A_i for atoms of this type).
        column = np.zeros(n + 1)
        column[:n] = -mask
        columns.append(column)
        keys.append(("A", atom_type))
        # d/dB: only this type's diagonal moves, so -(dM/dB) q is -q_i on those atoms.
        column = np.zeros(n + 1)
        column[:n] = -mask * q
        columns.append(column)
        keys.append(("B", atom_type))
    column = np.zeros(n + 1)  # d/dk: every off-diagonal moves by 1/r_ij
    column[:n] = -((1.0 / distance) @ q)
    columns.append(column)
    keys.append(("kappa", ""))
    derivatives = np.linalg.solve(matrix, np.array(columns).T)
    return {key: derivatives[:n, index] for index, key in enumerate(keys)}


def linearized_tolerance(derivative_map: dict[tuple[str, str], np.ndarray]) -> np.ndarray:
    """2.8: 5e-7 + sum_p |dq_i/dp| * half the last printed digit of p. A first-order estimate."""
    total = None
    for (kind, _), derivative in derivative_map.items():
        term = np.abs(derivative) * 0.5 * 10.0 ** (-DECIMALS[kind])
        total = term if total is None else total + term
    return CSV_HALF_UNIT + total


def combined_tolerance(linear: np.ndarray, envelope: np.ndarray | None, ratio: float) -> np.ndarray:
    """2.8's gate: tau_i = max(tau_linearized_i, 1.1 x envelope_i) where the envelope was sampled, and
    the subset's measured maximum envelope/linear ratio carried onto the fragments outside the subset."""
    if envelope is not None:
        return np.maximum(linear, 1.1 * envelope)
    return linear * ratio * 1.1


def total_charge(molecule: dict, scheme: str) -> float:
    """The fragment's total charge, from the source's own QM column. Integer by measurement, never assumed:
    `applicable` refuses a molecule whose column does not sum to one within 1e-3."""
    return float(round(sum(molecule["qm"][scheme])))


def rounding_envelope(elements, coords, total_charge: float, parameters: dict, reading: str, samples: int) -> np.ndarray:
    """max |q(p') - q(p)| over samples drawn in the full rounding box, plus every single-parameter corner."""
    rng = np.random.default_rng(SAMPLE_SEED)
    base = eem_charges(elements, coords, total_charge, parameters, reading)
    types = list(parameters["types"])
    half = {kind: 0.5 * 10.0 ** (-DECIMALS[kind]) for kind in DECIMALS}
    worst = np.zeros(len(elements))

    def perturbed(deltas):
        return {"kappa": parameters["kappa"] + deltas[("kappa", "")],
                "types": {t: (parameters["types"][t][0] + deltas[("A", t)], parameters["types"][t][1] + deltas[("B", t)]) for t in types}}

    keys = [("kappa", "")] + [(k, t) for t in types for k in ("A", "B")]
    trials = []
    for key in keys:  # every single-parameter corner, both signs
        for sign in (-1.0, 1.0):
            trials.append({other: (sign * half[key[0]] if other == key else 0.0) for other in keys})
    for _ in range(samples):
        trials.append({key: rng.uniform(-half[key[0]], half[key[0]]) for key in keys})
    for deltas in trials:
        worst = np.maximum(worst, np.abs(eem_charges(elements, coords, total_charge, perturbed(deltas), reading) - base))
    return worst + CSV_HALF_UNIT


# --- metrics --------------------------------------------------------------------------------------


def metric_set(pairs: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, float]:
    """Paper eqs 7-9, per molecule then averaged. R is reported in all four candidate conventions
    (Pearson r or r squared, sample or population sigma), because the paper's prose and its own eq 7
    disagree; 2.8 identifies which one Table S2 prints rather than assuming one."""
    out = collections.defaultdict(list)
    for reference, model in pairs:
        n = len(reference)
        centred_reference, centred_model = reference - reference.mean(), model - model.mean()
        covariance = float(centred_reference @ centred_model)
        for ddof, label in ((1, "sample"), (0, "population")):
            denominator = (n - 1) if ddof == 1 else n
            sigma = math.sqrt(float(centred_reference @ centred_reference) / denominator) * math.sqrt(float(centred_model @ centred_model) / denominator)
            r = covariance / denominator / sigma if sigma > 0 else float("nan")
            out[f"R_{label}"].append(r)
            out[f"R2_{label}"].append(r * r)
        out["RMSD_avg"].append(math.sqrt(float((reference - model) @ (reference - model)) / n))
        out["D_avg"].append(float(np.abs(reference - model).mean()))
    return {key: float(np.mean(values)) for key, values in out.items()}


# --- the check ------------------------------------------------------------------------------------


def dataset(name: str) -> list[dict]:
    """One dataset's molecules: the PDB geometry joined to the charge CSV, atom for atom, in file order."""
    structures = pdb_models(SI / "ci400448n_si_005" / STRUCTURES[name])
    out = []
    for molecule in charge_tables(SI / "ci400448n_si_006" / CHARGES[name]):
        geometry = structures[molecule["order"]] if len(structures) > molecule["order"] else None
        out.append({"dataset": name, **molecule,
                    "coords": None if geometry is None else np.array([[a[1], a[2], a[3]] for a in geometry]),
                    "geometry_elements": None if geometry is None else [a[0] for a in geometry]})
    return out


def applicable(molecule: dict, parameters: dict, scheme: str, model: str) -> str:
    """Why this molecule is out of a model's applicable population, or "" when it is in it."""
    if scheme not in molecule["qm"] or model not in molecule["eem"]:
        return f"absent from the {scheme} block"
    if molecule["coords"] is None or len(molecule["coords"]) != len(molecule["elements"]):
        return "no matching structure"
    if molecule["geometry_elements"] != molecule["elements"]:
        return "structure and charge elements differ"
    total = sum(molecule["qm"][scheme])
    if abs(total - round(total)) > 1e-3:
        return f"total charge {total:.4f} is not an integer"
    missing = sorted({e for e in molecule["elements"]} - set(parameters["types"]))
    return f"no Table S1 type for {', '.join(missing)}" if missing else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=int, default=12, help="how many E models to run (12 = all)")
    parser.add_argument("--samples", type=int, default=100, help="rounding-box draws per subset fragment (2.8-A1)")
    parser.add_argument("--datasets", default="training_set,insulin,ubiquitin")
    args = parser.parse_args()

    parameters_by_model = table_s1()
    printed = table_s2()
    e_models = [m for m in sorted(parameters_by_model) if m.startswith("E-")][: args.models]
    data = {name: dataset(name) for name in args.datasets.split(",")}
    atom_rows, model_rows = [], []

    for model in e_models:
        parameters = parameters_by_model[model]
        scheme = model.split("-", 1)[1]
        for name, molecules in data.items():
            reasons = {m["id"]: applicable(m, parameters, scheme, model) for m in molecules}
            excluded = [(i, r) for i, r in reasons.items() if r]
            members = [m for m in molecules if not reasons[m["id"]]]
            if not members:
                continue
            sizes = sorted(range(len(members)), key=lambda i: len(members[i]["elements"]))
            subset = {sizes[0], sizes[len(sizes) // 2], sizes[-1]}
            for reading in ("R_angstrom", "R_bohr"):
                pairs, reproduced, atoms, ratios, worst = [], 0, 0, [], (0.0, "")
                for index, molecule in enumerate(members):
                    elements, coords = molecule["elements"], molecule["coords"]
                    total = total_charge(molecule, scheme)
                    q = eem_charges(elements, coords, total, parameters, reading)
                    linear = linearized_tolerance(sensitivities(elements, coords, total, parameters, reading))
                    envelope = None
                    if index in subset:
                        envelope = rounding_envelope(elements, coords, total, parameters, reading, args.samples)
                        ratios.append(float(np.max(envelope / linear)))
                    tolerance = combined_tolerance(linear, envelope, max(ratios) if ratios else 1.0)
                    reference = np.array(molecule["eem"][model])
                    delta = np.abs(q - reference)
                    reproduced += int(np.sum(delta <= tolerance))
                    atoms += len(elements)
                    if delta.max() > worst[0]:
                        worst = (float(delta.max()), molecule["id"])
                    pairs.append((reference, q))
                    if index in subset:
                        for k in range(len(elements)):
                            atom_rows.append([model, reading, name, molecule["id"], k + 1, elements[k], f"{q[k]:.6f}",
                                              f"{reference[k]:.6f}", f"{q[k] - reference[k]:+.6f}", f"{tolerance[k]:.2e}",
                                              bool(delta[k] <= tolerance[k])])
                metrics = metric_set([(np.array(m["qm"][scheme]), q) for m, (ref, q) in zip(members, pairs)])
                against_printed = {key: printed.get((model, scheme, name, key)) for key in ("R_avg", "RMSD_avg", "D_avg")}
                verdict = "REPRODUCED" if reproduced == atoms else "PARTIAL"
                model_rows.append([model, reading, name, len(members), len(excluded), atoms, reproduced,
                                   f"{worst[0]:.6f}", worst[1], f"{max(ratios):.1f}" if ratios else "",
                                   *[f"{metrics[k]:.4f}" for k in ("R_sample", "R2_sample", "R_population", "R2_population", "RMSD_avg", "D_avg")],
                                   against_printed["R_avg"], against_printed["RMSD_avg"], against_printed["D_avg"], verdict])
                print(f"{model:20} {reading:11} {name:13} {len(members):3} molecules, {reproduced}/{atoms} atoms within tau, "
                      f"max|d| {worst[0]:.4f} ({worst[1]}), envelope/linear {max(ratios):.1f}x")
                print(f"    R sample {metrics['R_sample']:.4f} r2 {metrics['R2_sample']:.4f} population {metrics['R_population']:.4f} "
                      f"r2 {metrics['R2_population']:.4f} | printed R {against_printed['R_avg']}; "
                      f"RMSD {metrics['RMSD_avg']:.4f} vs {against_printed['RMSD_avg']}; D {metrics['D_avg']:.4f} vs {against_printed['D_avg']}")

    header = "# TRIAGE 2.8: Ionescu 2013 E models reproduced from Table S1. EX models are BLOCKED on typing.\n"
    for name, columns, rows in (
        ("ionescu_eem_atoms.csv",
         ["model", "reading", "dataset", "molecule", "atom", "element", "model_charge", "printed_charge", "delta", "tau", "reproduced"], atom_rows),
        ("ionescu_eem_models.csv",
         ["model", "reading", "dataset", "molecules", "excluded", "atoms", "atoms_reproduced", "max_abs_delta", "worst_molecule",
          "envelope_over_linear", "R_sample", "R2_sample", "R_population", "R2_population", "RMSD_avg", "D_avg",
          "printed_R_avg", "printed_RMSD_avg", "printed_D_avg", "verdict"], model_rows),
    ):
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\n").writerows([columns, *rows])
        (HERE / name).write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
