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

from openchem.domain.common import HEAVY_ATOMS, ScientificResult
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
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
    TrajectoryResult,
    VibrationalSpectrumResult,
)
from openchem.ui.visualization import atom_basis, declared_total, label_decimals

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


#: What a summary says about itself, so a reader can tell a PROJECTION from a
#: producer's declaration.
#:
#: **0d's RULE, RENDERED.** A presentation summary may be deterministically
#: projected from declared result data and must be IDENTIFIED as one; it never
#: introduces a new scientific claim. `len(peaks)` is a projection; a curve
#: crossing found by interpolation is a claim and belongs to a producer. Saying
#: so on the view is what keeps the two distinguishable once both are rows in
#: the same reader.
SUMMARY_LIMITATION = (
    "This is a summary of the result, not the result. Open it for every value."
)


def _summary_fact(
    label: str,
    value,
    display: str,
    category: FactCategory,
    source: str,
    *,
    units: str = "",
    basis: Basis = Basis.DETERMINISTIC,
) -> Fact:
    """One projected fact.

    `source` is the PRODUCER's own method, never "summary": `Fact.source`
    answers where a value came from scientifically, and overwriting it to
    record that a view assembled the row would destroy real provenance to
    record a different kind. What says "this was projected" is the view's
    limitation, which is a statement about the whole entry.
    """
    return Fact(
        category=category,
        label=label,
        value=value,
        display_value=display,
        source=source or "core",
        basis=basis,
        units=units,
    )


def _source_of(result: Any) -> str:
    return str(getattr(result, "method", "") or "")


def _numeric_range(
    result: Any, values, category: FactCategory
) -> tuple[Fact, ...]:
    """The span of a numeric payload, at the producer's own precision.

    Empty when nothing in the payload is a number -- a categorical per-atom
    dataset (oxidation states drawn as labels, functional-group ids) has a
    count and no range, and inventing one from category ids would be a
    quantity nobody computed.
    """
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not numbers:
        return ()
    places = label_decimals(result)
    low, high = min(numbers), max(numbers)
    return (
        _summary_fact(
            "Range",
            (low, high),
            f"{low:.{places}f} to {high:.{places}f}",
            category,
            _source_of(result),
            units=getattr(result, "units", "") or "",
        ),
    )


def _declared_total_fact(result: Any, category: FactCategory) -> tuple[Fact, ...]:
    """The producer's molecular total, if it declared one.

    **NEVER SUMMED, AND THAT IS THE WHOLE POINT OF THE KEY.**
    `domain/common.TOTAL` exists because the UI used to invent a molecular
    total by adding per-atom values up -- the `Overall:` bug that put a net
    -1.36 e on a neutral molecule. `declared_total` returns None for no
    declaration, an explicit refusal AND a malformed one, so an undeclared
    total simply produces no row.
    """
    total = declared_total(result)
    if total is None:
        return ()
    places = label_decimals(result)
    return (
        _summary_fact(
            total["label"],
            total["value"],
            f"{total['value']:.{places}f}",
            category,
            _source_of(result),
            units=total["units"],
            # **HEURISTIC, AND THE DECLARATION'S OWN `basis` IS NOT THIS ONE.**
            # `declare_total(..., basis=HEAVY_ATOMS)` says WHICH ATOMS the
            # total is over -- it is the atom basis, not `Fact.Basis` -- so
            # reading it as a scientific basis raises, which is how this was
            # found rather than shipped. The producer declares no scientific
            # basis for its total, so none may be invented: understating a
            # Wiener index as judgement is recoverable, and claiming a fitted
            # Crippen total as "right, or the periodic table is wrong" is the
            # overstatement `DETERMINISTIC_DESCRIPTORS` errs away from.
            basis=Basis.HEURISTIC,
        ),
    )


def _per_atom_summary(result: PerAtomDataset, category: FactCategory) -> tuple[Fact, ...]:
    """A per-atom dataset as the few numbers a reader wants beside it.

    The DECLARED total leads, because it is the number the row was opened
    for -- a LogP contribution table whose summary omits the molecule's LogP
    is true and useless. The count and the range are projections; the atom
    basis is a producer declaration and is carried because a value keyed to
    explicit hydrogens and one keyed to heavy atoms are different data under
    the same name.
    """
    return (
        *_declared_total_fact(result, category),
        _summary_fact(
            "Atoms", len(result.values), str(len(result.values)), category, _source_of(result)
        ),
        *_numeric_range(result, result.values.values(), category),
        _summary_fact(
            "Keyed to", atom_basis(result), _ATOM_BASIS_LABELS[atom_basis(result)],
            category, _source_of(result),
        ),
    )


#: How each declared atom basis reads. Hand-written rather than derived from
#: the value, because `explicit_h` titles as "Explicit H" and what a reader
#: needs is what it MEANS -- the restate-the-identifier degeneracy the help
#: contracts refuse one floor up.
_ATOM_BASIS_LABELS = {
    HEAVY_ATOMS: "heavy atoms (hydrogens implicit)",
    "explicit_h": "every atom, hydrogens included",
    "pi_system": "the pi system only",
}


def _spectrum_summary(result: SpectrumResult, category: FactCategory) -> tuple[Fact, ...]:
    """Peak count and range, keyed by ATOM -- which is what a spectrum whose
    values are per-nucleus is made of."""
    return (
        _summary_fact(
            "Signals", len(result.values), str(len(result.values)), category, _source_of(result)
        ),
        *_numeric_range(result, result.values.values(), category),
    )


def _vibrational_summary(
    result: VibrationalSpectrumResult, category: FactCategory
) -> tuple[Fact, ...]:
    """**MODES, NOT ATOMS, AND THE GENERIC ANSWER IS WRONG RATHER THAN
    THIN.** A vibrational result leaves `values` empty on purpose -- a normal
    mode is not a property of one atom -- so the shared payload walk reported
    `None found.` for a spectrum with real modes in it. Measured on three:
    "None found." That is the fourth consumer of one vocabulary read through
    a different registry, after the clipboard, the view factory and the
    inspector.
    """
    wavenumbers = [mode.wavenumber_cm1 for mode in result.modes]
    facts = [
        _summary_fact(
            "Modes", len(result.modes), str(len(result.modes)), category, _source_of(result)
        )
    ]
    if wavenumbers:
        places = label_decimals(result)
        low, high = min(wavenumbers), max(wavenumbers)
        facts.append(
            _summary_fact(
                "Wavenumbers",
                (low, high),
                f"{low:.{places}f} to {high:.{places}f}",
                category,
                _source_of(result),
                units=getattr(result, "units", "") or "cm^-1",
            )
        )
    return tuple(facts)


def _ph_curve_summary(result: PhCurveResult, category: FactCategory) -> tuple[Fact, ...]:
    """**THE PRODUCER'S OWN FACTS FIRST, UNCHANGED.** `PhCurveResult.facts`
    is where the pI and the LogP live -- scalars a producer COMPUTED, which
    used to be interpolated into the display name because there was nowhere
    to put them. They pass through; only the shape of the curve is projected.
    """
    projected = [
        _summary_fact(
            "Series",
            tuple(result.series),
            ", ".join(result.series) or "none",
            category,
            _source_of(result),
        )
    ]
    if result.ph_values:
        projected.append(
            _summary_fact(
                "pH range",
                (result.ph_values[0], result.ph_values[-1]),
                f"{result.ph_values[0]:.2f} to {result.ph_values[-1]:.2f}"
                f" ({len(result.ph_values)} points)",
                category,
                _source_of(result),
            )
        )
    return (*result.facts, *projected)


def _structure_set_summary(
    result: StructureSetResult, category: FactCategory
) -> tuple[Fact, ...]:
    """Counts, **never a SMILES list**.

    A hundred structures rendered as facts is the wall the reader exists to
    avoid, and the set already has an inspector that draws them. What a
    summary owes is how many there are and whether it is showing all of them
    -- `truncated` is a producer declaration and reads as a different claim
    from a short list.
    """
    facts = [
        _summary_fact(
            "Structures", len(result.entries), str(len(result.entries)),
            category, _source_of(result),
        )
    ]
    if result.total_available and result.total_available != len(result.entries):
        facts.append(
            _summary_fact(
                "Available", result.total_available, str(result.total_available),
                category, _source_of(result),
            )
        )
    if result.truncated:
        facts.append(
            _summary_fact(
                "Showing", "truncated",
                f"the first {len(result.entries)} of {result.total_available}",
                category, _source_of(result),
            )
        )
    return tuple(facts)


def _trajectory_summary(
    result: TrajectoryResult, category: FactCategory
) -> tuple[Fact, ...]:
    """Frames, duration and temperature -- and a final energy **only if an
    energy series exists**.

    A trajectory with no energies is an ordinary trajectory, and reporting
    `0.0` for one would be a number nobody computed sitting where a real
    energy goes.
    """
    facts = [
        _summary_fact(
            "Frames", len(result.frames), str(len(result.frames)), category, _source_of(result)
        )
    ]
    if result.times:
        facts.append(
            _summary_fact(
                "Duration", result.times[-1], f"{result.times[-1]:.6g}",
                category, _source_of(result), units="ps",
            )
        )
    if result.temperature is not None:
        facts.append(
            _summary_fact(
                "Temperature", result.temperature, f"{result.temperature:.6g}",
                category, _source_of(result), units="K",
            )
        )
    if result.energies:
        facts.append(
            _summary_fact(
                "Final energy", result.energies[-1], f"{result.energies[-1]:.6g}",
                category, _source_of(result), units="kcal/mol",
            )
        )
    return tuple(facts)


def _no_summary_needed(result: Any, _category: FactCategory) -> tuple[Fact, ...]:
    """This kind already has a report-shaped form, so `summarise` returns
    THAT rather than projecting one.

    **NAMED IN THE TABLE RATHER THAN LEFT OUT**, for the reason
    `_generic_to_text` is: "this is the right answer here" and "nothing
    matched" must stay distinguishable in the registry itself, which is
    exactly how the vibrational case stayed invisible. It RAISES rather than
    returning `()`, because an empty projection is indistinguishable from a
    result that genuinely had nothing to say -- and for these two the answer
    is not a projection at all.

    A `ReportResult` is returned whole so its provenance, cache state and
    version travel with it. An `AlertResult` goes through
    `chem/report_adapter.report_from_alert`, which is the ONE bridge for that
    and preserves the `cache_state` and `error` a refused catalog carries --
    a view built from its facts alone would render a failure as a calculator
    that ran and had nothing to say.
    """
    raise TypeError(
        f"{type(result).__name__} is already report-shaped; `summarise` returns "
        "its native form rather than a projection"
    )


def _no_chart(_result: Any) -> tuple:
    """This kind declares no chart. A named entry, same rule as above."""
    return ()


def _ph_curve_chart(result: PhCurveResult) -> tuple:
    """The curve itself, through the ONE adapter that already builds it.

    `ph_curve_widget.annotation_for` is what the pH dialog draws from, so the
    reader and that dialog cannot disagree about the picture. A second
    pairing of the grid with the series is exactly where a double transform
    would hide.

    **THE INSPECTOR TURNS ITS CHART OFF AND THIS DOES NOT**, and both are
    right: that dialog already shows the curve an inch above its facts, so a
    second plot of the same numbers is not a second view of them. The reader
    shows no curve at all without this.
    """
    from openchem.ui.widgets.ph_curve_widget import annotation_for

    annotation = annotation_for(result)
    return (annotation,) if annotation is not None else ()


@dataclass(frozen=True)
class ResultAdapter:
    """How one kind of result is presented."""

    #: Clipboard/text projection.
    to_text: Callable[[Any], str]
    #: Which dedicated viewer opens it, or `NO_RICH_VIEW`.
    rich_view: str
    #: The few facts a reader shows in place of the whole result.
    summary: Callable[[Any, FactCategory], tuple[Fact, ...]]
    #: Charts this kind can project. `()` for every kind whose content is not
    #: a curve -- named, not defaulted.
    chart: Callable[[Any], tuple]
    #: Which field holds "what arrived", and what one of them is called.
    #:
    #: **KEYED BY KIND BECAUSE PROBING FIELDS IN A FIXED ORDER GUESSES.**
    #: `PropertyPanel._summarise` walked a tuple of candidate attribute names
    #: and took the first one present -- with `("values", "atom")` FIRST. A
    #: vibrational spectrum leaves `values` empty on purpose, so the walk
    #: found an empty payload and the panel row read **"None found." for a
    #: spectrum with real modes in it**. Measured on three. That is the same
    #: one-vocabulary-many-registries defect the module docstring opens with,
    #: in a fourth consumer.
    #:
    #: `("", "")` for the two kinds that are already report-shaped: they are
    #: rendered as facts rather than as a one-line "what arrived".
    payload: tuple[str, str]


#: Kind -> how to present it. TOTAL over `RESULT_KINDS`, which
#: `test_every_kind_has_an_adapter` asserts -- a missing entry would raise a
#: KeyError deep in a paint path rather than at registration.
ADAPTERS: dict[str, ResultAdapter] = {
    REPORT: ResultAdapter(
        to_text=_report_to_text, rich_view=NO_RICH_VIEW,
        summary=_no_summary_needed, chart=_no_chart,
        payload=("", ""),
    ),
    ALERT: ResultAdapter(
        to_text=_alert_to_text, rich_view=NO_RICH_VIEW,
        summary=_no_summary_needed, chart=_no_chart,
        payload=("", ""),
    ),
    PER_ATOM: ResultAdapter(
        to_text=_per_atom_to_text, rich_view=CALCULATOR_INSPECTOR,
        summary=_per_atom_summary, chart=_no_chart,
        payload=("values", "atom"),
    ),
    SPECTRUM: ResultAdapter(
        to_text=_spectrum_to_text, rich_view=NMR_VIEW,
        summary=_spectrum_summary, chart=_no_chart,
        payload=("values", "signal"),
    ),
    VIBRATIONAL_SPECTRUM: ResultAdapter(
        to_text=_vibrational_to_text, rich_view=IR_VIEW,
        summary=_vibrational_summary, chart=_no_chart,
        payload=("modes", "mode"),
    ),
    PH_CURVE: ResultAdapter(
        to_text=_ph_curve_to_text, rich_view=CALCULATOR_INSPECTOR,
        summary=_ph_curve_summary, chart=_ph_curve_chart,
        payload=("ph_values", "pH point"),
    ),
    STRUCTURE_SET: ResultAdapter(
        to_text=_structure_set_to_text, rich_view=CALCULATOR_INSPECTOR,
        summary=_structure_set_summary, chart=_no_chart,
        payload=("entries", "structure"),
    ),
    TRAJECTORY: ResultAdapter(
        to_text=_generic_to_text, rich_view=CALCULATOR_INSPECTOR,
        summary=_trajectory_summary, chart=_no_chart,
        payload=("frames", "frame"),
    ),
}


def summarise(
    result: Any,
    *,
    result_id: str,
    name: str,
    category: str = "",
    structure_version: int = 0,
):
    """`result` in the shape the results reader consumes.

    **THE CALLER SUPPLIES THE TWO THINGS THE RESULT CANNOT KNOW.** Measured
    over every non-report result the registry produces for aspirin:
    `PerAtomDataset.category` is EMPTY for all twelve of them, and
    `PhCurveResult`, `StructureSetResult`, `TrajectoryResult` and
    `NMRSpectrumResult` have no such field at all -- so a summary that read
    the section off the result would file twenty entries under "Other".
    Neither does any of them carry a `structure_version`: only
    `StructureReport` does, so an unstamped summary would read as stale the
    moment the structure moved past 0, which is exactly what alert-derived
    reports used to do.

    `PropertyPanel._show_result` already resolves both at the point every one
    of these arrives, which is why they are arguments rather than a second
    injected lookup.

    A REPORT passes straight through: it is already what the reader consumes,
    and wrapping it would flatten its provenance into a view.
    """
    kind = kind_of(result)
    if kind == REPORT:
        return result
    if kind == ALERT:
        from openchem.chem.report_adapter import report_from_alert

        return report_from_alert(result)
    adapter = adapter_for(result)
    from openchem.domain.calculator_taxonomy import category_for
    from openchem.ui.result_summary import ResultSummaryView

    fact_category = category_for(category)
    producer_limitations = tuple(getattr(result, "limitations", ()) or ())
    return ResultSummaryView(
        report_id=result_id,
        name=name,
        category=category,
        facts=adapter.summary(result, fact_category),
        charts=adapter.chart(result),
        # The projection's own caveat FIRST, then whatever the producer said.
        # A reader meeting the producer's caveats under a summary would have
        # no way to tell which half it was reading.
        limitations=(SUMMARY_LIMITATION, *producer_limitations),
        molecule_uuid=str(getattr(result, "molecule_uuid", "") or ""),
        structure_version=structure_version,
        # CARRIED, NEVER RE-DERIVED. A refused calculator has fewer facts to
        # project than a successful one, so it is exactly the case a summary
        # would otherwise render as a producer that ran and had nothing to
        # say -- the statement `merge_reports` stopped making when it stopped
        # gating on facts.
        cache_state=getattr(result, "cache_state", None),
        error=getattr(result, "error", None),
        error_summary=getattr(result, "error_summary", None),
        inapplicable=bool(getattr(result, "inapplicable", False)),
    )


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
