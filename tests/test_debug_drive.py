"""`OPENCHEM_DRIVE` must be inert unless asked for, and unkillable when it is.

The driver exists so a measurement can happen inside the REAL window
without driving the machine's mouse and keyboard. It ships in the
application, so the two things that matter are that it does nothing at all
by default, and that a bad script degrades to a log line rather than
taking the app down with it.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QWidget

import openchem.app.debug_drive as debug_drive

import conftest


@pytest.fixture
def window(qapp):
    """A REAL QObject, because the driver schedules its next step against
    the window as Qt's CONTEXT OBJECT and `object()` is not something Qt
    can bind to.

    These two tests passed a bare `object()`, which worked only while the
    scheduling was `QTimer.singleShot(after, self._run_next)` -- a form
    that is tied to nothing and so goes on running steps against a window
    that has been destroyed. Production has always passed a real
    MainWindow here, so the stand-in was a test convenience rather than a
    supported shape.

    Disposed per the per-file recipe in CLAUDE.md, which also cancels any
    step still scheduled when the test ends -- which is the whole point of
    binding to the window, demonstrated rather than asserted.
    """
    built = QWidget()
    yield built
    conftest.dispose(built)


def test_it_does_nothing_unless_the_variable_is_set(monkeypatch):
    """Off by default, at the cost of one `os.environ` read at import."""
    monkeypatch.setattr(debug_drive, "_DRIVE_SCRIPT", None)
    assert debug_drive.start_if_requested(object()) is None


def test_a_missing_script_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(debug_drive, "_DRIVE_SCRIPT", str(tmp_path / "nope.json"))
    assert debug_drive.start_if_requested(object()) is None


def test_a_malformed_script_is_reported_not_raised(monkeypatch, tmp_path):
    script = tmp_path / "bad.json"
    script.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(debug_drive, "_DRIVE_SCRIPT", str(script))
    assert debug_drive.start_if_requested(object()) is None


def test_a_script_that_is_not_a_list_is_refused(monkeypatch, tmp_path):
    """A dict parses fine and would then be iterated as its keys, which
    fails much later and much less clearly."""
    script = tmp_path / "dict.json"
    script.write_text(json.dumps({"do": "quit"}), encoding="utf-8")
    monkeypatch.setattr(debug_drive, "_DRIVE_SCRIPT", str(script))
    assert debug_drive.start_if_requested(object()) is None


def test_an_unknown_step_does_not_stop_the_script(window, caplog):
    """A typo in one step must not strand the remaining ones -- a script
    that silently stops half way looks exactly like the app hanging, which
    is the failure mode this whole tool exists to avoid.
    """
    driver = debug_drive._Driver(window, [{"do": "nonsense"}, {"do": "wait"}])
    driver._run_next()
    assert driver._index == 1
    assert "unknown step" in caplog.text
    driver._run_next()
    assert driver._index == 2


def test_a_step_that_raises_does_not_stop_the_script(window, caplog):
    """`import` against a window with no project raises inside the step;
    the driver must log it and carry on to the next one."""
    driver = debug_drive._Driver(window, [{"do": "expand", "section": "admet"}, {"do": "wait"}])
    driver._run_next()
    assert driver._index == 1
    assert "failed" in caplog.text
    driver._run_next()
    assert driver._index == 2


def test_destroying_the_window_stops_the_script(qapp, monkeypatch):
    """The point of binding each step to the window as Qt's context object.

    A bare `QTimer.singleShot(after, self._run_next)` is tied to nothing,
    so closing the window mid-script left the remaining steps queued and
    running against a window that no longer exists -- every one of them a
    C++ call through `self._window`.

    **The surviving-window arm is the control and is load-bearing**: a
    script that never advanced at all reads exactly like one correctly
    cancelled, so without it this passes against a harness that does
    nothing.

    The driver is deliberately NOT a Qt child of the window (see
    `_Driver`), which is what lets this read `_index` after the window is
    gone -- a wrapper destroyed as a child would raise instead.
    """
    monkeypatch.setattr(debug_drive, "_DEFAULT_AFTER_MS", 0)
    steps = [{"do": "wait"}, {"do": "wait"}, {"do": "wait"}]

    def run_a_script(*, destroy: bool) -> int:
        built = QWidget()
        driver = debug_drive._Driver(built, list(steps))
        driver.start()
        if destroy:
            conftest.dispose(built)
        for _ in range(10):
            QCoreApplication.processEvents()
        if not destroy:
            conftest.dispose(built)
        return driver._index

    advanced = run_a_script(destroy=False)
    assert advanced > 0, "the control never advanced, so the arm below proves nothing"

    assert run_a_script(destroy=True) == 0, "a step ran against a destroyed window"
