"""The panels must operate on the molecule the rest of the app is showing.

Reported as "ORCA will not run -- it says to generate conformers, and the
3D viewer is showing ten of them". ORCA was not involved: the Quantum
Chemistry panel's dropdown was pointing at a DIFFERENT molecule, which was
invisible because both were called "New molecule".

Two independent defects produced it, so there are two tests:
  * the panel never followed `MoleculeSelected` at all;
  * `QComboBox.clear()` during a repopulate resets the index to 0, and the
    panels are repopulated on every project mutation.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.app.settings import Settings
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel


@pytest.fixture
def widgets():
    """Every widget a test builds, destroyed deterministically after it.

    Same reasoning, and the same per-widget flush, as the fixture in
    tests/test_batch_panel.py -- see its docstring. These tests call
    `processEvents()` to deliver EventBus's queued signals, which is
    exactly the call that drains a stale `DeferredDelete` and crashes.
    """
    built = []
    yield built
    for widget in built:
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture
def two_molecule_project():
    """Deliberately BOTH named "New molecule" -- the condition that hid the bug."""
    engine = ChemistryEngine()
    first = MoleculeModel(display_name="New molecule")
    engine.set_structure_from_smiles(first, "O")
    second = MoleculeModel(display_name="New molecule")
    engine.set_structure_from_smiles(second, "C1CN1")
    second.conformers.append(ConformerModel(molblock=second.molblock, energy=53.72))
    project = ProjectModel(name="Untitled project")
    project.molecules.extend([first, second])
    return project, first, second, engine


def _panel(engine, widgets):
    bus = EventBus()
    settings = Settings(bus)
    panel = QuantumChemistryPanel(
        QuantumChemistryService(bus, settings, providers={}), engine, settings, bus
    )
    widgets.append(panel)
    return panel, bus


def test_panel_follows_the_selected_molecule(qapp, two_molecule_project, widgets):
    project, _first, second, engine = two_molecule_project
    panel, bus = _panel(engine, widgets)
    panel.set_project(project)

    bus.publish(MoleculeSelected(molecule_uuid=second.uuid))
    qapp.processEvents()

    assert panel._current_molecule() is second


def test_repopulating_the_combo_keeps_the_selection(qapp, two_molecule_project, widgets):
    """Adding a molecule must not silently move the panel to the first one.

    `MainWindow._refresh_molecule_combos` calls `set_project` again after
    any project mutation, so this fires on every import, every plugin
    result and every File > New Molecule.
    """
    project, _first, second, engine = two_molecule_project
    panel, bus = _panel(engine, widgets)
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=second.uuid))
    qapp.processEvents()

    project.molecules.append(MoleculeModel(display_name="Added later"))
    panel.set_project(project)

    assert panel._current_molecule() is second


def test_run_is_not_blocked_when_the_selected_molecule_has_conformers(
    qapp, two_molecule_project, widgets
):
    """The reported symptom, end to end.

    The first molecule has no conformer and the second does; with the
    second selected, Run must get past the conformer guard rather than
    telling the user to go and generate the conformers they already have.
    """
    project, _first, second, engine = two_molecule_project
    panel, bus = _panel(engine, widgets)
    panel.set_project(project)
    bus.publish(MoleculeSelected(molecule_uuid=second.uuid))
    qapp.processEvents()

    panel._on_run_clicked()

    assert "Generate Conformers" not in panel._status_label.text()
