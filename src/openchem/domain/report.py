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

import dataclasses
import math
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

    def with_facts(self, facts: tuple[Fact, ...]) -> StructureReport:
        """A copy showing only `facts`. Frozen, so filtering makes a new one."""
        return dataclasses.replace(self, facts=facts)

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


_Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class ArrowAnnotation:
    """A physical vector the calculation produced, drawable on the conformer.

    **UNITS AND FRAME ARE THE CONTRACT.** `anchor` is in Angstrom, in the
    conformer's own coordinate frame -- the same frame the molblock the
    calculator ran on is written in, so a dialog that loads that conformer
    needs no transform and a view that shows an ALIGNED copy must not draw
    this without applying the same alignment. `vector` is the physical
    quantity in its own units (`units` says which -- "D" for a dipole),
    and its magnitude must NEVER be read as Angstrom: the renderer maps it
    to a display length and says so, because direction is physics and
    on-screen length is presentation.

    **`anchor` is a rendering anchor, not part of the physical
    definition.** A neutral molecule's dipole is origin-independent;
    anchoring the drawn arrow at the centre of mass is a display choice,
    and translating the molecule does not change the dipole.
    """

    anchor: _Vector3
    vector: _Vector3
    units: str
    label: str


@dataclass(frozen=True)
class ConeAnnotation:
    """A cone the calculation swept -- apex, axis, opening, extent, all in
    Angstrom in the conformer's frame. `axis` points from the apex toward
    the cone's opening; `length` is how far along the axis the calculation
    actually reached, never a number assembled to look plausible."""

    apex: _Vector3
    axis: _Vector3
    half_angle_deg: float
    length: float
    label: str


@dataclass(frozen=True)
class AxesAnnotation:
    """Three SIGNED direction vectors with half-extents, in Angstrom in the
    conformer's frame. The vectors are the exact directions the reported
    extents were measured along, sign convention included -- an
    eigenvector's sign is arbitrary, so a consumer must never re-derive
    these and risk rendering a mathematically identical answer pointing
    the other way."""

    origin: _Vector3
    axes: tuple[_Vector3, _Vector3, _Vector3]
    extents: tuple[float, float, float]
    labels: tuple[str, str, str]


SpatialAnnotation = ArrowAnnotation | ConeAnnotation | AxesAnnotation


def _finite_vector3(value: Any) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value)
    )


def valid_spatial_annotation(annotation: Any) -> bool:
    """Whether `annotation` is WELL-FORMED. Structural only, failing closed.

    The `valid_total_declaration` split, applied to geometry: this checks
    that vectors have three finite components, that an arrow or cone axis
    is not the zero vector, that a cone opens by a real angle
    (0 < half-angle < 180) over a positive length, and that axes come in
    threes with non-negative extents. **The half-angle bound is 180, not
    90, because real ligand cones open past the hemisphere**: Tolman's own
    table has P(tBu)3 at a FULL angle of 182 degrees, half-angle 91 -- a
    bound of 90 would refuse a legitimate measurement. It does NOT check that the dipole
    points the right way or that a cone matches the steric sweep -- those
    are chemistry claims, and the producers' own tests hold them.

    A consumer that receives an annotation failing this must REFUSE to
    draw it (with a log line), never guess or normalise: a picture built
    from repaired nonsense reads as a result, which is worse than no
    picture. And nothing may ever DERIVE an annotation from numbers found
    lying in provenance -- `ReportResult.spatial == ()` is the producer's
    statement that this result has no spatial representation.
    """
    if isinstance(annotation, ArrowAnnotation):
        return (
            _finite_vector3(annotation.anchor)
            and _finite_vector3(annotation.vector)
            and any(v != 0.0 for v in annotation.vector)
        )
    if isinstance(annotation, ConeAnnotation):
        return (
            _finite_vector3(annotation.apex)
            and _finite_vector3(annotation.axis)
            and any(v != 0.0 for v in annotation.axis)
            and isinstance(annotation.half_angle_deg, (int, float))
            and math.isfinite(annotation.half_angle_deg)
            and 0.0 < annotation.half_angle_deg < 180.0
            and isinstance(annotation.length, (int, float))
            and math.isfinite(annotation.length)
            and annotation.length > 0.0
        )
    if isinstance(annotation, AxesAnnotation):
        return (
            _finite_vector3(annotation.origin)
            and isinstance(annotation.axes, tuple)
            and len(annotation.axes) == 3
            and all(_finite_vector3(axis) and any(v != 0.0 for v in axis) for axis in annotation.axes)
            and isinstance(annotation.extents, tuple)
            and len(annotation.extents) == 3
            and all(
                isinstance(e, (int, float)) and not isinstance(e, bool) and math.isfinite(e) and e >= 0.0
                for e in annotation.extents
            )
            and isinstance(annotation.labels, tuple)
            and len(annotation.labels) == 3
        )
    return False


@dataclass(frozen=True, kw_only=True)
class ReportResult(StructureReport):
    """A CALCULATOR's output, as facts rather than a list of strings.

    This is what `AlertResult` had quietly become. `matched` is a
    `list[str]`, and it turned into the generic line carrier for anything
    that was not a single scalar: `topology_analysis` puts
    `"Szeged index: 12"` in it, `regulatory/calculator.py` documents doing
    so deliberately. Counted before this existed: **25 distinct
    `alert_id`s, of which only five are alerts.** The other twenty were
    reports wearing an alert's clothes, and the panel painted every one of
    them in warning red.

    A `Fact` carries what a string cannot: units, basis, evidence,
    limitations, which atoms it is about, and how specialist it is. All of
    that was already being computed and then flattened away at the last
    step.

    **`AlertResult` is NOT deprecated.** PAINS, BRENK, mutagenicity and
    hERG really are catalogs where a match is a warning, and "N alert(s)"
    in red is the right rendering for them. This is for everything else.

    The three identity fields mirror `AlertResult`'s so a migrating
    calculator changes its return type and nothing else -- the id it
    already publishes under, the display name, and the category the panel
    files it in.
    """

    report_id: str  # e.g. "geometry_analysis", matching the calculator id
    name: str  # display name, e.g. "Geometry"
    category: str = "other"
    #: Geometry the CALCULATION produced -- a dipole vector, a swept cone,
    #: measured axes -- drawable on the conformer the calculator ran on.
    #:
    #: **ANALYTICAL GEOMETRY ONLY, NEVER UI DECORATION.** "Highlight atom
    #: 4" belongs in `VisualizationLayer`; putting presentation choices
    #: here would couple the domain layer to how panels look, which is the
    #: drift this sentence exists to stop. Declared by the producer,
    #: validated by `valid_spatial_annotation`, rendered by the UI --
    #: never inferred by the UI from numbers found in provenance. An empty
    #: tuple is the producer's statement that this result has no spatial
    #: representation, which is true of most of them: a Wiener index, a
    #: formula and a pKa have no geometry, and a decorative model would
    #: dress a number up as a picture.
    #:
    #: Defaulted, so every existing constructor and plugin keeps working.
    spatial: tuple[SpatialAnnotation, ...] = ()

    @property
    def matched(self) -> list[str]:
        """The facts as lines, for anything still expecting `AlertResult`.

        **Derived, never stored.** A fact already holds its label, value
        and units separately, so this composes them on demand; there is no
        second copy to fall out of step with the facts, and nothing can
        write to it.

        Kept because `matched` is in the plugin API and is what a large
        number of existing assertions read. A test asking "does the
        topology calculator report a Randic index" is asking a real
        question, and the answer is the same whichever shape it arrives
        in -- so those tests keep working and keep meaning something.

        New code should read `facts`: this cannot express units, basis,
        evidence, limitations or which atoms a value is about, which is
        the entire reason for the migration.
        """
        return [
            f"{fact.label}: {fact.display_value}" if fact.label != self.name else fact.display_value
            for fact in self.facts
        ]
