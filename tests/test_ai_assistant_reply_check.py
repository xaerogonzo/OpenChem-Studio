"""Setting the assistant's reply against what the application knows (`plugins/ai_assistant/reply_check.py`; `docs/AI_CALCULATION_BRIDGE.md`, section 28).

The sentences are the ones live models produced (`qwen2.5:14b`, section 27), so the patterns are held to what was actually said, not to what I expected to be said.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from ai_assistant.providers import AIResponse
from ai_assistant.reply_check import check_reply, claims_a_waiting_approval, unshown_numbers

sys.path.insert(0, str(Path(__file__).parent))
from test_ai_assistant_bridge import _call, _two_step, rig  # noqa: E402,F401

from PySide6.QtTest import QTest  # noqa: E402

# --- a waiting approval that is not there -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sentence", [
    "The ORCA single-point energy calculation has been set up and is awaiting your approval.",
    "A single-point energy calculation with ORCA at B3LYP def2-SVP has been prepared. The calculation is waiting for your approval.",
    "The ORCA job to calculate the NMR shielding constants for water has been prepared. A preview is on your screen, and the calculation will start only if you approve it.",
    "A preview is on the user's screen and nothing has started.",
    "Please review and approve the preview to proceed with the calculation.",
    "Approve the card to start it.",
])
def test_a_present_tense_claim_that_something_waits_is_recognised(sentence):
    assert claims_a_waiting_approval(sentence), sentence


@pytest.mark.parametrize("sentence", [
    "Water is H2O.",
    "ORCA starts only if you approve it.",
    "I can leave a card for you to approve.",
    "I cannot approve it for you.",
    "A single point gives the SCF energy at the geometry as supplied.",
    "The tool refused: orca.sp has no parameter 'basis_set'; it takes charge, multiplicity, method_basis.",
    "There is no current preview waiting for your approval for a molecular weight calculation.",
    "Nothing is awaiting your approval.",
    "The job is not waiting for approval; it was never prepared.",
    "No preview is on your screen.",
    "I haven't left a preview on your screen.",
])
def test_conditional_and_unrelated_sentences_are_not_claims(sentence):
    assert not claims_a_waiting_approval(sentence), sentence


def test_a_denial_in_one_sentence_does_not_hide_a_claim_in_the_next_or_one_after_the_denial_word():
    assert claims_a_waiting_approval("Nothing was started. A preview is waiting for your approval.")
    assert claims_a_waiting_approval("It is not the same job, but a preview is on your screen.") is False  # the denial is in the same sentence before the words: read as a denial
    assert claims_a_waiting_approval("A preview is waiting for your approval, and nothing has started.")


def test_a_claim_with_no_card_showing_is_a_finding_for_the_person_and_for_the_model():
    findings = check_reply("A preview is on your screen, waiting for your approval.", approvals_waiting=0, shown_text="", tools_offered=True)
    assert [f.kind for f in findings] == ["waiting_approval"]
    assert "no approval card is showing" in findings[0].message and "Nothing was requested" in findings[0].message
    assert "no approval card exists" in findings[0].note and "run_calculator" in findings[0].note


def test_the_same_claim_with_a_card_showing_is_not_a_finding():
    assert check_reply("A preview is on your screen, waiting for your approval.", approvals_waiting=1, shown_text="", tools_offered=True) == []


# --- a number the model was never shown -------------------------------------------------------------------------------------------------------------------------


def test_a_number_in_what_the_model_was_shown_is_supported_and_one_that_is_not_is_listed():
    shown = "Molecular weight: 18.01528 g/mol. The SCF energy is -76.3295."
    assert unshown_numbers("The weight is 18.01528 and the energy -76.3295.", shown) == []
    assert unshown_numbers("The weight is 18.01528 g/mol.", "") == ["18.01528"]


def test_honest_rounding_is_supported_and_more_precision_than_was_shown_is_not():
    shown = "mass 18.01528"
    assert unshown_numbers("18.015 and 18.02", shown) == [], "rounded to fewer places than shown"
    assert unshown_numbers("18.1", shown) == ["18.1"], "a different number, not a rounding"
    assert unshown_numbers("18.015281", shown) == ["18.015281"], "more places than the application ever showed"
    assert unshown_numbers("18.01528", "mass 18.0153") == ["18.01528"]


def test_each_unsupported_number_is_listed_once_in_the_order_it_appears():
    assert unshown_numbers("It is 4.76, or about 4.76, and 9.25.", "") == ["4.76", "9.25"]


def test_only_decimal_numbers_are_checked_and_tokens_that_merely_contain_digits_are_not_numbers():
    reply = "B3LYP with def2-SVP or 6-31G(d), pH7.4 of H2O, version 2.5.1, 3 atoms, 1024 tokens, and 2.5.1.3."
    assert unshown_numbers(reply, "") == []


def test_a_sign_is_not_part_of_the_comparison():
    assert unshown_numbers("The energy is -76.3295 Eh.", "scf 76.3295") == []
    assert unshown_numbers("The energy is 76.3295 Eh.", "scf -76.3295") == []


def test_the_models_own_earlier_words_are_not_evidence_because_only_what_it_was_shown_is_passed_in():
    # The panel passes the molecule summary, the person's messages and the tool results; the model's own replies are left out so a number invented once cannot vouch for itself.
    findings = check_reply("It is 18.01528.", approvals_waiting=0, shown_text="user: what is the weight?", tools_offered=True)
    assert [f.kind for f in findings] == ["unshown_number"]
    assert "18.01528 appears nowhere" in findings[0].message and "18.01528" in findings[0].note


def test_several_numbers_are_named_together_in_the_plural():
    findings = check_reply("Values 1.25 and 2.5.", approvals_waiting=0, shown_text="", tools_offered=True)
    assert "1.25, 2.5 appear nowhere" in findings[0].message


def test_without_tools_the_number_rule_is_not_applied_because_the_model_could_not_have_kept_it():
    assert check_reply("It is 18.01528.", approvals_waiting=0, shown_text="", tools_offered=False) == []
    # ... but a claim about the application's own state is still wrong without tools.
    assert [f.kind for f in check_reply("It is awaiting your approval.", approvals_waiting=0, shown_text="", tools_offered=False)] == ["waiting_approval"]


def test_both_findings_can_come_from_one_reply():
    findings = check_reply("The weight is 18.01528 and a preview is on your screen.", approvals_waiting=0, shown_text="", tools_offered=True)
    assert [f.kind for f in findings] == ["waiting_approval", "unshown_number"]


# --- in the panel: the check runs a moment after the reply, against the cards that are showing then ---------------------------------------------------------------


def _reply(rig, text, *, tools=True):
    """What the panel does when the loop finishes with `text`, then the time the check waits for queued cards."""
    rig.panel._shown_calculation_tools = tools
    rig.panel._on_response(AIResponse(text=text))
    QTest.qWait(700)
    rig.qapp.processEvents()


def test_a_reply_that_says_a_preview_is_waiting_when_no_card_is_showing_is_said_so_under_it_and_told_to_the_model(rig):
    _reply(rig, "The calculation has been prepared. A preview is on your screen, waiting for your approval.")
    assert rig.panel.reply_findings == ["waiting_approval"]
    assert "no approval card is showing" in rig.panel._transcript.toPlainText()
    assert any(n.startswith("[Application note] Your last reply said a preview was waiting") for n in rig.panel._notes)


def test_the_same_reply_with_a_card_showing_is_left_alone(rig):
    rig.panel._cards["card-1"] = object()  # an approval card on screen
    assert rig.panel.approvals_waiting() == 1
    _reply(rig, "A preview is on your screen, waiting for your approval.")
    assert rig.panel.reply_findings == [] and "Application check" not in rig.panel._transcript.toPlainText() and rig.panel._notes == []


def test_a_card_that_arrives_just_after_the_reply_is_not_called_missing(rig):
    """The reason the check waits: a card is built from queued events, and checking in the same instant would call a card that is about to appear a card that does not exist."""
    from PySide6.QtCore import QTimer

    rig.panel._shown_calculation_tools = True
    QTimer.singleShot(150, lambda: rig.panel._cards.__setitem__("card-1", object()))  # the card is built a moment after the reply, inside the wait
    rig.panel._on_response(AIResponse(text="A preview is on your screen, waiting for your approval."))
    QTest.qWait(900)
    rig.qapp.processEvents()
    assert rig.panel.approvals_waiting() == 1 and rig.panel.reply_findings == []


def test_a_running_job_and_a_described_only_calculator_are_not_cards_waiting_for_approval(rig):
    rig.panel._service_cards["svc"] = object()
    rig.panel._running_cards["run"] = object()
    assert rig.panel.approvals_waiting() == 0


def test_a_number_the_model_was_never_shown_is_said_so_and_one_a_tool_returned_is_not(rig):
    rig.panel._shown_system_context = "Selected molecule: water"
    _reply(rig, "The molecular weight of water is 18.01528 g/mol.")
    assert rig.panel.reply_findings == ["unshown_number"] and "18.01528 appears nowhere" in rig.panel._transcript.toPlainText()
    assert any("State a value only if a tool result contains it" in n for n in rig.panel._notes)

    rig.panel.reply_findings.clear()
    rig.panel._notes.clear()
    rig.panel._shown_tool_results.append('{"ok": true, "value": 18.01528, "unit": "g/mol"}')
    _reply(rig, "The molecular weight of water is 18.015 g/mol.")  # rounded from what a tool returned
    assert rig.panel.reply_findings == [] and rig.panel._notes == []


def test_the_models_own_earlier_replies_do_not_vouch_for_a_number(rig):
    from ai_assistant.providers import AIMessage

    rig.panel._history.append(AIMessage(role="assistant", content="It is 18.01528."))
    _reply(rig, "As I said, 18.01528.")
    assert rig.panel.reply_findings == ["unshown_number"]


def test_what_a_person_said_counts_as_shown(rig):
    from ai_assistant.providers import AIMessage

    rig.panel._history.append(AIMessage(role="user", content="Use a threshold of 0.75 please."))
    _reply(rig, "With a threshold of 0.75 the answer changes.")
    assert rig.panel.reply_findings == []


def test_a_tool_result_read_in_an_earlier_turn_still_counts_in_a_later_one(rig):
    """The loop's messages are not kept in the panel's history, so a number read in turn 1 and repeated in turn 2 would look invented unless the results are kept."""
    from ai_assistant.providers import AIMessage

    provider = _two_step([_call("read_results")], final="Done.")
    thread, _box = rig.loop(provider, rig.bridge())
    rig.settle(thread)
    assert rig.panel._shown_tool_results, "the worker thread records what each tool returned"
    rig.panel._shown_tool_results.append('energy -76.3295')
    rig.panel._history.append(AIMessage(role="user", content="and the energy?"))
    _reply(rig, "The energy is -76.3295.")
    assert rig.panel.reply_findings == []


def test_without_calculator_tools_a_number_is_not_checked_but_a_false_card_claim_still_is(rig):
    _reply(rig, "The weight is 18.01528.", tools=False)
    assert rig.panel.reply_findings == []
    _reply(rig, "It is awaiting your approval.", tools=False)
    assert rig.panel.reply_findings == ["waiting_approval"]


def test_the_line_the_check_adds_is_scrolled_into_view_in_a_long_transcript(rig):
    """Found by looking at the real window: the check was in the transcript and below what could be seen."""
    rig.panel.resize(400, 300)
    rig.panel.show()
    for i in range(60):
        rig.panel._append_transcript("You", f"filler line {i}")
    rig.panel._transcript.verticalScrollBar().setValue(0)
    _reply(rig, "The weight is 18.01528.")
    bar = rig.panel._transcript.verticalScrollBar()
    assert rig.panel.reply_findings == ["unshown_number"] and bar.maximum() > 0 and bar.value() == bar.maximum()


def test_more_places_than_were_shown_is_flagged_even_when_the_rounded_values_coincide():
    assert unshown_numbers("18.00", "mass 18.0") == ["18.00"], "two places were never shown, only one"
    assert unshown_numbers("18.0", "mass 18.00") == [], "fewer places than shown is a rounding"


def test_every_kind_of_approval_card_counts_as_waiting_and_nothing_else_does(rig):
    panel = rig.panel
    assert panel.approvals_waiting() == 0
    panel._cards["run"] = object()
    panel._score_cards["score"] = object()
    panel._synthesis_cards["search"] = object()
    assert panel.approvals_waiting() == 3
    for cards in (panel._cards, panel._score_cards, panel._synthesis_cards):
        cards.clear()
        assert panel.approvals_waiting() == {id(panel._cards): 2, id(panel._score_cards): 1, id(panel._synthesis_cards): 0}[id(cards)]
