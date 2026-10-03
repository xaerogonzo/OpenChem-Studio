"""Copy or save a panel's table as CSV (the survey's item 5)."""

from __future__ import annotations

import csv
import io

import pytest
from PySide6.QtWidgets import QFileDialog, QTableWidget, QTableWidgetItem

from openchem.services.table_export_service import rows_to_csv_text, write_rows_csv
from openchem.ui.table_export import (
    copy_table_csv,
    export_table_csv,
    install_table_export,
    table_rows,
)


def _table(rows=(("a", "1.5"), ("b", "2"))):
    table = QTableWidget(len(rows), 2)
    table.setHorizontalHeaderLabels(["Name", "Value (Å)"])
    for r, (name, value) in enumerate(rows):
        table.setItem(r, 0, QTableWidgetItem(name))
        table.setItem(r, 1, QTableWidgetItem(value))
    return table


def test_the_table_is_read_as_displayed_headers_then_rows(qapp):
    headers, rows = table_rows(_table())
    assert headers == ["Name", "Value (Å)"] and rows == [["a", "1.5"], ["b", "2"]]


def test_hidden_columns_and_rows_are_left_out(qapp):
    table = _table((("a", "1"), ("b", "2"), ("c", "3")))
    table.setColumnHidden(1, True)
    table.setRowHidden(1, True)
    assert table_rows(table) == (["Name"], [["a"], ["c"]])


def test_columns_follow_the_order_the_user_dragged_them_into(qapp):
    table = _table()
    table.horizontalHeader().moveSection(0, 1)
    headers, rows = table_rows(table)
    assert headers == ["Value (Å)", "Name"] and rows[0] == ["1.5", "a"]


def test_a_cell_with_no_item_is_empty_not_a_crash(qapp):
    table = QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(["x", "y"])
    table.setItem(0, 0, QTableWidgetItem("only"))
    assert table_rows(table)[1] == [["only", ""]]


def test_a_cell_that_starts_like_a_formula_is_protected():
    """A spreadsheet evaluates `=...`, `+...`, `-...` and `@...`; panel text can start with any."""
    text = rows_to_csv_text(["h"], [["=1+1"], ["-alert"], ["fine"]])
    cells = [row[0] for row in csv.reader(io.StringIO(text))]
    assert cells == ["h", "'=1+1", "'-alert", "fine"]


def test_the_file_has_a_bom_so_excel_reads_the_units(tmp_path):
    path = tmp_path / "t.csv"
    write_rows_csv(path, ["Å"], [["µ"]])
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert path.read_text(encoding="utf-8-sig").splitlines() == ["Å", "µ"]


def test_copying_puts_csv_text_on_the_clipboard(qapp):
    from PySide6.QtGui import QGuiApplication

    QGuiApplication.clipboard().clear()
    message = copy_table_csv(_table())
    assert message == "Copied 2 row(s) as CSV."
    assert QGuiApplication.clipboard().text().splitlines() == ["Name,Value (Å)", "a,1.5", "b,2"]


def test_an_empty_table_says_so_instead_of_writing_an_empty_file(qapp, tmp_path, monkeypatch):
    empty = QTableWidget(0, 2)
    assert "nothing" in copy_table_csv(empty)
    called = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: called.append(1) or ("", "")))
    assert "nothing" in export_table_csv(empty, None, "t")
    assert not called  # never even asked where to put it


def test_export_writes_through_the_save_dialog_and_cancel_writes_nothing(qapp, tmp_path, monkeypatch):
    target = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    assert export_table_csv(_table(), None, "t") == "Exported 2 row(s) to out.csv."
    assert target.read_text(encoding="utf-8-sig").splitlines()[0] == "Name,Value (Å)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    other = tmp_path / "never.csv"
    assert export_table_csv(_table(), None, "t") == "" and not other.exists()


def test_the_default_file_name_comes_from_the_stem(qapp, monkeypatch):
    seen = []

    def fake(parent, caption, directory, filters):
        seen.append(directory)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    export_table_csv(_table(), None, "Docking Poses / run 2")
    assert seen == ["docking-poses-run-2.csv"]


def test_install_gives_the_table_a_menu_with_both_actions(qapp):
    table = _table()
    helper = install_table_export(table, "t")
    assert helper.parent() is table  # owned by the table, so it goes with it
    assert [a.text() for a in helper.build_menu().actions()] == ["Copy table as CSV", "Export CSV..."]


@pytest.mark.parametrize(
    ("module", "attributes"),
    [
        ("openchem.ui.panels.docking_panel", ["docking-poses"]),
        ("openchem.ui.panels.interactions_panel", ["interactions", "contacts"]),
        ("openchem.ui.panels.alignment_panel", ["alignment-results"]),
        ("openchem.ui.panels.quantum_chemistry_panel", ["orca-spectrum", "nmr-hybrid", "-correlations"]),
    ],
)
def test_every_result_panel_installs_the_menu_on_its_tables(module, attributes):
    """Asserted on the module's own source so a panel that grows a new results
    table is not silently left without one: each stem below must be installed."""
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(module))
    for stem in attributes:
        assert f'install_table_export(' in source and stem in source, (module, stem)
