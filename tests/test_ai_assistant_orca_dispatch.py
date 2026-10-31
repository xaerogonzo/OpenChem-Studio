"""The assistant asks for an ORCA job; a person approves it on a card; the job starts by the Run button's rules; the model is told how it ended (dispatch, step 2).

Everything here is the real host, the real assistant plugin and its real tool loop. Only the Quantum Chemistry panel is a recording stand-in (`QuantumStarter`), so that no ORCA runs; the panel's own
half is `tests/test_quantum_start_assistant_run.py` and the host's `tests/test_calculation_host_orca.py`. What is asserted here is what a person sees and what a model is told: the card, that nothing
starts before Approve, the ledger's words at each stage, and the note that goes ahead of the next message.
"""

from __future__ import annotations

import json
import shutil
import sys

import pytest
from test_ai_assistant_bridge import _call, _Rig, _tool_message, _two_step
from test_calculation_host_orca import _Starter, completed

from openchem.domain.quantum_chemistry_run import RunStatus
from openchem.domain.run_lifecycle import RunState


@pytest.fixture
def rig(qapp, tmp_path, monkeypatch):
    rig = _Rig(qapp, tmp_path, held=True)
    rig.starter = _Starter()
    rig.world.host.set_quantum_starter(rig.starter)
    rig.world.add_conformer(rig.world.molecule)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    fake = tmp_path / "orca.exe"
    fake.write_text("not really")
    rig.world.services.quantum_chemistry_service._settings.set("orca/executable_path", str(fake))
    return rig


def ask(rig, calculator_id="orca.sp", **parameters) -> dict:
    """The model calls run_calculator, on a worker thread, as the tool loop would; returns the reply it reads."""
    provider = _two_step([_call("run_calculator", calculator_id=calculator_id, parameters=parameters)])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    rig.qapp.processEvents()
    return json.loads(_tool_message(provider)[0].content)


def preparation_of(rig, run_id):
    return rig.world.host._ledger.get(run_id)


# --- the card ---------------------------------------------------------------------------------------------------------------------------------


def test_asking_for_an_orca_job_leaves_a_card_and_starts_nothing(rig):
    reply = ask(rig, "orca.opt", method_basis="PBE0 def2-TZVP", charge=1, multiplicity=2)
    assert reply["state"] == "awaiting_approval" and reply["started"] is False and "ORCA runs for minutes to hours" in reply["why_approval_is_needed"]
    assert "do not call run_calculator" in reply["message"] and "preview_only" not in json.dumps(reply)

    assert rig.starter.calls == [] and rig.world.pool.tasks == []
    (run_id,) = rig.panel.pending_run_ids()
    assert run_id == reply["run_id"] and rig.panel.service_preview_keys() == []
    card = rig.panel._cards[run_id]
    assert card.approve_button.text() == "Approve" and card.cancel_button.text() == "Cancel"
    assert any("waiting for your approval" in line for line in rig.panel.ledger_lines())
    text = "\n".join(preparation_of(rig, run_id).preview)
    assert "PBE0 def2-TZVP" in text and "charge=1" in text and "multiplicity=2" in text


def test_the_model_is_told_which_orca_calculators_it_can_ask_for_and_which_it_cannot(rig):
    provider = _two_step([_call("find_calculators", query="orca", limit=30)])
    thread, _ = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    routes = {c["calculator_id"]: c["route"] for c in json.loads(_tool_message(provider)[0].content)["calculators"]}
    assert routes["orca.sp"] == routes["orca.led"] == routes["orca.proton_affinity"] == "needs_approval"
    assert routes["orca.fukui"] == routes["orca.bond_dissociation_enthalpy"] == routes["orca.tautomer_distribution"] == "preview_only"


def test_a_job_that_cannot_be_started_here_is_still_only_described(rig):
    reply = ask(rig, "orca.bond_dissociation_enthalpy")
    assert reply["state"] == "preview_only" and rig.panel.pending_run_ids() == [] and len(rig.panel.service_preview_keys()) == 1


def test_a_computer_without_orca_gets_the_reason_and_no_card(rig):
    rig.world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    reply = ask(rig)
    assert reply["ok"] is False and reply["problems"][0]["code"] == "not_ready" and "External Tools" in reply["problems"][0]["message"]
    assert rig.panel.pending_run_ids() == [] and any("not started" in line for line in rig.panel.ledger_lines())


def test_a_setting_the_calculator_does_not_take_is_refused_and_no_card_is_left(rig):
    reply = ask(rig, "orca.sp", method_basis="not a method")
    assert reply["problems"][0]["code"] == "not_a_choice" and rig.panel.pending_run_ids() == []


# --- Approve ----------------------------------------------------------------------------------------------------------------------------------


def test_only_the_users_approve_hands_the_job_to_the_panel(rig):
    reply = ask(rig, "orca.nmr", charge=-1)
    run_id = reply["run_id"]
    for _ in range(3):
        rig.qapp.processEvents()
    assert rig.starter.calls == []

    rig.panel._cards[run_id].approve_button.click()
    [(molecule_uuid, choice, fingerprint)] = rig.starter.calls
    assert molecule_uuid == rig.world.molecule.uuid and (choice.calc_type, choice.charge) == ("nmr", -1)
    assert fingerprint == preparation_of(rig, run_id).input_fingerprint
    assert rig.panel.pending_run_ids() == [] and rig.world.host.state_of(run_id) is RunState.RUNNING
    assert any("running in the Quantum Chemistry panel" in line for line in rig.panel.ledger_lines())
    assert rig.panel._notes == [], "the model is told when it ends, not when it starts"


def test_when_the_job_ends_the_ledger_and_the_note_say_how_and_where_to_read_it(rig):
    run_id = ask(rig)["run_id"]
    rig.panel._cards[run_id].approve_button.click()
    completed(rig.world, preparation_of(rig, run_id), run_id="orca-run-7")
    assert any("ORCA finished it" in line for line in rig.panel.ledger_lines())
    (note,) = rig.panel._notes
    assert note.startswith("[Application note] The ORCA job you asked for, orca.sp on Aspirin") and run_id in note
    assert "ended 'completed'" in note and "orca-run-7" in note and "read_quantum_runs" in note and "State no value you have not read." in note


def test_the_note_goes_ahead_of_the_users_next_message(rig):
    run_id = ask(rig)["run_id"]
    rig.panel._cards[run_id].approve_button.click()
    completed(rig.world, preparation_of(rig, run_id))
    rig.panel._input.setPlainText("what did it find?")
    rig.panel._history.clear()
    sent = {}
    module = sys.modules[type(rig.panel).__module__]
    original = module.run_async
    module.run_async = lambda func, *a, **k: sent.update(called=True)
    try:
        rig.panel._on_send_clicked()
    finally:
        module.run_async = original
    assert sent.get("called") and rig.panel._notes == []
    last = rig.panel._history[-1]
    assert last.role == "user" and last.content.startswith("[Application note] The ORCA job you asked for") and last.content.endswith("what did it find?")


@pytest.mark.parametrize("status, ledger, note", [
    (RunStatus.COMPLETED_WITH_WARNINGS, "ORCA finished it", "reported 1 warning(s)"),
    (RunStatus.FAILED, "failed", "did not produce a result"),
    (RunStatus.CANCELLED, "cancelled while running", "cancelled before it finished"),
])
def test_a_job_that_did_not_finish_cleanly_is_told_as_it_ended(rig, status, ledger, note):
    run_id = ask(rig)["run_id"]
    rig.panel._cards[run_id].approve_button.click()
    completed(rig.world, preparation_of(rig, run_id), status=status, warnings=["w"])
    assert any(ledger in line for line in rig.panel.ledger_lines())
    assert note in rig.panel._notes[0] and "ended '" in rig.panel._notes[0]


def test_the_panels_refusal_reaches_the_person_and_the_model_in_its_own_words(rig):
    rig.starter.answer = "This panel is busy with another calculation. Nothing was started; wait for it to finish (or cancel it) and ask again."
    run_id = ask(rig)["run_id"]
    rig.panel._cards[run_id].approve_button.click()
    assert rig.world.host.state_of(run_id) is RunState.REFUSED
    assert any("not started: the panel's rules declined it" in line and "busy with another calculation" in line for line in rig.panel.ledger_lines())
    assert "busy with another calculation" in rig.panel._notes[0] and "ended 'refused'" in rig.panel._notes[0]


def test_cancelling_the_card_starts_nothing_and_the_model_is_told(rig):
    run_id = ask(rig)["run_id"]
    rig.panel._cards[run_id].cancel_button.click()
    rig.qapp.processEvents()
    assert rig.starter.calls == [] and rig.world.host.state_of(run_id) is RunState.CANCELLED
    assert any("cancelled; nothing was started" in line for line in rig.panel.ledger_lines())
    assert "ORCA job you asked for" in rig.panel._notes[0] and "cancelled" in rig.panel._notes[0]


def test_approving_after_the_drawing_was_edited_hands_nothing_over(rig):
    run_id = ask(rig)["run_id"]
    rig.world.engine.set_structure_from_smiles(rig.world.molecule, "CCO")
    rig.panel._cards[run_id].approve_button.click()
    assert rig.starter.calls == [] and rig.world.host.state_of(run_id) is RunState.INVALIDATED
    assert any("withdrawn" in line for line in rig.panel.ledger_lines()) and "invalidated" in rig.panel._notes[0]


# --- proton affinity: a card for a fixed protocol -----------------------------------------------------------------------------------------------


def test_proton_affinity_is_a_card_for_a_molecule_with_no_conformer_and_the_model_is_told_how_it_ended(rig):
    ammonia = rig.world.add("N", "Ammonia")
    assert ammonia.conformers == []
    reply = ask(rig, "orca.proton_affinity")
    assert reply["state"] == "awaiting_approval" and rig.starter.calls == []
    run_id = reply["run_id"]
    assert "2 ORCA geometry optimizations" in " ".join(preparation_of(rig, run_id).preview)

    rig.panel._cards[run_id].approve_button.click()
    [(molecule_uuid, choice, _fingerprint)] = rig.starter.calls
    assert molecule_uuid == ammonia.uuid and choice.calc_type == "proton_affinity"
    assert any("running in the Quantum Chemistry panel" in line for line in rig.panel.ledger_lines()) and rig.panel._notes == []

    completed(rig.world, preparation_of(rig, run_id), calc_type="proton_affinity", calculation_input="drawing")
    assert any("ORCA finished it" in line for line in rig.panel.ledger_lines())
    assert "orca.proton_affinity on Ammonia" in rig.panel._notes[0] and "read_quantum_runs" in rig.panel._notes[0]


def test_a_charged_base_gets_the_reason_and_no_card(rig):
    rig.world.add("C[N+](C)(C)C", "Tetramethylammonium")
    reply = ask(rig, "orca.proton_affinity")
    assert reply["problems"][0]["code"] == "invalid_structure" and "does not apply" in reply["problems"][0]["message"] and rig.panel.pending_run_ids() == []


# --- the tools cannot do what only the button can ----------------------------------------------------------------------------------------------


def test_the_tools_hold_no_way_to_approve_or_start(rig):
    bridge = rig.bridge()
    calculations = bridge._calculations
    for name in ("approve", "cancel", "pending", "set_quantum_starter", "start_assistant_run"):
        assert not hasattr(calculations, name) and not hasattr(bridge, name), name
    assert not hasattr(rig.world.host, "start_assistant_run"), "the host hands over; only the panel starts"
