"""A person can set a molecule's spin multiplicity, and it is kept (OS item 12 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

Before this the Quantum panel's Multiplicity box was re-derived from the drawing on every selection, so a singlet O2 (drawn `O=O`, default triplet) or a triplet carbene drawn without a radical code could be
asked for once and was forgotten. `MoleculeModel.multiplicity` holds the choice, `SetMultiplicityCommand` makes it undoable, and `ChemistryEngine.stated_spin` applies it ONLY when the structure's electrons allow
it, because ORCA exits 55 on a parity-impossible pair after the job is queued.
"""

from __future__ import annotations

import pytest
from test_quantum_chemistry_panel import _dispose_panel, _make_panel

from openchem.chem.engine import ChemistryEngine
from openchem.chem.open_shell_geometry import build_open_shell_geometry
from openchem.commands.molecule_commands import SetMultiplicityCommand
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged

ENGINE = ChemistryEngine()


def _model(smiles: str, multiplicity: int | None = None) -> MoleculeModel:
    model = MoleculeModel(display_name=smiles)
    ENGINE.set_structure_from_smiles(model, smiles)
    model.multiplicity = multiplicity
    return model


def test_a_stated_multiplicity_replaces_the_default_and_the_drawings_own_stays_available():
    o2 = _model("O=O")
    assert ENGINE.default_multiplicity(o2) == 3
    o2.multiplicity = 1
    assert ENGINE.default_multiplicity(o2) == 1
    assert ENGINE.drawn_multiplicity(o2) == 3, "what the drawing implies, whatever was set"


@pytest.mark.parametrize("smiles, impossible", [("O=O", 2), ("O", 2), ("[CH3]", 1), ("[CH3]", 3)])
def test_a_multiplicity_the_electrons_cannot_have_is_ignored_not_applied(smiles, impossible):
    model = _model(smiles, impossible)
    assert ENGINE.multiplicity_issue(model, impossible)
    assert ENGINE.default_multiplicity(model) == ENGINE.drawn_multiplicity(model)


def test_an_edit_that_changes_the_electron_count_drops_the_stale_choice():
    model = _model("[CH3]", 4)  # a quartet methyl radical is parity-valid (9 electrons)
    assert ENGINE.default_multiplicity(model) == 4
    ENGINE.set_structure_from_smiles(model, "[CH2]")  # 8 electrons: 4 is impossible now
    assert ENGINE.default_multiplicity(model) == ENGINE.drawn_multiplicity(model) == 3


def test_the_chosen_multiplicity_picks_which_methylene_geometry_is_built():
    """Singlet CH2 is 102.4 degrees (Petek 1989) and triplet 133.9 (Jensen and Bunker 1988): the choice must reach the geometry table."""
    angles = {}
    for multiplicity in (1, 3):
        model = _model("[CH2]", multiplicity)
        built = build_open_shell_geometry(ENGINE.mol_from_model(model, allow_hypervalent=True))
        assert built is not None
        carbon, h1, h2 = (built.coordinates[i] for i in (0, 1, 2))
        import numpy as np

        u, v = np.array(h1) - np.array(carbon), np.array(h2) - np.array(carbon)
        angles[multiplicity] = float(np.degrees(np.arccos(u @ v / np.linalg.norm(u) / np.linalg.norm(v))))
    assert round(angles[1], 1) == 102.4 and round(angles[3], 1) == 133.9


def test_the_command_is_undoable_and_announces_the_change():
    model = _model("O=O")
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(MoleculeChanged, lambda event: seen.append(event.molecule_uuid))
    command = SetMultiplicityCommand(model, 1, bus)
    command.redo()
    assert model.multiplicity == 1
    command.undo()
    assert model.multiplicity is None
    assert seen == [model.uuid, model.uuid]


def test_it_is_saved_with_the_project_only_when_set():
    model = _model("O=O")
    assert "multiplicity" not in model.to_dict()
    model.multiplicity = 1
    assert MoleculeModel.from_dict(model.to_dict()).multiplicity == 1
    assert MoleculeModel.from_dict(_model("O").to_dict()).multiplicity is None


# --- the panel's box -----------------------------------------------------------------------------------------------------------------------------


def _panel_on(smiles: str, multiplicity: int | None = None):
    panel, engine, _service = _make_panel()
    molecule = MoleculeModel(display_name=smiles)
    engine.set_structure_from_smiles(molecule, smiles)
    molecule.multiplicity = multiplicity
    project = ProjectModel(name="t")
    project.molecules.append(molecule)
    requests: list = []
    panel.multiplicity_requested.connect(lambda uuid, value: requests.append((uuid, value)))
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    panel._on_molecule_changed(0)  # the combo may already sit on it, which fires nothing
    return panel, molecule, requests


def test_the_box_shows_the_stored_choice_and_selecting_does_not_store_anything(qapp):
    panel, molecule, requests = _panel_on("O=O", 5)
    try:
        assert panel._multiplicity_spin.value() == 5
        assert requests == []
    finally:
        _dispose_panel(panel)


def test_editing_the_box_asks_for_the_command_and_going_back_to_the_drawings_value_clears_it(qapp):
    panel, molecule, requests = _panel_on("O=O")
    try:
        assert panel._multiplicity_spin.value() == 3
        panel._multiplicity_spin.setValue(1)
        assert requests == [(molecule.uuid, 1)]
        molecule.multiplicity = 1  # what the window's command does
        panel._multiplicity_spin.setValue(3)
        assert requests[-1] == (molecule.uuid, None)
    finally:
        _dispose_panel(panel)


def test_a_value_the_electrons_cannot_have_is_left_in_the_box_and_not_stored(qapp):
    panel, molecule, requests = _panel_on("O=O")
    try:
        panel._multiplicity_spin.setValue(2)
        assert requests == [] and panel._multiplicity_spin.value() == 2
    finally:
        _dispose_panel(panel)


def test_an_undo_moves_the_box_back_without_asking_for_another_command(qapp):
    panel, molecule, requests = _panel_on("O=O", 1)
    try:
        molecule.multiplicity = None
        panel._on_molecule_event(MoleculeChanged(molecule_uuid=molecule.uuid, kind="identity"))
        assert panel._multiplicity_spin.value() == 3 and requests == []
    finally:
        _dispose_panel(panel)


def test_selecting_a_molecule_with_a_stale_choice_does_not_store_anything(qapp):
    """The panel writes the box itself (O2 with a stored 2, which its electrons cannot have, shows the default 3); that write is not the person editing."""
    panel, molecule, requests = _panel_on("O=O", 2)
    try:
        assert panel._multiplicity_spin.value() == 3 and requests == []
    finally:
        _dispose_panel(panel)
