"""Where each molecule's reader was, and what may move it.

A window keyed on a molecule is thrown away when the selection moves, so
"which report was focused" has never had to survive anything. A reader that
FOLLOWS the selection turns that into state, and the failure mode is not
neutral: silently jumping back to "All results" every time somebody glances at
another molecule is worse than the window it replaces.

Guards come in pairs. "It restores the report" is satisfied by a memory that
restores everything including reports that no longer exist, and "it falls back"
is satisfied by one that never restores anything -- so both halves are here,
and so is the one that says the filter is NOT part of the fallback.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from openchem.domain.reader_state import (
    DEFAULT_VIEW,
    NO_MOLECULE,
    NOTHING_COMPUTED,
    READER_STATES,
    SHOWING,
    ReaderMemory,
    ReaderView,
    reader_state,
)


# --- the three states ----------------------------------------------------


def test_no_molecule_and_nothing_computed_are_different_states():
    """**THE PAIR THIS VOCABULARY EXISTS FOR.** "Pick a molecule" and
    "nothing has been computed for this one yet" send a reader to two
    different places, and rendering both as blankness is the failure
    `MergedResultsDialog._render` already refuses for the second."""
    assert reader_state(None, 0) == NO_MOLECULE
    assert reader_state("", 0) == NO_MOLECULE
    assert reader_state("mol-1", 0) == NOTHING_COMPUTED


def test_a_reader_with_something_to_show_is_showing():
    assert reader_state("mol-1", 1) == SHOWING


def test_no_molecule_wins_over_a_result_count():
    """A count left over from a previous selection must not make a reader
    with nothing selected look like it is showing that molecule's results."""
    assert reader_state(None, 7) == NO_MOLECULE


@pytest.mark.parametrize(
    ("uuid", "count"), [(None, 0), ("", 3), ("mol-1", 0), ("mol-1", 9)]
)
def test_every_answer_is_in_the_closed_vocabulary(uuid, count):
    assert reader_state(uuid, count) in READER_STATES


# --- the memory ----------------------------------------------------------


def test_a_molecule_nobody_has_read_opens_on_the_default_view():
    assert ReaderMemory().recall("mol-1", ["a"]) == DEFAULT_VIEW


def test_a_remembered_position_comes_back():
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="lewis_sites", search="donor"))
    recalled = memory.recall("mol-1", ["lewis_sites", "topology_analysis"])
    assert recalled.report_id == "lewis_sites"
    assert recalled.search == "donor"


def test_each_molecule_has_its_own_position():
    """Per uuid, which is what stops one molecule inheriting another's filter
    -- the reason falling back may keep the filter at all."""
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="lewis_sites", search="donor"))
    memory.remember("mol-2", ReaderView(report_id="topology_analysis"))
    assert memory.recall("mol-1", ["lewis_sites"]).report_id == "lewis_sites"
    assert memory.recall("mol-2", ["topology_analysis"]).search == ""


def test_a_report_that_no_longer_exists_falls_back_to_all_results():
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="retired_calculator"))
    assert memory.recall("mol-1", ["lewis_sites"]).report_id == ""


def test_falling_back_keeps_the_filter():
    """The narrow half, and the one a "fall back to the default view" mutation
    passes without. The search text is about what somebody is looking FOR, not
    about which report -- dropping it answers a question nobody asked."""
    memory = ReaderMemory()
    memory.remember(
        "mol-1", ReaderView(report_id="retired", search="donor", everything=True)
    )
    recalled = memory.recall("mol-1", ["lewis_sites"])
    assert recalled.report_id == ""
    assert recalled.search == "donor"
    assert recalled.everything is True


def test_a_stale_report_is_restored_rather_than_jumped_away_from():
    """**A STALE RESULT IS A RECORD OF WHAT WAS COMPUTED**, and this project
    refuses to discard one everywhere else. `recall` is not told about
    staleness at all -- a stale report is simply one of the ids that exist --
    which is a stronger guarantee than remembering not to consult it."""
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="bbb_score"))
    # The caller hands over every id it can show, stale included.
    assert memory.recall("mol-1", ["bbb_score"]).report_id == "bbb_score"


def test_recall_is_told_only_which_ids_exist():
    """The structural half of the rule above: there is nowhere to pass a
    staleness verdict, so no future edit can start filtering on one without
    changing the signature."""
    parameters = list(inspect.signature(ReaderMemory.recall).parameters)
    assert parameters == ["self", "molecule_uuid", "available"]


def test_remembering_all_results_is_not_the_same_as_remembering_nothing():
    """A molecule deliberately left on "All results" with a filter set must
    keep the filter. Collapsing it into "unknown molecule" would silently
    clear the box every time somebody came back."""
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="", search="ring"))
    assert memory.recall("mol-1", []).search == "ring"
    assert memory.recall("mol-2", []) == DEFAULT_VIEW


def test_a_falsy_uuid_records_nothing():
    """Otherwise every reader with no molecule selected files its position
    under one key, and the next molecule to arrive inherits it."""
    memory = ReaderMemory()
    memory.remember("", ReaderView(report_id="lewis_sites"))
    assert len(memory) == 0


def test_forgetting_one_molecule_leaves_the_others():
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="a"))
    memory.remember("mol-2", ReaderView(report_id="b"))
    memory.forget("mol-1")
    assert memory.recall("mol-1", ["a"]) == DEFAULT_VIEW
    assert memory.recall("mol-2", ["b"]).report_id == "b"


def test_clearing_drops_everything():
    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="a"))
    memory.clear()
    assert len(memory) == 0


def test_a_stored_position_cannot_be_mutated_by_its_reader():
    """Frozen, so a consumer that edits what it was handed cannot rewrite the
    memory underneath every other consumer."""
    view = ReaderView(report_id="a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.report_id = "b"
