"""Round 3 Track 2, experiment E3: the shipped EEM on Ionescu et al. 2013's deposited fragments.

    uv run --no-sync python benchmarks/charges/consumers/ionescu2013_benchmark.py [SI directory]

An APPLICATION BENCHMARK (preregistration.md E3): Bultinck 2002 part I EEM,
as shipped, on the 41 deposited protein fragments and two test proteins,
against the deposit's "MPA/6-31G*/gas" charges. A protein-fragment domain at a
different QM level from Bultinck's fit: no gate, and no claim about small
molecules follows. The deposit is read in place and each file's SHA-256 is
recorded; only the per-fragment and summary outputs are committed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem import charge_equilibration as ce  # noqa: E402

DEFAULT_SI = pathlib.Path("D:/Xaero Stuff/Documents/Sci Downloads/ionescu2013_si")
SCHEME = "MPA/6-31G*/gas"
HERE = pathlib.Path(__file__).resolve().parent
ELEMENTS = ("H", "C", "N", "O")
SETS = {
    "training": ("ci400448n_si_005/training_set.pdb", "ci400448n_si_006/QM_EEM_q_training_set.csv"),
    "insulin": ("ci400448n_si_005/test_insulin_3E7Y.pdb", "ci400448n_si_006/QM_EEM_q_insulin.csv"),
    "ubiquitin": ("ci400448n_si_005/test_ubiquitin_1UBQ.pdb", "ci400448n_si_006/QM_EEM_q_ubiquitin.csv"),
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pdb(path: pathlib.Path) -> dict[str, list[tuple[float, float, float]]]:
    """MODEL id -> coordinates in file order. A file without MODEL records is one model, "1"."""
    models, current = {}, "1"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MODEL"):
            current = line.split()[1]
        elif line.startswith(("ATOM", "HETATM")):
            models.setdefault(current, []).append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
    return models


def read_charges(path: pathlib.Path) -> dict[str, tuple[list[str], list[float]]]:
    """Fragment id -> (elements, SCHEME charges), from whichever of the deposit's two CSV layouts this file uses."""
    rows = [r for r in csv.reader(io.StringIO(path.read_text(encoding="utf-8", errors="replace")), delimiter="\t")]
    out: dict[str, tuple[list[str], list[float]]] = {}
    if rows[0] and rows[0][0] == "Nr":  # one structure, one column per scheme
        column = rows[0].index(SCHEME)
        data = [r for r in rows[1:] if len(r) > column and r[0].strip()]
        return {"1": ([r[1] for r in data], [float(r[column]) for r in data])}
    in_scheme, fragment = False, None
    for r in rows:
        cells = [c.strip() for c in r]
        if cells and cells[0] == "QM scheme":
            in_scheme = cells[1] == SCHEME
            continue
        if not in_scheme or not any(cells):
            continue
        if cells[0] == "NSC":
            fragment = cells[1]
            out[fragment] = ([], [])
        elif fragment is not None and len(cells) >= 4 and cells[1].isdigit():
            out[fragment][0].append(cells[2])
            out[fragment][1].append(float(cells[3]))
    return out


def r_squared(x, y) -> float:
    x, y = np.asarray(x), np.asarray(y)
    return float(np.corrcoef(x, y)[0, 1] ** 2) if len(x) > 2 and x.std() > 0 and y.std() > 0 else math.nan


def run(si: pathlib.Path) -> dict:
    fragment_rows, pooled, populations, hashes = [], {}, {"source": 0, "applicable": 0, "excluded_S": 0, "excluded_Ca": 0,
                                                        "excluded_other": 0, "excluded_order": 0, "excluded_charge": 0}, {}
    for set_name, (pdb_name, csv_name) in SETS.items():
        pdb_path, csv_path = si / pdb_name, si / csv_name
        hashes[pdb_name], hashes[csv_name] = sha256(pdb_path), sha256(csv_path)
        coordinates, charges = read_pdb(pdb_path), read_charges(csv_path)
        for fragment, (elements, qm) in charges.items():
            populations["source"] += 1
            coords = coordinates.get(fragment) or (coordinates["1"] if len(coordinates) == 1 else None)
            present = set(elements)
            reason = ""
            if coords is None or len(coords) != len(elements):
                reason, key = f"PDB MODEL {fragment} has {0 if coords is None else len(coords)} atoms, charges {len(elements)}", "excluded_order"
            elif "S" in present:
                reason, key = "contains S (EEM part I parameterises H, C, N, O, F)", "excluded_S"
            elif "Ca" in present:
                reason, key = "contains Ca", "excluded_Ca"
            elif present - set(ELEMENTS) - {"F"}:
                reason, key = f"contains {sorted(present - set(ELEMENTS) - {'F'})}", "excluded_other"
            net = sum(qm)
            if not reason and abs(net - round(net)) > 0.01:
                reason, key = f"deposited charges sum to {net:.4f}, not an integer", "excluded_charge"
            if reason:
                populations[key] += 1
                fragment_rows.append([set_name, fragment, len(elements), "", "", "", reason])
                continue
            result = ce.eem_charges(elements, np.asarray(coords), int(round(net)))
            if result.status != "converged":
                populations["excluded_other"] += 1
                fragment_rows.append([set_name, fragment, len(elements), "", "", "", f"EEM {result.status}"])
                continue
            populations["applicable"] += 1
            eem = np.asarray(result.charges)
            err = eem - np.asarray(qm)
            fragment_rows.append([set_name, fragment, len(elements), int(round(net)), f"{r_squared(eem, qm):.4f}",
                                  f"{math.sqrt(float(np.mean(err ** 2))):.4f}", ""])
            for e, q_eem, q_qm in zip(elements, eem, qm):
                pooled.setdefault((set_name, e), ([], []))
                pooled[(set_name, e)][0].append(float(q_eem))
                pooled[(set_name, e)][1].append(q_qm)
    summary_rows = []
    for set_name in SETS:
        all_eem, all_qm = [], []
        for e in ELEMENTS:
            if (set_name, e) not in pooled:
                continue
            eem, qm = pooled[(set_name, e)]
            all_eem += eem
            all_qm += qm
            summary_rows.append([set_name, e, len(eem), f"{r_squared(eem, qm):.4f}", f"{math.sqrt(np.mean((np.array(eem) - qm) ** 2)):.4f}"])
        if all_eem:
            summary_rows.append([set_name, "All", len(all_eem), f"{r_squared(all_eem, all_qm):.4f}",
                                 f"{math.sqrt(np.mean((np.array(all_eem) - all_qm) ** 2)):.4f}"])
    header = (f"# preregistration.md E3: shipped EEM (Bultinck 2002 part I) against Ionescu 2013's \"{SCHEME}\" charges. "
              "An application benchmark, no gate.\n# Source SHA-256: " + "; ".join(f"{k} {v}" for k, v in hashes.items()) + "\n")
    for name, columns, rows in (("ionescu2013_fragments.csv", ["set", "fragment", "atoms", "net_charge", "r2", "rmsd", "excluded"], fragment_rows),
                                ("ionescu2013_summary.csv", ["set", "element", "n", "r2", "rmsd"], summary_rows)):
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\n").writerows([columns, *rows])
        (HERE / name).write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")
    print("populations:", populations)
    for row in summary_rows:
        print(" ", row)
    return {"populations": populations, "summary": summary_rows}


if __name__ == "__main__":
    run(pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SI)
