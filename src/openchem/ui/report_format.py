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

from openchem.domain.bond_report import BondReport
from openchem.domain.molecule_report import MoleculeReport
from openchem.domain.report import CATEGORY_LABELS, ReportResult


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
    # A CALCULATOR's report -- Geometry, Topology, Regulatory and the
    # rest. It names itself, and it has no atom index to fall through to:
    # `property_panel` puts one of these in a FactView, so before this
    # branch existed "Open in window" then Copy raised
    # `AttributeError: 'ReportResult' object has no attribute
    # 'atom_index'` on every calculator result.
    if isinstance(report, ReportResult):
        return report.name or "Result"
    return f"Atom {report.atom_index + 1} ({report.symbol})"


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
    if isinstance(report, ReportResult):
        return {"subject": "result", "report_id": report.report_id, "name": report.name}
    return {"subject": "atom", "atom_index": report.atom_index, "symbol": report.symbol}


def format_report(report, fmt: str) -> str:
    """One report as text, whatever its subject.

    Four formats because the destinations differ: Markdown for an issue or
    a notebook, plain text for an email, JSON for a script or an LLM, CSV
    for a spreadsheet. A module-level function rather than a method so the
    formats are testable without constructing a panel -- and so anything
    else that grows a report can reuse them.
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
                    }
                    for fact in report.facts
                ],
                "assumptions": list(report.assumptions),
                "limitations": list(report.limitations),
            },
            indent=1,
        )

    if fmt == "CSV":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["category", "label", "value", "units", "source", "basis"])
        for fact in report.facts:
            writer.writerow([
                fact.category.value, fact.label, fact.display_value,
                fact.units, fact.source, fact.basis.value,
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
                    f"| {fact.label} | {fact.display_value} | {fact.source} | {fact.basis.value} |"
                )
            lines.append("")
        for text in report.limitations:
            lines.append(f"> {text}")
        return "\n".join(lines).rstrip() + "\n"

    lines = [header, "=" * len(header), ""]
    for category, facts in grouped.items():
        lines.append(f"{CATEGORY_LABELS[category]}:")
        for fact in facts:
            lines.append(f"  {fact.label}: {fact.display_value}  [{fact.basis.value}]")
        lines.append("")
    for text in report.limitations:
        lines.append(f"Limitation: {text}")
    return "\n".join(lines).rstrip() + "\n"
