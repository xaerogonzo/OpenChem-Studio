"""Polarizability refit 2 (`PREREGISTRATION_2.md`): the small-molecule evidence, four model variants, one holdout.

    uv run --no-sync python benchmarks/polarizability/refit2.py

The corpora (Bosque and Sales 2002, and the CRC Handbook table) are kept outside git. The pure functions here are tested by `tests/test_polarizability_refit2.py`.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from rdkit import Chem

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = pathlib.Path(r"D:/Xaero Stuff/Documents/OpenChem Studio literature/polarizability_corpus")
SEED = 20261105
SIMPLER_UNLESS_BETTER_BY = 0.2
MIN_MOLECULES_FIT = 5
UNFITTED = ("P", "Si", "B", "Se")
VARIANTS = {"A": (False, False), "B": (False, True), "C": (True, False), "D": (True, True)}  # (split hydrogen, constant)
COMPLEXITY = {"A": 0, "B": 1, "C": 1, "D": 2}


def atom_counts(smiles: str, split_h: bool) -> dict[str, int]:
    """Counts of each atom type; with `split_h` a hydrogen is typed by its neighbour (C and everything else together, O, N)."""
    counts: dict[str, int] = {}
    for atom in Chem.AddHs(Chem.MolFromSmiles(smiles)).GetAtoms():
        key = atom.GetSymbol()
        if key == "H" and split_h:
            neighbour = atom.GetNeighbors()[0].GetSymbol()
            key = "H(O)" if neighbour == "O" else "H(N)" if neighbour == "N" else "H"
        counts[key] = counts.get(key, 0) + 1
    return counts


def design(rows: list[dict], keys: list[str], split_h: bool, constant: bool) -> np.ndarray:
    matrix = []
    for row in rows:
        counts = atom_counts(row["smiles"], split_h)
        matrix.append([counts.get(k, 0) for k in keys] + ([1] if constant else []))
    return np.array(matrix, dtype=float)


def fit(rows: list[dict], keys: list[str], split_h: bool, constant: bool) -> np.ndarray:
    """Weighted least squares on the relative error: minimise the sum of ((x.b - y) / y)^2."""
    y = np.array([r["exp"] for r in rows], dtype=float)
    beta, *_ = np.linalg.lstsq(design(rows, keys, split_h, constant) / y[:, None], np.ones(len(y)), rcond=None)
    return beta


def predict(rows: list[dict], keys: list[str], beta: np.ndarray, split_h: bool, constant: bool) -> np.ndarray:
    """NaN for a molecule with an atom type the fit does not have."""
    out = []
    for row in rows:
        counts = atom_counts(row["smiles"], split_h)
        if any(k not in keys for k in counts):
            out.append(np.nan)
            continue
        out.append(sum(beta[i] * counts.get(k, 0) for i, k in enumerate(keys)) + (beta[-1] if constant else 0.0))
    return np.array(out)


def percent_errors(predicted: np.ndarray, rows: list[dict]) -> np.ndarray:
    y = np.array([r["exp"] for r in rows], dtype=float)
    return 100.0 * (predicted - y) / y


def summarise(err: np.ndarray) -> dict:
    ok = err[~np.isnan(err)]
    if not len(ok):
        return {"n": 0, "mape": None, "bias": None, "max": None}
    return {"n": int(len(ok)), "mape": float(np.abs(ok).mean()), "bias": float(ok.mean()), "max": float(np.abs(ok).max())}


def cross_validate(rows: list[dict], keys: list[str], split_h: bool, constant: bool, folds: int = 10, seed: int = SEED) -> float:
    order = np.random.default_rng(seed).permutation(len(rows))
    errors = np.full(len(rows), np.nan)
    for fold in np.array_split(order, folds):
        held = set(int(i) for i in fold)
        train = [r for i, r in enumerate(rows) if i not in held]
        beta = fit(train, keys, split_h, constant)
        test = [rows[i] for i in sorted(held)]
        errors[sorted(held)] = percent_errors(predict(test, keys, beta, split_h, constant), test)
    return summarise(errors)["mape"]


def choose_variant(cv: dict[str, float], margin: float = SIMPLER_UNLESS_BETTER_BY) -> str:
    """The registered rule: the best cross-validated variant, unless a simpler one is within `margin` points of it."""
    best = min(cv, key=cv.get)
    simpler = [v for v in cv if COMPLEXITY[v] < COMPLEXITY[best] and cv[v] - cv[best] < margin]
    return min(simpler, key=lambda v: (COMPLEXITY[v], cv[v])) if simpler else best


def size_bins(rows: list[dict]) -> dict[str, list[int]]:
    n = [sum(r["composition"].values()) for r in rows]
    return {"up_to_6": [i for i, k in enumerate(n) if k <= 6], "7_to_12": [i for i, k in enumerate(n) if 7 <= k <= 12], "over_12": [i for i, k in enumerate(n) if k > 12]}


def standard_errors(rows: list[dict], keys: list[str], beta: np.ndarray, split_h: bool, constant: bool) -> np.ndarray:
    y = np.array([r["exp"] for r in rows], dtype=float)
    a = design(rows, keys, split_h, constant) / y[:, None]
    residual = a @ beta - 1.0
    dof = max(len(y) - len(beta), 1)
    covariance = (residual @ residual / dof) * np.linalg.inv(a.T @ a)
    return np.sqrt(np.diag(covariance))


def load_corpora():
    canonical = lambda s: Chem.MolToSmiles(Chem.MolFromSmiles(s))  # noqa: E731
    bosque = [r for r in json.loads((CORPUS / "bosque2002_resolved.json").read_text(encoding="utf-8")) if r["status"] == "ok"]
    taken = {canonical(r["smiles"]) for r in bosque}
    crc = []
    for r in json.loads((CORPUS / "crc97_resolved.json").read_text(encoding="utf-8")):
        if not r["match"]:  # no structure, or one whose formula is not the printed one
            continue
        key = canonical(r["smiles"])
        if key in taken:
            continue
        taken.add(key)
        crc.append({**r, "exp": r["value"]})
    return bosque, crc


def run() -> dict:
    bosque, crc = load_corpora()
    rng = np.random.default_rng(SEED)
    pick = rng.permutation(len(crc))
    cut = int(round(0.7 * len(crc)))
    crc_dev, crc_hold = [crc[i] for i in sorted(pick[:cut])], [crc[i] for i in sorted(pick[cut:])]
    # Registered rule 2: an element is fitted only with at least MIN_MOLECULES_FIT development molecules; a molecule with any other element is left out of the fit and
    # of the evaluation (counted below). The first run applied no such rule and fitted one-molecule metals (kept as refit2_run1_unrestricted.json, superseded).
    def elements_of(r):
        return set(r["composition"]) - {"D"}

    development_all = [r for r in bosque if r["section"] == "working"] + crc_dev
    per_element = {}
    for r in development_all:
        for e in elements_of(r):
            per_element[e] = per_element.get(e, 0) + 1
    fitted_elements = {e for e, n in per_element.items() if n >= MIN_MOLECULES_FIT}
    usable = lambda r: elements_of(r) <= fitted_elements  # noqa: E731
    dev = [r for r in development_all if usable(r)]
    bos_hold = [r for r in bosque if r["section"] != "working" and usable(r)]
    hold = [r for r in crc_hold if usable(r)]
    extra = {e: per_element.get(e, 0) for e in UNFITTED}
    dropped = {"development": len(development_all) - len(dev), "holdout_crc": len(crc_hold) - len(hold), "holdout_bosque": sum(1 for r in bosque if r["section"] != "working") - len(bos_hold)}

    cv = {}
    keys_for = {}
    for name, (split_h, constant) in VARIANTS.items():
        keys = sorted({k for r in dev for k in atom_counts(r["smiles"], split_h)})
        keys_for[name] = keys
        cv[name] = cross_validate(dev, keys, split_h, constant)
    chosen = choose_variant(cv)

    # the shipped table, for comparison
    from openchem.chem.electronic_properties import ADDITIVE_POLARIZABILITY as shipped

    def shipped_predict(rows):
        out = []
        for r in rows:
            counts = atom_counts(r["smiles"], False)
            out.append(sum(shipped[k] * n for k, n in counts.items()) if all(k in shipped for k in counts) else np.nan)
        return np.array(out)

    results = {"seed": SEED, "development": len(dev), "holdout_crc": len(hold), "holdout_bosque": len(bos_hold), "development_molecules_per_listed_element": extra, "elements_fitted": sorted(fitted_elements), "molecules_left_out": dropped, "cv_mape": cv, "chosen": chosen, "variants": {}}
    for name, (split_h, constant) in VARIANTS.items():
        keys = keys_for[name]
        beta = fit(dev, keys, split_h, constant)
        entry = {"values": dict(zip(keys + (["constant"] if constant else []), (float(b) for b in beta)))}
        for label, rows in (("crc_holdout", hold), ("bosque_holdout", bos_hold)):
            err = percent_errors(predict(rows, keys, beta, split_h, constant), rows)
            entry[label] = summarise(err)
            if label == "crc_holdout":
                entry["crc_by_size"] = {b: summarise(err[idx]) for b, idx in size_bins(rows).items()}
        results["variants"][name] = entry
    results["shipped"] = {}
    for label, rows in (("crc_holdout", hold), ("bosque_holdout", bos_hold)):
        err = percent_errors(shipped_predict(rows), rows)
        results["shipped"][label] = summarise(err)
        if label == "crc_holdout":
            results["shipped"]["crc_by_size"] = {b: summarise(err[idx]) for b, idx in size_bins(rows).items()}
    split_h, constant = VARIANTS[chosen]
    keys = keys_for[chosen]
    beta = fit(dev, keys, split_h, constant)
    err = percent_errors(predict(hold, keys, beta, split_h, constant), hold)
    worst = np.argsort(-np.nan_to_num(np.abs(err)))[:10]
    results["worst_chosen"] = [{"name": hold[i]["name"], "formula": hold[i]["formula"] if "formula" in hold[i] else "", "exp": hold[i]["exp"], "percent": float(err[i])} for i in worst]
    # The table that ships: the chosen variant refitted on every usable molecule (development and holdout of both corpora), as the first refit did.
    everything = [r for r in bosque + crc if elements_of(r) <= fitted_elements]
    final_keys = sorted({k for r in everything for k in atom_counts(r["smiles"], split_h)})
    final_beta = fit(everything, final_keys, split_h, constant)
    final_se = standard_errors(everything, final_keys, final_beta, split_h, constant)
    molecules = {k: sum(1 for r in everything if k in atom_counts(r["smiles"], split_h)) for k in final_keys}
    names = final_keys + (["constant"] if constant else [])
    results["shipped_fit_all_rows"] = {
        n: {"value": float(b), "se": float(e), "molecules": molecules.get(n, len(everything)), "weakly_determined": molecules.get(n, len(everything)) < 10}
        for n, b, e in zip(names, final_beta, final_se)
    }
    results["rows_used_in_final_fit"] = len(everything)
    water = [r for r in crc if r["smiles"] == "O"]
    if water:
        w = float(predict(water, keys, beta, split_h, constant)[0])
        results["water"] = {"exp": water[0]["exp"], "chosen": w, "percent": 100 * (w - water[0]["exp"]) / water[0]["exp"], "in_holdout": water[0] in hold}
    return results


if __name__ == "__main__":
    out = run()
    target = HERE / "results" / "refit2.json"
    target.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("variants", "worst_chosen")}, indent=1))
    for name, v in out["variants"].items():
        print(name, "crc", v["crc_holdout"], "bosque", v["bosque_holdout"])
    print("shipped", out["shipped"])
    sys.exit(0)
