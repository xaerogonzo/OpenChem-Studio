"""Scores a conformer de-duplication run against the corpus references.

WHAT THIS CAN AND CANNOT TELL YOU. Half the references are textbook
counts and half are computational LOWER BOUNDS -- "at least this many
minima were found under this protocol", not "the molecule has this many
conformers". A run that exceeds a lower bound has not failed; a run that
falls short of one has. Those are different tests and the table marks
which is which rather than averaging them into a single score.

It also reports what the counts alone hide:

  * the threshold sweep, with and without the energy veto, so a change to
    either constant shows its whole shape rather than one number;
  * RMSD / TFD / max-dihedral for pairs that were close enough
    geometrically to be merge candidates -- the population the veto acts
    on, and the only one whose diagnosis says anything;
  * seed-to-seed stability as numbers, with NO hardcoded verdict about
    what "stable" is. A human reads it. That is reported two ways,
    because counts alone hide the interesting failure: five seeds each
    returning 14 conformers looks stable and is not, if they are 14
    DIFFERENT conformers every time. So the SETS are compared as well --
    `union` is what all seeds found pooled, and `coverage` is the
    fraction of it a single run typically finds.

Usage:
    python score.py predictions_shipped.json
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: Passing a lower bound is fine; falling short of it is not. Spelled out
#: because "found more than the reference" reads like a failure in a
#: table of numbers unless something says otherwise.
OK = "ok"
SHORT = "SHORT"
OVER = "over"


def _verdict(found: float, reference: int, reference_type: str) -> str:
    if reference_type == "computational_lower_bound":
        return OK if found >= reference else SHORT
    if found == reference:
        return OK
    return OVER if found > reference else SHORT


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    molecules = corpus["molecules"]
    predictions = payload["predictions"]

    # The same deliberate guard benchmarks/naming/score.py has: a stale
    # predictions file is REFUSED rather than silently mis-scored against
    # a corpus it was not generated for.
    if len(predictions) != len(molecules):
        print(
            f"REFUSED: predictions cover {len(predictions)} molecules, "
            f"corpus has {len(molecules)}. This predictions file was generated "
            f"against a different corpus revision -- regenerate it with "
            f"build_predictions.py rather than scoring it."
        )
        return 1
    mismatched = [
        (p["name"], m["name"])
        for p, m in zip(predictions, molecules)
        if p["name"] != m["name"]
    ]
    if mismatched:
        print(f"REFUSED: predictions are in a different order to the corpus: {mismatched[:3]}")
        return 1

    env = payload.get("environment", {})
    print(f"label: {payload.get('label')}")
    print(
        "  rdkit {rdkit_version} | {embedder} | {force_field}\n"
        "  rms_threshold {rms_threshold} | energy_window {energy_window} | "
        "{seeds} seeds x {embeddings_per_seed} embeddings".format(**env)
    )
    print()

    print(
        f"{'molecule':<20} {'ref':>5} {'type':<12} {'found':>12} {'E-bound':>8} {'verdict':>8}"
    )
    print("-" * 72)
    failures = 0
    for entry, prediction in zip(molecules, predictions):
        runs = [r for r in prediction["runs"] if "error" not in r]
        if not runs:
            print(f"{entry['name']:<20} {'':>5} {'':<12} {'GENERATION FAILED':>12}")
            failures += 1
            continue
        found = [r["distinct"] for r in runs]
        bound = [r["distinct_energies"] for r in runs]
        mean = statistics.mean(found)
        verdict = _verdict(mean, entry["reference"], entry["reference_type"])
        failures += verdict == SHORT
        label = "textbook" if entry["reference_type"] == "textbook" else "lower bound"
        spread = f"{mean:.1f} [{min(found)}-{max(found)}]"
        print(
            f"{entry['name']:<20} {entry['reference']:>5} {label:<12} {spread:>12} "
            f"{statistics.mean(bound):>8.1f} {verdict:>8}"
        )

    print()
    print("seed stability, COUNTS (distinct conformers per seed)")
    print(f"{'molecule':<20} {'mean':>6} {'min':>5} {'max':>5} {'range':>6} {'stdev':>6}   runs")
    print("-" * 78)
    for entry, prediction in zip(molecules, predictions):
        found = [r["distinct"] for r in prediction["runs"] if "error" not in r]
        if not found:
            continue
        stdev = statistics.stdev(found) if len(found) > 1 else 0.0
        print(
            f"{entry['name']:<20} {statistics.mean(found):>6.1f} {min(found):>5} "
            f"{max(found):>5} {max(found) - min(found):>6} {stdev:>6.2f}   {found}"
        )

    print()
    print("seed stability, SETS -- do the seeds find the SAME conformers?")
    print("  union    distinct conformers found by all seeds pooled")
    print("  coverage mean per seed / union. 1.00 = every run finds the whole set;")
    print("           1/nseeds = every run finds its own private set.")
    print("  jaccard  |A n B| / |A u B| over seed pairs, same sameness rule as the dedup")
    print(f"{'molecule':<20} {'union':>6} {'mean/seed':>10} {'coverage':>9} {'jacc mean':>10} {'jacc min':>9}")
    print("-" * 78)
    for entry, prediction in zip(molecules, predictions):
        overlap = prediction.get("set_overlap") or {}
        if not overlap:
            print(f"{entry['name']:<20} {'(needs >=2 seeds)':>6}")
            continue
        print(
            f"{entry['name']:<20} {overlap['union']:>6} {overlap['mean_per_seed']:>10.2f} "
            f"{overlap['coverage']:>9.2f} {overlap['jaccard_mean']:>10.3f} "
            f"{overlap['jaccard_min']:>9.3f}"
        )

    print()
    print("threshold sweep, mean distinct across seeds (veto / RMSD alone)")
    thresholds = sorted(predictions[0]["runs"][0]["threshold_sweep"], key=float)
    print(f"{'molecule':<20} " + " ".join(f"{t:>11}" for t in thresholds))
    print("-" * 72)
    for entry, prediction in zip(molecules, predictions):
        runs = [r for r in prediction["runs"] if "error" not in r]
        if not runs:
            continue
        cells = []
        for threshold in thresholds:
            veto = statistics.mean(r["threshold_sweep"][threshold]["veto"] for r in runs)
            plain = statistics.mean(r["threshold_sweep"][threshold]["rmsd_only"] for r in runs)
            cells.append(f"{veto:>5.1f}/{plain:<5.1f}")
        print(f"{entry['name']:<20} " + " ".join(cells))

    print()
    print("merge candidates: pairs close enough geometrically to merge, and what")
    print("the other measures said. A kept-apart pair with a LOW max-dihedral is")
    print("one where both geometric measures were blind and only energy saw it.")
    print(f"{'molecule':<20} {'pairs':>6} {'vetoed':>7} {'worst dE':>9} {'its TFD':>8} {'its maxDih':>11}")
    print("-" * 72)
    for entry, prediction in zip(molecules, predictions):
        summaries = [r["merge_candidates"] for r in prediction["runs"] if "error" not in r]
        examined = sum(s["examined"] for s in summaries)
        if not examined:
            print(f"{entry['name']:<20} {0:>6}")
            continue
        vetoed = sum(s["vetoed"] for s in summaries)
        worst = max(
            (c for s in summaries for c in s["worst"]),
            key=lambda c: c["energy_difference"] or 0.0,
        )
        print(
            f"{entry['name']:<20} {examined:>6} {vetoed:>7} "
            f"{worst['energy_difference'] or 0:>9.2f} {worst['tfd'] if worst['tfd'] is not None else -1:>8.3f} "
            f"{worst['max_dihedral_change'] if worst['max_dihedral_change'] is not None else -1:>11.1f}"
        )

    print()
    print(f"{failures} molecule(s) below reference." if failures else "No molecule below reference.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
