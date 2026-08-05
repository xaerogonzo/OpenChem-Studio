"""The second export path: a table of many molecules, not one structure.

`ExportService` turns ONE `MoleculeModel` into ONE chemical-format file
(.mol, .sdf, .smi) through RDKit or Open Babel. Nothing about that is
reusable here -- there is no chemical format whose subject is "200
molecules and the 47 numbers computed for each" -- so this is a separate
service rather than a format added to that one. `ExportService` is
untouched.

TWO OUTPUTS, because they answer different questions.

CSV is for the next tool. It is what gets opened in Excel, read by pandas,
plotted in Origin. It carries the numbers at full precision and nothing
else, because anything else stops it being a CSV.

The REPORT is for the record. A CSV cannot carry per-cell provenance --
there is nowhere to put it -- and a table of 9,400 numbers with no
statement of what produced them is exactly the honesty this codebase
spends effort on everywhere else. So the report writes the table AND a
methods section: what each column came from, by what method, with what
parameters, how many molecules failed it and why. It is Markdown because
it has to be readable as it stands, pasteable into a notebook, and
diffable.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openchem.domain.batch import BatchTable
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.export")

#: Characters Excel and LibreOffice treat as the start of a FORMULA rather
#: than of text. A calculator's own output can begin with any of them ("-"
#: opens several alert descriptions), and a spreadsheet that evaluates a
#: cell of chemistry output is at best wrong and at worst a way to run
#: something. Prefixed with an apostrophe, which both applications read as
#: "this is literally text" and neither displays.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


class TableExportService:
    """`BatchTable` -> .csv or .md. No chemistry, no Qt, no engine.

    Deliberately not merged into `ExportService`: that one is constructed
    with a `ChemistryEngine` and dispatches across RDKit/Open Babel/plugin
    exporters by file extension, none of which this needs or should
    inherit.
    """

    def export_csv(
        self, table: BatchTable, path: Path, progress: ProgressHandle | None = None
    ) -> None:
        """One row per molecule, one column per computed property.

        WRITTEN AS UTF-8 WITH A BOM. Half these column headers carry units
        that are not ASCII -- Å², Å³, µ -- and Excel on Windows reads a
        BOM-less UTF-8 file as the system code page, which turns every one
        of them into mojibake at the moment the file is opened. `utf-8-sig`
        is what makes the units survive the trip; every other reader
        (pandas, R, Origin) skips the BOM without being told.

        Numeric cells export their VALUE, not their display text.
        `mol_wt` shows as "180.2" on screen and writes as
        180.15899999999996 here, because the screen is for reading and the
        file is for computing with, and a re-rounded number cannot be
        un-rounded later.
        """
        progress = progress or ProgressHandle()
        progress.report(0.0, f"Writing {path.name}")
        headers = _disambiguated_headers(table)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Molecule", *(headers[column.column_id] for column in table.columns)])
            total = max(len(table.row_uuids), 1)
            for index, molecule_uuid in enumerate(table.row_uuids):
                writer.writerow(
                    [
                        _safe(table.row_labels.get(molecule_uuid, molecule_uuid)),
                        *(_csv_cell(table, molecule_uuid, column) for column in table.columns),
                    ]
                )
                progress.report((index + 1) / total, f"{index + 1}/{total}")
        progress.report(1.0, "Done")
        logger.info("Exported batch table (%d rows x %d columns) to %s", len(table.row_uuids), len(table.columns), path)

    def export_report(
        self, table: BatchTable, path: Path, title: str = "Batch results", progress: ProgressHandle | None = None
    ) -> None:
        """The table plus what produced every column of it."""
        progress = progress or ProgressHandle()
        progress.report(0.0, f"Writing {path.name}")
        path.write_text(self.render_report(table, title), encoding="utf-8")
        progress.report(1.0, "Done")
        logger.info("Exported batch report to %s", path)

    def render_report(self, table: BatchTable, title: str = "Batch results") -> str:
        """The report as text.

        Separate from writing it so the formatting -- the part that can be
        wrong -- is testable without a filesystem, the same split
        `ui/result_clipboard.py` already makes for the same reason.
        """
        headers = _disambiguated_headers(table)
        lines = [
            f"# {title}",
            "",
            f"{len(table.row_uuids)} molecules x {len(table.columns)} properties, "
            f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
            "",
        ]
        lines.extend(self._results_table(table, headers))
        lines.extend(self._methods_section(table, headers))
        return "\n".join(lines) + "\n"

    def _results_table(self, table: BatchTable, headers: dict[str, str]) -> list[str]:
        if not table.columns:
            return ["_No properties were computed._", ""]
        header_cells = ["Molecule", *(headers[column.column_id] for column in table.columns)]
        lines = [
            "| " + " | ".join(_escape_pipes(cell) for cell in header_cells) + " |",
            "|" + "|".join(["---"] * len(header_cells)) + "|",
        ]
        for molecule_uuid in table.row_uuids:
            row = [table.row_labels.get(molecule_uuid, molecule_uuid)]
            for column in table.columns:
                cell = table.cell(molecule_uuid, column.column_id)
                row.append("" if cell is None else (cell.text or ("—" if cell.failed else "")))
            lines.append("| " + " | ".join(_escape_pipes(cell) for cell in row) + " |")
        lines.append("")
        return lines

    def _methods_section(self, table: BatchTable, headers: dict[str, str]) -> list[str]:
        """One entry per column: what computed it, how, and what went wrong.

        The failure count is here rather than only in the table because a
        column can be 90% empty and still look like a column -- and a mean
        taken over the 10% that worked is a different claim from a mean
        over all of it.
        """
        lines = ["## Methods and provenance", ""]
        if not table.columns:
            return lines + ["_Nothing was computed._", ""]
        for column in table.columns:
            cells = [table.cell(uuid, column.column_id) for uuid in table.row_uuids]
            present = [cell for cell in cells if cell is not None]
            failures = Counter(
                (cell.error or "unspecified failure") for cell in present if cell.failed
            )
            methods = sorted(
                {
                    f"{cell.provenance.created_by}/{cell.provenance.method}"
                    for cell in present
                    if cell.provenance is not None
                }
            )
            lines.append(f"### {headers[column.column_id]}")
            lines.append("")
            lines.append(f"- Source: `{column.source}` / `{column.source_id}`")
            if methods:
                lines.append(f"- Method: {', '.join(methods)}")
            if column.prediction_basis:
                lines.append(f"- Basis: **{column.prediction_basis.replace('_', ' ')}**")
            parameters = _parameters_of(present)
            if parameters:
                lines.append(f"- Parameters: {parameters}")
            filled = sum(1 for cell in present if not cell.failed and cell.text)
            lines.append(f"- Values: {filled} of {len(table.row_uuids)} molecules")
            for reason, count in failures.most_common():
                lines.append(f"- Failed for {count}: {reason}")
            lines.append("")
        return lines


def _parameters_of(cells) -> str:
    """The calculator parameters actually used, when every cell agrees.

    Reported only on agreement: cells from different runs can legitimately
    carry different parameters, and printing one of them as though it
    applied to the column would be a false statement about the other rows.
    """
    seen = {
        tuple(sorted((key, str(value)) for key, value in cell.provenance.parameters.items()))
        for cell in cells
        if cell.provenance is not None and cell.provenance.parameters
    }
    if len(seen) != 1:
        return "" if not seen else "(varied between molecules)"
    return ", ".join(f"{key} = {value}" for key, value in next(iter(seen)))


def _disambiguated_headers(table: BatchTable) -> dict[str, str]:
    """column_id -> header, with the source appended only where needed.

    Two columns can honestly share a label: `logd` reports "LogP" and the
    RDKit descriptor set has one too. Appending the source to every header
    would make all of them unreadable ("Wiener index [topology_analysis]"
    x 27), so it is appended only to the ones that would otherwise
    collide.
    """
    counts = Counter(column.header for column in table.columns)
    return {
        column.column_id: (
            f"{column.header} [{column.source_id}]" if counts[column.header] > 1 else column.header
        )
        for column in table.columns
    }


def _csv_cell(table: BatchTable, molecule_uuid: str, column) -> str:
    cell = table.cell(molecule_uuid, column.column_id)
    if cell is None:
        return ""
    if column.numeric and cell.value is not None:
        return repr(cell.value)
    return _safe(cell.text)


def _safe(text: str) -> str:
    return f"'{text}" if text[:1] in _FORMULA_LEAD else text


def _escape_pipes(text: str) -> str:
    """A pipe inside a cell ends the cell in Markdown, silently shifting
    every column after it one to the left."""
    return text.replace("|", "\\|").replace("\n", " ")
