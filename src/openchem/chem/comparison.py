"""Building a per-atom comparison, and the atom correspondence it needs.

The correspondence is the hard half and the reason this is not a loop over
`zip()`. Aspirin's carbonyl carbon is atom 8; salicylic acid's is atom 2.
Comparing index against index would subtract an oxygen from a carbon and
report a confident number for it.

**The correspondence here is 2D and needs no conformer**, unlike
`chem/alignment.py`'s, which computes the same maximum common substructure
and then throws the mapping into O3A. That path drops hydrogens (O3A
refuses them as constraints) and generates a conformer if one is missing --
both correct for 3D overlay, both wrong here. A partial charge exists for a
freshly drawn molecule with no 3D coordinates at all, and its hydrogens
carry some of the most interesting differences.
"""

from __future__ import annotations

import logging
import math

from rdkit import Chem
from rdkit.Chem import rdFMCS

from openchem.chem.result_reduction import PER_ATOM_AGGREGATES
from openchem.domain.comparison import (
    AtomDelta,
    ComparisonDataset,
    ComparisonEntry,
    EntryKind,
)
from openchem.domain.common import CATEGORICAL_SCALE, CacheState, Provenance
from openchem.domain.scientific_result import PerAtomDataset
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: Seconds `rdFMCS` may spend before returning its best effort.
#:
#: `FindMCS`'s own signature defaults this to `timeout=3600` (checked, not
#: assumed -- note `MCSParameters().Timeout` reads 0, so the two entry
#: points disagree and the function's default is the one that applies
#: here). An hour on a pair it cannot solve means the window is gone for an
#: hour. A partial MCS is still a usable correspondence; an unresponsive
#: dialog is not.
MCS_TIMEOUT = 10

#: Aromatic bonds match ONLY aromatic bonds, and this is load-bearing.
#:
#: RDKit's default `CompareOrder` treats aromatic and single as
#: interchangeable -- its SMARTS comes back containing `:,-` -- so the MCS
#: happily opens benzene's ring and maps it onto a six-carbon sugar chain.
#: Measured: benzene against glucose matched 12 of 12 atoms with ZERO
#: element mismatches, which is why checking elements agree is not enough
#: to catch it. With `CompareOrderExact` that pair collapses to 2.
#:
#: The obvious-looking alternatives were measured and are worse. Atoms
#: mapped, per arm -- `ringOnly` is `ringMatchesRingOnly` alone, `strict` is
#: that plus `completeRingsOnly` plus `CompareOrderExact`, `exactOnly` is
#: the bond compare on its own (what ships):
#:
#:     pair                  default  ringOnly  strict  exactOnly
#:     benzene/glucose            12        10       2          2
#:     glucose ring/open          22         5       5         22
#:     pyridine/benzene           10        10       2         10
#:     cyclopentane/cyclohexane   15        15       3         15
#:     aspirin/salicylic acid     15        15      15         15
#:     morphine/codeine           39        39      39         39
#:
#: `ringMatchesRingOnly` is the clearest loser: it costs glucose 22 -> 5 and
#: still leaves benzene mapping 10 atoms onto a sugar.
#:
#: Glucose's pyranose against its open-chain aldehyde is a tautomer pair a
#: chemist genuinely wants to compare, and ring-based strictness throws it
#: away to fix nothing.
#:
#: The cost, stated plainly: benzene against cyclohexane also collapses to
#: 2. That is deliberate. An aromatic carbon and an sp3 carbon at "the same
#: position" are not the same site, and a partial-charge difference between
#: them is not a difference at a shared atom.
_BOND_COMPARE = rdFMCS.BondCompare.CompareOrderExact

_AGGREGATES = {
    "mean": lambda values: sum(values) / len(values),
    "sum": sum,
    "min": min,
    "max": max,
    "max_abs": lambda values: max(values, key=abs),
}


def atom_correspondence(
    reference: Chem.Mol, other: Chem.Mol, *, timeout: int = MCS_TIMEOUT
) -> dict[int, int]:
    """Reference atom index -> the matching atom index in `other`.

    Empty when the two share no substructure, which is a real answer:
    benzene and glucose have nothing to compare atom-wise, and an empty
    mapping says so where a fabricated one would not.

    **There is deliberately no fast path for "the same molecule".** One was
    written -- equal canonical SMILES and equal atom count, return
    `{i: i}` -- and it is wrong, because neither condition constrains atom
    ORDER. Measured on salicylic acid written two ways
    (`OC(=O)c1ccccc1O` against `Oc1ccccc1C(=O)O`): same canonical SMILES,
    same 16 atoms, and index-against-index pairs an oxygen with a carbon at
    indices 2 and 8. Two copies of one structure that arrived by different
    routes -- one parsed from a molblock, one from SMILES -- are exactly the
    case a conformer or method comparison hits.

    The MCS handles both. It returns the identity for molecules that really
    are in the same order (measured on five, including cyclohexane and its
    768 automorphisms) and the correct permutation for those that are not.
    """
    if reference.GetNumAtoms() == 0 or other.GetNumAtoms() == 0:
        return {}

    try:
        result = rdFMCS.FindMCS([reference, other], timeout=timeout, bondCompare=_BOND_COMPARE)
    except Exception:  # noqa: BLE001 - a failed MCS is "no correspondence", not a crash
        logger.exception("MCS failed while building an atom correspondence")
        return {}
    if not result.smartsString or result.numAtoms == 0:
        return {}

    pattern = Chem.MolFromSmarts(result.smartsString)
    if pattern is None:
        return {}
    reference_match = reference.GetSubstructMatch(pattern)
    other_match = other.GetSubstructMatch(pattern)
    if not reference_match or not other_match:
        return {}
    return dict(zip(reference_match, other_match))


def build_comparison(
    results: dict[str, PerAtomDataset | None],
    names: dict[str, str],
    *,
    calculator_id: str,
    calculator_name: str,
    aggregate: str = "mean",
    order: list[str] | None = None,
) -> ComparisonDataset:
    """Assemble one calculator's results for several molecules.

    A molecule mapped to None becomes an `ABSENT` entry rather than being
    dropped, so a comparison of four molecules where one has not been
    computed still shows four rows. Silently showing three is how a
    comparison becomes misleading -- the reader has no way to know a
    molecule is missing rather than merely unremarkable.
    """
    if aggregate not in PER_ATOM_AGGREGATES:
        aggregate = "mean"

    uuids = order if order is not None else list(results)
    entries: list[ComparisonEntry] = []
    units = ""
    categorical = False

    for uuid in uuids:
        name = names.get(uuid, uuid)
        result = results.get(uuid)
        if result is None:
            entries.append(
                ComparisonEntry(
                    molecule_uuid=uuid,
                    molecule_name=name,
                    kind=EntryKind.ABSENT,
                    note="not computed",
                )
            )
            continue

        units = units or result.units
        if _is_categorical(result):
            categorical = True

        if result.cache_state is CacheState.FAILED:
            entries.append(
                ComparisonEntry(
                    molecule_uuid=uuid,
                    molecule_name=name,
                    kind=EntryKind.ABSENT,
                    note=result.error or "failed",
                )
            )
            continue

        if not result.values:
            # Empty is not failure: caffeine really does match zero
            # functional groups. Carry the producer's own sentence when it
            # left one, exactly as the batch path does.
            entries.append(
                ComparisonEntry(
                    molecule_uuid=uuid,
                    molecule_name=name,
                    kind=EntryKind.PER_ATOM,
                    values={},
                    aggregate=aggregate,
                    units=result.units,
                    note=_summary_note(result) or "no values",
                )
            )
            continue

        numbers = list(result.values.values())
        entries.append(
            ComparisonEntry(
                molecule_uuid=uuid,
                molecule_name=name,
                kind=EntryKind.PER_ATOM,
                # A categorical dataset gets no scalar. The mean of the ring
                # system ids 1, 2 and 3 is 2.0 and describes nothing.
                scalar=None if categorical else _AGGREGATES[aggregate](numbers),
                values=dict(result.values),
                aggregate="" if categorical else aggregate,
                units=result.units,
            )
        )

    limitations: list[str] = []
    if categorical:
        limitations.append(
            "These values are category identifiers, not measurements. "
            "Differences between them are not meaningful."
        )

    return ComparisonDataset(
        calculator_id=calculator_id,
        calculator_name=calculator_name,
        entries=tuple(entries),
        aggregate="" if categorical else aggregate,
        units=units,
        categorical=categorical,
        limitations=tuple(limitations),
        provenance=Provenance(
            created_by="comparison",
            method=calculator_id,
            parameters={"aggregate": aggregate},
        ),
    )


def deltas_against(
    dataset: ComparisonDataset,
    reference_uuid: str,
    other_uuid: str,
    correspondence: dict[int, int],
    *,
    reference_mol: Chem.Mol | None = None,
) -> list[AtomDelta]:
    """Per-atom differences for the atoms the two molecules share.

    Refuses a categorical dataset outright rather than returning plausible
    nonsense: subtracting functional-group id 3 from id 7 yields 4, which
    is a number and means nothing at all.

    Atoms outside the correspondence are omitted, not zero-filled. An atom
    that exists in only one of the two has no difference to report, and a
    zero there would read as "identical here" -- the opposite of the truth.
    """
    if dataset.categorical:
        return []
    reference = dataset.entry_for(reference_uuid)
    other = dataset.entry_for(other_uuid)
    if reference is None or other is None or not reference or not other:
        return []

    deltas: list[AtomDelta] = []
    for reference_index, other_index in sorted(correspondence.items()):
        if reference_index not in reference.values or other_index not in other.values:
            continue
        element = ""
        if reference_mol is not None and reference_index < reference_mol.GetNumAtoms():
            element = reference_mol.GetAtomWithIdx(reference_index).GetSymbol()
        deltas.append(
            AtomDelta(
                reference_index=reference_index,
                other_index=other_index,
                reference_value=reference.values[reference_index],
                other_value=other.values[other_index],
                element=element,
            )
        )
    return deltas


def _is_categorical(result: PerAtomDataset) -> bool:
    provenance = getattr(result, "provenance", None)
    if provenance is None:
        return False
    try:
        return provenance.parameters.get("scale") == CATEGORICAL_SCALE
    except AttributeError:
        return False


def _summary_note(result: PerAtomDataset) -> str:
    provenance = getattr(result, "provenance", None)
    if provenance is None:
        return ""
    try:
        return str(provenance.parameters.get("summary", "") or "")
    except AttributeError:
        return ""


# --- comparing molecules on their reported VALUES ---------------------------
#
# The existing machinery above compares one calculator's PER-ATOM data
# between two structures, which needs atom correspondence and is the hard
# case. This is the everyday one: aspirin against salicylic acid, on
# molecular weight and TPSA and LogP, side by side.
#
# Kept in `chem/` rather than in the panel so it is testable without Qt,
# and so the AI assistant and any export can reach the same rows.


@dataclass(frozen=True)
class CompareCell:
    """One molecule's value for one property, WITH where it came from.

    **A CELL THAT FORGETS ITS SOURCE CANNOT BE CLICKED THROUGH.** The table used to keep only
    `(display, units)`, so a double-click had no report to open and the numbers had no help text.
    `numeric_value` is the producer's own number (`DescriptorValue.value` / `Fact.value`), never
    parsed back out of `display`, which is rounded and may carry units or text.
    """

    display: str
    units: str = ""
    numeric_value: float | None = None
    #: Which property this is, independent of its wording: two reports that both call a fact
    #: "Energy" are two rows, and the user-facing label is never the key.
    row_key: str = ""
    #: The reader report this value sits in (`reveal_fact`'s first argument); "" when unknown.
    report_id: str = ""
    #: The fact's label inside that report (`reveal_fact`'s second argument).
    fact_label: str = ""
    help_id: str = ""
    link: object | None = None


def finite_number(value: object) -> float | None:
    """`value` as a float when it is a real, finite number (not a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class ValueRow:
    """One property across every molecule being compared.

    `values` is positional and always the same length as the molecule
    list, with `""` where a molecule has no such value -- a ragged row
    would put a number under the wrong heading, which is the one failure
    mode a comparison table must not have.
    """

    label: str
    units: str
    values: tuple[str, ...]
    #: Whether the molecules disagree. Absence counts as disagreement: a
    #: property one molecule has and another does not IS a difference, and
    #: hiding that row under "differences only" would be the more
    #: misleading of the two choices.
    differs: bool
    #: What the row IS (see `CompareCell.row_key`); the dict key it was built from.
    row_key: str = ""
    #: Positional like `values`; None where a molecule has no value, or the input was a bare tuple.
    cells: tuple[CompareCell | None, ...] = ()

    def numeric_values(self) -> tuple[float | None, ...]:
        """The values as numbers where they are numbers.

        Offered rather than stored: a row is built from display strings so
        it can carry "C9H8O4" and "ambiphilic" as readily as "180.16", and
        a consumer that wants to sort or plot asks for the numbers.
        """
        out: list[float | None] = []
        for text in self.values:
            try:
                out.append(float(text.split()[0]) if text else None)
            except (ValueError, IndexError):
                out.append(None)
        return tuple(out)

    def numbers(self) -> tuple[float | None, ...]:
        """The producers' own numbers, where each cell has one (never parsed from the text)."""
        return tuple(cell.numeric_value if cell is not None else None for cell in self.cells)

    def source_cell(self) -> tuple[int, CompareCell] | None:
        """The first molecule (in column order) that HAS a value, with its cell.

        The Property column opens this one: opening the first column's cell when it is blank
        would send somebody to a fact that molecule does not have.
        """
        for index, cell in enumerate(self.cells):
            if cell is not None and cell.display:
                return index, cell
        return None


def _as_cell(key: str, entry: object) -> CompareCell:
    """A bare `(display, units)` pair, or a cell, as a cell."""
    if isinstance(entry, CompareCell):
        return entry
    display, units = entry  # type: ignore[misc]
    return CompareCell(display=display, units=units, row_key=key, fact_label=key)


def compare_values(
    columns: list[tuple[str, dict[str, object]]],
) -> list[ValueRow]:
    """Molecules side by side, one row per property.

    `columns` is ordered `(molecule_name, {row_key: CompareCell | (display_value, units)})`.
    Ordered rather than a mapping because the caller chose the column
    order and a dict would silently reorder it. A bare pair is its own key
    and label, which is what every caller did before cells existed.

    **Rows are keyed by `row_key`, not by wording.** Two reports that both
    emit "Energy" are two properties; when their labels collide the row
    label gains the report it came from, so the table never shows two
    indistinguishable rows.

    **Rows come out in first-seen order, not sorted.** A calculator emits
    its facts in a deliberate order -- formula before mass before
    composition -- and alphabetising would scatter that. A property only
    the third molecule has appears after the ones the first two share,
    which is also the order somebody added them.
    """
    order: list[str] = []
    units_by_key: dict[str, str] = {}
    label_by_key: dict[str, str] = {}
    report_by_key: dict[str, str] = {}
    for _name, values in columns:
        for key, entry in values.items():
            cell = _as_cell(key, entry)
            if key not in units_by_key:
                order.append(key)
                units_by_key[key] = cell.units
                label_by_key[key] = cell.fact_label or key
                report_by_key[key] = cell.report_id
            elif not units_by_key[key]:
                units_by_key[key] = cell.units

    wording = [label_by_key[key] for key in order]
    rows: list[ValueRow] = []
    for key in order:
        cells = tuple(
            _as_cell(key, values[key]) if key in values else None for _name, values in columns
        )
        shown = tuple(cell.display if cell is not None else "" for cell in cells)
        label = label_by_key[key]
        if wording.count(label) > 1 and report_by_key[key]:
            label = f"{label} [{report_by_key[key]}]"
        rows.append(
            ValueRow(
                label=label,
                units=units_by_key[key],
                values=shown,
                differs=len(set(shown)) > 1,
                row_key=key,
                cells=cells,
            )
        )
    return rows


def differing_rows(rows: list[ValueRow]) -> list[ValueRow]:
    """Only the rows where the molecules disagree.

    THE FEATURE THAT MAKES A COMPARISON WORTH OPENING. Aspirin against
    salicylic acid share most of a sixty-row table; the four rows that
    differ are the answer, and finding them by eye is the work the table
    was supposed to save.
    """
    return [row for row in rows if row.differs]


# --- which molecule is higher, and what that may be said to mean ------------------
#
# A bigger number is not a better one, and for a quantity on a log scale or one that can be
# negative "twice as much" is meaningless. So direction is only offered for properties someone
# has decided it is meaningful for, and says no more than the policy allows. Anything not listed
# gets no marker at all: silence, not an invented interpretation.

#: Ordering is meaningful: one is higher than the other. No factor is offered.
ORDER = "order"
#: A ratio scale (a mass, an area, a count of atoms): "about 2.5 times" is meaningful too.
RATIO = "ratio"

#: `help_id` -> what may be said about a difference. Deliberately small and reviewed; a row not in
#: it is never marked. LogP and logS are log scales, so they are ORDER only.
COMPARISON_POLICY: dict[str, str] = {
    "descriptor.mol_wt": RATIO,
    "descriptor.exact_mass": RATIO,
    "descriptor.heavy_atom_count": RATIO,
    "descriptor.tpsa": RATIO,
    "descriptor.mol_logp": ORDER,
    "descriptor.esol_logs": ORDER,
    "descriptor.num_rotatable_bonds": ORDER,
    "descriptor.num_hbd": ORDER,
    "descriptor.num_hba": ORDER,
    "descriptor.ring_count": ORDER,
}


@dataclass(frozen=True)
class Direction:
    """Which molecules have the highest and lowest value of one row.

    Indices are positions in the row (molecule order). `factor` is highest / lowest, only for a
    ratio-scale row whose values are all positive; `difference` is highest - lowest.
    """

    highest: tuple[int, ...]
    lowest: tuple[int, ...]
    difference: float
    factor: float | None = None


def direction(row: ValueRow) -> Direction | None:
    """Which molecule(s) are highest and lowest on `row`, or None when that should not be said.

    None when: the row's property has no comparison policy; fewer than two molecules have a real
    finite number (a missing value is never read as zero); the present values do not share one
    unit (the numbers would not be comparable); or they are all equal.
    """
    cells = [(i, c) for i, c in enumerate(row.cells) if c is not None and c.numeric_value is not None]
    if len(cells) < 2:
        return None
    policy = next((COMPARISON_POLICY[c.help_id] for _i, c in cells if c.help_id in COMPARISON_POLICY), None)
    if policy is None:
        return None
    if len({c.units for _i, c in cells}) != 1:
        return None
    numbers = [c.numeric_value for _i, c in cells]
    high, low = max(numbers), min(numbers)
    if high == low:
        return None
    factor = high / low if policy == RATIO and low > 0 else None
    return Direction(
        highest=tuple(i for i, c in cells if c.numeric_value == high),
        lowest=tuple(i for i, c in cells if c.numeric_value == low),
        difference=high - low,
        factor=factor,
    )


#: One clause per reviewed property, in the order a summary tells them. `{hi}`/`{lo}` are the
#: molecules' names and `{a}`/`{b}` their values (the higher's first). Worded as "calculated" /
#: "estimated" because that is what these are, and never as better or worse.
_SUMMARY_CLAUSES: tuple[tuple[str, str], ...] = (
    ("descriptor.mol_wt", "{hi} is heavier ({a} against {b} g/mol)."),
    (
        "descriptor.mol_logp",
        "{hi} has the higher estimated LogP ({a} against {b}), which means it is estimated to lean "
        "more toward oily surroundings, and less toward watery ones, than {lo} does.",
    ),
    (
        "descriptor.tpsa",
        "{hi} has more water-attracting surface (polar surface area {a} against {b} A^2).",
    ),
    (
        "descriptor.esol_logs",
        "{hi} is estimated to dissolve more readily in water ({a} against {b} on a log scale).",
    ),
)


def summary_sentence(names: list[str], rows: list[ValueRow]) -> str:
    """A few plain sentences about exactly two molecules, or "" when there is nothing sound to say.

    Only properties with a written clause are told, only when both molecules have a real number in
    the same unit and the numbers differ. It never infers anything from an unreviewed row.
    """
    if len(names) != 2:
        return ""
    by_help = {}
    for row in rows:
        helps = [c.help_id for c in row.cells if c is not None and c.help_id]
        if helps:
            by_help.setdefault(helps[0], row)
    told: list[str] = []
    for help_id, template in _SUMMARY_CLAUSES:
        row = by_help.get(help_id)
        found = direction(row) if row is not None else None
        if found is None or len(found.highest) != 1 or len(found.lowest) != 1:
            continue
        hi, lo = found.highest[0], found.lowest[0]
        told.append(
            template.format(
                hi=names[hi], lo=names[lo], a=row.values[hi], b=row.values[lo]
            )
        )
    return ("By these calculated numbers: " + " ".join(told)) if told else ""
