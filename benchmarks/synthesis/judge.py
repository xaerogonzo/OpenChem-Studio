"""The judge of the synthesis benchmark (`PREREGISTRATION.md`): the reading rule over per-target outcomes. Pure arithmetic, tested in `tests/test_synthesis_benchmark.py` before any planner run, so the rule cannot move after a result is seen.

A target row is `{"index": int, "failed": bool, "solved": bool, "recovered_at_10": bool, "top1_has_reaction": bool, "top1_valid": bool}`; a stability row is `{"index": int, "solved": [bool, bool, bool]}` (the solved flag of each of three identical runs).
Four claims, each with its own verdict, and the overall verdict from them. Feasibility is not a claim this benchmark makes.
"""
from __future__ import annotations

from dataclasses import dataclass

GO, PARTIAL, NO_GO, NOT_EVALUABLE = "GO", "PARTIAL", "NO-GO", "NOT EVALUABLE"
PASS = "PASS"
#: THE APPROVED THRESHOLDS (Alex, 2026-10-19). Fractions of the 300 targets, except the stability counts (of 20) and the validity fraction, which is of the targets whose first route has a reaction.
SOLVED_PASS, SOLVED_PARTIAL = 0.90, 0.80
RECOVERED_PASS, RECOVERED_PARTIAL = 0.50, 0.35
VALID_PASS, VALID_PARTIAL = 0.95, 0.80
#: Of the 20 repeated targets, how many must keep the same solved flag across three runs for a PASS, and for a PARTIAL (the PARTIAL bound completes the approved PASS bar and is stated in the preregistration).
STABLE_PASS, STABLE_PARTIAL = 19, 17
#: The number of repeated targets; fewer complete triples than this leaves the stability claim unestablished and the run NOT EVALUABLE.
STABILITY_TARGETS = 20
#: More than this fraction of targets that FAILED (the planner crashed, timed out or returned nothing parseable) makes the run NOT EVALUABLE: that is a protocol or environment defect, not a planner result.
FAILED_ALLOWED = 0.05
#: Fewer targets than this with a first route that has a reaction leaves the validity claim empty, and the run NOT EVALUABLE.
VALIDITY_MINIMUM = 100


@dataclass(frozen=True)
class Claim:
    name: str
    value: float | None
    verdict: str


def _grade(value: float | None, passes: float, partial: float) -> str:
    if value is None:
        return NOT_EVALUABLE
    if value >= passes:
        return PASS
    if value >= partial:
        return PARTIAL
    return NO_GO


def judge(rows: list[dict], stability: list[dict]) -> dict:
    """The four claims and the overall verdict. NOT EVALUABLE when too many targets failed or the validity claim has nothing to stand on."""
    total = len(rows)
    failed = sum(1 for r in rows if r["failed"])
    solved = sum(1 for r in rows if r["solved"] and not r["failed"])
    recovered = sum(1 for r in rows if r["recovered_at_10"] and not r["failed"])
    with_reaction = [r for r in rows if r["top1_has_reaction"] and not r["failed"]]
    valid = sum(1 for r in with_reaction if r["top1_valid"])
    stable = sum(1 for s in stability if len(set(s["solved"])) == 1)

    claims = {
        "solved": Claim("a route was returned (solved with the set stock)", solved / total if total else None, _grade(solved / total if total else None, SOLVED_PASS, SOLVED_PARTIAL)),
        "recovered": Claim("the reference route is among the first 10 returned", recovered / total if total else None, _grade(recovered / total if total else None, RECOVERED_PASS, RECOVERED_PARTIAL)),
        "valid": Claim("the first route is fully validated", valid / len(with_reaction) if with_reaction else None, _grade(valid / len(with_reaction) if with_reaction else None, VALID_PASS, VALID_PARTIAL)),
        "stable": Claim("the solved flag is identical across three runs", float(stable) if stability else None, _grade(float(stable) if stability else None, STABLE_PASS, STABLE_PARTIAL)),
    }
    if not total or failed / total > FAILED_ALLOWED or len(with_reaction) < VALIDITY_MINIMUM or len(stability) < STABILITY_TARGETS:
        overall = NOT_EVALUABLE
    else:
        verdicts = [c.verdict for c in claims.values()]
        overall = GO if all(v == PASS for v in verdicts) else NO_GO if NO_GO in verdicts else PARTIAL
    return {"overall": overall, "claims": claims, "targets": total, "failed": failed, "with_reaction": len(with_reaction), "stability_targets": len(stability)}
