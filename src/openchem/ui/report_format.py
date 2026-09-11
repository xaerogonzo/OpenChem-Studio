"""Turning a report into text: Markdown, plain, JSON, CSV.

Moved out of `atom_inspector_panel.py`, where it lived as module functions
while that panel was the only consumer. `FactView` is the second, and a
widget importing from a panel is the backwards dependency the whole
extraction exists to remove -- so the formats moved to where both can
reach them rather than one reaching across the other.

Four formats because the destinations differ: Markdown for an issue or a
notebook, plain text for an email, JSON for a script or an LLM, CSV for a
spreadsheet. Plain functions, so they are testable without constructing
any widget at all.

`atom_inspector_panel` re-exports every name, so no existing import
changed.
"""

from __future__ import annotations

import csv
import io
import json

from openchem.domain.atom_report import AtomReport
from openchem.domain.bond_report import BondReport
from openchem.domain.molecule_report import MoleculeReport
from openchem.domain.report import CATEGORY_LABELS


def names_itself(report) -> bool:
    """Whether this report is a RESULT: something that carries its own id
    and display name rather than describing an atom, a bond or a molecule.

    **ASKED OF THE CONTRACT, NOT OF A TYPE, AND THAT IS THE FIX.** The two
    functions below used to test `isinstance(report, ReportResult)` and fall
    off the end into the atom branch -- so anything result-shaped that was
    not literally a `ReportResult` reached `report.atom_index`. Two of the
    results reader's own entries are exactly that:

        the "All results" view      a view over the merge
        "Molecular Properties"      the always-on descriptor aggregate

    Measured before this existed: **8 of 12** (two subjects x four formats)
    raised `AttributeError: ... has no attribute 'atom_index'`, unhandled,
    out of the Copy and Export click paths. The `ReportResult` branch's own
    comment records fixing that same error once already, for calculator
    results; adding a branch per new type is what let it come back.

    `StructureReport` carries neither `report_id` nor `name`, so an atom,
    bond or molecule report cannot answer True here by accident.
    """
    return hasattr(report, "report_id") and hasattr(report, "name")


def report_header(report) -> str:
    """How a report names its own subject.

    One function so a title, a Markdown heading and a plain-text banner
    cannot disagree about what the report is about.
    """
    if isinstance(report, MoleculeReport):
        name = report.display_name or report.formula or "Molecule"
        return f"{name} ({report.formula})" if report.formula else name
    if isinstance(report, BondReport):
        return f"Bond {report.bond_index + 1} ({report.label})"
    if names_itself(report):
        return report.name or "Result"
    if isinstance(report, AtomReport):
        return f"Atom {report.atom_index + 1} ({report.symbol})"
    raise TypeError(_unknown_subject(report))


def _subject_fields(report) -> dict:
    """The identity keys for JSON, which differ per subject.

    Kept separate from the fact serialisation because the facts are the
    same shape for all three and only the subject is not -- "anything else
    that grows a report" was the stated reason these formats were a module
    function, and this is that."""
    if isinstance(report, MoleculeReport):
        return {
            "subject": "molecule",
            "display_name": report.display_name,
            "formula": report.formula,
            "atom_count": report.atom_count,
            "bond_count": report.bond_count,
        }
    if isinstance(report, BondReport):
        return {
            "subject": "bond",
            "bond_index": report.bond_index,
            "label": report.label,
            "begin_atom_index": report.begin_atom_index,
            "end_atom_index": report.end_atom_index,
        }
    if names_itself(report):
        return {"subject": "result", "report_id": report.report_id, "name": report.name}
    if isinstance(report, AtomReport):
        return {"subject": "atom", "atom_index": report.atom_index, "symbol": report.symbol}
    raise TypeError(_unknown_subject(report))


def _unknown_subject(report) -> str:
    """**FAIL CLOSED, NAMING THE TYPE.** The old default was the ATOM branch,
    so an unrecognised subject died on `report.atom_index` -- an error naming
    a field the reader has never heard of, several frames from the dispatch
    that could not place it. Same shape as the `FactLink` chain that fell off
    its end, and the same cure: say what happened.
    """
    return (
        f"{type(report).__name__} is not a report subject this can format. A "
        "reader entry either describes an atom, a bond or a molecule, or names "
        "itself with a `report_id` and a `name` -- see `names_itself`."
    )


def chart_rows(chart) -> list[list[str]]:
    """A declared chart as a header row plus data rows, or [] if it has none.

    **BY THE ANNOTATION'S OWN SHAPE, NEVER BY DUCK-TYPING A `.points`.**
    The two drawable kinds carry their numbers differently -- a line chart
    holds named series of (x, y) pairs, a stick chart holds sticks with an
    optional label -- and a consumer guessing from attribute names is the
    probe-for-a-field-nobody-has failure this project already paid for
    across nine calculators.

    A depiction returns nothing, correctly: it is a picture of a structure
    and has no table to paste.
    """
    from openchem.domain.report import LineChartAnnotation, StickChartAnnotation

    if isinstance(chart, LineChartAnnotation):
        names = [s.name or chart.y_label for s in chart.series]
        xs: list = []
        for series in chart.series:
            for x, _y in series.points:
                if x not in xs:
                    xs.append(x)
        rows = [[chart.x_label, *names]]
        for x in xs:
            row = [f"{x:.6g}"]
            for series in chart.series:
                value = next((y for px, y in series.points if px == x), None)
                row.append("" if value is None else f"{value:.6g}")
            rows.append(row)
        return rows if len(rows) > 1 else []

    if isinstance(chart, StickChartAnnotation):
        rows = [[chart.x_label, chart.y_label, "label"]]
        for stick in chart.sticks:
            rows.append([f"{stick.x:.6g}", f"{stick.y:.6g}", stick.label or ""])
        return rows if len(rows) > 1 else []

    return []


def _chart_lines(report) -> list[str]:
    """Every declared chart as a tab-separated block, for a plain-text copy."""
    lines: list[str] = []
    for chart in getattr(report, "charts", ()) or ():
        rows = chart_rows(chart)
        if not rows:
            continue
        lines.append("")
        if getattr(chart, "title", ""):
            lines.append(chart.title)
        lines.extend("\t".join(row) for row in rows)
    return lines


def format_report(report, fmt: str) -> str:
    """One report as text, whatever its subject.

    Four formats because the destinations differ: Markdown for an issue or
    a notebook, plain text for an email, JSON for a script or an LLM, CSV
    for a spreadsheet. A module-level function rather than a method so the
    formats are testable without constructing a panel -- and so anything
    else that grows a report can reuse them.

    **EVERY FORMAT CARRIES `Fact.limitations`, AND NONE OF THEM DID.** The
    report-level ones were emitted and the per-fact ones were dropped by all
    four, which went unnoticed while the surface that mattered was the
    Properties panel: `PropertyPanel.as_text` took deliberate care to export
    a failed descriptor's FULL reason rather than the short cell form, and
    its own docstring says so. 2c removes that surface, and measured here
    before the fix, all three text formats exported "Needs a 3D conformer"
    with the sentence saying what to press nowhere in the file -- the exact
    leak the panel's rule existed to stop, one surface along.
    """
    header = report_header(report)
    grouped = report.by_category()

    if fmt == "JSON":
        return json.dumps(
            {
                "molecule_uuid": report.molecule_uuid,
                **_subject_fields(report),
                "structure_version": report.structure_version,
                "facts": [
                    {
                        "category": fact.category.value,
                        "label": fact.label,
                        "display_value": fact.display_value,
                        "source": fact.source,
                        "basis": fact.basis.value,
                        "units": fact.units,
                        "evidence": list(fact.evidence),
                        "limitations": list(fact.limitations),
                    }
                    for fact in report.facts
                ],
                "assumptions": list(report.assumptions),
                "limitations": list(report.limitations),
                "charts": [
                    {"title": getattr(c, "title", ""), "rows": chart_rows(c)}
                    for c in getattr(report, "charts", ()) or ()
                    if chart_rows(c)
                ],
            },
            indent=1,
        )

    if fmt == "CSV":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            ["category", "label", "value", "units", "source", "basis", "limitations"]
        )
        for fact in report.facts:
            writer.writerow([
                fact.category.value, fact.label, fact.display_value,
                fact.units, fact.source, fact.basis.value,
                "; ".join(fact.limitations),
            ])
        return buffer.getvalue()

    if fmt == "Markdown":
        lines = [f"## {header}", ""]
        for category, facts in grouped.items():
            lines.append(f"### {CATEGORY_LABELS[category]}")
            lines.append("")
            lines.append("| Fact | Value | Source | Basis |")
            lines.append("| --- | --- | --- | --- |")
            for fact in facts:
                lines.append(
                    f"| {fact.label} | {fact.value_with_units} "
                    f"| {fact.source} | {fact.basis.value} |"
                )
            lines.append("")
            for fact in facts:
                for text in fact.limitations:
                    lines.append(f"> **{fact.label}** -- {text}")
            if any(fact.limitations for fact in facts):
                lines.append("")
        for text in report.limitations:
            lines.append(f"> {text}")
        return "\n".join(lines).rstrip() + "\n"

    lines = [header, "=" * len(header), ""]
    for category, facts in grouped.items():
        lines.append(f"{CATEGORY_LABELS[category]}:")
        for fact in facts:
            lines.append(f"  {fact.label}: {fact.value_with_units}  [{fact.basis.value}]")
            for text in fact.limitations:
                lines.append(f"    {text}")
        lines.append("")
    for text in report.limitations:
        lines.append(f"Limitation: {text}")
    # **THE PICTURE'S NUMBERS, WHICH NO FORMAT CARRIED.** A report that
    # declares a curve exported the facts and dropped the curve, so a copy
    # said less than the screen showed -- the defect the Properties panel's
    # own "Copy all" had once, in a second place. Measured when
    # `solubility_curve` was merged into `Solubility`: 57 rows lost.
    lines.extend(_chart_lines(report))
    return "\n".join(lines).rstrip() + "\n"
