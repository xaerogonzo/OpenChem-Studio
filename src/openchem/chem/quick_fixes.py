"""Repairs a `StructureIssue` can offer, and how safe each one is.

Every fix returns a NEW molblock and mutates nothing. The caller applies it
through `EditStructureCommand`, so `Ctrl+Z` brings back exactly what was
there -- a repair that cannot be undone is worse than the issue it fixed,
and this is the one place in the app that changes somebody's structure
without them drawing anything.

`FixSafety` is shown before the fix runs, not after. "Remove the explicit
hydrogens" and "throw away every fragment but the biggest" are both one
click, and only one of them can lose work.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class FixSafety(str, Enum):
    """What a fix can cost you.

    SAFE       -- the structure means the same thing afterwards.
    REVERSIBLE -- it changes the drawing, not the chemistry.
    LOSSY      -- atoms or bonds go away. Say so before running it.
    """

    SAFE = "safe"
    REVERSIBLE = "reversible"
    LOSSY = "lossy"


@dataclass(frozen=True, kw_only=True)
class QuickFix:
    fix_id: str
    label: str  # what the button says
    safety: FixSafety
    apply: Callable[[str], str]  # molblock -> molblock
    description: str = ""


class QuickFixRegistry:
    """`fix_id` -> a repair, resolved at display time.

    An issue carries a `fix_id` string rather than a callable because an
    issue is data: it travels through events, gets exported, and would not
    survive a bound method. A `fix_id` naming nothing registered simply
    means no button appears, which is what lets a plugin emit issues
    referring to fixes only it provides.
    """

    def __init__(self) -> None:
        self._fixes: dict[str, QuickFix] = {}

    def register(self, fix: QuickFix) -> None:
        self._fixes[fix.fix_id] = fix

    def get(self, fix_id: str) -> QuickFix | None:
        return self._fixes.get(fix_id) if fix_id else None

    def all(self) -> list[QuickFix]:
        return sorted(self._fixes.values(), key=lambda f: f.fix_id)


# --- the core fixes ---------------------------------------------------------


def _read(molblock: str):
    from rdkit import Chem

    mol = Chem.MolFromMolBlock(molblock, sanitize=False, removeHs=False)
    if mol is None:
        raise ValueError("this structure could not be read")
    mol.UpdatePropertyCache(strict=False)
    return mol


def _write(mol) -> str:
    from rdkit import Chem

    return Chem.MolToMolBlock(mol, kekulize=False)


def keep_largest_fragment(molblock: str) -> str:
    """Discard every fragment but the one with the most atoms.

    LOSSY, and the common case is a salt: dropping the counter-ion changes
    the compound's identity, its formula and its mass. Offered rather than
    applied automatically for exactly that reason.
    """
    from rdkit import Chem

    mol = _read(molblock)
    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    if len(fragments) < 2:
        return molblock
    largest = max(fragments, key=lambda f: f.GetNumAtoms())
    return _write(largest)


def remove_explicit_hydrogens(molblock: str) -> str:
    """Fold explicit hydrogens back into their heavy atoms' counts.

    SAFE: the molecule is unchanged, only how it is written. RDKit keeps
    hydrogens that carry information anyway -- isotopic labels, charges,
    ones that define stereo -- so this cannot silently drop a deuterium.
    """
    from rdkit import Chem

    mol = _read(molblock)
    return _write(Chem.RemoveHs(mol, sanitize=False))


def recompute_layout(molblock: str) -> str:
    """Throw away the coordinates and generate a fresh depiction.

    REVERSIBLE: this touches only where things are drawn. It is the fix for
    crossing bonds, stretched bonds and crowding, all of which are
    complaints about the drawing rather than the chemistry.
    """
    from rdkit.Chem import AllChem

    mol = _read(molblock)
    # No RemoveAllConformers() first: `Compute2DCoords` defaults to
    # clearConfs=True and replaces them itself. Measured on a hexane whose
    # atom 3 had been dragged 9 units away -- with and without the call,
    # the result is the same regenerated depiction. It was written, and
    # mutation testing found nothing could tell the two apart.
    AllChem.Compute2DCoords(mol)
    return _write(mol)


def merge_coincident_atoms(molblock: str) -> str:
    """Fuse unbonded atoms drawn on top of one another into one.

    LOSSY. Two atoms at one point are usually one atom drawn twice -- the
    classic result of clicking an existing atom while a template is armed --
    but they can also be a deliberate overlap, and this cannot tell the
    difference. Bonds are re-pointed at the survivor before its twin goes.
    """
    from rdkit import Chem

    mol = _read(molblock)
    if mol.GetNumConformers() == 0:
        return molblock
    conformer = mol.GetConformer()
    positions = [conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]

    lengths = [
        positions[b.GetBeginAtomIdx()].Distance(positions[b.GetEndAtomIdx()])
        for b in mol.GetBonds()
    ]
    lengths = [length for length in lengths if length > 0]
    if not lengths:
        return molblock
    limit = (sorted(lengths)[len(lengths) // 2]) * 0.01

    # survivor index -> the atoms being folded into it. Built first, so the
    # edit below works from a stable picture rather than from indices that
    # shift as atoms are removed.
    merge_into: dict[int, list[int]] = {}
    claimed: set[int] = set()
    for i in range(mol.GetNumAtoms()):
        if i in claimed:
            continue
        for j in range(i + 1, mol.GetNumAtoms()):
            if j in claimed or mol.GetBondBetweenAtoms(i, j) is not None:
                continue
            if positions[i].Distance(positions[j]) <= limit:
                merge_into.setdefault(i, []).append(j)
                claimed.add(j)

    if not merge_into:
        return molblock

    editable = Chem.RWMol(mol)
    for survivor, doomed in merge_into.items():
        for victim in doomed:
            for neighbour in [n.GetIdx() for n in mol.GetAtomWithIdx(victim).GetNeighbors()]:
                if neighbour == survivor or editable.GetBondBetweenAtoms(survivor, neighbour):
                    continue
                bond = mol.GetBondBetweenAtoms(victim, neighbour)
                editable.AddBond(survivor, neighbour, bond.GetBondType())
    for victim in sorted(claimed, reverse=True):
        editable.RemoveAtom(victim)

    return _write(editable.GetMol())


_CORE_FIXES = (
    QuickFix(
        fix_id="remove_explicit_hydrogens",
        label="Make hydrogens implicit",
        safety=FixSafety.SAFE,
        apply=remove_explicit_hydrogens,
        description="The molecule is unchanged; only how it is written.",
    ),
    QuickFix(
        fix_id="recompute_layout",
        label="Recompute layout",
        safety=FixSafety.REVERSIBLE,
        apply=recompute_layout,
        description="Redraws the structure. The chemistry is untouched.",
    ),
    QuickFix(
        fix_id="keep_largest_fragment",
        label="Keep the largest fragment",
        safety=FixSafety.LOSSY,
        apply=keep_largest_fragment,
        description="Discards the other fragments. For a salt this removes the counter-ion.",
    ),
    QuickFix(
        fix_id="merge_coincident_atoms",
        label="Merge overlapping atoms",
        safety=FixSafety.LOSSY,
        apply=merge_coincident_atoms,
        description="Fuses atoms drawn at the same point into one, keeping their bonds.",
    ),
)


def build_default_fix_registry() -> QuickFixRegistry:
    registry = QuickFixRegistry()
    for fix in _CORE_FIXES:
        registry.register(fix)
    return registry
