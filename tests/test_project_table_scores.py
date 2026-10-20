"""The scores a person defined, as columns of the Results dock's project table (slice 3c of `docs/DERIVED_SCORES_DESIGN.md`).

The view is handed a table by hand (so every way a cell can be refused is one row) and the same table goes through the real exports; the real run, the real
window and the parity with the Results reader are in `test_main_window_scores.py`.
"""

from __future__ import annotations

import csv
import dataclasses

import pytest
from PySide6.QtWidgets import QWidget

from openchem.bootstrap import build_service_container
from openchem.domain.batch import BatchCell, BatchColumn, BatchResultStore, BatchTable
from openchem.domain.common import CacheState
from openchem.domain.score_definition import DISPLAY_SUFFIX, ScoreDefinition
from openchem.domain.score_outputs import approved_output
from openchem.events.events import ScoreDefinitionsChanged
from openchem.services.batch_service import BatchProgress
from openchem.ui.widgets.project_table import ProjectTableView
from openchem.ui.widgets.results_workspace import ResultsWorkspace
from openchem.ui.widgets.sortable_item import SORT_ROLE

_TPSA = "descriptor:tpsa"
_LOGP = "descriptor:mol_logp"
_ROWS = ("aspirin-uuid", "ethanol-uuid")
_LABEL = f"Window {DISPLAY_SUFFIX}"


def _column(output_id: str) -> BatchColumn:
    kind, _, rest = output_id.partition(":")
    return BatchColumn(column_id=output_id, label=rest, units=approved_output(output_id).carried_as, source=kind, source_id=rest, numeric=True)


def _table(*, logp=True) -> BatchTable:
    table = BatchTable()
    for uuid, label in zip(_ROWS, ("Aspirin", "Ethanol")):
        table.add_row(uuid, label)
    series = [(_TPSA, (63.6, 20.2))] + ([(_LOGP, (1.31, -0.0014))] if logp else [])
    for output_id, values in series:
        table.add_column(_column(output_id))
        for uuid, value in zip(_ROWS, values):
            table.set_cell(uuid, output_id, BatchCell(value=value, text=f"{value:.4g}"))
    return table


def _definition(**changes) -> ScoreDefinition:
    base = dict(
        score_id="user.window", label="Window", formula="ramp(psa, 140, 60) * ramp(logp, 5, 2)", result_unit="1",
        inputs=(("psa", _TPSA), ("logp", _LOGP)), schema_version=1, owner="", created="2026-10-15", note="",
    )
    base.update(changes)
    return ScoreDefinition(**base)


def _event(table: BatchTable, state=CacheState.COMPLETED) -> BatchProgress:
    return BatchProgress(state=state, completed=2, total=2, message="2 molecules.", table=table, store=BatchResultStore())


class Definitions:
    """The project's scores as the window holds them: a list the test edits, handed to the view as a callable."""

    def __init__(self, *items):
        self.items = list(items)

    def __call__(self):
        return tuple(self.items)


@pytest.fixture
def services(qapp):
    return build_service_container()


def _view(services, definitions=None, **kwargs) -> ProjectTableView:
    return ProjectTableView(services.calculator_registry, services.table_export_service, None, score_definitions=definitions, **kwargs)


def _headers(view) -> list[str]:
    grid = view._results
    return [grid.horizontalHeaderItem(i).text() for i in range(grid.columnCount())]


def _column_of(view, header_start: str) -> int:
    return next(i for i, text in enumerate(_headers(view)) if text.startswith(header_start))


# --- the grid ----------------------------------------------------------------------------------------------------------------------------


def test_without_a_score_provider_the_table_is_what_the_run_made(services):
    view = _view(services)
    view.apply_progress(_event(_table()), adopt=True)
    assert _headers(view) == ["Molecule", f"tpsa ({approved_output(_TPSA).carried_as})", "mol_logp"]


def test_a_score_column_is_the_first_column_after_the_molecule(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    assert _headers(view)[:2] == ["Molecule", _LABEL]


def test_a_score_is_a_column_of_the_grid_with_the_suffix_in_its_header_and_a_number_in_each_row(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    column = _column_of(view, "Window")
    assert _headers(view)[column] == _LABEL
    grid = view._results
    texts = {grid.item(row, 0).text(): grid.item(row, column).text() for row in range(grid.rowCount())}
    assert set(texts) == {"Aspirin", "Ethanol"} and all(float(text) > 0 for text in texts.values())
    assert grid.item(0, column).data(SORT_ROLE) == float(grid.item(0, column).text()) or isinstance(grid.item(0, column).data(SORT_ROLE), float)


def test_a_score_column_sorts_as_a_number(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    column = _column_of(view, "Window")
    for row in range(2):
        assert isinstance(view._results.item(row, column).data(SORT_ROLE), float)


def test_the_run_s_own_table_is_never_written_into(services):
    raw = _table()
    before = ([c.column_id for c in raw.columns], dict(raw.cells))
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(raw), adopt=True)
    assert ([c.column_id for c in raw.columns], dict(raw.cells)) == before
    assert [c.column_id for c in view.table().columns][0] == "score:user.window" and view.table() is not raw


def test_the_table_the_exports_and_the_analytics_get_has_the_score_column(services):
    seen = []
    view = _view(services, Definitions(_definition()), on_analyse=seen.append)
    view.apply_progress(_event(_table()), adopt=True)
    view._analyse()
    assert [c.column_id for c in seen[0].columns][0] == "score:user.window"


# --- following the definitions -----------------------------------------------------------------------------------------------------------


def test_a_score_defined_after_the_run_appears_without_another_run(services):
    definitions = Definitions()
    view = _view(services, definitions)
    view.apply_progress(_event(_table()), adopt=True)
    assert not any(text.startswith("Window") for text in _headers(view))
    definitions.items.append(_definition())
    view.refresh_scores()
    assert any(text == _LABEL for text in _headers(view))


def test_an_edited_score_changes_its_numbers_and_a_removed_one_goes(services):
    definitions = Definitions(_definition())
    view = _view(services, definitions)
    view.apply_progress(_event(_table()), adopt=True)
    column = _column_of(view, "Window")
    before = view._results.item(0, column).text()
    definitions.items[:] = [_definition(formula="ramp(psa, 100, 60)", inputs=(("psa", _TPSA),))]
    view.refresh_scores()
    assert view._results.item(0, _column_of(view, "Window")).text() != before
    definitions.items.clear()
    view.refresh_scores()
    assert not any(text.startswith("Window") for text in _headers(view))


def test_refreshing_before_any_run_does_nothing(services):
    view = _view(services, Definitions(_definition()))
    view.refresh_scores()
    assert view.table() is None


def test_a_score_whose_input_the_run_did_not_compute_is_not_a_column_and_the_note_says_why(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table(logp=False)), adopt=True)
    assert not any(text.startswith("Window") for text in _headers(view))
    assert not view._score_note.isHidden() and view._score_note.text().startswith("Scores not shown, because this run did not compute what they read:")
    assert "mol_logp" in view._score_note.text() and _LABEL in view._score_note.text()


def test_the_note_is_gone_when_nothing_is_missing(services):
    definitions = Definitions(_definition())
    view = _view(services, definitions)
    view.apply_progress(_event(_table(logp=False)), adopt=True)
    assert not view._score_note.isHidden()
    view.apply_progress(_event(_table()), adopt=True)
    assert view._score_note.isHidden() and view._score_note.text() == ""


def test_a_partly_filled_table_during_a_run_has_the_score_for_the_rows_that_are_in(services):
    table = _table()
    for output_id in (_TPSA, _LOGP):
        del table.cells[(_ROWS[1], output_id)]
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(table, CacheState.RUNNING), adopt=True)
    column = _column_of(view, "Window")
    cells = {view._results.item(row, 0).text(): view._results.item(row, column).text() for row in range(2)}
    assert cells["Aspirin"] != "" and cells["Ethanol"] == ""


def test_a_one_molecule_detail_run_does_not_replace_the_table_or_its_scores(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    before = view.table()
    view.apply_progress(_event(BatchTable()), adopt=False)
    assert view.table() is before


# --- a refused row -----------------------------------------------------------------------------------------------------------------------


def test_a_row_whose_input_failed_shows_a_dash_and_says_why_on_hover(services):
    table = _table()
    table.set_cell(_ROWS[1], _LOGP, BatchCell(text="", cache_state=CacheState.FAILED, error="boom"))
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(table), adopt=True)
    column = _column_of(view, "Window")
    row = next(i for i in range(2) if view._results.item(i, 0).text() == "Ethanol")
    item = view._results.item(row, column)
    assert item.text() == "—" and "logp (descriptor:mol_logp): boom" in item.toolTip()


def test_a_score_cell_s_tooltip_names_the_formula_the_unit_and_that_nothing_validated_it(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    tip = view._results.item(0, _column_of(view, "Window")).toolTip()
    assert "user / derived_score:1" in tip and "validation = user_defined_unvalidated" in tip and "Inputs: psa = 63.6" in tip and "logp = 1.31" in tip


def test_the_column_s_tooltip_says_what_it_is(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    tip = view._results.horizontalHeaderItem(_column_of(view, "Window")).toolTip()
    assert "Source: score / user.window" in tip and "Formula: ramp(psa, 140, 60) * ramp(logp, 5, 2)" in tip
    assert "Reads: psa = tpsa; logp = mol_logp" in tip and "Nothing has checked it against measurements" in tip


# --- the Columns menu --------------------------------------------------------------------------------------------------------------------


def test_the_score_columns_are_their_own_group_and_the_group_can_be_hidden(services):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    column = next(c for c in view.table().columns if c.source == "score")
    assert view._column_category(column) == "Derived scores"
    view._hidden_categories.add("Derived scores")
    view._apply_column_visibility()
    index = _column_of(view, "Window")
    assert view._results.isColumnHidden(index) and not view._results.isColumnHidden(index + 1)


def test_a_hidden_group_stays_hidden_when_the_definitions_change(services):
    definitions = Definitions(_definition())
    view = _view(services, definitions)
    view.apply_progress(_event(_table()), adopt=True)
    view._hidden_categories.add("Derived scores")
    view._apply_column_visibility()
    definitions.items.append(_definition(score_id="user.other", label="Other", formula="ramp(psa, 140, 60)", inputs=(("psa", _TPSA),)))
    view.refresh_scores()
    assert view._results.isColumnHidden(_column_of(view, "Window")) and view._results.isColumnHidden(_column_of(view, "Other"))


# --- the exports -------------------------------------------------------------------------------------------------------------------------


def test_the_csv_has_the_score_with_its_suffix_and_its_full_precision_number(services, tmp_path):
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(_table()), adopt=True)
    path = tmp_path / "table.csv"
    services.table_export_service.export_csv(view.table(), path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][1] == _LABEL
    scored = {row[0]: row[1] for row in rows[1:]}
    expected = view.table().cell(_ROWS[0], "score:user.window").value
    assert float(scored["Aspirin"]) == expected and repr(expected) == scored["Aspirin"], "the number is written whole, not as the four digits the grid shows"


def test_a_refused_row_is_an_empty_csv_cell_and_never_a_zero(services, tmp_path):
    table = _table()
    table.set_cell(_ROWS[1], _LOGP, BatchCell(text="", cache_state=CacheState.FAILED, error="boom"))
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(table), adopt=True)
    path = tmp_path / "table.csv"
    services.table_export_service.export_csv(view.table(), path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = {row[0]: row[1] for row in csv.reader(handle)}
    assert rows["Ethanol"] == "" and rows["Aspirin"] != ""


def test_the_report_says_the_score_is_a_user_s_formula_and_why_a_row_has_none(services):
    table = _table()
    table.set_cell(_ROWS[1], _LOGP, BatchCell(text="", cache_state=CacheState.FAILED, error="boom"))
    view = _view(services, Definitions(_definition()))
    view.apply_progress(_event(table), adopt=True)
    report = services.table_export_service.render_report(view.table())
    section = report.split(f"### {_LABEL}")[1].split("###")[0]
    assert "Source: `score` / `user.window`" in section and "Method: user/derived_score:1" in section
    assert "- Note: Formula: ramp(psa, 140, 60) * ramp(logp, 5, 2). Reads: psa = tpsa; logp = mol_logp." in section
    assert "A formula a person wrote. Nothing has checked it against measurements." in section
    assert "Values: 1 of 2 molecules" in section and "Failed for 1: logp (descriptor:mol_logp): boom" in section
    assert "Basis" not in section


# --- the Results dock --------------------------------------------------------------------------------------------------------------------


def test_the_workspace_rebuilds_the_score_columns_when_a_definition_changes(services):
    definitions = Definitions()
    workspace = ResultsWorkspace(
        QWidget(), services.calculator_registry, services.table_export_service, services.event_bus, services.chemistry_engine,
        score_definitions=definitions,
    )
    workspace.table_view.apply_progress(_event(_table()), adopt=True)
    assert not any(c.source == "score" for c in workspace.table_view.table().columns)
    definitions.items.append(_definition())
    services.event_bus.publish(ScoreDefinitionsChanged(project_uuid="p", score_ids=("user.window",)))
    assert any(c.source == "score" for c in workspace.table_view.table().columns)
    assert dataclasses.is_dataclass(ScoreDefinitionsChanged)


# --- the Batch panel's own table ---------------------------------------------------------------------------------------------------------


def _batch_panel(services, definitions):
    from openchem.ui.panels.batch_panel import BatchPanel

    return BatchPanel(
        services.batch_service, services.calculator_registry, services.table_export_service, services.event_bus, services.chemistry_engine, None,
        score_definitions=definitions,
    )


def _batch_headers(panel) -> list[str]:
    grid = panel._results
    return [grid.horizontalHeaderItem(i).text() for i in range(grid.columnCount())]


def test_the_batch_panel_s_own_table_has_the_score_column_when_the_run_it_adopts_lands(services):
    panel = _batch_panel(services, Definitions(_definition()))
    panel._filling_table = True
    services.event_bus.publish(_event(_table()))
    assert [h for h in _batch_headers(panel) if h.startswith("Window")] == [_LABEL]
    assert panel._view.table().columns[0].source == "score"


def test_the_batch_panel_s_scores_follow_a_definition_without_a_second_run(services):
    definitions = Definitions()
    panel = _batch_panel(services, definitions)
    panel._filling_table = True
    services.event_bus.publish(_event(_table()))
    assert not any(h.startswith("Window") for h in _batch_headers(panel))
    definitions.items.append(_definition())
    services.event_bus.publish(ScoreDefinitionsChanged(project_uuid="p", score_ids=("user.window",)))
    assert [h for h in _batch_headers(panel) if h.startswith("Window")] == [_LABEL]
    definitions.items.clear()
    services.event_bus.publish(ScoreDefinitionsChanged(project_uuid="p", score_ids=("user.window",)))
    assert not any(h.startswith("Window") for h in _batch_headers(panel))


def test_the_batch_panel_says_which_score_has_no_column_because_the_run_did_not_compute_its_inputs(services):
    panel = _batch_panel(services, Definitions(_definition()))
    panel._filling_table = True
    services.event_bus.publish(_event(_table(logp=False)))
    assert not any(h.startswith("Window") for h in _batch_headers(panel))
    assert not panel._view._score_note.isHidden() and "mol_logp" in panel._view._score_note.text()


def test_a_batch_panel_built_without_a_score_provider_shows_the_run_s_table_alone(services):
    panel = _batch_panel(services, None)
    panel._filling_table = True
    services.event_bus.publish(_event(_table()))
    assert not any(c.source == "score" for c in panel._view.table().columns)
    services.event_bus.publish(ScoreDefinitionsChanged(project_uuid="p", score_ids=()))


def test_a_one_molecule_detail_run_does_not_replace_the_batch_panel_s_table_or_its_scores(services):
    panel = _batch_panel(services, Definitions(_definition()))
    panel._filling_table = True
    services.event_bus.publish(_event(_table()))
    narrow = BatchTable()
    narrow.add_row(_ROWS[0], "Aspirin")
    panel._filling_table = False
    services.event_bus.publish(_event(narrow))
    assert panel._results.rowCount() == 2 and [h for h in _batch_headers(panel) if h.startswith("Window")] == [_LABEL]
