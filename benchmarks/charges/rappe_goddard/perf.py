"""Amendment A8's QEq time gate.

    uv run --no-sync python benchmarks/charges/rappe_goddard/perf.py [--runs 3]

Times `ce.qeq_charges` alone (integrals, linear solves, hydrogen iteration) on
the frozen structures in tests/fixtures/charges/qeq_perf_conformers.csv, with
the shipped method: ADOPTED readings, experimental hydrogen set. Import,
parsing and conformer generation are outside the timed region by construction.

The gate (median of the runs): atorvastatin <= 5 s, aspirin <= 0.5 s. These are
acceptance measurements on one machine, recorded with its environment, and
never a CI timing test; the numerical gates live in the test suite.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import platform
import statistics
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem import charge_equilibration as ce  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "charges" / "qeq_perf_conformers.csv"
GATES = {"aspirin": 0.5, "atorvastatin": 5.0}


def structures() -> dict[str, tuple[list[str], np.ndarray]]:
    rows = list(csv.DictReader(line for line in FIXTURE.read_text(encoding="utf-8").splitlines() if not line.startswith("#")))
    out: dict[str, list] = {}
    for row in rows:
        out.setdefault(row["molecule"], []).append((int(row["index"]), row["element"], float(row["x"]), float(row["y"]), float(row["z"])))
    return {name: ([a[1] for a in sorted(atoms)], np.array([a[2:] for a in sorted(atoms)])) for name, atoms in out.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    runs = parser.parse_args().runs
    import rdkit

    print(f"environment: {platform.platform()}; {platform.processor() or platform.machine()}; Python {platform.python_version()}; numpy {np.__version__}; rdkit {rdkit.__version__}")
    print(f"{'molecule':14} {'atoms':>5} {'H %':>5} {'iter':>4} {'median s':>9}  runs                      gate")
    for name, (elements, coords) in structures().items():
        times = []
        result = None
        for _ in range(runs):
            start = time.perf_counter()
            result = ce.qeq_charges(elements, coords, hydrogen="experimental", readings=ce.ADOPTED)
            times.append(time.perf_counter() - start)
        median = statistics.median(times)
        gate = GATES.get(name)
        verdict = "" if gate is None else f"<= {gate} s: {'held' if median <= gate else 'FAILED'}"
        share = 100.0 * elements.count("H") / len(elements)
        print(f"{name:14} {len(elements):5} {share:5.1f} {result.iterations:4} {median:9.3f}  {', '.join(f'{t:.3f}' for t in times):24}  {verdict}")


if __name__ == "__main__":
    main()
