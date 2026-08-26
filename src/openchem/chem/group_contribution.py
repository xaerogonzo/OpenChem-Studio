"""The mechanics two group-contribution methods share, and nothing more.

`chem/joback.py` and `chem/hansen.py` both decompose a structure into named
groups by matching SMARTS in priority order. This module holds the parts that
are MEASURABLY common -- the compile-time pattern validation, the
claim-and-skip walk, and the description of an atom no group covered.

**IT IS NOT A "GROUP CONTRIBUTION ENGINE", AND THE DIFFERENCE IS DELIBERATE.**
A general abstraction over "methods that decompose a molecule into groups"
would have been designed from two examples and would have had to swallow
their differences. Those differences are real:

    Joback    ONE pass. Every heavy atom must be covered exactly once, and
              the equations are bare group sums.
    Hansen    TWO passes with DIFFERENT rules. First-order groups partition
              the molecule as Joback's do; second-order groups deliberately
              OVERLAP them -- Stefanis & Panayiotou's principle (ii) requires
              a second-order group to "have adjacent first-order groups as
              building blocks" -- so the second pass must claim nothing.

Feeding the second pass through `claim_groups` would silently match almost
none of it, and the failure is the dangerous kind: a plausible number from a
molecule whose corrections were all skipped, every atom covered, no refusal
raised. So Hansen's second-order semantics stay explicit in `hansen.py`, and
this module lends it only the first pass.

That is this project's own lesson applied rather than quoted: reusing a
mechanism whose invariants do not apply is not reuse. `EditStructureCommand`
was reused for conformer adoption because pushing a molblock onto the undo
stack is exactly what it is for, and it was wrong three ways, each invisible
to the tests and visible in the running app.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem


@dataclass(frozen=True)
class GroupWalk:
    """What one claim-and-skip pass found.

    `uncovered` is atom INDICES rather than a count, so a caller can describe
    the first offender rather than only say how many there were.
    """

    counts: dict[str, int]
    uncovered: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return not self.uncovered


def build_patterns(
    spec: tuple[tuple[str, str, str], ...],
    known_groups: set[str],
    atom_counts: dict[str, int],
    method: str,
) -> tuple[tuple[str, Chem.Mol, str], ...]:
    """Compile a spec, validated on three counts, at import rather than in use.

    A typo in a group id fails where it is written instead of silently never
    matching; an unparseable SMARTS fails the same way; and a pattern whose
    atom count disagrees with the declared one fails rather than quietly
    claiming a neighbouring group's atom.

    **THE ATOM-COUNT INVARIANT IS THE LOAD-BEARING ONE**, and it travels with
    this walk rather than being left to each caller to remember. It caught
    three bugs in Joback, two of which produced WRONG ANSWERS rather than
    refusals: phenol lost its ipso carbon, and propyne got two groups for
    three carbons and came out 27 K low. A second fragmenter written without
    it is a second chance at the same three.

    The cure for a pattern that needs context it must not claim is a
    recursive `$()`, which matches without contributing an atom to the match.
    """
    #: A GROUP MAY HAVE SEVERAL PATTERNS, and a uniqueness check here is
    #: wrong. Joback gives `-NO2` two -- the hypervalent form and the
    #: charge-separated one -- because RDKit will hand you either depending on
    #: how the structure was drawn. Adding a "appears twice in the spec" guard
    #: during this extraction broke 54 tests immediately, which is the
    #: extraction's own regression net working: the shared walk must not be
    #: stricter than the code it was lifted from.
    compiled: list[tuple[str, Chem.Mol, str]] = []
    for group_id, smarts, why in spec:
        if group_id not in known_groups:
            raise ValueError(
                f"{method}: the spec names {group_id!r}, which is not in the "
                "shipped table"
            )
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            raise ValueError(
                f"{method}: {group_id!r} has an unparseable SMARTS: {smarts!r}"
            )
        expected = atom_counts.get(group_id, 1)
        if pattern.GetNumAtoms() != expected:
            raise ValueError(
                f"{method}: {group_id!r} is declared {expected} atom(s) but its "
                f"SMARTS {smarts!r} matches {pattern.GetNumAtoms()} -- it would "
                "claim an atom belonging to another group. Use a recursive $() "
                "for context that must not be claimed."
            )
        compiled.append((group_id, pattern, why))
    return tuple(compiled)


def claim_groups(
    mol: Chem.Mol, patterns: tuple[tuple[str, Chem.Mol, str], ...]
) -> GroupWalk:
    """Walk patterns in PRIORITY ORDER, claiming atoms as they match.

    A match touching an already-claimed atom is skipped, so the order of
    `patterns` is the method's own specificity ranking and not a detail. This
    is what makes first-order coverage a partition.

    **NEVER USE THIS FOR A CORRECTION PASS.** A group meant to overlap the
    ones already matched will be skipped by the very rule that makes this
    correct here -- see the module docstring.
    """
    claimed: set[int] = set()
    counts: dict[str, int] = {}
    for group_id, pattern, _why in patterns:
        for match in mol.GetSubstructMatches(pattern, uniquify=True):
            if claimed.intersection(match):
                continue
            claimed.update(match)
            counts[group_id] = counts.get(group_id, 0) + 1
    uncovered = tuple(
        atom.GetIdx() for atom in mol.GetAtoms() if atom.GetIdx() not in claimed
    )
    return GroupWalk(counts=counts, uncovered=uncovered)


def count_overlapping(
    mol: Chem.Mol, patterns: tuple[tuple[str, Chem.Mol, str], ...]
) -> dict[str, int]:
    """Count matches WITHOUT claiming, for a correction pass.

    The complement of `claim_groups`, and the reason Hansen needs a second
    entry point rather than a flag: its second-order groups are built FROM
    adjacent first-order groups, so every one of them overlaps atoms the
    first pass already claimed. Counting them under the claim rule yields
    almost nothing and raises no error.
    """
    counts: dict[str, int] = {}
    for group_id, pattern, _why in patterns:
        found = len(mol.GetSubstructMatches(pattern, uniquify=True))
        if found:
            counts[group_id] = found
    return counts


def describe_uncovered(mol: Chem.Mol, uncovered: tuple[int, ...]) -> str:
    """Name the first atom no group covered, in terms a chemist can act on.

    An index alone sends a reader counting atoms in a SMILES; the element,
    its hydrogens, its connections and whether it is in a ring are what
    identify which group is missing from the spec.
    """
    if not uncovered:
        return ""
    first = mol.GetAtomWithIdx(uncovered[0])
    detail = (
        f"{first.GetSymbol()} at index {first.GetIdx()} "
        f"({first.GetTotalNumHs()} H, {first.GetDegree()} connections, "
        f"{'in a ring' if first.IsInRing() else 'not in a ring'})"
    )
    if len(uncovered) > 1:
        detail += f", and {len(uncovered) - 1} more"
    return detail
