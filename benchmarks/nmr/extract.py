"""Turn one split of nmrshiftdb2 into model-ready rows.

Run once per split. The training split is featurised against an index
built from ITSELF, with the leave-one-out correction applied; the held-out
split is featurised against that same index with no correction, because
that is exactly the situation a real prediction is in.

    python benchmarks/nmr/extract.py train.sd index.sqlite train.npz --leave-one-out
    python benchmarks/nmr/extract.py heldout.sd index.sqlite heldout.npz

Every row also carries what the plain HOSE lookup would have answered and
how it rated itself, so the baseline, the model and the hybrid are all
scored on one identical set of atoms. Scoring them on separately-collected
sets is the way to compare coverage while believing you compared accuracy.

The row-building itself lives in `chem/nmr_ml.py`, not here: the in-app
trainer has to produce byte-identical features and the only reliable way
to ensure that is to share the loop.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as nmr_ml  # noqa: E402
from openchem.chem.nmr_database import connect  # noqa: E402

SPHERES = 6


def extract(sdf: Path, index: Path, destination: Path, leave_one_out: bool) -> None:
    connection = connect(index)
    features: list[list[float]] = []
    targets: list[float] = []
    elements: list[int] = []
    records: list[int] = []
    hose_shift: list[float] = []
    hose_quality: list[int] = []

    started = time.time()

    def progress(spectra: int) -> None:
        print(
            f"  {spectra:,} spectra  {len(targets):,} rows  {time.time() - started:.0f}s",
            flush=True,
        )

    uncorrected: list[list[float]] = []

    for row in nmr_ml.training_rows(
        sdf, connection, SPHERES, correct_leakage=leave_one_out, on_progress=progress
    ):
        features.append(row.features)
        targets.append(row.shift)
        elements.append(0 if row.element == "C" else 1)
        records.append(row.record)
        hose_shift.append(row.hose_shift)
        hose_quality.append(row.hose_quality)
        if leave_one_out:
            uncorrected.append(row.uncorrected_lookup)
    connection.close()

    np.savez_compressed(
        destination,
        features=np.asarray(features, dtype=np.float32),
        targets=np.asarray(targets, dtype=np.float32),
        elements=np.asarray(elements, dtype=np.int8),
        records=np.asarray(records, dtype=np.int32),
        hose_shift=np.asarray(hose_shift, dtype=np.float32),
        hose_quality=np.asarray(hose_quality, dtype=np.int8),
        # Empty on the held-out split, where there is nothing to correct.
        uncorrected=np.asarray(uncorrected, dtype=np.float32),
    )
    print(f"{len(targets):,} rows -> {destination} in {time.time() - started:.0f}s")


if __name__ == "__main__":
    extract(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        Path(sys.argv[3]),
        leave_one_out="--leave-one-out" in sys.argv,
    )
