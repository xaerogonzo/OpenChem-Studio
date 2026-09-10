"""The merged results window: one per molecule, modeless, live.

Four of these are LIFECYCLE tests. The window is now subscribed to results
arriving and keyed on an identity, and none of that is covered by the
merge being correct -- an ordinary Qt lifetime bug is exactly the class a
domain-level test cannot see.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from openchem.domain.common import CacheState
from openchem.domain.report import (
    ArrowAnnotation,
    Basis,
    Fact,
    FactCategory,
    ReportResult,
    Stick,
    StickChartAnnotation,
)
from openchem.ui.widgets.results_view import (
    ALL_RESULTS,
    EMPTY_MESSAGES,
    GROUP_HEADING,
    ResultsView,
    STALE_MARK,
)
from openchem.domain.reader_state import NO_MOLECULE
from openchem.ui.widgets.collapsible_section import CollapsibleSection
from tests.conftest import dispose


def _rows(window):
    """Every row of the focus box, as (text, data).

    Read as data rather than by POSITION, which is what these guards did
    before the list gained group headings -- `itemText(1)` was the first
    calculator and is now the first heading. Position was never the contract:
    `_sync_focus_box` restores the selection with `findData`.
    """
    box = window._focus_box
    return [(box.itemText(i), box.itemData(i)) for i in range(box.count())]


def _entries(window):
    """Just the selectable entries, in order."""
    return [(text, data) for text, data in _rows(window) if data != GROUP_HEADING]


def _fact(label: str, source: str = "RDKit") -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source=source,
        basis=Basis.DETERMINISTIC,
    )


def _chart(title: str) -> StickChartAnnotation:
    return StickChartAnnotation(
        sticks=(Stick(1.0, 1.0),),
        x_label="m/z",
        y_label="Relative abundance",
        x_descending=False,
        title=title,
    )


def _report(
    report_id, name, labels, charts=(), spatial=(), version=0, category="other"
) -> ReportResult:
    return ReportResult(
        molecule_uuid="mol-1",
        report_id=report_id,
        name=name,
        category=category,
        facts=tuple(_fact(label) for label in labels),
        charts=tuple(charts),
        spatial=tuple(spatial),
        structure_version=version,
    )


def _two():
    return (
        _report("elemental_analysis", "Elemental Analysis", ["Formula"],
                charts=[_chart("Isotope pattern")]),
        _report("lewis_sites", "Lewis Sites", ["Donor sites"], charts=[_chart("Sites")]),
    )


# --- the complaint this exists for ---------------------------------------


def test_two_calculators_land_in_one_window(qapp):
    """The whole point: running a second calculator used to replace the
    first window rather than adding to it."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    assert [f.label for f in window.merged().facts] == ["Formula", "Donor sites"]
    dispose(window)


def test_the_filter_now_has_something_to_filter(qapp):
    """`FactView`'s search was built for a hundred facts and was being
    handed one calculator's four."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    view = window._view
    view.search_box().setText("donor")
    assert view.visible_fact_labels() == ["Donor sites"]
    dispose(window)


def test_the_search_also_matches_the_producing_calculator(qapp):
    """`Fact.origin` is stamped by the merge, so "show me everything the
    Lewis calculator said" is a question the box can answer."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window._view.search_box().setText("lewis_sites")
    assert window._view.visible_fact_labels() == ["Donor sites"]
    dispose(window)


# --- focus ---------------------------------------------------------------


def test_a_details_button_arrives_focused_on_its_own_report(qapp):
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window.set_focus("lewis_sites")
    assert window.focus() == "lewis_sites"
    assert window._view.visible_fact_labels() == ["Donor sites"]
    dispose(window)


def test_focusing_one_report_never_shows_anothers_chart(qapp):
    """Once several calculators contribute a chart, "the first chart" stops
    being an answer to anything."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window.set_focus("elemental_analysis")
    titles = [w.annotation().title for w in window._view.chart_widgets()]
    assert titles == ["Isotope pattern"]
    window.set_focus("lewis_sites")
    titles = [w.annotation().title for w in window._view.chart_widgets()]
    assert titles == ["Sites"]
    dispose(window)


def test_showing_everything_shows_every_chart(qapp):
    window = ResultsView("mol-1")
    window.set_reports(_two())
    titles = [w.annotation().title for w in window._view.chart_widgets()]
    assert titles == ["Isotope pattern", "Sites"]
    dispose(window)


def test_focus_is_by_report_id_and_an_unknown_one_falls_back_to_all(qapp):
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window.set_focus("no_such_calculator")
    assert window.focus() == ""
    assert len(window._view.chart_widgets()) == 2
    dispose(window)


def test_the_focus_control_lists_every_calculator_by_name(qapp):
    """Never a prettified id: the window asks the container, which asks the
    report."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    assert [text for text, _data in _entries(window)] == [
        ALL_RESULTS,
        "Elemental Analysis",
        "Lewis Sites",
    ]
    dispose(window)


def test_the_list_is_grouped_by_section_and_the_headings_cannot_be_chosen(qapp):
    """**THE "Showing" LIST IS GROUPED THE WAY THE PANEL ABOVE IT IS.** It
    was flat and arrival-ordered, which for a molecule with everything run is
    30 entries in whatever order the calculations finished.

    A heading has to be unselectable or arrowing through the list lands on
    one, so it is DISABLED rather than merely styled -- Qt then refuses to
    make it current.
    """
    window = ResultsView("mol-1")
    window.set_reports(
        [
            _report("lewis_sites", "Lewis Sites", ["Donor"], category="lewis"),
            _report(
                "elemental_analysis",
                "Elemental Analysis",
                ["Formula"],
                category="identity",
            ),
        ]
    )
    box = window._focus_box
    headings = [
        (i, text) for i, (text, data) in enumerate(_rows(window)) if data == GROUP_HEADING
    ]
    assert [text for _i, text in headings] == ["Identity", "Lewis Acid/Base"], (
        "sections are named by the shared taxonomy, and are in its order"
    )
    model = box.model()
    for index, _text in headings:
        assert not model.item(index).isEnabled(), "a heading must not be selectable"
    dispose(window)


def test_a_heading_is_never_mistaken_for_the_all_results_entry(qapp):
    """`_sync_focus_box` restores with `findData(self._focus)`, and `""` is a
    REAL value there -- it is what ALL_RESULTS carries. A heading holding the
    same thing would be found first and the box would restore onto a row
    nobody can select."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    assert window._focus_box.findData("") == 0, "ALL_RESULTS is still row 0"
    assert GROUP_HEADING != ""
    dispose(window)


def test_the_selection_survives_a_result_landing_above_it(qapp):
    """**A CALCULATION FINISHING MUST NOT MOVE WHAT SOMEBODY IS READING.**

    The list is rebuilt from scratch on every arrival, so the selection is
    restored by `findData` rather than by index -- and this fixture makes the
    two disagree: the arriving result belongs to an EARLIER section, so it
    pushes the focused entry down by two rows (its own heading and itself).
    A restore that remembered a position would land on the wrong report, or
    on a heading.
    """
    lewis = _report("lewis_sites", "Lewis Sites", ["Donor"], category="lewis")
    window = ResultsView("mol-1")
    window.set_reports([lewis])
    window.set_focus("lewis_sites")
    before = window._focus_box.currentIndex()

    early = _report(
        "elemental_analysis", "Elemental Analysis", ["Formula"], category="identity"
    )
    window.set_reports([lewis, early])

    assert window.focus() == "lewis_sites", "the reader's choice must survive"
    assert window._focus_box.currentData() == "lewis_sites"
    assert window._focus_box.currentIndex() != before, (
        "fixture is degenerate: the arrival did not move the entry, so an "
        "index-based restore would have passed too"
    )
    dispose(window)


def test_no_heading_is_emitted_for_a_section_with_nothing_in_it(qapp):
    """The selector shows what has been COMPUTED, so its group set differs
    per molecule and per session. Somebody who has run one calculator must
    not scroll twenty headings."""
    window = ResultsView("mol-1")
    window.set_reports(
        [_report("lewis_sites", "Lewis Sites", ["Donor"], category="lewis")]
    )
    headings = [text for text, data in _rows(window) if data == GROUP_HEADING]
    assert headings == ["Lewis Acid/Base"]
    dispose(window)


# --- staleness -----------------------------------------------------------


def test_a_stale_report_is_marked_and_kept(qapp):
    """**REPORTED, NEVER DISCARDED.** Silently serving a stale result and
    silently blanking it are the two ways this goes wrong, and they look
    identical from outside."""
    old = _report(
        "lewis_sites", "Lewis Sites", ["Donor sites"], version=1, category="lewis"
    )
    new = _report(
        "elemental_analysis",
        "Elemental Analysis",
        ["Formula"],
        version=2,
        category="identity",
    )
    window = ResultsView("mol-1")
    window.set_reports([old, new], structure_version=2)
    # Elemental Analysis first: `identity` precedes `lewis` in the shared
    # taxonomy, which is the order the sections above already use. Before
    # this the list followed the order the two results arrived in.
    assert [text for text, _data in _entries(window)] == [
        ALL_RESULTS,
        "Elemental Analysis",
        "Lewis Sites" + STALE_MARK,
    ]
    assert len(window.merged().facts) == 2, "neither is discarded"
    dispose(window)


def test_a_focused_stale_report_says_so_above_its_facts(qapp):
    old = _report("lewis_sites", "Lewis Sites", ["Donor sites"], version=1)
    window = ResultsView("mol-1")
    window.set_reports([old], structure_version=2)
    window.set_focus("lewis_sites")
    assert "earlier version" in window._view._summary.text()
    dispose(window)


def test_the_stale_marks_update_in_an_OPEN_window(qapp):
    """**THE LIFECYCLE TEST, NOT THE SYNCHRONOUS ONE.** The behaviour a
    user experiences is editing the molecule while the window is open, and
    a merge that is only correct at construction never shows it."""
    report = _report("lewis_sites", "Lewis Sites", ["Donor sites"], version=1)
    window = ResultsView("mol-1")
    window.set_reports([report], structure_version=1)
    assert dict(map(reversed, _entries(window)))["lewis_sites"] == "Lewis Sites"
    # The structure moves under it, and the same reports are pushed again.
    window.set_reports([report], structure_version=2)
    assert (
        dict(map(reversed, _entries(window)))["lewis_sites"]
        == "Lewis Sites" + STALE_MARK
    )
    dispose(window)


# --- the empty state -----------------------------------------------------


def test_nothing_computed_says_so_rather_than_showing_an_empty_report(qapp):
    """"Nothing has been computed" and "everything ran and had nothing to
    say" are different statements, and an empty report makes the second
    one."""
    window = ResultsView("mol-1")
    window.set_reports([])
    # **`isHidden()`, NOT `isVisible()`.** A child of a window nobody
    # showed reports `isVisible() == False` whatever its own flag says, so
    # the obvious assertion here passes against a panel that is showing an
    # empty report -- measured: mutating the empty-state branch away left
    # this test green until it was rewritten this way.
    assert not window._empty.isHidden()
    assert window._view.isHidden()
    assert window.merged().reports == ()
    dispose(window)


def test_a_result_arriving_replaces_the_empty_state(qapp):
    window = ResultsView("mol-1")
    window.set_reports([])
    window.set_reports(_two())
    assert window._empty.isHidden()
    assert not window._view.isHidden()
    assert window.merged().reports
    dispose(window)


# --- provenance ----------------------------------------------------------


def test_a_facts_source_and_its_origin_stay_independent(qapp):
    """A fact can honestly be sourced "RDKit" and originate in Elemental
    Analysis; collapsing the two destroys real provenance to record
    different provenance."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    formula = next(f for f in window.merged().facts if f.label == "Formula")
    assert formula.source == "RDKit"
    assert formula.origin == "elemental_analysis"
    dispose(window)


def test_spatial_annotations_keep_their_owner(qapp):
    arrow = ArrowAnnotation(
        anchor=(0.0, 0.0, 0.0), vector=(1.0, 0.0, 0.0), units="D", label="mu"
    )
    window = ResultsView("mol-1")
    window.set_reports([
        _report("dipole", "Dipole Moment", ["Dipole"], spatial=[arrow]),
        _report("lewis_sites", "Lewis Sites", ["Donor sites"]),
    ])
    assert window.merged().spatial_for("dipole") == (arrow,)
    assert window.merged().spatial_for("lewis_sites") == ()
    dispose(window)


# --- a report with no facts ----------------------------------------------
#
# `merge_reports` used to refuse one, so a refused calculator's report reached
# this window not at all and read as nothing having happened. Admitting it is
# only half the fix; the other half is that "0 facts." is not an explanation.


def _failed(report_id: str, reason: str, *, inapplicable: bool = False) -> ReportResult:
    """A producer's refusal, in the shape `report_from_fields` really emits --
    empty facts, FAILED, and the reason in `error`."""
    return ReportResult(
        report_id=report_id,
        name=report_id.replace("_", " ").title(),
        molecule_uuid="u",
        facts=(),
        cache_state=CacheState.FAILED,
        error=reason,
        inapplicable=inapplicable,
    )


def test_a_failed_report_with_no_facts_is_shown_rather_than_dropped(qapp):
    """The live bug. `compute_lewis_sites` returns `matched=[]` with
    `cache_state=FAILED` on refusal, so this exact shape was invisible here."""
    dialog = ResultsView("u")
    dialog.set_reports([_failed("lewis_sites", "no assignable Lewis sites")])
    assert [r.report_id for r in dialog.merged().reports] == ["lewis_sites"]
    # And reachable in the selector, not merely in the model.
    labels = [dialog._focus_box.itemText(i) for i in range(dialog._focus_box.count())]
    assert "Lewis Sites" in labels
    dispose(dialog)


def test_a_failed_report_says_why_rather_than_reading_as_an_empty_result(qapp):
    """Without this the fix trades one wrong statement for another: a refused
    calculator would appear as one that ran and had nothing to say."""
    dialog = ResultsView("u")
    dialog.set_reports([_failed("lewis_sites", "no assignable Lewis sites")])
    dialog.set_focus("lewis_sites")
    assert "no assignable Lewis sites" in dialog._view.summary_text()
    dispose(dialog)


def test_a_refusal_does_not_read_as_a_fault(qapp):
    """A REFUSAL IS NOT A FAULT. The method not covering this molecule is a
    correct, permanent answer; painting it as a crash is what made two working
    calculators read as broken. The existing `inapplicable` field separates
    them -- this asserts the reader uses it rather than inventing a second
    vocabulary."""
    dialog = ResultsView("u")
    dialog.set_reports([_failed("joback", "no group for a ring tertiary amine", inapplicable=True)])
    dialog.set_focus("joback")
    text = dialog._view.summary_text()
    assert "Not applicable" in text
    assert "did not run" not in text
    dispose(dialog)


def test_a_failed_and_stale_report_says_both(qapp):
    """Two facts about one result. Showing one would leave a reader to
    discover the other by surprise."""
    dialog = ResultsView("u")
    dialog.set_reports([_failed("lewis_sites", "no assignable Lewis sites")], structure_version=3)
    dialog.set_focus("lewis_sites")
    text = dialog._view.summary_text()
    assert "no assignable Lewis sites" in text
    assert "earlier version" in text
    dispose(dialog)


def test_a_completed_report_carries_no_status_line(qapp):
    """The narrow half. A status line on every report would be noise, and
    "always explain" satisfies the three guards above while doing it."""
    dialog = ResultsView("u")
    dialog.set_reports([_report("ok", "OK", ["Mass"])])
    dialog.set_focus("ok")
    text = dialog._view.summary_text()
    assert "did not run" not in text and "Not applicable" not in text
    dispose(dialog)


# --- the three states a reader can be empty in ---------------------------


def test_a_reader_with_no_molecule_says_so_rather_than_nothing_computed(qapp):
    """**TWO EMPTY STATES, NOT ONE.** "Pick a molecule" and "nothing has been
    computed for this one yet" send a reader to two different places. This
    window is always opened FOR a molecule, so the first has had no route
    through the application -- a reader that follows the selection has one,
    which is why the text exists before the dock does.
    """
    from openchem.domain.reader_state import NO_MOLECULE, NOTHING_COMPUTED

    nothing = ResultsView("")
    nothing.set_reports([])
    assert nothing._empty.text() == EMPTY_MESSAGES[NO_MOLECULE]

    a_molecule = ResultsView("mol-1")
    a_molecule.set_reports([])
    assert a_molecule._empty.text() == EMPTY_MESSAGES[NOTHING_COMPUTED]
    assert EMPTY_MESSAGES[NO_MOLECULE] != EMPTY_MESSAGES[NOTHING_COMPUTED]
    dispose(nothing)
    dispose(a_molecule)


def test_a_reader_with_results_shows_them_rather_than_either_message(qapp):
    """The narrow half: "always show the empty label" satisfies the pair
    above and hides every result in the application."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    assert window._empty.isHidden()
    assert not window._view.isHidden()
    dispose(window)


# --- where the reader is --------------------------------------------------


def test_the_window_reports_its_own_position(qapp):
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window.set_focus("lewis_sites")
    window._view.search_box().setText("donor")
    view = window.view()
    assert view.report_id == "lewis_sites"
    assert view.search == "donor"
    assert view.everything is False
    dispose(window)


def test_applying_a_position_does_not_record_it_as_a_move(qapp):
    """**A HOST RESTORING MUST NOT WRITE BACK.** With a recall that FELL BACK
    -- the focused report is gone -- recording the restore would overwrite the
    remembered id with the empty one, and a report that came back later could
    never be restored again."""
    from openchem.domain.reader_state import ReaderMemory, ReaderView

    memory = ReaderMemory()
    memory.remember("mol-1", ReaderView(report_id="gone", search="donor"))
    window = ResultsView("mol-1")
    window.set_reader_memory(memory)
    window.set_reports(_two())

    window.apply_view(memory.recall("mol-1", [r.report_id for r in window.merged().reports]))
    assert window.focus() == "", "the remembered report is genuinely absent"
    assert memory.recall("mol-1", ["gone"]).report_id == "gone", (
        "the restore overwrote the memory it came from"
    )
    dispose(window)


def test_a_reader_choosing_in_the_box_is_recorded(qapp):
    """The complement: a READER moving the control is exactly what the memory
    is for, so this must be written."""
    from openchem.domain.reader_state import ReaderMemory

    memory = ReaderMemory()
    window = ResultsView("mol-1")
    window.set_reader_memory(memory)
    window.set_reports(_two())

    index = window._focus_box.findData("lewis_sites")
    window._focus_box.setCurrentIndex(index)
    assert memory.recall("mol-1", ["lewis_sites"]).report_id == "lewis_sites"
    dispose(window)


def test_a_window_with_no_memory_behaves_exactly_as_before(qapp):
    """Optional, so nothing that builds one without a memory changes."""
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window.set_focus("lewis_sites")
    window._view.search_box().setText("donor")
    assert window.focus() == "lewis_sites"
    dispose(window)


def test_a_reader_with_no_molecule_records_no_position(qapp):
    """**THE OTHER HALF OF THE NO-MOLECULE STATE, AND ONLY MUTATION FOUND
    IT.** The rendering half is above; this is the recording one. A reader
    with nothing selected still has a search box somebody can type in, and
    filing that under any key at all means the next molecule to arrive
    inherits a filter it never had.

    `ReaderMemory.remember` refuses a falsy uuid, and that cannot help here:
    the failure is the WINDOW substituting a truthy one. Mutating
    `self._molecule_uuid` to `self._molecule_uuid or "x"` passed every other
    guard in this file.
    """
    from openchem.domain.reader_state import ReaderMemory

    memory = ReaderMemory()
    window = ResultsView("")
    window.set_reader_memory(memory)
    window.set_reports([])

    window._view.search_box().setText("ring")
    assert len(memory) == 0, "a reader with no molecule filed a position"
    dispose(window)


def test_the_reader_stands_up_with_no_window_and_no_molecule(qapp):
    """What a dock needs and a dialog never did.

    The reader was opened FOR a molecule, so "no molecule is selected" had
    no route through the application at all -- `reader_state` named the
    state and nothing could reach it. A reader that FOLLOWS the selection
    starts there, before anything is chosen, which is why the molecule uuid
    is defaulted rather than required.

    It also fails if the initial state is ASSUMED rather than rendered: the
    empty label is constructed holding the nothing-computed message, and
    until this widget renders itself that is what it shows -- naming the
    wrong problem, and sending somebody looking for a calculator to run.
    """
    view = ResultsView()
    assert view.molecule_uuid() == ""
    assert not view._empty.isHidden()
    assert view._empty.text() == EMPTY_MESSAGES[NO_MOLECULE]
    assert view._view.isHidden()
    dispose(view)


def _folded_fact(label: str) -> Fact:
    """A fact in a category `DEFAULT_EXPANDED` does NOT hold.

    The file's own `_fact` is `IDENTITY`, which is one of the two that open
    by default -- so a report built from it cannot show a fold either way,
    and both guards below would pass whatever the code did. TOPOLOGY is the
    category the driven defect was found in.
    """
    return Fact(
        category=FactCategory.TOPOLOGY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )


def _folded_report(report_id: str, name: str) -> ReportResult:
    return ReportResult(
        molecule_uuid="mol-1",
        report_id=report_id,
        name=name,
        category="topology",
        facts=(_folded_fact(f"{name} index"),),
    )


def test_a_focused_report_opens_with_its_answer_visible(qapp):
    """**THE ANSWER BEHIND A FOLD, FOR THE SECOND TIME IN THIS REPOSITORY.**

    `DEFAULT_EXPANDED` is a default for a LARGE report -- its own docstring
    says "a hundred-odd facts rendered flat is a wall" -- and the reader
    focused on ONE producer is not that. Driven, focusing Topology Analysis
    showed a title and a folded `Topology (27)`: everything asked for, one
    click away, with every test green because nothing asserted a section's
    initial state.

    The complement matters as much and is asserted below: All results IS
    the wall `DEFAULT_EXPANDED` exists for.
    """
    view = ResultsView("mol-1")
    view.set_reports([_folded_report("topology", "Topology Analysis")])
    view.set_focus("topology")

    sections = view._view.findChildren(CollapsibleSection)
    assert sections, "setup: the report must render at least one section"
    folded = [s for s in sections if not s.is_expanded()]
    assert not folded, (
        f"{len(folded)} of {len(sections)} section(s) opened folded on a report "
        "somebody explicitly focused"
    )
    dispose(view)


def test_all_results_still_opens_folded_because_it_IS_the_wall(qapp):
    """The narrow half. "Expand everything, always" satisfies the guard
    above and undoes the reason `DEFAULT_EXPANDED` exists -- every producer
    for the molecule at once, rendered flat."""
    view = ResultsView("mol-1")
    view.set_reports(
        [
            _folded_report("topology", "Topology Analysis"),
            _folded_report("lewis", "Lewis Sites"),
        ]
    )
    view.set_focus("")

    sections = view._view.findChildren(CollapsibleSection)
    assert sections, "setup: the merged view must render sections"
    assert any(not s.is_expanded() for s in sections), (
        "All results must keep the default fold -- it is the wall the "
        "default exists for"
    )
    dispose(view)
