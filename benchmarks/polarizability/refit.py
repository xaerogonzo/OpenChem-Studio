"""Refit of the additive atomic polarizability table, as fixed by PREREGISTRATION.md.

`python benchmarks/polarizability/refit.py` reads the corpus (kept outside git, `OPENCHEM_POLARIZABILITY_CORPUS` or the default folder), fits, judges and writes
`results/refit.json` beside this file. The functions are pure so `tests/test_polarizability_refit.py` can hold them to small known problems.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_CORPUS = pathlib.Path(r"D:/Xaero Stuff/Documents/OpenChem Studio literature/polarizability_corpus/bosque2002_resolved.json")
SEED = 20261105
MIN_MOLECULES_FIT = 5  # PREREGISTRATION 2
MIN_MOLECULES_FIRM = 10

#: The table being replaced (for comparison only).
CURRENT = {"H": 0.3888, "C": 1.3266, "N": 0.9754, "O": 0.7658, "S": 2.4772, "F": 0.4642, "Cl": 2.2604, "Br": 3.3181, "I": 5.5593, "P": 2.63, "Si": 3.9628, "B": 1.6, "Se": 3.38}
#: Bosque and Sales 2002, Table 4 (cubic angstrom), with its intercept: context only.
BOSQUE_TABLE4 = {"Br": 3.29, "C": 1.51, "Cl": 2.16, "F": 0.222, "H": 0.174, "I": 5.45, "N": 1.03, "O": 0.571, "P": 2.48, "S": 2.99}
BOSQUE_INTERCEPT = 0.318


def design(rows: list[dict], elements: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Atom counts per molecule (rows) by element (columns), and the experimental values."""
    x = np.array([[r["composition"].get(e, 0) for e in elements] for r in rows], dtype=float)
    y = np.array([r["exp"] for r in rows], dtype=float)
    return x, y


def fit_relative(x: np.ndarray, y: np.ndarray, relative: bool = True) -> np.ndarray:
    """Least squares on the relative error (weights 1/y^2) or, with relative=False, on the absolute one."""
    w = (1.0 / y) if relative else np.ones_like(y)
    beta, *_ = np.linalg.lstsq(x * w[:, None], y * w, rcond=None)
    return beta


def standard_errors(x: np.ndarray, y: np.ndarray, beta: np.ndarray, relative: bool = True) -> np.ndarray:
    """Standard errors of the weighted fit (the residual variance of the weighted problem)."""
    w = (1.0 / y) if relative else np.ones_like(y)
    xw = x * w[:, None]
    resid = (y - x @ beta) * w
    dof = max(len(y) - len(beta), 1)
    cov = np.linalg.pinv(xw.T @ xw) * float(resid @ resid) / dof
    return np.sqrt(np.diag(cov))


def percent_errors(predicted: np.ndarray, y: np.ndarray) -> np.ndarray:
    return 100.0 * (predicted - y) / y


def summarise(err: np.ndarray) -> dict:
    a = np.abs(err)
    return {"n": int(len(err)), "mape": float(a.mean()), "median": float(np.median(a)), "p90": float(np.percentile(a, 90)),
            "max": float(a.max()), "bias": float(err.mean())}


def predict_table(rows: list[dict], table: dict[str, float], intercept: float = 0.0) -> np.ndarray | None:
    """Predictions from a per-element table; None if any molecule has an element it lacks."""
    out = []
    for r in rows:
        if any(e not in table for e in r["composition"]):
            return None
        out.append(intercept + sum(table[e] * n for e, n in r["composition"].items()))
    return np.array(out)


def stability(rows: list[dict], elements: list[str], draws: int = 200, fraction: float = 0.8, seed: int = SEED) -> dict[str, float]:
    """Standard deviation over mean of each value across fits on random subsets of the rows."""
    rng = np.random.default_rng(seed)
    x, y = design(rows, elements)
    betas = []
    for _ in range(draws):
        idx = rng.choice(len(rows), size=int(fraction * len(rows)), replace=False)
        betas.append(fit_relative(x[idx], y[idx]))
    b = np.array(betas)
    return {e: float(b[:, i].std() / abs(b[:, i].mean())) for i, e in enumerate(elements)}


def run(corpus: pathlib.Path) -> dict:
    data = json.loads(corpus.read_text(encoding="utf-8"))
    usable = [r for r in data if r["status"] == "ok"]
    work = [r for r in usable if r["section"] == "working"]
    pred = [r for r in usable if r["section"] == "prediction"]
    count_work = {}
    for r in work:
        for e in r["composition"]:
            count_work[e] = count_work.get(e, 0) + 1
    elements = sorted(e for e, n in count_work.items() if n >= MIN_MOLECULES_FIT)
    # Added after run 1 (see RESULT): a molecule with an element that is not fitted (phosphorus, 4 working-set molecules) cannot take part in a fit that has no column for
    # it, and in judging it is predicted with the CURRENT table's value for that element. Run 1 ignored the element, which was wrong.
    only_fitted = lambda rows: [r for r in rows if set(r["composition"]) <= set(elements)]
    work_all, work = work, only_fitted(work)
    pred_all, pred = pred, only_fitted(pred)
    x, y = design(work, elements)
    beta = fit_relative(x, y)
    se = standard_errors(x, y, beta)
    fitted = dict(zip(elements, map(float, beta)))
    xp, yp = design(pred, elements)
    report = {
        "rows": {"usable": len(usable), "working": len(work_all), "prediction": len(pred_all), "working_fitted_elements_only": len(work), "prediction_fitted_elements_only": len(pred)},
        "molecules_per_element_working": count_work, "elements_fitted": elements,
        "working_fit": {e: {"value": float(b), "se": float(s), "firm": count_work[e] >= MIN_MOLECULES_FIRM} for e, b, s in zip(elements, beta, se)},
        "unweighted_working_fit": dict(zip(elements, map(float, fit_relative(x, y, relative=False)))),
        "prediction": {"refit": summarise(percent_errors(xp @ beta, yp))},
    }
    mixed = {**CURRENT, **fitted}  # refit values where fitted, the current table's elsewhere
    report["prediction_including_unfitted_elements"] = {
        "n": len(pred_all), "refit_with_current_for_unfitted": summarise(percent_errors(predict_table(pred_all, mixed), np.array([r["exp"] for r in pred_all]))),
        "current_table": summarise(percent_errors(predict_table(pred_all, CURRENT), np.array([r["exp"] for r in pred_all])))}
    cur = predict_table(pred, CURRENT)
    report["prediction"]["current_table"] = summarise(percent_errors(cur, yp)) if cur is not None else None
    bos = predict_table(pred, BOSQUE_TABLE4, BOSQUE_INTERCEPT)
    report["prediction"]["bosque_table4"] = summarise(percent_errors(bos, yp)) if bos is not None else None
    cw = predict_table(work, CURRENT)
    report["working_current_table"] = summarise(percent_errors(cw, y)) if cw is not None else None
    report["working_refit"] = summarise(percent_errors(x @ beta, y))
    # the values that ship: the same model on all usable rows
    xa, ya = design(only_fitted(usable), elements)
    ball = fit_relative(xa, ya)
    sea = standard_errors(xa, ya, ball)
    report["shipped_fit_all_rows"] = {e: {"value": float(b), "se": float(s)} for e, b, s in zip(elements, ball, sea)}
    report["stability_sd_over_mean"] = stability(work, elements)
    report["ratio_to_current"] = {e: float(report["shipped_fit_all_rows"][e]["value"] / CURRENT[e]) for e in elements}
    return report


if __name__ == "__main__":
    path = pathlib.Path(os.environ.get("OPENCHEM_POLARIZABILITY_CORPUS", DEFAULT_CORPUS))
    result = run(path)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "refit.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    sys.exit(0)
