"""The judge of `PREREGISTRATION.md`: the reading rule over the computed and reference values, for each of PA and GB and for each arm. Pure arithmetic, tested in `tests/test_proton_affinity_judge.py`, so the rule cannot move after a result is seen.

A record is `{"name": str, "pa_ref_kj": float, "gb_ref_kj": float, "pa_kcal": float|None, "gb_kcal": float|None}`: the Hunter-Lias values from `nist_values.json` in kJ/mol and the computed ones in kcal/mol (None for a base the arm did not
produce). The error is computed - reference, in kcal/mol.
"""
from __future__ import annotations

from dataclasses import dataclass

PASS, PARTIAL, FAIL, NOT_EVALUABLE = "PASS", "PARTIAL", "FAIL", "NOT EVALUABLE"
KJ_PER_KCAL = 4.184
#: Hunter and Lias: the scale is not well established below propene's proton affinity (751.6 kJ/mol); bases whose reference PA is at or below this are the LOW stratum, reported and never deciding.
LOW_BASICITY_KJ = 751.6
#: The approved thresholds (kcal/mol): the mean absolute error for a PASS, per arm; the largest single error; the mean signed error; and the mean absolute error up to which a result is PARTIAL.
MAE_PASS = {"primary": 2.5, "secondary": 2.0}
MAX_ERROR = 5.0
MSE_LIMIT = 1.5
MAE_PARTIAL = 4.0
#: More missing bases than this in the deciding stratum is NOT EVALUABLE.
MISSING_ALLOWED = 2


@dataclass(frozen=True)
class Stats:
    count: int
    missing: int
    mae: float | None
    mse: float | None
    max_abs: float | None


def reference_kcal(record: dict, quantity: str) -> float:
    return record[f"{quantity}_ref_kj"] / KJ_PER_KCAL


def is_low(record: dict) -> bool:
    return record["pa_ref_kj"] <= LOW_BASICITY_KJ


def stratum(records: list[dict], low: bool) -> list[dict]:
    return [r for r in records if is_low(r) is low]


def stats(records: list[dict], quantity: str) -> Stats:
    """Mean absolute, mean signed and largest absolute error (kcal/mol) over the records that have a computed value, and how many are missing."""
    errors = [r[f"{quantity}_kcal"] - reference_kcal(r, quantity) for r in records if r.get(f"{quantity}_kcal") is not None]
    missing = len(records) - len(errors)
    if not errors:
        return Stats(0, missing, None, None, None)
    return Stats(len(errors), missing, sum(abs(e) for e in errors) / len(errors), sum(errors) / len(errors), max(abs(e) for e in errors))


def verdict(deciding: Stats, arm: str) -> str:
    """The rule for one quantity of one arm, on the deciding (above-propene) stratum: NOT EVALUABLE if more than two are missing; PASS at MAE <= the arm's limit with no error above 5 and a mean signed error within 1.5; PARTIAL up to MAE 4; else FAIL."""
    if deciding.missing > MISSING_ALLOWED or deciding.count == 0:
        return NOT_EVALUABLE
    if deciding.mae <= MAE_PASS[arm] and deciding.max_abs <= MAX_ERROR and abs(deciding.mse) <= MSE_LIMIT:
        return PASS
    if deciding.mae <= MAE_PARTIAL:
        return PARTIAL
    return FAIL


def judge(records: list[dict], arm: str) -> dict:
    """For PA and for GB: the verdict on the deciding stratum, and the statistics of the deciding stratum, the low stratum and all bases (the last two reported, in no rule)."""
    out: dict = {}
    for quantity in ("pa", "gb"):
        deciding = stats(stratum(records, low=False), quantity)
        out[quantity] = {"verdict": verdict(deciding, arm), "deciding": deciding, "low": stats(stratum(records, low=True), quantity), "all": stats(records, quantity)}
    return out
