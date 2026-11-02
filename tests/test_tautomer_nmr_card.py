"""The assistant asking for NMR on the tautomers of a finished tautomer distribution (`orca.tautomer_nmr`; `docs/AI_CALCULATION_BRIDGE.md`, section 22).

Three layers: the shared rules (`prepare_tautomer_nmr`, what the button and a card both ask), the host (a card drawn from the frozen turn's runs, bound to the run it names, ended by the NMR run's record) and
the Quantum Chemistry panel (a start that applies the same rules to the stored run and the drawing as they are at Approve). The service is a recording double; the distribution is the real keto and enol
fixture of the averaging tests, so the stored geometries and populations are real data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_calculation_host_orca import _Starter, approve, completed, prepare, world  # noqa: E402,F401
from test_quantum_chemistry_panel import _tautomer_distribution_run  # noqa: E402
from test_tautomer_nmr_average import PARENT, _build  # noqa: E402
from test_tautomer_nmr_panel import setup  # noqa: E402,F401

from openchem.chem.quantum_run_request import (  # noqa: E402
    PreparedTautomerNmr,
    RunChoice,
    RunRefusal,
    prepare_tautomer_nmr,
    start_tautomer_nmr,
)
from openchem.domain.calculation_bridge import ProblemCode  # noqa: E402
from openchem.domain.quantum_chemistry_run import RunStatus  # noqa: E402
from openchem.domain.run_lifecycle import RunState  # noqa: E402

NMR = "orca.tautomer_nmr"


# --- the shared rules --------------------------------------------------------------------------------------------------------------------------


def test_the_tautomers_of_a_stored_distribution_are_the_jobs_and_the_text_says_where_they_start():
    _nmr, distribution, _ = _build()
    prepared = prepare_tautomer_nmr(distribution, PARENT, "HF STO-3G")
    assert isinstance(prepared, PreparedTautomerNmr) and prepared.jobs == len(prepared.targets) >= 2 and prepared.problems == ()
    text = prepared.card_text()
    assert f"run {PARENT}" in text and "no structure is embedded or optimized again" in text and "representative conformer" in text
    assert f"{prepared.jobs} real ORCA NMR calculation(s) for {len(prepared.targets)} tautomer(s) at HF STO-3G" in text
    assert "cached reference" in text and "\n" not in text
    assert prepared.queued_text() == f"queued -- {prepared.jobs} NMR calculation(s) for {len(prepared.targets)} tautomer(s)"


def test_no_distribution_or_no_method_is_refused_in_the_buttons_words():
    _nmr, distribution, _ = _build()
    assert prepare_tautomer_nmr(None, PARENT, "HF STO-3G") == RunRefusal("Select a tautomer distribution run first.")
    assert prepare_tautomer_nmr(distribution, PARENT, "") == RunRefusal("Enter a method/basis (e.g. 'B3LYP def2-SVP').")


def test_a_distribution_with_no_stored_geometry_is_refused_with_the_reason():
    _nmr, distribution, _ = _build(store_geometry=False)
    refusal = prepare_tautomer_nmr(distribution, PARENT, "HF STO-3G")
    assert isinstance(refusal, RunRefusal) and refusal.message.startswith("No tautomer can be run: ") and "rerun the tautomer distribution" in refusal.message


def test_what_cannot_be_run_is_listed_and_never_dropped_silently():
    _nmr, distribution, _ = _build()
    prepared = prepare_tautomer_nmr(distribution, PARENT, "HF STO-3G")
    with_problem = PreparedTautomerNmr(prepared.parent_run_id, prepared.method_basis, prepared.per_conformer, prepared.targets, ("T9: no candidate succeeded",))
    assert "Left out: T9: no candidate succeeded" in with_problem.question() and "Left out: T9" in with_problem.card_text()


def test_starting_hands_the_service_what_the_button_always_handed_it():
    _nmr, distribution, _ = _build()
    prepared = prepare_tautomer_nmr(distribution, PARENT, "HF STO-3G")
    seen = []

    class Service:
        def request_tautomer_nmr(self, **kwargs):
            seen.append(kwargs)

    class Molecule:
        uuid = "mol"

    start_tautomer_nmr(Service(), Molecule(), prepared, 1, 2)
    [call] = seen
    assert call["targets"] == list(prepared.targets) and call["molecule_uuid"] == "mol" and (call["charge"], call["multiplicity"]) == (1, 2)
    assert call["method_basis"] == "HF STO-3G" and call["per_conformer"] is False and call["parent_run_id"] == PARENT and call["skipped"] == ()


# --- the host: the card ------------------------------------------------------------------------------------------------------------------------


def record_distribution(world, run_id="dist-run-1", *, status=RunStatus.COMPLETED, started=1000.0, store_geometry=True, with_result=True):
    """A finished (or not) tautomer distribution in the project's own run store, for the molecule the host holds."""
    _nmr, distribution, _ = _build(store_geometry=store_geometry)
    run = _tautomer_distribution_run(world.molecule.uuid, distribution)
    run.run_id, run.status, run.started_at, run.completed_at = run_id, status, started, started + 5.0
    if not with_result:
        run.results.clear()
        run.output_status.clear()
    world.services.result_store_service.record_quantum_chemistry_run(run)
    return run


def test_without_a_finished_distribution_the_card_says_what_to_run_first(world):
    result = prepare(world, NMR)
    assert result.preparation is None
    [problem] = result.problems
    assert problem.code is ProblemCode.NEEDS_INPUT and problem.parameter == "distribution_run_id" and "run orca.tautomer_distribution first" in problem.message
    assert world.starter.calls == []


@pytest.mark.parametrize("status, with_result", [(RunStatus.FAILED, True), (RunStatus.CANCELLED, True), (RunStatus.COMPLETED, False)])
def test_a_distribution_that_did_not_finish_or_holds_no_result_is_not_one_to_start_from(world, status, with_result):
    record_distribution(world, status=status, with_result=with_result)
    [problem] = prepare(world, NMR).problems
    assert problem.code is ProblemCode.NEEDS_INPUT and "no finished tautomer distribution" in problem.message


def test_the_card_names_the_run_the_tautomers_and_the_jobs_and_starts_nothing(world):
    record_distribution(world)
    result = prepare(world, NMR)
    preparation = result.preparation
    assert preparation is not None and preparation.parameters["distribution_run_id"] == "dist-run-1"
    text = "\n".join(preparation.preview)
    assert "What it would cost (approving accepts it)" in text and "run dist-run-1" in text and "real ORCA NMR calculation(s) for 2 tautomer(s)" in text
    assert "Tautomer NMR button" in text and "stored tautomer distribution" in text and "every structure is embedded fresh" not in text
    assert world.starter.calls == [] and world.host.state_of(preparation.run_id) is RunState.PREVIEWED
    assert preparation.calculation_input == "drawing" and preparation.drawing_fingerprint == ""


def test_the_newest_finished_distribution_is_the_one_used_unless_a_run_is_named(world):
    record_distribution(world, "old", started=100.0)
    record_distribution(world, "new", started=900.0)
    assert prepare(world, NMR).preparation.parameters["distribution_run_id"] == "new"
    named = prepare(world, NMR, {"distribution_run_id": "old"}).preparation
    assert named.parameters["distribution_run_id"] == "old" and "run old" in "\n".join(named.preview)


def test_a_run_named_that_is_not_a_finished_distribution_of_this_molecule_is_refused_by_name(world):
    record_distribution(world, "real")
    [problem] = prepare(world, NMR, {"distribution_run_id": "other"}).problems
    assert problem.code is ProblemCode.NEEDS_INPUT and "'other' is not a finished tautomer distribution" in problem.message


def test_a_distribution_with_no_stored_geometries_is_refused_on_the_card(world):
    record_distribution(world, store_geometry=False)
    [problem] = prepare(world, NMR).problems
    assert problem.code is ProblemCode.NEEDS_INPUT and "No tautomer can be run" in problem.message


def test_the_settings_are_validated_like_any_cards(world):
    record_distribution(world)
    [problem] = prepare(world, NMR, {"method_basis": "made up"}).problems
    assert problem.code is ProblemCode.NOT_A_CHOICE


def test_no_orca_is_not_ready_and_says_where_to_set_it_up(world, monkeypatch):
    record_distribution(world)
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    monkeypatch.setattr("shutil.which", lambda name: None)
    [problem] = prepare(world, NMR).problems
    assert problem.code is ProblemCode.NOT_READY and "ORCA" in problem.message


# --- the host: approving and ending ------------------------------------------------------------------------------------------------------------


def test_approving_hands_the_panel_the_settings_and_the_run_the_card_named(world):
    record_distribution(world)
    preparation = prepare(world, NMR, {"method_basis": "PBE0 def2-TZVP"}).preparation
    assert approve(world, preparation.run_id) is RunState.RUNNING
    [(molecule_uuid, choice, fingerprint)] = world.starter.calls
    assert molecule_uuid == world.molecule.uuid and choice.calc_type == "tautomer_nmr" and choice.source_run_id == "dist-run-1"
    assert (choice.method_basis, choice.charge, choice.multiplicity) == ("PBE0 def2-TZVP", 0, 1) and fingerprint == preparation.input_fingerprint


def test_the_run_ends_on_the_nmr_run_record_which_carries_no_fingerprint(world):
    record_distribution(world)
    preparation = prepare(world, NMR).preparation
    approve(world, preparation.run_id)
    completed(world, preparation, calc_type="tautomer_nmr", calculation_input="", input_fingerprint="", status=RunStatus.COMPLETED)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED] and world.host._quantum_inflight == {}


def test_a_distribution_record_does_not_end_a_tautomer_nmr_job(world):
    record_distribution(world)
    preparation = prepare(world, NMR).preparation
    approve(world, preparation.run_id)
    completed(world, preparation, calc_type="tautomer_distribution", calculation_input="", input_fingerprint="", status=RunStatus.COMPLETED)
    assert world.outcomes == [] and world.host.state_of(preparation.run_id) is RunState.RUNNING


def test_editing_the_drawing_after_the_card_withdraws_it(world):
    record_distribution(world)
    preparation = prepare(world, NMR).preparation
    world.engine.set_structure_from_smiles(world.molecule, "CCC(C)=O")
    assert approve(world, preparation.run_id) is RunState.INVALIDATED and world.starter.calls == []


def test_a_running_job_can_be_stopped_from_its_card(world):
    record_distribution(world)
    preparation = prepare(world, NMR).preparation
    approve(world, preparation.run_id)
    assert world.host.stop(preparation.run_id) is True and world.starter.stopped == [world.molecule.uuid]


# --- the panel: the same rules at Approve ------------------------------------------------------------------------------------------------------


def choice_for(run_id="dist-run-1", method="HF STO-3G") -> RunChoice:
    return RunChoice(calc_type="tautomer_nmr", method_basis=method, charge=0, multiplicity=1, source_run_id=run_id)


def drawing_fp(panel, molecule) -> str:
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import DRAWING

    return input_fingerprint(panel._chemistry_engine, molecule, DRAWING)


def test_the_panel_starts_nmr_on_the_stored_distribution_with_the_cards_settings(setup):
    panel, _bus, service, molecule, _run, _nmr, distribution = setup
    reason = panel.start_assistant_run(molecule.uuid, choice_for(PARENT, "PBE0 def2-TZVP"), drawing_fp(panel, molecule))
    assert reason == ""
    [request] = service.tautomer_nmr_requests
    assert request["method_basis"] == "PBE0 def2-TZVP" and request["parent_run_id"] == PARENT and request["molecule_uuid"] == molecule.uuid
    assert request["per_conformer"] is False and len(request["targets"]) >= 2 and request["skipped"] == ()
    assert panel._pending_molecule_uuid == molecule.uuid and panel._tautomer_nmr_distribution is distribution
    assert not panel._run_button.isEnabled() and not panel._tautomer_nmr_button.isEnabled() and panel._cancel_button.isEnabled()
    assert panel._status_label.text().startswith("queued -- ") and "NMR calculation(s)" in panel._status_label.text()


def test_the_panel_shows_no_dialog_for_a_card_the_card_was_the_cost_question(setup, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    panel, _bus, service, molecule, *_ = setup
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: pytest.fail("the card showed the cost")))
    assert panel.start_assistant_run(molecule.uuid, choice_for(PARENT), drawing_fp(panel, molecule)) == "" and len(service.tautomer_nmr_requests) == 1


def test_a_run_that_is_gone_or_holds_no_distribution_starts_nothing(setup):
    panel, _bus, service, molecule, *_ = setup
    reason = panel.start_assistant_run(molecule.uuid, choice_for("no-such-run"), drawing_fp(panel, molecule))
    assert reason == "Select a tautomer distribution run first." and service.tautomer_nmr_requests == [] and panel._pending_molecule_uuid is None


def test_a_blank_method_is_refused_in_the_buttons_words(setup):
    panel, _bus, service, molecule, *_ = setup
    reason = panel.start_assistant_run(molecule.uuid, choice_for(PARENT, "  "), drawing_fp(panel, molecule))
    assert reason == "Enter a method/basis (e.g. 'B3LYP def2-SVP')." and service.tautomer_nmr_requests == []


def test_a_drawing_edited_after_the_card_starts_nothing(setup):
    panel, _bus, service, molecule, *_ = setup
    reason = panel.start_assistant_run(molecule.uuid, choice_for(PARENT), "not-the-fingerprint-now")
    assert "edited after this was prepared" in reason and service.tautomer_nmr_requests == [] and panel._pending_molecule_uuid is None


def test_the_panel_waits_behind_a_job_it_is_already_running(setup):
    panel, _bus, service, molecule, *_ = setup
    assert panel.start_assistant_run(molecule.uuid, choice_for(PARENT), drawing_fp(panel, molecule)) == ""
    assert "busy with another calculation" in panel.start_assistant_run(molecule.uuid, choice_for(PARENT), drawing_fp(panel, molecule))
    assert len(service.tautomer_nmr_requests) == 1


def test_a_card_stops_through_the_same_service_call_as_the_cancel_button(setup, monkeypatch):
    panel, _bus, service, molecule, *_ = setup
    cancelled = []
    monkeypatch.setattr(service, "has_active_job", lambda uuid: uuid == molecule.uuid)
    monkeypatch.setattr(service, "cancel", cancelled.append)
    panel.start_assistant_run(molecule.uuid, choice_for(PARENT), drawing_fp(panel, molecule))
    assert panel.cancel_assistant_run(molecule.uuid) is True and cancelled == [molecule.uuid]



def test_the_card_shows_the_run_it_resolved_in_its_settings_and_not_a_blank(world):
    record_distribution(world)
    text = "\n".join(prepare(world, NMR).preparation.preview)
    assert "distribution_run_id='dist-run-1'" in text and "distribution_run_id=''" not in text


def test_what_could_not_be_run_is_handed_to_the_service_as_skipped():
    _nmr, distribution, _ = _build()
    prepared = prepare_tautomer_nmr(distribution, PARENT, "HF STO-3G")
    with_problem = PreparedTautomerNmr(prepared.parent_run_id, prepared.method_basis, prepared.per_conformer, prepared.targets, ("T9: no candidate succeeded",))
    seen = []

    class Service:
        def request_tautomer_nmr(self, **kwargs):
            seen.append(kwargs)

    class Molecule:
        uuid = "mol"

    start_tautomer_nmr(Service(), Molecule(), with_problem, 0, 1)
    assert seen[0]["skipped"] == ("T9: no candidate succeeded",)


def test_the_card_says_it_starts_from_the_stored_distribution_by_the_tautomer_nmr_buttons_rules(world):
    record_distribution(world)
    text = "\n".join(prepare(world, NMR).preparation.preview)
    assert "It starts from the stored tautomer distribution, by the same rules as the Quantum Chemistry panel's Tautomer NMR button, and shows in that panel while it runs" in text


def test_the_panel_hands_the_service_the_cards_charge_and_multiplicity(setup):
    panel, _bus, service, molecule, *_ = setup
    odd = RunChoice(calc_type="tautomer_nmr", method_basis="HF STO-3G", charge=1, multiplicity=2, source_run_id=PARENT)
    assert panel.start_assistant_run(molecule.uuid, odd, drawing_fp(panel, molecule)) == ""
    assert (service.tautomer_nmr_requests[0]["charge"], service.tautomer_nmr_requests[0]["multiplicity"]) == (1, 2)
