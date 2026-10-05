"""Measure the Windows suite's crash rate, per arm, from the legs of `windows-crash-rate.yml`.

    python tools/crash_rate.py leg --arm as-is --replica 3 --exit-code 1 --crashed true \\
        --seconds 840 --detail "shard 1 crashed at 5%" --out leg-as-is-3.json
    python tools/crash_rate.py report legs/            # a markdown table, to the step summary

WHY THIS EXISTS. The access-violation crash cannot be reproduced locally (it needs the CI runner's
desktop session and GPU), and it fires on roughly half of master's first attempts, so the only way to
learn whether a change to it did anything is to sample it on CI, many times, under controlled
conditions. A fix that "looked green" on three pushes proved nothing: at a crash rate near 50% three
greens happen by chance one time in eight. The `workflow_dispatch` workflow runs ONE shard N times
per arm, ONCE EACH (no retry, which would hide exactly the event being counted), and this tool turns
the legs into a rate with an interval and a significance test.

**WHAT A LEG IS.** One attempt at one shard, classified by `tools/ci_classify_crash.ps1` (a crash is
a fatal exception, no pytest summary line and no FAILED/ERROR line) and by the shard's exit code:

    crashed   the process died; no test is reported failed          <- what is being counted
    failed    pytest finished and reported a real failure           <- NOT a crash; reported, not counted
    passed    pytest finished clean

**THE RATE IS crashed / (crashed + failed + passed).** A leg that never reported (the job was
cancelled or timed out) is listed as MISSING and is not in the denominator: counting it either way
would be a guess about a run nobody observed.

**TWO ARMS ARE COMPARED WITH FISHER'S EXACT TEST,** not a z-test: the legs are few (10 to 20 per arm)
and the rates sit near the ends of the range, where the normal approximation is wrong. The interval
on each rate is Wilson's, for the same reason. Neither is a license to stop sampling when the number
looks good: choose the replica count BEFORE the run (`docs/LESSONS.md`, "A P-VALUE LOOKED AT REPEATEDLY
IS NOT A P-VALUE").
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

OUTCOMES = ("crashed", "failed", "passed")


def leg_outcome(crashed: bool, exit_code: int) -> str:
    """`crashed` wins over the exit code: a crash exits non-zero too, and is not a test failure."""
    if crashed:
        return "crashed"
    return "passed" if exit_code == 0 else "failed"


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """The 95% Wilson score interval for a proportion. (0, 0) for n == 0, which means "no data", and
    the caller says so rather than printing it as a rate."""
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_exact(a_hits: int, a_n: int, b_hits: int, b_n: int) -> float:
    """Two-sided Fisher's exact p-value for `a_hits/a_n` against `b_hits/b_n`.

    Sums the probability of every table with the same margins that is no more likely than the
    observed one (the standard two-sided definition, with a small tolerance for float ties)."""
    if min(a_n, b_n) <= 0:
        return 1.0
    hits, n = a_hits + b_hits, a_n + b_n

    def pmf(k: int) -> float:
        return math.comb(a_n, k) * math.comb(b_n, hits - k) / math.comb(n, hits)

    lo, hi = max(0, hits - b_n), min(a_n, hits)
    observed = pmf(a_hits)
    return min(1.0, sum(p for p in (pmf(k) for k in range(lo, hi + 1)) if p <= observed * (1 + 1e-9)))


@dataclass(frozen=True)
class ArmSummary:
    arm: str
    crashed: int
    failed: int
    passed: int

    @property
    def n(self) -> int:
        return self.crashed + self.failed + self.passed

    @property
    def rate(self) -> float | None:
        return self.crashed / self.n if self.n else None

    @property
    def interval(self) -> tuple[float, float]:
        return wilson(self.crashed, self.n)


def load_legs(directory: Path) -> list[dict]:
    legs = []
    for path in sorted(directory.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("outcome") in OUTCOMES and "arm" in data:
            legs.append(data)
    return legs


def summarise(legs: list[dict]) -> list[ArmSummary]:
    arms: dict[str, dict[str, int]] = {}
    for leg in legs:
        counts = arms.setdefault(leg["arm"], dict.fromkeys(OUTCOMES, 0))
        counts[leg["outcome"]] += 1
    return [ArmSummary(arm, c["crashed"], c["failed"], c["passed"]) for arm, c in sorted(arms.items())]


def render(summaries: list[ArmSummary], expected: dict[str, int] | None = None, legs: list[dict] | None = None) -> str:
    """The markdown the workflow writes to its step summary. `expected` (arm -> planned legs) lets a
    cancelled or timed-out leg show as MISSING instead of silently shrinking n."""
    lines = [
        "## Windows crash rate",
        "",
        "| arm | legs | crashed | failed | passed | crash rate | 95% interval (Wilson) | missing |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        low, high = s.interval
        rate = "no data" if s.rate is None else f"{s.rate:.0%}"
        interval = "n/a" if s.rate is None else f"{low:.0%} to {high:.0%}"
        missing = max(0, (expected or {}).get(s.arm, s.n) - s.n)
        lines.append(f"| {s.arm} | {s.n} | {s.crashed} | {s.failed} | {s.passed} | {rate} | {interval} | {missing} |")
    for arm, planned in sorted((expected or {}).items()):
        if arm not in {s.arm for s in summaries}:
            lines.append(f"| {arm} | 0 | 0 | 0 | 0 | no data | n/a | {planned} |")
    if len(summaries) == 2 and all(s.n for s in summaries):
        a, b = summaries
        p = fisher_exact(a.crashed, a.n, b.crashed, b.n)
        lines += [
            "",
            f"**{a.arm} vs {b.arm}: Fisher's exact p = {p:.3f}** "
            f"({a.crashed}/{a.n} against {b.crashed}/{b.n} crashed).",
            "",
            "Two-sided, one pre-chosen sample size. Do not extend the run until this crosses 0.05; "
            "a non-significant result at this n means the difference is not large enough to see, "
            "not that there is none.",
        ]
    elif len(summaries) == 1:
        lines += ["", "One arm: this is a rate, not a comparison."]
    crashes = [leg for leg in (legs or []) if leg["outcome"] == "crashed"]
    if crashes:
        lines += ["", "### Where the crashes were", ""]
        lines += [f"- {leg['arm']} #{leg.get('replica', '?')}: {leg.get('detail') or 'no detail'}" for leg in crashes]
    return "\n".join(lines) + "\n"


def _bool(text: str) -> bool:
    return text.strip().lower() == "true"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    leg = sub.add_parser("leg", help="write one leg's JSON")
    leg.add_argument("--arm", required=True)
    leg.add_argument("--replica", required=True)
    leg.add_argument("--exit-code", type=int, required=True)
    leg.add_argument("--crashed", type=_bool, required=True)
    leg.add_argument("--seconds", type=float, default=0.0)
    leg.add_argument("--detail", default="")
    leg.add_argument("--ref", default="")
    leg.add_argument("--out", required=True, type=Path)
    report = sub.add_parser("report", help="summarise a directory of legs as markdown")
    report.add_argument("directory", type=Path)
    report.add_argument("--expected", default="", help='JSON object, arm -> planned legs: \'{"as-is": 10}\'')
    args = parser.parse_args(argv)

    if args.command == "leg":
        args.out.write_text(
            json.dumps(
                {
                    "arm": args.arm,
                    "replica": args.replica,
                    "outcome": leg_outcome(args.crashed, args.exit_code),
                    "exit_code": args.exit_code,
                    "seconds": round(args.seconds, 1),
                    "detail": args.detail,
                    "ref": args.ref,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0

    legs = load_legs(args.directory)
    expected = json.loads(args.expected) if args.expected else None
    print(render(summarise(legs), expected, legs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
