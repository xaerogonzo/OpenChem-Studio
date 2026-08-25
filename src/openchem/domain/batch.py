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


#: What KIND of thing a cell holds. A closed vocabulary, in the shape
#: `applies_to` and `CALCULATION_INPUTS` already use, because the
#: distinction it draws was previously carried by rendering and would
#: otherwise drift back into one.
#:
#: **THE EM DASH USED TO MEAN BOTH.** A failed calculation and a real
#: result with no scalar form -- a per-atom dataset, a spectrum, a
#: structure set, a 3D view -- rendered identically, and they are opposite
#: statements: one says nothing was computed, the other says something was
#: and a table is the wrong shape for it. `reduce_result` refuses 25 of the
#: real registry's result lines outright, so this is the common case rather
#: than an edge one.
SCALAR = "scalar"
NON_SCALAR = "non_scalar"
FAILED = "failed"
CELL_KINDS = frozenset({SCALAR, NON_SCALAR, FAILED})


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
    #: One of `CELL_KINDS`. Defaults to SCALAR so every existing producer
    #: keeps its meaning; a producer that has something a table cannot hold
    #: says NON_SCALAR and the view offers the row action instead of
    #: printing a dash that reads as a failure.
    kind: str = SCALAR

    @property
    def failed(self) -> bool:
        return self.cache_state is CacheState.FAILED

    @property
    def non_scalar(self) -> bool:
        """A real result with no scalar form. NOT a failure.

        Asked separately from `failed` on purpose: a view that tests only
        `failed` renders this as an em dash and tells the reader nothing
        was computed, which is the opposite of what happened.
        """
        return self.kind == NON_SCALAR and not self.failed


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


# --- the canonical store, and why the table is not it -------------------------


@dataclass(frozen=True, kw_only=True)
class ResultKey:
    """Which result this is -- everything that changes the answer.

    **NONE OF THESE FOUR IS INVENTED HERE.** Retaining a result rather than
    reducing it and dropping it makes "which result am I looking at" a real
    question, and getting it wrong trades a lossy system for a stale one --
    so every component is a contract this project already has:

    `molecule_uuid` is the application's SEMANTIC identity, not an object
    identity: `MoleculeModel.uuid` is a uuid4 carried through `to_dict()`
    into the project file, so it survives save, reload and import.
    `ResultCache`'s docstring warns against keying on it ALONE -- precisely
    because it is stable across structure edits -- which is what
    `structure_version` is here for.

    `structure_version` is `StructureCheckService.current_version()`, the
    counter `StructureReport.structure_version` is already built on and the
    Atom Inspector's report cache is already keyed on. Its reason applies
    unchanged: a result cannot outlive the structure it describes.

    `parameters_key` is `services.result_cache.key_for`'s output, computed
    by the CALLER rather than here -- `domain/` holds no services import,
    and one key recipe is the whole point. That function is already
    sorted-JSON-into-SHA-256, already stable across processes and sessions
    (it rules out `hash()` for PYTHONHASHSEED reasons), and already
    stringifies values rather than trusting them to serialise. A second
    parameter-serialisation scheme is how two identical requests become two
    different keys.
    """

    molecule_uuid: str
    calculator_id: str
    parameters_key: str = ""
    structure_version: int = 0


@dataclass
class BatchResultStore:
    """Every computed `ScientificResult`, keyed by what produced it.

    **THIS IS THE CANONICAL FORM AND `BatchTable` IS A PROJECTION OF IT.**
    The direction matters: a `BatchTable` is rows by columns, and the thing
    being stored is keyed by `(molecule, calculator, parameters, version)`,
    which is not a table and does not become one because a table can be
    built from it. If the store were the table, `reduce_result` would be
    back in the storage position by another route -- which is the exact
    loss this exists to end. Measured when it was written:
    `chem/result_reduction.py` recovers 73 numeric columns from the real
    registry and REFUSES 25 lines outright.

    Retaining costs little at the sizes this app offers. Measured over 8
    drug-like molecules against all 53 registry-executable calculators:
    424 results, **9.05 KiB mean, 37.1 KiB worst** (`regulatory_screen`,
    which is the same size for every molecule). Extrapolated at every
    calculator ticked: 5 molecules 2.3 MiB, 50 molecules 23 MiB, 200
    molecules 94 MiB, 1000 molecules 469 MiB.

    So there is NO eviction and no disk spill, deliberately -- nothing in
    the measurement asks for one at the sizes reached by opening a few
    molecules, which is all the lazy path ever accumulates. The bulk path
    is the one that could reach the top of that table, and it states its
    cost before it runs.

    `BatchTable.per_atom` predates this and is the same idea in its
    narrower form -- one result type, kept un-reduced for the comparison
    view. It is left where it is rather than migrated in the same change:
    it works, it is guarded, and `chem/comparison.py` and
    `BatchAnalysisDialog` both read it.
    """

    results: dict[ResultKey, object] = field(default_factory=dict)

    def put(self, key: ResultKey, result: object) -> None:
        self.results[key] = result

    def get(self, key: ResultKey) -> object | None:
        return self.results.get(key)

    def has(self, key: ResultKey) -> bool:
        return key in self.results

    def for_molecule(self, molecule_uuid: str, structure_version: int | None = None) -> dict[str, object]:
        """`{calculator_id: result}` for one molecule.

        `structure_version` filters to results that still describe the
        CURRENT structure. Passing None returns everything held for the
        molecule regardless of age, which is what a "show me what is
        stored" view wants and NOT what a detail pane wants.
        """
        found: dict[str, object] = {}
        for key, result in self.results.items():
            if key.molecule_uuid != molecule_uuid:
                continue
            if structure_version is not None and key.structure_version != structure_version:
                continue
            found[key.calculator_id] = result
        return found

    def stale_for(self, molecule_uuid: str, structure_version: int) -> list[ResultKey]:
        """Keys held for this molecule that describe an OLDER structure.

        Reported rather than deleted. A stale result is still a record of
        what was computed, and the panel says so rather than silently
        serving it or silently blanking it -- those are the two ways this
        would go wrong and they look identical from the outside.
        """
        return [
            key
            for key in self.results
            if key.molecule_uuid == molecule_uuid and key.structure_version != structure_version
        ]

    def merged_report(self, molecule_uuid: str, structure_version: int | None = None):
        """One molecule's retained facts, as a single report.

        **THIS IS WHAT MAKES BATCH RENDER LIKE PROPERTIES**, and it is a
        merge rather than a new renderer: `FactView` takes anything with
        `facts`, `by_category()` and `find()`, its docstring says so
        outright, and it is already the Properties panel's "Details..." for
        sixteen calculators. Building a second renderer for the same facts
        is the divergence this whole change exists to end.

        Only the results that ARE reports contribute. A spectrum, a
        structure set or a per-atom dataset has no facts to merge and is
        reached through its own inspector instead -- `non_scalar_results`
        below is what a view offers those from. Returns None when the
        molecule has no facts at all, which a caller must render as "not
        computed yet" rather than as an empty report.
        """
        from openchem.domain.report import ReportResult

        facts: list = []
        limitations: list[str] = []
        assumptions: list[str] = []
        for result in self.for_molecule(molecule_uuid, structure_version).values():
            got = getattr(result, "facts", None)
            if not got:
                continue
            facts.extend(got)
            limitations.extend(getattr(result, "limitations", ()) or ())
            assumptions.extend(getattr(result, "assumptions", ()) or ())
        if not facts:
            return None
        return ReportResult(
            report_id=f"batch:{molecule_uuid}",
            name="Batch results",
            molecule_uuid=molecule_uuid,
            structure_version=structure_version or 0,
            facts=tuple(facts),
            # De-duplicated in order: several calculators legitimately
            # carry the same caveat, and printing it five times buries the
            # four that differ.
            limitations=tuple(dict.fromkeys(limitations)),
            assumptions=tuple(dict.fromkeys(assumptions)),
        )

    def non_scalar_results(self, molecule_uuid: str, structure_version: int | None = None) -> dict[str, object]:
        """The retained results a report cannot show -- per-atom datasets,
        spectra, structure sets, pH curves.

        These are the ones with their own inspector, and the reason the
        detail view offers a row action rather than an em dash.
        """
        return {
            calculator_id: result
            for calculator_id, result in self.for_molecule(molecule_uuid, structure_version).items()
            if not getattr(result, "facts", None)
        }

    def calculators_for(self, molecule_uuid: str) -> set[str]:
        return {k.calculator_id for k in self.results if k.molecule_uuid == molecule_uuid}

    def __len__(self) -> int:
        return len(self.results)


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
    #: `StructureCheckService.current_version()` at the moment the run was
    #: requested. Part of every retained result's key, so editing a
    #: molecule makes its results STALE rather than wrong -- see
    #: `ResultKey`. Zero when no checker is wired, which is what a bare
    #: fixture has; the guard for staleness must move this or it is
    #: testing the cache rather than the invalidation.
    structure_version: int = 0
