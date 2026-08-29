"""Read a widget-lifetime census trail and say which test the process died in.

`tests/conftest.py` writes `census.txt` when `OPENCHEM_CENSUS` is set: one
`BEGIN` line before each test, one `  end` line after it, `LATE` lines for a
widget destroyed outside the test that built it, and a
`# session finished` sentinel written from `pytest_sessionfinish`.

## WHY THIS EXISTS: THE TRACEBACK NAMES THE WRONG TEST

The Linux job's fingerprint step derived its victim by grepping the pytest
log for the deepest `tests/*.py", line N in ...` frame. **For a fatal signal
that frame is wherever the process happened to be**, not the test that died --
`abort()` unwinds through pluggy, and the test function may not appear at all.
Measured on master `becc743`, the annotation said:

    Reached [57%] then died at an unidentified frame.

...while `census.txt`, in the same artifact, named it exactly:

    tests/test_nmr_view_dialog.py::test_dialog_shows_the_signal_list

That is a fourth observation in the same file, three of them on that file's
first test. **It localises the victim; it does not establish the cause** --
the location is pinned and the trigger is not. What this tool changes is that
the observation is now free on every run instead of costing an artifact
download, an unzip and two greps.

## THE SENTINEL IS THE ORACLE FOR "DID IT FINISH", NOT THE COUNTS

Reporting totals from a session-finish hook cannot work, because the process
dies before it -- so the run that reports is by construction a run that did
not crash. The sentinel has the opposite property: if the process aborts the
line is simply ABSENT, and its absence is the answer.

**A `LATE` line after the sentinel is process teardown, not a cross-test
landmine**, which is why they are counted separately here. Reading all of them
as landmines reports thousands that are not there.

## FAIL CLOSED

A missing, empty or unparseable trail reports `NO TRAIL`, never a victim and
never silence. "I could not find out" is not "it did not crash" -- the same
rule the `webgl` fixture follows, and the reason a blanket `except` in a probe
is worse than no probe at all.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

#: The sentinel `pytest_sessionfinish` writes. Its ABSENCE is the signal.
#:
#: Matched as a prefix rather than in full, because the line carries the
#: session's exit status after it and a future field would break an
#: equality test silently.
SENTINEL = "# session finished"

#: What a test's opening line starts with. One per test, written BEFORE it
#: runs, so it survives the `abort()` this whole instrument exists to catch.
BEGIN = "BEGIN "

#: What a test's closing line starts with -- indented, so it cannot be
#: confused with `BEGIN` by a prefix match.
END = "  end "

#: A widget destroyed outside the test that built it.
LATE = "LATE "


@dataclass(frozen=True)
class Census:
    """What a trail says, with "could not tell" kept distinct from "no".

    `victim` is the last test that BEGAN and never ENDED. It is None on a
    run that finished cleanly, and None on a trail that could not be read --
    `usable` is what separates those two, and a caller that ignores it turns
    an unreadable trail into a clean bill of health.
    """

    usable: bool
    finished: bool
    victim: str | None
    tests_begun: int
    late_during_run: int
    late_after_sentinel: int
    detail: str

    def describe(self) -> str:
        if not self.usable:
            return f"NO TRAIL -- {self.detail}"
        if self.finished and self.victim is None:
            return (
                f"the session finished; {self.tests_begun} tests ran, "
                f"{self.late_during_run} late destruction(s) during the run "
                f"({self.late_after_sentinel} at teardown)"
            )
        if self.finished:
            return (
                f"the session finished but {self.victim} never ended -- "
                f"{self.tests_begun} tests began"
            )
        return (
            f"died in {self.victim or 'a test the trail does not name'} "
            f"after {self.tests_begun} test(s); "
            f"{self.late_during_run} late destruction(s) during the run"
        )


def read_census(text: str) -> Census:
    """Parse a trail. Never raises on content; only reports.

    The victim is tracked as "begun and not yet ended" rather than "the last
    BEGIN", because those differ on a trail whose final test completed: the
    last BEGIN always exists, and reporting it unconditionally would name a
    victim on every clean run.
    """
    if not text.strip():
        return Census(
            usable=False,
            finished=False,
            victim=None,
            tests_begun=0,
            late_during_run=0,
            late_after_sentinel=0,
            detail="the census file is empty",
        )

    pending: str | None = None
    begun = 0
    finished = False
    late_before = 0
    late_after = 0

    for line in text.splitlines():
        if line.startswith(BEGIN):
            pending = line[len(BEGIN) :].split(" pid=")[0].strip()
            begun += 1
        elif line.startswith(END):
            nodeid = line[len(END) :].split(" built=")[0].strip()
            if pending == nodeid:
                pending = None
        elif line.startswith(LATE):
            if finished:
                late_after += 1
            else:
                late_before += 1
        elif line.startswith(SENTINEL):
            finished = True

    if begun == 0:
        return Census(
            usable=False,
            finished=finished,
            victim=None,
            tests_begun=0,
            late_during_run=late_before,
            late_after_sentinel=late_after,
            detail="no BEGIN lines: this is not a census trail",
        )

    return Census(
        usable=True,
        finished=finished,
        victim=pending,
        tests_begun=begun,
        late_during_run=late_before,
        late_after_sentinel=late_after,
        detail="",
    )


def read_path(path: Path) -> Census:
    """Read a trail from disk, reporting rather than raising if it cannot."""
    try:
        return read_census(path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        return Census(
            usable=False,
            finished=False,
            victim=None,
            tests_begun=0,
            late_during_run=0,
            late_after_sentinel=0,
            detail=f"could not read {path}: {exc}",
        )


def main(argv: list[str]) -> int:
    """Print one line for the workflow to embed in its annotation.

    **ALWAYS EXITS 0.** This is a diagnostic, and a diagnostic that can fail
    a job would eventually be deleted for crying wolf -- the Linux job is
    advisory by design and this must not change that.
    """
    if len(argv) != 2:
        print("usage: read_census.py <census.txt>")
        return 0
    print(read_path(Path(argv[1])).describe())
    return 0


if __name__ == "__main__":  # pragma: no cover - the CLI entry point
    raise SystemExit(main(sys.argv))
