"""`QuantumChemistryPanel.start_assistant_run`: the job an assistant's card described, started by the Run button's own rules once a person has approved it (dispatch, step 2).

The panel is the one place that knows what a pressed Run commits to (which molecule it waits for, what was submitted, a clean slate for the results), so a card's Approve goes through it rather than
around it. These hold it to the button: the same arguments reach the service, the panel waits for the job exactly as it does for its own, and everything the button refuses is refused here in the
button's words, with the answer coming back as text because nobody is watching this panel when an assistant's card is approved.
"""

from __future__ import annotations

import pytest
from test_orca_led import _pair
from test_quantum_chemistry_panel import _dispose_panel, _make_panel, _panel_with_conformers

from rdkit import Chem

from openchem.chem.calculation_input import canonical_conformer, geometry_fingerprint
from openchem.chem.quantum_run_request import NO_CONFORMER, NO_USABLE_CONFORMER, TWO_PARTNERS_MESSAGE, RunChoice
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel


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


def choice(**kw) -> RunChoice:
    base = dict(calc_type="sp", method_basis="B3LYP pcSseg-1", charge=0, multiplicity=1)
    base.update(kw)
    return RunChoice(**base)


def fingerprint_of(molecule) -> str:
    return geometry_fingerprint(canonical_conformer(molecule))


def untouched(panel, service) -> None:
    assert service.requests == [] and service.boltzmann_requests == []
    assert panel._pending_molecule_uuid is None and panel._run_button.isEnabled() and not panel._cancel_button.isEnabled()


# --- the same job the button would have started ----------------------------------------------------------------------------------------------------


def test_it_hands_the_service_exactly_what_the_run_button_hands_it(panel_of):
    panel, service, molecule = panel_of(3)
    panel._on_run_clicked()
    [by_button] = service.requests
    # The same molecule again: the panel is idle once the first job has ended.
    service.requests.clear()
    panel._pending_molecule_uuid = None
    panel._run_button.setEnabled(True)
    assert panel.start_assistant_run(molecule.uuid, choice(), fingerprint_of(molecule)) == ""
    [by_card] = service.requests
    assert set(by_card) == set(by_button)
    for key in by_button:
        if key in ("mol", "molecule_uuid"):
            continue
        assert by_card[key] == by_button[key], key
    assert Chem.MolToMolBlock(by_card["mol"]) == Chem.MolToMolBlock(by_button["mol"])
    assert by_card["molecule_uuid"] == molecule.uuid and by_card["calculation_input"] == "geometry"


def test_the_card_chooses_the_settings_and_not_the_panels_controls(panel_of):
    panel, service, molecule = panel_of(3)
    panel._calc_type_combo.setCurrentText("Geometry Optimization")
    panel._charge_spin.setValue(2)
    panel.start_assistant_run(molecule.uuid, choice(calc_type="nmr", method_basis="PBE0 def2-TZVP", charge=-1, multiplicity=2), fingerprint_of(molecule))
    [request] = service.requests
    assert (request["calc_type"], request["method_basis"], request["charge"], request["multiplicity"], request["provider_id"]) == ("nmr", "PBE0 def2-TZVP", -1, 2, "orca")


def test_the_panel_then_waits_for_the_job_as_it_does_for_its_own(panel_of):
    panel, service, molecule = panel_of(2)
    assert panel.start_assistant_run(molecule.uuid, choice(), fingerprint_of(molecule)) == ""
    assert panel._pending_molecule_uuid == molecule.uuid and panel._status_label.text() == "queued"
    assert not panel._run_button.isEnabled() and panel._cancel_button.isEnabled()
    canonical = canonical_conformer(molecule)
    assert panel._pending_molblock == molecule.molblock and panel._pending_conformer_molblock == canonical.molblock
    assert panel._pending_mol is not None and panel._pending_conformer_note == ""


def test_the_panel_shows_the_molecule_the_job_is_for(panel_of):
    panel, service, molecule = panel_of(2)
    other = MoleculeModel(display_name="Other")
    panel._chemistry_engine.set_structure_from_smiles(other, "CCO")
    panel._project.molecules.insert(0, other)
    panel.set_project(panel._project)
    panel._molecule_combo.setCurrentIndex(0)
    assert panel._molecule_combo.currentData() == other.uuid
    assert panel.start_assistant_run(molecule.uuid, choice(), fingerprint_of(molecule)) == ""
    assert panel._molecule_combo.currentData() == molecule.uuid and panel._pending_molecule_uuid == molecule.uuid


def test_an_average_is_never_what_a_card_asks_for(panel_of):
    panel, service, molecule = panel_of(3)
    panel._boltzmann_check.setChecked(True)
    panel.start_assistant_run(molecule.uuid, choice(calc_type="nmr"), fingerprint_of(molecule))
    assert len(service.requests) == 1 and service.boltzmann_requests == [], "the choice says one job, whatever the box is ticked to"


# --- what it refuses, and in whose words ----------------------------------------------------------------------------------------------------------


def test_a_panel_that_is_already_waiting_for_a_job_refuses_a_second(panel_of):
    panel, service, molecule = panel_of(2)
    assert panel.start_assistant_run(molecule.uuid, choice(), fingerprint_of(molecule)) == ""
    reason = panel.start_assistant_run(molecule.uuid, choice(calc_type="opt"), fingerprint_of(molecule))
    assert "busy with another calculation" in reason and len(service.requests) == 1


def test_a_molecule_the_service_is_already_running_is_not_started_again(panel_of):
    panel, service, molecule = panel_of(2)
    assert service._job_manager.try_start("quantum_chemistry", molecule.uuid)
    assert "already running for this molecule" in panel.start_assistant_run(molecule.uuid, choice(), fingerprint_of(molecule))
    assert service.requests == [] and panel._pending_molecule_uuid is None


def test_a_molecule_that_is_no_longer_in_the_project_is_not_started(panel_of):
    panel, service, molecule = panel_of(2)
    assert "no longer in the open project" in panel.start_assistant_run("not-a-molecule", choice(), "x")
    untouched(panel, service)


def test_with_no_project_open_nothing_is_started(qapp):
    panel, _engine, service = _make_panel()
    try:
        assert "no longer in the open project" in panel.start_assistant_run("x", choice(), "x")
        untouched(panel, service)
    finally:
        _dispose_panel(panel)


def test_everything_the_button_refuses_is_refused_in_the_buttons_words(qapp):
    panel, engine, service = _make_panel()
    try:
        bare = MoleculeModel(display_name="Water")
        engine.set_structure_from_smiles(bare, "O")
        project = ProjectModel(name="t")
        project.molecules.append(bare)
        panel.set_project(project)
        assert panel.start_assistant_run(bare.uuid, choice(), "x") == NO_CONFORMER
        bare.conformers.append(ConformerModel(molblock=bare.molblock, method="drawing"))
        assert panel.start_assistant_run(bare.uuid, choice(), "x") == NO_USABLE_CONFORMER
        untouched(panel, service)
    finally:
        _dispose_panel(panel)


def test_a_blank_method_is_refused_as_it_is_for_the_button(panel_of):
    panel, service, molecule = panel_of(2)
    assert panel.start_assistant_run(molecule.uuid, choice(method_basis="  "), fingerprint_of(molecule)) == "Enter a method/basis (e.g. 'B3LYP def2-SVP')."
    untouched(panel, service)


def test_a_conformer_that_is_not_the_one_the_card_was_made_for_is_not_run(panel_of):
    panel, service, molecule = panel_of(3)
    reason = panel.start_assistant_run(molecule.uuid, choice(), "the fingerprint of another conformer")
    assert "not the one this was prepared for" in reason
    untouched(panel, service)


# --- an interaction breakdown: the card was the cost question, the structure's refusals remain ------------------------------------------------


def _pair_panel(panel_of, z_shift: float):
    panel, service, _ = panel_of(1)
    molecule = MoleculeModel(display_name="Ammonia borane")
    panel._chemistry_engine.set_structure_from_smiles(molecule, "N.B")
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(_pair(z_shift)), method="rdkit_etkdg"))
    panel._project.molecules.append(molecule)
    panel.set_project(panel._project)
    return panel, service, molecule


def test_the_cost_dialog_is_not_shown_because_approving_the_card_was_the_answer(panel_of, monkeypatch):
    panel, service, molecule = _pair_panel(panel_of, 0.0)
    monkeypatch.setattr(panel, "_confirm_led_cost", lambda parent, mol: pytest.fail("the card showed the cost"))
    assert panel.start_assistant_run(molecule.uuid, choice(calc_type="led"), fingerprint_of(molecule)) == ""
    assert [r["calc_type"] for r in service.requests] == ["led"]


def test_a_structure_that_is_not_two_partners_is_refused_with_the_dialogs_words(panel_of):
    panel, service, molecule = panel_of(2)
    assert panel.start_assistant_run(molecule.uuid, choice(calc_type="led"), fingerprint_of(molecule)) == TWO_PARTNERS_MESSAGE
    untouched(panel, service)


def test_partners_that_overlap_are_refused_whoever_asked(panel_of):
    panel, service, molecule = _pair_panel(panel_of, 1.5)
    reason = panel.start_assistant_run(molecule.uuid, choice(calc_type="led"), fingerprint_of(molecule))
    assert "overlap" in reason and "two separate species" in reason
    untouched(panel, service)


def test_the_dialog_the_button_shows_says_what_it_always_said(panel_of, monkeypatch):
    """`_confirm_led_cost` now reads its rules and words from the shared review; its boxes are unchanged."""
    from PySide6.QtWidgets import QMessageBox

    panel, _service, molecule = panel_of(2)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda parent, title, text: shown.append(("information", title, text))))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda parent, title, text: shown.append(("warning", title, text))))
    from openchem.chem.engine import ChemistryEngine

    mol = ChemistryEngine().mol_from_model(molecule)
    assert panel._confirm_led_cost(panel, mol) is False
    assert shown == [("information", "Two partners needed", TWO_PARTNERS_MESSAGE)]
    shown.clear()
    assert panel._confirm_led_cost(panel, _pair(1.5)) is False
    assert shown[0][:2] == ("warning", "This geometry cannot be decomposed") and "overlap" in shown[0][2]


def test_the_expensive_job_question_is_the_dialog_the_button_always_showed(panel_of, monkeypatch):
    """A job whose cost is worth a question still asks it, with the shared text and the same two buttons; the card is what makes that question unnecessary for an assistant's job."""
    from PySide6.QtWidgets import QMessageBox

    panel, _service, _molecule = panel_of(1)
    asked = []

    def question(parent, title, text, buttons, default):
        asked.append((title, text, default))
        return QMessageBox.StandardButton.Yes if len(asked) == 1 else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    big = Chem.AddHs(Chem.MolFromSmiles("c1ccc2ccccc2c1.c1ccc2ccccc2c1"))
    assert panel._confirm_led_cost(panel, big) is True
    assert panel._confirm_led_cost(panel, big) is False
    title, text, default = asked[0]
    assert title == "This calculation is expensive" and text.endswith("\n\nStart it anyway?") and "basis functions, DLPNO-CCSD(T)" in text
    assert default == QMessageBox.StandardButton.No
    assert panel._confirm_led_cost(panel, _pair(0.0)) is True and len(asked) == 2, "a modest job asks nothing"


# --- proton affinity: a fixed protocol, run on the drawing ---------------------------------------------------------------------------------------


def _pa_panel(smiles="N", conformers=False):
    """A panel whose service records proton-affinity requests (the base double records only the other kinds)."""
    panel, engine, service = _make_panel()
    requests: list[dict] = []
    service.request_proton_affinity = lambda **kw: requests.append(kw)  # type: ignore[method-assign]
    molecule = MoleculeModel(display_name=smiles)
    engine.set_structure_from_smiles(molecule, smiles)
    project = ProjectModel(name="t")
    project.molecules.append(molecule)
    panel.set_project(project)
    panel._molecule_combo.setCurrentIndex(0)
    return panel, molecule, service, requests


@pytest.fixture
def pa_panel(qapp):
    made = []

    def build(*args, **kw):
        built = _pa_panel(*args, **kw)
        made.append(built[0])
        return built

    yield build
    for panel in made:
        _dispose_panel(panel)


def drawing_fingerprint(panel, molecule) -> str:
    from openchem.chem.calculation_input import input_fingerprint

    return input_fingerprint(panel._chemistry_engine, molecule, "drawing")


PA = choice(calc_type="proton_affinity", method_basis="M062X def2-TZVPD")


def test_a_card_starts_proton_affinity_with_exactly_what_the_button_hands_the_service(pa_panel):
    button_panel, button_molecule, _service, by_button = pa_panel("N")
    button_panel._on_proton_affinity_clicked()
    panel, molecule, _service, by_card = pa_panel("N")
    assert panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule)) == ""
    assert len(by_button) == len(by_card) == 1
    for key in ("smiles", "calculation_input", "input_fingerprint", "structure_identity"):
        assert by_card[0][key] == by_button[0][key], key
    assert by_card[0]["molecule_uuid"] == molecule.uuid and by_card[0]["calculation_input"] == "drawing"


def test_a_card_needs_no_conformer_and_the_panel_waits_as_it_does_for_its_own(pa_panel):
    panel, molecule, _service, requests = pa_panel("N")
    assert molecule.conformers == []
    assert panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule)) == ""
    assert panel._pending_molecule_uuid == molecule.uuid and panel._status_label.text().startswith("queued -- 2 optimization")
    assert not panel._run_button.isEnabled() and not panel._proton_affinity_button.isEnabled() and panel._cancel_button.isEnabled()
    assert panel._pending_conformer_molblock == "" and panel._pending_mol is not None


def test_the_cost_dialog_is_not_shown_for_a_card_whose_base_is_outside_what_was_measured(pa_panel, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: pytest.fail("the card showed the cost")))
    panel, molecule, _service, requests = pa_panel("CCl")
    assert panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule)) == ""
    assert len(requests) == 1


def test_a_base_the_protocol_cannot_compute_is_refused_in_the_buttons_words(pa_panel):
    panel, molecule, _service, requests = pa_panel("C[N+](C)(C)C")
    reason = panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule))
    assert reason.startswith("Proton affinity does not apply:") and requests == [] and panel._pending_molecule_uuid is None


def test_a_drawing_edited_after_the_card_is_not_run(pa_panel):
    panel, molecule, _service, requests = pa_panel("N")
    before = drawing_fingerprint(panel, molecule)
    panel._chemistry_engine.set_structure_from_smiles(molecule, "CN")
    assert "edited after this was prepared" in panel.start_assistant_run(molecule.uuid, PA, before)
    assert requests == [] and panel._pending_molecule_uuid is None


def test_proton_affinity_waits_behind_a_job_the_panel_is_already_running(pa_panel):
    panel, molecule, _service, requests = pa_panel("N")
    assert panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule)) == ""
    assert "busy with another calculation" in panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule)) and len(requests) == 1


def test_proton_affinity_is_not_started_again_for_a_molecule_the_service_is_running(pa_panel):
    panel, molecule, service, requests = pa_panel("N")
    assert service._job_manager.try_start("quantum_chemistry", molecule.uuid)
    assert "already running for this molecule" in panel.start_assistant_run(molecule.uuid, PA, drawing_fingerprint(panel, molecule)) and requests == []


def test_the_panel_shows_the_molecule_a_proton_affinity_card_is_for(pa_panel):
    panel, ammonia, _service, requests = pa_panel("N")
    other = MoleculeModel(display_name="Other")
    panel._chemistry_engine.set_structure_from_smiles(other, "CCO")
    panel._project.molecules.insert(0, other)
    panel.set_project(panel._project)
    panel._molecule_combo.setCurrentIndex(0)
    assert panel._molecule_combo.currentData() == other.uuid
    assert panel.start_assistant_run(ammonia.uuid, PA, drawing_fingerprint(panel, ammonia)) == ""
    assert panel._molecule_combo.currentData() == ammonia.uuid and requests[0]["molecule_uuid"] == ammonia.uuid
