"""What the Quantum Chemistry panel's Run button decides, pinned before its request-building moved out of the panel (`chem/quantum_run_request.py`).

The button used to hold, in one 125-line handler, every rule for "may this molecule be run as asked, and with what": a molecule is selected, it has a conformer, the conformer is usable 3D, a method
is typed, an open-shell Fukui run and a conformer average are refused, an average resolves, a cost is accepted. Most of those branches had no test. These pin each one through the real panel and a
service double that records what it was handed, so the extraction is held to behaviour and not to a reading of the code: they pass on the handler as it was and on the shared function that replaced it.
"""

from __future__ import annotations

import pytest
from test_quantum_chemistry_panel import _dispose_panel, _make_panel, _panel_with_conformers

from openchem.chem.calculation_input import canonical_conformer, geometry_fingerprint
from openchem.chem.fukui import conformer_average_message, open_shell_message
from openchem.domain.calculator import ENSEMBLE, GEOMETRY
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel

SINGLE_KEYS = {
    "mol", "molecule_uuid", "calc_type", "charge", "multiplicity", "method_basis", "provider_id", "input_fingerprint", "calculation_input", "structure_identity", "source_slot",
}
ENSEMBLE_KEYS = {"mols", "molecule_uuid", "calc_type", "charge", "multiplicity", "method_basis", "provider_id", "input_fingerprint", "calculation_input", "structure_identity"}


@pytest.fixture
def panel_of(qapp):
    made = []

    def build(count: int = 3):
        panel, service, molecule = _panel_with_conformers(count)
        made.append(panel)
        return panel, service, molecule

    yield build
    for panel in made:
        _dispose_panel(panel)


def untouched(panel, service) -> None:
    """A refusal leaves the panel as it was and asks the service for nothing."""
    assert service.requests == [] and service.boltzmann_requests == []
    assert panel._pending_molecule_uuid is None
    assert panel._run_button.isEnabled() and not panel._cancel_button.isEnabled()


# --- refusals, each in the order the handler makes them ------------------------------------------------------------------------------------------


def test_with_no_molecule_selected_it_says_so_and_asks_nothing(qapp):
    panel, _engine, service = _make_panel()
    try:
        panel._on_run_clicked()
        assert panel._status_label.text() == "Select a molecule with a structure first."
        untouched(panel, service)
    finally:
        _dispose_panel(panel)


def test_a_molecule_with_no_conformer_is_sent_to_generate_one(qapp):
    panel, engine, service = _make_panel()
    try:
        molecule = MoleculeModel(display_name="Water")
        engine.set_structure_from_smiles(molecule, "O")
        project = ProjectModel(name="t")
        project.molecules.append(molecule)
        panel.set_project(project)
        panel._molecule_combo.setCurrentIndex(0)
        panel._method_combo.setCurrentText("HF STO-3G")
        panel._on_run_clicked()
        assert panel._status_label.text().startswith("Generate one with Structure")
        untouched(panel, service)
    finally:
        _dispose_panel(panel)


def test_a_conformer_that_is_flat_is_refused_and_never_run_on_the_drawing(panel_of):
    panel, service, molecule = panel_of(1)
    molecule.conformers[:] = [ConformerModel(molblock=molecule.molblock, method="drawing")]
    panel._on_run_clicked()
    assert panel._status_label.text().startswith("The selected molecule's conformer has no usable 3D coordinates.")
    untouched(panel, service)


def test_no_method_typed_is_refused(panel_of):
    panel, service, _molecule = panel_of(2)
    panel._method_combo.setCurrentText("   ")
    panel._on_run_clicked()
    assert panel._status_label.text() == "Enter a method/basis (e.g. 'B3LYP def2-SVP')."
    untouched(panel, service)


def test_an_open_shell_fukui_run_is_refused_with_the_engines_own_words(panel_of):
    panel, service, _molecule = panel_of(2)
    panel._calc_type_combo.setCurrentText("Fukui functions (Hirshfeld)")
    panel._multiplicity_spin.setValue(2)
    panel._on_run_clicked()
    assert panel._status_label.text() == open_shell_message(2)
    untouched(panel, service)


def test_a_fukui_run_averaged_over_conformers_is_refused(panel_of):
    panel, service, _molecule = panel_of(3)
    panel._calc_type_combo.setCurrentText("Fukui functions (Hirshfeld)")
    panel._boltzmann_check.setChecked(True)
    panel._on_run_clicked()
    assert panel._status_label.text() == conformer_average_message()
    untouched(panel, service)


def test_an_average_over_a_set_with_an_unusable_conformer_names_it_and_is_refused(panel_of):
    panel, service, molecule = panel_of(3)
    molecule.conformers[1] = ConformerModel(molblock=molecule.molblock, method="drawing")
    panel._boltzmann_check.setChecked(True)
    panel._on_run_clicked()
    assert panel._status_label.text() == "Cannot average over the conformers: Conformer 2 has no 3D coordinates."
    untouched(panel, service)


def test_an_averaging_run_is_only_an_average_when_there_is_more_than_one_conformer(panel_of):
    panel, service, _molecule = panel_of(1)
    panel._boltzmann_check.setChecked(True)
    panel._on_run_clicked()
    assert len(service.requests) == 1 and service.boltzmann_requests == [], "one conformer: a single run, as the panel always did"


def test_a_cost_the_person_declines_starts_nothing(panel_of, monkeypatch):
    panel, service, _molecule = panel_of(2)
    asked = []
    monkeypatch.setattr(panel, "_confirm_led_cost", lambda parent, mol: asked.append(mol.GetNumAtoms()) or False)
    panel._calc_type_combo.setCurrentText("Interaction energy breakdown (LED)")
    panel._on_run_clicked()
    assert len(asked) == 1 and asked[0] > 0, "asked once, about the molecule that would be run"
    untouched(panel, service)


def test_a_cost_the_person_accepts_runs_it(panel_of, monkeypatch):
    panel, service, _molecule = panel_of(2)
    monkeypatch.setattr(panel, "_confirm_led_cost", lambda parent, mol: True)
    panel._calc_type_combo.setCurrentText("Interaction energy breakdown (LED)")
    panel._on_run_clicked()
    assert [r["calc_type"] for r in service.requests] == ["led"]


def test_no_cost_is_asked_for_any_other_calculation(panel_of, monkeypatch):
    panel, service, _molecule = panel_of(2)
    monkeypatch.setattr(panel, "_confirm_led_cost", lambda parent, mol: pytest.fail("only LED asks"))
    for label in ("Single Point", "Geometry Optimization", "Optimization + Frequency", "NMR (raw shielding)"):
        panel._calc_type_combo.setCurrentText(label)
        panel._run_button.setEnabled(True)
        panel._on_run_clicked()
    assert [r["calc_type"] for r in service.requests] == ["sp", "opt", "opt_freq", "nmr"]


# --- what a started run hands the service, and what the panel does about it ---------------------------------------------------------------------


def test_a_single_run_hands_the_service_exactly_these_arguments(panel_of):
    panel, service, molecule = panel_of(3)
    panel._calc_type_combo.setCurrentText("Single Point")
    panel._charge_spin.setValue(1)
    panel._multiplicity_spin.setValue(2)
    panel._on_run_clicked()
    [request] = service.requests
    canonical = canonical_conformer(molecule)
    assert set(request) == SINGLE_KEYS
    assert request["molecule_uuid"] == molecule.uuid and request["calc_type"] == "sp"
    assert (request["charge"], request["multiplicity"], request["method_basis"], request["provider_id"]) == (1, 2, "B3LYP pcSseg-1", "orca")
    assert request["input_fingerprint"] == geometry_fingerprint(canonical) and request["calculation_input"] == GEOMETRY
    assert request["structure_identity"] == molecule.canonical_smiles != ""
    assert request["source_slot"] == molecule.conformers.index(canonical) + 1
    assert request["mol"].GetNumAtoms() == 14 and request["mol"].GetConformer().Is3D()


def test_a_solvent_goes_into_the_method_header_of_the_run(panel_of):
    panel, service, _molecule = panel_of(2)
    index = next(i for i in range(panel._solvent_combo.count()) if panel._solvent_combo.itemData(i))
    solvent = panel._solvent_combo.itemData(index)
    panel._solvent_combo.setCurrentIndex(index)
    panel._on_run_clicked()
    assert service.requests[0]["method_basis"] == f"B3LYP pcSseg-1 CPCM({solvent})"


def test_an_averaged_run_hands_the_service_every_conformer_and_an_ensemble_identity(panel_of):
    panel, service, molecule = panel_of(3)
    panel._calc_type_combo.setCurrentText("NMR (raw shielding)")
    panel._boltzmann_check.setChecked(True)
    panel._on_run_clicked()
    assert service.requests == []
    [request] = service.boltzmann_requests
    assert set(request) == ENSEMBLE_KEYS and request["calc_type"] == "nmr" and request["calculation_input"] == ENSEMBLE
    assert len(request["mols"]) == 3 and request["structure_identity"] == molecule.canonical_smiles
    assert request["input_fingerprint"] and request["input_fingerprint"] != geometry_fingerprint(canonical_conformer(molecule))


def test_a_started_run_leaves_the_panel_waiting_for_it(panel_of):
    panel, service, molecule = panel_of(2)
    panel._on_run_clicked()
    assert len(service.requests) == 1
    assert panel._pending_molecule_uuid == molecule.uuid and panel._status_label.text() == "queued"
    assert not panel._run_button.isEnabled() and panel._cancel_button.isEnabled()
    canonical = canonical_conformer(molecule)
    assert panel._pending_molblock == molecule.molblock and panel._pending_conformer_molblock == canonical.molblock
    assert panel._pending_mol is not None and panel._pending_mol.GetNumAtoms() == 14 and panel._optimized_conformer_molblock == ""


def test_a_conformer_that_is_not_the_one_every_calculation_uses_is_noted_for_a_single_point_and_not_for_an_optimization(panel_of):
    panel, service, molecule = panel_of(3)
    automatic = canonical_conformer(molecule)
    other = next(c for c in molecule.conformers if c is not automatic)
    assert panel.choose_conformer(molecule.uuid, other.conformer_id)
    panel._calc_type_combo.setCurrentText("Single Point")
    panel._on_run_clicked()
    slot = molecule.conformers.index(other) + 1
    assert panel._pending_conformer_note.startswith(f"Computed on conformer {slot}, not the one every calculation uses")
    assert service.requests[0]["input_fingerprint"] == geometry_fingerprint(other) and service.requests[0]["source_slot"] == slot
    panel._run_button.setEnabled(True)
    panel._calc_type_combo.setCurrentText("Geometry Optimization")
    panel._on_run_clicked()
    assert panel._pending_conformer_note == ""
