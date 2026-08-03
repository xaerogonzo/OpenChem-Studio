"""Is the model's edge on the `rough` band real, or is it nothing?

The difference is 0.05 ppm on 2,024 atoms and calling that "noise" by eye
is exactly the kind of claim this project does not accept. Paired
bootstrap over molecules -- not over atoms, because atoms of one molecule
share a structure and an assignment, so resampling them independently
would understate the interval.
"""
from __future__ import annotations

import gzip
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as nmr_ml  # noqa: E402

WORK = Path("D:/Random Programs/OpenChemStudio_Data/nmr_train_work")
BANDS = nmr_ml.QUALITY_BANDS


def main() -> None:
    held = dict(np.load(WORK / "heldout.npz"))
    with gzip.open(WORK / "models.pkl.gz", "rb") as handle:
        models = pickle.load(handle)

    for element, code in (("C", 0), ("H", 1)):
        rows = held["elements"] == code
        features = held["features"][rows]
        truth = held["targets"][rows].astype(float)
        hose = held["hose_shift"][rows].astype(float)
        quality = held["hose_quality"][rows]
        records = held["records"][rows]
        covered = ~np.isnan(hose)

        fallback = float(np.median(truth))
        baseline = np.where(covered, hose, fallback)
        predicted = baseline + np.asarray(models[element]["estimator"].predict(features), dtype=float)

        print(f"\n=== {element}")
        for band in ("good", "medium", "rough"):
            mask = (quality == BANDS.index(band)) & covered
            hose_error = np.abs(hose[mask] - truth[mask])
            model_error = np.abs(predicted[mask] - truth[mask])
            delta = model_error - hose_error  # negative => model better

            groups = np.unique(records[mask])
            index_of = {record: i for i, record in enumerate(groups)}
            owner = np.asarray([index_of[r] for r in records[mask]])
            by_group = [delta[owner == i] for i in range(len(groups))]

            rng = np.random.default_rng(0)
            draws = np.empty(4000)
            for i in range(draws.size):
                pick = rng.integers(0, len(by_group), len(by_group))
                draws[i] = np.concatenate([by_group[j] for j in pick]).mean()
            low, high = np.percentile(draws, [2.5, 97.5])
            print(
                f"  {band:7} n={mask.sum():6,} over {len(groups):4,} molecules   "
                f"HOSE {hose_error.mean():6.2f}  model {model_error.mean():6.2f}   "
                f"delta {delta.mean():+6.3f}  95% CI [{low:+.2f}, {high:+.2f}]"
                f"   {'model better' if high < 0 else 'HOSE better' if low > 0 else 'not distinguishable'}"
            )


if __name__ == "__main__":
    main()
