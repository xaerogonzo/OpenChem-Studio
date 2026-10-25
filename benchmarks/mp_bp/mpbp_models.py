"""The candidates of `PREREGISTRATION.md` section 2, as functions of a structure, and the baseline of section 10.

Nothing here reads a label except `fit_candidate_c` and `family_baseline`, and both take their rows as arguments, so
the caller decides which partition they see: the preregistration lets them see **development** rows only (and
`fit_candidate_c` is told which penalty to use, chosen on selection rows by the caller).

A prediction is a number or a REFUSAL with a coded reason; a refusal is never a number, and the coverage of every
method is reported against the eligible denominator so that a method cannot improve its headline by refusing.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

#: The ridge penalties Candidate C may use (section 2.1); the one that gives the lowest selection MAE is used.
RIDGE_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _joback():
    sys.path.insert(0, str(ROOT / "src"))
    from openchem.chem import joback

    return joback


def _mg():
    return _load("marrero2001_groups", ROOT / "benchmarks" / "thermophysical" / "marrero2001_groups.py")


@dataclass(frozen=True)
class Prediction:
    """A value in kelvin, or a refusal reason (never both)."""

    value: float | None = None
    refusal: str = ""

    def __post_init__(self) -> None:
        if (self.value is None) == (not self.refusal):
            raise ValueError("a prediction is a value or a refusal, exactly one")


# ----------------------------------------------------------------------------------------------- Joback
def joback_features(smiles: str) -> dict:
    """Joback's fragmentation of one structure, as plain data: `{"counts": {group id: n}}` or `{"refusal": code}`."""
    from rdkit import Chem

    jb = _joback()
    f = jb.fragment(Chem.MolFromSmiles(smiles))
    if not f.applicable:
        return {"refusal": f.refusal.name}
    out = {"counts": dict(f.counts)}
    tb, tf = jb.boiling_point(f), jb.freezing_point(f)
    out["tb"] = tb
    out["tf"] = tf
    return out


def joback_prediction(features: dict, output: str) -> Prediction:
    """`output` is `"tb"` or `"tf"`."""
    if "refusal" in features:
        return Prediction(refusal=features["refusal"])
    value = features[output]
    return Prediction(refusal="NO_CONTRIBUTION") if value is None else Prediction(value=float(value))


# ----------------------------------------------------------------------------------------------- Marrero-Gani
def mg_features(smiles: str) -> dict:
    """Marrero-Gani's first-order fragmentation, as plain data: counts by group id and the Tm and Tb estimates, or
    a refusal code (`grouping_<reason>`, `no_contribution`, `nonpositive_group_sum`) for each."""
    mg = _mg()
    try:
        counts = mg.fragment(smiles).counts
    except mg.GroupingRefusal as exc:
        return {"refusal": f"grouping_{exc.reason}"}
    out: dict = {"counts": {int(k): int(v) for k, v in counts.items()}}
    for prop, key in (("Tm", "tm"), ("Tb", "tb")):
        try:
            out[key] = mg.estimate_first_order(prop, counts)
        except mg.NoContribution:
            out[key] = {"refusal": "no_contribution"}
        except ValueError:
            out[key] = {"refusal": "nonpositive_group_sum"}
    return out


def mg_prediction(features: dict, output: str) -> Prediction:
    if "refusal" in features:
        return Prediction(refusal=features["refusal"])
    value = features[output]
    if isinstance(value, dict):
        return Prediction(refusal=value["refusal"])
    return Prediction(value=float(value))


# ----------------------------------------------------------------------------------------------- Candidate C
@dataclass(frozen=True)
class CandidateC:
    """Joback's groups with coefficients fitted to ONE property on the development partition only.

    A group with no development example has no coefficient and is `unfitted`: a molecule that uses one is refused,
    so a zero is never read as a fitted contribution."""

    property: str
    penalty: float
    groups: tuple[str, ...]          # the fitted group ids, in column order
    coefficients: tuple[float, ...]
    intercept: float
    unfitted: tuple[str, ...]
    n_training: int

    def predict(self, joback: dict) -> Prediction:
        if "refusal" in joback:
            return Prediction(refusal=joback["refusal"])
        counts = joback["counts"]
        missing = sorted(g for g in counts if g in self.unfitted)
        if missing:
            return Prediction(refusal="UNFITTED_GROUP")
        by_group = dict(zip(self.groups, self.coefficients))
        return Prediction(value=self.intercept + sum(n * by_group[g] for g, n in counts.items()))

    def to_json(self) -> dict:
        return {"property": self.property, "penalty": self.penalty, "groups": list(self.groups),
                "coefficients": list(self.coefficients), "intercept": self.intercept,
                "unfitted": list(self.unfitted), "n_training": self.n_training}

    @staticmethod
    def from_json(d: dict) -> CandidateC:
        return CandidateC(d["property"], d["penalty"], tuple(d["groups"]), tuple(d["coefficients"]),
                          d["intercept"], tuple(d["unfitted"]), d["n_training"])


def fit_candidate_c(prop: str, penalty: float, joback_rows: list[dict], targets: list[float],
                    all_groups: list[str]) -> CandidateC:
    """Ridge regression, intercept unpenalised, features unscaled: `w = (Xc'Xc + lambda I)^-1 Xc' yc`, `b = ybar - xbar.w`.

    `joback_rows` are the Joback fragmentations of the DEVELOPMENT rows (a refused one has no features and is
    skipped by the caller), `targets` their labels in kelvin."""
    if penalty not in RIDGE_GRID:
        raise ValueError(f"penalty {penalty} is not in the preregistered grid {RIDGE_GRID}")
    if len(joback_rows) != len(targets) or not joback_rows:
        raise ValueError("need one target per fragmentation and at least one row")
    seen = {g for row in joback_rows for g in row["counts"]}
    fitted = [g for g in all_groups if g in seen]
    unfitted = [g for g in all_groups if g not in seen]
    col = {g: j for j, g in enumerate(fitted)}
    X = np.zeros((len(joback_rows), len(fitted)))
    for i, row in enumerate(joback_rows):
        for g, n in row["counts"].items():
            X[i, col[g]] = n
    y = np.asarray(targets, dtype=float)
    xbar, ybar = X.mean(axis=0), y.mean()
    Xc, yc = X - xbar, y - ybar
    w = np.linalg.solve(Xc.T @ Xc + penalty * np.eye(len(fitted)), Xc.T @ yc)
    return CandidateC(prop, penalty, tuple(fitted), tuple(float(v) for v in w), float(ybar - xbar @ w),
                      tuple(unfitted), len(joback_rows))


# ----------------------------------------------------------------------------------------------- baseline
def family_baseline(dev_families: list[str], dev_values: list[float]) -> tuple[dict[str, float], float]:
    """Section 10's baseline from DEVELOPMENT rows only: the mean per family, and the mean over all of them."""
    if not dev_values:
        raise ValueError("a baseline needs development rows")
    sums: dict[str, list[float]] = {}
    for fam, v in zip(dev_families, dev_values):
        sums.setdefault(fam, []).append(v)
    return {fam: math.fsum(vs) / len(vs) for fam, vs in sums.items()}, math.fsum(dev_values) / len(dev_values)


def baseline_prediction(family: str, by_family: dict[str, float], overall: float) -> float:
    return by_family.get(family, overall)
