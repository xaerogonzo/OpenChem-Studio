"""Everything known about one bond.

The sibling `AtomReport` predicted, and the one with the most genuinely
bond-shaped content: order and aromaticity, ring membership, whether it
rotates, its measured length against what that order usually is, the
structure-check issues that name it, and where a retrosynthetic
disconnection would cut.

**A bond is identified by its index, and carries the two atoms it joins.**
Both are needed. The index is what RDKit, the structure checker and the
viewers all key on; the atom pair is what a person reads. Storing only
one of them would mean every consumer deriving the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.report import StructureReport


@dataclass(frozen=True, kw_only=True)
class BondReport(StructureReport):
    """Every fact collected about one bond.

    `label` is the human form -- "C3-O4", or "C3=O4" for a double bond --
    built once at collection time so a table, a clipboard export and a
    tooltip cannot disagree about how a bond is named.
    """

    bond_index: int
    begin_atom_index: int = -1
    end_atom_index: int = -1
    label: str = ""
