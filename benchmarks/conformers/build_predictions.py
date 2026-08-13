"""Runs the shipped conformer pipeline over the corpus and records what it found.

SEPARATE FROM SCORING, and deliberately: generation is minutes and
scoring is milliseconds, so predictions are produced once and scored many
times -- which also lets two algorithms be compared without regenerating
either. `benchmarks/naming/` already splits the same way.

The environment block is written INTO the predictions file rather than
merely printed. An RDKit upgrade can move every number here, and without
the version recorded beside the results there is nothing to say whether
the toolkit or the algorithm changed.

Usage:
    python build_predictions.py [--label NAME] [--seeds 5] [--embeddings 50]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import rdkit
from rdkit import Chem, RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from openchem.chem.conformer_providers import (  # noqa: E402
    DEFAULT_ENERGY_WINDOW,
    DEFAULT_RMS_THRESHOLD,
    RDKitConformerProvider,
    distinct_conformers,
    merge_candidates,
)

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent

#: Swept so a future change to either constant shows its whole SHAPE
#: rather than one number. The shipped pair sits in here; a threshold
#: that only looks good at its own value is what got us here.
RMS_SWEEP = [0.25, 0.35, 0.50, 0.75, 1.00]

#: The energy veto disabled, for the arm that shows what RMSD alone does.
#: A window of 0.0 vetoes nothing that is not already identical... so the
#: "no veto" arm is an INFINITE window: every pair agrees, so geometry
#: alone decides. Getting this backwards silently produces the wrong
#: control, which is why it is named rather than inlined.
NO_VETO = float("inf")

#: Seed bases are STRIDED, and the obvious `range(seeds)` is wrong.
#: `RDKitConformerProvider` uses `random_seed + attempt` so that the
#: embeddings within one run differ from each other -- which means
#: consecutive bases OVERLAP: base 0 draws seeds 0..49 and base 1 draws
#: 1..50, sharing 49 of 50 embeddings. Measured with the naive version,
#: all five "independent" arms returned identical counts for seven of
#: eight molecules, which reads as perfect stability and is really the
#: same run measured five times. A stride larger than any embedding
#: count keeps the arms disjoint.
SEED_STRIDE = 100_003


def _environment(seeds: int, embeddings: int) -> dict:
    return {
        "rdkit_version": rdkit.__version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "embedder": "ETKDGv3",
        # Explicit, never implicit: this flag moves ethylmorphine's union
        # from 17 to 25, so a predictions file must say which sampling
        # produced it or two files cannot be compared.
        "use_small_ring_torsions": RDKitConformerProvider.use_small_ring_torsions,
        "force_field": "MMFF94 (UFF fallback)",
        "rms_threshold": DEFAULT_RMS_THRESHOLD,
        "energy_window": DEFAULT_ENERGY_WINDOW,
        "seeds": seeds,
        "embeddings_per_seed": embeddings,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _one_seed(smiles: str, seed: int, embeddings: int) -> tuple[dict, list]:
    """`(what to record, the conformers it retained)`.

    The retained conformers come back so the caller can compare SETS
    across seeds -- they are RDKit mols and never reach the predictions
    file, which stores the resulting statistics instead.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"error": "SMILES did not parse"}, []
    batch = RDKitConformerProvider(random_seed=seed).generate_conformer_batch(
        mol, embeddings, optimize=True
    )
    sweep = {
        f"{threshold:.2f}": {
            "veto": len(distinct_conformers(batch.results, threshold, DEFAULT_ENERGY_WINDOW)),
            "rmsd_only": len(distinct_conformers(batch.results, threshold, NO_VETO)),
        }
        for threshold in RMS_SWEEP
    }
    # An INDEPENDENT reference: distinct converged energies, which is not
    # derived from the geometric comparison being benchmarked. A LOWER
    # bound -- enantiomeric conformers share an energy, so this undercounts.
    energies: list[float] = []
    for _mol, energy in batch.results:
        if energy is not None and not any(abs(energy - seen) < 0.05 for seen in energies):
            energies.append(energy)
    candidates = merge_candidates(batch.results, with_torsions=True)
    retained = distinct_conformers(batch.results)
    return {
        "seed": seed,
        "attempted": batch.attempted,
        "embedded": batch.embedded,
        "converged": batch.converged,
        "embedding_failures": batch.embedding_failures,
        "convergence_failures": batch.convergence_failures,
        "distinct": len(retained),
        "distinct_energies": len(energies),
        "threshold_sweep": sweep,
        "merge_candidates": _summarise(candidates),
    }, retained


def _set_overlap(per_seed: list[list]) -> dict:
    """How much the conformers found by different seeds are the SAME ones.

    WHY COUNTS ARE NOT ENOUGH. Five seeds each returning 14 conformers
    looks stable and is not, if they are 14 DIFFERENT conformers every
    time -- the search would then be sampling a different slice of the
    space on each run and no single run would be representative. The
    counts cannot tell those apart; this can.

    THE SAME CRITERION DECIDES SAMENESS WITHIN A RUN AND ACROSS RUNS, and
    that falls out for free rather than needing a second matching
    implementation: pooling two seeds and de-duplicating gives the union
    under exactly the shipped rule, so

        |A n B| = |A| + |B| - |A u B|

    is exact. A parallel matcher would be a second definition of "the
    same conformer" free to drift from the first.

    `union` pools every seed: it is the total the search found across all
    runs, and `coverage` (mean per seed / union) is the fraction of that
    one run typically finds. Coverage near 1.0 means the runs agree and
    a single run is representative; near 1/n means each run is finding
    its own private set.
    """
    runs = [r for r in per_seed if r]
    if len(runs) < 2:
        return {}
    pooled = distinct_conformers([item for run in runs for item in run])
    jaccards = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            union = len(distinct_conformers(runs[i] + runs[j]))
            intersection = len(runs[i]) + len(runs[j]) - union
            jaccards.append(intersection / union if union else 1.0)
    mean_per_seed = sum(len(r) for r in runs) / len(runs)
    return {
        "union": len(pooled),
        "mean_per_seed": round(mean_per_seed, 2),
        # 1.0 = every seed finds the whole discovered set.
        "coverage": round(mean_per_seed / len(pooled), 3) if pooled else None,
        "jaccard_mean": round(sum(jaccards) / len(jaccards), 3),
        "jaccard_min": round(min(jaccards), 3),
        "pairs": len(jaccards),
    }


def _one(c) -> dict:
    return {
        "rmsd": round(c.rmsd, 4),
        "energy_difference": None if c.energy_difference is None else round(c.energy_difference, 3),
        "tfd": None if c.tfd is None else round(c.tfd, 4),
        "max_dihedral_change": None if c.max_dihedral_change is None else round(c.max_dihedral_change, 1),
        "merged": c.merged,
        "candidate_origin": c.candidate_origin,
        "representative_origin": c.representative_origin,
    }


def _population(candidates, rank) -> dict:
    """One side of the merge decision, described the same way as the other.

    `rank` picks the extremes worth keeping in full, and it DIFFERS between
    the two populations on purpose -- see `_summarise`.
    """
    if not candidates:
        return {"pairs": 0}
    measured = [c for c in candidates if c.max_dihedral_change is not None]
    return {
        "pairs": len(candidates),
        "rmsd_min": round(min(c.rmsd for c in candidates), 4),
        "rmsd_max": round(max(c.rmsd for c in candidates), 4),
        # How many moved a real torsion, at three cuts rather than one, so
        # the SHAPE of the distribution survives into the file. A single
        # threshold here would be the same mistake the RMSD threshold made.
        "torsion_over_30": sum(1 for c in measured if c.max_dihedral_change > 30),
        "torsion_over_60": sum(1 for c in measured if c.max_dihedral_change > 60),
        "torsion_over_90": sum(1 for c in measured if c.max_dihedral_change > 90),
        # A diagnostic that could not answer is NOT a zero. Counted, so a
        # population that is mostly unmeasured cannot be read as a
        # population that mostly did not move.
        "torsion_unavailable": len(candidates) - len(measured),
        "worst": [_one(c) for c in sorted(candidates, key=rank)[:5]],
    }


def _summarise(candidates) -> dict:
    """Both sides of the merge decision, described symmetrically.

    A RECORD, not a raw dump. Storing every candidate put ethylmorphine
    alone at ~5000 entries and the file at 588 KB, which is then
    re-committed as a fresh blob every time the benchmark is
    regenerated -- for data `score.py` only ever reads in aggregate.
    The extremes are kept in full because they are the ones anybody
    investigating will want to see, and they are what the docstrings in
    `conformer_providers` quote.

    **THE MERGED SIDE USED TO BE A BARE COUNT, and it is the side that
    matters for "is de-duplication throwing things away".** A vetoed pair
    was RETAINED -- it is not a loss -- while a merged pair is a structure
    that no longer exists in the result. Reporting the first in detail and
    the second as an integer meant the discarded population was the one
    population nobody could look at.

    **THE TWO SIDES ARE RANKED BY DIFFERENT THINGS, deliberately.** A
    vetoed pair is interesting when the energy gap is large and the
    geometry saw nothing, so it ranks by dE. A merged pair is interesting
    when a real torsion moved and the merge happened anyway, and dE cannot
    express that -- ranking the merged side by dE returned five pairs
    differing by 0.27 kcal/mol and said nothing at all.
    """
    return {
        # Kept at the top level: `score.py` reads these, and the docstrings
        # in `conformer_providers` quote them.
        "examined": len(candidates),
        "vetoed": sum(1 for c in candidates if not c.merged),
        "merged_away": _population(
            [c for c in candidates if c.merged],
            rank=lambda c: -(c.max_dihedral_change or 0.0),
        ),
        "vetoed_merge": _population(
            [c for c in candidates if not c.merged],
            rank=lambda c: -(c.energy_difference or 0.0),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="shipped")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--embeddings", type=int, default=50)
    args = parser.parse_args()

    corpus = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    predictions = []
    for entry in corpus["molecules"]:
        started = time.time()
        pairs = [
            _one_seed(entry["smiles"], index * SEED_STRIDE, args.embeddings)
            for index in range(args.seeds)
        ]
        runs = [record for record, _retained in pairs]
        overlap = _set_overlap([retained for _record, retained in pairs])
        predictions.append({"name": entry["name"], "runs": runs, "set_overlap": overlap})
        counts = [r.get("distinct") for r in runs]
        summary = (
            f" union {overlap['union']:>3} coverage {overlap['coverage']:.2f}" if overlap else ""
        )
        print(
            f"  {entry['name']:<20} {str(counts):<24}{summary}  ({time.time() - started:.1f}s)",
            flush=True,
        )

    out = HERE / f"predictions_{args.label}.json"
    out.write_text(
        json.dumps(
            {
                "label": args.label,
                "environment": _environment(args.seeds, args.embeddings),
                "predictions": predictions,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
