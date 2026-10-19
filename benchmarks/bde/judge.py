"""The judge of the bond-dissociation benchmark (`docs/BDE_DESIGN.md`): the reading rule over computed and reference DH298. Pure arithmetic, tested in `tests/test_bde_benchmark.py`, so the rule cannot move after a result is seen.

A record is `{"name": str, "dh_ref": float, "uncertainty": float, "dh_kcal": float|None}`: Blanksby and Ellison's value and its stated uncertainty (kcal/mol) and the computed one (None for a bond the arm did not produce). The error is computed - reference.
"""
from __future__ import annotations

from dataclasses import dataclass

PASS, PARTIAL, FAIL, NOT_EVALUABLE = "PASS", "PARTIAL", "FAIL", "NOT EVALUABLE"
#: A bond whose stated experimental uncertainty is above this (kcal/mol) is in the LOW-precision stratum, reported and never deciding: a reference that loose cannot tell a good calculation from a bad one.
UNCERTAINTY_LIMIT = 1.0
#: THE THRESHOLDS (kcal/mol), proposed in `docs/BDE_DESIGN.md` and frozen only when the preregistration is committed: the mean absolute error for a PASS, the largest single error, the mean signed error, and the mean absolute error up to which a result is PARTIAL.
MAE_PASS = {"primary": 2.5, "secondary": 2.0}
MAX_ERROR = 5.0
MSE_LIMIT = 1.5
MAE_PARTIAL = 3.5
#: More missing bonds than this in the deciding stratum is NOT EVALUABLE.
MISSING_ALLOWED = 3


@dataclass(frozen=True)
class Stats:
    count: int
    missing: int
    mae: float | None
    mse: float | None
    max_abs: float | None


def is_low(record: dict) -> bool:
    return record["uncertainty"] > UNCERTAINTY_LIMIT


def stats(records: list[dict]) -> Stats:
    """Mean absolute, mean signed and largest absolute error over the records that have a computed value, and how many are missing."""
    errors = [r["dh_kcal"] - r["dh_ref"] for r in records if r.get("dh_kcal") is not None]
    missing = len(records) - len(errors)
    if not errors:
        return Stats(0, missing, None, None, None)
    return Stats(len(errors), missing, sum(abs(e) for e in errors) / len(errors), sum(errors) / len(errors), max(abs(e) for e in errors))


def verdict(deciding: Stats, arm: str) -> str:
    """NOT EVALUABLE if more than three deciding bonds are missing; PASS at MAE <= the arm's limit with no error above 5 and a mean signed error within 1.5; PARTIAL up to MAE 3.5; else FAIL."""
    if deciding.missing > MISSING_ALLOWED or deciding.count == 0:
        return NOT_EVALUABLE
    if deciding.mae <= MAE_PASS[arm] and deciding.max_abs <= MAX_ERROR and abs(deciding.mse) <= MSE_LIMIT:
        return PASS
    if deciding.mae <= MAE_PARTIAL:
        return PARTIAL
    return FAIL


def judge(records: list[dict], arm: str) -> dict:
    """The verdict on the deciding stratum and the statistics of the deciding stratum, the low-precision stratum and all bonds (the last two reported, in no rule)."""
    deciding = stats([r for r in records if not is_low(r)])
    return {"verdict": verdict(deciding, arm), "deciding": deciding, "low": stats([r for r in records if is_low(r)]), "all": stats(records)}
