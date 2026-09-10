"""One adapter registry over the shared result-kind vocabulary.

**THE VOCABULARY IS IN `domain/result_kinds.py`; THE PRESENTATIONS ARE HERE.**
That split is the point. `domain/` answers "this is a `PerAtomDataset`"; this
module answers "a per-atom dataset is copied like this and opens that viewer".
Putting viewer names in `domain/` would be UI routing in the scientific layer,
and this project has kept that boundary deliberately clean.

**IT REPLACES A TYPE-KEYED DISPATCH THAT WAS THE THIRD OF ITS KIND.**
`result_clipboard`'s own header described itself as "the third registry in this
codebase to use it", after `_VISUALIZATION_ADAPTERS` and
`_RESULT_VIEW_FACTORIES`. Three registries over one vocabulary is three chances
to disagree about what a result IS -- and they DID disagree, the same way,
three times over:

    result_to_text            isinstance(SpectrumResult) -> the NMR renderer
    _RESULT_VIEW_FACTORIES    exact type only -> no entry, generic fallback
    _open_inspector           isinstance(SpectrumResult) -> NmrViewDialog

Every one treats a `VibrationalSpectrumResult` as an NMR spectrum, because it
subclasses `SpectrumResult`. It is not one: its data is per NORMAL MODE, and it
leaves `values` and `elements` deliberately empty -- its own docstring says a
vibrational peak is not a property of an atom. So an atom-keyed renderer
produces an empty table for it.

Measured on the shipped code before this existed, copying a two-mode IR
spectrum gave two lines -- a header in NMR vocabulary ("Atom", "Element",
"Shift") and not one of the modes.

That path is LIVE: ORCA publishes vibrational spectra through
`SpectrumComputed`, which the Properties panel subscribes to. `_open_inspector`'s
version is LATENT -- it needs `_pending_calculator_id` to match, and no
REGISTERED calculator produces a vibrational spectrum today, so it is one
registration away rather than broken now. Recorded because it is the same
defect and becomes reachable without anybody touching it.

**KEYED BY KIND, NOT BY TYPE**, so the subclass question is asked once, in
`kind_of`, instead of once per registry with a different answer each time.

**THE TABLE IS TOTAL.** Every kind has an entry, including the ones whose right
answer is the generic rendering -- named explicitly as `_generic_to_text`
rather than reached through a fallback branch, so "we chose this" and "nothing
matched" stay distinguishable in the registry itself. That distinction is
exactly what let the vibrational case stay invisible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openchem.domain.common import ScientificResult
from openchem.domain.report import ReportResult
from openchem.domain.result_kinds import (
    ALERT,
    PER_ATOM,
    PH_CURVE,
    REPORT,
    SPECTRUM,
    STRUCTURE_SET,
    TRAJECTORY,
    VIBRATIONAL_SPECTRUM,
    kind_of,
)
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    VibrationalSpectrumResult,
)
from openchem.ui.visualization import declared_total, label_decimals

#: This kind has no dedicated viewer to open. A VALUE rather than an absent
#: entry, so "no rich view" and "nobody filled this in" stay different states --
#: the same reason `decline_total` requires a reason.
NO_RICH_VIEW = ""

#: The rich-view identifiers, matching `FactLink.target`'s vocabulary. Strings
#: rather than an enum for the reason that field gives: a new destination
#: should not require changing a type everything else imports.
CALCULATOR_INSPECTOR = "calculator_inspector"
#: The dedicated NMR view -- grouped signals, integrations, multiplicities.
NMR_VIEW = "nmr_view"
#: IR has its own viewer (`IrViewWidget`), reached from the Quantum Chemistry
#: panel. Named here so the registry can say a vibrational spectrum does NOT
#: belong in the NMR view, which is the point of it having its own kind.
IR_VIEW = "ir_view"


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
        lines.append(f"{fact.label}: {fact.value_with_units}")
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


def _vibrational_to_text(result: VibrationalSpectrumResult) -> str:
    """A vibrational spectrum as MODES, which is what it is made of.

    **IT USED TO COPY AS A HEADER AND NOTHING ELSE.** `SpectrumResult`'s
    renderer walks `values`, keyed by ATOM INDEX, and a vibrational result
    leaves that empty on purpose -- a normal mode is not a property of one
    atom. Measured on two modes: two lines out, both dropped, under an
    `Atom / Element / Shift` header that is NMR vocabulary.

    Wavenumber and IR intensity, because those are the two columns a reader
    plots. `is_imaginary` is not a column: it is derivable from the sign, and
    a negative wavenumber IS the finding rather than a flag beside it.
    """
    lines = [result.name, "Mode\tWavenumber (cm^-1)\tIR intensity (km/mol)"]
    for index, mode in enumerate(result.modes, start=1):
        intensity = (
            "" if mode.ir_intensity_km_mol is None else f"{mode.ir_intensity_km_mol:.6g}"
        )
        lines.append(f"{index}\t{mode.wavenumber_cm1:.6g}\t{intensity}")
    if result.imaginary_warning:
        # Carried, not filtered. An imaginary mode says the geometry is a
        # saddle point and invalidates every thermochemistry number from the
        # same job -- a copy that dropped it would export a spectrum that
        # looks fine.
        lines.append("")
        lines.append(result.imaginary_warning)
    return "\n".join(lines)


def _generic_to_text(result: ScientificResult) -> str:
    """The name, or the failure reason. **A CHOICE, NOT A FALLBACK.**

    Registered explicitly for the kinds whose content does not belong on a
    clipboard as text -- a trajectory is a hundred molblocks, and pasting them
    as a block helps nobody. Naming it in the table is what keeps "this is the
    right answer here" distinguishable from "nothing matched", which is how
    the vibrational case stayed invisible.
    """
    if result.cache_state.value == "failed":
        return getattr(result, "error", "") or "Failed"
    return getattr(result, "name", "") or type(result).__name__


@dataclass(frozen=True)
class ResultAdapter:
    """How one kind of result is presented."""

    #: Clipboard/text projection.
    to_text: Callable[[Any], str]
    #: Which dedicated viewer opens it, or `NO_RICH_VIEW`.
    rich_view: str


#: Kind -> how to present it. TOTAL over `RESULT_KINDS`, which
#: `test_every_kind_has_an_adapter` asserts -- a missing entry would raise a
#: KeyError deep in a paint path rather than at registration.
ADAPTERS: dict[str, ResultAdapter] = {
    REPORT: ResultAdapter(to_text=_report_to_text, rich_view=NO_RICH_VIEW),
    ALERT: ResultAdapter(to_text=_alert_to_text, rich_view=NO_RICH_VIEW),
    PER_ATOM: ResultAdapter(to_text=_per_atom_to_text, rich_view=CALCULATOR_INSPECTOR),
    SPECTRUM: ResultAdapter(to_text=_spectrum_to_text, rich_view=NMR_VIEW),
    VIBRATIONAL_SPECTRUM: ResultAdapter(to_text=_vibrational_to_text, rich_view=IR_VIEW),
    PH_CURVE: ResultAdapter(to_text=_ph_curve_to_text, rich_view=CALCULATOR_INSPECTOR),
    STRUCTURE_SET: ResultAdapter(
        to_text=_structure_set_to_text, rich_view=CALCULATOR_INSPECTOR
    ),
    TRAJECTORY: ResultAdapter(to_text=_generic_to_text, rich_view=CALCULATOR_INSPECTOR),
}


def adapter_for(result: object) -> ResultAdapter:
    """The adapter for `result`, or raise `UnknownResultKind`.

    Refuses rather than defaulting, for the reason `kind_of` does: a default
    produces a plausible-looking empty presentation that a caller cannot tell
    from a result which genuinely had nothing to say.
    """
    return ADAPTERS[kind_of(result)]


def result_to_text(result: ScientificResult) -> str:
    """A copyable rendering of any calculator result.

    Dispatches through the shared vocabulary rather than its own type table.
    The isinstance ladder this replaced is why: it matched `SpectrumResult`
    deliberately, so `NMRSpectrumResult` would not "silently fall through to
    the generic fallback" -- and sent every `VibrationalSpectrumResult` to the
    same renderer, which cannot show one.
    """
    return adapter_for(result).to_text(result)
