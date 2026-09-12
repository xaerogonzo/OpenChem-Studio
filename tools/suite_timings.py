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

import json
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

#: How far the three-way split may fail to add up before it is called a
#: contradiction rather than a boundary effect. The hook's clock and
#: pytest's session clock start and stop at slightly different moments, so
#: demanding exact agreement would turn a sub-second artefact into a false
#: alarm. A gap larger than this is arithmetic that cannot be true.
RECONCILE_TOLERANCE_SECONDS = 1.0

#: Properties `tests/conftest.py` writes at session finish. The names are
#: a CONTRACT between these two files; changing one without the other
#: silently drops a number rather than failing, which is why they are
#: declared here in one place rather than spelled inline.
_SECONDS_PROPERTIES = {
    "openchem_hook_logfinish_seconds": "hook_seconds",
    "openchem_gc_collect_seconds": "gc_seconds",
}
_COUNT_PROPERTIES = {
    "openchem_hook_calls": "hook_calls",
    "openchem_gc_calls": "gc_calls",
    "openchem_retained_windows": "retained_windows",
}
_TEXT_PROPERTIES = {
    "openchem_collect_policy": "collect_policy",
}
_BUCKETS_PROPERTY = "openchem_hook_buckets"


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

    #: What `tests/conftest.py` reported about its own per-test hook.
    #: `None` means the property was ABSENT -- an XML written before this
    #: existed -- which is a different thing from a measured zero and must
    #: keep rendering the old single "unattributed" line.
    hook_seconds: float | None = None
    gc_seconds: float | None = None
    hook_calls: int | None = None
    gc_calls: int | None = None
    retained_windows: int | None = None
    collect_policy: str | None = None
    buckets: dict | None = None

    @property
    def in_session_unaccounted(self) -> float:
        """Session clock minus test time: in pytest, in no test case."""
        return self.declared_time - self.summed

    @property
    def remaining_unaccounted(self) -> float | None:
        """What is left once the hook is named. `None` if it was not."""
        if self.hook_seconds is None:
            return None
        return self.in_session_unaccounted - self.hook_seconds

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


def _numeric_property(label: str, name: str, raw: str, cast):
    """Parse one declared property, refusing a value it cannot vouch for.

    **ABSENT AND MALFORMED ARE DIFFERENT AND MUST NOT COLLAPSE.** Absent
    means an XML written before the producer existed, and the old single
    line is the right rendering for it. Malformed means the producer and
    this reader have drifted apart -- and reading it as zero would report
    "the hook costs nothing", which is the most misleading answer
    available and the exact shape of finding this branch exists to chase.
    """
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise TimingError(
            f"{label}: property {name!r} has value {raw!r}, which is not a "
            f"{cast.__name__}. The producer in tests/conftest.py and this "
            f"reader disagree; refusing to guess a number for it."
        ) from None


def _bucket_property(label: str, raw: str) -> dict:
    """Parse the self-describing bucket object.

    It carries its own `scheme` because a bare `[[785, 37.2]]` cannot say
    whether 785 counts collected tests, completed hook calls, or the stride
    between samples -- and a reader six months on would have to guess.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TimingError(
            f"{label}: property {_BUCKETS_PROPERTY!r} is not valid JSON "
            f"({exc}). Refusing to report a shape from it."
        ) from exc
    if not isinstance(parsed, dict) or "buckets" not in parsed:
        raise TimingError(
            f"{label}: property {_BUCKETS_PROPERTY!r} parsed, but is not an "
            f"object carrying a 'buckets' key. Got {type(parsed).__name__}."
        )
    return parsed


def _read_properties(report: Report, suite) -> None:
    container = suite.find("properties")
    if container is None:
        return
    for prop in container.findall("property"):
        name = prop.get("name", "")
        raw = prop.get("value", "")
        if name in _SECONDS_PROPERTIES:
            setattr(report, _SECONDS_PROPERTIES[name],
                    _numeric_property(report.label, name, raw, float))
        elif name in _COUNT_PROPERTIES:
            setattr(report, _COUNT_PROPERTIES[name],
                    _numeric_property(report.label, name, raw, int))
        elif name in _TEXT_PROPERTIES:
            setattr(report, _TEXT_PROPERTIES[name], raw)
        elif name == _BUCKETS_PROPERTY:
            report.buckets = _bucket_property(report.label, raw)


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
        _read_properties(report, suite)
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


def _accounting(report: Report, wall: float | None) -> list[str]:
    """Partition the session's time, naming every term.

    **ONE REMAINDER CALLED "unattributed" WAS THE PROBLEM.** It meant
    "wall clock not represented by a JUnit case", which silently bundled
    three unrelated things: the per-test hook, everything else inside
    pytest, and the process start/stop outside pytest's own clock. A
    single 38% could not be acted on because no one term could be
    attacked. These are the same seconds, split.

    `<testsuite time>` is NOT the wall clock -- measured on a 44-test run,
    pytest reported 6.93 s while the attribute said 5.377 s. An earlier
    draft subtracted the two and labelled the difference "collection",
    wrong by an order of magnitude. So the wall clock stays an INPUT and
    its absence is stated rather than papered over.
    """
    arm = ""
    if report.collect_policy is not None:
        arm = f"   [collect policy: {report.collect_policy}]"
    lines = [
        f"  WHERE THE TIME WENT{arm}",
        f"    test time           {report.summed:10.1f} s   "
        f"setup + call + teardown, per JUnit",
    ]
    if report.hook_seconds is None:
        lines.append(
            f"    in no test case     {report.in_session_unaccounted:10.1f} s   "
            f"in pytest, in no case (this XML declares no hook properties)"
        )
    else:
        lines.append(
            f"    runtest_logfinish   {report.hook_seconds:10.1f} s   "
            f"per-test hook, outside all three phases"
        )
        if report.gc_seconds is not None:
            detail = ""
            if report.gc_calls is not None and report.hook_calls is not None:
                detail = (f"   {report.gc_calls} collects "
                          f"in {report.hook_calls} calls")
            lines.append(
                f"      of which gc.collect{report.gc_seconds:8.1f} s{detail}"
            )
        remaining = report.remaining_unaccounted
        lines.append(
            f"    remaining unaccounted{remaining:9.1f} s   "
            f"in pytest, in neither of the above"
        )
        # A NEGATIVE RESIDUAL IS NOT A ROUNDING STORY. The hook would be
        # claiming more time than the session clock leaves outside the
        # tests, which cannot both be true -- so say so loudly rather than
        # printing a minus sign and letting it read as a small number.
        if remaining < -RECONCILE_TOLERANCE_SECONDS:
            lines.append(
                f"    ** CONTRADICTION: the hook claims {abs(remaining):.1f} s "
                f"more than the session clock leaves outside the tests. One "
                f"of the two clocks is wrong; do not quote either."
            )
    lines.append(f"    {'-' * 60}")
    lines.append(
        f"    <testsuite time>    {report.declared_time:10.1f} s   "
        f"pytest's own session clock"
    )
    if wall is not None:
        lines.append(
            f"    outside pytest      {wall - report.declared_time:10.1f} s   "
            f"process start/stop"
        )
        lines.append(f"    wall clock          {wall:10.1f} s   (given)")
    else:
        lines.append(
            "    wall clock                   -- pass --wall=SECONDS "
            "(pytest's own summary, or the CI job duration)"
        )
    return lines


def _bucket_table(report: Report) -> list[str]:
    """Does the hook get more expensive as the run goes on?

    **PRINTED EVEN WHEN THE TOTAL IS SMALL**, because flat buckets are a
    RESULT rather than an absence of one: they refute the growing-heap
    explanation whatever the total turned out to be. A table shown only
    when the total looked interesting could never report that, and the
    magnitude and the shape are separate questions on purpose.
    """
    if not report.buckets:
        return []
    data = report.buckets.get("buckets") or []
    if not data:
        return []
    lines = [
        f"  gc.collect() cost by decile of completed COLLECTS "
        f"({report.buckets.get('scheme', 'scheme NOT DECLARED')})",
    ]
    rows = []
    for index, entry in enumerate(data, start=1):
        calls, seconds = entry[0], entry[1]
        per_ms = (seconds / calls * 1000) if calls else 0.0
        rows.append((str(index), str(calls), f"{seconds:.2f}", f"{per_ms:.2f}"))
    lines.append(_table(
        rows, ("decile", "collects", "seconds", "ms/collect"), (6, 9, 9, 11),
    ))
    if report.retained_windows is not None:
        lines.append(
            f"  {report.retained_windows} MainWindows retained for the whole "
            f"session -- the heap grows on purpose, see tests/conftest.py"
        )
    first, last = data[0], data[-1]
    if first[0] and last[0] and first[1] > 0:
        a = first[1] / first[0] * 1000
        b = last[1] / last[0] * 1000
        lines.append(
            f"  first decile {a:.2f} ms/collect -> last decile {b:.2f} ms/collect "
            f"= {b / a:.2f}x"
        )
    return lines


def describe(report: Report, top: int, wall: float | None = None) -> str:
    out = [
        f"=== {report.label}  ({report.path.name}) ===",
        f"  tests            {len(report.cases)}",
        f"  by status        " + "  ".join(
            f"{k}={v}" for k, v in sorted(report.counts().items())
        ),
        "",
    ]
    out.extend(_accounting(report, wall))
    buckets = _bucket_table(report)
    if buckets:
        out.append("")
        out.extend(buckets)
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
