"""`FactView`'s chart sections.

The channel's whole claim is that a chart is DECLARED by the producer and
never derived from what the facts happen to look like. Most of this file
exists to make that claim testable.
"""

from __future__ import annotations

from openchem.domain.report import (
    Basis,
    Fact,
    FactCategory,
    ReportResult,
    Stick,
    StickChartAnnotation,
    StructureReport,
)
from openchem.ui.widgets.fact_view import FactView
from tests.conftest import dispose


def _chart(title: str = "Isotope pattern") -> StickChartAnnotation:
    return StickChartAnnotation(
        sticks=(Stick(278.0, 0.51, "M"), Stick(280.0, 1.0, "M+2"), Stick(282.0, 0.49, "M+4")),
        x_label="m/z",
        y_label="Relative abundance",
        x_descending=False,
        title=title,
        caption="CALCULATED -- natural-abundance isotope distribution.",
    )


def _fact(label: str = "Formula", value: str = "C7H4Br2O2") -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=value,
        display_value=value,
        source="Elemental Analysis",
        basis=Basis.DETERMINISTIC,
    )


def _report(charts=(), facts=None) -> ReportResult:
    return ReportResult(
        molecule_uuid="u",
        report_id="elemental_analysis",
        name="Elemental Analysis",
        facts=tuple(facts if facts is not None else (_fact(),)),
        charts=tuple(charts),
    )


def test_one_chart_widget_per_declared_annotation(qapp):
    view = FactView()
    view.set_report(_report(charts=(_chart("A"), _chart("B"))))
    assert len(view.chart_widgets()) == 2
    dispose(view)


def test_a_report_that_declares_none_renders_none(qapp):
    view = FactView()
    view.set_report(_report())
    assert view.chart_widgets() == []
    dispose(view)


def test_a_chart_is_never_derived_from_the_facts(qapp):
    """**THE TEST THE WHOLE CHANNEL EXISTS TO MAKE POSSIBLE.** Elemental
    analysis really does emit "C: 30.04%" lines as facts, and a view that
    parsed those into bars would have invented a picture the producer never
    claimed. A picture reads as a result."""
    facts = [
        _fact("C", "30.04%"),
        _fact("H", "1.44%"),
        _fact("Br", "57.09%"),
        _fact("O", "11.43%"),
    ]
    view = FactView()
    view.set_report(_report(facts=facts))
    assert view.chart_widgets() == []
    dispose(view)


def test_a_report_type_with_no_charts_field_renders_none(qapp):
    """`StructureReport` -- what the Atom Inspector renders -- has no
    `charts` attribute at all, so reading `report.charts` would raise
    rather than return nothing."""
    report = StructureReport(molecule_uuid="u", facts=(_fact(),))
    assert not hasattr(report, "charts")
    view = FactView()
    view.set_report(report)
    assert view.chart_widgets() == []
    dispose(view)


def test_filtering_the_facts_does_not_destroy_the_charts(qapp):
    """`_render` clears and rebuilds the fact sections on every keystroke.
    A chart built in there would be destroyed and rebuilt per character --
    losing its expanded state, and rebuilding a painted widget for a filter
    that does not apply to it."""
    view = FactView()
    view.set_report(_report(charts=(_chart(),)))
    before = view.chart_widgets()
    view.search_box().setText("nothing matches this")
    after = view.chart_widgets()
    assert len(after) == 1
    assert after[0] is before[0], "the same widget, not a rebuilt one"
    dispose(view)


def test_a_filter_that_hides_every_fact_still_leaves_the_chart(qapp):
    """A chart is not a fact. Hiding a picture because its producer's LABEL
    did not match the needle would filter on something the reader cannot
    see."""
    view = FactView()
    view.set_report(_report(charts=(_chart(),)))
    view.search_box().setText("zzzz")
    assert view.visible_fact_labels() == []
    assert len(view.chart_widgets()) == 1
    dispose(view)


def test_the_first_chart_is_open_and_the_rest_are_folded(qapp):
    """A result whose whole point is its picture must not open on a heading
    where the picture should be -- `set_report`'s own docstring records
    that lesson from the formulation report. Several charts at once is the
    batch case, and five expanded plots is a wall of the same kind."""
    view = FactView()
    view.set_report(_report(charts=(_chart("A"), _chart("B"), _chart("C"))))
    states = [section.is_expanded() for section in view._chart_sections]
    assert states == [True, False, False]
    dispose(view)


def test_the_charts_sit_above_the_facts(qapp):
    """Where a picture of the result belongs, and the reason
    `_rebuild_charts` runs before `_render`."""
    view = FactView()
    view.set_report(_report(charts=(_chart(),)))
    layout = view._container_layout
    chart_index = layout.indexOf(view._chart_sections[0])
    fact_indexes = [layout.indexOf(section) for section in view._sections.values()]
    assert fact_indexes, "asserts its own setup: there ARE fact sections to be above"
    assert chart_index < min(fact_indexes)
    dispose(view)


def test_charts_stay_above_the_facts_even_if_they_are_rebuilt_later(qapp):
    """Asserts the property of `_rebuild_charts` itself, not of the order
    `set_report` happens to call things in.

    Found by mutation: inserting a chart section at the END of the
    container (before the stretch) rather than at an absolute index is
    equivalent TODAY, because `set_report` rebuilds the charts while the
    container holds nothing but the stretch. It stops being equivalent the
    moment anything rebuilds a chart after a render -- so this reaches that
    state deliberately and pins the invariant rather than the sequence.
    """
    view = FactView()
    view.set_report(_report(charts=(_chart(),)))
    view._rebuild_charts()
    layout = view._container_layout
    chart_index = layout.indexOf(view._chart_sections[0])
    fact_indexes = [layout.indexOf(section) for section in view._sections.values()]
    assert fact_indexes, "asserts its own setup: the fact sections are still there"
    assert chart_index < min(fact_indexes)
    dispose(view)


def test_a_surface_with_its_own_visualisation_opts_out(qapp):
    """`CalculatorInspectorDialog` already draws the result an inch above
    its facts; a second plot of the same numbers is not a second view."""
    view = FactView(show_charts=False)
    view.set_report(_report(charts=(_chart(),)))
    assert view.chart_widgets() == []
    dispose(view)


def test_showing_a_second_report_replaces_the_first_reports_charts(qapp):
    view = FactView()
    view.set_report(_report(charts=(_chart("A"), _chart("B"))))
    view.set_report(_report(charts=(_chart("C"),)))
    widgets = view.chart_widgets()
    assert len(widgets) == 1
    assert widgets[0].annotation().title == "C"
    dispose(view)


def test_clearing_removes_the_charts_too(qapp):
    view = FactView()
    view.set_report(_report(charts=(_chart(),)))
    view.clear()
    assert view.chart_widgets() == []
    dispose(view)


def test_open_in_window_carries_the_charts(qapp):
    view = FactView()
    view.set_report(_report(charts=(_chart(),)))
    dialog = view.open_in_window()
    assert dialog is not None
    detached = dialog.findChildren(FactView)
    assert detached and len(detached[0].chart_widgets()) == 1
    dispose(dialog)
    dispose(view)


def test_a_malformed_chart_is_refused_by_the_widget_it_reaches(qapp):
    """The view builds a section for whatever the producer declared; the
    widget is what refuses to draw a malformed one, so a bad annotation
    costs an empty plot rather than a broken window."""
    broken = StickChartAnnotation(
        sticks=(), x_label="m/z", y_label="I", x_descending=False
    )
    view = FactView()
    view.set_report(_report(charts=(broken,)))
    widgets = view.chart_widgets()
    assert len(widgets) == 1
    assert not widgets[0].is_drawing()
    dispose(view)
