"""The Quantum Chemistry panel's **Bond dissociation...** button: the question it asks, what it hands the service, what it refuses before queueing anything, and how the result reads.

The service is a recording double, as in `test_proton_affinity_panel.py`; the result shown is built by the real chemistry from real ORCA outputs of hydrogen cyanide, so the text the panel prints is the text a run would print.
"""
from __future__ import annotations

from pathlib import Path

import conftest
import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from openchem.app.settings import Settings
from openchem.chem import bond_dissociation as bd
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
from openchem.ui.panels import quantum_chemistry_panel as panel_module
from openchem.ui.panels.quantum_chemistry_panel import QuantumChemistryPanel

_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
H_ATOM = (_FIXTURES / "bde_h_atom.out").read_text(encoding="utf-8")
HCN = (_FIXTURES / "bde_hcn_parent_optfreq.out").read_text(encoding="utf-8")
CN_RADICAL = (_FIXTURES / "bde_cn_radical_optfreq.out").read_text(encoding="utf-8")
WATER = (_FIXTURES / "pa_water_optfreq.out").read_text(encoding="utf-8")


class _RecordingService(QuantumChemistryService):
    def __init__(self, event_bus: EventBus) -> None:
        super().__init__(event_bus, Settings(event_bus), providers={})
        self.bond_requests: list[dict] = []

    def request_bond_dissociation(self, **kwargs) -> None:
        self.bond_requests.append(kwargs)


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


@pytest.fixture
def answer_dialog(monkeypatch):
    """Answers the bond-choice dialog the way a person would: `ticks` is which of its boxes stay ticked (None: leave the default), then Run (or Cancel)."""
    seen: list[panel_module._BondChoiceDialog] = []

    def install(ticks: list[int] | None = None, accept: bool = True):
        def exec_(self):
            seen.append(self)
            if ticks is not None:
                for number, box in enumerate(self._boxes):
                    box.setChecked(number in ticks)
            return QDialog.DialogCode.Accepted if accept and self._run.isEnabled() else QDialog.DialogCode.Rejected

        monkeypatch.setattr(panel_module._BondChoiceDialog, "exec", exec_)
        return seen

    return install


def _result_for(smiles: str, outputs: list[str], molecule_uuid: str) -> QuantumChemistryResultReady:
    """The result event a run would publish, from the chemistry and real outputs."""
    sequence = bd.Sequence(smiles)
    for text in outputs:
        sequence.next_job()
        sequence.finish(text)
    assert sequence.done
    return QuantumChemistryResultReady(molecule_uuid=molecule_uuid, descriptors=bd.descriptors(sequence, molecule_uuid), conformer=None)


def test_the_button_exists_with_its_own_help_and_says_what_it_was_measured_to_do(qapp, dispose):
    panel, *_ = _panel_with("C#N")
    dispose(panel)
    tip = panel._bond_dissociation_button.toolTip()
    assert panel._bond_dissociation_button.text() == "Bond dissociation..."
    assert "bond dissociation enthalpy" in tip.lower() and "49 bonds" in tip and "LOW" in tip and "nine heavy atoms" in tip


def test_the_dialog_lists_every_bond_ticked_and_marks_the_classes_measured_to_run_worse(qapp, dispose):
    bonds = bd.describe_bonds("OO")  # hydrogen peroxide: one bond class, an O-H next to an oxygen
    dialog = panel_module._BondChoiceDialog(bonds, None)
    assert len(dialog._boxes) == 1 and dialog._boxes[0].isChecked() and dialog.chosen_atoms() == [0]
    assert "measured to run lowest" in dialog._boxes[0].text() and "3.3 kcal/mol" in dialog._boxes[0].text()
    thiol = panel_module._BondChoiceDialog(bd.describe_bonds("CS"), None)
    assert [box.text().endswith("the radical may have no value") for box in thiol._boxes] == [False, True]
    assert "49 X-H bonds" in thiol.findChildren(type(thiol._boxes[0]))[0].parent().findChildren(panel_module.QLabel)[-1].text()
    dialog.deleteLater()
    thiol.deleteLater()


def test_the_dialog_will_not_run_with_nothing_ticked_or_more_than_the_limit(qapp):
    dialog = panel_module._BondChoiceDialog(bd.describe_bonds("CC(O)C(N)CS"), None)
    assert len(dialog._boxes) > bd.MAX_BONDS and dialog.chosen_atoms() == [b["atom"] for b in bd.describe_bonds("CC(O)C(N)CS")[: bd.MAX_BONDS]]
    assert dialog._run.isEnabled()
    dialog._boxes[bd.MAX_BONDS].setChecked(True)
    assert not dialog._run.isEnabled() and "between 1 and" in dialog._run.toolTip()
    for box in dialog._boxes:
        box.setChecked(False)
    assert not dialog._run.isEnabled() and dialog.chosen_atoms() == []
    dialog._boxes[0].setChecked(True)
    assert dialog._run.isEnabled()
    dialog.deleteLater()


def test_a_click_hands_the_service_the_structure_the_chosen_bonds_and_the_identity_captured_now(qapp, dispose, answer_dialog):
    panel, molecule, service, _bus = _panel_with("C#N")
    dispose(panel)
    seen = answer_dialog()

    panel._on_bond_dissociation_clicked()

    assert len(seen) == 1 and len(service.bond_requests) == 1
    request = service.bond_requests[0]
    assert request["smiles"] == molecule.canonical_smiles and request["atoms"] == [0] and request["molecule_uuid"] == molecule.uuid
    assert request["calculation_input"] == DRAWING and request["input_fingerprint"] and request["structure_identity"] == molecule.canonical_smiles
    assert panel._status_label.text().startswith("queued -- 3 job(s)")
    assert not panel._bond_dissociation_button.isEnabled() and not panel._proton_affinity_button.isEnabled() and not panel._run_button.isEnabled() and panel._cancel_button.isEnabled()


def test_only_the_ticked_bonds_are_sent(qapp, dispose, answer_dialog):
    panel, _molecule, service, _bus = _panel_with("CO")  # methanol: C-H and O-H
    dispose(panel)
    answer_dialog(ticks=[1])

    panel._on_bond_dissociation_clicked()

    assert service.bond_requests[0]["atoms"] == [1]  # the oxygen
    assert panel._status_label.text().startswith("queued -- 3 job(s)")  # the atom, the parent and one radical


def test_cancelling_the_dialog_queues_nothing_and_leaves_the_buttons_alone(qapp, dispose, answer_dialog):
    panel, _molecule, service, _bus = _panel_with("CO")
    dispose(panel)
    answer_dialog(accept=False)

    panel._on_bond_dissociation_clicked()

    assert service.bond_requests == [] and panel._bond_dissociation_button.isEnabled() and panel._run_button.isEnabled() and not panel._cancel_button.isEnabled()


def test_a_molecule_the_protocol_cannot_compute_is_refused_before_the_question_is_asked(qapp, dispose, answer_dialog):
    panel, _molecule, service, _bus = _panel_with("C[N+](C)(C)C")
    dispose(panel)
    seen = answer_dialog()

    panel._on_bond_dissociation_clicked()

    assert seen == [] and service.bond_requests == []
    assert "does not apply" in panel._status_label.text() and "charged" in panel._status_label.text()
    assert panel._bond_dissociation_button.isEnabled() and panel._run_button.isEnabled()


def test_a_molecule_the_benchmarks_did_not_measure_asks_first_and_runs_on_yes(qapp, dispose, answer_dialog, monkeypatch):
    panel, _molecule, service, _bus = _panel_with("CCl")  # chlorine: computable, not measured
    dispose(panel)
    answer_dialog()
    asked = []

    def answer(reply):
        def question(parent, title, text, *args, **kwargs):
            asked.append(text)
            return reply
        return question

    monkeypatch.setattr(QMessageBox, "question", answer(QMessageBox.StandardButton.No))
    panel._on_bond_dissociation_clicked()
    assert service.bond_requests == [] and "outside what the benchmark measured" in asked[0] and "Cl:" in asked[0]

    monkeypatch.setattr(QMessageBox, "question", answer(QMessageBox.StandardButton.Yes))
    panel._on_bond_dissociation_clicked()
    assert len(service.bond_requests) == 1


def test_the_dialog_marks_a_bond_of_a_kind_that_was_never_measured(qapp):
    dialog = panel_module._BondChoiceDialog(bd.describe_bonds("c1ccccc1P"), None)
    texts = [box.text() for box in dialog._boxes]
    assert any(t.startswith("PH2-H") and t.endswith("no bond of this kind was measured") for t in texts)
    dialog.deleteLater()


def test_a_long_run_names_its_job_count_and_can_be_declined(qapp, dispose, answer_dialog, monkeypatch):
    panel, _molecule, service, _bus = _panel_with("Cc1ccccc1")  # toluene: four bond classes, one conformer: the atom, the parent and four radicals is six jobs; with six bonds there are more
    dispose(panel)
    answer_dialog()
    panel._BOND_DISSOCIATION_CONFIRM_ABOVE = 5
    asked = []

    def decline(parent, title, text, *args, **kwargs):
        asked.append(text)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    panel._on_bond_dissociation_clicked()

    assert service.bond_requests == [] and len(asked) == 1 and "6 ORCA jobs" in asked[0]
    assert panel._bond_dissociation_button.isEnabled()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel._on_bond_dissociation_clicked()
    assert len(service.bond_requests) == 1


def test_the_result_reads_with_one_decimal_the_bond_table_and_the_measured_error(qapp, dispose, answer_dialog):
    panel, molecule, _service, bus = _panel_with("C#N")
    dispose(panel)
    answer_dialog()
    panel._on_bond_dissociation_clicked()

    bus.publish(_result_for("C#N", [H_ATOM, HCN, CN_RADICAL], molecule.uuid))

    text = panel._results_label.text()
    assert "Weakest X-H bond dissociation enthalpy (298.15 K): 539." in text
    assert "Bonds (kJ/mol and kcal/mol; * marks the weakest" in text and "C-H, bonded to N:" in text and "kcal/mol) *" in text
    assert "49 X-H bonds" in text and "run LOW" in text


def test_a_bond_with_no_value_says_why_instead_of_breaking_the_panel(qapp, dispose, answer_dialog):
    panel, molecule, _service, bus = _panel_with("C#N")
    dispose(panel)
    answer_dialog()
    panel._on_bond_dissociation_clicked()

    bus.publish(_result_for("C#N", [H_ATOM, HCN, WATER], molecule.uuid))  # a radical that is not HCN's

    text = panel._results_label.text()
    assert "Weakest X-H bond dissociation enthalpy (298.15 K): no value" in text and "rearranged" in text
    assert "no value -- no accepted radical structure" in text


def test_the_buttons_come_back_when_the_run_ends_in_either_state(qapp, dispose, answer_dialog):
    panel, molecule, _service, bus = _panel_with("C#N")
    dispose(panel)
    answer_dialog()
    for state in (CacheState.COMPLETED, CacheState.FAILED):
        panel._on_bond_dissociation_clicked()
        assert not panel._bond_dissociation_button.isEnabled()
        bus.publish(QuantumChemistryJobStateChanged(molecule_uuid=molecule.uuid, state=state, message=""))
        assert panel._bond_dissociation_button.isEnabled() and panel._run_button.isEnabled() and not panel._cancel_button.isEnabled()


def _stored_run_for(smiles: str, outputs: list[str], molecule_uuid: str):
    """A finished run as the Runs history holds it: the descriptors the real chemistry built from real outputs."""
    from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus

    sequence = bd.Sequence(smiles)
    for text in outputs:
        sequence.next_job()
        sequence.finish(text)
    return QuantumChemistryRun(
        run_id="r-bd", molecule_uuid=molecule_uuid, calc_type="bond_dissociation", method_basis=bd.METHOD_LABEL, charge=0, multiplicity=1,
        calculation_input=DRAWING, input_fingerprint="", input_molblock="", status=RunStatus.COMPLETED,
        results={"descriptors": bd.descriptors(sequence, molecule_uuid)},
    )


def test_a_stored_run_comes_back_with_its_bond_table_and_one_with_no_value_re_renders_without_raising(qapp, dispose):
    panel, molecule, _service, _bus = _panel_with("C#N")
    dispose(panel)

    panel._render_run(_stored_run_for("C#N", [H_ATOM, HCN, CN_RADICAL], molecule.uuid))
    assert "Weakest X-H bond dissociation enthalpy (298.15 K): 539." in panel._results_label.text() and "Bonds (kJ/mol" in panel._results_label.text()

    panel._render_run(_stored_run_for("C#N", [H_ATOM, HCN, WATER], molecule.uuid))
    assert "(298.15 K): no value" in panel._results_label.text()
