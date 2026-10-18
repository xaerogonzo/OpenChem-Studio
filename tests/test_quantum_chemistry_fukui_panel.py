"""The Quantum Chemistry panel's side of the Fukui calculation: what it refuses before queueing a job, and what it says when
the run is done (live and from a stored run). The harness is the panel test file's own (a recording service, no QProcess)."""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import CALC_TYPE_LABELS
from openchem.domain.common import CacheState, Provenance
from openchem.domain.conformer import ConformerModel
from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.events import (
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    QuantumChemistryRunCompleted,
)

from test_quantum_chemistry_panel import (
    _dispose_panel,
    _make_panel,
    _panel_with_conformers,
)

FUKUI = "Fukui functions (Hirshfeld)"


def _dataset(property_id, values, *, molecule_uuid, unbound_ev=None):
    parameters = {} if unbound_ev is None else {"unbound_anion_ev": unbound_ev}
    return PerAtomDataset(
        property_id=property_id, name=property_id, units="", method="orca", molecule_uuid=molecule_uuid,
        values=dict(enumerate(values)),
        provenance=Provenance(created_by="core", method="orca", parameters=parameters),
    )


def _run(molecule_uuid, *, molblock="", unbound_ev=2.02):
    plus = [0.30, 0.45, 0.25]
    datasets = [
        _dataset("orca.fukui_plus", plus, molecule_uuid=molecule_uuid, unbound_ev=unbound_ev),
        _dataset("orca.fukui_minus", [0.50, 0.20, 0.30], molecule_uuid=molecule_uuid),
        _dataset("orca.fukui_zero", [0.40, 0.325, 0.275], molecule_uuid=molecule_uuid),
        _dataset("orca.fukui_dual", [-0.20, 0.25, -0.05], molecule_uuid=molecule_uuid),
    ]
    run = QuantumChemistryRun(
        run_id="run-1", molecule_uuid=molecule_uuid, calc_type="fukui", method_basis="B3LYP def2-SVP", charge=0,
        multiplicity=1, calculation_input="geometry", input_fingerprint="fp", input_molblock=molblock,
        status=RunStatus.COMPLETED,
    )
    run.results["per_atom"] = datasets
    run.output_status["per_atom"] = OutputStatus.AVAILABLE
    return run


def _select_fukui(panel) -> None:
    panel._calc_type_combo.setCurrentIndex(panel._calc_type_combo.findText(FUKUI))


def test_the_fukui_calculation_is_in_the_panel(qapp):
    panel, _engine, _service = _make_panel()
    try:
        offered = [panel._calc_type_combo.itemText(i) for i in range(panel._calc_type_combo.count())]
        assert FUKUI in offered
        assert CALC_TYPE_LABELS[FUKUI] == "fukui"
    finally:
        _dispose_panel(panel)


def test_a_closed_shell_fukui_run_is_submitted_with_its_calc_type(qapp):
    panel, service, _molecule = _panel_with_conformers(1)
    try:
        _select_fukui(panel)
        panel._on_run_clicked()
        assert len(service.requests) == 1
        request = service.requests[0]
        assert request["calc_type"] == "fukui" and request["multiplicity"] == 1
    finally:
        _dispose_panel(panel)


@pytest.mark.parametrize("multiplicity", [2, 3])
def test_an_open_shell_fukui_run_is_refused_before_a_job_is_queued(qapp, multiplicity):
    panel, service, _molecule = _panel_with_conformers(1)
    try:
        _select_fukui(panel)
        panel._multiplicity_spin.setValue(multiplicity)
        panel._on_run_clicked()
        assert service.requests == [] and service.boltzmann_requests == []
        assert "closed-shell" in panel._status_label.text() and f"multiplicity {multiplicity}" in panel._status_label.text()
        assert panel._run_button.isEnabled()  # nothing was started, so Run is still there
    finally:
        _dispose_panel(panel)


def test_the_same_open_shell_setting_is_fine_for_another_calculation(qapp):
    """The refusal belongs to Fukui, not to multiplicity 2."""
    panel, service, _molecule = _panel_with_conformers(1)
    try:
        panel._calc_type_combo.setCurrentIndex(panel._calc_type_combo.findText("Single Point"))
        panel._multiplicity_spin.setValue(2)
        panel._on_run_clicked()
        assert len(service.requests) == 1
    finally:
        _dispose_panel(panel)


def test_a_fukui_run_cannot_be_averaged_over_conformers(qapp):
    panel, service, _molecule = _panel_with_conformers(3)
    try:
        _select_fukui(panel)
        panel._boltzmann_check.setChecked(True)
        panel._on_run_clicked()
        assert service.requests == [] and service.boltzmann_requests == []
        assert "cannot be averaged over conformers" in panel._status_label.text()
    finally:
        _dispose_panel(panel)


def test_the_averaging_box_with_one_conformer_is_the_ordinary_path(qapp):
    """Nothing to average over: the panel already routes this to a single run, and the refusal must not fire."""
    panel, service, _molecule = _panel_with_conformers(1)
    try:
        _select_fukui(panel)
        panel._boltzmann_check.setChecked(True)
        panel._on_run_clicked()
        assert len(service.requests) == 1
    finally:
        _dispose_panel(panel)


# --- what the panel says when the run is done --------------------------------------------------------------------------


def _finish(service, run) -> None:
    """The two events a finished job publishes, in the service's order: the result, then the run. Published on the bus
    the panel was built on (the recording service holds it)."""
    bus = service._event_bus
    bus.publish(QuantumChemistryResultReady(molecule_uuid=run.molecule_uuid, descriptors=list(run.results.get("descriptors", [])), conformer=None))
    bus.publish(QuantumChemistryRunCompleted(run=run))


def test_the_live_summary_follows_the_descriptor_lines(qapp):
    from openchem.domain.descriptor import DescriptorValue

    panel, service, molecule = _panel_with_conformers(1)
    try:
        _select_fukui(panel)
        panel._on_run_clicked()
        run = _run(molecule.uuid)
        run.results["descriptors"] = [
            DescriptorValue(
                descriptor_id="orca.scf_energy", name="SCF Energy", units="Hartree", category="quantum_chemistry",
                provider="orca", molecule_uuid=molecule.uuid, value=-1.5, cache_state=CacheState.COMPLETED,
            )
        ]
        _finish(service, run)

        lines = panel._results_label.text().splitlines()
        assert lines[0].startswith("SCF Energy: -1.500000 Hartree")
        assert lines[1] == "Fukui functions (Hirshfeld, vertical) for 3 atoms:"
        # Butane's atoms 1-3 are carbons; numbered from 1, as the Atom Inspector numbers them.
        assert lines[2] == "Largest f+ (attack by a nucleophile): C (atom 2): 0.450"
        assert lines[3] == "Largest f- (attack by an electrophile): C (atom 1): 0.500"
        assert lines[4] == "Largest f0 (attack by a radical): C (atom 1): 0.400"
        assert lines[5].startswith("The anion is 2.02 eV ABOVE the neutral")
    finally:
        _dispose_panel(panel)


def test_a_run_with_no_per_atom_output_changes_nothing(qapp):
    panel, service, molecule = _panel_with_conformers(1)
    try:
        panel._on_run_clicked()
        panel._results_label.setText("SCF Energy: -1.0 Hartree")
        run = _run(molecule.uuid)
        run.results.pop("per_atom")
        service._event_bus.publish(QuantumChemistryRunCompleted(run=run))
        assert panel._results_label.text() == "SCF Energy: -1.0 Hartree"
    finally:
        _dispose_panel(panel)


def test_another_molecules_run_is_not_written_into_this_results_line(qapp):
    panel, service, molecule = _panel_with_conformers(1)
    try:
        panel._on_run_clicked()
        panel._results_label.setText("this molecule's line")
        service._event_bus.publish(QuantumChemistryRunCompleted(run=_run("some-other-molecule")))
        assert panel._results_label.text() == "this molecule's line"
    finally:
        _dispose_panel(panel)


def test_no_unbound_sentence_when_the_run_recorded_no_energy(qapp):
    panel, service, molecule = _panel_with_conformers(1)
    try:
        panel._on_run_clicked()
        panel._results_label.setText("")
        service._event_bus.publish(QuantumChemistryRunCompleted(run=_run(molecule.uuid, unbound_ev=None)))
        assert "ABOVE" not in panel._results_label.text()
        assert panel._results_label.text().startswith("Fukui functions (Hirshfeld, vertical) for 3 atoms:")
    finally:
        _dispose_panel(panel)


def test_a_stored_run_is_painted_with_the_same_summary(qapp):
    """`_render_run` is how a historical run comes back; it reads the elements from the run's own molblock."""
    panel, service, molecule = _panel_with_conformers(1)
    try:
        water = Chem.AddHs(Chem.MolFromSmiles("O"))
        AllChem.EmbedMolecule(water, randomSeed=7)
        run = _run(molecule.uuid, molblock=Chem.MolToMolBlock(water))
        panel._render_run(run)
        lines = panel._results_label.text().splitlines()
        assert lines[0] == "Fukui functions (Hirshfeld, vertical) for 3 atoms:"
        assert lines[1] == "Largest f+ (attack by a nucleophile): H (atom 2): 0.450"  # water: O, H, H
        assert any(line.startswith("The anion is 2.02 eV ABOVE") for line in lines)
    finally:
        _dispose_panel(panel)


def test_a_stored_run_with_no_molblock_still_says_where_without_inventing_an_element(qapp):
    panel, service, molecule = _panel_with_conformers(1)
    try:
        panel._render_run(_run(molecule.uuid, molblock=""))
        assert "? (atom 2)" in panel._results_label.text()
    finally:
        _dispose_panel(panel)


# --- the service's own refusal of the averaging path ----------------------------------------------------------------------


def test_the_service_refuses_to_average_a_fukui_run_over_conformers(qapp):
    """The panel says it first; this is the guard behind it, for any other caller."""
    from test_quantum_chemistry_run_recording import _make_service
    from test_quantum_chemistry_service import FakeQuantumEngineProvider

    service, bus = _make_service(FakeQuantumEngineProvider(stdout_text="ok"))
    states: list[QuantumChemistryJobStateChanged] = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=7)

    service.request_boltzmann_nmr(
        mols=[mol, mol], molecule_uuid="mol-1", calc_type="fukui", charge=0, multiplicity=1,
        method_basis="B3LYP def2-SVP", provider_id="fake",
    )

    assert states[-1].state is CacheState.FAILED and "cannot be averaged over conformers" in states[-1].message
    assert not service._active_jobs and not service._boltzmann_runs
