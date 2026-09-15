"""TRIAGE.md check 2.2: Mathieu 2007 Table I's "EEM (EQ)" row against the shipped EEM.

    uv run --no-sync python benchmarks/charges/models/mathieu_eem_check.py [--freeze]

`--freeze` reads the EPAPS folder in Alex's Sci Downloads and writes
tests/fixtures/charge_models/mathieu2007_eq.csv; without it the script reads
only that fixture. Metrics as corrected in TRIAGE.md 2.2: R^2 per element and
over all atoms (squared Pearson), and eq 15's Delta-q (element-averaged mean
squared deviation, no square root). The shipped `ce.eem_charges` is called
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem import charge_equilibration as ce  # noqa: E402

EPAPS = pathlib.Path(r"D:\Xaero Stuff\Documents\Sci Downloads\mathieu2007_si\A6.11.108.EPAPS\EQ")
FIXTURE = ROOT / "tests" / "fixtures" / "charge_models" / "mathieu2007_eq.csv"
ELEMENTS = ("C", "H", "N", "O", "F")
#: Mathieu 2007, Table I, "EEM (EQ)", read from the rendered page.
PRINTED = {"C": 0.96, "H": 0.81, "N": 0.95, "O": 0.66, "F": 0.36, "All": 0.97, "dq": 0.0668}


def freeze() -> None:
    files = sorted(EPAPS.glob("*.xyz"))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["molecule", "atom", "element", "x", "y", "z", "mulliken"])
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        count = int(lines[0].split()[0])
        for k, line in enumerate(lines[2:2 + count]):
            element, x, y, z, q = line.split()[:5]
            writer.writerow([path.stem, k + 1, element, x, y, z, q])
    header = ("# D. Mathieu, J. Chem. Phys. 2007, 127, 224103, EPAPS E-JCPSA6-127-509743, EQ directory, as deposited:\n"
              "# OpenBabel-generated .xyz, each atom's coordinates (angstrom) followed by its B3LYP/6-31G* Mulliken charge.\n"
              f"# {len(files)} files, frozen by benchmarks/charges/models/mathieu_eem_check.py --freeze.\n")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")
    print(f"froze {len(files)} molecules into {FIXTURE}")


def molecules() -> dict[str, list[dict[str, str]]]:
    lines = [l for l in FIXTURE.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in csv.DictReader(lines):
        out[row["molecule"]].append(row)
    return dict(out)


def r_squared(a: list[float], b: list[float]) -> float:
    return float(np.corrcoef(a, b)[0, 1] ** 2)


def evaluate() -> dict:
    data = molecules()
    excluded, refused, nonzero = [], [], []
    pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for name, atoms in sorted(data.items()):
        elements = [a["element"] for a in atoms]
        if any(e not in ELEMENTS for e in elements):
            excluded.append(name)
            continue
        mulliken = [float(a["mulliken"]) for a in atoms]
        net = round(sum(mulliken))
        if abs(sum(mulliken)) > 0.01:
            nonzero.append((name, round(sum(mulliken), 4)))
        coords = np.array([[float(a["x"]), float(a["y"]), float(a["z"])] for a in atoms])
        result = ce.eem_charges(elements, coords, float(net))
        if result.status != "converged":
            refused.append((name, result.status))
            continue
        for e, q, m in zip(elements, result.charges, mulliken):
            pairs[e].append((float(q), m))
    metrics = {e: r_squared([p[0] for p in pairs[e]], [p[1] for p in pairs[e]]) for e in ELEMENTS if len(pairs[e]) > 2}
    everything = [p for e in ELEMENTS for p in pairs[e]]
    metrics["All"] = r_squared([p[0] for p in everything], [p[1] for p in everything])
    present = [e for e in ELEMENTS if pairs[e]]
    metrics["dq"] = sum(sum((q - m) ** 2 for q, m in pairs[e]) / len(pairs[e]) for e in present) / len(present)
    return {
        "molecules": len(data), "excluded": excluded, "refused": refused, "nonzero_mulliken_sum": nonzero,
        "counts": {e: len(pairs[e]) for e in ELEMENTS}, "metrics": metrics,
        "diagnostics": {"sqrt_dq": math.sqrt(metrics["dq"]),
                        "all_atom_rms": math.sqrt(sum((q - m) ** 2 for q, m in everything) / len(everything))},
    }


def verdict(report: dict) -> dict[str, bool]:
    out = {}
    for key, printed in PRINTED.items():
        tolerance = 0.00005 if key == "dq" else 0.005
        out[key] = abs(report["metrics"][key] - printed) <= tolerance
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    if parser.parse_args().freeze:
        freeze()
    report = evaluate()
    checks = verdict(report)
    print(f"molecules {report['molecules']}, excluded {len(report['excluded'])}, refused {len(report['refused'])}, "
          f"non-neutral Mulliken sums {report['nonzero_mulliken_sum']}")
    print("atoms per element", report["counts"])
    for key, printed in PRINTED.items():
        print(f"  {key:4} reconstructed {report['metrics'][key]:.4f}  printed {printed}  {'PASS' if checks[key] else 'MISS'}")
    print("  diagnostics", {k: round(v, 4) for k, v in report["diagnostics"].items()})
    if report["excluded"]:
        print("  excluded:", report["excluded"])


if __name__ == "__main__":
    main()
