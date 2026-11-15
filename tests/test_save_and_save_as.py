"""Save writes to the project's own file; Save As always asks (`MainWindow._save_project` / `_save_project_as`)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container


@pytest.fixture
def window(qapp, tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _answer_dialog_with(monkeypatch, answer: str):
    """Replace the save dialog; the returned list records every time it was shown (and its start path)."""
    shown: list[str] = []

    def fake(parent=None, caption="", dir="", *a, **k):
        shown.append(dir)
        return (answer, "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    return shown


def test_first_save_asks_then_later_saves_do_not(window, tmp_path, monkeypatch):
    target = tmp_path / "first.ocsproj"
    shown = _answer_dialog_with(monkeypatch, str(target))

    assert window._save_project() is True
    assert len(shown) == 1 and target.is_file()

    target.unlink()
    assert window._save_project() is True
    assert len(shown) == 1, "a project that has a file was asked for one again"
    assert target.is_file(), "Save did not write to the project's own file"


def test_save_as_always_asks_and_the_next_save_goes_to_the_new_file(window, tmp_path, monkeypatch):
    first, second = tmp_path / "a.ocsproj", tmp_path / "b.ocsproj"
    shown = _answer_dialog_with(monkeypatch, str(first))
    window._save_project()
    shown = _answer_dialog_with(monkeypatch, str(second))

    assert window._save_project_as() is True
    assert len(shown) == 1 and Path(shown[0]) == first, "Save As did not offer the current file's name and folder"
    first.unlink()
    window._save_project()
    assert second.is_file() and not first.exists(), "Save kept writing to the old file after Save As"


def test_cancelled_save_as_changes_nothing(window, tmp_path, monkeypatch):
    _answer_dialog_with(monkeypatch, "")
    assert window._save_project_as() is False
    assert getattr(window, "_project_path", "") == ""


def test_a_new_project_does_not_inherit_the_last_file(window, tmp_path, monkeypatch):
    target = tmp_path / "old.ocsproj"
    shown = _answer_dialog_with(monkeypatch, str(target))
    window._save_project()
    window._new_project()
    window._save_project()
    assert len(shown) == 2, "Save on a new project wrote over the previous project's file"


def test_an_opened_project_saves_back_to_where_it_came_from(window, tmp_path, monkeypatch):
    target = tmp_path / "opened.ocsproj"
    _answer_dialog_with(monkeypatch, str(target))
    window._save_project()
    window._new_project()
    window.open_project_file(target)
    target.unlink()
    shown = _answer_dialog_with(monkeypatch, "")
    assert window._save_project() is True
    assert shown == [] and target.is_file()


def test_a_vanished_folder_falls_back_to_asking(window, tmp_path, monkeypatch):
    folder = tmp_path / "gone"
    folder.mkdir()
    _answer_dialog_with(monkeypatch, str(folder / "p.ocsproj"))
    window._save_project()
    (folder / "p.ocsproj").unlink()
    folder.rmdir()
    shown = _answer_dialog_with(monkeypatch, "")
    assert window._save_project() is False
    assert len(shown) == 1
