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
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openchem.domain.common import ScientificResult
from openchem.domain.structure_issue import Basis, Severity
from openchem.domain.visualization import VisualizationLayer


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
    #: WHICH OPENCHEM REPORT this fact arrived in -- a `report_id`, so
    #: `elemental_analysis` rather than "Elemental Analysis".
    #:
    #: **A SECOND, INDEPENDENT DIMENSION OF PROVENANCE, AND NOT A RENAME
    #: OF `source`.** They answer different questions: `source` is
    #: the scientific or producer-declared origin of the VALUE -- "RDKit",
    #: "LewisAnalysis" -- while this is which calculator run it came back
    #: in. A fact can honestly be sourced "RDKit" and originate in
    #: Elemental Analysis, and collapsing the two would destroy real
    #: provenance in order to record different provenance.
    #:
    #: Stamped by `merge_reports` rather than by producers, because a fact
    #: cannot know which of several reports it will be merged into.
    #: Defaulted to empty, so every existing producer is untouched and an
    #: unmerged report's facts carry nothing new.
    origin: str = ""
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
    #: A stable SEMANTIC identifier for what this fact MEANS, which a view
    #: resolves to a help contract -- `descriptor.tpsa`.
    #:
    #: **AN ID, NEVER A `HelpTooltip`.** That class is a UI object, and a
    #: domain dataclass holding one would put presentation inside `domain/`
    #: -- the layering `tests/test_layering.py` enforces. The producer names
    #: the concept; `ui/fact_help.py` says what the concept means.
    #:
    #: Empty means "nothing written for this one", which is the ordinary
    #: case and not a failure: a calculator's facts already carry their own
    #: evidence and limitations on the row, and the registry exists for
    #: values that have nowhere else to say what they are. It defaults to
    #: empty so every existing producer is untouched.
    help_id: str = ""

    @property
    def value_with_units(self) -> str:
        """`display_value` and `units` composed, for one line of prose.

        **THE ONE PLACE THE TWO ARE JOINED.** Eight consumers need a fact
        as a single string -- the row in `FactView`, the Atom Inspector's
        headline summary, the substance card's rows, the Properties
        panel's collapsed summary, the clipboard, Markdown and plain-text
        export, and `ReportResult.matched` -- and each of them composed it
        (or forgot to) on its own until this existed. Measured over the real
        registry at the time it was added: **896 distinct facts, 449
        carrying units**, of which the 223 arriving through
        `report_adapter` had the units in BOTH fields and exported
        `"C: 60.00 % %"`, while the other 226 held them apart and
        rendered `"70.7"` with no `kbar` anywhere on screen. One defect in
        each direction, from two conventions for one thing.

        **JSON and CSV DO NOT USE THIS, deliberately.** They give value and
        units their own field, which is the more useful shape for a script
        and is why `units` exists as a field at all. Composing there would
        destroy a distinction those formats are able to keep.

        Never written back into `display_value`: label, value and units
        stay three fields and the consumer joins them. Storing the joined
        string is the one-field-two-jobs bug that put the units in
        `display_value` in the first place.
        """
        units = self.units.strip()
        return f"{self.display_value} {units}".strip() if units else self.display_value


def group_facts_by_category(
    facts: tuple[Fact, ...] | list[Fact],
) -> dict[FactCategory, tuple[Fact, ...]]:
    """Facts grouped for display, in `CATEGORY_ORDER`.

    Categories with nothing in them are omitted rather than shown empty -- a
    subject with no spectroscopy should not carry a Spectroscopy heading
    saying so.

    **A FUNCTION BECAUSE THERE WERE THREE COPIES OF IT.** `StructureReport`,
    `DescriptorAggregate` and the results window's own all-results view each
    had one, and every reader entry goes through one of the three. Three
    implementations of "what the reader shows" is three chances to disagree
    about it, which this repository has paid for four times -- and its
    sibling `find_facts` HAD already diverged.
    """
    grouped: dict[FactCategory, list[Fact]] = {}
    for fact in facts:
        grouped.setdefault(fact.category, []).append(fact)
    return {
        category: tuple(grouped[category])
        for category in CATEGORY_ORDER
        if category in grouped
    }


def find_facts(facts: tuple[Fact, ...] | list[Fact], text: str) -> tuple[Fact, ...]:
    """Facts matching `text`, for a search box.

    Searches the label, the rendered value, the producing report and the
    evidence, because somebody typing "aromatic" may be looking for any of
    them and should not have to know which.

    **THE THREE COPIES DID NOT AGREE, AND THE SEARCH BOX IS ONE CONTROL.**
    Measured before this existed:

        StructureReport       label, value, evidence
        DescriptorAggregate   label, value
        the all-results view  label, value, origin, evidence

    So the same box meant three different things depending on which entry was
    focused -- Molecular Properties silently searched no evidence at all.
    Unifying on the widest is a no-op TODAY, which is what makes it safe:
    measured over the real registry, 0 of 164 producer facts carry an
    `origin` (the merge stamps its own copies, never the report's) and the
    aggregate's facts carry no evidence. It is the divergence that is
    removed, not a behaviour.
    """
    needle = text.strip().lower()
    if not needle:
        return tuple(facts)
    return tuple(
        fact
        for fact in facts
        if needle in fact.label.lower()
        or needle in fact.display_value.lower()
        or needle in fact.origin.lower()
        or any(needle in item.lower() for item in fact.evidence)
    )


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

    # **THERE WAS A `__bool__` HERE RETURNING `bool(self.facts)`, AND IT MADE
    # A FACTLESS REPORT FALSY.** Harmless while a report with nothing to say
    # was nothing to show; a trap the moment one is first-class -- a report
    # legitimately has no facts when it FAILED, when the method does not apply
    # to this molecule, or when its whole content is a picture.
    #
    # It made `if report:` mean "has facts" while reading as "exists", and
    # both of its reachable users meant the second. `MergedResultsDialog`
    # focused with `report_id if merged.report_for(report_id) else ""`, so a
    # refused calculator appeared in the selector and choosing it silently
    # fell back to All results; `FactView._molblock_for_report` resolved no
    # structure for one, so its depiction could never draw.
    #
    # Measured before removing it: ONE boolean-context use in `src/` and three
    # bare `assert report` in tests, every one of which meant "it still has
    # facts" (their own messages say so) and now says `report.facts` -- which
    # is a stronger assertion, not a weaker one. Nothing wanted this operator.
    #
    # A dataclass with no `__bool__` is truthy, which is the right answer to
    # "does this report exist". Anything wanting the other question asks
    # `report.facts`, where it cannot be misread.

    def by_category(self) -> dict[FactCategory, tuple[Fact, ...]]:
        """Facts grouped for display, in `CATEGORY_ORDER`."""
        return group_facts_by_category(self.facts)

    def facts_from(self, source: str) -> tuple[Fact, ...]:
        return tuple(fact for fact in self.facts if fact.source == source)

    def with_facts(self, facts: tuple[Fact, ...]) -> StructureReport:
        """A copy showing only `facts`. Frozen, so filtering makes a new one."""
        return dataclasses.replace(self, facts=facts)

    def find(self, text: str) -> tuple[Fact, ...]:
        """Facts matching `text`, for a search box."""
        return find_facts(self.facts, text)


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


@dataclass(frozen=True)
class Stick:
    """One line of a stick chart: where it stands, how tall, what it is.

    `label` is what a renderer may print beside a stick that has room for
    one -- an isotopologue, a fragment formula. Empty means the position
    and the height are the whole statement.

    **THE LABEL RIDES ON THE STICK RATHER THAN IN A PARALLEL LIST**, so
    "labels aligned with points" is true by construction and there is no
    off-by-one for a validator to catch.
    """

    x: float
    y: float
    label: str = ""


@dataclass(frozen=True)
class StickChartAnnotation:
    """A line spectrum the calculation produced: positions and heights.

    **THE AXIS DIRECTION IS THE PRODUCER'S, NEVER THE RENDERER'S GUESS.**
    NMR runs high shift to the left and m/z runs low mass to the left, and
    a renderer that picked by sniffing `x_units` would mirror one of them
    silently -- which does not look broken, it looks like a different
    compound. `IrSpectrumWidget` records the same convention as a measured
    choice rather than a stylistic one.

    **`y` IS THE QUANTITY THAT WAS COMPUTED, IN `y_units`.** Its magnitude
    is never pixels: a renderer maps the tallest stick to the plot height
    and prints the real maximum with its units. Renormalising is the
    PRODUCER'S call and `y_units` says which convention it used; a
    renderer that renormalises invents a calibrated axis.

    `caption` is the producer's own sentence under the plot -- where a
    mass spectrum says it is a CALCULATED natural-abundance distribution
    rather than something an instrument measured. Presentation-neutral
    here: this class knows nothing about spectra, and a Lewis-site or
    reaction diagram will use the same field for its own statement.

    Sticks are NOT required to arrive sorted, and producer order is
    preserved -- a hit test resolves first-match-wins, the rule both
    existing spectrum widgets already use for two peaks sharing an x.
    """

    sticks: tuple[Stick, ...]
    #: Axis name WITHOUT units, with the units beside it -- the
    #: `Fact.value` / `Fact.units` split, composed for display.
    x_label: str
    y_label: str
    #: True when high x belongs on the LEFT (chemical shift, wavenumber).
    #: Required rather than defaulted: one keyword at each call site buys
    #: out the whole class of silently-mirrored spectra.
    x_descending: bool
    x_units: str = ""
    y_units: str = ""
    title: str = ""
    caption: str = ""


@dataclass(frozen=True)
class LineSeries:
    """One curve of a line chart: its points and its name in the legend.

    **THE POINTS RIDE WITH THE NAME**, so "labels aligned with series" is
    true by construction -- the same reason `Stick` carries its own label
    rather than sitting beside a parallel list.

    A series does NOT carry its own axis direction or units. Those are
    properties of the CHART: two curves drawn on one pair of axes are in
    one coordinate system, and a renderer reconciling them per series
    would silently redraw one of them.
    """

    points: tuple[tuple[float, float], ...]
    name: str = ""


@dataclass(frozen=True)
class LineChartAnnotation:
    """A continuous curve the calculation produced: several series on one pair
    of axes.

    The second chart kind, and the sibling of `StickChartAnnotation`
    rather than a replacement: sticks are discrete events at a position
    (an isotopologue, a reflection) and a line is a quantity sampled
    across a range (a fraction against pH, an absorbance against
    wavelength). Drawing one as the other misstates what was computed.

    **THE AXIS FIELDS ARE THE STICK KIND'S, FOR THE SAME REASONS.**
    `x_descending` is required rather than defaulted, because a mirrored
    plot does not look broken -- it looks like a different result -- and
    `y` is the quantity that was computed in `y_units`, never pixels.

    **`x_descending` IS A COORDINATE TRANSFORM, NOT A DATA OPERATION.**
    False means numerical x increases left to right and True means it
    decreases; a renderer maps points through it and must never reverse
    or reorder them. What the producer handed over is what a hit test and
    a readout see.
    """

    series: tuple[LineSeries, ...]
    #: Axis name WITHOUT units, with the units beside it -- the
    #: `Fact.value` / `Fact.units` split, composed for display.
    x_label: str
    y_label: str
    #: True when high x belongs on the LEFT. Required, per the stick
    #: kind's own note: one keyword per call site buys out the whole class
    #: of silently-mirrored plots.
    x_descending: bool
    x_units: str = ""
    y_units: str = ""
    title: str = ""
    caption: str = ""
    #: Pin an end of the y axis, or None to derive it from the data.
    #:
    #: **AN AXIS DECLARATION, NOT A CHEMISTRY ONE**, which is what makes
    #: it belong on a generic annotation beside `x_descending`. A quantity
    #: with real bounds -- a microspecies distribution is 0-100% -- gets
    #: an axis at those bounds; everything else gets a padded fit. Found
    #: by rendering one and looking at it: a distribution that cannot
    #: leave 0-100 was drawn on an axis running -8% to 108%, which reads
    #: as headroom the quantity does not have.
    #:
    #: Only the end that is pinned is pinned: a curve bounded below at
    #: zero and unbounded above sets `y_min` alone and the top still fits
    #: the data.
    y_min: float | None = None
    y_max: float | None = None


#: The union of chart kinds. TWO members; `spatial` shipped as three and
#: each additional one costs a `|`. Every consumer dispatches by
#: `isinstance` from the first line, so a third is additive rather than a
@dataclass(frozen=True)
class DepictionAnnotation:
    """A picture drawn ON the structure rather than on a pair of axes.

    The third chart kind, and the one that is not a chart -- Lewis donor
    and acceptor sites coloured onto the 2D depiction, a per-atom
    contribution shown where the atoms are. `ReportResult.charts` means
    *producer-declared presentation annotations* and has since this
    arrived; the field keeps its name because renaming a shipped one is
    churn, and `visualizations` is the migration if anybody ever wants it.

    **IT WRAPS `VisualizationLayer` RATHER THAN RESTATING IT.** That type
    has been "atom index -> colour and label, renderer-independent" since
    Phase 11 and is what the 3D viewer already consumes, so a per-atom map
    of its own here would be a second representation of one idea -- the
    drift this repository has paid for five times. What this adds is only
    the presentation framing the channel needs, exactly as
    `StickChartAnnotation` adds axes and a caption around bare `Stick`s.

    **IT CARRIES NO GEOMETRY, NO MOLECULE AND NO TOOLKIT OBJECT**, and
    that is the contract rather than an omission:

        annotation      WHAT to draw -- atom indices and their styling
        report          WHICH molecule -- `StructureReport.molecule_uuid`
        render context  the geometry, resolved and supplied by the UI

    Which is how `spatial` already works: an `ArrowAnnotation` is in the
    molecule's frame and the viewer holds the molecule. Nothing here may
    grow atom coordinates, bond geometry, a conformer or a 2D layout; a
    renderer needing one asks a rendering service for it.
    """

    layer: VisualizationLayer
    title: str = ""
    caption: str = ""


#: The union of chart kinds. THREE members; `spatial` shipped as three and
#: each additional one costs a `|`. Every consumer dispatches by
#: `isinstance` from the first line, so a fourth is additive rather than a
#: rewrite of everything that reads a bare type alias.
ChartAnnotation = StickChartAnnotation | LineChartAnnotation | DepictionAnnotation


def _finite(*values: Any) -> bool:
    """Real numbers, and `bool` is not one.

    `isinstance(True, int)` is True in Python, so a producer handing over
    a flag where a coordinate belongs would otherwise pass every numeric
    check and plot at 1.0.
    """
    return all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        for v in values
    )


def _valid_stick(stick: Any) -> bool:
    return isinstance(stick, Stick) and _finite(stick.x, stick.y)


def _valid_series(series: Any) -> bool:
    """A series is well formed: a named tuple of finite (x, y) pairs.

    Says nothing about ORDER, SPACING or EMPTINESS -- those are the rules
    `valid_chart_annotation`'s line branch decides, and they are decided
    there so the reasoning sits with the refusals it explains.
    """
    return (
        isinstance(series, LineSeries)
        and isinstance(series.points, tuple)
        and all(
            isinstance(point, tuple) and len(point) == 2 and _finite(*point)
            for point in series.points
        )
    )


def valid_chart_annotation(annotation: Any) -> bool:
    """Whether `annotation` is WELL-FORMED. Structural only, failing closed.

    `valid_spatial_annotation`'s split, applied to a chart: the sticks are
    finite, there is at least one of them, both axes are named, and the
    direction flag is a real bool.

    **AT LEAST ONE STICK, because `charts == ()` is already how a producer
    says it has no chart.** An annotation holding nothing is a claim
    followed by silence -- the same contradiction `any(v != 0.0 ...)`
    refuses for a zero dipole vector.

    **BOTH AXIS LABELS MUST BE NON-EMPTY.** Numbers on an unlabelled axis
    read as a measurement in units the reader supplies themselves.
    Checking the string is PRESENT is structural; checking that it names a
    real unit is not, and is not done.

    **NEGATIVE HEIGHTS ARE ACCEPTED, DELIBERATELY.** Requiring `y >= 0`
    reads as structural for a stick chart and is a judgment about the
    chemistry: this application already computes signed per-atom
    quantities -- Crippen LogP contributions run either way -- and a
    difference spectrum is the obvious second case. A bound written from
    the common case is the `half_angle_deg < 180` mistake, which refused a
    real Tolman measurement. A mass spectrum's own non-negativity is held
    by the mass-spectrum tests, where it is a claim about mass spectra.

    It does NOT check that m/z values are reachable isotopologues, that
    intensities sum to anything, that a base peak sits at 100, or that any
    range is physically plausible -- those are chemistry claims and the
    producer's own tests hold them. It does not require sorted sticks.

    A consumer that receives an annotation failing this must REFUSE to
    draw it (with a log line), never sort, clamp or normalise it into
    shape: a picture built from repaired nonsense reads as a result. And
    nothing may ever DERIVE a chart from numbers found lying in the facts.
    """
    if isinstance(annotation, StickChartAnnotation):
        return (
            isinstance(annotation.sticks, tuple)
            and bool(annotation.sticks)
            and all(_valid_stick(stick) for stick in annotation.sticks)
            and isinstance(annotation.x_descending, bool)
            and isinstance(annotation.x_label, str)
            and bool(annotation.x_label.strip())
            and isinstance(annotation.y_label, str)
            and bool(annotation.y_label.strip())
        )
    if isinstance(annotation, DepictionAnnotation):
        return _valid_depiction(annotation)
    if isinstance(annotation, LineChartAnnotation):
        if not _valid_axes(annotation):
            return False
        if not isinstance(annotation.series, tuple) or not annotation.series:
            return False
        if not all(_valid_series(series) for series in annotation.series):
            return False
        return _line_series_rules_hold(annotation)
    return False


#: A hex colour, the one representation a declared depiction may use.
#: ONE spelling throughout rather than accepting `"#f00"`, an RGB tuple and
#: a CSS name in different places: `VisualizationLayer.atom_colors` has
#: always been "resolved hex", `ColorScale.color_for` emits exactly this,
#: and `render_2d_svg` and the 3D viewer both parse it. A second accepted
#: form would be a second parser in every consumer.
_HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _valid_depiction(annotation: DepictionAnnotation) -> bool:
    """Whether a declared depiction is WELL-FORMED. Structural only.

    Checks what can be checked WITHOUT the molecule, which is the line the
    ownership model draws: this has atom indices and no structure, so it
    can say an index is not a non-negative integer and cannot say whether
    the molecule has one. That second question belongs to the render
    context, which resolves `molecule_uuid` and already refuses an
    out-of-range index -- `render_2d_svg`'s own `drawable()` guard exists
    because calculators legitimately hold data keyed to `AddHs(mol)` while
    the depiction is the editor's molblock.

    **A MALFORMED COLOUR IS REFUSED**, and that is not fussiness. Colour
    is producer-owned so a renderer cannot invent a legend -- but "any
    string is a colour" would let a malformed declaration through to be
    dropped silently by whichever painter received it, which is the
    failing-open this channel exists to prevent.

    It does NOT judge the chemistry: which atoms are donors, whether two
    colours are distinguishable, whether a label is informative. A
    reviewer owns the meaning.
    """
    layer = annotation.layer
    if not isinstance(layer, VisualizationLayer):
        return False
    if not isinstance(layer.atom_colors, dict) or not layer.atom_colors:
        return False
    for index, colour in layer.atom_colors.items():
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            return False
        if not isinstance(colour, str) or not _HEX_COLOUR.match(colour):
            return False
    labels = layer.atom_labels
    if labels is not None:
        if not isinstance(labels, dict):
            return False
        for index, text in labels.items():
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                return False
            if not isinstance(text, str):
                return False
    return True


def _valid_axes(annotation: Any) -> bool:
    """The axis declaration both kinds share, and neither may skip.

    Split out when the line kind arrived so the two branches cannot drift
    apart on what an axis IS -- the rule this repository has paid for
    whenever one concept had two implementations.
    """
    return (
        isinstance(annotation.x_descending, bool)
        and isinstance(annotation.x_label, str)
        and bool(annotation.x_label.strip())
        and isinstance(annotation.y_label, str)
        and bool(annotation.y_label.strip())
    )


def _line_series_rules_hold(annotation: LineChartAnnotation) -> bool:
    """Whether a well-formed line chart's SERIES are acceptable.

    Reached only once every series is structurally sound: real
    `LineSeries` objects holding finite `(x, y)` pairs, at least one
    series, and both axes named. What is left is judgment, and the line
    this project holds is that **the validator owns the SHAPE and a
    reviewer owns the MEANING** -- `valid_chart_annotation` above accepts
    an m/z of 1e6 and negative heights, and says why it DECLINED each
    refusal. The same, here.

    ## REFUSED: A SERIES WHOSE x IS NOT MONOTONIC

    **A BREAK FROM `StickChartAnnotation`, AND THE GEOMETRY IS WHY.**
    That kind explicitly does not require sorting and preserves producer
    order, which costs nothing: sticks are drawn independently at their
    own positions, so order affects only which of two sticks sharing an x
    a hit test resolves to. A line is a POLYLINE -- consecutive points
    are joined -- so **order is not metadata about the picture, it IS the
    picture.** Scrambled x draws a zigzag that no reading of the data
    supports, and it is far likelier a producer building its points from
    an unordered mapping than a deliberate path.

    NON-DECREASING **OR** NON-INCREASING, never strict. Two values at one
    x is a real thing to have -- two measurements at one pH, a step in a
    titration -- and the direction is per series so a producer may hand
    over a curve running either way.

    **A PARAMETRIC PATH IS A DIFFERENT KIND, NOT A LOOSER RULE HERE.** A
    hysteresis loop or a phase portrait revisits x, and the honest home
    for one is its own annotation whose contract says the ORDER is the
    data. Weakening this to admit it would leave the ordinary case --
    a quantity sampled across a range -- with no check at all.

    ## REFUSED: A SERIES WITH NO POINTS

    `sticks` requires at least one member because `charts == ()` is
    already how a producer says it has no chart, and a named series
    holding nothing is the same contradiction one level down: a legend
    entry with no curve under it reads as "this quantity is zero here"
    rather than "this was not computed". A producer with nothing to say
    for a series omits the series.

    ## DECLINED: REQUIRING THE SERIES TO SHARE AN x GRID

    The five pH calculators do share `ph_grid`, so a rule fitted to them
    would pass today and refuse the first legitimate overlay -- a
    computed curve against a measured one, sampled where the instrument
    sampled. That is the `half_angle_deg < 180` mistake, which refused a
    real Tolman measurement because the common case looked like the only
    case.

    ## DECLINED: ANY RULE ABOUT WHAT THE NUMBERS MEAN

    No range check, no monotonic y, no requirement that fractions sum to
    one or that a probability lies in [0, 1]. Those are chemistry claims
    and the producers' own tests hold them.

    ## NaN IS NOT A GAP, and that is recorded rather than merely enforced

    `_finite` already refuses non-finite coordinates upstream. Stated
    here because the next reader to want a DISCONTINUOUS curve will find
    the validator refusing NaN with no supported way to express one, and
    the tempting repair is to weaken the check. It needs its own
    representation instead -- a series per segment is the cheap answer
    and needs nothing new.

    A consumer receiving an annotation this refuses must REFUSE TO DRAW
    it, never sort, clamp or trim it into shape. In particular the
    renderer may not quietly sort a scrambled series: that would move the
    refusal into a repair and put a picture built from repaired nonsense
    on the screen.
    """
    for series in annotation.series:
        if not series.points:
            return False
        xs = [x for x, _y in series.points]
        non_decreasing = all(a <= b for a, b in zip(xs, xs[1:]))
        non_increasing = all(a >= b for a, b in zip(xs, xs[1:]))
        if not (non_decreasing or non_increasing):
            return False
    return True


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
    #: Whether a MATCH here means "look at this" -- the catalog verdict,
    #: carried rather than dropped.
    #:
    #: **IT IS HERE BECAUSE DROPPING IT RE-CREATED THE DEFECT THE FIELD WAS
    #: INVENTED TO FIX.** `AlertResult.severity`'s own docstring says why it
    #: exists: "without it a renderer cannot tell 'this molecule contains a
    #: PAINS substructure' from 'this molecule weighs 43.025'". Once the
    #: Properties panel stopped painting alerts itself, the results reader
    #: became that renderer -- and `report_from_alert` was handing it a
    #: report with the verdict already discarded. Measured: a clean PAINS and
    #: an elemental analysis with no lines arrived BYTE-IDENTICAL (no facts,
    #: no severity), and a WARNING catalog was indistinguishable from an
    #: ERROR one.
    #:
    #: INFO by default, which keeps `report_fields` honest: a calculator
    #: migrating away from `AlertResult` is by definition not a catalog, so
    #: it declares nothing and gets the neutral value. Only
    #: `report_from_alert`, converting a genuine catalog, carries a real one.
    severity: Severity = Severity.INFO
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
    #: 2D charts the CALCULATION produced -- an isotope envelope, a site
    #: diagram -- drawable without a conformer.
    #:
    #: **ANALYTICAL DATA ONLY, NEVER DECORATION, AND NEVER DERIVED FROM
    #: THE FACTS.** `charts == ()` is the producer's statement that this
    #: result has no chart, which is true of most of them. Elemental
    #: analysis already emits "C: 55.34%" as facts, and a consumer that
    #: parsed those into bars would have invented a picture the producer
    #: never claimed -- a picture reads as a result. Declared by the
    #: producer, validated by `valid_chart_annotation`, rendered by the
    #: UI; the same contract `spatial` above carries, for the case where
    #: there is no 3D geometry to draw on.
    #:
    #: Defaulted, so every existing constructor and plugin keeps working.
    charts: tuple[ChartAnnotation, ...] = ()

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
            f"{fact.label}: {fact.value_with_units}"
            if fact.label != self.name
            else fact.value_with_units
            for fact in self.facts
        ]
