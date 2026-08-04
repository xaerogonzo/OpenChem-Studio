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
        rows: list[list[str]] = []
        while index < len(lines):
            row = lines[index]
            if not row.strip() or row.startswith(("#", "_", "loop_", "data_")):
                break
            tokens = _cif_tokens(row)
            if len(tokens) == len(names):
                rows.append(tokens)
            index += 1
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
