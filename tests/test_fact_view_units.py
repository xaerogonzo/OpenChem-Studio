"""Switching a result's unit in the reader, with nothing recomputed.

Solubility used to take its unit as a calculation parameter, so reading the
same curve in mg/mL instead of log mol/L meant running the calculator again
for numbers it had already produced. The result now declares its renderings
and the reader chooses among them; these pin the three states a result can
be in -- none declared, a complete declaration, a declaration that does not
hold -- and that everything a reader takes away follows the choice.
"""

from __future__ import annotations

import dataclasses

from rdkit import Chem

from openchem.chem.solubility import MG_PER_ML, UNIT_KEYS, compute_solubility
from openchem.domain.merged_results import merge_reports
from openchem.domain.report import LineRendering, LineSeries, rendering_state
from openchem.ui.report_format import format_report
from openchem.ui.widgets.fact_view import FactView

import conftest

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


def _solubility():
    return compute_solubility(Chem.MolFromSmiles(ASPIRIN), "u", {"pka_values": "3.49"})


def _view(report) -> FactView:
    view = FactView()
    view.resize(900, 700)
    view.set_report(report, "Solubility")
    return view


def test_a_result_that_declares_its_units_offers_them(qapp):
    view = _view(_solubility())
    try:
        assert not view._rendering_widget.isHidden()
        labels = [view._rendering_box.itemText(i) for i in range(view._rendering_box.count())]
        assert labels == ["log mol/L", "mg/mL", "mol/L"]
        assert view.rendering() == UNIT_KEYS["logS (log mol/L)"]
    finally:
        conftest.dispose(view)


def test_switching_changes_the_facts_the_chart_and_the_copy_and_runs_nothing(qapp, monkeypatch):
    import openchem.chem.solubility as solubility

    report = _solubility()
    view = _view(report)
    try:
        # Anything recomputed would have to come through here.
        monkeypatch.setattr(solubility, "analyse_solubility", lambda *a, **k: (_ for _ in ()).throw(AssertionError("recomputed")))
        before_labels = view.visible_fact_labels()
        before_chart = view._report.charts[0]

        view.set_rendering(UNIT_KEYS[MG_PER_ML])

        after_labels = view.visible_fact_labels()
        assert any("(mg/mL)" in label for label in after_labels), after_labels
        assert not any("(log mol/L)" in label for label in after_labels), after_labels
        assert before_labels != after_labels

        chart = view._report.charts[0]
        assert "mg/mL" in chart.y_label and "mg/mL" not in before_chart.y_label
        assert [x for x, _ in chart.series[0].points] == [x for x, _ in before_chart.series[0].points]

        copied = format_report(view._report, "Plain text")
        assert "mg/mL" in copied and "log mol/L" not in copied.split("Solubility category")[0]
        assert view.report() is report, "the source report must stay whole for a caller"
    finally:
        conftest.dispose(view)


def test_the_choice_is_remembered_per_result(qapp):
    report = _solubility()
    view = _view(report)
    try:
        view.set_rendering(UNIT_KEYS[MG_PER_ML])
        view.set_report(dataclasses.replace(report, report_id="other"), "Other")
        assert view.rendering() == UNIT_KEYS["logS (log mol/L)"], "another result opens on its default"
        view.set_report(report, "Solubility")
        assert view.rendering() == UNIT_KEYS[MG_PER_ML]
    finally:
        conftest.dispose(view)


def test_a_result_with_no_renderings_offers_no_choice(qapp):
    """An old stored result, or any result with one way to be read."""
    report = dataclasses.replace(_solubility(), renderings=())
    view = _view(report)
    try:
        assert view._rendering_widget.isHidden()
        assert "Units cannot be switched" not in view.status_text()
    finally:
        conftest.dispose(view)


def test_a_declaration_that_does_not_hold_offers_no_choice_and_says_why(qapp):
    """Present is not complete: a rendering whose x grid differs would change
    the curve under the cursor, not its unit."""
    report = _solubility()
    chart = report.charts[0]
    broken_series = tuple(
        LineSeries(points=tuple((x + 0.5, y) for x, y in series.points), name=series.name)
        for series in chart.renderings[1].series
    )
    broken = dataclasses.replace(
        chart,
        renderings=(chart.renderings[0], LineRendering(
            key=chart.renderings[1].key, series=broken_series, y_label=chart.renderings[1].y_label,
        ), chart.renderings[2]),
    )
    bad = dataclasses.replace(report, charts=(broken,))
    assert rendering_state(bad)[0] == "invalid"

    view = _view(bad)
    try:
        assert view._rendering_widget.isHidden()
        assert "Units cannot be switched" in view.status_text()
        # Readable, in its default form: every fact is still there.
        assert len(view._report.facts) == len(bad.facts)
    finally:
        conftest.dispose(view)


def test_all_results_shows_one_unit_per_quantity():
    """The flattened view keeps each report's DEFAULT rendering, so the
    intrinsic solubility is not listed three times."""
    report = _solubility()
    merged = merge_reports([report])
    intrinsic = [f for f in merged.facts if f.label.startswith("Predicted intrinsic solubility")]
    assert len(intrinsic) == 1 and "(log mol/L)" in intrinsic[0].label


def test_the_mutation_that_stops_filtering_is_caught(qapp):
    """Guard on the guard: with every rendering's facts shown, the view
    lists the intrinsic solubility three times -- which the tests above
    would call a pass only if they read the wrong thing."""
    report = _solubility()
    view = _view(report)
    try:
        intrinsic = [label for label in view.visible_fact_labels() if label.startswith("Predicted intrinsic")]
        assert len(intrinsic) == 1, intrinsic
    finally:
        conftest.dispose(view)
