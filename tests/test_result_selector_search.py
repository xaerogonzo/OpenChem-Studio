"""Two searches, deliberately separate.

Stage 1e. The selector search narrows WHICH result you are reading; the
`FactView` box below it narrows the VALUES inside the one you chose. One box
over facts, reports, categories, providers and viewers at once cannot tell a
reader which of those it just matched, and a hit in a value would silently
change which producer is on screen.

**IT EXISTS BECAUSE 1a MADE THE LIST LONG.** Measured on a full run for
aspirin after 1a: 60 entries across 20 groups, which with the headings and
"All results" is **81 rows** in one combo. Before 1a it was 30 across 17.

The rule is split the way `ui/visual_check.py` splits its own: the MATCHING
is a pure function over entries, tested headless, and the widget half is
tested by driving the window.
"""

from __future__ import annotations

import pytest

from openchem.domain.reader_state import ReaderView
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.domain.result_ordering import (
    display_name_of,
    matches_search,
    matching_reports,
)
from openchem.ui.widgets.results_view import (
    ALL_RESULTS,
    GROUP_HEADING,
    ResultsView,
)
from tests.conftest import dispose

MOLECULE = "mol-1"


def _fact(label: str) -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )


def _report(report_id, name, category="identity", facts=("Formula",)) -> ReportResult:
    return ReportResult(
        molecule_uuid=MOLECULE,
        report_id=report_id,
        name=name,
        category=category,
        facts=tuple(_fact(f) for f in facts),
    )


def _corpus():
    """Three sections, so a filter can empty one and leave two."""
    return [
        _report("elemental_analysis", "Elemental Analysis", "identity"),
        _report("solubility", "Solubility", "solubility"),
        _report("solubility_ph", "Solubility vs pH", "solubility"),
        _report("topology_analysis", "Topology Analysis", "topology"),
    ]


@pytest.fixture
def window(qapp):
    w = ResultsView(MOLECULE)
    w.set_reports(_corpus())
    yield w
    dispose(w)


def _rows(window):
    box = window._focus_box
    return [(box.itemText(i), box.itemData(i)) for i in range(box.count())]


def _entries(window):
    return [text for text, data in _rows(window) if data != GROUP_HEADING]


def _headings(window):
    return [text for text, data in _rows(window) if data == GROUP_HEADING]


# --- the rule, headless --------------------------------------------------


def test_an_empty_search_is_the_absence_of_a_filter():
    """Not a filter that happens to match everything -- the distinction the
    reader states elsewhere between "nothing remembered" and a real value."""
    reports = _corpus()
    assert matching_reports(reports, "") == tuple(reports)
    assert matching_reports(reports, "   ") == tuple(reports)


def test_it_matches_a_result_by_name_whatever_the_case():
    matched = matching_reports(_corpus(), "TOPOLOGY")
    assert [r.report_id for r in matched] == ["topology_analysis"]


def test_it_matches_a_whole_SECTION_by_its_heading():
    """**THE HALF THAT MAKES IT USEFUL TO SOMEBODY WHO FORGOT A NAME.**
    "solubility" finds everything filed under Solubility whatever each entry
    is called, which is how a reader looks for a calculator they cannot name.
    Here both entries happen to be named for it too, so the discriminating
    case is the one below."""
    matched = matching_reports(_corpus(), "solubility")
    assert {r.report_id for r in matched} == {"solubility", "solubility_ph"}


def test_the_section_is_matched_even_when_no_name_contains_it():
    """The narrow half of the above, and without it "match the name only"
    passes that test. `category_label("admet")` is "ADMET / Regulatory", and
    no shipped entry in it is called that."""
    reports = [_report("herg", "hERG Risk Factors", "admet")]
    assert matching_reports(reports, "regulatory")
    assert not matching_reports(reports, "kinase")


def test_a_result_that_matches_neither_is_dropped():
    assert matching_reports(_corpus(), "zzz-nothing") == ()


def test_the_focused_result_survives_a_search_that_excludes_it():
    """**FILTERING NARROWS WHAT YOU CAN PICK, NEVER WHAT YOU ARE READING.**

    0i settled that jumping away from a reading position is the worse of the
    two failures, and `ALL_RESULTS`' own rule is that the control always names
    what it is currently doing. A list that hid the current selection would
    show one report and name another.
    """
    matched = matching_reports(_corpus(), "topology", always="solubility")
    ids = [r.report_id for r in matched]
    assert "solubility" in ids
    assert "topology_analysis" in ids


def test_keeping_the_focus_does_not_smuggle_in_its_neighbours():
    """The narrow half: `always` keeps ONE entry, not its whole section."""
    matched = matching_reports(_corpus(), "topology", always="solubility")
    assert "solubility_ph" not in [r.report_id for r in matched]


def test_the_callers_order_survives():
    """It is handed straight to `grouped_reports`, which cuts groups from a
    SORTED sequence -- so a filter that reordered would silently regroup.

    **AND THE FIRST FIXTURE FOR THIS WAS DEGENERATE.** `_corpus()` happens to
    be in alphabetical order by display name, so a mutation sorting the output
    produced an identical list and survived. The input here CONTRADICTS
    alphabetical order, which is the only arrangement that can tell "kept the
    caller's order" from "sorted it and got lucky".
    """
    reports = [
        _report("z_first", "Zulu Tool", "topology"),
        _report("a_second", "Alpha Tool", "topology"),
    ]
    assert [r.name for r in reports] != sorted(r.name for r in reports), (
        "the fixture must not already be alphabetical, or this passes vacuously"
    )
    matched = matching_reports(reports, "")
    assert [r.report_id for r in matched] == ["z_first", "a_second"]


def test_an_entry_with_no_name_is_findable_by_its_id():
    """The same fallback `MergedResults.name_for` makes: an id is at least
    true, and it is the only string a reader can see for such an entry."""
    anonymous = _report("weird_id", "")
    assert display_name_of(anonymous) == "weird_id"
    assert matches_search(anonymous, "weird")


# --- the window ----------------------------------------------------------


def test_typing_narrows_the_list(window):
    assert len(_entries(window)) == 5, "All results plus four"
    window._selector_search.setText("topology")
    assert _entries(window) == [ALL_RESULTS, "Topology Analysis"]


def test_a_section_the_filter_empties_loses_its_heading(window):
    """**INHERITED, NOT IMPLEMENTED.** `grouped_reports` never emits a group
    with nothing in it, and its docstring says that is what makes a search
    control safe to add without revisiting it. So the filter is applied to the
    INPUT and the headings follow."""
    assert len(_headings(window)) == 3
    window._selector_search.setText("topology")
    assert _headings(window) == ["Topology"]


def test_all_results_is_never_filtered_away(window):
    window._selector_search.setText("zzz-nothing")
    assert _entries(window) == [ALL_RESULTS]
    assert _headings(window) == []


def test_the_focused_result_stays_in_the_list_and_stays_focused(window):
    window.set_focus("solubility")
    window._selector_search.setText("topology")
    assert window.focus() == "solubility", "filtering must not move the reader"
    assert "Solubility" in _entries(window)


def test_clearing_the_search_brings_everything_back(window):
    window._selector_search.setText("topology")
    window._selector_search.setText("")
    assert len(_entries(window)) == 5
    assert len(_headings(window)) == 3


# --- and the two searches stay separate ----------------------------------


def test_the_two_searches_are_remembered_apart(window):
    """One narrows the values inside a report, the other which report is on
    screen. Collapsing them into one field would apply a fact filter to a
    selector or the reverse, and neither string means anything in the other
    box."""
    window._selector_search.setText("solub")
    window._view.set_filter_state("formula", False)

    state = window.view()
    assert state.selector_search == "solub"
    assert state.search == "formula"


def test_typing_in_the_selector_is_recorded_as_a_move(window):
    """**THE OTHER HALF OF `apply_view`'s RULE, AND NOTHING ASSERTED IT.**

    A host restoring a position must not write it back; a READER typing must.
    `view()` reads the widget, so every guard built on it stayed green with
    `_remember` deleted from the handler -- the reader simply forgot the box
    between sessions, silently, which is the same class of silence 0i exists
    to remove.
    """
    remembered = []
    window.set_reader_memory(_RecordingMemory(remembered))

    window._selector_search.setText("solub")

    assert remembered, "typing must reach the memory"
    _uuid, view = remembered[-1]
    assert view.selector_search == "solub"


def test_restoring_a_position_puts_both_back_without_recording_it(window):
    """`apply_view` is a host RESTORING, so it must not write the restore back
    -- the rule 0i established, applied to the second box. Signals are blocked
    for exactly that reason."""
    remembered = []
    window.set_reader_memory(_RecordingMemory(remembered))

    window.apply_view(ReaderView(report_id="solubility", search="pH", selector_search="solub"))

    assert window._selector_search.text() == "solub"
    assert window.focus() == "solubility"
    assert remembered == [], "restoring a position must not record it as a move"


class _RecordingMemory:
    """Enough of `ReaderMemory` to see whether anything was written."""

    def __init__(self, log):
        self._log = log

    def remember(self, molecule_uuid, view):
        self._log.append((molecule_uuid, view))

    def recall(self, molecule_uuid, available):
        return None

    def forget(self, molecule_uuid):
        pass
