"""Schindler 2021 SQE and Geidl 2015 EEM, against their deposited data and the authors' ChargeFW2.

    uv run --no-sync python benchmarks/charges/models/schindler_sqe_check.py a4
    uv run --no-sync python benchmarks/charges/models/schindler_sqe_check.py b
    uv run --no-sync python benchmarks/charges/models/schindler_sqe_check.py c

Everything is frozen by `schindler_sqe_preregistration.md`; this file implements it and decides
nothing. The equations are transcribed from the paper (p 2) and from ChargeFW2's `src/methods/sqe.cpp`
and `src/methods/eem.cpp` at commit 19e73b248cc3983853892d3b42ca0e967a09954a. The one question they
disagree on, the sign of the right-hand side, is a READING, run both ways (section 2).

The source structures are read with a small V2000 parser of our own, not RDKit: sanitising would
re-perceive aromatic bonds and change the bond orders the atom types are made of.
"""

from __future__ import annotations

import io
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field

import numpy as np
from scipy.special import erf

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
SI = pathlib.Path(os.environ.get("OPENCHEM_SCI_DOWNLOADS", r"D:\Xaero Stuff\Documents\Sci Downloads")) / "schindler2021_si"
SQE_PARAMETERS = ROOT / "tests" / "fixtures" / "charges" / "schindler2021" / "SQE_CCD_gen_parameters.json"
GEIDL_NPA = ROOT / "tests" / "fixtures" / "charges" / "geidl2015" / "B3LYP_6-311G_NPA.par"
CHARGEFW2_COMMIT = "19e73b248cc3983853892d3b42ca0e967a09954a"
READINGS = ("R_plus", "R_minus")
AGREE = 1e-6


# --- source data ---------------------------------------------------------------------------------------


@dataclass
class Molecule:
    name: str
    elements: list[str]
    coords: np.ndarray
    bonds: list[tuple[int, int, int]]  # (i, j, order), 0-based, in file order
    formal: list[int] = field(default_factory=list)

    @property
    def total_charge(self) -> int:
        return sum(self.formal)


def parse_sdf(text: str) -> list[Molecule]:
    """V2000 records: title, counts line, atom block, bond block, `M  CHG`. Fails closed on anything else."""
    molecules = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].strip() and i == len(lines) - 1:
            break
        name = lines[i].strip()
        counts = lines[i + 3]
        if "V2000" not in counts:
            raise ValueError(f"{name}: not a V2000 record (line {i + 4})")
        n_atoms, n_bonds = int(counts[0:3]), int(counts[3:6])
        elements, coords, formal = [], [], []
        charge_codes = {1: 3, 2: 2, 3: 1, 5: -1, 6: -2, 7: -3}
        for line in lines[i + 4:i + 4 + n_atoms]:
            coords.append((float(line[0:10]), float(line[10:20]), float(line[20:30])))
            elements.append(line[31:34].strip())
            code = int(line[36:39]) if line[36:39].strip() else 0
            formal.append(charge_codes.get(code, 0))
        bonds = []
        for line in lines[i + 4 + n_atoms:i + 4 + n_atoms + n_bonds]:
            bonds.append((int(line[0:3]) - 1, int(line[3:6]) - 1, int(line[6:9])))
        j = i + 4 + n_atoms + n_bonds
        chg_seen = False
        while lines[j].strip() != "$$$$":
            if lines[j].startswith("M  CHG"):
                if not chg_seen:  # an M  CHG block supersedes the atom-block charge codes
                    formal = [0] * n_atoms
                    chg_seen = True
                fields = lines[j].split()[3:]
                for k in range(0, len(fields), 2):
                    formal[int(fields[k]) - 1] = int(fields[k + 1])
            j += 1
        molecules.append(Molecule(name, elements, np.array(coords, dtype=float), bonds, formal))
        i = j + 1
    return molecules


def parse_chg(text: str) -> dict[str, tuple[list[str], np.ndarray]]:
    """ChargeFW2's charge format: name, atom count, then `index element charge` per atom."""
    out: dict[str, tuple[list[str], np.ndarray]] = {}
    lines = [l for l in text.splitlines()]
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        name, n = lines[i].strip(), int(lines[i + 1])
        rows = [lines[i + 2 + k].split() for k in range(n)]
        if name in out:
            raise ValueError(f"{name} appears twice in the charge file")
        out[name] = ([r[1] for r in rows], np.array([float(r[2]) for r in rows]))
        i += 2 + n
    return out


def load_dataset(name: str) -> list[tuple[Molecule, np.ndarray]]:
    """Every deposited molecule with its reference charges, matched by name, atom count and element."""
    sdf = zipfile.ZipFile(SI / "schindler2021_S3.zip").read(f"{name}.sdf").decode("utf-8")
    chg = zipfile.ZipFile(SI / "schindler2021_S4.zip").read(f"{name}.chg").decode("utf-8")
    molecules, charges = parse_sdf(sdf), parse_chg(chg)
    if len(molecules) != len(charges):
        raise ValueError(f"{name}: {len(molecules)} structures but {len(charges)} charge records")
    paired = []
    for molecule in molecules:
        if molecule.name not in charges:
            raise ValueError(f"{name}: {molecule.name} has no charge record")
        elements, q = charges[molecule.name]
        if [e.upper() for e in elements] != [e.upper() for e in molecule.elements]:
            raise ValueError(f"{name}: {molecule.name} element sequence differs between SDF and charges")
        paired.append((molecule, q))
    return paired


def load_split() -> dict[str, list[str]]:
    text = (SI / "schindler2021_S2.txt").read_text(encoding="utf-8")
    parts = re.split(r"\*\*\* (.+?) \*\*\*", text)
    return {parts[k].strip(): [x.strip() for x in parts[k + 1].replace("\n", " ").split(",") if x.strip()]
            for k in range(1, len(parts), 2)}


# --- typing and parameters ---------------------------------------------------------------------------


def hbo_types(molecule: Molecule) -> list[str]:
    """Element plus the highest bond order over the atom's bonds (ChargeFW2 `structures/molecule.cpp`).

    An atom with no bonds gets order 0, which no published type has, so it is refused.
    """
    highest = [0] * len(molecule.elements)
    for i, j, order in molecule.bonds:
        highest[i] = max(highest[i], order)
        highest[j] = max(highest[j], order)
    return [f"{e.upper()}/{h}" for e, h in zip(molecule.elements, highest)]


def load_sqe_parameters(path: pathlib.Path = SQE_PARAMETERS) -> tuple[dict, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    names = data["atom"]["names"]
    if names != ["chi", "eta", "width"]:
        raise ValueError(f"unexpected atom parameter names {names}")
    atoms = {k.upper(): tuple(v) for k, v in data["atom"]["data"].items()}
    bonds = {k.upper(): float(v) for k, v in data["bond"]["data"].items()}
    return atoms, bonds


def bond_kappa(bonds: dict, type_i: str, type_j: str, order: int) -> float | None:
    """Unordered in the atom pair: the published keys happen to be sorted, and nothing here relies on it."""
    for a, b in ((type_i, type_j), (type_j, type_i)):
        key = f"{a}-{b}-{order}"
        if key in bonds:
            return bonds[key]
    return None


def load_geidl(path: pathlib.Path = GEIDL_NPA) -> tuple[float, dict]:
    lines = [l.split() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if lines[0][0] != "kappa":
        raise ValueError("Geidl parameter file does not open with kappa")
    return float(lines[0][1]), {f"{p[0].upper()}/{p[1]}": (float(p[2]), float(p[3])) for p in lines[1:]}


# --- the two models -------------------------------------------------------------------------------------


def distances(coords: np.ndarray) -> np.ndarray:
    return np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)


def sqe_matrix(molecule: Molecule, atoms: dict, bonds: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray] | str:
    """(T, H, split matrix) or the reason the molecule is refused."""
    types = hbo_types(molecule)
    missing = sorted({t for t in types if t not in atoms})
    if missing:
        return f"atom type {', '.join(missing)} not parameterised"
    n, m = len(types), len(molecule.bonds)
    chi = np.array([atoms[t][0] for t in types])
    eta = np.array([atoms[t][1] for t in types])
    width = np.array([atoms[t][2] for t in types])
    r = distances(molecule.coords)
    d0 = np.sqrt(2.0 * width[:, None] ** 2 + 2.0 * width[None, :] ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        H = erf(r / d0) / r
    H[np.diag_indices(n)] = eta
    T = np.zeros((m, n))
    kappa = np.zeros(m)
    for k, (i, j, order) in enumerate(molecule.bonds):
        T[k, i], T[k, j] = 1.0, -1.0
        value = bond_kappa(bonds, types[i], types[j], order)
        if value is None:
            return f"bond type {types[i]}-{types[j]}-{order} not parameterised"
        kappa[k] = value
    return T, chi, T @ H @ T.T + np.diag(kappa)


def sqe_charges(molecule: Molecule, atoms: dict, bonds: dict, reading: str) -> np.ndarray | str:
    built = sqe_matrix(molecule, atoms, bonds)
    if isinstance(built, str):
        return built
    T, chi, split = built
    if T.shape[0] == 0:
        return np.zeros(len(molecule.elements))
    c = chi if reading == "R_plus" else -chi
    return T.T @ np.linalg.solve(split, T @ c)


def eem_charges(molecule: Molecule, kappa: float, parameters: dict) -> np.ndarray | str:
    """ChargeFW2 `eem.cpp`, "full": B on the diagonal, kappa/r off it, -A, bordered by the total charge."""
    types = hbo_types(molecule)
    missing = sorted({t for t in types if t not in parameters})
    if missing:
        return f"atom type {', '.join(missing)} not parameterised"
    n = len(types)
    r = distances(molecule.coords)
    A = np.zeros((n + 1, n + 1))
    with np.errstate(divide="ignore"):
        A[:n, :n] = kappa / r
    A[np.diag_indices(n)] = [parameters[t][1] for t in types]
    A[n, :n] = 1.0
    A[:n, n] = 1.0
    A[n, n] = 0.0
    b = np.zeros(n + 1)
    b[:n] = [-parameters[t][0] for t in types]
    b[n] = molecule.total_charge
    return np.linalg.solve(A, b)[:n]


# --- the paper's metrics ----------------------------------------------------------------------------------


def metrics(pairs: list[tuple[list[str], np.ndarray, np.ndarray]], pooled_rmsdat: bool = True) -> dict:
    """Per-molecule R2 and RMSD averaged over the set; RMSDat the worst per-type RMSD (section 1)."""
    r2s, rmsds, undefined = [], [], 0
    by_type: dict[str, list[float]] = {}
    per_molecule_type: dict[str, list[float]] = {}
    for types, ref, model in pairs:
        diff = model - ref
        rmsds.append(math.sqrt(float(np.mean(diff ** 2))))
        if np.std(ref) == 0 or np.std(model) == 0:
            undefined += 1
        else:
            r2s.append(float(np.corrcoef(ref, model)[0, 1] ** 2))
        seen: dict[str, list[float]] = {}
        for t, d in zip(types, diff):
            by_type.setdefault(t, []).append(float(d))
            seen.setdefault(t, []).append(float(d))
        for t, ds in seen.items():
            per_molecule_type.setdefault(t, []).append(math.sqrt(np.mean(np.square(ds))))
    pooled = {t: math.sqrt(float(np.mean(np.square(v)))) for t, v in by_type.items()}
    averaged = {t: float(np.mean(v)) for t, v in per_molecule_type.items()}
    return {
        "molecules": len(pairs), "r2_undefined": undefined,
        "R2": float(np.mean(r2s)), "RMSD": float(np.mean(rmsds)),
        "RMSDat": max(pooled.values()), "RMSDat_type": max(pooled, key=pooled.get),
        "RMSDat_sensitivity_per_molecule_mean": max(averaged.values()),
    }


# --- ChargeFW2 in WSL --------------------------------------------------------------------------------------


def to_wsl_path(path: pathlib.Path) -> str:
    resolved = str(path.resolve())
    return "/mnt/" + resolved[0].lower() + resolved[2:].replace("\\", "/")


def chargefw2_parameter_file(atoms: dict, bonds: dict, out: pathlib.Path) -> pathlib.Path:
    """S7's full-precision values in ChargeFW2's schema, so the authors' code runs the published numbers."""
    def element(symbol: str) -> str:
        return symbol[0] + symbol[1:].lower()
    atom_rows = [{"key": [element(k.split("/")[0]), "hbo", k.split("/")[1]], "value": list(v)} for k, v in sorted(atoms.items())]
    bond_rows = []
    for key, value in sorted(bonds.items()):
        # keys look like "C/1-H/1-1": the bond order is after the last "-", the two types before it
        pair, order = key.rsplit("-", 1)
        first, second = pair.split("-")
        bond_rows.append({"key": [element(first.split("/")[0]), "hbo", first.split("/")[1],
                                  element(second.split("/")[0]), "hbo", second.split("/")[1], "bo", order],
                          "value": [value]})
    payload = {
        "metadata": {"name": "Schindler 2021 (CCD_gen), S7 full precision", "method": "sqe",
                     "publication": "10.1186/s13321-021-00528-w",
                     "notes": "Parameterised to reproduce B3LYP/6-311G/NPA charges; values from Additional file 7"},
        "atom": {"names": ["electronegativity", "hardness", "width"], "data": atom_rows},
        "bond": {"names": ["kappa"], "data": bond_rows},
    }
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return out


#: Runs inside the WSL environment. The CLI prints charges to 5 decimals, which cannot test a 1e-6 gate,
#: so the authors' own Python bindings are used instead: they return the solver's doubles.
_CHARGEFW2_DRIVER = """
import json, sys, chargefw2
molecules = chargefw2.Molecules(sys.argv[1], True, False, False)  # read_hetatm, ignore_water, permissive_types=False
charges = chargefw2.calculate_charges(molecules, sys.argv[2], sys.argv[3], sys.argv[5])  # chg_out_dir: it writes files, keep them out of the tree
json.dump({name: list(values) for name, values in charges.items()}, open(sys.argv[4], "w"))
"""


def run_chargefw2(sdf: pathlib.Path, method: str, par_file: pathlib.Path, out_dir: pathlib.Path) -> dict[str, np.ndarray]:
    """ChargeFW2's `calculate_charges` at full precision, with permissive types off.

    The binding looks a parameter NAME up as `<install>/share/parameters/<name>.json`; an absolute path
    replaces that directory (std::filesystem semantics), so the file is given without its extension.
    """
    if par_file.suffix != ".json":
        raise ValueError(f"{par_file} must be a .json parameter file")
    out_dir.mkdir(parents=True, exist_ok=True)
    driver = out_dir / "driver.py"
    driver.write_bytes(_CHARGEFW2_DRIVER.encode("utf-8"))
    result = out_dir / "charges.json"
    command = (
        "export MAMBA_ROOT_PREFIX=~/tools/mamba PYTHONPATH=~/tools/chargefw2/lib CHARGEFW2_INSTALL_DIR=~/tools/chargefw2/; "
        f"~/tools/bin/micromamba run -n chargefw2 python '{to_wsl_path(driver)}' '{to_wsl_path(sdf)}' {method} "
        f"'{to_wsl_path(par_file.with_suffix(''))}' '{to_wsl_path(result)}' '{to_wsl_path(out_dir)}'"
    )
    done = subprocess.run(["wsl.exe", "-e", "bash", "-lc", command], capture_output=True, text=True)
    if done.returncode != 0 or not result.exists():
        raise RuntimeError(f"ChargeFW2 exited {done.returncode}: {done.stderr[-2000:]}")
    return {name: np.array(values) for name, values in json.loads(result.read_text(encoding="utf-8")).items()}


# --- stages ---------------------------------------------------------------------------------------------------

#: A space-free working directory both Windows and WSL can reach.
WORK = pathlib.Path(os.environ.get("TEMP", "/tmp")) / "schindler_sqe_work"
RESULTS = HERE / "schindler_sqe_results"
SEED = 20260917
#: S6 Table 2 (CCD_gen), SQE, seed 5 -- the registered oracle.
ORACLE = {"train": {"R2": 0.9953, "RMSD": 0.0282, "RMSDat": 0.0414}, "test": {"R2": 0.9952, "RMSD": 0.0279, "RMSDat": 0.0481}}
#: Half a unit of the fourth printed decimal, plus the registered solver allowance.
PRINTED_TOLERANCE = 5e-5 + 1e-6


def sdf_records(text: str) -> dict[str, str]:
    """Each record's raw text, keyed by its title, so subsets are written without re-serialising."""
    out = {}
    for chunk in text.split("$$$$"):
        body = chunk.lstrip("\r\n")
        if body.strip():
            out[body.splitlines()[0].strip()] = body.rstrip("\r\n") + "\n$$$$\n"
    return out


def write_sdf(path: pathlib.Path, records: list[str]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(records), encoding="utf-8", newline="\n")
    return path


def sha256(path: pathlib.Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name: str, payload: dict) -> pathlib.Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(ROOT)} sha256 {sha256(path)}")
    return path


def stage_a4(chargefw2_json: pathlib.Path) -> dict:
    """A.4: ChargeFW2's own CCD_gen file against S7's published values, on 20 molecules."""
    if sha256(chargefw2_json) != "ca68bc7e2bff6753a23f831c588947c219021ccd31082c696eb0ea6e80eb1134":
        raise ValueError("that is not ChargeFW2's CCD_gen parameter file at the pinned commit")
    records = sdf_records(zipfile.ZipFile(SI / "schindler2021_S3.zip").read("CCD_gen.sdf").decode("utf-8"))
    names = sorted(np.random.default_rng(SEED).choice(sorted(records), size=20, replace=False).tolist())
    subset = write_sdf(WORK / "a4" / "subset.sdf", [records[n] for n in names])
    atoms, bonds = load_sqe_parameters()
    s7_file = chargefw2_parameter_file(atoms, bonds, WORK / "a4" / "s7_params.json")
    own = run_chargefw2(subset, "sqe", chargefw2_json, WORK / "a4" / "own")
    s7 = run_chargefw2(subset, "sqe", s7_file, WORK / "a4" / "s7")
    diffs = {n: float(np.max(np.abs(own[n] - s7[n]))) for n in names if n in own and n in s7}
    result = {
        "stage": "A.4", "molecules": names, "computed_by_both": len(diffs),
        "refused": sorted(set(names) - set(diffs)), "max_abs_diff": max(diffs.values()) if diffs else None,
        "per_molecule_max_abs_diff": diffs, "agree_within_1e-6": bool(diffs) and max(diffs.values()) <= AGREE and len(diffs) == 20,
        "chargefw2_commit": CHARGEFW2_COMMIT, "own_parameter_sha256": sha256(chargefw2_json), "s7_parameter_sha256": sha256(SQE_PARAMETERS),
    }
    result["runs_for_part_b"] = "chargefw2_own_file" if result["agree_within_1e-6"] else "s7_values_via_par_file"
    save("a4", result)
    return result


def stage_b(parameter_choice: str, chargefw2_json: pathlib.Path) -> dict:
    atoms, bonds = load_sqe_parameters()
    split = load_split()
    data = load_dataset("CCD_gen")
    records = sdf_records(zipfile.ZipFile(SI / "schindler2021_S3.zip").read("CCD_gen.sdf").decode("utf-8"))
    full = write_sdf(WORK / "b" / "CCD_gen.sdf", [records[m.name] for m, _ in data])
    par = chargefw2_json if parameter_choice == "chargefw2_own_file" else chargefw2_parameter_file(atoms, bonds, WORK / "b" / "s7_params.json")
    theirs = run_chargefw2(full, "sqe", par, WORK / "b" / "chargefw2")

    ours: dict[str, dict[str, np.ndarray]] = {r: {} for r in READINGS}
    refused_ours: dict[str, str] = {}
    smallest_eigenvalue, condition = {}, {}
    for molecule, _ in data:
        built = sqe_matrix(molecule, atoms, bonds)
        if isinstance(built, str):
            refused_ours[molecule.name] = built
            continue
        T, _, split_matrix = built
        if T.shape[0]:
            eig = np.linalg.eigvalsh(split_matrix)
            smallest_eigenvalue[molecule.name] = float(eig[0])
            condition[molecule.name] = float(np.abs(eig).max() / np.abs(eig).min())
        for reading in READINGS:
            ours[reading][molecule.name] = sqe_charges(molecule, atoms, bonds, reading)

    b1 = {}
    for reading in READINGS:
        both = [n for n in ours[reading] if n in theirs]
        agree = [n for n in both if np.max(np.abs(ours[reading][n] - theirs[n])) <= AGREE]
        worst = max(both, key=lambda n: float(np.max(np.abs(ours[reading][n] - theirs[n])))) if both else None
        b1[reading] = {"computed_by_both": len(both), "agree_within_1e-6": len(agree),
                       "fraction": len(agree) / len(both) if both else None,
                       "worst_molecule": worst, "worst_abs_diff": float(np.max(np.abs(ours[reading][worst] - theirs[worst]))) if worst else None}
    only_ours_refused = sorted(n for n in refused_ours if n in theirs)
    only_theirs_refused = sorted(n for n in ours["R_plus"] if n not in theirs)

    by_name = {m.name: (m, q) for m, q in data}
    b2 = {}
    for reading in READINGS:
        b2[reading] = {}
        for subset, key in (("train", "CCD_gen training set"), ("test", "CCD_gen test set")):
            pairs = [(hbo_types(by_name[n][0]), by_name[n][1], ours[reading][n]) for n in split[key] if n in ours[reading]]
            computed = metrics(pairs)
            computed["covered"] = len(pairs)
            computed["of"] = len(split[key])
            computed["matches"] = {k: abs(round(computed[k], 4) - v) <= 1e-9 or abs(computed[k] - v) <= PRINTED_TOLERANCE
                                   for k, v in ORACLE[subset].items()}
            b2[reading][subset] = computed
        hits = sum(sum(b2[reading][s]["matches"].values()) for s in ("train", "test"))
        b2[reading]["values_matching"] = hits
        b2[reading]["verdict"] = "REPRODUCED" if hits == 6 else ("PARTIAL" if hits else "NOT-REPRODUCED")
    reproduced = [r for r in READINGS if b2[r]["verdict"] == "REPRODUCED"]
    reading_is = reproduced[0] if len(reproduced) == 1 else "undetermined"

    charged = {m.name for m, _ in data if m.total_charge != 0}
    strata = {}
    if reading_is != "undetermined":
        for label, selector in (("charged", lambda n: n in charged), ("neutral", lambda n: n not in charged)):
            pairs = [(hbo_types(by_name[n][0]), by_name[n][1], ours[reading_is][n]) for n in ours[reading_is] if selector(n)]
            strata[label] = metrics(pairs)
    eig_values = np.array(list(smallest_eigenvalue.values()))
    cond_values = np.array(list(condition.values()))
    result = {
        "stage": "B", "parameter_choice": parameter_choice, "molecules": len(data),
        "refused_by_us": len(refused_ours), "refused_by_us_reasons": sorted(set(refused_ours.values())),
        "refused_only_by_us": only_ours_refused, "refused_only_by_chargefw2": only_theirs_refused,
        "B1": b1, "B2": b2, "model_reading": reading_is, "strata": strata,
        "conditioning": {
            "not_positive_definite": int(np.sum(eig_values <= 0)), "of": int(eig_values.size),
            "not_positive_definite_names": sorted(n for n, v in smallest_eigenvalue.items() if v <= 0)[:50],
            "condition_median": float(np.median(cond_values)), "condition_p90": float(np.percentile(cond_values, 90)),
            "condition_max": float(cond_values.max()), "smallest_eigenvalue_min": float(eig_values.min()),
        },
        "chargefw2_commit": CHARGEFW2_COMMIT, "numpy": np.__version__,
    }
    save("b", result)
    return result


def stage_b_a1() -> dict:
    """Amendment B-A1: MACH's two aggregations (`modules/comparison.py`), under R_minus."""
    atoms, bonds = load_sqe_parameters()
    split = load_split()
    by_name = {m.name: (m, q) for m, q in load_dataset("CCD_gen")}
    out = {"stage": "B-A1", "reading": "R_minus"}
    for subset, key in (("train", "CCD_gen training set"), ("test", "CCD_gen test set")):
        refs, emps, rounded_rmsd, rounded_r2 = [], [], [], []
        for name in split[key]:
            molecule, ref = by_name[name]
            emp = sqe_charges(molecule, atoms, bonds, "R_minus")
            refs.append(ref)
            emps.append(emp)
            rounded_rmsd.append(round(float(np.sqrt(np.mean((ref - emp) ** 2))), 4))
            pearson = round(float(np.corrcoef(ref, emp)[0, 1]), 4)
            rounded_r2.append(round(pearson ** 2, 4))
        ref_all, emp_all = np.concatenate(refs), np.concatenate(emps)
        out[subset] = {
            "A1_pooled": {"RMSD": float(np.sqrt(np.mean((ref_all - emp_all) ** 2))), "R2": float(np.corrcoef(ref_all, emp_all)[0, 1] ** 2)},
            "A1_rounded_mean": {"RMSD": round(float(np.mean(rounded_rmsd)), 4), "R2": round(float(np.mean(rounded_r2)), 4)},
            "printed": {"RMSD": ORACLE[subset]["RMSD"], "R2": ORACLE[subset]["R2"]},
        }
        for arm in ("A1_pooled", "A1_rounded_mean"):
            out[subset][arm]["matches"] = {k: abs(v - ORACLE[subset][k]) <= PRINTED_TOLERANCE for k, v in out[subset][arm].items() if k in ("RMSD", "R2")}
    save("b_a1", out)
    return out


#: Ionescu section 9.3's silent-error definitions, unchanged (section 5.4).
SIGN_Q, MAGNITUDE = 0.10, 0.50
#: The registered G2 criteria (section 5.5).
G2_COVERAGE, G2_RMSD, G2_SILENT, G2_NOT_PD = 0.90, 0.05, 0.10, 0.01


def _geidl_training_ids() -> set[str]:
    """Column A of Geidl's Additional file 1, read from the xlsx's own XML (no spreadsheet library)."""
    import xml.etree.ElementTree as ET

    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    book = zipfile.ZipFile(SI.parent / "geidl2015_si" / "geidl2015_S1.xlsx")
    shared = [si.findtext("s:t", default="", namespaces=ns) or "".join(r.findtext("s:t", default="", namespaces=ns) for r in si.findall("s:r", ns))
              for si in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("s:si", ns)]
    ids = set()
    for cell in ET.fromstring(book.read("xl/worksheets/sheet1.xml")).iter(f"{{{ns['s']}}}c"):
        if re.fullmatch(r"A\d+", cell.get("r", "")) and cell.get("r") != "A1":
            value = cell.findtext("s:v", namespaces=ns)
            ids.add(shared[int(value)] if cell.get("t") == "s" else value)
    return ids


def _inchikey(record: str) -> str | None:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromMolBlock(record, removeHs=False)
    return Chem.MolToInchiKey(mol) if mol is not None else None


def _gasteiger(record: str, n: int) -> np.ndarray | str:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdPartialCharges

    RDLogger.DisableLog("rdApp.*")
    mol = Chem.MolFromMolBlock(record, removeHs=False)
    if mol is None or mol.GetNumAtoms() != n:
        return "RDKit could not read the record with its atoms intact"
    rdPartialCharges.ComputeGasteigerCharges(mol)
    q = np.array([a.GetDoubleProp("_GasteigerCharge") for a in mol.GetAtoms()])
    return "Gasteiger returned NaN" if not np.all(np.isfinite(q)) else q


def _bultinck(molecule: Molecule) -> np.ndarray | str:
    """The application's shipped Bultinck Part I EEM, called as the application calls it."""
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from openchem.chem import charge_equilibration as ce

    elements = [e[0] + e[1:].lower() for e in molecule.elements]
    result = ce.eem_charges(elements, molecule.coords, float(molecule.total_charge))
    return np.asarray(result.charges) if result.status == "converged" else result.status


def _not_positive_definite(molecule: Molecule, model: str, sqe_params, geidl) -> bool:
    if model == "schindler_sqe":
        T, _, split_matrix = sqe_matrix(molecule, *sqe_params)
        return bool(T.shape[0]) and float(np.linalg.eigvalsh(split_matrix)[0]) <= 0
    kappa, parameters = geidl
    types = hbo_types(molecule)
    with np.errstate(divide="ignore"):
        block = kappa / distances(molecule.coords)
    block[np.diag_indices(len(types))] = [parameters[t][1] for t in types]
    return float(np.linalg.eigvalsh(block)[0]) <= 0


def _evaluate(population, model: str, sqe_params, geidl) -> dict:
    pairs, refused, silent, not_pd = [], {}, 0, 0
    charged_pairs, neutral_pairs = [], []
    for molecule, ref, record in population:
        if model == "schindler_sqe":
            q = sqe_charges(molecule, *sqe_params, "R_minus")
        elif model == "geidl_eem_npa":
            q = eem_charges(molecule, *geidl)
        elif model == "bultinck_part1_eem":
            q = _bultinck(molecule)
        else:
            q = _gasteiger(record, len(molecule.elements))
        if isinstance(q, str):
            refused[q] = refused.get(q, 0) + 1
            continue
        types = hbo_types(molecule)
        pairs.append((types, ref, q))
        (charged_pairs if molecule.total_charge else neutral_pairs).append((types, ref, q))
        sign = np.any((np.abs(ref) >= SIGN_Q) & (np.sign(ref) != np.sign(q)))
        if sign or np.any(np.abs(ref - q) >= MAGNITUDE):
            silent += 1
        if model in ("schindler_sqe", "geidl_eem_npa") and _not_positive_definite(molecule, model, sqe_params, geidl):
            not_pd += 1
    covered = len(pairs)
    out = {"population": len(population), "covered": covered,
           "coverage": covered / len(population) if population else None,
           "refused": refused, "silent_error_molecules": silent,
           "silent_error_rate": silent / covered if covered else None, "not_positive_definite": not_pd}
    if covered:
        m = metrics(pairs)
        out["per_molecule_average"] = {"R2": m["R2"], "RMSD": m["RMSD"], "r2_undefined": m["r2_undefined"]}
        out["RMSDat_pooled_per_type"] = m["RMSDat"]
        out["RMSDat_type"] = m["RMSDat_type"]
        ref_all = np.concatenate([r for _, r, _ in pairs])
        emp_all = np.concatenate([q for _, _, q in pairs])
        out["pooled"] = {"RMSD": float(np.sqrt(np.mean((ref_all - emp_all) ** 2))),
                         "R2": float(np.corrcoef(ref_all, emp_all)[0, 1] ** 2)}
        for label, subset in (("charged", charged_pairs), ("neutral", neutral_pairs)):
            if subset:
                sm = metrics(subset)
                out[f"stratum_{label}"] = {"molecules": len(subset), "per_molecule_RMSD": sm["RMSD"], "per_molecule_R2": sm["R2"]}
    return out


def _g2_verdict(result: dict) -> dict:
    failed = []
    if result["coverage"] is None or result["coverage"] < G2_COVERAGE:
        failed.append(f"coverage {result['coverage']} < {G2_COVERAGE}")
    if result["covered"]:
        if result["per_molecule_average"]["RMSD"] > G2_RMSD:
            failed.append(f"per-molecule RMSD {result['per_molecule_average']['RMSD']:.4f} > {G2_RMSD}")
        if result["silent_error_rate"] > G2_SILENT:
            failed.append(f"silent-error rate {result['silent_error_rate']:.3f} > {G2_SILENT}")
        if result["not_positive_definite"] / result["covered"] > G2_NOT_PD:
            failed.append(f"not positive definite on {result['not_positive_definite']} of {result['covered']}")
    return {"verdict": "G2-CANDIDATE" if not failed else "NOT-G2-CANDIDATE", "failed": failed}


def stage_c() -> dict:
    sqe_params = load_sqe_parameters()
    geidl = load_geidl()
    split = load_split()
    geidl_training = _geidl_training_ids()
    archive = zipfile.ZipFile(SI / "schindler2021_S3.zip")
    ccd = {m.name: (m, q) for m, q in load_dataset("CCD_gen")}
    ccd_records = sdf_records(archive.read("CCD_gen.sdf").decode("utf-8"))
    dtp = load_dataset("DTP_small")
    dtp_records = sdf_records(archive.read("DTP_small.sdf").decode("utf-8"))

    training_keys, unreadable_training = set(), 0
    for name in split["CCD_gen training set"]:
        key = _inchikey(ccd_records[name])
        if key is None:
            unreadable_training += 1
        else:
            training_keys.add(key)
    primary, excluded, unreadable_dtp = [], [], 0
    for molecule, ref in dtp:
        key = _inchikey(dtp_records[molecule.name])
        if key is None:
            unreadable_dtp += 1
        elif key in training_keys:
            excluded.append(molecule.name)
            continue
        primary.append((molecule, ref, dtp_records[molecule.name]))
    geidl_primary = [item for item in primary if item[0].name not in geidl_training]
    secondary = [(ccd[n][0], ccd[n][1], ccd_records[n]) for n in split["CCD_gen test set"]]

    models = {
        "schindler_sqe": _evaluate(primary, "schindler_sqe", sqe_params, geidl),
        "schindler_sqe_without_geidl_overlap": _evaluate(geidl_primary, "schindler_sqe", sqe_params, geidl),
        "geidl_eem_npa": _evaluate(geidl_primary, "geidl_eem_npa", sqe_params, geidl),
        "context_bultinck_part1_eem": _evaluate(primary, "bultinck_part1_eem", sqe_params, geidl),
        "context_gasteiger": _evaluate(primary, "gasteiger", sqe_params, geidl),
    }
    result = {
        "stage": "C",
        "reading": "R_minus (ChargeFW2's convention; B.2 left the reading undetermined)",
        "C_primary": {
            "population": "DTP_small", "molecules": len(dtp),
            "excluded_identical_to_CCD_gen_training": sorted(excluded),
            "inchikey_unreadable_dtp": unreadable_dtp, "inchikey_unreadable_ccd_training": unreadable_training,
            "evaluated": len(primary), "geidl_training_overlap_removed": len(primary) - len(geidl_primary),
            "models": models,
            "verdicts": {"schindler_sqe": _g2_verdict(models["schindler_sqe"]), "geidl_eem_npa": _g2_verdict(models["geidl_eem_npa"])},
        },
        "C_secondary": {
            "population": "CCD_gen test split", "molecules": len(secondary),
            "models": {
                "schindler_sqe": _evaluate(secondary, "schindler_sqe", sqe_params, geidl),
                "geidl_eem_npa_overlap_unmeasured": _evaluate(secondary, "geidl_eem_npa", sqe_params, geidl),
                "context_bultinck_part1_eem": _evaluate(secondary, "bultinck_part1_eem", sqe_params, geidl),
                "context_gasteiger": _evaluate(secondary, "gasteiger", sqe_params, geidl),
            },
        },
    }
    save("c", result)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3 and not (len(sys.argv) == 2 and sys.argv[1] in ("c", "b-a1")):
        sys.exit("usage: schindler_sqe_check.py a4 <chargefw2-ccd_gen.json> | b <chargefw2-ccd_gen.json> | c")
    stage = sys.argv[1]
    if stage == "a4":
        print(json.dumps({k: v for k, v in stage_a4(pathlib.Path(sys.argv[2])).items() if k != "per_molecule_max_abs_diff"}, indent=1))
    elif stage == "b-a1":
        print(json.dumps(stage_b_a1(), indent=1))
    elif stage == "b":
        choice = json.loads((RESULTS / "a4.json").read_text(encoding="utf-8"))["runs_for_part_b"]
        out = stage_b(choice, pathlib.Path(sys.argv[2]))
        print(json.dumps({k: out[k] for k in ("B1", "B2", "model_reading", "strata", "conditioning", "refused_by_us")}, indent=1))
    elif stage == "c":
        out = stage_c()
        slim = {k: v for k, v in out["C_primary"].items() if k != "excluded_identical_to_CCD_gen_training"}
        print(json.dumps({"C_primary": slim, "C_secondary": out["C_secondary"]}, indent=1))
    else:
        sys.exit(f"unknown stage {stage}")
