"""Read pytest's JUnit XML and say where the suite's time goes.

    python tools/suite_timings.py windows=suite-timings-windows.xml
    python tools/suite_timings.py windows=win.xml linux=linux.xml

WHY THIS EXISTS. The Windows and Linux CI jobs run the same pytest
invocation against the same tree -- Linux additionally under `xvfb-run`
and on a different runner image -- and finish 35-41 minutes against
18m36. Until this was written the only number either job produced was the
total, so nothing could distinguish "the Windows runner is uniformly
slower" from "one class of test pays a platform cost there". Those have
completely different fixes and the second one is actionable.

WHY JUNIT RATHER THAN `--durations`. `--durations=N` prints the slowest N
and nothing joinable. The suite here is a LONG TAIL, not an outlier --
after the regulatory build left it, the slowest test is ~21 s out of
~1236 s across 7836 tests -- so the question is about aggregates per file
and per platform, which needs a time for EVERY test.

WHAT IT CANNOT DO. `--junitxml` is written at session finish, so this
reads COMPLETED runs only. A segfault or a CI timeout leaves no usable
XML. That is a real limit and not worked around here: the repository's
one crash-surviving per-test instrument is the Qt census in
`tests/conftest.py`, and switching it on wraps `QWidget.__init__` -- that
file records double-wrapping destabilising a run by itself. An instrument
that changes what it measures is worse than none, and timing is precisely
what it would distort.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

REPO = Path(__file__).resolve().parent.parent

#: Ratio views ignore anything under this, because a ratio on a tiny file
#: is noise wearing a big number. See `_by_ratio`.
DEFAULT_MIN_SECONDS = 5.0

#: How many rows each table prints.
DEFAULT_TOP = 25


class TimingError(RuntimeError):
    """The report could not be trusted, with the reason a reader needs."""


@dataclass
class Case:
    file: str
    name: str
    seconds: float
    status: str


@dataclass
class Report:
    label: str
    path: Path
    cases: list[Case] = field(default_factory=list)
    #: What the `<testsuite>` element DECLARED, which is the oracle the
    #: parsed rows are checked against rather than a second opinion.
    declared_tests: int = 0
    declared_time: float = 0.0

    @property
    def summed(self) -> float:
        return sum(case.seconds for case in self.cases)

    def by_file(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for case in self.cases:
            totals[case.file] += case.seconds
        return dict(totals)

    def counts(self) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for case in self.cases:
            totals[case.status] += 1
        return dict(totals)


def _file_for(classname: str) -> str:
    """`tests.test_foo` and `tests.test_foo.TestBar` both -> `tests/test_foo.py`.

    pytest's JUnit output carries no `file` attribute, only the dotted
    `classname`, and a class-based test appends the class to it. So the
    longest dotted prefix that names a real file wins, and a name that
    matches nothing on disk is returned as-is rather than guessed at --
    a wrong file attribution would move seconds between rows silently,
    which is the one thing this report must not do.
    """
    # AN EMPTY CLASSNAME IS A REAL CASE AND IT USED TO CRASH HERE.
    # `"".split(".")` is `[""]`, not `[]`, so the loop ran once with
    # `Path("")` -- which is `.` -- and `with_suffix` raised `has an empty
    # name`. The `or "<unknown>"` below looked like the guard for it and
    # sat after the loop, unreachable. Found by feeding the parser a file
    # of deliberate outcomes rather than by reading it.
    parts = [p for p in classname.split(".") if p]
    while parts:
        candidate = Path(*parts).with_suffix(".py")
        if (REPO / candidate).is_file():
            return candidate.as_posix()
        parts.pop()
    return classname or "<unknown>"


#: What pytest's JUnit writer actually emits, MEASURED on a file of
#: deliberate outcomes rather than assumed from the terminal summary --
#: the two do not agree and the differences both under-report:
#:
#:     pytest says    JUnit writes
#:     passed         no child element
#:     xpassed        no child element      <- indistinguishable
#:     skipped        <skipped type="pytest.skip">
#:     xfailed        <skipped type="pytest.xfail">   <- counted as skipped
#:     failed         <failure>
#:     error          <error>
#:
#: So `1 failed, 1 passed, 1 skipped, 1 xfailed, 1 xpassed, 1 error` came
#: back as `errors="1" failures="1" skipped="2"` over six `<testcase>`
#: rows. The row COUNT is trustworthy -- one per outcome, errors included,
#: which is what `load` checks -- but a status breakdown read as pytest's
#: own vocabulary would be wrong twice.
_XFAIL_TYPE = "pytest.xfail"


def _status_of(case: ElementTree.Element) -> str:
    if case.find("failure") is not None:
        return "failed"
    if case.find("error") is not None:
        return "error"
    skipped = case.find("skipped")
    if skipped is not None:
        return "xfailed" if skipped.get("type") == _XFAIL_TYPE else "skipped"
    # Includes xpassed, which JUnit does not distinguish from a pass.
    return "passed_or_xpassed"


def load(label: str, path: Path) -> Report:
    """Parse one report, refusing anything it cannot vouch for.

    **A TRUNCATED FILE MUST NOT PRODUCE A CONFIDENT TOTAL.** A run killed
    by a CI timeout is exactly when somebody reaches for this, and a
    silently short XML would understate the very tail being looked for.
    Two things catch it: the XML does not parse at all when the closing
    tags are missing, and the `<testsuite tests=...>` count is compared
    with the rows actually read.
    """
    if not path.is_file():
        raise TimingError(f"{label}: {path} does not exist")
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        raise TimingError(
            f"{label}: {path} is not well-formed XML ({exc}). A run killed "
            f"mid-session leaves a partial file; there is nothing to report "
            f"from it."
        ) from exc

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise TimingError(f"{label}: {path} contains no <testsuite> element")

    report = Report(label=label, path=path)
    for suite in suites:
        report.declared_tests += int(suite.get("tests", 0))
        report.declared_time += float(suite.get("time", 0.0) or 0.0)
        for case in suite.iter("testcase"):
            report.cases.append(
                Case(
                    file=_file_for(case.get("classname", "")),
                    name=case.get("name", "<unnamed>"),
                    seconds=float(case.get("time", 0.0) or 0.0),
                    status=_status_of(case),
                )
            )

    if len(report.cases) != report.declared_tests:
        raise TimingError(
            f"{label}: <testsuite> declares {report.declared_tests} tests but "
            f"{len(report.cases)} <testcase> rows were read. The file is "
            f"incomplete or not what it claims; refusing to total it."
        )
    return report


def _table(rows, headers, widths) -> str:
    line = "  ".join(h.ljust(w) if i == 0 else h.rjust(w) for i, (h, w) in enumerate(zip(headers, widths)))
    out = [line, "  ".join("-" * w for w in widths)]
    for row in rows:
        out.append("  ".join(
            str(c).ljust(w) if i == 0 else str(c).rjust(w)
            for i, (c, w) in enumerate(zip(row, widths))
        ))
    return "\n".join(out)


def describe(report: Report, top: int, wall: float | None = None) -> str:
    out = [
        f"=== {report.label}  ({report.path.name}) ===",
        f"  tests            {len(report.cases)}",
        f"  by status        " + "  ".join(
            f"{k}={v}" for k, v in sorted(report.counts().items())
        ),
        f"  sum of per-test  {report.summed:9.1f} s",
        f"  <testsuite time> {report.declared_time:9.1f} s",
    ]
    # THE GAP IS A FINDING IN ITS OWN RIGHT, AND THE XML CANNOT SHOW IT
    # ALONE. Per-test times exclude collection, session-scoped fixtures and
    # interpreter startup, so a large difference between them and the JOB'S
    # WALL CLOCK says the cost is in none of the tests and no per-test
    # optimisation will touch it.
    #
    # `<testsuite time>` is NOT that wall clock -- measured on a 44-test
    # run, pytest reported 6.93 s while the attribute said 5.377 s. An
    # earlier draft of this function subtracted the two and labelled the
    # 0.1 s difference "collection", which was wrong by an order of
    # magnitude and would have read as "there is nothing outside the
    # tests". So the wall clock is an INPUT, and its absence is stated
    # rather than papered over.
    if wall is not None:
        out.append(f"  wall clock       {wall:9.1f} s   (given)")
        out.append(
            f"  unattributed     {wall - report.summed:9.1f} s   "
            f"(collection, session fixtures, interpreter startup)"
        )
    else:
        out.append(
            "  unattributed         -- pass --wall=SECONDS (pytest's own "
            "summary, or the CI job duration) to see it"
        )
    out.append("")
    out.append(f"  slowest {top} tests")
    slowest = sorted(report.cases, key=lambda c: -c.seconds)[:top]
    out.append(_table(
        [(f"{c.file}::{c.name}"[:78], f"{c.seconds:.2f}") for c in slowest],
        ("test", "seconds"), (78, 9),
    ))
    out.append("")
    out.append(f"  slowest {top} files")
    files = sorted(report.by_file().items(), key=lambda kv: -kv[1])[:top]
    out.append(_table(
        [(f, f"{s:.1f}", f"{100 * s / report.summed:.1f}%") for f, s in files],
        ("file", "seconds", "share"), (58, 9, 7),
    ))
    return "\n".join(out)


def compare(a: Report, b: Report, top: int, min_seconds: float) -> str:
    """Per-file, both absolute and relative.

    **A RATIO ALONE MISLEADS IN BOTH DIRECTIONS, which is why every view
    below carries the seconds too.** A file at 0.20 s against 0.05 s is a
    4x ratio contributing nothing to a twenty-minute gap; one at 180 s
    against 120 s is a 1.5x ratio contributing a full minute. Sorting by
    ratio alone would put the first at the top and bury the second.
    """
    left, right = a.by_file(), b.by_file()
    rows = []
    for name in sorted(set(left) | set(right)):
        x, y = left.get(name, 0.0), right.get(name, 0.0)
        ratio = (x / y) if y > 0 else float("inf")
        rows.append((name, x, y, x - y, ratio))

    def fmt(subset):
        return _table(
            [(n[:52], f"{x:.1f}", f"{y:.1f}", f"{d:+.1f}",
              ("inf" if r == float("inf") else f"{r:.2f}"))
             for n, x, y, d, r in subset],
            ("file", a.label, b.label, "delta", "ratio"), (52, 9, 9, 9, 7),
        )

    out = [
        "",
        f"=== {a.label} vs {b.label} ===",
        f"  total per-test   {a.summed:9.1f} s   {b.summed:9.1f} s   "
        f"({a.summed - b.summed:+.1f} s)",
        "",
        f"  largest absolute delta ({a.label} - {b.label}) -- where the gap actually is",
        fmt(sorted(rows, key=lambda r: -r[3])[:top]),
        "",
        f"  largest ratio among files over {min_seconds:g} s in {a.label}"
        " -- which KIND of test pays",
        fmt(sorted([r for r in rows if r[1] >= min_seconds], key=lambda r: -r[4])[:top]),
        "",
        f"  largest {a.label} runtime -- what dominates regardless of platform",
        fmt(sorted(rows, key=lambda r: -r[1])[:top]),
    ]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    top, min_seconds, specs = DEFAULT_TOP, DEFAULT_MIN_SECONDS, []
    walls: dict[str, float] = {}
    for arg in argv:
        if arg.startswith("--top="):
            top = int(arg.split("=", 1)[1])
        elif arg.startswith("--min-seconds="):
            min_seconds = float(arg.split("=", 1)[1])
        elif arg.startswith("--wall"):
            # --wall=SECONDS for one report, or --wall-<label>=SECONDS
            key, _, value = arg.partition("=")
            walls[key[len("--wall"):].lstrip("-")] = float(value)
        elif "=" in arg:
            label, _, path = arg.partition("=")
            specs.append((label, Path(path)))
        else:
            specs.append((Path(arg).stem, Path(arg)))
    if not specs:
        print(__doc__)
        return 2

    reports = [load(label, path) for label, path in specs]
    for report in reports:
        print(describe(report, top, walls.get(report.label, walls.get(""))))
        print()
    if len(reports) == 2:
        print(compare(reports[0], reports[1], top, min_seconds))
    elif len(reports) > 2:
        print(f"(comparison is pairwise; {len(reports)} reports given, showing each alone)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except TimingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
