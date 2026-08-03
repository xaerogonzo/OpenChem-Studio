"""Train the shift model and score it against the HOSE lookup it corrects.

THE PROTOCOL IS FIXED and matches the one recorded in
`chem/nmr_database.py`: the index is rebuilt from every record except each
twentieth, and those twentieth molecules are then predicted against their
own measured shifts. A different split produces numbers that cannot be
compared with the table already in that docstring, which makes them worth
nothing.

    python benchmarks/nmr/extract.py train.sd idx.sqlite train.npz --leave-one-out
    python benchmarks/nmr/extract.py heldout.sd idx.sqlite heldout.npz
    python benchmarks/nmr/holdout.py train.npz heldout.npz --importance

Three predictors are scored on ONE identical set of atoms:

  * HOSE     -- the lookup exactly as it ships.
  * model    -- the gradient-boosted regressor alone.
  * hybrid   -- lookup where it rates itself confident, model where it
                does not.

Reported per quality band, because the bands are the whole point: the
lookup's `good` band is already better than a scaled ab initio
calculation, and a headline average that mixes it with `rough` hides both
the thing worth keeping and the thing worth fixing.

TWO CHOICES HERE ARE MEASURED RATHER THAN ASSUMED, both switchable:

  * `--target residual` fits `shift - lookup` instead of `shift`. A
    regression tree predicts a piecewise constant, so asking one to
    reproduce a 0-220 ppm axis makes it a staircase, and a staircase
    cannot beat a lookup that is already within 1.2 ppm. Fitting the
    correction instead leaves the tree doing what it is good at.
  * `--no-hash` drops the hashed-HOSE categoricals.

Iteration count is chosen on `dev` -- every twentieth record OF THE
TRAINING FILE -- so no molecule is shared with the fit or the held-out
set. Choosing it on a random row split would leak: atoms of one molecule
are correlated and several would land on both sides.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import features as nmr_ml  # noqa: E402

BANDS = nmr_ml.QUALITY_BANDS
ELEMENT_CODES = {"C": 0, "H": 1}
SPHERES = 6


def load(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def first_available_mean(block: np.ndarray) -> np.ndarray:
    """The deepest sphere that still had enough evidence, per row.

    This is the lookup's own answer recovered from the feature block, and
    on training rows that block is the leave-one-out one -- so the
    baseline a training row is corrected against is the baseline it would
    have had if it were not in the index. Using the uncorrected lookup
    here instead would hand the model its own answer through the back
    door.
    """
    means = block[:, 0::3]
    found = ~np.isnan(means)
    index = np.argmax(found, axis=1)
    value = means[np.arange(means.shape[0]), index]
    return np.where(found.any(axis=1), value, np.nan)


def scores(errors: np.ndarray) -> tuple[float, float, int]:
    if errors.size == 0:
        return float("nan"), float("nan"), 0
    return float(np.mean(errors)), float(np.median(errors)), int(errors.size)


def report(title: str, rows: list[tuple[str, np.ndarray]]) -> None:
    print(f"\n  {title}")
    print(f"    {'band':8} {'n':>7}  {'MAE':>7} {'median':>7}")
    for name, errors in rows:
        mae, median, count = scores(errors)
        print(f"    {name:8} {count:>7,}  {mae:>7.2f} {median:>7.2f}")


def fit(features, targets, dev_features, dev_targets, categorical, max_iter):
    """Fit, choosing the iteration count on the molecule-grouped dev set.

    `absolute_error` rather than squared: NMR error is judged by MAE and
    median, and a squared loss spends its capacity on the handful of
    grossly mis-assigned records a public deposition inevitably contains.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    estimator = HistGradientBoostingRegressor(
        loss="absolute_error",
        max_iter=max_iter,
        learning_rate=0.08,
        max_leaf_nodes=63,
        min_samples_leaf=40,
        l2_regularization=1.0,
        categorical_features=categorical or None,
        early_stopping=False,
        random_state=0,
    )
    estimator.fit(features, targets)

    best_iterations, best_mae = max_iter, float("inf")
    for count, prediction in enumerate(estimator.staged_predict(dev_features), start=1):
        mae = float(np.mean(np.abs(prediction - dev_targets)))
        if mae < best_mae:
            best_mae, best_iterations = mae, count
    print(f"    dev MAE {best_mae:.3f} ppm at {best_iterations}/{max_iter} iterations")
    if best_iterations < max_iter:
        estimator.set_params(max_iter=best_iterations)
        estimator.fit(features, targets)
    return estimator, best_iterations


def run(args: argparse.Namespace) -> None:
    train = load(args.train)
    held = load(args.heldout)
    names = list(nmr_ml.feature_names(SPHERES))
    categorical = nmr_ml.categorical_feature_indices(SPHERES)

    if args.leaky:
        # The ablation for the leave-one-out correction: put the
        # uncorrected lookup block back and let the model see its own
        # answer, which is what a careless pipeline would have done.
        train["features"] = train["features"].copy()
        train["features"][:, : 3 * SPHERES] = train["uncorrected"]

    if args.no_hash:
        keep = [index for index in range(len(names)) if index not in categorical]
        train["features"] = train["features"][:, keep]
        held["features"] = held["features"][:, keep]
        names = [names[index] for index in keep]
        categorical = []

    models: dict[str, object] = {}
    for element, code in ELEMENT_CODES.items():
        rows = train["elements"] == code
        if not rows.any():
            continue
        print(f"\n=== {element} ===")

        is_dev = (train["records"] % 20 == 1) & rows
        is_fit = ~(train["records"] % 20 == 1) & rows
        print(f"  fit {is_fit.sum():,} rows, dev {is_dev.sum():,} rows")

        held_rows = held["elements"] == code
        features = held["features"][held_rows]
        truth = held["targets"][held_rows].astype(np.float64)
        quality = held["hose_quality"][held_rows]
        hose = held["hose_shift"][held_rows].astype(np.float64)
        covered = ~np.isnan(hose)

        # An uncovered atom still needs a number to correct FROM. The
        # training set's median for this element is the only honest
        # choice: it uses nothing about the molecule being predicted.
        fallback = float(np.median(train["targets"][is_fit]))
        base_train = first_available_mean(train["features"][:, : 3 * SPHERES])
        base_train = np.where(np.isnan(base_train), fallback, base_train)
        base_held = np.where(covered, hose, fallback)

        if args.target == "residual":
            fit_target = train["targets"] - base_train
        else:
            fit_target = train["targets"].astype(np.float64)

        started = time.time()
        estimator, iterations = fit(
            train["features"][is_fit],
            fit_target[is_fit],
            train["features"][is_dev],
            fit_target[is_dev],
            categorical,
            args.max_iter,
        )
        elapsed = time.time() - started
        print(f"    trained in {elapsed:.0f}s")

        raw = np.asarray(estimator.predict(features), dtype=np.float64)
        predicted = base_held + raw if args.target == "residual" else raw

        hose_error = np.abs(hose - truth)
        model_error = np.abs(predicted - truth)
        print(
            f"  held-out atoms {truth.size:,}, HOSE coverage "
            f"{100.0 * covered.sum() / truth.size:.1f}%"
        )

        report(
            "HOSE lookup (as shipped)",
            [(band, hose_error[(quality == index) & covered]) for index, band in enumerate(BANDS)]
            + [("ALL", hose_error[covered])],
        )
        report(
            "model alone",
            [(band, model_error[quality == index]) for index, band in enumerate(BANDS)]
            + [("ALL", model_error[covered]), ("ALL+uncov", model_error)],
        )

        best_rule = None
        for keep_bands in (("good",), ("good", "medium")):
            mask = np.isin(quality, [BANDS.index(band) for band in keep_bands]) & covered
            error = np.abs(np.where(mask, hose, predicted) - truth)
            report(
                f"hybrid: HOSE for {'+'.join(keep_bands)}, model elsewhere",
                [(band, error[quality == index]) for index, band in enumerate(BANDS)]
                + [("ALL", error[covered]), ("ALL+uncov", error)],
            )
            if best_rule is None or float(np.mean(error)) < best_rule[1]:
                best_rule = (keep_bands, float(np.mean(error)))

        # Only what the significance check needs to re-derive predictions;
        # nothing here is loaded by the application, because nothing ships.
        models[element] = {
            "estimator": estimator,
            "max_spheres": SPHERES,
            "target": args.target,
            "iterations": iterations,
            "train_seconds": round(elapsed, 1),
            "fallback_shift": fallback,
        }

        if args.importance:
            _importance(estimator, features, truth - base_held if args.target == "residual" else truth, names)

    if args.out:
        import gzip
        import pickle

        with gzip.open(args.out, "wb") as handle:
            pickle.dump(models, handle, protocol=5)
        print(f"\nwrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


def _importance(estimator, features: np.ndarray, truth: np.ndarray, names: list[str]) -> None:
    """Permutation importance on a subsample.

    Subsampled because it predicts once per feature per repeat, and the
    full held-out set times sixty features is minutes for a number that
    only has to rank.
    """
    from sklearn.inspection import permutation_importance

    limit = min(6000, features.shape[0])
    pick = np.random.default_rng(0).choice(features.shape[0], size=limit, replace=False)
    result = permutation_importance(
        estimator,
        features[pick],
        truth[pick],
        n_repeats=3,
        random_state=0,
        scoring="neg_mean_absolute_error",
    )
    order = np.argsort(result.importances_mean)[::-1]
    print("\n  feature importance (ppm of MAE lost when the column is shuffled)")
    for index in order[:20]:
        print(f"    {names[index]:22} {result.importances_mean[index]:+.3f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("train", type=Path)
    parser.add_argument("heldout", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--max-iter", type=int, default=400)
    parser.add_argument("--target", choices=("residual", "raw"), default="residual")
    parser.add_argument("--importance", action="store_true")
    parser.add_argument("--no-hash", action="store_true", help="Ablate the hashed-HOSE columns.")
    parser.add_argument(
        "--leaky",
        action="store_true",
        help="Ablate the leave-one-out correction, to measure what it is worth.",
    )
    run(parser.parse_args())
