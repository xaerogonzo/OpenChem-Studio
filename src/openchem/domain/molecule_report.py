"""Everything known about a whole molecule.

The third sibling, and the one whose value is least about new information
and most about REACH. The Properties panel already shows most of this;
what it cannot do is hand the whole lot to a plugin, an export, a batch
row or an assistant as one structured object. `MoleculeReport` is that
object.

**It is not "the Properties panel as data" and the difference matters.**
The panel shows what its 51 registered calculators produce. A report also
carries identity, structure-check findings, alerts, Lewis character and
what spectra exist -- the things that live in four other panels. The point
is that one call answers "what do you know about this molecule", where
today the answer is spread across the whole application.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.report import StructureReport


@dataclass(frozen=True, kw_only=True)
class MoleculeReport(StructureReport):
    """Every fact collected about one molecule.

    `display_name` and `formula` are lifted out of the facts because a
    consumer listing several reports needs to label them without walking
    the fact tuple, and because those two are what a person recognises a
    molecule by.
    """

    display_name: str = ""
    formula: str = ""
    #: How many atoms and bonds the report could have been built for. A
    #: molecule report is the natural index into the per-atom and per-bond
    #: ones, and a consumer should not have to re-parse a structure to know
    #: how many there are.
    atom_count: int = 0
    bond_count: int = 0
