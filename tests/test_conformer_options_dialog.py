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

    These two numbers are decisions with measurements behind them
    (2026-08-13): keep=10 silently truncated ethylmorphine at the old
    defaults (12 distinct found, 10 returned, measured live), and 100
    embeddings roughly doubles a flexible molecule's yield (10 -> 15
    distinct) at ~5 s. An accidental revert should fail HERE, naming the
    evidence, rather than quietly reintroducing silent truncation.
    Changing them again is fine -- with a new measurement, and this test
    updated to cite it.
    """
    assert DEFAULT_CONFORMERS_TO_KEEP == 20
    assert DEFAULT_EMBEDDINGS_TO_TRY == 100
