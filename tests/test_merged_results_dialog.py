"""The merged results window: one per molecule, modeless, live.

Four of these are LIFECYCLE tests. The window is now subscribed to results
arriving and keyed on an identity, and none of that is covered by the
merge being correct -- an ordinary Qt lifetime bug is exactly the class a
domain-level test cannot see.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from openchem.domain.report import (
    ArrowAnnotation,
    Basis,
    Fact,
    FactCategory,
    ReportResult,
    Stick,
    StickChartAnnotation,
)
from openchem.ui.dialogs.merged_results_dialog import (
    ALL_RESULTS,
    STALE_MARK,
    MergedResultsDialog,
)
from tests.conftest import dispose


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


def _report(report_id, name, labels, charts=(), spatial=(), version=0) -> ReportResult:
    return ReportResult(
        molecule_uuid="mol-1",
        report_id=report_id,
        name=name,
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
    window = MergedResultsDialog("mol-1", "Butyryl Fentanyl")
    window.set_reports(_two())
    assert [f.label for f in window.merged().facts] == ["Formula", "Donor sites"]
    dispose(window)


def test_the_filter_now_has_something_to_filter(qapp):
    """`FactView`'s search was built for a hundred facts and was being
    handed one calculator's four."""
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    view = window._view
    view.search_box().setText("donor")
    assert view.visible_fact_labels() == ["Donor sites"]
    dispose(window)


def test_the_search_also_matches_the_producing_calculator(qapp):
    """`Fact.origin` is stamped by the merge, so "show me everything the
    Lewis calculator said" is a question the box can answer."""
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    window._view.search_box().setText("lewis_sites")
    assert window._view.visible_fact_labels() == ["Donor sites"]
    dispose(window)


# --- focus ---------------------------------------------------------------


def test_a_details_button_arrives_focused_on_its_own_report(qapp):
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    window.set_focus("lewis_sites")
    assert window.focus() == "lewis_sites"
    assert window._view.visible_fact_labels() == ["Donor sites"]
    dispose(window)


def test_focusing_one_report_never_shows_anothers_chart(qapp):
    """Once several calculators contribute a chart, "the first chart" stops
    being an answer to anything."""
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    window.set_focus("elemental_analysis")
    titles = [w.annotation().title for w in window._view.chart_widgets()]
    assert titles == ["Isotope pattern"]
    window.set_focus("lewis_sites")
    titles = [w.annotation().title for w in window._view.chart_widgets()]
    assert titles == ["Sites"]
    dispose(window)


def test_showing_everything_shows_every_chart(qapp):
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    titles = [w.annotation().title for w in window._view.chart_widgets()]
    assert titles == ["Isotope pattern", "Sites"]
    dispose(window)


def test_focus_is_by_report_id_and_an_unknown_one_falls_back_to_all(qapp):
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    window.set_focus("no_such_calculator")
    assert window.focus() == ""
    assert len(window._view.chart_widgets()) == 2
    dispose(window)


def test_the_focus_control_lists_every_calculator_by_name(qapp):
    """Never a prettified id: the window asks the container, which asks the
    report."""
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    labels = [window._focus_box.itemText(i) for i in range(window._focus_box.count())]
    assert labels == [ALL_RESULTS, "Elemental Analysis", "Lewis Sites"]
    dispose(window)


# --- staleness -----------------------------------------------------------


def test_a_stale_report_is_marked_and_kept(qapp):
    """**REPORTED, NEVER DISCARDED.** Silently serving a stale result and
    silently blanking it are the two ways this goes wrong, and they look
    identical from outside."""
    old = _report("lewis_sites", "Lewis Sites", ["Donor sites"], version=1)
    new = _report("elemental_analysis", "Elemental Analysis", ["Formula"], version=2)
    window = MergedResultsDialog("mol-1")
    window.set_reports([old, new], structure_version=2)
    labels = [window._focus_box.itemText(i) for i in range(window._focus_box.count())]
    assert labels == [ALL_RESULTS, "Lewis Sites" + STALE_MARK, "Elemental Analysis"]
    assert len(window.merged().facts) == 2, "neither is discarded"
    dispose(window)


def test_a_focused_stale_report_says_so_above_its_facts(qapp):
    old = _report("lewis_sites", "Lewis Sites", ["Donor sites"], version=1)
    window = MergedResultsDialog("mol-1")
    window.set_reports([old], structure_version=2)
    window.set_focus("lewis_sites")
    assert "earlier version" in window._view._summary.text()
    dispose(window)


def test_the_stale_marks_update_in_an_OPEN_window(qapp):
    """**THE LIFECYCLE TEST, NOT THE SYNCHRONOUS ONE.** The behaviour a
    user experiences is editing the molecule while the window is open, and
    a merge that is only correct at construction never shows it."""
    report = _report("lewis_sites", "Lewis Sites", ["Donor sites"], version=1)
    window = MergedResultsDialog("mol-1")
    window.set_reports([report], structure_version=1)
    assert window._focus_box.itemText(1) == "Lewis Sites"
    # The structure moves under it, and the same reports are pushed again.
    window.set_reports([report], structure_version=2)
    assert window._focus_box.itemText(1) == "Lewis Sites" + STALE_MARK
    dispose(window)


# --- the empty state -----------------------------------------------------


def test_nothing_computed_says_so_rather_than_showing_an_empty_report(qapp):
    """"Nothing has been computed" and "everything ran and had nothing to
    say" are different statements, and an empty report makes the second
    one."""
    window = MergedResultsDialog("mol-1")
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
    window = MergedResultsDialog("mol-1")
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
    window = MergedResultsDialog("mol-1")
    window.set_reports(_two())
    formula = next(f for f in window.merged().facts if f.label == "Formula")
    assert formula.source == "RDKit"
    assert formula.origin == "elemental_analysis"
    dispose(window)


def test_spatial_annotations_keep_their_owner(qapp):
    arrow = ArrowAnnotation(
        anchor=(0.0, 0.0, 0.0), vector=(1.0, 0.0, 0.0), units="D", label="mu"
    )
    window = MergedResultsDialog("mol-1")
    window.set_reports([
        _report("dipole", "Dipole Moment", ["Dipole"], spatial=[arrow]),
        _report("lewis_sites", "Lewis Sites", ["Donor sites"]),
    ])
    assert window.merged().spatial_for("dipole") == (arrow,)
    assert window.merged().spatial_for("lewis_sites") == ()
    dispose(window)
