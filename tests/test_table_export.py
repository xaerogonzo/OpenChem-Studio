"""The second export path: a table, not a structure.

Most of this is about the things that make an export quietly wrong rather
than obviously broken -- a BOM Excel needs, a re-rounded number that cannot
be un-rounded, a leading minus sign a spreadsheet evaluates, and a pipe
that shifts every Markdown column one to the left.
"""

from __future__ import annotations

from openchem.domain.batch import BatchCell, BatchColumn, BatchTable
from openchem.domain.common import CacheState, Provenance
from openchem.services.table_export_service import TableExportService


def _table() -> BatchTable:
    table = BatchTable()
    table.add_row("a", "aspirin")
    table.add_row("b", "caffeine")
    table.add_column(
        BatchColumn(
            column_id="descriptor:mol_wt",
            label="Molecular Weight",
            units="g/mol",
            source="descriptor",
            source_id="mol_wt",
        )
    )
    table.add_column(
        BatchColumn(
            column_id="descriptor:formula",
            label="Molecular Formula",
            source="descriptor",
            source_id="formula",
            numeric=False,
        )
    )
    table.add_column(
        BatchColumn(
            column_id="calculator:admet_ml:hERG blockade",
            label="hERG blockade",
            source="calculator",
            source_id="admet_ml",
            prediction_basis="empirical",
        )
    )
    provenance = Provenance(
        created_by="core", method="rdkit", parameters={"decimal_places": 2}, timestamp=0.0
    )
    table.set_cell(
        "a", "descriptor:mol_wt", BatchCell(value=180.15899999999996, text="180.2", provenance=provenance)
    )
    table.set_cell("a", "descriptor:formula", BatchCell(text="C9H8O4", provenance=provenance))
    table.set_cell(
        "a", "calculator:admet_ml:hERG blockade", BatchCell(value=0.02, text="0.02", provenance=provenance)
    )
    table.set_cell("b", "descriptor:mol_wt", BatchCell(value=194.194, text="194.2", provenance=provenance))
    table.set_cell("b", "descriptor:formula", BatchCell(text="C8H10N4O2", provenance=provenance))
    table.set_cell(
        "b",
        "calculator:admet_ml:hERG blockade",
        BatchCell(text="", cache_state=CacheState.FAILED, error="ADMET-AI is not configured."),
    )
    return table


# --- CSV ----------------------------------------------------------------


def test_csv_is_written_with_a_bom_so_excel_keeps_the_units(tmp_path):
    """Without it, Excel on Windows reads UTF-8 as the system code page and
    every Å² in a header becomes mojibake at the moment the file opens."""
    table = _table()
    table.add_column(BatchColumn(column_id="tpsa", label="TPSA", units="Å²"))
    table.set_cell("a", "tpsa", BatchCell(value=63.6, text="63.6"))
    path = tmp_path / "out.csv"
    TableExportService().export_csv(table, path)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Å²" in path.read_text(encoding="utf-8-sig").splitlines()[0]


def test_csv_carries_full_precision_not_the_displayed_text(tmp_path):
    """The screen is for reading; the file is for computing with. A
    re-rounded number cannot be un-rounded later."""
    path = tmp_path / "out.csv"
    TableExportService().export_csv(_table(), path)
    assert "180.15899999999996" in path.read_text(encoding="utf-8-sig")


def test_a_text_cell_that_looks_like_a_formula_is_neutralised(tmp_path):
    """A spreadsheet evaluating a cell of chemistry output is at best wrong."""
    table = _table()
    table.add_column(BatchColumn(column_id="note", label="Note", numeric=False))
    table.set_cell("a", "note", BatchCell(text="=1+1"))
    table.set_cell("b", "note", BatchCell(text="-hydroxy"))
    path = tmp_path / "out.csv"
    TableExportService().export_csv(table, path)
    body = path.read_text(encoding="utf-8-sig")
    assert "'=1+1" in body
    assert "'-hydroxy" in body


def test_a_negative_number_is_not_treated_as_a_formula(tmp_path):
    """The guard is for TEXT. Quoting a real negative value would turn a
    numeric column into strings."""
    table = BatchTable()
    table.add_row("a", "x")
    table.add_column(BatchColumn(column_id="logp", label="LogP"))
    table.set_cell("a", "logp", BatchCell(value=-1.03, text="-1.03"))
    path = tmp_path / "out.csv"
    TableExportService().export_csv(table, path)
    assert ",-1.03" in path.read_text(encoding="utf-8-sig")


def test_every_row_and_column_reaches_the_file(tmp_path):
    path = tmp_path / "out.csv"
    TableExportService().export_csv(_table(), path)
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) == 3  # header + two molecules
    assert lines[0].split(",")[0] == "Molecule"


def test_colliding_headers_are_disambiguated_by_source(tmp_path):
    """`logd` reports "LogP" and so does the RDKit descriptor set. Two
    identical headers in one CSV are unusable."""
    table = _table()
    table.add_column(
        BatchColumn(column_id="a:LogP", label="LogP", source_id="logd")
    )
    table.add_column(
        BatchColumn(column_id="descriptor:mol_logp", label="LogP", source_id="mol_logp")
    )
    path = tmp_path / "out.csv"
    TableExportService().export_csv(table, path)
    header = path.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "LogP [logd]" in header
    assert "LogP [mol_logp]" in header


def test_headers_that_do_not_collide_are_left_alone(tmp_path):
    """Appending the source to all 27 topology columns would make every one
    of them unreadable."""
    path = tmp_path / "out.csv"
    TableExportService().export_csv(_table(), path)
    assert "Molecular Weight (g/mol)," in path.read_text(encoding="utf-8-sig")


# --- report -------------------------------------------------------------


def test_the_report_states_what_produced_every_column():
    """A CSV cannot carry provenance -- there is nowhere to put it. This is
    where it goes."""
    report = TableExportService().render_report(_table())
    assert "## Methods and provenance" in report
    assert "core/rdkit" in report
    assert "decimal_places = 2" in report


def test_the_report_carries_the_prediction_basis():
    assert "**empirical**" in TableExportService().render_report(_table())


def test_the_report_counts_the_failures_and_gives_their_reason():
    """A column that is 90% empty still looks like a column, and a mean over
    the 10% that worked is a different claim from a mean over all of it."""
    report = TableExportService().render_report(_table())
    assert "Values: 1 of 2 molecules" in report
    assert "Failed for 1: ADMET-AI is not configured." in report


def test_the_report_table_has_a_row_per_molecule():
    report = TableExportService().render_report(_table())
    assert "| aspirin |" in report
    assert "| caffeine |" in report


def test_a_pipe_in_a_value_does_not_shift_every_later_column():
    table = _table()
    table.add_column(BatchColumn(column_id="n", label="Name", numeric=False))
    table.set_cell("a", "n", BatchCell(text="a|b"))
    assert "a\\|b" in TableExportService().render_report(table)


def test_an_empty_table_reports_as_empty_rather_than_as_a_broken_table():
    report = TableExportService().render_report(BatchTable())
    assert "_No properties were computed._" in report


def test_the_report_writes_to_disk(tmp_path):
    path = tmp_path / "report.md"
    TableExportService().export_report(_table(), path, title="My run")
    assert path.read_text(encoding="utf-8").startswith("# My run")
