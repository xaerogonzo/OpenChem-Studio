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
        "force_field": "MMFF94 (UFF fallback)",
        "rms_threshold": DEFAULT_RMS_THRESHOLD,
        "energy_window": DEFAULT_ENERGY_WINDOW,
        "seeds": seeds,
        "embeddings_per_seed": embeddings,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _one_seed(smiles: str, seed: int, embeddings: int) -> dict:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {"error": "SMILES did not parse"}
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
    return {
        "seed": seed,
        "attempted": batch.attempted,
        "embedded": batch.embedded,
        "converged": batch.converged,
        "embedding_failures": batch.embedding_failures,
        "convergence_failures": batch.convergence_failures,
        "distinct": len(distinct_conformers(batch.results)),
        "distinct_energies": len(energies),
        "threshold_sweep": sweep,
        "merge_candidates": _summarise(candidates),
    }


def _summarise(candidates) -> dict:
    """Aggregates plus the few pairs worth looking at individually.

    A RECORD, not a raw dump. Storing every candidate put ethylmorphine
    alone at ~5000 entries and the file at 588 KB, which is then
    re-committed as a fresh blob every time the benchmark is
    regenerated -- for data `score.py` only ever reads in aggregate.
    The extremes are kept in full because they are the ones anybody
    investigating will want to see, and they are what the docstrings in
    `conformer_providers` quote.
    """
    def _one(c) -> dict:
        return {
            "rmsd": round(c.rmsd, 4),
            "energy_difference": None if c.energy_difference is None else round(c.energy_difference, 3),
            "tfd": None if c.tfd is None else round(c.tfd, 4),
            "max_dihedral_change": None if c.max_dihedral_change is None else round(c.max_dihedral_change, 1),
            "merged": c.merged,
        }

    vetoed = [c for c in candidates if not c.merged]
    return {
        "examined": len(candidates),
        "vetoed": len(vetoed),
        # The band the veto operates in -- if these ever reach down to
        # _IDENTICAL_SHAPE_RMSD the floor is doing nothing.
        "vetoed_rmsd_min": round(min((c.rmsd for c in vetoed), default=0.0), 4),
        "vetoed_rmsd_max": round(max((c.rmsd for c in vetoed), default=0.0), 4),
        "worst": [
            _one(c)
            for c in sorted(candidates, key=lambda c: -(c.energy_difference or 0.0))[:5]
        ],
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
        runs = [
            _one_seed(entry["smiles"], index * SEED_STRIDE, args.embeddings)
            for index in range(args.seeds)
        ]
        predictions.append({"name": entry["name"], "runs": runs})
        counts = [r.get("distinct") for r in runs]
        print(f"  {entry['name']:<20} {counts}  ({time.time() - started:.1f}s)", flush=True)

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
