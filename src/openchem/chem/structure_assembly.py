"""The biological assembly a depositor annotated, read from the file.

WHAT THIS IS FOR. A deposited file holds the ASYMMETRIC UNIT, which is a
crystallographic convenience, not a biological claim. The depositor
separately annotates which chains and which transformations produce the
functional molecule. The two differ often enough to matter: measured
across the 49 curated receptors, 9 disagree, in both directions.

    file holds MORE than the biological unit   6 entries
        e.g. 4DAJ, muscarinic M3 -- 4 chains in the file, and the
        annotated assembly is a MONOMER. The extra chains are lattice
        neighbours, and docking the file whole searches against protein
        that is not part of the target.

    file holds LESS                            1 entry
        4DKL, mu-opioid -- one chain in the file, annotated as a DIMER.
        The partner exists only once the deposited operator is applied.

THIS ANNOTATES, IT DOES NOT BUILD. No coordinates are generated and no
transformation is applied. Naming which chains belong turns the chain
exclusion in the Docking panel from guesswork into something the
depositor already answered, which is the whole value here; generating the
missing partner is a separate step that would create atoms Vina has to
see and the interaction analysis has to agree about, and it is not done
here for exactly that reason.

Read a caveat with the "less" case before acting on it: a missing partner
invalidates docking only when the site is AT the interface. Mu-opioid's
orthosteric pocket sits inside the monomer, so 4DKL docks fine as
deposited -- the annotation is information, not an error to fix.

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


def _transforms_from_pdb(text: str) -> dict[str, Transform]:
    """`REMARK 350 BIOMT1/2/3` as `{id: Transform}`.

    Three lines make one operator and all three are required: a matrix
    missing a row is a broken record, not a two-dimensional rotation.
    """
    rows: dict[str, dict[int, list[float]]] = {}
    for line in text.splitlines():
        if not line.startswith("REMARK 350   BIOMT"):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        which = parts[2][-1]
        operator_id = parts[3]
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


def operator_transforms(structure_text: str, source_format: str) -> dict[str, Transform]:
    """Every transformation the file declares, by operator id."""
    if source_format in ("mmcif", "cif"):
        return _transforms_from_mmcif(structure_text)
    return _transforms_from_pdb(structure_text)


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
    docstring. The `BIOMT1` lines are counted rather than parsed: how many
    transformations there are is the question this answers, and their
    contents would only matter to a builder, which this is not.
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
