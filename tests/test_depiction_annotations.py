"""A picture drawn ON the structure, and the boundary that keeps it honest.

The third chart kind is the one that is not a chart, and the whole design
rests on a split:

    annotation      WHAT to draw -- atom indices and their styling
    report          WHICH molecule -- StructureReport.molecule_uuid
    render context  the geometry, resolved and supplied by the UI

**IT WRAPS `VisualizationLayer` RATHER THAN RESTATING IT.** That type has
been "atom index -> colour and label, renderer-independent" since Phase 11
and is what the 3D viewer already consumes, so a per-atom map of its own
would have been a second representation of one idea. Half this file exists
to keep that true.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.lewis import LEWIS_ROLE_COLOURS, compute_lewis_sites
from openchem.domain.report import DepictionAnnotation, valid_chart_annotation
from openchem.domain.visualization import VisualizationLayer
from openchem.ui.widgets.chart_widgets import CHART_WIDGET_TYPES, chart_widget_for
from openchem.ui.widgets.depiction_widget import NO_STRUCTURE, DepictionWidget

import conftest

_DOMAIN = Path(__file__).resolve().parent.parent / "src" / "openchem" / "domain"


def _layer(**overrides) -> VisualizationLayer:
    fields = {"name": "Lewis sites", "atom_colors": {0: "#0072b2"}}
    fields.update(overrides)
    return VisualizationLayer(**fields)


def _molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


# --- the annotation ---------------------------------------------------------


def test_a_well_formed_depiction_is_accepted():
    assert valid_chart_annotation(DepictionAnnotation(layer=_layer()))


def test_it_carries_no_geometry_no_molecule_and_no_toolkit_object():
    """The contract, not an omission.

    An annotation holding an RDKit molecule would put a toolkit object in
    `domain/`; one holding coordinates would give the report a second copy
    of the structure that goes stale the moment the drawing changes. The
    field list is the assertion.
    """
    fields = set(DepictionAnnotation.__dataclass_fields__)
    assert fields == {"layer", "title", "caption"}

    layer_fields = set(VisualizationLayer.__dataclass_fields__)
    forbidden = {"mol", "molblock", "conformer", "coords", "coordinates", "bonds", "geometry"}
    assert not (layer_fields & forbidden), layer_fields


def test_the_domain_layer_type_is_the_one_the_viewer_already_uses():
    """MOVED, never copied.

    `VisualizationLayer` was in `ui/visualization.py` and is imported from
    `domain/` now; `ui/` re-exports it, so the twenty-two modules naming
    it are untouched. If these ever become two classes the 3D viewer and
    the 2D depiction stop describing the same thing.
    """
    from openchem.ui.visualization import VisualizationLayer as FromUI

    assert FromUI is VisualizationLayer


def test_the_moved_types_bring_no_toolkit_or_gui_with_them():
    """Which is what made the move possible at all.

    `domain/` may import neither a chemistry toolkit nor Qt --
    `tests/test_layering.py` holds that generally; this says the specific
    thing about the module that moved, so a later edit adding a `chem`
    import here fails naming this file rather than the layering guard.
    """
    source = (_DOMAIN / "visualization.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    for name in imported:
        assert not name.startswith("openchem.chem"), name
        assert not name.startswith("openchem.ui"), name
        assert not name.startswith(("PySide6", "rdkit")), name


@pytest.mark.parametrize(
    "colours",
    [{}, {0: "red"}, {0: "#f00"}, {-1: "#0072b2"}, {True: "#0072b2"}, {0: 5}],
    ids=["empty", "css-name", "short-hex", "negative", "bool-index", "not-a-string"],
)
def test_a_malformed_layer_is_refused(colours):
    """A MALFORMED COLOUR IS REFUSED, and that is not fussiness.

    Colour is producer-owned so a renderer cannot invent a legend -- but
    "any string is a colour" would let a malformed declaration through to
    be dropped silently by whichever painter received it, which is the
    failing-open this channel exists to prevent.

    `bool` is in the list because `isinstance(True, int)` is True in
    Python, so a flag where an atom index belongs would otherwise pass
    every check and colour atom 1.
    """
    assert not valid_chart_annotation(DepictionAnnotation(layer=_layer(atom_colors=colours)))


def test_the_validator_does_NOT_ask_whether_the_molecule_has_that_atom():
    """It cannot, and the line is the ownership model.

    This has atom indices and no structure. Whether index 99 exists is
    the render context's question, and `render_2d_svg` already answers it
    -- its `drawable()` guard drops an unknown index rather than raising,
    because calculators legitimately hold data keyed to `AddHs(mol)` while
    the depiction is the editor's molblock.
    """
    assert valid_chart_annotation(DepictionAnnotation(layer=_layer(atom_colors={99: "#0072b2"})))


# --- the widget and its render context --------------------------------------


def test_without_a_structure_it_SAYS_SO_rather_than_drawing_an_empty_frame(qapp):
    """"Nothing declared" and "no structure here" are different facts.

    An empty frame reads as `charts == ()`, which is a producer saying it
    has no picture. This one has a picture and nowhere to put it.
    """
    widget = DepictionWidget(DepictionAnnotation(layer=_layer()))
    assert not widget.is_drawing()
    assert NO_STRUCTURE in widget._message.text()
    conftest.dispose(widget)


def test_with_a_structure_it_draws_the_declared_colours(qapp):
    """End to end, through the renderer the app already uses.

    Asserted on the SVG rather than on the widget's state, because
    `render_2d_svg` draws text as bezier paths and a colour reaching the
    output is the only evidence the layer was honoured.
    """
    annotation = compute_lewis_sites(Chem.MolFromSmiles("CS(C)=O"), "m1", {}).charts[0]
    widget = DepictionWidget(annotation, molblock=_molblock("CS(C)=O"))
    assert widget.is_drawing()
    svg = widget._svg().lower()
    assert LEWIS_ROLE_COLOURS["donor"].lstrip("#") in svg
    conftest.dispose(widget)


def test_having_no_structure_is_not_reported_as_a_FAULT(qapp):
    """The distinction a fallback would erase.

    Deleting the no-molblock check still shows the right message -- by
    letting `render_2d_svg` raise on an empty molblock and catching it.
    Measured as a mutation: same words on screen, and a WARNING logged
    every time. A `FactView` with no host resolver is the ordinary case
    (the Atom Inspector has no project), so that would be a warning per
    render for nothing being wrong, which is how a log stops being read.

    The `except` stays for a genuinely broken molblock, where a warning
    is the right answer.
    """
    import logging

    widget = DepictionWidget(DepictionAnnotation(layer=_layer()))
    logger = logging.getLogger("openchem.ui")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    logger.addHandler(handler)
    try:
        widget.set_molblock("")
    finally:
        logger.removeHandler(handler)

    assert NO_STRUCTURE in widget._message.text()
    assert not records, f"no structure is not a fault: {[r.getMessage() for r in records]}"
    conftest.dispose(widget)


def test_a_BROKEN_molblock_is_reported_as_a_fault(qapp):
    """The other side, and it is what keeps the rule narrow.

    "Never log" satisfies the guard above and would swallow a host
    handing over text that is not a molblock at all -- which is a real
    defect somebody needs to see.
    """
    import logging

    widget = DepictionWidget(DepictionAnnotation(layer=_layer()))
    logger = logging.getLogger("openchem.ui")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    logger.addHandler(handler)
    try:
        widget.set_molblock("this is not a molblock")
    finally:
        logger.removeHandler(handler)

    assert NO_STRUCTURE in widget._message.text()
    assert records, "a broken structure IS a fault and is logged"
    conftest.dispose(widget)


def test_a_malformed_depiction_is_refused_by_the_widget(qapp):
    widget = DepictionWidget(DepictionAnnotation(layer=_layer(atom_colors={0: "red"})))
    assert widget.annotation() is None
    conftest.dispose(widget)


def test_the_factory_routes_it_and_declares_its_type(qapp):
    widget = chart_widget_for(DepictionAnnotation(layer=_layer()), molblock=_molblock("CCO"))
    assert isinstance(widget, DepictionWidget)
    assert type(widget) in CHART_WIDGET_TYPES
    conftest.dispose(widget)


def test_the_message_is_a_LABEL_and_never_rendered_through_the_svg_widget(qapp):
    """A `QSvgWidget` scales its viewBox to fill the pane.

    So a refusal drawn as SVG becomes unreadable text at whatever size the
    pane happens to be -- this project has already turned a refusal card
    into 37 px of clipped prose that way. Only a picture goes in the SVG.
    """
    widget = DepictionWidget(DepictionAnnotation(layer=_layer()))
    assert widget._view.isHidden(), "no picture, so the SVG surface is not shown"
    assert not widget._message.isHidden()
    conftest.dispose(widget)


# --- the producer -----------------------------------------------------------


def test_lewis_sites_declares_a_depiction():
    """SHIPPED IS NOT REACHABLE, for the third time in this branch.

    A chart kind whose only producer is a test is machinery nobody can
    see. The roadmap named Lewis-site diagrams as the thing waiting on
    this channel.
    """
    report = compute_lewis_sites(Chem.MolFromSmiles("CS(C)=O"), "m1", {})
    assert len(report.charts) == 1
    assert valid_chart_annotation(report.charts[0])
    assert report.charts[0].layer.atom_colors


def test_an_ambiphilic_atom_gets_ONE_colour_of_its_own():
    """It is one fact, not two.

    `analyse` reports ambiphilic as its own role for exactly this reason
    -- water is the textbook case, its oxygen donating a lone pair while
    its O-H accepts. Painting it as both would mean the last write wins,
    silently.
    """
    report = compute_lewis_sites(Chem.MolFromSmiles("O"), "m1", {})
    layer = report.charts[0].layer
    assert set(layer.atom_colors.values()) == {LEWIS_ROLE_COLOURS["ambiphilic"]}
    assert layer.atom_labels == {0: "ambiphilic"}


def test_a_molecule_with_no_sites_declares_no_picture():
    """`charts == ()` is how a producer says it has none, and an empty
    layer would be a claim followed by silence."""
    assert compute_lewis_sites(Chem.MolFromSmiles("C"), "m1", {}).charts == ()


def test_the_role_colours_are_categorical_and_distinguishable():
    """A role is a CATEGORY, so interpolating between donor and acceptor
    would be meaningless -- these are indexed, not blended, and taken from
    the Okabe-Ito palette this codebase already uses for categorical
    per-atom data because it is designed for distinguishability under the
    common colour-vision deficiencies."""
    assert len(set(LEWIS_ROLE_COLOURS.values())) == len(LEWIS_ROLE_COLOURS)
    assert set(LEWIS_ROLE_COLOURS) == {"donor", "acceptor", "ambiphilic"}


def test_the_caption_is_PAINTED_and_not_merely_declared(qapp):
    """The legend is the one thing a reader needs to interpret the picture.

    Found by driving the app: the Lewis diagram drew two blue atoms and
    nothing on screen said blue meant donor, because the caption was
    declared and dropped. This project's own rule -- a meaning that lives
    only in a tooltip is absent from every screenshot -- with the caption
    not reaching even a tooltip.
    """
    annotation = compute_lewis_sites(Chem.MolFromSmiles("CS(C)=O"), "m1", {}).charts[0]
    assert annotation.caption, "the producer really does declare one"

    widget = DepictionWidget(annotation, molblock=_molblock("CS(C)=O"))
    assert widget._caption.text() == annotation.caption
    assert not widget._caption.isHidden()
    conftest.dispose(widget)


def test_the_caption_goes_with_the_picture_it_explains(qapp):
    """Left showing over a refusal it would describe colours that are not
    on screen."""
    annotation = compute_lewis_sites(Chem.MolFromSmiles("CS(C)=O"), "m1", {}).charts[0]
    widget = DepictionWidget(annotation)
    assert widget._caption.isHidden(), "no picture, so no legend"
    conftest.dispose(widget)
