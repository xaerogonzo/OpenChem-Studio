"""The suite-timing reader, and the two ways it lied before it was broken.

`tools/suite_timings.py` reads pytest's JUnit XML to say where the suite's
time goes. It is a measuring instrument, so the thing it must never do is
produce a confident total from data that does not support one -- a run
killed by the CI timeout is exactly when somebody reaches for it.

**THE MAPPING BELOW WAS MEASURED, NOT ASSUMED.** JUnit does not encode
what pytest's terminal summary says: a file of deliberate outcomes came
back with `1 failed, 1 passed, 1 skipped, 1 xfailed, 1 xpassed, 1 error`
on the terminal and `errors="1" failures="1" skipped="2"` in the XML.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _module():
    """The tool itself, loaded by path -- `tools/` is not a package.

    **REGISTERED IN `sys.modules` BEFORE IT IS EXECUTED, and that is not
    tidiness.** `@dataclass` resolves its annotations through
    `sys.modules[cls.__module__]`, so a module executed without being
    registered raises `AttributeError` out of `dataclasses._process_class`
    the moment it defines one -- which is a stack trace about CPython
    internals rather than about this file. All nine tests here failed that
    way first.
    """
    if "_suite_timings" in sys.modules:
        return sys.modules["_suite_timings"]
    spec = importlib.util.spec_from_file_location(
        "_suite_timings", REPO / "tools" / "suite_timings.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_suite_timings"] = module
    spec.loader.exec_module(module)
    return module


def _xml(cases: str, tests: int, time: str = "1.0") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites name="pytest tests">'
        f'<testsuite name="pytest" errors="0" failures="0" skipped="0" '
        f'tests="{tests}" time="{time}">{cases}</testsuite></testsuites>'
    )


def _case(classname: str, name: str, seconds: str = "1.0", child: str = "") -> str:
    inner = f">{child}</testcase>" if child else " />"
    return f'<testcase classname="{classname}" name="{name}" time="{seconds}"{inner}'


def test_a_truncated_report_is_refused_rather_than_totalled(tmp_path):
    """**THE FAILURE THIS TOOL EXISTS AROUND.** `--junitxml` is written at
    session finish, so a segfault or the 45-minute CI kill leaves a partial
    file -- and a partial file totalled without complaint would understate
    exactly the long tail being looked for, in the direction that reads as
    good news."""
    timings = _module()
    whole = _xml(_case("tests.test_layering", "test_one"), tests=1)
    cut = tmp_path / "cut.xml"
    cut.write_text(whole[: len(whole) // 2], encoding="utf-8")

    with pytest.raises(timings.TimingError, match="not well-formed"):
        timings.load("cut", cut)


def test_a_report_that_lost_rows_is_refused(tmp_path):
    """Well-formed, and still not trustworthy: the header claims more tests
    than the body carries. Caught by comparing the two rather than by
    trusting either."""
    timings = _module()
    path = tmp_path / "short.xml"
    path.write_text(_xml(_case("tests.test_layering", "test_one"), tests=44), encoding="utf-8")

    with pytest.raises(timings.TimingError, match="declares 44 tests but 1"):
        timings.load("short", path)


def test_an_empty_classname_does_not_crash_the_parser(tmp_path):
    """`"".split(".")` is `[""]`, not `[]`, so the file-name loop ran once
    with `Path("")` -- which is `.` -- and `with_suffix` raised. The
    `or "<unknown>"` guard looked like it covered this and sat after the
    loop, unreachable. Found by feeding the parser deliberate outcomes."""
    timings = _module()
    path = tmp_path / "anon.xml"
    path.write_text(_xml(_case("", "test_nameless"), tests=1), encoding="utf-8")

    report = timings.load("anon", path)

    assert report.cases[0].file == "<unknown>"


def test_an_xfail_is_not_counted_as_a_plain_skip(tmp_path):
    """MEASURED: pytest writes an xfail as `<skipped type="pytest.xfail">`,
    so a reader looking only at the tag reports it as a skip and the
    `skipped=` total silently covers two different outcomes."""
    timings = _module()
    cases = (
        _case("tests.test_layering", "s", child='<skipped type="pytest.skip" />')
        + _case("tests.test_layering", "x", child='<skipped type="pytest.xfail" />')
    )
    path = tmp_path / "x.xml"
    path.write_text(_xml(cases, tests=2), encoding="utf-8")

    assert timings.load("x", path).counts() == {"skipped": 1, "xfailed": 1}


def test_a_failure_and_an_error_are_kept_apart(tmp_path):
    """A test that failed and a fixture that blew up are different
    problems, and JUnit does distinguish them."""
    timings = _module()
    cases = (
        _case("tests.test_layering", "f", child="<failure />")
        + _case("tests.test_layering", "e", child="<error />")
    )
    path = tmp_path / "fe.xml"
    path.write_text(_xml(cases, tests=2), encoding="utf-8")

    assert timings.load("fe", path).counts() == {"failed": 1, "error": 1}


def test_a_class_based_test_is_attributed_to_its_FILE(tmp_path):
    """JUnit carries no `file` attribute, only the dotted `classname`, and
    a class-based test appends the class to it. Attributing that to a
    file that does not exist would move seconds between rows of the very
    table being read."""
    timings = _module()
    path = tmp_path / "c.xml"
    path.write_text(
        _xml(_case("tests.test_layering.TestSomething", "test_one"), tests=1),
        encoding="utf-8",
    )

    assert timings.load("c", path).cases[0].file == "tests/test_layering.py"


def test_the_per_file_totals_account_for_every_second(tmp_path):
    timings = _module()
    cases = (
        _case("tests.test_layering", "a", seconds="1.5")
        + _case("tests.test_layering", "b", seconds="2.0")
        + _case("tests.test_docs_are_current", "c", seconds="0.5")
    )
    path = tmp_path / "t.xml"
    path.write_text(_xml(cases, tests=3), encoding="utf-8")

    report = timings.load("t", path)

    assert report.by_file() == {
        "tests/test_layering.py": 3.5,
        "tests/test_docs_are_current.py": 0.5,
    }
    assert report.summed == pytest.approx(4.0)


def test_the_ratio_view_ignores_files_too_small_to_matter(tmp_path):
    """**A RATIO ALONE MISLEADS IN BOTH DIRECTIONS.** A file at 0.20 s
    against 0.05 s is a 4x ratio contributing nothing to a twenty-minute
    gap; one at 180 s against 120 s is 1.5x and contributes a minute.
    Sorting by ratio with no floor puts the first at the top and buries
    the second, which is the reading error this whole comparison exists to
    avoid."""
    timings = _module()

    def write(name, big, small):
        path = tmp_path / name
        path.write_text(
            _xml(
                _case("tests.test_layering", "big", seconds=str(big))
                + _case("tests.test_docs_are_current", "small", seconds=str(small)),
                tests=2,
            ),
            encoding="utf-8",
        )
        return timings.load(name, path)

    windows = write("w.xml", 180.0, 0.20)
    linux = write("l.xml", 120.0, 0.05)

    text = timings.compare(windows, linux, top=5, min_seconds=5.0)
    ratio_section = text.split("largest ratio")[1].split("largest")[0]

    assert "test_layering" in ratio_section
    assert "test_docs_are_current" not in ratio_section, (
        "a 4x ratio on a 0.2 s file outranked a 60 s difference"
    )


def test_the_absolute_delta_view_finds_the_real_gap(tmp_path):
    """The complement: the file with the SMALLER ratio is the one holding
    the seconds, and the delta view has to put it first."""
    timings = _module()

    def write(name, big, small):
        path = tmp_path / name
        path.write_text(
            _xml(
                _case("tests.test_layering", "big", seconds=str(big))
                + _case("tests.test_docs_are_current", "small", seconds=str(small)),
                tests=2,
            ),
            encoding="utf-8",
        )
        return timings.load(name, path)

    windows = write("w.xml", 180.0, 0.20)
    linux = write("l.xml", 120.0, 0.05)

    delta_section = timings.compare(windows, linux, top=5, min_seconds=5.0)
    first_table = delta_section.split("largest absolute delta")[1]
    rows = [r for r in first_table.splitlines() if "tests/" in r]

    assert "test_layering" in rows[0], "the 60 s difference was not first"
