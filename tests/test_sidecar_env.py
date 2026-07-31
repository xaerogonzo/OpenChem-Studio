"""Interpreter-path validation for the out-of-process sidecars.

Every case here is one a user actually hit or could hit from the External
Tools dialog. The `.codecov.yml` case is verbatim: that path really was
stored, and the only symptom was "[WinError 193] %1 is not a valid Win32
application".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from openchem.services.sidecar_env import (
    interpreter_problem,
    recovery_hint,
    working_interpreter_in,
)


def test_a_real_interpreter_reports_no_problem():
    assert interpreter_problem(sys.executable) is None


def test_an_empty_path_is_reported_as_unconfigured():
    assert "No interpreter configured" in interpreter_problem("")
    assert "No interpreter configured" in interpreter_problem("   ")


def test_a_missing_path_says_so():
    assert "Nothing exists at" in interpreter_problem(str(Path("no") / "such" / "python.exe"))


def test_a_directory_points_at_what_to_pick_instead(tmp_path):
    problem = interpreter_problem(str(tmp_path))

    assert "is a folder" in problem
    assert ("Scripts" in problem) if os.name == "nt" else ("bin" in problem)


def test_the_real_codecov_yml_case_is_named_clearly(tmp_path):
    """The exact failure from the screenshot: a file from the cloned
    pkasolver repo stored as the interpreter."""
    yml = tmp_path / ".codecov.yml"
    yml.write_text("coverage: {}\n", encoding="utf-8")

    problem = interpreter_problem(str(yml))

    assert problem == ".codecov.yml is a text file, not a Python interpreter."


def test_a_binary_that_is_not_python_is_rejected(tmp_path):
    """Guards the case a name filter cannot: something that really does
    execute, but is not a Python."""
    if os.name != "nt":
        target = tmp_path / "notpython"
        target.write_text("#!/bin/sh\necho hello\n", encoding="utf-8")
        target.chmod(0o755)
        assert interpreter_problem(str(target)) is not None


def test_a_working_environment_is_found_and_offered(tmp_path):
    """The recovery path: the app installed the environment, so when the
    configured path is wrong it can say where the right one is."""
    # A REAL venv, not a copied python.exe: a bare copy has no DLLs or
    # stdlib beside it and will not run, so faking one would test the
    # wrong thing. pip is skipped to keep this quick.
    import venv

    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    interpreter = tmp_path / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )

    assert working_interpreter_in(tmp_path) == interpreter
    hint = recovery_hint(tmp_path)
    assert "A working interpreter was found at" in hint
    assert hint.isascii(), "must stay ASCII: this string reaches cp1252 consoles and logs"


def test_no_hint_when_there_is_nothing_to_suggest(tmp_path):
    """Empty rather than a sentence, so callers can concatenate it
    unconditionally."""
    assert recovery_hint(tmp_path) == ""
    assert working_interpreter_in(tmp_path) is None
