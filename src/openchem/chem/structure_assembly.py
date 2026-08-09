"""The biological assembly a depositor annotated, read from the file.

WHAT THIS IS FOR. A deposited file holds the ASYMMETRIC UNIT, which is a
crystallographic convenience, not a biological claim. The depositor
separately annotates which chains and which transformations produce the
functional molecule. The two differ often enough to matter: re-derived
over the 48 PDB deposits in the bundled catalogue, comparing each file's
chains against its PRIMARY assembly, **11 disagree, in both directions**.

    file holds MORE than the biological unit   8 entries
        1ERE 2VT4 3PBL 4DAJ 6A93 6B73 6WGT 7M93. 4DAJ, muscarinic M3,
        is the clearest: 4 chains in the file and a MONOMER annotated.
        The extras are lattice neighbours, and docking the file whole
        searches against protein that is not part of the target.

    file holds LESS                            3 entries
        4DKL 4EA3 5I6X. 4DKL, mu-opioid, is one chain in the file
        annotated as a DIMER; its partner exists only once the deposited
        operator is applied.

(An earlier version of this said "9 ... 6 and 1". That counted operators
across EVERY biomolecule in a file rather than the primary assembly's, so
it credited entries whose alternative assemblies need copies their
primary does not. The primary is the one docking uses.)

THIS ANNOTATES **AND NOW ALSO BUILDS.** `build_assembly` applies the
transformations and returns structure text; `parse_assembly` and the
`AssemblyAnnotation` half remain exactly what they were, for callers that
only want to know what the depositor said.

Read a caveat with the "less" case before acting on it: a missing partner
invalidates docking only when the site is AT the interface. Mu-opioid's
orthosteric pocket sits inside the monomer, so 4DKL docks correctly as
deposited -- which is precisely why it is the CONTROL for the builder
(building must not move a result that should not move) rather than a
demonstration of it.

VERIFIED AGAINST RCSB, not only against itself. `benchmarks/assembly/`
compares what this builds from `REMARK 350` against the assemblies RCSB
generates from the mmCIF `_pdbx_struct_oper_list` -- an independent
reading of the same annotation. 4DKL, 4EA3 and 5I6X agree on every atom
to the written digit; 1A34 is refused at 208,440 atoms and RCSB's file
confirms that count exactly. 2OMF's 115 differing atoms are the deposit's
own precision, not a defect: `-0.866025` here against `-0.8660254038`
there, which only reaches the third decimal at a rounding boundary.

**A transposed matrix is invisible to almost everything.** Every operator
in the bundled 49-receptor catalogue is axis-aligned, so transposing one
changes nothing; measured through the gate, a transposed builder still
matches 4DKL, 4EA3 and 5I6X byte for byte and is caught only by 2OMF's
3-fold, by 118.5 A. Any future corpus, fixture or spot-check that means
to exercise a rotation needs a DENSE one -- `tests/test_assembly_gate.py`
enforces that on the gate's corpus and checks the claim against the real
matrix rather than a flag.

ID SPACES. mmCIF assembly records reference `label_asym_id`, and PDB
`REMARK 350` references author chain ids. Those are different id spaces --
4DAJ has 18 label ids and 4 author ids for the same atoms. Confirmed live
that Open Babel hands `structure_summary` the LABEL ids from mmCIF and
the author ids from PDB, so each format is internally consistent and the
chain names here line up with the chain names there PROVIDED both come
from the same text. Parsing an assembly from one format and chains from
the other would silently name different chains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from openchem.chem.pose_analysis import _cif_tokens

#: The assembly a depositor designates as the biological one. RCSB orders
#: them so that "1" is the author- and/or software-determined primary
#: assembly; the rest are alternatives and sub-assemblies.
PRIMARY_ASSEMBLY_ID = "1"


@dataclass(frozen=True)
class BiologicalAssembly:
    """One annotated assembly.

    `operator_applications` is how many (chain-group x transformation)
    placements the annotation specifies -- that is, how many positioned
    copies the assembly is built from. 1 means the listed chains are used
    exactly as they sit in the file; more means at least one copy has to
    be generated or moved, and `chain_ids` then under-describes the real
    oligomer.

    Defined that way rather than as "number of distinct operators"
    because the two formats count differently and the aggregate has to
    mean one thing. 4EA3 is the case that forced it: its assembly 1
    applies the identity to chain A and a translation to chain B, written
    as two `_pdbx_struct_assembly_gen` rows in mmCIF and as two
    `APPLY THE FOLLOWING TO CHAINS` blocks in PDB. Counting per row and
    taking the maximum reported 1 from mmCIF and 2 from PDB for the same
    deposit; summing the applications reports 2 from both.
    """

    assembly_id: str
    chain_ids: tuple[str, ...]
    operator_applications: int
    oligomeric_details: str = ""

    @property
    def needs_generated_copies(self) -> bool:
        return self.operator_applications > 1


@dataclass(frozen=True)
class AssemblyAnnotation:
    """Every assembly a file declares, plus the chains it actually holds."""

    assemblies: tuple[BiologicalAssembly, ...] = field(default_factory=tuple)

    @property
    def primary(self) -> BiologicalAssembly | None:
        for assembly in self.assemblies:
            if assembly.assembly_id == PRIMARY_ASSEMBLY_ID:
                return assembly
        return self.assemblies[0] if self.assemblies else None

    def extra_chains(self, present: list[str]) -> tuple[str, ...]:
        """Chains in the FILE that the primary assembly does not use.

        These are the ones worth excluding before docking -- lattice
        neighbours and crystallisation extras. Returns nothing when there
        is no annotation, rather than guessing that everything unlisted is
        surplus.
        """
        primary = self.primary
        if primary is None or not primary.chain_ids:
            return ()
        listed = set(primary.chain_ids)
        return tuple(c for c in present if c not in listed)


def _read_text_field(lines: list[str], index: int) -> tuple[str, int]:
    """Read a `;`-delimited multi-line value starting at `lines[index]`.

    Returns the value with newlines removed, plus the index after the
    closing delimiter. Newlines go because every value read through here
    is a list (`asym_id_list`), and a chain list wrapped across lines is
    one list, not two.
    """
    collected = [lines[index][1:]]
    index += 1
    while index < len(lines) and not lines[index].startswith(";"):
        collected.append(lines[index])
        index += 1
    return "".join(part.strip() for part in collected), index + 1


def _loop_rows(text: str, prefix: str) -> tuple[list[str], list[list[str]]]:
    """Column names and rows of the mmCIF category whose tags start `prefix`.

    Both CIF forms appear in real assembly records and they are told apart
    by the `loop_` keyword, which CIF requires before a looped category.
    Guessing from the tag line instead does not work: in the single-row
    form a tag can carry NO inline value and take a `;`-delimited block on
    the following lines, which looks exactly like a bare loop header.

    4PE5 is that case, and it is the reason this is written carefully --
    its `asym_id_list` is 108 chains wrapped in a text field, and reading
    it as a loop header produced no assembly at all while RCSB reported a
    tetramer. It is the same multi-line text field that had to be WRITTEN
    correctly in `chem/binarycif.py`; here it has to be read.
    """
    lines = text.splitlines()
    names: list[str] = []
    values: list[str] = []

    index = 0
    while index < len(lines) and not lines[index].startswith(prefix):
        index += 1
    if index >= len(lines):
        return [], []

    previous = next(
        (lines[i].strip() for i in range(index - 1, -1, -1) if lines[i].strip()), ""
    )
    if previous == "loop_":
        while index < len(lines) and lines[index].startswith(prefix):
            names.append(lines[index].strip().split(".", 1)[1])
            index += 1
        # **A LOOP BODY IS A TOKEN STREAM, NOT ONE ROW PER LINE**, and
        # reading it line by line silently drops every wrapped row.
        #
        # This required `len(tokens) == len(names)` on a single physical
        # line. 1A34 writes each of its 60 `_pdbx_struct_oper_list` rows
        # as 16 values across TWO lines, so every row failed that test and
        # the category came back EMPTY -- no operators at all for a
        # 60-operator entry, with nothing to say so. It is the same silent
        # shape as the 4PE5 case this function's docstring already
        # records, and it went unnoticed because nothing consumed the
        # matrices until now.
        #
        # Chunking a flat token stream by the column count is also what a
        # real CIF reader does, so this is less special-casing than the
        # line-based version was, not more.
        rows: list[list[str]] = []
        pending: list[str] = []
        while index < len(lines):
            row = lines[index]
            if not row.strip() or row.startswith(("#", "_", "loop_", "data_")):
                break
            if row.startswith(";"):
                # A `;` block is ONE value however many lines it spans.
                value, index = _read_text_field(lines, index)
                pending.append(value)
            else:
                pending.extend(_cif_tokens(row))
                index += 1
            while len(pending) >= len(names):
                rows.append(pending[: len(names)])
                pending = pending[len(names) :]
        return names, rows

    while index < len(lines):
        line = lines[index]
        if line.startswith(prefix):
            tokens = _cif_tokens(line)
            names.append(tokens[0].split(".", 1)[1])
            if len(tokens) > 1:
                values.append(" ".join(tokens[1:]))
                index += 1
            else:
                # The value is a `;` block on the following lines.
                index += 1
                while index < len(lines) and not lines[index].strip():
                    index += 1
                if index < len(lines) and lines[index].startswith(";"):
                    value, index = _read_text_field(lines, index)
                    values.append(value)
                else:
                    values.append("")
            continue
        if line.strip() and not line.startswith("#"):
            break
        index += 1

    return (names, [values]) if names else ([], [])


class AssemblyError(ValueError):
    """A deposit's assembly records cannot be turned into transformations.

    Carries a message naming what is wrong and where -- "assembly 2
    references operator 17, absent from _pdbx_struct_oper_list" rather
    than "invalid assembly" -- because the caller shows it to somebody who
    has to decide what to do about a file they did not write.
    """


#: How far from orthogonal a matrix may sit and still count as a rotation.
#:
#: DERIVED FROM WHAT DEPOSITS ACTUALLY WRITE, not chosen. Coordinates and
#: matrices are serialised at fixed precision -- PDB `REMARK 350` writes 6
#: decimals, mmCIF's `_pdbx_struct_oper_list` 8 to 10 -- so a genuine
#: rotation read back from text is orthogonal only to about that.
#: Measured over 277 operators, every one in the 48 cached PDB deposits
#: plus five mmCIF entries including 1A34's 62:
#:
#:     operators validated              277, all "rotation"
#:     worst |RtR - I|                  1.64e-08
#:
#: The axis-aligned majority are EXACT (their entries are only 0 and
#: +/-1), so that bound comes entirely from the general rotations --
#: which is also why a corpus of axis-aligned operators cannot calibrate
#: this. 1e-4 leaves a factor of 6100 over the worst real case while
#: still refusing a matrix that is not a rotation at all.
#: `test_the_rigid_body_tolerance_clears_every_real_operator` recomputes
#: it from the corpus, so tightening this fails naming what it breaks.
_RIGID_TOLERANCE = 1e-4


@dataclass(frozen=True)
class Transform:
    """One rigid-body placement: rotate, then translate.

    `operator_id` is a STRING and not an int. Real deposits use `P` and
    `X0` alongside `1`..`60` (1A34 does both), so only a RANGE inside an
    expression is numeric -- an id is a label.
    """

    operator_id: str
    matrix: tuple[tuple[float, float, float], ...]
    vector: tuple[float, float, float]

    def apply(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        m, v = self.matrix, self.vector
        return (
            m[0][0] * x + m[0][1] * y + m[0][2] * z + v[0],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + v[1],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + v[2],
        )

    @property
    def is_identity(self) -> bool:
        return all(
            abs(self.matrix[i][j] - (1.0 if i == j else 0.0)) <= _RIGID_TOLERANCE
            for i in range(3)
            for j in range(3)
        ) and all(abs(component) <= _RIGID_TOLERANCE for component in self.vector)

    @property
    def determinant(self) -> float:
        m = self.matrix
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    @property
    def orthogonality_error(self) -> float:
        """max |(RtR - I)| -- zero for a true rotation."""
        worst = 0.0
        m = self.matrix
        for i in range(3):
            for j in range(3):
                dot = sum(m[k][i] * m[k][j] for k in range(3))
                worst = max(worst, abs(dot - (1.0 if i == j else 0.0)))
        return worst

    def validate(self) -> str:
        """`"rotation"`, `"reflection"`, or raise for anything else.

        **NO REFLECTION HAS EVER BEEN SEEN HERE, and this branch is
        therefore untested against real data.** Measured across 52
        operators in 48 cached deposits and 1A34's 62: every determinant
        is +1. It is detected and reported rather than refused because
        absence in one corpus is not proof the format forbids it, and
        refusing an operator a depositor wrote would be the more damaging
        of the two mistakes.
        """
        if self.orthogonality_error > _RIGID_TOLERANCE:
            raise AssemblyError(
                f"Operator {self.operator_id} is not a rigid-body transformation: "
                f"its rotation is non-orthogonal by {self.orthogonality_error:.2e}, "
                f"over the {_RIGID_TOLERANCE:.0e} tolerance."
            )
        determinant = self.determinant
        if abs(determinant - 1.0) <= _RIGID_TOLERANCE:
            return "rotation"
        if abs(determinant + 1.0) <= _RIGID_TOLERANCE:
            return "reflection"
        raise AssemblyError(
            f"Operator {self.operator_id} has determinant {determinant:.6f}, "
            f"which is neither +1 (rotation) nor -1 (reflection); it scales or "
            f"shears the structure."
        )


def compose(outer: Transform, inner: Transform) -> Transform:
    """`outer` applied AFTER `inner` -- the right-hand group goes first.

    **THE ORDER IS THE WHOLE POINT.** mmCIF writes a product expression
    `(1,2)(3,4)` meaning the RIGHT group is applied first, and the count
    this module already reported is order-independent while a built
    structure is not. Composing the wrong way round produces a perfectly
    plausible assembly in the wrong place.

    p -> outer(inner(p)) = (Ro.Ri) p + (Ro.vi + vo)
    """
    ro, ri = outer.matrix, inner.matrix
    matrix = tuple(
        tuple(sum(ro[i][k] * ri[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )
    vector = tuple(
        sum(ro[i][k] * inner.vector[k] for k in range(3)) + outer.vector[i] for i in range(3)
    )
    return Transform(
        operator_id=f"{outer.operator_id}x{inner.operator_id}",
        matrix=matrix,  # type: ignore[arg-type]
        vector=vector,  # type: ignore[arg-type]
    )


def _count_operators(expression: str) -> int:
    """How many transformations an `oper_expression` denotes.

    The grammar allows `1`, a list `1,2,3`, a range `1-60`, and products
    of parenthesised groups such as `(1-60)(61-88)`. A range is what an
    icosahedral capsid looks like, and reading `1-60` as a single operator
    would report a 60-mer as a monomer.
    """
    expression = expression.strip()
    if not expression or expression in (".", "?"):
        return 1

    groups = re.findall(r"\(([^)]*)\)", expression) or [expression]
    total = 1
    for group in groups:
        count = 0
        for part in group.split(","):
            part = part.strip()
            if not part:
                continue
            span = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
            if span:
                count += int(span.group(2)) - int(span.group(1)) + 1
            else:
                count += 1
        total *= max(count, 1)
    return max(total, 1)


def _expand_group(group: str) -> list[str]:
    """One comma-separated group to its operator ids, in written order.

    Only a RANGE is numeric. `X0` and `P` are ids a real deposit uses
    (1A34 writes both), so anything that is not `n-m` is taken whole.
    """
    ids: list[str] = []
    for part in group.split(","):
        part = part.strip()
        if not part:
            continue
        span = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if span:
            ids.extend(str(n) for n in range(int(span.group(1)), int(span.group(2)) + 1))
        else:
            ids.append(part)
    return ids


def expand_expression(expression: str) -> list[tuple[str, ...]]:
    """An `oper_expression` as ordered tuples of operator ids to compose.

    Each tuple is written left-to-right and **applied right-to-left**, so
    `("X0", "5")` means operator 5 first, then X0. A single group yields
    one-element tuples.

    `len(expand_expression(e)) == _count_operators(e)` by construction --
    the count this module already published is the size of this list, and
    `test_the_enumerator_and_the_shipped_count_agree` holds the two
    together so the published `operator_applications` cannot drift.
    """
    expression = expression.strip()
    if not expression or expression in (".", "?"):
        return [()]
    groups = re.findall(r"\(([^)]*)\)", expression) or [expression]
    combinations: list[tuple[str, ...]] = [()]
    for group in groups:
        ids = _expand_group(group)
        if not ids:
            continue
        combinations = [existing + (single,) for existing in combinations for single in ids]
    return combinations or [()]


def _transforms_from_mmcif(text: str) -> dict[str, Transform]:
    """`_pdbx_struct_oper_list` as `{id: Transform}`.

    The tags INTERLEAVE matrix and translation -- `matrix[1][1..3]` then
    `vector[1]`, then row 2, then row 3 -- so reading nine values followed
    by three silently puts the translation in the wrong place. They are
    addressed by name here for that reason.
    """
    names, rows = _loop_rows(text, "_pdbx_struct_oper_list.")
    if not names:
        return {}
    transforms: dict[str, Transform] = {}
    for row in rows:
        cell = dict(zip(names, row))
        operator_id = cell.get("id", "").strip()
        if not operator_id:
            continue
        try:
            matrix = tuple(
                tuple(float(cell[f"matrix[{i}][{j}]"]) for j in (1, 2, 3)) for i in (1, 2, 3)
            )
            vector = tuple(float(cell[f"vector[{i}]"]) for i in (1, 2, 3))
        except (KeyError, ValueError) as exc:
            raise AssemblyError(
                f"Operator {operator_id} has an unreadable transformation matrix in "
                f"_pdbx_struct_oper_list ({exc})."
            ) from exc
        transforms[operator_id] = Transform(operator_id, matrix, vector)  # type: ignore[arg-type]
    return transforms


def _transforms_from_pdb(text: str, assembly_id: str | None = None) -> dict[str, Transform]:
    """`REMARK 350 BIOMT1/2/3` as `{id: Transform}`.

    **PDB OPERATOR IDS ARE SCOPED PER BIOMOLECULE, and reading them
    globally silently builds the wrong structure.** Each `BIOMOLECULE:`
    block restarts its numbering, so the same id means different things in
    different blocks. 4EA3, in the bundled catalogue, is the case:

        BIOMOLECULE 1, operator 2   translation x = +14.85678
        BIOMOLECULE 2, operator 2   translation x = -27.24922

    A global map keeps whichever came last, so building assembly 1 placed
    its second chain 42 A from where the depositor put it -- a plausible
    dimer, in the wrong place, with nothing to say so. `assembly_id`
    restricts the read to one block; `None` keeps the FIRST definition of
    each id and is for inspection only, never for building.

    Three lines make one operator and all three are required: a matrix
    missing a row is a broken record, not a two-dimensional rotation.
    """
    rows: dict[str, dict[int, list[float]]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("REMARK 350"):
            body = line[10:].strip()
            if body.startswith("BIOMOLECULE:"):
                current = body.split(":", 1)[1].strip()
        if not line.startswith("REMARK 350   BIOMT"):
            continue
        if assembly_id is not None and current != assembly_id:
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        which = parts[2][-1]
        operator_id = parts[3]
        if assembly_id is None and operator_id in rows and int(which) in rows[operator_id]:
            continue  # first definition wins; see the docstring
        try:
            rows.setdefault(operator_id, {})[int(which)] = [float(v) for v in parts[4:8]]
        except ValueError as exc:
            raise AssemblyError(
                f"Operator {operator_id} has an unreadable BIOMT{which} line in "
                f"REMARK 350 ({exc})."
            ) from exc

    transforms: dict[str, Transform] = {}
    for operator_id, collected in rows.items():
        missing = [i for i in (1, 2, 3) if i not in collected]
        if missing:
            raise AssemblyError(
                f"Operator {operator_id} is missing BIOMT row(s) "
                f"{', '.join(str(m) for m in missing)} in REMARK 350."
            )
        matrix = tuple(tuple(collected[i][:3]) for i in (1, 2, 3))
        vector = tuple(collected[i][3] for i in (1, 2, 3))
        transforms[operator_id] = Transform(operator_id, matrix, vector)  # type: ignore[arg-type]
    return transforms


def operator_transforms(
    structure_text: str, source_format: str, assembly_id: str | None = None
) -> dict[str, Transform]:
    """Every transformation available to one assembly, by operator id.

    `assembly_id` matters for PDB and not for mmCIF: `REMARK 350` restarts
    its operator numbering in every `BIOMOLECULE:` block, while
    `_pdbx_struct_oper_list` is one global list with unique ids that
    expressions reference. See `_transforms_from_pdb` for what reading PDB
    globally costs.
    """
    if source_format in ("mmcif", "cif"):
        return _transforms_from_mmcif(structure_text)
    return _transforms_from_pdb(structure_text, assembly_id)


def _from_mmcif(text: str) -> AssemblyAnnotation:
    gen_names, gen_rows = _loop_rows(text, "_pdbx_struct_assembly_gen.")
    if not gen_names:
        return AssemblyAnnotation()

    def column(names, row, key):
        return row[names.index(key)] if key in names and names.index(key) < len(row) else ""

    details_names, details_rows = _loop_rows(text, "_pdbx_struct_assembly.")
    details_by_id = {
        column(details_names, row, "id"): column(details_names, row, "oligomeric_details")
        for row in details_rows
    }

    # One assembly can span several gen rows -- 4DAJ writes five, each
    # naming a different chain group -- so they accumulate per assembly.
    chains: dict[str, list[str]] = {}
    operators: dict[str, int] = {}
    for row in gen_rows:
        assembly_id = column(gen_names, row, "assembly_id")
        if not assembly_id:
            continue
        listed = column(gen_names, row, "asym_id_list")
        for chain in listed.split(","):
            chain = chain.strip()
            if chain and chain not in chains.setdefault(assembly_id, []):
                chains[assembly_id].append(chain)
        # Summed, not maxed: each gen row is its own set of placements
        # applied to its own chain group, and the total is what the
        # PDB side counts too. See BiologicalAssembly's docstring.
        count = _count_operators(column(gen_names, row, "oper_expression"))
        operators[assembly_id] = operators.get(assembly_id, 0) + count

    return AssemblyAnnotation(
        assemblies=tuple(
            BiologicalAssembly(
                assembly_id=assembly_id,
                chain_ids=tuple(ids),
                operator_applications=max(operators.get(assembly_id, 1), 1),
                oligomeric_details=details_by_id.get(assembly_id, ""),
            )
            for assembly_id, ids in chains.items()
        )
    )


def _from_pdb(text: str) -> AssemblyAnnotation:
    """`REMARK 350`, the PDB-format equivalent.

    Chains are author ids here, not the mmCIF label ids -- see the module
    docstring. The `BIOMT1` lines are COUNTED here and parsed elsewhere:
    this function answers "how many transformations", which is all the
    annotation needs. `_transforms_from_pdb` reads their contents for the
    builder, and scopes them per biomolecule, which this does not have to.
    """
    assemblies: list[BiologicalAssembly] = []
    current_id = ""
    current_chains: list[str] = []
    biomt1 = 0

    def flush():
        if current_id:
            assemblies.append(
                BiologicalAssembly(
                    assembly_id=current_id,
                    chain_ids=tuple(current_chains),
                    operator_applications=max(biomt1, 1),
                )
            )

    for line in text.splitlines():
        if not line.startswith("REMARK 350"):
            continue
        body = line[10:].strip()
        if body.startswith("BIOMOLECULE:"):
            flush()
            current_id = body.split(":", 1)[1].strip()
            current_chains = []
            biomt1 = 0
        elif "CHAINS:" in body:
            for chain in body.split("CHAINS:", 1)[1].split(","):
                chain = chain.strip()
                if chain and chain not in current_chains:
                    current_chains.append(chain)
        elif body.startswith("BIOMT1"):
            biomt1 += 1
    flush()
    return AssemblyAnnotation(assemblies=tuple(assemblies))


@dataclass(frozen=True)
class AssemblyInstance:
    """One placed copy: a source chain under one composed operator.

    **THE IDENTITY IS `(source_chain, operator_id)`, NOT THE CHAIN NAME.**
    `generated_chain_id` is a serialisation detail — the name the copy
    happens to carry in the emitted text — and nothing may recover the
    relationship by parsing it back out. That distinction stops mattering
    only until an assembly applies sixty operators to one chain, which
    1A34 does.
    """

    source_chain: str
    operator_id: str
    generated_chain_id: str

    @property
    def is_original(self) -> bool:
        """True when this copy sits exactly where the deposit put it."""
        return self.source_chain == self.generated_chain_id


@dataclass(frozen=True)
class AssemblyBuildResult:
    """What a build produced, or why it produced nothing.

    A result rather than a bare string so **partial output is not
    representable**: a caller cannot accidentally dock half an assembly,
    because a failure carries no text at all.
    """

    ok: bool
    output_text: str = ""
    assembly_id: str = ""
    instances: tuple[AssemblyInstance, ...] = ()
    warnings: tuple[str, ...] = ()
    failure_reason: str = ""

    @property
    def generated_copies(self) -> int:
        """Copies that are not the deposited chains themselves."""
        return sum(1 for instance in self.instances if not instance.is_original)

    @property
    def changed_the_structure(self) -> bool:
        """Whether building actually produced something different.

        "I asked for the biological assembly" and "the biological
        assembly differed from what I had" are different facts, and a
        result has to be able to tell them apart six months later.
        """
        return self.generated_copies > 0


#: Chain ids available to generated copies, in order. PDB gives the field
#: ONE column, so this is the whole alphabet there is -- 62 names, and an
#: assembly needing a 63rd cannot be written as PDB at all.
_PDB_CHAIN_IDS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "abcdefghijklmnopqrstuvwxyz" "0123456789"
)

#: PDB's atom serial field is five columns.
_PDB_MAX_SERIAL = 99_999

#: Above this many atoms a built assembly is not something the rest of
#: the application can use: Vina will not dock it and the viewer will not
#: survive it. 1A34 is 60 operators over 3,474 atoms = 208,440, and 2BTV
#: reaches 2.9 million -- both real entries in the corpus, which is why
#: the guard exists rather than being hypothetical.
#:
#: Atom count is the first gate and deliberately not the only conceivable
#: one; residue count, chain count and preparation cost are the obvious
#: next terms if one turns out to bind first.
DEFAULT_ATOM_LIMIT = 100_000


def _generation_rows(text: str, source_format: str, assembly_id: str) -> list[tuple[list[str], str]]:
    """`[(chain ids, oper_expression)]` for one assembly, in written order.

    Separate from `parse_assembly`, which accumulates chains across rows
    to answer "which chains belong". A builder needs the PAIRING that
    accumulation throws away: 4DAJ writes five rows, each naming a
    different chain group with its own operators, and applying every
    operator to every chain would be a different structure.
    """
    rows: list[tuple[list[str], str]] = []
    if source_format in ("mmcif", "cif"):
        names, gen_rows = _loop_rows(text, "_pdbx_struct_assembly_gen.")
        for row in gen_rows:
            cell = dict(zip(names, row))
            if cell.get("assembly_id", "").strip() != assembly_id:
                continue
            chains = [c.strip() for c in cell.get("asym_id_list", "").split(",") if c.strip()]
            rows.append((chains, cell.get("oper_expression", "").strip()))
        return rows

    current_id, chains = "", []
    operators: list[str] = []
    for line in text.splitlines():
        if not line.startswith("REMARK 350"):
            continue
        body = line[10:].strip()
        if body.startswith("BIOMOLECULE:"):
            if current_id == assembly_id and chains:
                rows.append((chains, ",".join(operators)))
            current_id = body.split(":", 1)[1].strip()
            chains, operators = [], []
        elif "CHAINS:" in body:
            if operators and current_id == assembly_id and chains:
                # A second `APPLY THE FOLLOWING TO CHAINS` inside one
                # biomolecule starts a new group, exactly like an extra
                # mmCIF gen row. 4EA3 is the entry that does this.
                rows.append((chains, ",".join(operators)))
                chains, operators = [], []
            for chain in body.split("CHAINS:", 1)[1].split(","):
                chain = chain.strip()
                if chain and chain not in chains:
                    chains.append(chain)
        elif body.startswith("BIOMT1"):
            parts = body.split()
            if len(parts) > 1:
                operators.append(parts[1])
    if current_id == assembly_id and chains:
        rows.append((chains, ",".join(operators)))
    return rows


def parse_assembly(structure_text: str, source_format: str) -> AssemblyAnnotation:
    """Read the deposited assembly annotation, or an empty one.

    Absence is normal and is NOT an error: computed models, edited files
    and anything not from a structural database carry no annotation. The
    caller shows nothing rather than inventing a default, because
    "unlisted" would otherwise read as "surplus" and invite a user to
    delete chains on the strength of a record that was never there.
    """
    if source_format in ("mmcif", "cif"):
        return _from_mmcif(structure_text)
    return _from_pdb(structure_text)


#: Records dropped from a built assembly, and why each one.
#:
#: **ANISOU** carries an anisotropic displacement TENSOR, which under a
#: rotation R transforms as R.U.Rt. Carried through untouched it would
#: describe the wrong orientation for every generated copy -- a wrong
#: number rather than a missing one. It is refinement metadata neither
#: Vina nor the viewer reads, and it is 125,545 lines across the 25 corpus
#: deposits that carry it. Rotating it is the correct fix if anything ever
#: needs it.
#:
#: **MASTER** counts the records of the file it was written for. After
#: building, every one of its numbers is wrong.
#:
#: **REMARK 350** is the build instruction itself. A built assembly that
#: still carries it tells the next reader to build it AGAIN -- feed the
#: output back through `parse_assembly` and it reports a multiplicity the
#: structure already has. Re-entrancy, not tidiness.
_DROPPED_PDB_RECORDS = ("ANISOU", "MASTER", "REMARK 350")


def _build_pdb(
    text: str,
    assembly_id: str,
    rows: list[tuple[list[str], str]],
    transforms: dict[str, Transform],
    atom_limit: int,
) -> AssemblyBuildResult:
    lines = text.splitlines()
    if any(line.startswith("MODEL ") for line in lines):
        return AssemblyBuildResult(
            ok=False,
            failure_reason=(
                "This deposit holds several models (MODEL/ENDMDL) and the assembly "
                "annotation does not say which one to transform."
            ),
        )

    by_chain: dict[str, list[str]] = {}
    for line in lines:
        if line.startswith(("ATOM  ", "HETATM")):
            by_chain.setdefault(line[21], []).append(line)
    if not by_chain:
        return AssemblyBuildResult(ok=False, failure_reason="This file contains no atoms.")

    # Placements, deduplicated: the same (source chain, operator) is ONE
    # copy however many generation rows happen to name it.
    placements: list[tuple[str, tuple[str, ...]]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    warnings: list[str] = []
    for chains, expression in rows:
        for combination in expand_expression(expression):
            for chain in chains:
                key = (chain, combination)
                if key not in seen:
                    seen.add(key)
                    placements.append(key)
    if not placements:
        return AssemblyBuildResult(
            ok=False, failure_reason=f"Assembly {assembly_id} names no chains to place."
        )

    # Resolve and compose. Everything that can refuse does so HERE, before
    # a single line is written, so a failure leaves nothing half-built.
    composed: dict[tuple[str, ...], Transform] = {}
    for _chain, combination in placements:
        if combination in composed:
            continue
        resolved: Transform | None = None
        for operator_id in reversed(combination):  # the right-hand group goes first
            operator = transforms.get(operator_id)
            if operator is None:
                declared = ", ".join(sorted(transforms)) or "none"
                return AssemblyBuildResult(
                    ok=False,
                    failure_reason=(
                        f"Assembly {assembly_id} references operator {operator_id!r}, which "
                        f"is absent from this file's transformation list (it declares "
                        f"{declared})."
                    ),
                )
            try:
                kind = operator.validate()
            except AssemblyError as exc:
                return AssemblyBuildResult(ok=False, failure_reason=str(exc))
            if kind == "reflection":
                warnings.append(
                    f"Operator {operator_id} is a reflection (determinant -1). No deposit in "
                    f"the reference corpus contains one, so this path is untested against "
                    f"real data."
                )
            resolved = operator if resolved is None else compose(resolved, operator)
        if resolved is None:
            resolved = Transform("identity", ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), (0.0, 0.0, 0.0))
        composed[combination] = resolved

    missing = sorted({chain for chain, _ in placements if chain not in by_chain})
    if missing:
        held = ", ".join(sorted(by_chain))
        return AssemblyBuildResult(
            ok=False,
            failure_reason=(
                f"Assembly {assembly_id} names chain(s) {', '.join(missing)}, which this file "
                f"does not contain (it holds {held})."
            ),
        )

    total_atoms = sum(len(by_chain[chain]) for chain, _ in placements)
    if total_atoms > atom_limit:
        return AssemblyBuildResult(
            ok=False,
            failure_reason=(
                f"Assembly {assembly_id} would contain {total_atoms:,} atoms, over the "
                f"{atom_limit:,} limit for docking preparation."
            ),
        )
    if total_atoms > _PDB_MAX_SERIAL:
        return AssemblyBuildResult(
            ok=False,
            failure_reason=(
                f"Assembly {assembly_id} would contain {total_atoms:,} atoms, more than PDB's "
                f"{_PDB_MAX_SERIAL:,} atom serial limit can express. Use the mmCIF form."
            ),
        )

    # Chain names. **THE IDENTITY KEEPS THE DEPOSITED NAME**, so a saved
    # docking box, an excluded chain and every existing reference still
    # address exactly what they addressed before the build.
    # A source chain keeps its deposited name for ONE of its placements:
    # the identity if it has one, otherwise its first. Only the extra
    # copies need invented names. Renaming a chain that is placed just
    # once would break addressability for nothing -- 4EA3 places chain B
    # only under a translation, and calling that `C` would mean somebody
    # excluding "chain B" no longer finds it.
    assigned: dict[tuple[str, tuple[str, ...]], str] = {}
    keeps_name: dict[str, tuple[str, ...]] = {}
    for chain, combination in placements:
        if chain in keeps_name and not composed[combination].is_identity:
            continue
        if chain not in keeps_name or composed[combination].is_identity:
            keeps_name[chain] = combination
    for chain, combination in keeps_name.items():
        assigned[(chain, combination)] = chain
    spare = [c for c in _PDB_CHAIN_IDS if c not in set(by_chain)]
    for key in placements:
        if key in assigned:
            continue
        if not spare:
            return AssemblyBuildResult(
                ok=False,
                failure_reason=(
                    f"Assembly {assembly_id} needs more chain names than PDB's single column "
                    f"can express ({len(placements)} copies against {len(_PDB_CHAIN_IDS)} "
                    f"available names). Use the mmCIF form."
                ),
            )
        assigned[key] = spare.pop(0)

    # Header records survive verbatim apart from those dropped above.
    # CRYST1 STAYS: it is genuine crystallographic metadata, and
    # `pose_analysis.is_symmetry_generated` already removes the copies
    # Open Babel invents -- they carry no residue record, and these do.
    out: list[str] = [
        line
        for line in lines
        if not line.startswith(("ATOM  ", "HETATM", "TER   ", "CONECT", "END"))
        and not line.startswith(_DROPPED_PDB_RECORDS)
    ]

    serial = 0
    serial_map: dict[tuple[str, tuple[str, ...], str], int] = {}
    instances: list[AssemblyInstance] = []
    blank3 = " " * 3
    for chain, combination in placements:
        transform = composed[combination]
        new_chain = assigned[(chain, combination)]
        instances.append(
            AssemblyInstance(
                source_chain=chain,
                operator_id="x".join(combination) if combination else "identity",
                generated_chain_id=new_chain,
            )
        )
        for line in by_chain[chain]:
            serial += 1
            serial_map[(chain, combination, line[6:11].strip())] = serial
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            nx, ny, nz = transform.apply(x, y, z)
            out.append(
                f"{line[:6]}{serial:>5}{line[11:21]}{new_chain}{line[22:30]}"
                f"{nx:>8.3f}{ny:>8.3f}{nz:>8.3f}{line[54:]}"
            )
        serial += 1
        out.append(f"TER   {serial:>5}      {blank3} {new_chain}")

    # CONECT is REWRITTEN, not dropped: Open Babel perceives HETATM bonds
    # from it, so losing it would silently change the cofactors and
    # ligands in the receptor. 53 of 56 corpus deposits carry one.
    for line in lines:
        if not line.startswith("CONECT"):
            continue
        fields = [f for f in (line[i : i + 5].strip() for i in range(6, min(len(line), 31), 5)) if f]
        if not fields:
            continue
        for chain, combination in placements:
            mapped = [serial_map.get((chain, combination, field)) for field in fields]
            if all(m is not None for m in mapped):
                out.append("CONECT" + "".join(f"{m:>5}" for m in mapped))
    out.append("END")

    return AssemblyBuildResult(
        ok=True,
        output_text="\n".join(out) + "\n",
        assembly_id=assembly_id,
        instances=tuple(instances),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def build_assembly(
    structure_text: str,
    source_format: str,
    assembly_id: str = PRIMARY_ASSEMBLY_ID,
    atom_limit: int = DEFAULT_ATOM_LIMIT,
) -> AssemblyBuildResult:
    """The deposited biological assembly, as structure text.

    Emits the SAME format it was handed, because `source_format` travels
    with the text to Mol*, Open Babel and Vina alike.

    Fails whole or not at all -- see `AssemblyBuildResult`. Every refusal
    names what is wrong and where, because whoever reads it is looking at
    a file they did not write.
    """
    annotation = parse_assembly(structure_text, source_format)
    if not annotation.assemblies:
        return AssemblyBuildResult(
            ok=False, failure_reason="This file carries no biological assembly annotation."
        )
    if not any(a.assembly_id == assembly_id for a in annotation.assemblies):
        declared = ", ".join(a.assembly_id for a in annotation.assemblies)
        return AssemblyBuildResult(
            ok=False,
            failure_reason=(
                f"This file declares no assembly {assembly_id!r} (it declares {declared})."
            ),
        )

    rows = _generation_rows(structure_text, source_format, assembly_id)
    if not rows:
        return AssemblyBuildResult(
            ok=False,
            failure_reason=f"Assembly {assembly_id} carries no generation rows to build from.",
        )
    try:
        transforms = operator_transforms(structure_text, source_format, assembly_id)
    except AssemblyError as exc:
        return AssemblyBuildResult(ok=False, failure_reason=str(exc))

    if source_format in ("mmcif", "cif"):
        return AssemblyBuildResult(
            ok=False,
            failure_reason=(
                "Building from mmCIF is not implemented yet -- the PDB form of this "
                "deposit can be built."
            ),
        )
    return _build_pdb(structure_text, assembly_id, rows, transforms, atom_limit)
