"""Results lists method groups, Quantum run ids, and history delete."""

from __future__ import annotations

from openchem.ui.result_summary import ResultSummaryView
from openchem.ui.widgets.results_view import METHOD_FOLD_PREFIX, ResultsView


def _charge(report_id: str, method: str, *, historical: bool = False) -> ResultSummaryView:
    return ResultSummaryView(
        report_id=report_id,
        name=f"Partial Charge (3D) · {method}",
        category="charge",
        method_model=method,
        history_kind="execution",
        history_id=report_id.split(":", 1)[-1],
        historical=historical,
        order_id="geometry_partial_charge",
    )


def test_showing_lists_collapsible_method_groups(qapp):
    reader = ResultsView("m")
    reader.set_reports([_charge("exec:eem", "eem"), _charge("exec:qeq", "qeq")])
    texts = [reader._focus_box.itemText(i) for i in range(reader._focus_box.count())]
    assert any("eem" in text for text in texts)
    assert any("qeq" in text for text in texts)
    folds = [
        i
        for i in range(reader._focus_box.count())
        if str(reader._focus_box.itemData(i) or "").startswith(METHOD_FOLD_PREFIX)
    ]
    assert folds
    before = reader._focus_box.count()
    reader._focus_box.setCurrentIndex(folds[0])
    after = reader._focus_box.count()
    assert after != before or reader._collapsed_groups


def test_historical_method_groups_start_collapsed(qapp):
    reader = ResultsView("m")
    reader.set_reports([_charge("exec:old", "eem", historical=True)])
    texts = [reader._focus_box.itemText(i) for i in range(reader._focus_box.count())]
    assert any(text.startswith("▸") for text in texts)


def test_quantum_run_rows_use_qc_report_ids(qapp):
    reader = ResultsView("m")
    reader.set_reports(
        [
            ResultSummaryView(
                report_id="qc:abcd1234ffff",
                name="nmr · orca · B3LYP def2-SVP · abcd1234",
                category="quantum_chemistry",
                method_model="orca B3LYP def2-SVP",
                history_kind="quantum",
                history_id="abcd1234ffff",
            )
        ]
    )
    ids = [reader._focus_box.itemData(i) for i in range(reader._focus_box.count())]
    assert "qc:abcd1234ffff" in ids


def test_delete_from_history_is_not_offered_on_a_cache_only_row(qapp):
    from PySide6.QtWidgets import QMenu

    from openchem.ui.widgets.fact_view import FactView

    view = FactView()
    view.set_report(
        ResultSummaryView(report_id="MolWt", name="Molecular weight", category="molecular"),
        "Molecular weight",
        "",
    )
    menu = QMenu()
    view._add_report_actions(menu)
    labels = [action.text() for action in menu.actions() if action.text()]
    assert "Delete from history..." not in labels


def test_named_compare_dialog_is_a_table(qapp):
    from openchem.domain.history_compare import NamedCompareRow
    from openchem.ui.dialogs.compare_results_dialog import NamedValueCompareDialog

    dialog = NamedValueCompareDialog(
        [NamedCompareRow("logS", "-0.5", "-0.2", 0.3)],
        "solubility · a",
        "solubility · b",
        "water",
    )
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "logS"
    assert "logS" in dialog.table_text()


def test_delete_from_history_is_offered_on_a_history_row(qapp):
    from PySide6.QtWidgets import QMenu

    from openchem.ui.widgets.fact_view import FactView

    view = FactView()
    report = _charge("exec:eem", "eem")
    view.set_report(report, "Partial Charge", "")
    menu = QMenu()
    view._add_report_actions(menu)
    labels = [action.text() for action in menu.actions() if action.text()]
    assert "Delete from history..." in labels
