"""Every picture a result declares, as peers, each saying what KIND it is.

**THEY ARE ALREADY PEERS IN THE MODEL AND WERE NOT ON SCREEN.** A chart, a
2D depiction and a 3D overlay are all producer-declared annotations validated
fail-closed, and `ui/visualization.py`'s own header records the layer type as
"renderer-independent". What differed was where each ended up: charts and
depictions render inside the reader, and a spatial annotation could only be
seen in a separate modal window that the reader was never part of.

**AND THE TYPE LABEL IS THE POINT, NOT DECORATION.** "Open" says nothing
about what arrives. A reader choosing between a stick chart of an isotope
pattern, a 2D structure with sites marked on it and a vector drawn on a 3D
conformer is choosing between three different things to look at, and the
three cost very different amounts to open -- a 3D overlay is a QtWebEngine
process, which this project has measured accumulating into a 40-minute hang.

**KIND IS DERIVED FROM THE ANNOTATION TYPE, NEVER FROM A STRING ON IT.**
`chart_widget_for` already dispatches by type in one place, and its own
comment says why: a `kind ==` string ladder would be a weaker vocabulary
beside the types the domain already has, and its typos fail open. This asks
the same question the same way, so the two cannot disagree about what an
annotation IS.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.report import (
    ArrowAnnotation,
    AxesAnnotation,
    ConeAnnotation,
    DepictionAnnotation,
    LineChartAnnotation,
    StickChartAnnotation,
)

#: A plot of numbers -- sticks or curves.
CHART = "Chart"
#: The molecule as drawn, with atoms marked on it.
DEPICTION = "2D depiction"
#: Something drawn on a 3D conformer: a vector, a cone, a set of axes.
OVERLAY_3D = "3D overlay"

#: The closed vocabulary, so a consumer can be total over it. A kind absent
#: from this is a programming error rather than a new sort of picture, which
#: is the same fail-closed rule `RESULT_KINDS` follows.
VISUALIZATION_KINDS = (CHART, DEPICTION, OVERLAY_3D)

#: Annotation type -> kind. TOTAL over the six shipped annotation types, and
#: a walk over the source asserts it stays total -- a seventh type added
#: without an entry here would silently become "no picture at all", which is
#: the invisible failure this module exists to end.
_KIND_OF_ANNOTATION = {
    StickChartAnnotation: CHART,
    LineChartAnnotation: CHART,
    DepictionAnnotation: DEPICTION,
    ArrowAnnotation: OVERLAY_3D,
    ConeAnnotation: OVERLAY_3D,
    AxesAnnotation: OVERLAY_3D,
}

#: Which kinds a fact list can draw for itself.
#:
#: **A 3D OVERLAY IS DELIBERATELY NOT ONE.** It needs a `Mol3DViewerBackend`,
#: which is a QtWebEngine process -- this project has measured those
#: accumulating to 116 and hanging the suite -- and a fixed-height 3D view
#: inside a `QScrollArea` with `setWidgetResizable(True)` is the
#: height-for-width fight already lost three times here. So it is offered as
#: something to OPEN, which is a smaller claim than rendering it in a row.
_INLINE_KINDS = frozenset({CHART, DEPICTION})


@dataclass(frozen=True)
class Visualization:
    """One declared picture, and what a reader can do with it."""

    #: The producer's own title, or a positional fallback.
    title: str
    #: One of `VISUALIZATION_KINDS`.
    kind: str
    #: Whether a fact list can render it, or whether it has to be opened.
    inline: bool
    #: Which annotation this is among the ones the result declared, so an
    #: "open" action names one rather than "the spatial ones".
    index: int


def kind_of_annotation(annotation) -> str:
    """Which kind `annotation` is, or raise.

    Refuses rather than defaulting, for the reason `kind_of` does: a default
    turns an unrecognised annotation into a plausible-looking picture of the
    wrong sort, and a reader cannot tell that from a producer's own choice.
    """
    kind = _KIND_OF_ANNOTATION.get(type(annotation))
    if kind is None:
        raise TypeError(
            f"{type(annotation).__name__} declares no visualization kind; add it "
            "to _KIND_OF_ANNOTATION rather than letting it render as nothing"
        )
    return kind


def declared_visualizations(entry) -> tuple[Visualization, ...]:
    """Every picture `entry` declares, charts first, then spatial.

    **READ WITH `getattr`, BECAUSE NOT EVERY ENTRY HAS EITHER FIELD.**
    `charts` is on `ReportResult` and on a summary view; `spatial` is on
    `ReportResult` alone; `StructureReport`, `AtomReport` and `BondReport`
    have neither, and this is rendered by a widget the Atom Inspector also
    uses. The reader contract deliberately excludes both for that reason.

    **NOTHING HERE DERIVES A PICTURE.** An empty result is the producer's
    statement that it has none -- the rule `_rebuild_charts` already states,
    and the reason elemental analysis's "C: 55.34%" facts do not become bars.
    """
    owner = str(getattr(entry, "name", "") or "")
    found: list[Visualization] = []
    for annotation in tuple(getattr(entry, "charts", ()) or ()):
        found.append(_describe(annotation, len(found), owner))
    for annotation in tuple(getattr(entry, "spatial", ()) or ()):
        found.append(_describe(annotation, len(found), owner))
    return tuple(found)


def _describe(annotation, index: int, owner: str = "") -> Visualization:
    kind = kind_of_annotation(annotation)
    # **`label` IS A VALUE ON EVERY SPATIAL PRODUCER, NOT A NAME, AND DRIVING
    # THE APP IS WHAT SHOWED IT.** The first version read `title or label`,
    # on the reasoning that the two families name themselves differently --
    # and the row for aspirin's dipole came out titled **"0.89 D"**, a
    # measurement sitting where a picture's name belongs. Checked across all
    # three shipped producers afterwards, every one of them formats a NUMBER
    # into that field:
    #
    #     dipole.py             label=f"{magnitude:.2f} D"
    #     steric.py             label=f"{angle:.1f} deg"
    #     geometry_analysis.py  labels=one per axis
    #
    # It is a caption drawn ON the model, which is why the 3D view wants it
    # and a list of pictures does not.
    #
    # **AND MY OWN FIXTURE HAD INVENTED THE OPPOSITE**, passing
    # `label="Dipole moment"` -- a name no producer writes -- so every unit
    # test agreed with a rule the application disproved on its first run.
    #
    # So the fallback is the OWNER's name: a spatial annotation is one
    # report's picture, and the report is the thing that names it.
    name = str(getattr(annotation, "title", "") or "")
    return Visualization(
        # The annotation's own title, then the result it belongs to, then the
        # KIND -- never a positional "Visualization 3", which tells a reader
        # deciding whether to open something nothing at all.
        title=name or owner or kind,
        kind=kind,
        inline=kind in _INLINE_KINDS,
        index=index,
    )
