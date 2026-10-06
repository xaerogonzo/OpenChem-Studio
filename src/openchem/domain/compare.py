"""Comparing per-atom results from different methods -- only where a comparison means something.

**THE STORE HOLDS ONE RESULT PER CALCULATOR PER STRUCTURE**, so running a second charge model
replaced the first: two methods could never be on screen together, which is the whole reason
comparing them was hard. The Properties panel now keeps a short pool of the per-atom results a
structure has produced (one per method and parameters), and this module says which of them can
honestly be set beside each other.

A column-by-column table is only true if every column describes THE SAME THING, and a per-atom
result can differ from another in ways the table would hide -- a value for atom 5 of one structure
beside a value for atom 5 of another reads as a comparison and is not one:

    the same molecule           a charge for ethanol beside one for benzene means nothing
    the same input fingerprint  the same molecule EDITED between the runs has different atoms
    the same calculation input  a drawing's atoms (no explicit hydrogens) are not a conformer's
    the same atoms              the same indices, or the rows do not line up
    the same units              e beside kcal/mol is not a difference
    two different results       a result beside itself is a table of zeros

Otherwise it REFUSES, and says which. That is the point of the module: a Compare that quietly
tabulates whatever it is handed is a way to publish a wrong difference.

Pure and Qt-free.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from openchem.domain.scientific_result import PerAtomDataset, SpectrumResult

#: The fewest results a comparison has: one is a table, not a comparison.
MIN_COMPARED = 2

#: The most. Four columns, their differences and a spread do not fit a window that is also
#: meant to be read, and nobody is choosing among more than four charge models by eye.
MAX_COMPARED = 4


@dataclass(frozen=True)
class ComparedResult:
    """One per-atom result and the identity that says what its atoms ARE.

    The dataset does not carry its own input fingerprint or calculation input (no result
    type does -- they are known by whoever dispatched it), so they travel beside it.
    "" means the producer did not say.
    """

    dataset: PerAtomDataset
    input_fingerprint: str = ""
    calculation_input: str = ""
    #: The result this was made from, when it is not itself a `PerAtomDataset` -- a spectrum
    #: (`spectrum_as_per_atom`). Lets a window that holds the spectrum find its own entry, and
    #: lets the caller read what the dataset view dropped (the element of each atom).
    origin: object | None = None
    #: Set by `distinguish_labels` when two results would otherwise carry one name.
    display_label: str = ""

    @property
    def label(self) -> str:
        """What the column is called: the result's own name, which usually carries the method."""
        return self.display_label or str(self.dataset.name or self.dataset.method or self.dataset.property_id)

    def same_result_as(self, other: ComparedResult) -> bool:
        """Whether this is the very same calculation: same property, method and parameters."""
        a, b = self.dataset, other.dataset
        return (
            a.property_id == b.property_id
            and a.method == b.method
            and _parameters_of(a) == _parameters_of(b)
        )


def spectrum_as_per_atom(spectrum: SpectrumResult) -> PerAtomDataset:
    """A spectrum seen as the per-atom result it is, so it meets the same rules a charge does.

    A predicted NMR spectrum IS one number per nucleus keyed by atom index, so setting the
    database lookup's shifts beside an ab initio run's is the same comparison as setting two
    charge models side by side -- and needs the same refusals (the same molecule, the same
    drawing, the same atoms, the same units), which this reuses rather than restating. Only the
    shape changes; nothing is added, so the method and units stay exactly the spectrum's own.
    """
    return PerAtomDataset(
        property_id=spectrum.spectrum_type,
        name=spectrum.name,
        units=spectrum.units,
        method=spectrum.method,
        molecule_uuid=spectrum.molecule_uuid,
        values=dict(spectrum.values),
        provenance=spectrum.provenance,
        cache_state=spectrum.cache_state,
        error=spectrum.error,
    )


def distinguish_labels(results: Sequence[ComparedResult]) -> list[ComparedResult]:
    """`results` with any repeated label made unique, by what actually differs between them.

    Two runs of one calculator under different settings have the same name, and a table with two
    columns called "C NMR (experimental database)" cannot be read: which is the reference? So a
    label that repeats gains the parameters that differ among its twins (`(spheres=2)`), and
    where nothing differs, its position. Labels that are already unique are left exactly alone.
    """
    results = list(results)
    labels = [r.label for r in results]
    out: list[ComparedResult] = []
    for position, result in enumerate(results):
        twins = [i for i, label in enumerate(labels) if label == labels[position]]
        if len(twins) == 1:
            out.append(result)
            continue
        parameters = [_parameters_of(results[i].dataset) for i in twins]
        # Scalar settings only: provenance also carries diagnostics (a per-atom table of match
        # counts), which differ between any two runs and would swamp the heading.
        keys = sorted({key for p in parameters for key, v in p.items() if isinstance(v, (bool, int, float, str))})
        varying = [k for k in keys if len({repr(p.get(k)) for p in parameters}) > 1]
        mine = _parameters_of(result.dataset)
        if varying:
            detail = ", ".join(f"{k}={mine.get(k)}" for k in varying)
        else:
            detail = str(twins.index(position) + 1)
        out.append(replace(result, display_label=f"{labels[position]} ({detail})"))
    return out


def _parameters_of(dataset: PerAtomDataset) -> dict:
    provenance = getattr(dataset, "provenance", None)
    parameters = getattr(provenance, "parameters", None)
    return dict(parameters) if isinstance(parameters, dict) else {}


@dataclass(frozen=True)
class CompareRefusal:
    """Why these results cannot be compared, as a code a caller can branch on and a sentence."""

    code: str
    message: str


#: Fewer than two results: one is a table, not a comparison.
TOO_FEW = "TOO_FEW"

#: More than `MAX_COMPARED` results.
TOO_MANY = "TOO_MANY"

#: The results are for different molecules.
DIFFERENT_MOLECULES = "DIFFERENT_MOLECULES"

#: The results describe different structures: the molecule was edited between the runs,
#: or one was computed on a protonation state and another on the drawing.
DIFFERENT_STRUCTURE = "DIFFERENT_STRUCTURE"

#: One result was computed on the drawing and another on a 3D conformer.
DIFFERENT_INPUT = "DIFFERENT_INPUT"

#: The results are keyed by different atoms, so their rows do not line up.
DIFFERENT_ATOMS = "DIFFERENT_ATOMS"

#: The results are in different units.
DIFFERENT_UNITS = "DIFFERENT_UNITS"

#: The same calculation appears twice.
SAME_RESULT_TWICE = "SAME_RESULT_TWICE"


@dataclass(frozen=True)
class AtomRow:
    """One atom across every compared result."""

    index: int
    #: One value per compared result, in the order they were given.
    values: tuple[float, ...]
    #: Largest minus smallest across the results: how much the methods disagree here.
    spread: float
    #: Each later result minus the FIRST, so the first is the reference.
    deltas: tuple[float, ...]


@dataclass(frozen=True)
class Comparison:
    """Two to four per-atom results, lined up atom by atom."""

    columns: tuple[ComparedResult, ...]
    units: str
    rows: tuple[AtomRow, ...]

    def largest_spread(self) -> AtomRow | None:
        """The atom the methods disagree about most, or None for an empty comparison."""
        return max(self.rows, key=lambda row: row.spread, default=None)

    def as_text(self, symbols: dict[int, str] | None = None) -> str:
        """The table as tab-separated text, for a paste into a notebook or a spreadsheet."""
        symbols = symbols or {}
        header = ["atom", "element", *(c.label for c in self.columns), "spread"]
        header += [f"delta {c.label} - {self.columns[0].label}" for c in self.columns[1:]]
        lines = ["\t".join(header)]
        for row in self.rows:
            cells = [str(row.index + 1), symbols.get(row.index, "")]
            cells += [f"{value:.6g}" for value in row.values]
            cells.append(f"{row.spread:.6g}")
            cells += [f"{delta:.6g}" for delta in row.deltas]
            lines.append("\t".join(cells))
        return f"Units: {self.units}\n" + "\n".join(lines)


def compare(results: Sequence[ComparedResult]) -> Comparison | CompareRefusal:
    """Line up per-atom `results`, or refuse and say why.

    The refusals are checked in the order a person would want to hear them: the count first,
    then that these are the same molecule, then that its atoms are the same atoms.
    """
    if len(results) < MIN_COMPARED:
        return CompareRefusal(TOO_FEW, f"Choose at least {MIN_COMPARED} results to compare.")
    if len(results) > MAX_COMPARED:
        return CompareRefusal(TOO_MANY, f"At most {MAX_COMPARED} results can be compared at once.")

    results = distinguish_labels(results)
    first = results[0]
    labels = [r.label for r in results]

    if any(r.dataset.molecule_uuid != first.dataset.molecule_uuid for r in results):
        return CompareRefusal(DIFFERENT_MOLECULES, "These results are for different molecules.")

    # "" is "the producer did not say". Stated and unstated cannot be confirmed equal, so
    # a mixture is refused; none stated (a test double) compares as equal.
    fingerprints = {r.input_fingerprint for r in results}
    if len(fingerprints) > 1:
        return CompareRefusal(
            DIFFERENT_STRUCTURE,
            "These results were computed for different drawings of this molecule -- it was "
            "edited between the runs -- so atom 5 of one is not atom 5 of the other. Run the "
            "methods again on the structure as it is now.",
        )
    if len({r.calculation_input for r in results}) > 1:
        return CompareRefusal(
            DIFFERENT_INPUT,
            "One result was computed on the drawing and another on a 3D conformer, which have "
            "different atoms (a conformer carries explicit hydrogens).",
        )

    # A result can be keyed by ITS OWN structure rather than the drawing's: the pH-dependent
    # charges are computed on a selected microspecies, whose atoms are renumbered wherever a
    # proton leaves. Two of them at different pH, or one beside a drawing-based result, have
    # different atoms whatever their fingerprints say about the drawing.
    if len({r.dataset.structure_fingerprint for r in results}) > 1:
        return CompareRefusal(
            DIFFERENT_STRUCTURE,
            "These results describe different structures (for example a protonation state at one "
            "pH beside another, or beside the drawing), so their atoms are not the same atoms.",
        )

    if any(r.dataset.units != first.dataset.units for r in results):
        stated = ", ".join(f"{label}: {r.dataset.units or 'no units'}" for label, r in zip(labels, results))
        return CompareRefusal(DIFFERENT_UNITS, f"These results are in different units ({stated}).")

    atoms = set(first.dataset.values)
    if any(set(r.dataset.values) != atoms for r in results):
        return CompareRefusal(
            DIFFERENT_ATOMS,
            "These results cover different atoms, so their rows do not line up.",
        )

    for position, candidate in enumerate(results):
        for other in results[position + 1:]:
            if candidate.same_result_as(other):
                return CompareRefusal(
                    SAME_RESULT_TWICE,
                    f"{candidate.label} appears twice; a result compared with itself is all zeros.",
                )

    rows = []
    for index in sorted(atoms):
        values = tuple(float(r.dataset.values[index]) for r in results)
        rows.append(
            AtomRow(
                index=index,
                values=values,
                spread=max(values) - min(values),
                deltas=tuple(value - values[0] for value in values[1:]),
            )
        )
    return Comparison(columns=tuple(results), units=first.dataset.units, rows=tuple(rows))
