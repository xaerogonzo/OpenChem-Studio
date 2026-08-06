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

`BondReport` and `MoleculeReport` are the obvious siblings. Nothing below
is atom-specific on purpose -- `AtomFact` and `FactCategory` describe a
FINDING, not an atom -- so admitting them later should not need a
redesign.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openchem.domain.common import ScientificResult
from openchem.domain.structure_issue import Basis


class FactCategory(str, Enum):
    """What KIND of fact this is -- deliberately not which module made it.

    The UI groups by this, and that is the whole reason it exists. Grouping
    by producer gives four consecutive "Lewis" headings, which reads as an
    implementation detail leaking onto the screen. Grouping by category
    gives Electronic / Topology / Spectroscopy, which is how somebody
    already thinks about an atom before they open anything.

    `AtomFact.source` still records the producer, because "where did this
    come from" is a real question -- it is just a different question from
    "what sort of thing is it".
    """

    IDENTITY = "identity"
    ELEMENT = "element"
    STRUCTURE = "structure"
    ELECTRONIC = "electronic"
    QUANTUM = "quantum"
    SPECTROSCOPY = "spectroscopy"
    TOPOLOGY = "topology"
    GEOMETRY = "geometry"
    REGULATORY = "regulatory"


#: Display order. A category absent from a report is simply skipped, so
#: this is an ordering rather than a required set.
CATEGORY_ORDER: tuple[FactCategory, ...] = (
    FactCategory.IDENTITY,
    FactCategory.ELEMENT,
    FactCategory.STRUCTURE,
    FactCategory.ELECTRONIC,
    FactCategory.QUANTUM,
    FactCategory.SPECTROSCOPY,
    FactCategory.TOPOLOGY,
    FactCategory.GEOMETRY,
    FactCategory.REGULATORY,
)

CATEGORY_LABELS: dict[FactCategory, str] = {
    FactCategory.IDENTITY: "Identity",
    FactCategory.ELEMENT: "Element",
    FactCategory.STRUCTURE: "Structure",
    FactCategory.ELECTRONIC: "Electronic",
    FactCategory.QUANTUM: "Quantum",
    FactCategory.SPECTROSCOPY: "Spectroscopy",
    FactCategory.TOPOLOGY: "Topology",
    FactCategory.GEOMETRY: "Geometry",
    FactCategory.REGULATORY: "Regulatory",
}

#: Open expanded. Everything else starts collapsed: a hundred-odd facts
#: rendered flat is a wall, and progressive disclosure is far cheaper to
#: design in than to retrofit.
DEFAULT_EXPANDED: frozenset[FactCategory] = frozenset(
    {FactCategory.IDENTITY, FactCategory.ELECTRONIC}
)


@dataclass(frozen=True)
class FactLink:
    """Where to go to see the tool this fact came from.

    **The parameters are the point.** "Open NMR" is much less useful than
    "open NMR, select this nucleus, highlight its peak", and the codebase
    already works this way -- `PeriodicTableDialog.select(symbol)` exists
    and takes exactly this kind of argument.

    A link makes the inspector a HUB rather than a replacement: it answers
    "where did this come from" by handing you over to the tool that owns
    the answer, instead of reimplementing that tool's view.
    """

    #: Which surface to open: "calculator_inspector", "nmr_view",
    #: "periodic_table", "structure_check", "interactions".
    target: str
    #: Whatever the target needs -- calculator_id, element symbol, atom
    #: index, issue id. Kept open rather than typed per target so a new
    #: destination does not change this class.
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""


@dataclass(frozen=True)
class AtomFact:
    """One thing known about one atom, with its provenance and its basis.

    **`value` is `Any`, and `display_value` sits beside it.** A
    `str | float` union looks tidier right up until it has to hold a list
    of locants, a set of ring systems, several oxidation assignments, a
    spectral peak, or the evidence behind a Lewis role. Flattening those
    into a string throws away precisely the structure a plugin or the AI
    assistant wants to consume. The UI renders `display_value` and never
    has to care what the value really is.

    `basis` is the existing DETERMINISTIC/HEURISTIC vocabulary rather than
    a confidence number, for the reason the structure checker has none: a
    percentage nobody measured is worse than an honest label.
    """

    category: FactCategory
    label: str
    value: Any
    display_value: str
    #: The producing module or analysis -- "LewisAnalysis", "RDKit",
    #: "gasteiger_charge". Provenance, not grouping.
    source: str
    basis: Basis
    #: Why this fact holds: the rules that fired, the SMARTS that matched.
    evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    link: FactLink | None = None
    #: Set when the value is a number, so a consumer can format or compare
    #: without re-parsing `display_value`.
    units: str = ""


@dataclass(frozen=True, kw_only=True)
class AtomReport(ScientificResult):
    """Every fact collected about one atom.

    `structure_version` is what makes a cached report safe to reuse. It
    comes from `StructureCheckService.current_version()`, the counter that
    already exists and already increments on every structure change --
    reusing it means a report cannot outlive the structure it describes,
    and means there is only one such mechanism to reason about.

    Keying on a VERSION rather than a timestamp also leaves the door open
    to diffing two reports of the same atom ("at version 12 the Lewis role
    changed from donor to ambiphilic"), which is a comparison rather than
    a new subsystem.
    """

    molecule_uuid: str
    atom_index: int
    symbol: str = ""
    structure_version: int = 0
    facts: tuple[AtomFact, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.facts)

    def by_category(self) -> dict[FactCategory, tuple[AtomFact, ...]]:
        """Facts grouped for display, in `CATEGORY_ORDER`.

        Categories with nothing in them are omitted rather than shown
        empty -- an atom with no spectroscopy should not carry a
        Spectroscopy heading saying so.
        """
        grouped: dict[FactCategory, list[AtomFact]] = {}
        for fact in self.facts:
            grouped.setdefault(fact.category, []).append(fact)
        return {
            category: tuple(grouped[category])
            for category in CATEGORY_ORDER
            if category in grouped
        }

    def facts_from(self, source: str) -> tuple[AtomFact, ...]:
        return tuple(fact for fact in self.facts if fact.source == source)

    def find(self, text: str) -> tuple[AtomFact, ...]:
        """Facts matching `text`, for the inspector's search box.

        Searches the label, the rendered value and the evidence, because
        somebody typing "aromatic" may be looking for a label, a value or
        the rule that produced one, and they should not have to know
        which.
        """
        needle = text.strip().lower()
        if not needle:
            return self.facts
        return tuple(
            fact
            for fact in self.facts
            if needle in fact.label.lower()
            or needle in fact.display_value.lower()
            or any(needle in item.lower() for item in fact.evidence)
        )
