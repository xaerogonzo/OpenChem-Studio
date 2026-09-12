"""The dialog that asks for two numbers instead of one.

Its predecessor asked for "Number of conformers" and passed the answer
straight to the EMBEDDER, so a user asking for 10 got 10 random attempts
and however many distinct shapes fell out -- reported as "Kept 2 distinct
conformer(s) of 10 embedded", which reads as a failure rather than as an
answer about the molecule.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from openchem.ui.dialogs.conformer_options_dialog import (
    DEFAULT_CONFORMERS_TO_KEEP,
    DEFAULT_EMBEDDINGS_TO_TRY,
    MAX_CONFORMERS_TO_KEEP,
    MAX_EMBEDDINGS,
    ConformerOptionsDialog,
)

import conftest


def _dispose(widget) -> None:
    """Per widget, and never the global form.

    A test that builds a widget and walks away leaves Python to destroy it
    at whatever arbitrary later moment the collector runs -- inside an
    unrelated test, from within Qt's own event dispatch, as an access
    violation. `sendPostedEvents(None, DeferredDelete)` would drain every
    pending delete in the process including ones other files queued, which
    is the double-free CLAUDE.md already documents.
    """
    conftest.dispose(widget)


def test_the_dialog_asks_for_embeddings_and_conformers_separately(qapp):
    dialog = ConformerOptionsDialog()
    try:
        assert dialog.embeddings_to_try() == DEFAULT_EMBEDDINGS_TO_TRY
        assert dialog.conformers_to_keep() == DEFAULT_CONFORMERS_TO_KEEP
        # They are genuinely two numbers, not one shown twice.
        assert dialog.embeddings_to_try() != dialog.conformers_to_keep()
    finally:
        _dispose(dialog)


def test_more_embeddings_are_offered_than_conformers(qapp):
    """The whole point of the split: a random search must be allowed to
    take far more samples than the number of distinct shapes wanted.
    Measured, 10 embeddings of a drug-like molecule found at most 6
    distinct geometries against a reference lower bound of 12."""
    dialog = ConformerOptionsDialog()
    try:
        assert DEFAULT_EMBEDDINGS_TO_TRY > DEFAULT_CONFORMERS_TO_KEEP
        assert MAX_EMBEDDINGS > MAX_CONFORMERS_TO_KEEP
    finally:
        _dispose(dialog)


def test_both_fields_are_bounded_below_at_one(qapp):
    """Zero embeddings or zero conformers is not a request anybody means,
    and it would produce an empty result that reads as a failure."""
    dialog = ConformerOptionsDialog()
    try:
        for spin in (dialog._embeddings_spin, dialog._keep_spin):
            assert spin.minimum() == 1
            spin.setValue(0)
            assert spin.value() == 1
    finally:
        _dispose(dialog)


def test_the_ceilings_are_enforced(qapp):
    dialog = ConformerOptionsDialog()
    try:
        # **ADVANCED FIRST, because Automatic does not read these fields.**
        # The embedding budget is the documented one unless the user has
        # asked to set it, so without this the assertion below would be
        # comparing the preset against a spin box nobody consulted.
        dialog._advanced.setChecked(True)
        dialog._embeddings_spin.setValue(MAX_EMBEDDINGS + 1000)
        dialog._keep_spin.setValue(MAX_CONFORMERS_TO_KEEP + 1000)
        assert dialog.embeddings_to_try() == MAX_EMBEDDINGS
        assert dialog.conformers_to_keep() == MAX_CONFORMERS_TO_KEEP
    finally:
        _dispose(dialog)


def test_rejecting_the_dialog_is_distinguishable_from_accepting_it(qapp):
    """`_on_generate_clicked` returns without generating unless the dialog
    was accepted -- a Cancel that read as an accept would start a
    long-running job the user just declined."""
    dialog = ConformerOptionsDialog()
    try:
        dialog.reject()
        assert dialog.result() == QDialog.DialogCode.Rejected
    finally:
        _dispose(dialog)


def test_the_dialog_explains_why_fewer_may_come_back(qapp):
    """"I asked for 10 and got 3" is the confusion this dialog exists to
    prevent, so it has to say so before the job runs rather than only in
    the status line afterwards."""
    from PySide6.QtWidgets import QLabel

    dialog = ConformerOptionsDialog()
    try:
        text = " ".join(
            label.text().lower() for label in dialog.findChildren(QLabel) if label.text()
        )
        assert "attempt" in text
        assert "fewer" in text
    finally:
        _dispose(dialog)


def test_the_defaults_are_the_ones_the_funnel_evidence_chose():
    """A change-detector on purpose -- the _LAYOUT_VERSION pattern.

    These two numbers are decisions with measurements behind them, and
    the embedding one has now been taken twice.

    keep=10 silently truncated ethylmorphine at the old defaults (2026-08-13:
    12 distinct found, 10 returned, measured live), so it is 20.

    **AND THE EMBEDDING NUMBER CHANGED MEANING, WHICH IS WHY IT MOVED
    10x.** It used to be the number of embeddings a run made, and 100 was
    chosen because it roughly doubled a flexible molecule's yield. It is
    now the CEILING on a search that stops itself when new shapes stop
    appearing, so leaving it at 100 would cut every flexible molecule short.
    Measured on the batched search: the plateau arrives at 200 embeddings
    for the reported fused cage (9 distinct, ~13 s, from either of two
    seeds) and at 350-400 for ethylmorphine (26-27 distinct, ~20 s). Nothing
    in the corpus reaches 1000, which is what a ceiling is for.

    Changing them again is fine -- with a new measurement, and this test
    updated to cite it.
    """
    assert DEFAULT_CONFORMERS_TO_KEEP == 20
    assert DEFAULT_EMBEDDINGS_TO_TRY == 1000


def test_automatic_spends_the_documented_budget_not_the_hidden_fields(qapp):
    """**THE PRESET HAS TO BE WHAT SHIPS.** The four search controls are
    hidden by default, so whatever they happen to hold is not a decision
    anybody made -- reading them in Automatic would make `AUTOMATIC_SEARCH`
    a comment rather than a setting, and the gate that measures it would be
    measuring something else."""
    from openchem.ui.dialogs.conformer_options_dialog import AUTOMATIC_SEARCH

    dialog = ConformerOptionsDialog()
    try:
        assert dialog.is_automatic()
        dialog._embeddings_spin.setValue(7)

        assert dialog.embeddings_to_try() == AUTOMATIC_SEARCH["max_embeddings"]
        options = dialog.options()
        assert options.max_embeddings == AUTOMATIC_SEARCH["max_embeddings"]
        assert options.embedding_batch_size == AUTOMATIC_SEARCH["embedding_batch_size"]
        assert options.plateau_batches_required == AUTOMATIC_SEARCH["plateau_batches_required"]
    finally:
        _dispose(dialog)


def test_advanced_hands_over_the_fields_the_user_set(qapp):
    """And the other half: having asked to set them, they are what is used."""
    dialog = ConformerOptionsDialog()
    try:
        dialog._advanced.setChecked(True)
        dialog._embeddings_spin.setValue(120)
        dialog._batch_spin.setValue(15)
        dialog._plateau_spin.setValue(4)

        options = dialog.options()

        assert options.max_embeddings == 120
        assert options.embedding_batch_size == 15
        assert options.plateau_batches_required == 4
    finally:
        _dispose(dialog)
