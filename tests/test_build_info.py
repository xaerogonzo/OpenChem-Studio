"""The About dialog is diagnostics, so its failure mode matters more than
its happy path: it is opened by someone whose install is already broken.
Every test here is about it staying useful when something is missing.
"""

from __future__ import annotations

import subprocess

import pytest

from openchem import build_info
from openchem.build_info import BuildInfo, collect
from openchem.ui.dialogs.about_dialog import AboutDialog


def test_collect_works_with_no_settings() -> None:
    """Callable without standing up the container -- a script or a test
    should be able to ask for this."""
    info = collect(None)
    assert isinstance(info, BuildInfo)
    assert info.version
    assert info.python
    assert info.tools  # reports "unknown (no settings)", not an empty dict


def test_library_versions_are_reported() -> None:
    info = collect(None)
    # PySide6 and RDKit are hard requirements, so a real version is expected
    # rather than the "not available" placeholder.
    assert info.libraries["PySide6"] != "not available"
    assert info.libraries["RDKit"] != "not available"


def test_missing_optional_library_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reason every import in _libraries is guarded. A diagnostics
    dialog that dies on a missing optional dependency fails exactly when
    someone is trying to report that dependency being missing.
    """
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def refuse_openbabel(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("openbabel"):
            raise ImportError("simulated missing Open Babel")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("builtins.__import__", refuse_openbabel)
    info = collect(None)
    assert "not installed" in info.libraries["Open Babel"]


def test_commit_falls_back_to_git_in_a_checkout() -> None:
    """No stamp exists in a source tree, so the commit has to come from git."""
    commit, source = build_info._commit()
    assert commit != ""
    assert source == "from the working checkout"


def test_commit_reports_unknown_rather_than_blank_when_git_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank field reads as 'no commit'; 'unknown' reads as 'not
    recorded'. The distinction matters in a bug report."""

    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("no git here")

    monkeypatch.setattr(subprocess, "run", explode)
    commit, source = build_info._commit()
    assert commit == "unknown"
    assert source == "git unavailable"


def test_stamped_commit_wins_over_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """What makes a frozen build identifiable. If this regresses, About
    silently starts reporting the developer's checkout instead."""
    monkeypatch.setattr(build_info, "_stamped", lambda name, default: "cafe123" if name == "commit" else default)
    commit, source = build_info._commit()
    assert commit == "cafe123"
    assert source == "baked at build time"


def test_configured_tool_path_that_no_longer_exists_is_flagged() -> None:
    """The failure this dialog exists to surface: a configured path reads
    identically to a working one until something actually looks at it.
    A real instance of this cost debugging time -- Vina was configured to a
    binary that had been moved.
    """

    class StaleSettings:
        def get(self, key: str, default: str = "") -> str:
            return r"C:\definitely\not\here\vina.exe"

    info = collect(StaleSettings())
    assert "[MISSING]" in info.tools["Vina"]


def test_as_text_contains_what_a_bug_report_needs() -> None:
    text = collect(None).as_text()
    for expected in ("OpenChem Studio", "Commit:", "Python:", "Libraries:", "External tools:"):
        assert expected in text


def test_about_dialog_copies_the_report_to_the_clipboard(qapp) -> None:
    from PySide6.QtWidgets import QApplication

    dialog = AboutDialog(None)
    dialog._copy()

    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == dialog.info.as_text()
    assert dialog._copy_button.text() == "Copied"
