"""The picker for individual always-on properties and alert catalogs.

What is guarded, each a defect the Batch panel's tree was written to avoid:

* nothing chosen before means everything ticked, and a previous choice survives by id;
* an id that no longer exists is dropped rather than kept, so a stale choice cannot run;
* the filter hides rows and NEVER unticks them, and ticking a heading never touches a row the
  filter is hiding;
* "nothing ticked" cannot be accepted, because it would run as everything or as nothing.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox

import conftest
from openchem.ui.dialogs.property_choice_dialog import PropertyChoiceDialog

GROUPS = {
    "Lipophilicity": [("logp", "LogP", "Crippen logP"), ("mr", "Molar refractivity", "")],
    "Size": [("mw", "Molecular weight", ""), ("hac", "Heavy atoms", "")],
}


@pytest.fixture
def built(qapp):
    dialogs = []
    yield dialogs
    for dialog in dialogs:
        conftest.dispose(dialog)


def _dialog(built, chosen=None, groups=GROUPS):
    dialog = PropertyChoiceDialog("Choose", "Pick.", groups, chosen)
    built.append(dialog)
    return dialog


def _ok(dialog):
    return dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)


def _group(dialog, index):
    return dialog._tree.topLevelItem(index)


def test_everything_is_ticked_when_nothing_was_chosen_before(built):
    assert _dialog(built).chosen() == {"logp", "mr", "mw", "hac"}


def test_a_previous_choice_survives_by_id(built):
    assert _dialog(built, {"logp", "hac"}).chosen() == {"logp", "hac"}


def test_an_id_that_no_longer_exists_is_dropped(built):
    assert _dialog(built, {"logp", "gone"}).chosen() == {"logp"}


def test_a_choice_that_names_nothing_that_exists_reads_as_everything(built):
    assert _dialog(built, {"gone"}).chosen() == {"logp", "mr", "mw", "hac"}


def test_the_count_says_how_many_are_ticked(built):
    dialog = _dialog(built, {"logp"})

    assert dialog._count.text() == "1 of 4 ticked"


def test_nothing_ticked_cannot_be_accepted(built):
    dialog = _dialog(built)

    dialog._untick_shown()

    assert dialog.chosen() == set() and not _ok(dialog).isEnabled()


def test_a_group_reads_partly_ticked_from_its_rows(built):
    dialog = _dialog(built, {"logp"})

    assert _group(dialog, 0).checkState(0) is Qt.CheckState.PartiallyChecked
    assert _group(dialog, 1).checkState(0) is Qt.CheckState.Unchecked


def test_ticking_a_heading_ticks_its_rows(built):
    dialog = _dialog(built, {"logp"})

    _group(dialog, 1).setCheckState(0, Qt.CheckState.Checked)

    assert dialog.chosen() == {"logp", "mw", "hac"}


def test_the_filter_hides_rows_and_keeps_their_ticks(built):
    dialog = _dialog(built)

    dialog._filter.setText("weight")

    assert dialog.shown_count() == 1
    assert dialog.chosen() == {"logp", "mr", "mw", "hac"}


def test_a_group_with_no_match_is_hidden(built):
    dialog = _dialog(built)

    dialog._filter.setText("weight")

    assert _group(dialog, 0).isHidden() and not _group(dialog, 1).isHidden()


def test_none_shown_unticks_only_what_the_filter_shows(built):
    dialog = _dialog(built)
    dialog._filter.setText("weight")

    dialog._untick_shown()
    dialog._filter.setText("")

    assert dialog.chosen() == {"logp", "mr", "hac"}


def test_all_shown_ticks_only_what_the_filter_shows(built):
    dialog = _dialog(built, {"logp"})
    dialog._filter.setText("heavy")

    dialog._tick_shown()
    dialog._filter.setText("")

    assert dialog.chosen() == {"logp", "hac"}


def test_ticking_a_heading_never_touches_a_row_the_filter_hides(built):
    dialog = _dialog(built, {"logp"})
    dialog._filter.setText("weight")

    _group(dialog, 1).setCheckState(0, Qt.CheckState.Checked)
    dialog._filter.setText("")

    assert dialog.chosen() == {"logp", "mw"}, "Heavy atoms was hidden, so it stays unticked"


def test_a_heading_name_matches_its_rows(built):
    dialog = _dialog(built)

    dialog._filter.setText("lipophil")

    assert dialog.shown_count() == 2


def test_the_tooltip_of_a_row_is_kept(built):
    leaf = _group(_dialog(built), 0).child(0)

    assert leaf.toolTip(0) == "Crippen logP"
