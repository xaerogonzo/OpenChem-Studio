"""The catalogue browser, and the import path behind it.

The import test drives a real MainWindow with only the network stubbed,
because the thing worth proving is that a picked entry ends up as a real
`MacromoleculeModel` on the project with its `ligand_code` intact -- that
last part is what the docking box depends on, and it is easy to drop
silently.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.receptor_library import RECEPTOR_LIBRARY, find
from openchem.ui.dialogs.receptor_library_dialog import ReceptorLibraryDialog


_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


@pytest.fixture
def window(qapp, tmp_path):
    """A real MainWindow, following `test_main_window_docking_visualization`.
    Plugin directories are pointed at empty paths so a developer's own
    installed plugins cannot change what this test sees."""
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    return _track(MainWindow(services, settings, session))


def _entry_items(dialog: ReceptorLibraryDialog) -> list:
    """Every leaf (receptor) item, skipping the family headers."""
    items = []
    tree = dialog._tree
    for i in range(tree.topLevelItemCount()):
        parent = tree.topLevelItem(i)
        items.extend(parent.child(j) for j in range(parent.childCount()))
    return items


def test_the_dialog_lists_every_catalogued_receptor(qapp):
    dialog = ReceptorLibraryDialog()

    assert len(_entry_items(dialog)) == len(RECEPTOR_LIBRARY)


def test_families_are_shown_as_groups(qapp):
    dialog = ReceptorLibraryDialog()

    headers = [
        dialog._tree.topLevelItem(i).text(0)
        for i in range(dialog._tree.topLevelItemCount())
    ]

    assert any(h.startswith("Opioid") for h in headers)
    assert any(h.startswith("Ion channel") for h in headers)


def test_a_family_header_cannot_be_imported(qapp):
    """Selecting "Opioid (7)" is not choosing a receptor, and Import must
    stay disabled rather than acting on whatever was selected before."""
    dialog = ReceptorLibraryDialog()
    header = dialog._tree.topLevelItem(0)

    assert not (header.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_searching_filters_the_tree_and_drops_empty_families(qapp):
    dialog = ReceptorLibraryDialog()

    dialog._search.setText("fentanyl")

    items = _entry_items(dialog)
    assert len(items) == 1
    assert "8EF5" in items[0].text(1)
    headers = [
        dialog._tree.topLevelItem(i).text(0)
        for i in range(dialog._tree.topLevelItemCount())
    ]
    assert headers == ["Opioid (1)"], "families with no match are not shown at all"


def test_clearing_the_search_restores_everything(qapp):
    dialog = ReceptorLibraryDialog()
    dialog._search.setText("fentanyl")
    dialog._search.setText("")

    assert len(_entry_items(dialog)) == len(RECEPTOR_LIBRARY)


def test_import_is_disabled_until_a_receptor_is_picked(qapp):
    dialog = ReceptorLibraryDialog()
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)

    assert not ok.isEnabled()
    assert dialog.selected_entry() is None

    dialog._tree.setCurrentItem(_entry_items(dialog)[0])

    assert ok.isEnabled()
    assert dialog.selected_entry() is not None


def test_the_details_pane_shows_what_the_choice_turns_on(qapp):
    """Resolution, state, the bound ligand and the caveat are exactly the
    fields that distinguish three structures of the same target -- the
    decision this dialog exists to support."""
    dialog = ReceptorLibraryDialog()
    dialog._search.setText("4DKL")
    dialog._tree.setCurrentItem(_entry_items(dialog)[0])

    text = dialog._details.text()

    assert "4DKL" in text
    assert "2.80" in text
    assert "inactive" in text
    assert "BF0" in text, "the ligand code drives the docking box"
    assert "T4-lysozyme" in text, "the caveat is surfaced, not buried"


def test_selecting_a_second_receptor_replaces_the_first(qapp):
    dialog = ReceptorLibraryDialog()
    items = _entry_items(dialog)
    dialog._tree.setCurrentItem(items[0])
    first = dialog.selected_entry()
    dialog._tree.setCurrentItem(items[1])

    assert dialog.selected_entry() is not first


# --- the import path, through a real MainWindow ---------------------------


def _accept_with(monkeypatch, entry):
    monkeypatch.setattr(ReceptorLibraryDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ReceptorLibraryDialog, "selected_entry", lambda self: entry)


def test_importing_a_catalogue_entry_keeps_the_ligand_code(window, monkeypatch):
    """Without `ligand_code` on the macromolecule's metadata, the docking
    panel cannot place the search box and the whole point of the
    catalogue is lost between the dialog and the project."""
    monkeypatch.setattr(
        "openchem.services.receptor_library_service.fetch_structure",
        lambda pdb_id, timeout=120: ("HEADER    STUB\nEND\n", "pdb"),
    )
    _accept_with(monkeypatch, find("4DKL"))

    before = len(window._session.project.macromolecules)
    window._open_receptor_library()

    macromolecules = window._session.project.macromolecules
    assert len(macromolecules) == before + 1
    imported = macromolecules[-1]
    assert imported.metadata["ligand_code"] == "BF0"
    assert imported.metadata["pdb_id"] == "4DKL"
    assert "4DKL" in imported.display_name
    assert imported.source_format == "pdb"


def test_a_failed_download_reports_and_imports_nothing(window, monkeypatch):
    monkeypatch.setattr(
        "openchem.services.receptor_library_service.fetch_structure",
        lambda pdb_id, timeout=120: (_ for _ in ()).throw(RuntimeError("no network")),
    )
    _accept_with(monkeypatch, find("4DKL"))
    shown: list[str] = []
    monkeypatch.setattr(
        "openchem.app.main_window.QMessageBox.critical",
        lambda parent, title, text: shown.append(text),
    )

    before = len(window._session.project.macromolecules)
    window._open_receptor_library()

    assert len(window._session.project.macromolecules) == before
    assert shown and "no network" in shown[0]


def test_cancelling_the_dialog_downloads_nothing(window, monkeypatch):
    def explode(*_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("a cancelled dialog must not fetch anything")

    monkeypatch.setattr("openchem.services.receptor_library_service.fetch_structure", explode)
    monkeypatch.setattr(ReceptorLibraryDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    before = len(window._session.project.macromolecules)
    window._open_receptor_library()

    assert len(window._session.project.macromolecules) == before
