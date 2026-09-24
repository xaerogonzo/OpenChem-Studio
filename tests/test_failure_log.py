"""A repeating failure is printed once per window -- and said to have repeated.

Five identical tracebacks in forty seconds filled the Console during a live
session on a nitramine, one per edit, each with a different message
("atoms [1, 3]", then "[5, 6]"). The cause is fixed; this is the class: a
failure that repeats every edit must not bury the log, and must never be hidden
without saying so.
"""

from __future__ import annotations

import logging
import logging.handlers
from dataclasses import dataclass

import pytest

from openchem import failure_log
from openchem.failure_log import CollapseRepeatedFailures, collapse_filter, describe, failure_key


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def lines(self) -> list[str]:
        return [r.getMessage() for r in self.records]


@dataclass
class _Rig:
    clock: _Clock
    logger: logging.Logger
    console: _Collect
    file: _Collect
    announced: _Collect


@pytest.fixture
def rig():
    """A private logger with two handlers sharing ONE filter, as the app's do.

    The filter's announcements go through the real `openchem.logging` logger,
    so the rig listens there as well and puts its level back afterwards.
    """
    clock = _Clock()
    shared = CollapseRepeatedFailures(window_seconds=30.0, clock=clock)
    logger = logging.Logger("openchem.test_failure_log")
    logger.setLevel(logging.DEBUG)
    console, file = _Collect(), _Collect()
    for handler in (console, file):
        handler.addFilter(shared)
        logger.addHandler(handler)
    announced = _Collect()
    notice = logging.getLogger("openchem.logging")
    previous_level = notice.level
    notice.addHandler(announced)
    notice.setLevel(logging.DEBUG)
    yield _Rig(clock, logger, console, file, announced)
    notice.removeHandler(announced)
    notice.setLevel(previous_level)


def _raise(atoms: str):
    raise ValueError(f"UndeclaredChargeState at atoms {atoms}")


def _fail(logger: logging.Logger, atoms: str) -> None:
    try:
        _raise(atoms)
    except ValueError:
        logger.exception("Alert computation failed for provider rdkit")


# --- what "the same failure" means -------------------------------------------


def test_the_same_failure_with_a_different_message_is_one_failure():
    """The key is where it happened, not what it said."""
    logger = logging.Logger("x")
    handler = _Collect()
    logger.addHandler(handler)
    _fail(logger, "[1, 3]")
    _fail(logger, "[5, 6]")
    first, second = handler.records
    assert failure_key(first) == failure_key(second)
    assert describe(first).exception == "ValueError"
    assert describe(first).origin == describe(second).origin
    assert describe(first).origin.startswith("test_failure_log.py:")


def test_a_different_place_is_a_different_failure():
    """Two failures that share a first line raise from different places."""
    logger = logging.Logger("x")
    handler = _Collect()
    logger.addHandler(handler)
    _fail(logger, "[1, 3]")
    try:
        raise ValueError("UndeclaredChargeState at atoms [1, 3]")  # a different line
    except ValueError:
        logger.exception("Alert computation failed for provider rdkit")
    first, second = handler.records
    assert failure_key(first) != failure_key(second)


# --- collapsing --------------------------------------------------------------


def test_a_burst_prints_one_traceback_and_says_the_rest_were_collapsed(rig):
    for step, atoms in enumerate(("[1, 3]", "[5, 6]", "[2, 4]", "[7, 8]")):
        rig.clock.now = step * 8.0  # 0, 8, 16, 24: all inside one 30 s window
        _fail(rig.logger, atoms)
    assert len(rig.console.records) == 1 and len(rig.file.records) == 1, "one traceback, in EVERY handler"
    (announcement,) = rig.announced.lines()
    assert "further identical tracebacks are collapsed for 30 s" in announcement
    assert "Alert computation failed for provider rdkit" in announcement

    rig.clock.now = 32.0  # the next window
    _fail(rig.logger, "[9, 9]")
    assert len(rig.console.records) == 2 and len(rig.file.records) == 2
    counted = [line for line in rig.announced.lines() if "collapsed in the previous" in line]
    assert len(counted) == 1 and counted[0].startswith("3 identical failure(s) were collapsed in the previous 30 s")


def test_every_handler_reaches_the_same_decision_about_one_record(rig):
    """A `LogRecord` is one object handed to each handler in turn. Per-handler
    filters would count it once each, so the console would collapse while the
    file did not -- and each would announce it."""
    for step in range(3):
        rig.clock.now = float(step)
        _fail(rig.logger, f"[{step}, {step}]")
    assert len(rig.console.records) == len(rig.file.records) == 1
    assert len(rig.announced.records) == 1, "announced once, not once per handler"


def test_only_a_traceback_at_error_or_above_is_ever_collapsed(rig):
    for _ in range(5):
        rig.logger.error("no traceback here")
        rig.logger.warning("nor here")
    assert len(rig.console.records) == 10, "a one-line failure needs no collapsing"
    assert not rig.announced.records


def test_a_repeat_after_the_window_is_reported_not_swallowed(rig):
    """A failure still happening minutes later shows itself again."""
    _fail(rig.logger, "[1, 1]")
    rig.clock.now = 31.0
    _fail(rig.logger, "[1, 1]")
    assert len(rig.console.records) == 2
    assert not rig.announced.records, "nothing was collapsed, so nothing is announced"


def test_the_filter_never_rewrites_a_record_a_handler_will_read_next(rig):
    """Records are shared between handlers; rewriting one for the sake of one
    would rewrite it for all."""
    _fail(rig.logger, "[1, 1]")
    (kept,) = rig.console.records
    assert kept.exc_info is not None
    assert kept.getMessage() == "Alert computation failed for provider rdkit"


# --- wiring -------------------------------------------------------------------


def test_the_app_uses_one_shared_instance():
    assert collapse_filter() is collapse_filter()
    assert isinstance(collapse_filter(), failure_log.CollapseRepeatedFailures)


def test_the_apps_handlers_carry_it(tmp_path, monkeypatch):
    """`configure_logging` puts the shared filter on the stream and file handlers."""
    from openchem.app import logging_setup

    monkeypatch.setenv("OPENCHEM_DATA_ROOT", str(tmp_path))
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        logging_setup.configure_logging()
        carriers = [h for h in root.handlers if collapse_filter() in h.filters]
        assert carriers, "no handler carries the collapse filter"
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in carriers)
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in before:
            root.addHandler(handler)


def test_the_console_panel_handler_carries_it(qapp):
    from openchem.ui.panels.console_panel import ConsolePanel

    root = logging.getLogger()
    before = list(root.handlers)
    panel = ConsolePanel()
    try:
        added = [h for h in root.handlers if h not in before]
        assert added and all(collapse_filter() in h.filters for h in added)
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
        panel.deleteLater()
