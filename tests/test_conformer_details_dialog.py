"""The generation funnel, shown to the user, from provenance alone.

Every count here was already being recorded by `ConformerService` and
displayed to nobody. The row that motivated the dialog is `Distinct`
against `Returned`: a run that finds 12 distinct conformers and hands back
10 is the requested cap doing its job, but nothing on screen said so once
the status line had scrolled away.

The cases that need guarding are the ones where provenance is INCOMPLETE,
because a dialog that fills gaps with plausible numbers is worse than the
blankness it replaces.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel

from openchem.domain.common import Provenance
from openchem.domain.conformer import ConformerModel
from openchem.ui.dialogs.conformer_details_dialog import ConformerDetailsDialog

import conftest


def _conformer(**parameters) -> ConformerModel:
    return ConformerModel(
        molblock="",
        energy=-1.0,
        method="rdkit",
        timestamp=0.0,
        provenance=Provenance(created_by="core", method="rdkit", parameters=parameters),
    )


def _shown(dialog: ConformerDetailsDialog) -> str:
    """Everything the dialog puts on screen, as one string.

    Asks what it SHOWS rather than how it stores it -- the same direction
    `tests/test_empty_states.py` walks, and what lets one guard cover a
    form row, a note and an absence.
    """
    return "\n".join(label.text() for label in dialog.findChildren(QLabel))


def _dispose(dialog) -> None:
    """A widget a test walks away from is destroyed at whatever arbitrary
    later moment the collector runs -- inside an unrelated test, from
    inside Qt's event dispatch. Per widget, never the global form."""
    conftest.dispose(dialog)


def test_the_full_funnel_is_shown(qapp):
    dialog = ConformerDetailsDialog(
        _conformer(
            conformers_attempted=50,
            conformers_embedded=50,
            conformers_converged=48,
            conformers_distinct=12,
            conformers_returned=10,
            num_conformers=10,
            embedding_failures=0,
            convergence_failures=2,
        )
    )
    try:
        shown = _shown(dialog)
        for stage in ("Embeddings attempted", "Successfully embedded", "Converged"):
            assert stage in shown
        assert "Distinct after production filtering" in shown
        assert "Returned" in shown
        # A non-zero failure is worth a row; see below for the zero case.
        assert "Failed to converge" in shown
        assert "2" in shown
    finally:
        _dispose(dialog)


def test_the_distinct_row_says_what_it_is_a_count_of(qapp):
    """Bare "Distinct: 12" beside a viewer showing 10 invites the reader to
    guess which number is the conformers they have."""
    dialog = ConformerDetailsDialog(_conformer(conformers_distinct=12))
    try:
        assert "Distinct after production filtering" in _shown(dialog)
    finally:
        _dispose(dialog)


def test_truncation_is_named_when_the_cap_is_demonstrably_the_reason(qapp):
    dialog = ConformerDetailsDialog(
        _conformer(conformers_distinct=12, conformers_returned=10, num_conformers=10)
    )
    try:
        shown = _shown(dialog)
        assert "2 more distinct conformers were found and not returned" in shown
        assert "keep 10" in shown
    finally:
        _dispose(dialog)


def test_a_shortfall_that_is_not_the_cap_is_not_blamed_on_the_cap(qapp):
    """The mechanism is not inferred from the residual.

    Returned below distinct is necessary and NOT sufficient: if the run
    came back with fewer than it was asked for, something other than the
    cap removed them, and saying "the limit did this" would be inventing a
    cause from a subtraction. This project has paid for that once already.
    """
    dialog = ConformerDetailsDialog(
        _conformer(conformers_distinct=12, conformers_returned=8, num_conformers=10)
    )
    try:
        assert "not returned" not in _shown(dialog)
    finally:
        _dispose(dialog)


def test_no_truncation_note_when_nothing_was_truncated(qapp):
    dialog = ConformerDetailsDialog(
        _conformer(conformers_distinct=4, conformers_returned=4, num_conformers=10)
    )
    try:
        assert "not returned" not in _shown(dialog)
    finally:
        _dispose(dialog)


def test_old_provenance_does_not_get_a_returned_count_invented_for_it(qapp):
    """**The case this dialog is most able to get wrong.**

    A run predating `conformers_returned` still records `distinct` and the
    cap, and `min(distinct, cap)` would in fact reproduce the number for
    every run the current code writes. It is still refused: nothing says
    which version of the service produced an old record, so the formula
    would be a claim about code that cannot be inspected. Show what was
    recorded, name what was not, invent nothing.
    """
    dialog = ConformerDetailsDialog(
        _conformer(conformers_distinct=12, num_conformers=10, conformers_embedded=50)
    )
    try:
        shown = _shown(dialog)
        assert "Distinct after production filtering" in shown
        # No Returned row, no truncation sentence, and no "10" derived
        # from min(12, 10).
        rows = dialog.findChild(QFormLayout)
        labels = [rows.itemAt(i, QFormLayout.ItemRole.LabelRole) for i in range(rows.rowCount())]
        captions = [item.widget().text() for item in labels if item is not None]
        assert not any(caption.startswith("Returned") for caption in captions)
        assert "not returned" not in shown
        # And it says the stage was not recorded rather than leaving a gap.
        assert "predates" in shown and "Returned" in shown
    finally:
        _dispose(dialog)


def test_a_conformer_with_no_generation_history_fabricates_nothing(qapp):
    """An imported conformer was not generated here and has no funnel."""
    for conformer in (None, ConformerModel(molblock="", method="import", timestamp=0.0)):
        dialog = ConformerDetailsDialog(conformer)
        try:
            shown = _shown(dialog)
            assert "No generation details were recorded" in shown
            assert "Embeddings attempted" not in shown
        finally:
            _dispose(dialog)


# --- how the search ended ----------------------------------------------------
#
# A count on its own reads as a failure. "8 distinct, search plateau after 9
# batches" is a statement about the sampling, and the difference is the whole
# reason this dialog exists.


def test_a_plateau_is_never_called_convergence():
    """**THE WORD MATTERS MOST WHERE THE READER IS ALREADY DOUBTFUL.** They
    opened this dialog because the count looked low; telling them the search
    "converged" implies the space was enumerated, which nothing here did."""
    note = ConformerDetailsDialog._stop_note(
        {"stop_reason": "plateau", "batches_without_new_candidates": 2}
    )

    assert "plateau" in note.lower()
    assert "converg" not in note.lower()
    assert "not a count of every shape" in note


def test_the_three_stop_reasons_are_different_answers():
    """A search that ran out of budget was still finding things; one that
    plateaued was not. Collapsing them would hide the case where asking for
    more would help."""
    plateau = ConformerDetailsDialog._stop_note({"stop_reason": "plateau"})
    budget = ConformerDetailsDialog._stop_note({"stop_reason": "budget"})
    clock = ConformerDetailsDialog._stop_note({"stop_reason": "time"})

    assert plateau and budget and clock
    assert len({plateau, budget, clock}) == 3
    assert "may find more" in budget, "the actionable half of a budget stop is missing"


def test_a_run_that_never_recorded_a_stop_reason_says_nothing():
    """Nothing is fabricated for an old project -- the rule the whole dialog
    already follows."""
    assert ConformerDetailsDialog._stop_note({}) == ""


def test_fewer_than_asked_for_is_explained_as_a_result():
    """**THE QUESTION SOMEBODY ACTUALLY OPENS THIS FOR.** Ask for 20, get 9,
    and the obvious reading is that something went wrong. The cap note
    answers the opposite case (found 26, kept 20) and says nothing here."""
    note = ConformerDetailsDialog._shortfall_note(
        {"conformers_distinct": 9, "conformers_returned": 9, "num_conformers": 20}
    )

    assert "9 distinct" in note
    assert "20" in note
    assert "does not manufacture" in note


def test_the_shortfall_note_is_silent_when_the_CAP_is_why():
    """Two different situations, and printing both would leave the reader to
    work out which applies to them."""
    capped = {"conformers_distinct": 26, "conformers_returned": 20, "num_conformers": 20}

    assert ConformerDetailsDialog._shortfall_note(capped) == ""
    assert ConformerDetailsDialog._truncation_note(capped) != ""
