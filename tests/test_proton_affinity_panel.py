"""The Quantum Chemistry panel's **Proton affinity...** button: what it hands the service, what it refuses before queueing anything, and how the result reads.

The service is a recording double, as in `test_quantum_chemistry_panel.py`; the result shown is built by the real chemistry from the benchmark's real ORCA outputs, so the text the panel prints is the text a run would print.
"""
from __future__ import annotations

from pathlib import Path

import conftest
import pytest
from PySide6.QtWidgets import QMessageBox

from openchem.app.settings import Settings
from openchem.chem import proton_affinity as pa
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import (
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
)
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
WATER = (_FIXTURES / "pa_water_optfreq.out").read_text(encoding="utf-8")
HYDRONIUM = (_FIXTURES / "pa_h3o_optfreq.out").read_text(encoding="utf-8")
PLANAR_HYDRONIUM = HYDRONIUM.replace("6:     807.65 cm**-1", "6:    -601.55 cm**-1")


class _RecordingService(QuantumChemistryService):
    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.proton_affinity_requests: list[dict] = []

    def request_proton_affinity(self, **kwargs) -> None:  # noqa: D102 - test double
        self.proton_affinity_requests.append(kwargs)


def _panel_with(smiles: str):
    bus = EventBus()
    engine = ChemistryEngine()
    service = _RecordingService(bus)
    panel = QuantumChemistryPanel(service, engine, Settings(bus), bus)
    molecule = MoleculeModel(display_name=smiles)
    engine.set_structure_from_smiles(molecule, smiles)
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    return panel, molecule, service, bus


@pytest.fixture
def dispose():
    panels = []
    yield panels.append
    for panel in panels:
        conftest.dispose(panel)


def _result_for(smiles: str, outputs: list[str], molecule_uuid: str) -> QuantumChemistryResultReady:
    """The result event a run would publish, from the chemistry and the benchmark's real outputs."""
    sequence = pa.Sequence(smiles)
    for text in outputs:
        sequence.next_job()
        sequence.finish(text)
    assert sequence.done
    return QuantumChemistryResultReady(molecule_uuid=molecule_uuid, descriptors=pa.descriptors(sequence, molecule_uuid), conformer=None)


def test_the_button_exists_with_its_own_help_and_says_what_it_was_measured_to_do(qapp, dispose):
    panel, *_ = _panel_with("O")
    dispose(panel)
    tip = panel._proton_affinity_button.toolTip()
    assert panel._proton_affinity_button.text() == "Proton affinity..."
    assert "proton affinity" in tip.lower() and "1.5 kcal/mol" in tip and "ten heavy atoms" in tip


def test_a_click_hands_the_service_the_structure_and_the_identity_captured_now(qapp, dispose):
    panel, molecule, service, _bus = _panel_with("O")
    dispose(panel)

    panel._on_proton_affinity_clicked()

    assert len(service.proton_affinity_requests) == 1
    request = service.proton_affinity_requests[0]
    assert request["smiles"] == molecule.canonical_smiles and request["molecule_uuid"] == molecule.uuid
    assert request["calculation_input"] == DRAWING and request["input_fingerprint"] and request["structure_identity"] == molecule.canonical_smiles
    assert panel._status_label.text().startswith("queued -- 2 optimization")
    assert not panel._proton_affinity_button.isEnabled() and not panel._run_button.isEnabled() and panel._cancel_button.isEnabled()


def test_a_base_the_benchmark_did_not_measure_is_refused_in_the_panel_before_anything_is_queued(qapp, dispose):
    panel, _molecule, service, _bus = _panel_with("CCl")
    dispose(panel)

    panel._on_proton_affinity_clicked()

    assert service.proton_affinity_requests == []
    assert "does not apply" in panel._status_label.text() and "Cl" in panel._status_label.text()
    assert panel._proton_affinity_button.isEnabled() and panel._run_button.isEnabled()


def test_a_long_run_names_its_job_count_and_can_be_declined(qapp, dispose, monkeypatch):
    panel, _molecule, service, _bus = _panel_with("c1ccncc1")  # pyridine: the base and four sites, five jobs
    dispose(panel)
    asked = []

    def decline(parent, title, text, *args, **kwargs):
        asked.append(text)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    panel._on_proton_affinity_clicked()

    assert service.proton_affinity_requests == [] and len(asked) == 1 and "5 ORCA geometry optimizations" in asked[0]
    assert panel._proton_affinity_button.isEnabled()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel._on_proton_affinity_clicked()
    assert len(service.proton_affinity_requests) == 1


def test_the_result_reads_with_one_decimal_the_site_table_and_the_measured_error(qapp, dispose):
    panel, molecule, _service, bus = _panel_with("O")
    dispose(panel)
    panel._on_proton_affinity_clicked()

    bus.publish(_result_for("O", [WATER, HYDRONIUM], molecule.uuid))

    text = panel._results_label.text()
    assert "Proton affinity (298.15 K): 686.8 kJ/mol" in text and "Gas-phase basicity (298.15 K): 655.8 kJ/mol" in text
    assert "Protonation sites" in text and "0, O:" in text and "*PA" in text
    assert "1.55 kcal/mol" in text and "too weakly" in text


def test_a_quantity_with_no_value_says_why_instead_of_breaking_the_panel(qapp, dispose):
    panel, molecule, _service, bus = _panel_with("O")
    dispose(panel)
    panel._on_proton_affinity_clicked()

    bus.publish(_result_for("O", [WATER, PLANAR_HYDRONIUM, PLANAR_HYDRONIUM], molecule.uuid))  # the benchmark's own water

    text = panel._results_label.text()
    assert "Proton affinity (298.15 K): no value" in text and "mol|ion|lone_pair0|0" in text and "Gas-phase basicity (298.15 K): no value" in text
    assert "Not accepted: mol|ion|lone_pair0|0" in text


def test_the_buttons_come_back_when_the_run_ends_in_either_state(qapp, dispose):
    panel, molecule, _service, bus = _panel_with("O")
    dispose(panel)
    for state in (CacheState.COMPLETED, CacheState.FAILED):
        panel._on_proton_affinity_clicked()
        assert not panel._proton_affinity_button.isEnabled()
        bus.publish(QuantumChemistryJobStateChanged(molecule_uuid=molecule.uuid, state=state, message=""))
        assert panel._proton_affinity_button.isEnabled() and panel._run_button.isEnabled() and not panel._cancel_button.isEnabled()
