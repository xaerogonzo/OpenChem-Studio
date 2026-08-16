"""Turn a calculator result into text you can paste somewhere useful.

Type-keyed dispatch, the third registry in this codebase to use it after
`_VISUALIZATION_ADAPTERS` ("how do I colour atoms for this") and
`_RESULT_VIEW_FACTORIES` ("what widget shows this"). This one answers
"what does this look like on the clipboard".

TABULAR RESULTS ARE TAB-SEPARATED, deliberately: a tab-separated block
pastes into Excel, Sheets or Origin as real columns, while a
prettily-aligned one pastes as a single ruined column. Text results stay
plain lines, since that is what they are.

Kept out of the dialog and out of Qt so it can be tested against the real
result objects without constructing a widget -- the formatting is the
part that can be wrong.
"""

from __future__ import annotations

from collections.abc import Callable

from openchem.domain.common import ScientificResult
from openchem.domain.report import ReportResult
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
)
from openchem.ui.visualization import declared_total, label_decimals


def _units_suffix(result: ScientificResult) -> str:
    units = getattr(result, "units", "")
    return f" ({units})" if units else ""


def _report_to_text(result: ReportResult) -> str:
    """A fact-based report, as label/value lines.

    Reuses `ui/report_format.py` rather than formatting facts a second
    way -- the Atom Inspector, `FactView` and this all reach the same four
    formats, so a report copied from any of them is byte-identical.
    """
    from openchem.ui.report_format import format_report

    return format_report(result, "Plain text")


def _alert_to_text(result: AlertResult) -> str:
    return "\n".join([result.name, *result.matched])


def _per_atom_to_text(result: PerAtomDataset) -> str:
    """The atom table, led by the molecular total when one is declared.

    ONCE, and only when the producer declared one. Pasting a LogP
    contribution table used to carry no LogP anywhere -- the one number
    somebody reading it would want -- while a table that had a total
    computed for it by the reader would be the summing bug in a new place.
    The headline is the dialog's, verbatim, at the dialog's precision, so a
    pasted result and the screen it came from cannot disagree.

    The BALANCE sentence is deliberately not copied: it explains the
    difference between the total and a column the reader now has in full,
    and can add up themselves.
    """
    lines = [result.name]
    total = declared_total(result)
    if total is not None:
        places = label_decimals(result)
        units = f" {total['units']}" if total["units"] else ""
        lines.append(f"{total['label']}\t{total['value']:.{places}f}{units}")
    lines.append(f"Atom\t{result.name}{_units_suffix(result)}")
    lines.extend(f"{index}\t{value:.6g}" for index, value in sorted(result.values.items()))
    return "\n".join(lines)


def _spectrum_to_text(result: SpectrumResult) -> str:
    # Element is worth a column here in a way it is not for a per-atom
    # dataset: a spectrum mixes 1H and 13C values in one result, and the
    # numbers are meaningless without knowing which nucleus each is.
    lines = [result.name, f"Atom\tElement\tShift{_units_suffix(result)}"]
    lines.extend(
        f"{index}\t{result.elements.get(index, '')}\t{value:.6g}"
        for index, value in sorted(result.values.items())
    )
    return "\n".join(lines)


def _ph_curve_to_text(result: PhCurveResult) -> str:
    """The scalar findings first, then the curve as a pasteable table.

    The facts go in because they are the half of this result a reader
    quotes -- an intrinsic solubility and a category are what ends up in a
    report, while the 57-row table is what ends up in a spreadsheet. A copy
    that dropped them would silently export less than the screen shows,
    which is the defect the Properties panel's "Copy all" already had once.
    """
    lines = [result.name]
    for fact in result.facts:
        units = f" {fact.units}" if fact.units else ""
        lines.append(f"{fact.label}: {fact.display_value}{units}")
    if result.facts:
        lines.append("")
    names = list(result.series)
    lines.append("\t".join([result.x_label, *names]))
    for row, ph in enumerate(result.ph_values):
        values = [f"{result.series[name][row]:.6g}" for name in names]
        lines.append("\t".join([f"{ph:.6g}", *values]))
    return "\n".join(lines)


def _structure_set_to_text(result: StructureSetResult) -> str:
    """SMILES per row, so the block pastes into a spreadsheet AND each
    cell is itself a structure any chemistry tool will accept.

    A single entry's molblock is available separately (see
    `structure_entry_text`) -- a molblock is multi-line and would destroy
    the row structure if inlined here.
    """
    from openchem.chem.engine import ChemistryEngine

    engine = ChemistryEngine()
    lines = [result.name, "#\tLabel\tSMILES\tEnergy\tScore"]
    for index, entry in enumerate(result.entries, start=1):
        try:
            smiles = engine.molblock_to_smiles(entry.molblock)
        except Exception:  # noqa: BLE001 - one bad entry must not lose the rest
            smiles = ""
        energy = "" if entry.energy is None else f"{entry.energy:.6g}"
        score = "" if entry.score is None else f"{entry.score:.6g}"
        lines.append(f"{index}\t{entry.label}\t{smiles}\t{energy}\t{score}")
    return "\n".join(lines)


_TEXT_ADAPTERS: dict[type, Callable[..., str]] = {
    AlertResult: _alert_to_text,
    ReportResult: _report_to_text,
    PerAtomDataset: _per_atom_to_text,
    PhCurveResult: _ph_curve_to_text,
    StructureSetResult: _structure_set_to_text,
}


def result_to_text(result: ScientificResult) -> str:
    """A copyable rendering of any calculator result.

    `SpectrumResult` is matched by isinstance rather than by exact type,
    unlike the others: `NMRSpectrumResult` subclasses it and formats
    identically, and a subclass silently falling through to the generic
    fallback is how the NMR result would have copied as nothing useful.
    """
    adapter = _TEXT_ADAPTERS.get(type(result))
    if adapter is not None:
        return adapter(result)
    if isinstance(result, SpectrumResult):
        return _spectrum_to_text(result)
    if result.cache_state.value == "failed":
        return getattr(result, "error", "") or "Failed"
    return getattr(result, "name", "") or type(result).__name__
