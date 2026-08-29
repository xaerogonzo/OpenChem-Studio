"""Guards for the census reader, and the narrow half is the whole point.

The tool answers "which test was the process in when it died". The tempting
implementation is `return the last BEGIN`, which satisfies every
crashed-trail test and **names a victim on every clean run too** -- so each
guard below has a partner asserting silence.

The trails here are CONSTRUCTED rather than copied from a real run. A real
one is 28,000 lines and its shape would be an accident of whichever run was
captured; these state the format the tool actually contracts with.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from read_census import read_census, read_path  # noqa: E402


def _trail(*lines: str) -> str:
    return "\n".join(lines) + "\n"


CLEAN = _trail(
    "BEGIN tests/test_a.py::test_one pid=42",
    "  end tests/test_a.py::test_one built=3 destroyed=3 late=0 alive=0",
    "BEGIN tests/test_b.py::test_two pid=42",
    "  end tests/test_b.py::test_two built=5 destroyed=5 late=0 alive=0",
    "# session finished exitstatus=0",
)

CRASHED = _trail(
    "BEGIN tests/test_a.py::test_one pid=42",
    "  end tests/test_a.py::test_one built=3 destroyed=3 late=0 alive=0",
    "BEGIN tests/test_nmr_view_dialog.py::test_dialog_shows_the_signal_list pid=42",
)


def test_a_crashed_trail_names_the_test_that_never_ended() -> None:
    """The whole reason this exists: the traceback names an arbitrary frame
    for a fatal signal, and the trail names the test."""
    census = read_census(CRASHED)
    assert census.usable
    assert not census.finished
    assert census.victim == "tests/test_nmr_view_dialog.py::test_dialog_shows_the_signal_list"
    assert "died in" in census.describe()


def test_a_clean_trail_names_NO_victim() -> None:
    """**THE NARROW HALF.** `return the last BEGIN` passes the test above and
    would report a victim on every green run, which is worse than reporting
    nothing: it would make the annotation cry wolf until somebody deleted it.
    """
    census = read_census(CLEAN)
    assert census.usable
    assert census.finished
    assert census.victim is None
    assert "died in" not in census.describe()


def test_the_sentinel_is_matched_as_a_prefix_not_in_full() -> None:
    """The line carries the exit status, and a future field would break an
    equality test silently -- reporting every clean run as a crash."""
    assert read_census(CLEAN).finished
    assert read_census(CLEAN.replace("exitstatus=0", "exitstatus=1 extra=x")).finished


def test_an_empty_trail_reports_NO_TRAIL_rather_than_a_victim() -> None:
    """**FAIL CLOSED.** "I could not find out" is not "it did not crash", and
    a tool that answered the second would turn an instrumentation failure
    into a clean bill of health."""
    census = read_census("")
    assert not census.usable
    assert census.victim is None
    assert census.describe().startswith("NO TRAIL")


def test_a_file_that_is_not_a_census_reports_NO_TRAIL() -> None:
    """Output exists and carries no BEGIN lines -- a redirected log, say.
    Distinct from empty, and equally not a verdict about crashing."""
    census = read_census("some other tool's output\nwith no census in it\n")
    assert not census.usable
    assert "not a census trail" in census.detail


def test_a_missing_file_reports_NO_TRAIL_rather_than_raising(tmp_path: Path) -> None:
    """A diagnostic that raises inside a workflow step is a diagnostic that
    fails the job it was added to observe."""
    census = read_path(tmp_path / "absent.txt")
    assert not census.usable
    assert census.describe().startswith("NO TRAIL")


def test_unusable_and_clean_are_distinguishable_though_both_lack_a_victim() -> None:
    """`victim is None` means two opposite things, and only `usable`
    separates them. A caller reading the victim alone cannot tell an
    unreadable trail from a green run."""
    clean = read_census(CLEAN)
    unusable = read_census("")
    assert clean.victim is unusable.victim is None
    assert clean.usable and not unusable.usable


def test_late_destructions_are_split_at_the_sentinel() -> None:
    """A LATE line AFTER the sentinel is process teardown, not a cross-test
    landmine. Counting them together reports thousands that are not there --
    measured on a real run, 0 during and 16022 at teardown."""
    trail = _trail(
        "BEGIN tests/test_a.py::test_one pid=42",
        "LATE QLabel built=tests/test_z.py::test_old died=tests/test_a.py::test_one",
        "  end tests/test_a.py::test_one built=3 destroyed=3 late=1 alive=0",
        "# session finished exitstatus=0",
        "LATE QWidget built=tests/test_a.py::test_one died=<session teardown>",
        "LATE QDialog built=tests/test_a.py::test_one died=<session teardown>",
    )
    census = read_census(trail)
    assert (census.late_during_run, census.late_after_sentinel) == (1, 2)


def test_a_session_that_finished_with_an_unclosed_test_is_its_own_state() -> None:
    """Neither "clean" nor "died mid-run". Reporting it as either would be a
    guess; it is rare enough that saying so is the honest answer."""
    trail = CLEAN.replace(
        "  end tests/test_b.py::test_two built=5 destroyed=5 late=0 alive=0\n", ""
    )
    census = read_census(trail)
    assert census.finished
    assert census.victim == "tests/test_b.py::test_two"
    assert "never ended" in census.describe()


def test_the_count_is_of_tests_begun_not_lines() -> None:
    """`tests_begun` is what makes "died at 57%" checkable against a
    collected count; counting lines would include every LATE line."""
    assert read_census(CLEAN).tests_begun == 2
    assert read_census(CRASHED).tests_begun == 2


def test_an_end_for_a_different_test_does_not_clear_the_victim() -> None:
    """The pairing is by nodeid. Clearing on ANY end line would let a
    mismatched trail report clean, which is the fail-open direction."""
    trail = _trail(
        "BEGIN tests/test_a.py::test_one pid=42",
        "  end tests/test_OTHER.py::test_other built=1 destroyed=1 late=0 alive=0",
    )
    assert read_census(trail).victim == "tests/test_a.py::test_one"
