"""The shared vocabulary for "everything known about X".

`AtomReport` came first and its types were written with nothing
atom-specific in them, on the stated bet that bonds and molecules would
want the same shape. They did: `Fact`, `FactCategory` and `FactLink` moved
here UNCHANGED, and `AtomReport` lost only its own identity fields to
`StructureReport`.

`domain/atom_report.py` re-exports everything under its old names, so the
bet also cost nothing to collect -- no existing import changed.

**A report is not a panel and not a calculation.** It is the answer to
"tell me everything you already know", assembled from results that other
things computed. Nothing here triggers work.
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
    already thinks about a structure before they open anything.

    `Fact.source` still records the producer, because "where did this come
    from" is a real question -- it is just a different question from "what
    sort of thing is it".

    The same categories serve atoms, bonds and molecules. A bond's length
    is GEOMETRY for exactly the reason an atom's coordinates are, and a
    reader who has learned the headings once should not have to learn them
    again per subject.
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


class Detail(str, Enum):
    """How much of a specialist a fact is for.

    **Two values, not five.** The obvious design was Basic / Physical /
    Electronic / Quantum / Everything, and that conflates two different
    axes: Physical, Electronic and Quantum are already `FactCategory`, and
    only "how deep" is new. Building the five-way version would have baked
    the confusion into the model, and a UI can still present exactly that
    control by composing the two.

    Two rather than three or four for the same reason `Basis` has two: an
    audience taxonomy nobody validated is the same mistake as a confidence
    percentage, which this project has built and declined to ship more
    than once. A third value becomes justified when a real case demands
    it, not in advance.
    """

    #: Anybody reading a structure wants this: element, charge, ring
    #: membership, a chemical shift.
    STANDARD = "standard"
    #: Real, and specialist. Fukui indices, the dual descriptor, local
    #: softness -- a beginner handed all of them at once learns nothing.
    ADVANCED = "advanced"


@dataclass(frozen=True)
class FactLink:
    """Where to go to see the tool this fact came from.

    **The parameters are the point.** "Open NMR" is much less useful than
    "open NMR, select this nucleus, highlight its peak", and the codebase
    already works this way -- `PeriodicTableDialog.select(symbol)` exists
    and takes exactly this kind of argument.

    A link makes a report a HUB rather than a replacement: it answers
    "where did this come from" by handing you over to the tool that owns
    the answer, instead of reimplementing that tool's view.
    """

    #: Which surface to open: "calculator_inspector", "nmr_view",
    #: "periodic_table", "structure_check", "interactions", "atom_report".
    target: str
    #: Whatever the target needs -- calculator_id, element symbol, atom
    #: index, issue id. Kept open rather than typed per target so a new
    #: destination does not change this class.
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""


@dataclass(frozen=True)
class Fact:
    """One thing known about one subject, with its provenance and basis.

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

    Says nothing about atoms, and that is deliberate -- it was written that
    way for `AtomReport` on the bet that bonds and molecules would want the
    identical shape, and they do.
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
    #: How specialist this is. Defaults to STANDARD, so every existing
    #: producer keeps its current behaviour and only facts that really are
    #: specialist have to say so.
    detail: Detail = Detail.STANDARD
    #: Which atoms this fact is ABOUT, for highlighting it on the structure
    #: when the reader hovers it.
    #:
    #: A separate field rather than something derived from `value`, because
    #: `value` may be a float, an enum, a list of locants or a spectral
    #: peak -- there is no general way to ask it "which atoms?". Empty
    #: means no highlight, so nothing existing changes.
    #:
    #: **Consumers must bounds-check these against whatever they are
    #: painting.** A conformer carries explicit hydrogens and a report
    #: usually does not: ethanol is 3 atoms in a report and 9 in the 3D
    #: viewer, and an out-of-range index raised `RuntimeError: Range Error`
    #: inside a Qt signal handler the last time this was assumed.
    highlight: tuple[int, ...] = ()


@dataclass(frozen=True, kw_only=True)
class StructureReport(ScientificResult):
    """What every report shares: facts, and the version they describe.

    `structure_version` is what makes a cached report safe to reuse. It
    comes from `StructureCheckService.current_version()`, the counter that
    already exists and already increments on every structure change --
    reusing it means a report cannot outlive the structure it describes,
    and means there is only one such mechanism to reason about.

    Keying on a VERSION rather than a timestamp also leaves the door open
    to diffing two reports of the same subject ("at version 12 the Lewis
    role changed from donor to ambiphilic"), which is a comparison rather
    than a new subsystem.
    """

    molecule_uuid: str
    structure_version: int = 0
    facts: tuple[Fact, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.facts)

    def by_category(self) -> dict[FactCategory, tuple[Fact, ...]]:
        """Facts grouped for display, in `CATEGORY_ORDER`.

        Categories with nothing in them are omitted rather than shown
        empty -- a subject with no spectroscopy should not carry a
        Spectroscopy heading saying so.
        """
        grouped: dict[FactCategory, list[Fact]] = {}
        for fact in self.facts:
            grouped.setdefault(fact.category, []).append(fact)
        return {
            category: tuple(grouped[category])
            for category in CATEGORY_ORDER
            if category in grouped
        }

    def facts_from(self, source: str) -> tuple[Fact, ...]:
        return tuple(fact for fact in self.facts if fact.source == source)

    def find(self, text: str) -> tuple[Fact, ...]:
        """Facts matching `text`, for a search box.

        Searches the label, the rendered value and the evidence, because
        somebody typing "aromatic" may be looking for a label, a value or
        the rule that produced one, and they should not have to know which.
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
