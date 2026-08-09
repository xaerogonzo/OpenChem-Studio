"""`OPENCHEM_DRIVE` must be inert unless asked for, and unkillable when it is.

The driver exists so a measurement can happen inside the REAL window
without driving the machine's mouse and keyboard. It ships in the
application, so the two things that matter are that it does nothing at all
by default, and that a bad script degrades to a log line rather than
taking the app down with it.
"""

from __future__ import annotations

import json

import openchem.app.debug_drive as debug_drive


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


def test_an_unknown_step_does_not_stop_the_script(qapp, caplog):
    """A typo in one step must not strand the remaining ones -- a script
    that silently stops half way looks exactly like the app hanging, which
    is the failure mode this whole tool exists to avoid.
    """
    driver = debug_drive._Driver(object(), [{"do": "nonsense"}, {"do": "wait"}])
    driver._run_next()
    assert driver._index == 1
    assert "unknown step" in caplog.text
    driver._run_next()
    assert driver._index == 2


def test_a_step_that_raises_does_not_stop_the_script(qapp, caplog):
    """`import` against a window with no project raises inside the step;
    the driver must log it and carry on to the next one."""
    driver = debug_drive._Driver(object(), [{"do": "expand", "section": "admet"}, {"do": "wait"}])
    driver._run_next()
    assert driver._index == 1
    assert "failed" in caplog.text
    driver._run_next()
    assert driver._index == 2
