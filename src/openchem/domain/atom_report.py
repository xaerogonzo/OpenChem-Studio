"""Everything known about one atom, gathered into one object.

This application computes a great deal per atom -- sixteen
`PerAtomDataset` properties across eight modules, plus Lewis roles,
oxidation states, NMR shieldings, structure-check issues, element facts
and RDKit intrinsics -- and shows each of them somewhere different.
Answering "tell me everything about this atom" needed no new chemistry,
only somewhere for the answers to meet.

**The deliverable is `AtomReport`, not the panel that renders it.** The
inspector is its first consumer; clipboard export, the AI assistant
plugin, batch and any future scripting surface are the rest, and each of
them would otherwise have to interrogate ten calculators itself.

The shared vocabulary now lives in `domain/report.py`, because
`BondReport` and `MoleculeReport` arrived and wanted it unchanged --
which is what the original note here predicted. `AtomFact` is `Fact`
under its old name, and everything else is re-exported, so no import that
used to work stopped working.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.report import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    DEFAULT_EXPANDED,
    Fact,
    FactCategory,
    FactLink,
    StructureReport,
)

#: `AtomFact` was always a `Fact` -- it said nothing about atoms even when
#: it was the only one. Kept as the name a dozen call sites already use.
AtomFact = Fact

__all__ = [
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "DEFAULT_EXPANDED",
    "AtomFact",
    "AtomReport",
    "Fact",
    "FactCategory",
    "FactLink",
]


@dataclass(frozen=True, kw_only=True)
class AtomReport(StructureReport):
    """Every fact collected about one atom.

    Adds only what identifies the subject; everything else -- the facts,
    the version, the grouping and search -- is `StructureReport`.
    """

    atom_index: int
    symbol: str = ""
