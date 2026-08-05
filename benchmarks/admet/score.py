"""Score the ADMET sidecar against the TDC ADMET Benchmark Group test sets.

WHY THIS EXISTS. `chem/admet_providers.py` reports 10 of the 104 columns
the model emits, and the discards include endpoints RDKit cannot produce
at all -- Caco-2, solubility, BBB, plasma protein binding, VDss, half
life, clearance, DILI, LD50, bioavailability, HIA, Pgp. Promoting one of
those to the UI is a claim about it, and this is what backs the claim.

THE HERG PRECEDENT IS THE REASON FOR EVERY COLUMN AFTER THE FIRST. hERG's
apparent separation on a ten-compound panel turned out to be molecular
size (r = +0.98 with heavy-atom count); the model had learnt "big
lipophilic molecules block hERG" and scored identically to a ruler. So an
accuracy number alone cannot decide whether an endpoint ships. Each one
is also scored against the two baselines that would fake it:

    size-only    molecular weight used directly as the prediction
    logP-only    Crippen logP used directly as the prediction

Both baselines are given their best orientation (a size baseline is
allowed to say "heavier means less soluble"), because the question is
whether the model beats them, not whether they are pointed the right way.
An endpoint whose model barely beats a ruler is not a prediction.

r(truth, size) is reported alongside, and it is the column that keeps this
fair. Some endpoints genuinely DO depend on size -- permeability and
solubility really do fall with molecular weight -- so a size-correlated
prediction is only damning when the model tracks size MORE closely than
the measured truth does.

Usage (see README.md for the two steps that produce the inputs):

    uv run --no-sync python score.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _metrics import auprc, auroc, mae, pearson, r2, spearman  # noqa: E402

# csv + numpy rather than pandas: the project's own environment has no
# pandas (only the ADMET sidecar does), and a benchmark that will not run
# where the code lives is a benchmark that gets quoted instead of re-run.
csv.field_size_limit(10_000_000)

DATA = Path("tdc_data")

#: TDC benchmark dataset -> the ADMET-AI column that predicts it, and
#: whether the endpoint is a classification or a regression.
#: Names on both sides are the projects' own; the mapping is not
#: guessable from either alone.
ENDPOINTS: dict[str, tuple[str, str]] = {
    "caco2_wang": ("Caco2_Wang", "regression"),
    "hia_hou": ("HIA_Hou", "classification"),
    "pgp_broccatelli": ("Pgp_Broccatelli", "classification"),
    "bioavailability_ma": ("Bioavailability_Ma", "classification"),
    "lipophilicity_astrazeneca": ("Lipophilicity_AstraZeneca", "regression"),
    "solubility_aqsoldb": ("Solubility_AqSolDB", "regression"),
    "bbb_martins": ("BBB_Martins", "classification"),
    "ppbr_az": ("PPBR_AZ", "regression"),
    "vdss_lombardo": ("VDss_Lombardo", "regression"),
    "cyp2d6_veith": ("CYP2D6_Veith", "classification"),
    "cyp3a4_veith": ("CYP3A4_Veith", "classification"),
    "cyp2c9_veith": ("CYP2C9_Veith", "classification"),
    "cyp2d6_substrate_carbonmangels": ("CYP2D6_Substrate_CarbonMangels", "classification"),
    "cyp3a4_substrate_carbonmangels": ("CYP3A4_Substrate_CarbonMangels", "classification"),
    "cyp2c9_substrate_carbonmangels": ("CYP2C9_Substrate_CarbonMangels", "classification"),
    "half_life_obach": ("Half_Life_Obach", "regression"),
    "clearance_microsome_az": ("Clearance_Microsome_AZ", "regression"),
    "clearance_hepatocyte_az": ("Clearance_Hepatocyte_AZ", "regression"),
    "herg": ("hERG", "classification"),
    "ames": ("AMES", "classification"),
    "dili": ("DILI", "classification"),
    "ld50_zhu": ("LD50_Zhu", "regression"),
}

#: ADMET-AI's OWN published test-set AUROC for each classification
#: endpoint, copied from the `AUROC` column of the vendor's
#: `admet_ai/resources/data/admet.csv`. Those figures come from models
#: trained by `train_tdc_admet_group.py` -- scaffold-split models built for
#: leaderboard comparison, which are NOT the models that ship.
#:
#: Kept here to be differenced against what we measure, which is the
#: evidence for `_leakage`'s conclusion.
PUBLISHED_AUROC: dict[str, float] = {
    "HIA_Hou": 0.9940,
    "Bioavailability_Ma": 0.7164,
    "Pgp_Broccatelli": 0.9475,
    "BBB_Martins": 0.9004,
    "CYP1A2_Veith": 0.9411,
    "CYP2C19_Veith": 0.9062,
    "CYP2C9_Veith": 0.9077,
    "CYP2D6_Veith": 0.8861,
    "CYP3A4_Veith": 0.9116,
    "CYP2C9_Substrate_CarbonMangels": 0.6279,
    "CYP2D6_Substrate_CarbonMangels": 0.8200,
    "CYP3A4_Substrate_CarbonMangels": 0.7048,
    "hERG": 0.8388,
    "AMES": 0.8816,
    "DILI": 0.8815,
}

#: Already surfaced by the app, so their rows are a re-check of shipped
#: behaviour rather than a promotion decision.
ALREADY_REPORTED = {
    "hERG", "AMES", "CYP1A2_Veith", "CYP2C9_Veith", "CYP2C19_Veith",
    "CYP2D6_Veith", "CYP3A4_Veith", "CYP2C9_Substrate_CarbonMangels",
    "CYP2D6_Substrate_CarbonMangels", "CYP3A4_Substrate_CarbonMangels",
}


def _load_predictions(split: str) -> dict[str, dict[str, float]]:
    """SMILES -> {column: value} for one split's predictions."""
    path = Path(f"predictions_{split}.csv")
    if not path.is_file():
        raise SystemExit(
            f"{path} is missing. Run fetch_tdc.py then predict.py first -- see README.md."
        )
    table: dict[str, dict[str, float]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            smiles = record.pop("smiles")
            values = {}
            for key, raw in record.items():
                try:
                    values[key] = float(raw)
                except (TypeError, ValueError):
                    continue
            table[smiles] = values
    return table


def _load_truth(dataset: str, split: str) -> list[tuple[str, float]]:
    path = DATA / f"{dataset}__{split}.csv"
    # predict.py only writes a `trainsample` file for the datasets big
    # enough to need thinning; the small ones were predicted whole.
    if not path.is_file() and split == "trainsample":
        path = DATA / f"{dataset}__trainval.csv"
    if not path.is_file():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            try:
                rows.append((record["Drug"], float(record["Y"])))
            except (TypeError, ValueError, KeyError):
                continue
    return rows


def _skill(truth: np.ndarray, score: np.ndarray, task: str) -> float:
    """One comparable number per endpoint, in the units the task deserves.

    AUROC for classification and Spearman for regression -- both rank
    statistics, so the same call scores a probability, a molecular weight
    and a regressed value without rescaling any of them. That is what lets
    the model and the size baseline be compared at all.
    """
    if task == "classification":
        value = auroc(truth, score)
        # A baseline pointing the wrong way is still a baseline; give it
        # its best orientation so beating it means something.
        return max(value, 1.0 - value)
    return abs(spearman(truth, score))


def _score_one(dataset: str, column: str, task: str, predictions, split: str) -> dict | None:
    truth_rows = [(s, y) for s, y in _load_truth(dataset, split) if s in predictions]
    truth_rows = [
        (s, y) for s, y in truth_rows
        if column in predictions[s] and "molecular_weight" in predictions[s]
    ]
    if len(truth_rows) < 10:
        return None

    truth = np.array([y for _s, y in truth_rows], dtype=float)
    prediction = np.array([predictions[s][column] for s, _y in truth_rows], dtype=float)
    weight = np.array([predictions[s]["molecular_weight"] for s, _y in truth_rows], dtype=float)
    logp = np.array([predictions[s]["logP"] for s, _y in truth_rows], dtype=float)

    row = {
        "dataset": dataset,
        "column": column,
        "task": task,
        "n": len(truth_rows),
        "skill": _skill(truth, prediction, task),
        "size_only": _skill(truth, weight, task),
        "logp_only": _skill(truth, logp, task),
        "r_pred_mw": pearson(prediction, weight),
        "r_pred_logp": pearson(prediction, logp),
        "r_truth_mw": pearson(truth, weight),
        "shipped": column in ALREADY_REPORTED,
    }
    if task == "classification":
        row["auroc"] = auroc(truth, prediction)
        row["auprc"] = auprc(truth, prediction)
        row["headline"] = row["auroc"]
    else:
        row["r2"] = r2(truth, prediction)
        row["mae"] = mae(truth, prediction)
        row["spearman"] = spearman(truth, prediction)
        row["headline"] = row["spearman"]
    return row


def main() -> int:
    test = _load_predictions("test")
    rows = []
    for dataset, (column, task) in ENDPOINTS.items():
        row = _score_one(dataset, column, task, test, "test")
        if row is None:
            print(f"  {dataset}: too few joined predictions -- skipped")
            continue
        rows.append(row)

    _report(rows)
    _leakage(rows)

    fields = sorted({key for row in rows for key in row})
    with open("scores.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print("\nwrote scores.csv")
    return 0


def _leakage(rows: list[dict]) -> None:
    """THE RESULT THAT INVALIDATES THE ACCURACY TABLE ABOVE, so read this
    before quoting any number from it.

    The TDC "test" split is NOT held out from the weights this app runs.
    ADMET-AI's own reproduction docs describe two separate training
    scripts: `train_tdc_admet_group.py`, which builds scaffold-split models
    for leaderboard comparison, and `train_tdc_admet_all.py`, which trains
    on all the data and produces the models that ship inside the wheel.
    We run the shipped ones, so every TDC molecule is a training molecule.

    Two measurements agree with that reading:

    1. Train-split skill vs test-split skill. Under real held-out
       evaluation a model scores better on data it trained on. Here the two
       are the SAME data as far as the weights are concerned, so the gap
       collapses toward zero -- which looks like healthy generalisation and
       is the opposite.
    2. Measured AUROC vs the vendor's own published AUROC for the
       scaffold-split models, on the same test molecules. A systematic
       positive delta is the memorisation the published models did not get
       to do.

    WHAT SURVIVES THIS. The confound comparison still decides something,
    in one direction. Leakage inflates the MODEL's column but leaves the
    molecular-weight and logP baselines untouched, so the measured gain is
    an upper bound on the model's real advantage over a ruler. An endpoint
    that cannot beat a ruler even with the answers memorised is a ruler --
    that inference is safe, and it is what the tiering in
    `chem/admet_providers.py` acts on.
    """
    print("\n" + "=" * 78)
    print("LEAKAGE CHECK -- is the TDC test split held out from the SHIPPED weights?")
    print("=" * 78)

    published = [
        (row["dataset"], row["auroc"], PUBLISHED_AUROC[row["column"]])
        for row in sorted(rows, key=lambda r: r["dataset"])
        if row["task"] == "classification" and row["column"] in PUBLISHED_AUROC
    ]
    if published:
        print("\nMeasured AUROC vs the vendor's published scaffold-split AUROC,")
        print("on the very same test molecules:\n")
        print(f"{'endpoint':<34}{'measured':>10}{'published':>11}{'delta':>8}")
        print("-" * 63)
        for dataset, measured, reference in published:
            print(f"{dataset:<34}{measured:>10.3f}{reference:>11.3f}{measured - reference:>+8.3f}")
        deltas = [measured - reference for _d, measured, reference in published]
        beat = sum(1 for d in deltas if d > 0)
        print(f"\n  mean delta {float(np.mean(deltas)):+.3f}   "
              f"higher on {beat}/{len(deltas)} endpoints")

    if not Path("predictions_train.csv").is_file():
        print("\n(no predictions_train.csv -- run `predict.py train` for the second check)")
        return

    train = _load_predictions("train")
    print("\nTrain-split skill vs test-split skill:\n")
    print(f"{'endpoint':<34}{'train':>8}{'test':>8}{'gap':>8}")
    print("-" * 58)
    gaps = []
    for row in sorted(rows, key=lambda r: r["dataset"]):
        train_row = _score_one(row["dataset"], row["column"], row["task"], train, "trainsample")
        if train_row is None:
            continue
        gap = train_row["skill"] - row["skill"]
        gaps.append(gap)
        print(f"{row['dataset']:<34}{train_row['skill']:>8.3f}{row['skill']:>8.3f}{gap:>+8.3f}")
    if gaps:
        print(f"\n  mean gap {float(np.mean(gaps)):+.3f}   max {max(gaps):+.3f}")
        print("  Near zero because BOTH splits trained these weights.")


def _report(rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("ACCURACY on the TDC held-out test split")
    print("=" * 78)
    print(f"{'endpoint':<34}{'n':>6}{'metric':>10}{'value':>9}   published")
    print("-" * 78)
    for row in sorted(rows, key=lambda r: r["dataset"]):
        metric = "AUROC" if row["task"] == "classification" else "Spearman"
        mark = "  (shipped)" if row["shipped"] else ""
        print(f"{row['dataset']:<34}{row['n']:>6}{metric:>10}{row['headline']:>9.3f}{mark}")

    print("\n" + "=" * 78)
    print("THE CONFOUND CHECK -- does the model beat a ruler?")
    print("=" * 78)
    print("skill = AUROC (classification) or |Spearman| (regression), so the")
    print("model, molecular weight and logP are scored on one scale.")
    print()
    print(f"{'endpoint':<34}{'model':>7}{'size':>7}{'logP':>7}{'gain':>7}"
          f"{'r(pred,MW)':>12}{'r(truth,MW)':>13}")
    print("-" * 91)
    for row in sorted(rows, key=lambda r: r["skill"] - max(r["size_only"], r["logp_only"])):
        gain = row["skill"] - max(row["size_only"], row["logp_only"])
        flag = ""
        if gain < 0.05:
            flag = "  <-- NO BETTER THAN A RULER"
        elif gain < 0.10:
            flag = "  <-- marginal"
        print(f"{row['dataset']:<34}{row['skill']:>7.3f}{row['size_only']:>7.3f}"
              f"{row['logp_only']:>7.3f}{gain:>+7.3f}{row['r_pred_mw']:>+12.2f}"
              f"{row['r_truth_mw']:>+13.2f}{flag}")

    print("\n  gain = how much the model adds over the better of the two baselines.")
    print("  r(truth,MW) is the honest defence: where it is large, the endpoint")
    print("  really does depend on size and a size-correlated model is not wrong.")


if __name__ == "__main__":
    raise SystemExit(main())
