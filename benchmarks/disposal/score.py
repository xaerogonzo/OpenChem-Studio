"""Score the disposal-flush A/B: does the mid-test flush move the crash rate?

## THE PREREGISTRATION LIVES IN `README.md`, NEXT TO THIS FILE

Read it before running anything. The decision rule, the escalation and
the power were fixed there BEFORE either arm was dispatched, because a
threshold chosen after seeing a number is a description of that number
and not a test of it -- the discipline
`benchmarks/solubility/base_bias.py` already applies here.

## TWO MODES, AND A REPLICA CANNOT EMIT A TABLE

    --leg     one CI leg -> one Bernoulli trial, written as leg.json
    --score   many leg.json -> the 2x2, Fisher exact p, odds ratio, CI

A single replica is one trial. The 2x2 assembles ACROSS arms, which is
why the two modes are separate rather than one script that "reports the
result" per leg.

## THE OUTCOME IS THE CENSUS SENTINEL, NEVER A GREP OF THE LOG

`tools/read_census.py` owns "did this session finish", and this defers to
it rather than reimplementing the question. Two implementations of one
oracle would drift, and this repository has paid for that four times.
Grepping `suite.log` for a crash marker is worse still: the phrase
appears in `conftest`'s own docstring, so the grep counts its own
subject -- measured, a run reporting "crash markers: 4" had not crashed.

## AND IT REFUSES A PARTIAL MATRIX RATHER THAN AVERAGING IT

**AN ARM THAT DOES NOT RUN IS NOT AN ARM.** This project has recorded
that twice -- three mutation arms that errored instead of running and
scored as passes, and a ran-count check that caught an arm as `INVALID
-- only 92 of 93 ran`. A leg that produced neither a pytest summary nor
a crash trail ran nothing, and scoring it as a completion is how a
partial matrix becomes a published n=10. So `--score` refuses unless it
holds every replica it was told to expect and every leg is accounted
for.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from read_census import read_census  # noqa: E402

#: The two arms. `control` is the shipped behaviour -- `conftest.dispose`
#: flushing the DeferredDelete itself; `treatment` defers that delivery to
#: `flush_deferred_deletes` at end of test. Both destroy the object.
ARMS = ("control", "treatment")

#: A run that reached the end prints one of these. Its ABSENCE is not the
#: oracle for a crash -- the census sentinel is -- but its presence is what
#: says a leg ran at all, which is the separate question `--score` refuses on.
SUMMARY = ("passed", "failed", "error")


def leg_record(census_text: str, log_text: str, arm: str, replica: str) -> dict:
    """One CI leg as one Bernoulli trial."""
    census = read_census(census_text)
    summary = [
        line
        for line in log_text.splitlines()
        if any(word in line for word in SUMMARY) and "==" in line
    ]

    # **`usable` IS NOT OPTIONAL.** `Census`'s own docstring says a caller
    # that ignores it "turns an unreadable trail into a clean bill of
    # health" -- and here it would do the opposite and worse: an
    # unreadable trail has `finished=False`, so a bare negation scores a
    # leg that produced no evidence as a CRASH. Three states, and
    # "could not tell" is one of them.
    if census.usable:
        crashed = not census.finished
    elif summary:
        # No trail, but pytest printed its summary: it reached the end.
        crashed = False
    else:
        crashed = None  # neither witness -- refused by `score()`

    return {
        "arm": arm,
        "replica": str(replica),
        # From the sentinel, never from a crash-marker count: that phrase
        # appears in `conftest`'s own docstring, so the grep counts its
        # own subject.
        "crashed": crashed,
        "census_usable": census.usable,
        "victim": census.victim,
        "tests_begun": census.tests_begun,
        "late_during_run": census.late_during_run,
        "has_summary": bool(summary),
        "summary": summary[-1] if summary else None,
        "detail": census.detail,
        # A leg with NEITHER witness ran nothing at all -- a runner that
        # died before pytest started, a checkout that failed. Refused
        # rather than counted.
        "ran": crashed is not None,
    }


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]].

    Written out rather than pulled from scipy, which is not a dependency
    of this project. Summing every table at least as extreme as the
    observed one, by probability -- the conventional two-sided form.
    """
    n = a + b + c + d
    row1, row2 = a + b, c + d
    col1 = a + c

    def table_p(x: int) -> float:
        return math.exp(
            math.lgamma(row1 + 1)
            + math.lgamma(row2 + 1)
            + math.lgamma(col1 + 1)
            + math.lgamma(n - col1 + 1)
            - math.lgamma(n + 1)
            - math.lgamma(x + 1)
            - math.lgamma(row1 - x + 1)
            - math.lgamma(col1 - x + 1)
            - math.lgamma(n - row1 - col1 + x + 1)
        )

    observed = table_p(a)
    low = max(0, col1 - row2)
    high = min(row1, col1)
    # The 1e-9 slack keeps a table that ties the observed probability from
    # being dropped by floating-point noise, which would understate p.
    return min(1.0, sum(table_p(x) for x in range(low, high + 1) if table_p(x) <= observed * (1 + 1e-9)))


def odds_ratio(a: int, b: int, c: int, d: int) -> float | None:
    """None when a cell is zero, which is the EXPECTED success case.

    A total elimination of the crash in the treatment arm puts a zero in
    the table and makes the odds ratio infinite. Reporting a finite
    number there means having quietly applied a continuity correction --
    inventing a value the data does not carry -- so this returns None and
    lets the interval carry the claim instead.
    """
    if 0 in (a, b, c, d):
        return None
    return (a * d) / (b * c)


def wilson(successes: int, total: int, z: float = 1.959963985) -> tuple[float, float]:
    """A 95% Wilson score interval for one arm's crash rate.

    Wilson rather than the normal approximation because the interesting
    outcome here is 0 successes out of 10, where the normal interval is
    the degenerate [0, 0] and says the rate is known exactly.
    """
    if total == 0:
        return (0.0, 1.0)
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def score(legs: list[dict], expected: dict[str, list[str]]) -> dict:
    """The 2x2 and its statistics, or a refusal."""
    problems: list[str] = []
    for arm in ARMS:
        want = sorted(str(r) for r in expected.get(arm, []))
        got = sorted(leg["replica"] for leg in legs if leg["arm"] == arm)
        if want != got:
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            problems.append(
                f"{arm}: expected replicas {want}, got {got}"
                + (f" -- MISSING {missing}" if missing else "")
                + (f" -- UNEXPECTED {extra}" if extra else "")
            )
    for leg in legs:
        if not leg["ran"]:
            problems.append(
                f"{leg['arm']} replica {leg['replica']}: no pytest summary AND no "
                "census trail -- this leg ran nothing and must not be scored"
            )
    if problems:
        return {"refused": True, "problems": problems}

    counts = {
        arm: {
            "crashed": sum(1 for leg in legs if leg["arm"] == arm and leg["crashed"]),
            "total": sum(1 for leg in legs if leg["arm"] == arm),
        }
        for arm in ARMS
    }
    a = counts["control"]["crashed"]
    b = counts["control"]["total"] - a
    c = counts["treatment"]["crashed"]
    d = counts["treatment"]["total"] - c
    return {
        "refused": False,
        "table": {"control": [a, b], "treatment": [c, d]},
        "fisher_p": fisher_exact_two_sided(a, b, c, d),
        "odds_ratio": odds_ratio(a, b, c, d),
        "control_rate_ci": wilson(a, a + b),
        "treatment_rate_ci": wilson(c, c + d),
        "victims": sorted({leg["victim"] for leg in legs if leg["victim"]}),
    }


def _render(result: dict) -> str:
    if result["refused"]:
        lines = ["REFUSED -- this is not the experiment that was registered:", ""]
        lines += [f"  - {p}" for p in result["problems"]]
        lines += ["", "An arm that does not run is not an arm. Nothing is scored."]
        return "\n".join(lines)
    a, b = result["table"]["control"]
    c, d = result["table"]["treatment"]
    orv = result["odds_ratio"]
    lo1, hi1 = result["control_rate_ci"]
    lo2, hi2 = result["treatment_rate_ci"]
    verdict = (
        "AN EFFECT (p < 0.05)"
        if result["fisher_p"] < 0.05
        else "INSUFFICIENT EVIDENCE -- change nothing"
    )
    return "\n".join(
        [
            "                crashed  completed",
            f"  control       {a:>7}  {b:>9}",
            f"  treatment     {c:>7}  {d:>9}",
            "",
            f"  Fisher exact (two-sided)  p = {result['fisher_p']:.4f}",
            f"  odds ratio                {'undefined (a zero cell)' if orv is None else f'{orv:.3f}'}",
            f"  control   crash rate 95% CI  [{lo1:.3f}, {hi1:.3f}]",
            f"  treatment crash rate 95% CI  [{lo2:.3f}, {hi2:.3f}]",
            "",
            f"  VERDICT: {verdict}",
            "",
            "  victims: " + (", ".join(result["victims"]) or "none -- every leg finished"),
        ]
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    one = sub.add_parser("leg", help="write one leg's record")
    one.add_argument("--census", type=Path, required=True)
    one.add_argument("--log", type=Path, required=True)
    one.add_argument("--arm", choices=ARMS, required=True)
    one.add_argument("--replica", required=True)
    one.add_argument("--out", type=Path, default=Path("leg.json"))

    many = sub.add_parser("score", help="assemble the 2x2 from many leg records")
    many.add_argument("legs", type=Path, nargs="+")
    many.add_argument(
        "--expect",
        required=True,
        help='JSON: {"control": [1,2,...], "treatment": [1,2,...]}',
    )

    args = parser.parse_args(argv[1:])

    if args.mode == "leg":
        record = leg_record(
            args.census.read_text(encoding="utf-8", errors="replace")
            if args.census.is_file()
            else "",
            args.log.read_text(encoding="utf-8", errors="replace")
            if args.log.is_file()
            else "",
            args.arm,
            args.replica,
        )
        args.out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=1))
        return 0

    legs = [json.loads(p.read_text(encoding="utf-8")) for p in args.legs]
    result = score(legs, json.loads(args.expect))
    print(_render(result))
    return 1 if result["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
