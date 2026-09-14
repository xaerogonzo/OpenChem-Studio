"""Amendment A9's O9 study on the frozen corpus.

    uv run --no-sync python benchmarks/charges/rappe_goddard/o9_study.py

For each molecule in tests/fixtures/charges/o9_corpus_conformers.csv: the
production QEq solve (ADOPTED, experimental set) and whether a bound was ever
or finally active; then, at that solve's hydrogen charges, the paper's bound
procedure against the constrained minimum. Writes o9_study.csv beside this file
and prints the aggregates. Research only: nothing here changes a result.
"""

from __future__ import annotations

import csv
import pathlib
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from openchem.chem import charge_equilibration as ce  # noqa: E402
import qeq_bounded_qp as qp  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "o9_corpus_conformers.csv"


def corpus():
    rows = list(csv.DictReader(line for line in FIXTURE.read_text(encoding="utf-8").splitlines() if not line.startswith("#")))
    molecules: dict[str, dict] = {}
    for row in rows:
        entry = molecules.setdefault(row["molecule"], {"category": row["category"], "smiles": row["smiles"], "net": float(row["net_charge"]), "atoms": []})
        entry["atoms"].append((int(row["index"]), row["element"], float(row["x"]), float(row["y"]), float(row["z"])))
    for entry in molecules.values():
        entry["atoms"].sort()
        entry["elements"] = [a[1] for a in entry["atoms"]]
        entry["coords"] = np.array([a[2:] for a in entry["atoms"]])
    return molecules


def main() -> None:
    out_rows = []
    by_category: dict[str, Counter] = defaultdict(Counter)
    for name, entry in corpus().items():
        elements, coords, net = entry["elements"], entry["coords"], entry["net"]
        result = ce.qeq_charges(elements, coords, net, hydrogen="experimental", readings=ce.ADOPTED)
        final_active = dict(getattr(result, "final_active_atoms", result.clamped))
        ever = bool(getattr(result, "ever_clamped", False))
        row = {"molecule": name, "category": entry["category"], "atoms": len(elements), "net_charge": net,
               "status": result.status, "iterations": result.iterations, "ever_clamped": ever,
               "final_active": ";".join(f"{elements[i]}{i}@{b:+g}" for i, b in sorted(final_active.items()))}
        stats = by_category[entry["category"]]
        stats["molecules"] += 1
        stats["converged"] += result.status == "converged"
        stats["ever_clamped"] += ever
        stats["final_active"] += bool(final_active)
        if result.status == "converged":
            q_h = {i: float(result.charges[i]) for i, e in enumerate(elements) if e == "H"}
            hardness, chi, _ = ce.qeq_hardness_matrix(elements, coords, q_h, "experimental", ce.ADOPTED)
            bounds = [ce.charge_bounds(e) for e in elements]
            lower, upper = np.array([b[0] for b in bounds]), np.array([b[1] for b in bounds])
            paper = ce.solve_bounded(hardness, chi, net, lower, upper).charges
            minimum = qp.constrained_minimum(hardness, chi, net, lower, upper)
            paper_optimal = qp.kkt_violation(hardness, chi, net, lower, upper, paper) <= 1e-9
            paper_active = {i for i in range(len(elements)) if paper[i] <= lower[i] + 1e-12 or paper[i] >= upper[i] - 1e-12}
            status_differs = sorted(paper_active ^ set(minimum.active))
            diff = paper - minimum.charges
            row.update({
                "tangent_min_eig": qp.tangent_min_eigenvalue(hardness),
                "paper_kkt_optimal": paper_optimal,
                "max_abs_dq": float(np.max(np.abs(diff))),
                "rms_dq": float(np.sqrt(np.mean(diff * diff))),
                "active_status_differs": ";".join(f"{elements[i]}{i}" for i in status_differs),
                "energy_paper_minus_opt_eV": qp.energy(hardness, chi, paper) - qp.energy(hardness, chi, minimum.charges),
                "qp_released": minimum.released,
            })
            stats["paper_not_optimal"] += not paper_optimal
        out_rows.append(row)
    fields = sorted({key for row in out_rows for key in row}, key=lambda k: list(out_rows[0]).index(k) if k in out_rows[0] else 99)
    with open(HERE / "o9_study.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)
    total = Counter()
    for stats in by_category.values():
        total.update(stats)
    print(f"molecules {total['molecules']}; converged {total['converged']}; ever clamped {total['ever_clamped']}; "
          f"final active bound {total['final_active']}; paper procedure not KKT-optimal {total['paper_not_optimal']}")
    for category, stats in sorted(by_category.items()):
        if stats["final_active"] or stats["ever_clamped"] or stats["paper_not_optimal"] or stats["converged"] < stats["molecules"]:
            print(f"  {category:22} {dict(stats)}")
    worst = sorted((r for r in out_rows if "max_abs_dq" in r), key=lambda r: -r["max_abs_dq"])[:5]
    for r in worst:
        print(f"  largest paper-vs-optimum: {r['molecule']:28} max|dq| {r['max_abs_dq']:.2e} e, dE {r['energy_paper_minus_opt_eV']:.2e} eV, final active {r['final_active'] or '-'}")


if __name__ == "__main__":
    main()
