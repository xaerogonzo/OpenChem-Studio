"""A table of computed values: molecules down, properties across.

Every other result type in this package answers a question about ONE
molecule. This one is the first that is about a SET of them, and it exists
because a project of 200 molecules and 46 calculators had no expressible
form -- `ProjectModel.molecules` was already a list and nothing could act
on it as a set.

WHY A CELL IS NOT JUST A NUMBER. The single-molecule views label every
result with what produced it and how far it can be trusted (`Provenance`,
`prediction_basis`), and a table is exactly where that honesty is easiest
to lose: 200 rows of bare numbers read as measurements. So the provenance
travels per CELL (two rows can hold values from different runs, methods or
timestamps) and the empirical/ab-initio label travels per COLUMN (it is a
property of the calculator, not of the molecule it ran on).

`value` and `text` are separate fields rather than one formatted string
because they answer different questions. `text` is what a human reads,
including for results that have no number at all ("3 alerts", "no
stereocentres"). `value` is what the analytics consume, and is None when
the cell genuinely has no number -- which the correlation and PCA paths
must skip rather than coerce to zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openchem.domain.common import CacheState, Provenance

#: `BatchColumn.source` values. Plain strings for the same reason
#: `CalculatorDefinition.category` is one: a new source needs a new
#: producer, not an enum edit in `domain/`.
SOURCE_DESCRIPTOR = "descriptor"
SOURCE_CALCULATOR = "calculator"
SOURCE_DOCKING = "docking"
SOURCE_DERIVED = "derived"


@dataclass(frozen=True, kw_only=True)
class BatchColumn:
    """One column: a property computed the same way for every row.

    `column_id` is namespaced by source (`descriptor:mol_wt`,
    `calculator:topology_analysis:Wiener index`) because a calculator that
    reports several numbers becomes several columns, and those need to be
    distinguishable from each other and from a descriptor of the same
    name. See `chem/result_reduction.py`.
    """

    column_id: str
    label: str
    units: str = ""
    source: str = SOURCE_CALCULATOR
    #: The descriptor_id or calculator_id this came from -- kept separate
    #: from `column_id` so several columns can be traced back to the one
    #: calculator that produced them.
    source_id: str = ""
    #: "empirical" | "ab_initio" | None, copied from the
    #: `CalculatorDefinition`. Same field, same meaning, same honesty as
    #: the Property panel's badge.
    prediction_basis: str | None = None
    #: False for a column that is text-only (a molecular formula, a list of
    #: matched alerts). The analytics offer only numeric columns, and a
    #: column that looks selectable but yields an empty scatter is worse
    #: than one that is absent.
    numeric: bool = True

    @property
    def header(self) -> str:
        return f"{self.label} ({self.units})" if self.units else self.label


@dataclass(frozen=True, kw_only=True)
class BatchCell:
    """One computed value for one molecule.

    A cell that failed is a real, expected outcome -- a 3D descriptor on a
    molecule with no conformer, a sidecar that is not configured -- and is
    represented rather than omitted, so a column of 200 values with 3 gaps
    reads as three explained failures instead of a silently shorter column.
    """

    value: float | None = None
    text: str = ""
    provenance: Provenance | None = None
    cache_state: CacheState = CacheState.COMPLETED
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.cache_state is CacheState.FAILED


@dataclass
class BatchTable:
    """Molecules as rows, computed properties as columns.

    Mutable, unlike every `ScientificResult` in this package, because it is
    built incrementally as a run progresses -- the panel shows partial
    results while the remaining molecules are still being computed, and a
    frozen table would mean rebuilding it once per molecule.

    Columns are DISCOVERED, not declared up front. A calculator that
    reports "Wiener index: 42" contributes a numeric column that nothing
    could have known the name of before it ran, and that is most of what
    makes 46 calculators tabulate into something worth analysing. The
    column order is first-seen order, which is the order the calculators
    were requested in.
    """

    row_uuids: list[str] = field(default_factory=list)
    row_labels: dict[str, str] = field(default_factory=dict)
    columns: list[BatchColumn] = field(default_factory=list)
    cells: dict[tuple[str, str], BatchCell] = field(default_factory=dict)
    #: (molecule_uuid, calculator_id) -> the un-reduced per-atom result.
    #:
    #: A cell keeps ONE number, which is right for a 200-row survey and
    #: throws away the only thing a difference map can be built from --
    #: aspirin against salicylic acid coloured by delta charge is a question
    #: about atom 7 against atom 7, and the mean has no atoms left in it.
    #: Kept here because the run already computed it and the alternative is
    #: recomputing every calculator to ask a follow-up question.
    #: `chem/comparison.py` is the consumer. Typed loosely to keep `domain`
    #: free of a `scientific_result` import it otherwise does not need.
    per_atom: dict[tuple[str, str], object] = field(default_factory=dict)

    def add_row(self, molecule_uuid: str, label: str) -> None:
        if molecule_uuid not in self.row_labels:
            self.row_uuids.append(molecule_uuid)
        self.row_labels[molecule_uuid] = label

    def add_column(self, column: BatchColumn) -> None:
        """First definition of a `column_id` wins.

        Two molecules can produce the same column with slightly different
        metadata (a calculator that reports units only when it has a
        value), and re-defining it mid-run would reorder the table under
        the user while it is being filled.
        """
        if any(existing.column_id == column.column_id for existing in self.columns):
            return
        self.columns.append(column)

    def set_cell(self, molecule_uuid: str, column_id: str, cell: BatchCell) -> None:
        self.cells[(molecule_uuid, column_id)] = cell

    def cell(self, molecule_uuid: str, column_id: str) -> BatchCell | None:
        return self.cells.get((molecule_uuid, column_id))

    def column(self, column_id: str) -> BatchColumn | None:
        for column in self.columns:
            if column.column_id == column_id:
                return column
        return None

    def set_per_atom(self, molecule_uuid: str, calculator_id: str, result: object) -> None:
        self.per_atom[(molecule_uuid, calculator_id)] = result

    def per_atom_for(self, molecule_uuid: str, calculator_id: str) -> object | None:
        return self.per_atom.get((molecule_uuid, calculator_id))

    def per_atom_calculators(self) -> list[str]:
        """Calculator ids with per-atom data for at least TWO molecules.

        One molecule cannot be compared against anything, and offering it
        produces an empty table -- the same reason `numeric_columns` demands
        two values rather than one.
        """
        counts: dict[str, int] = {}
        for _uuid, calculator_id in self.per_atom:
            counts[calculator_id] = counts.get(calculator_id, 0) + 1
        seen: list[str] = []
        for _uuid, calculator_id in self.per_atom:
            if counts[calculator_id] >= 2 and calculator_id not in seen:
                seen.append(calculator_id)
        return seen

    def numeric_columns(self) -> list[BatchColumn]:
        """Columns the analytics can consume -- declared numeric AND with
        at least two real values present.

        The second half matters: a column can be declared numeric and be
        entirely empty because every molecule failed it (a 3D descriptor
        across a project with no conformers). Offering it produces an
        empty scatter and a correlation of nan, which reads as a broken
        tool rather than as missing data.
        """
        return [
            column
            for column in self.columns
            if column.numeric and len(self.values(column.column_id)) >= 2
        ]

    def values(self, column_id: str) -> list[float]:
        """Present numeric values in this column, rows with none skipped."""
        found = []
        for molecule_uuid in self.row_uuids:
            cell = self.cells.get((molecule_uuid, column_id))
            if cell is not None and cell.value is not None:
                found.append(cell.value)
        return found

    def paired_values(self, x_column_id: str, y_column_id: str) -> tuple[list[float], list[float], list[str]]:
        """The rows where BOTH columns have a value, and which rows those are.

        Pairwise-complete rather than dropping any row with a gap anywhere:
        a correlation between two columns has no reason to lose rows
        because a third, unrelated column failed.
        """
        xs: list[float] = []
        ys: list[float] = []
        uuids: list[str] = []
        for molecule_uuid in self.row_uuids:
            x_cell = self.cells.get((molecule_uuid, x_column_id))
            y_cell = self.cells.get((molecule_uuid, y_column_id))
            if x_cell is None or y_cell is None:
                continue
            if x_cell.value is None or y_cell.value is None:
                continue
            xs.append(x_cell.value)
            ys.append(y_cell.value)
            uuids.append(molecule_uuid)
        return xs, ys, uuids

    def matrix(self, column_ids: list[str]) -> tuple[list[list[float]], list[str]]:
        """A complete-case matrix over `column_ids`, and its row uuids.

        Listwise deletion here, unlike `paired_values` above, because PCA
        and clustering need every row to be the same length -- a row with a
        gap cannot be projected. The dropped rows are recoverable by the
        caller (compare the returned uuids against `row_uuids`) so a panel
        can say how many were excluded instead of quietly analysing fewer
        molecules than the user selected.
        """
        rows: list[list[float]] = []
        uuids: list[str] = []
        for molecule_uuid in self.row_uuids:
            values = []
            for column_id in column_ids:
                cell = self.cells.get((molecule_uuid, column_id))
                if cell is None or cell.value is None:
                    break
                values.append(cell.value)
            else:
                rows.append(values)
                uuids.append(molecule_uuid)
        return rows, uuids


@dataclass(frozen=True, kw_only=True)
class BatchRequest:
    """What to compute, over which molecules.

    Descriptors and calculators are named separately because they run
    through genuinely different paths -- a `DescriptorProvider` computes
    its whole set in one call and returns scalars, while a registered
    calculator is invoked one at a time with parameters and returns a
    `ScientificResult`. Merging them into one list would mean re-deriving
    which is which on every use.
    """

    molecule_uuids: list[str] = field(default_factory=list)
    descriptor_ids: list[str] = field(default_factory=list)
    calculator_ids: list[str] = field(default_factory=list)
    #: calculator_id -> the parameters that calculator's settings dialog
    #: produced. A calculator absent from this mapping runs on its
    #: registered defaults.
    parameters: dict[str, dict] = field(default_factory=dict)
    #: How a per-atom dataset collapses to one number per molecule. There
    #: is no universally correct choice (a summed LogP contribution IS the
    #: molecule's LogP; a summed partial charge is its formal charge; a
    #: summed accessible surface area is its total SASA -- but a MEAN of
    #: any of them is also a real quantity), so it is the user's call and
    #: the column label says which was taken.
    per_atom_aggregate: str = "mean"
