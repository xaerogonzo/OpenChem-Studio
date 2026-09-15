"""TRIAGE.md check 2.2: Mathieu 2007 Table I's "EEM (EQ)" row against the shipped EEM.

    uv run --no-sync python benchmarks/charges/models/mathieu_eem_check.py [--freeze]

`--freeze` reads the EPAPS folder in Alex's Sci Downloads and writes the EQ and
TS fixtures (tests/fixtures/charge_models/mathieu2007_{eq,ts}.csv) and their
source manifests; without it the script reads
only that fixture. Metrics as corrected in TRIAGE.md 2.2: R^2 per element and
over all atoms (squared Pearson), and eq 15's Delta-q (element-averaged mean
squared deviation, no square root). The shipped `ce.eem_charges` is called
unchanged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import math
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem import charge_equilibration as ce  # noqa: E402

DEPOSIT = pathlib.Path(r"D:\Xaero Stuff\Documents\Sci Downloads\mathieu2007_si")
EPAPS = DEPOSIT / "A6.11.108.EPAPS" / "EQ"
FIXTURES = ROOT / "tests" / "fixtures" / "charge_models"
FIXTURE = FIXTURES / "mathieu2007_eq.csv"
#: set -> (source directory, fixture, manifest); TS added for checks 2.4 and 2.5.
SETS = {
    "EQ": (EPAPS, FIXTURE, FIXTURES / "mathieu2007_eq_manifest.csv"),
    "TS": (DEPOSIT / "A6.11.108.EPAPS" / "TS", FIXTURES / "mathieu2007_ts.csv", FIXTURES / "mathieu2007_ts_manifest.csv"),
}
ELEMENTS = ("C", "H", "N", "O", "F")
#: Mathieu 2007, Table I, "EEM (EQ)", read from the rendered page.
PRINTED = {"C": 0.96, "H": 0.81, "N": 0.95, "O": 0.66, "F": 0.36, "All": 0.97, "dq": 0.0668}
MANIFEST_COLUMNS = ["kind", "file", "sha256", "atoms", *ELEMENTS, "mulliken_sum", "coordinate_sum", "abs_charge_sum"]


def _atom_lines(path: pathlib.Path) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    count = int(lines[0].split()[0])
    return [line.split()[:5] for line in lines[2:2 + count]]


def checksums(atoms: list[list[str]]) -> dict[str, str]:
    """Exact decimal sums of the deposited strings, so the fixture can be checked against them."""
    from decimal import Decimal
    return {
        "mulliken_sum": str(sum((Decimal(a[4]) for a in atoms), Decimal(0))),
        "coordinate_sum": str(sum((Decimal(a[1]) + Decimal(a[2]) + Decimal(a[3]) for a in atoms), Decimal(0))),
        "abs_charge_sum": str(sum((abs(Decimal(a[4])) for a in atoms), Decimal(0))),
    }


def freeze(set_name: str = "EQ") -> None:
    folder, fixture, manifest = SETS[set_name]
    files = sorted(folder.glob("*.xyz"))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["molecule", "atom", "element", "x", "y", "z", "mulliken"])
    rows = []
    for path in files:
        atoms = _atom_lines(path)
        for k, (element, x, y, z, q) in enumerate(atoms):
            writer.writerow([path.stem, k + 1, element, x, y, z, q])
        counts = [sum(1 for a in atoms if a[0] == e) for e in ELEMENTS]
        rows.append(["xyz", path.name, hashlib.sha256(path.read_bytes()).hexdigest(), len(atoms), *counts, *checksums(atoms).values()])
    header = (f"# D. Mathieu, J. Chem. Phys. 2007, 127, 224103, EPAPS E-JCPSA6-127-509743, {set_name} directory, as deposited:\n"
              "# OpenBabel-generated .xyz, each atom's coordinates (angstrom) followed by its B3LYP/6-31G* Mulliken charge.\n"
              f"# {len(files)} files, frozen by benchmarks/charges/models/mathieu_eem_check.py --freeze.\n")
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")
    readme = DEPOSIT / "README.TXT"
    out = io.StringIO()
    mw = csv.writer(out, lineterminator="\n")
    mw.writerow(MANIFEST_COLUMNS)
    mw.writerow(["readme", readme.name, hashlib.sha256(readme.read_bytes()).hexdigest()] + [""] * (len(MANIFEST_COLUMNS) - 3))
    mw.writerow(["archive", "A6.11.108.EPAPS.ZIP", "NOT HELD"] + [""] * (len(MANIFEST_COLUMNS) - 3))
    mw.writerows(rows)
    manifest.write_text(f"# Source manifest for {fixture.name}: SHA-256 of every deposited file read, and exact decimal checksums.\n"
                        "# The deposit's ZIP is listed by README.TXT but only its extracted directories are held.\n" + out.getvalue(),
                        encoding="utf-8", newline="\n")
    print(f"froze {len(files)} {set_name} molecules into {fixture} and {manifest.name}")


def molecules(fixture: pathlib.Path = FIXTURE) -> dict[str, list[dict[str, str]]]:
    lines = [l for l in fixture.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
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
        for set_name in SETS:
            freeze(set_name)
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
