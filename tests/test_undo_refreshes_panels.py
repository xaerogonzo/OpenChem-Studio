"""Undo and redo must reach the panels, not just the project.

Every method that pushes a command refreshes the dropdowns itself --
`add_molecule`, `add_macromolecule`, the import paths. Undo and redo go
through none of them, so a project that changed back left the panels
listing things it no longer contains.

Measured before the fix: importing a receptor and pressing Ctrl+Z removed
it from the project and LEFT IT IN the Docking panel's receptor list,
where it could still be selected and docked against.
"""

from __future__ import annotations

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel

import conftest


@pytest.fixture
def widgets():
    built = []
    yield built
    for widget in built:
        widget.close()
        conftest.dispose(widget)


@pytest.fixture
def window(qapp, tmp_path, widgets):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    main_window = MainWindow(services, settings, SessionManager())
    widgets.append(main_window)
    return main_window


def _receptor_items(window) -> list[str]:
    combo = window._docking_panel._receptor_combo
    return [combo.itemText(row) for row in range(combo.count())]


def _ligand_items(window) -> list[str]:
    combo = window._docking_panel._ligand_combo
    return [combo.itemText(row) for row in range(combo.count())]


def test_undoing_a_macromolecule_import_clears_it_from_the_receptor_list(window, qapp):
    """The dangerous one: a receptor that is not in the project must not be
    selectable as a docking target."""
    window.add_macromolecule(MacromoleculeModel(display_name="1HSG"))
    qapp.processEvents()
    assert "1HSG" in _receptor_items(window)

    window._undo_stack.undo()
    qapp.processEvents()

    assert not window._session.project.macromolecules
    assert "1HSG" not in _receptor_items(window)


def test_redoing_the_import_puts_it_back(window, qapp):
    window.add_macromolecule(MacromoleculeModel(display_name="1HSG"))
    qapp.processEvents()
    window._undo_stack.undo()
    qapp.processEvents()

    window._undo_stack.redo()
    qapp.processEvents()

    assert "1HSG" in _receptor_items(window)


def test_undoing_a_molecule_add_clears_it_from_the_ligand_list(window, qapp):
    """Same hole, the other list. `AddMoleculeCommand` does publish an
    event, but nothing was refreshing the combos from it either."""
    window.add_molecule(MoleculeModel(display_name="Ligand candidate"))
    qapp.processEvents()
    assert "Ligand candidate" in _ligand_items(window)

    window._undo_stack.undo()
    qapp.processEvents()

    assert "Ligand candidate" not in _ligand_items(window)


def test_the_refresh_keeps_the_current_selection(window, qapp):
    """A repopulate must not move the panels onto a different molecule.

    This is what makes hooking the whole undo stack safe rather than
    disruptive -- `repopulate` restores by uuid, so refreshing on an
    unrelated undo costs nothing.
    """
    from openchem.commands.molecule_commands import RenameMoleculeCommand

    first = MoleculeModel(display_name="First")
    second = MoleculeModel(display_name="Second")
    window.add_molecule(first)
    window.add_molecule(second)
    qapp.processEvents()
    combo = window._quantum_chemistry_panel._molecule_combo
    combo.setCurrentIndex(combo.findData(first.uuid))

    # An UNRELATED command, undone. Adding a molecule would not do: that
    # deliberately selects the new one, so the panel moving is correct
    # behaviour rather than the refresh misbehaving.
    window._undo_stack.push(
        RenameMoleculeCommand(second, "Renamed", window._services.event_bus)
    )
    window._undo_stack.undo()
    qapp.processEvents()

    assert combo.currentData() == first.uuid
    assert second.display_name == "Second"


def test_a_macromolecules_metadata_survives_a_project_round_trip(window, tmp_path):
    """`ligand_code` is what `strip_ligand_codes` uses to clear the pocket a
    receptor's search box was derived from. If it did not survive save and
    load, reopening a project would silently dock into an occupied site --
    the bug that measured -5.34 against -9.75 on 1HSG.
    """
    receptor = MacromoleculeModel(display_name="1HSG")
    receptor.metadata["ligand_code"] = "MK1"
    window.add_macromolecule(receptor)

    path = tmp_path / "receptors.ocsproj"
    service = window._services.project_service
    service.save(window._session.project, path)
    loaded = service.load(path)

    assert loaded.macromolecules
    restored = loaded.macromolecules[0]
    assert restored.metadata.get("ligand_code") == "MK1"
    assert restored.uuid == receptor.uuid
