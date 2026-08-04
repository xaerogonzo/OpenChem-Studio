"""Score every strategy against whatever assigned spectra are available.

Run after `run_shieldings.py` has produced the shieldings for a method:

    uv run --no-sync python benchmarks/nmr/run_comparison.py "B3LYP def2-SVP"

Needs no ORCA -- it consumes the committed shieldings JSON, which is the
point of caching them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import score_hybrid as sh  # noqa: E402
from hybrid_strategies import BASELINES, STRATEGIES  # noqa: E402
from literature_shifts import SPECTRA  # noqa: E402
from run_shieldings import SHIELDINGS, slug  # noqa: E402


def main() -> None:
    method = sys.argv[1] if len(sys.argv) > 1 else "B3LYP def2-SVP"
    store = json.loads((SHIELDINGS / f"{slug(method)}.json").read_text(encoding="utf-8"))

    factors = sh.calibrate(store, "C")
    print(f"{method}: slope {factors.slope:.4f}  R^2 {factors.r_squared:.5f}  "
          f"residual RMS {factors.residual_rms:.3f} ppm\n")

    inputs = []
    for name, spectrum in SPECTRA.items():
        data, truth = sh.build_input(name, spectrum, store, factors, factors.residual_rms)
        if data is None:
            print(f"  (no shieldings for {name}, skipped)")
            continue
        inputs.append((data, truth))
    print(f"{len(inputs)} molecules, {sum(len(t) for _d, t in inputs)} assigned carbons\n")

    evaluations = [
        sh.evaluate(name, fn, inputs) for name, fn in {**BASELINES, **STRATEGIES}.items()
    ]
    print(sh.report(evaluations, f"{method} - all assigned carbons"))

    out = HERE / "reports"
    out.mkdir(exist_ok=True)
    (out / f"{slug(method)}_report.md").write_text(
        sh.report(evaluations, f"{method} - all assigned carbons"), encoding="utf-8"
    )
    for ev in evaluations:
        (out / f"{slug(method)}_{ev.name}_decisions.csv").write_text(
            sh.decision_matrix(ev), encoding="utf-8"
        )
    print(f"reports -> {out}")


if __name__ == "__main__":
    main()
