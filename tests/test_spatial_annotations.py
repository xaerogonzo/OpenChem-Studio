"""Shape-valued results drawn on the conformer: the contract, end to end.

Three layers of guard, deliberately overlapping. The DOMAIN guards hold
the fail-closed validation contract. The RENDERER guards hold the shape
state machine against the real page -- the machine mirrors
`apply_visualization`'s with one deliberate difference (a load DROPS
pending shapes, because their coordinates are in the previous conformer's
frame). And the DIRECTION ORACLE reads the geometry the page actually
drew, never the annotation: a producer sign bug and a renderer sign bug
would cancel in any annotation-level check, and the screenshot would look
perfectly right.
"""

from __future__ import annotations

import json
import math
import time

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dipole import centre_of_mass, compute_dipole_moment
from openchem.chem.geometry_analysis import compute_geometry_analysis
from openchem.chem.steric import compute_steric_analysis
from openchem.domain.report import (
    ArrowAnnotation,
    AxesAnnotation,
    ConeAnnotation,
    ReportResult,
    valid_spatial_annotation,
)
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend, shape_payloads

# The renderer's fixed conventions -- asserted, so a drive-by change to
# the page shows up here rather than as quietly different screenshots.
CONE_GENERATRICES = 16
CONE_CIRCLE_SEGMENTS = 32
ARROW_SPAN_FRACTION = 0.5
MIN_ARROW_LENGTH = 1.0

PAGE_READY_TIMEOUT_SECONDS = 60


def _with_conformer(smiles: str, seed: int = 7) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _wait_until(qapp, predicate, timeout_seconds: float = 15) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _run_js(qapp, backend: Mol3DViewerBackend, script: str) -> object:
    result: dict[str, object] = {}
    backend._page.runJavaScript(script, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=5)
    return result.get("value")


def _drawn(qapp, backend: Mol3DViewerBackend) -> list[dict]:
    raw = _run_js(qapp, backend, "JSON.stringify(drawnShapes)")
    return json.loads(raw) if raw else []


def _ready(qapp) -> Mol3DViewerBackend:
    backend = Mol3DViewerBackend()
    started = time.time()
    assert _wait_until(
        qapp, lambda: backend._page_ready, timeout_seconds=PAGE_READY_TIMEOUT_SECONDS
    ), f"page not ready after {time.time() - started:.1f}s"
    return backend


# --- domain: the fail-closed contract ---------------------------------------


def test_a_scalar_result_declares_no_spatial_representation():
    """`spatial == ()` is a statement, and the default makes it for every
    producer that has not thought about it -- the same restrictive-default
    move as `applies_to`."""
    result = ReportResult(report_id="x", name="X", molecule_uuid="u")
    assert result.spatial == ()


def test_malformed_annotations_are_refused_not_repaired():
    zero = ArrowAnnotation(anchor=(0.0, 0.0, 0.0), vector=(0.0, 0.0, 0.0), units="D", label="")
    nan = ArrowAnnotation(anchor=(0.0, 0.0, 0.0), vector=(float("nan"), 0.0, 1.0), units="D", label="")
    flat = ConeAnnotation(apex=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), half_angle_deg=0.0, length=1.0, label="")
    wrapped = ConeAnnotation(apex=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), half_angle_deg=180.0, length=1.0, label="")
    for bad in (zero, nan, flat, wrapped, "not an annotation"):
        assert not valid_spatial_annotation(bad)
    # And the render gate drops them BEFORE the bridge, so the page never
    # has to guess.
    assert shape_payloads([zero, nan]) == []


def test_a_bulky_ligands_half_angle_past_90_is_legitimate():
    """Tolman's own table has P(tBu)3 at a FULL angle of 182 degrees --
    half-angle 91. A bound of 90 would refuse a real measurement, which is
    why the validator's ceiling is 180."""
    wide = ConeAnnotation(apex=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), half_angle_deg=91.0, length=5.0, label="182 deg")
    assert valid_spatial_annotation(wide)


# --- producers ----------------------------------------------------------------


def test_the_dipole_arrow_is_anchored_at_the_centre_of_mass():
    mol = _with_conformer("Cl")
    result = compute_dipole_moment(mol, "u")
    assert len(result.spatial) == 1
    annotation = result.spatial[0]
    assert annotation.anchor == pytest.approx(tuple(centre_of_mass(mol)))
    assert annotation.vector == pytest.approx(tuple(result.provenance.parameters["vector"]))
    assert annotation.units == "D"


def test_a_symmetric_molecule_gets_no_arrow():
    """Benzene's residual vector is float noise -- its direction means
    nothing, and a drawn arrow would dress noise up as a result. The rule
    is tied to the DISPLAYED precision so text and picture cannot
    disagree: no arrow exactly when the panel says 'Dipole: 0.00'."""
    result = compute_dipole_moment(_with_conformer("c1ccccc1"), "u")
    assert result.spatial == ()
    assert "Dipole: 0.00" in result.matched[0]


def test_the_dipole_vector_rotates_with_the_frame():
    """The recurring frame-bug class, made a test: rotate the conformer,
    recompute, and the vector must follow the rotation with unchanged
    magnitude. A vector that stayed put would be in some other frame than
    the conformer it claims to annotate."""
    mol = _with_conformer("CO")
    before = compute_dipole_moment(mol, "u").spatial[0]

    conformer = mol.GetConformer()
    angle = math.radians(90)
    rotation = [
        [math.cos(angle), -math.sin(angle), 0.0],
        [math.sin(angle), math.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ]
    for i in range(mol.GetNumAtoms()):
        p = conformer.GetAtomPosition(i)
        x = rotation[0][0] * p.x + rotation[0][1] * p.y
        y = rotation[1][0] * p.x + rotation[1][1] * p.y
        conformer.SetAtomPosition(i, (x + 5.0, y - 2.0, p.z + 1.0))

    after = compute_dipole_moment(mol, "u").spatial[0]
    rotated = (
        rotation[0][0] * before.vector[0] + rotation[0][1] * before.vector[1],
        rotation[1][0] * before.vector[0] + rotation[1][1] * before.vector[1],
        before.vector[2],
    )
    assert after.vector == pytest.approx(rotated, abs=1e-9)
    magnitude = lambda v: math.sqrt(sum(x * x for x in v))  # noqa: E731
    assert magnitude(after.vector) == pytest.approx(magnitude(before.vector), abs=1e-12)


def test_the_cone_matches_the_steric_calculations_own_geometry():
    """Derived from the construction, never assembled from stored scalars.

    The apex must sit `metal_distance` beyond the donor along the bond
    axis, the half-angle must be half the reported full angle, and the
    length must be the sweep's actual reach -- the farthest vdW-sphere
    edge from the apex -- which for PPh3 is nothing like
    `metal_distance + sphere_radius` (two unrelated scalars that happen
    to be lying nearby in provenance).
    """
    mol = _with_conformer("c1ccccc1P(c1ccccc1)c1ccccc1")
    result = compute_steric_analysis(mol, "u")
    assert len(result.spatial) == 1
    cone = result.spatial[0]
    parameters = result.provenance.parameters
    assert cone.half_angle_deg == pytest.approx(parameters["cone_angle_deg"] / 2)

    prepared = Chem.AddHs(Chem.Mol(mol))
    positions = prepared.GetConformer().GetPositions()
    donor = parameters["donor_atom"]
    apex = cone.apex
    donor_distance = math.dist(apex, tuple(positions[donor]))
    assert donor_distance == pytest.approx(parameters["metal_distance_a"], abs=1e-6)

    table = Chem.GetPeriodicTable()
    reach = max(
        math.dist(tuple(positions[a.GetIdx()]), apex) + table.GetRvdw(a.GetAtomicNum())
        for a in prepared.GetAtoms()
        if a.GetIdx() != donor
    )
    assert cone.length == pytest.approx(reach, abs=1e-6)
    assert cone.length != pytest.approx(
        parameters["metal_distance_a"] + parameters["sphere_radius_a"], abs=0.5
    )


def test_a_2d_input_gets_no_cone_because_its_frame_is_not_displayable():
    """The steric calculator embeds its own ensemble for a flat drawing.
    Those coordinates are in a frame no viewer holds, and a cone drawn
    from them would sit plausibly on the WRONG conformer."""
    result = compute_steric_analysis(Chem.MolFromSmiles("c1ccccc1P(c1ccccc1)c1ccccc1"), "u")
    assert result.spatial == ()
    assert result.provenance.parameters["geometry_source"] == "free_ligand_mmff"


def test_the_axes_are_the_exact_directions_the_shadows_were_measured_along():
    from openchem.chem.projection_geometry import shape_descriptors

    mol = _with_conformer("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    result = compute_geometry_analysis(mol, "u")
    assert len(result.spatial) == 1
    axes = result.spatial[0]
    shape = shape_descriptors(mol)
    for declared, measured in zip(axes.axes, shape.principal_axes):
        assert declared == pytest.approx(measured)
    assert axes.extents == pytest.approx(shape.axis_half_spans)
    assert axes.origin == pytest.approx(shape.centroid)
    # Each label names its own shadow radius, index-aligned with the axes.
    for label, radius in zip(axes.labels, shape.projection_radii):
        assert f"{radius:.1f}" in label


# --- renderer: the state machine, against the real page ----------------------


def test_shapes_applied_before_ready_appear_after_the_load(qapp):
    backend = Mol3DViewerBackend()
    mol = _with_conformer("Cl")
    annotation = compute_dipole_moment(mol, "u").spatial[0]
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_shapes([annotation])
    assert _wait_until(qapp, lambda: backend._page_ready, timeout_seconds=PAGE_READY_TIMEOUT_SECONDS)
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) == 1)


def test_a_new_molecule_clears_rendered_shapes(qapp):
    backend = _ready(qapp)
    mol = _with_conformer("Cl")
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_shapes([compute_dipole_moment(mol, "u").spatial[0]])
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) == 1)

    backend.load_conformer(Chem.MolToMolBlock(_with_conformer("CO")))
    assert _wait_until(qapp, lambda: _drawn(qapp, backend) == [])
    assert _run_js(qapp, backend, "JSON.stringify(currentShapes)") in ("null", None)


def test_shapes_pending_from_before_a_load_never_reach_the_new_molecule(qapp):
    """The one deliberate difference from the visualization layer's
    machine: pending shapes belong to the load they were applied for."""
    backend = Mol3DViewerBackend()
    mol_a = _with_conformer("Cl")
    backend.apply_shapes([compute_dipole_moment(mol_a, "u").spatial[0]])  # for A
    backend.load_conformer(Chem.MolToMolBlock(_with_conformer("CO")))  # loads B
    assert _wait_until(qapp, lambda: backend._page_ready, timeout_seconds=PAGE_READY_TIMEOUT_SECONDS)
    _run_js(qapp, backend, "1")  # settle one round-trip
    assert _drawn(qapp, backend) == []


def test_shapes_for_the_inflight_load_survive_it(qapp):
    backend = Mol3DViewerBackend()
    mol = _with_conformer("Cl")
    backend.load_conformer(Chem.MolToMolBlock(mol))  # B's load, in flight
    backend.apply_shapes([compute_dipole_moment(mol, "u").spatial[0]])  # B's shapes
    assert _wait_until(qapp, lambda: backend._page_ready, timeout_seconds=PAGE_READY_TIMEOUT_SECONDS)
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) == 1)


def test_the_rendered_arrow_direction_is_the_vector_and_reverses_with_it(qapp):
    """THE DIRECTION ORACLE, on the drawn endpoints.

    HCl: mu = sum(q*r) points from the delta-minus chlorine toward the
    delta-plus hydrogen. The drawn arrow must run that way -- checked
    against the ATOM POSITIONS, so a producer sign bug and a renderer
    sign bug cannot cancel -- and reversing the annotation's vector must
    reverse the drawn endpoints.
    """
    mol = _with_conformer("Cl")
    molblock = Chem.MolToMolBlock(mol)
    annotation = compute_dipole_moment(mol, "u").spatial[0]

    backend = _ready(qapp)
    backend.load_conformer(molblock)
    backend.apply_shapes([annotation])
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) == 1)
    arrow = _drawn(qapp, backend)[0]

    positions = mol.GetConformer().GetPositions()
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    chlorine, hydrogen = positions[symbols.index("Cl")], positions[symbols.index("H")]
    toward_hydrogen = [h - c for h, c in zip(hydrogen, chlorine)]
    drawn_direction = [e - s for e, s in zip(arrow["end"], arrow["start"])]
    dot = sum(a * b for a, b in zip(toward_hydrogen, drawn_direction))
    assert dot > 0, (
        f"the drawn dipole arrow points away from the hydrogen "
        f"(direction {drawn_direction}); mu = sum(q*r) must point "
        f"delta-minus -> delta-plus, Cl -> H"
    )

    import dataclasses

    flipped = dataclasses.replace(annotation, vector=tuple(-v for v in annotation.vector))
    backend.apply_shapes([flipped])
    assert _wait_until(
        qapp,
        lambda: (d := _drawn(qapp, backend))
        and sum(
            a * b
            for a, b in zip(toward_hydrogen, [e - s for e, s in zip(d[0]["end"], d[0]["start"])])
        )
        < 0,
    ), "reversing the annotation's vector did not reverse the drawn arrow"


def test_the_arrow_length_is_display_scaled_never_the_debye_magnitude(qapp):
    """The vector is in DEBYE; the drawn length is
    max(MIN_ARROW_LENGTH, ARROW_SPAN_FRACTION * longest interatomic span)
    in Angstrom, midpoint on the anchor. Reading the magnitude as
    Angstrom is the units bug the contract forbids."""
    mol = _with_conformer("Cl")
    annotation = compute_dipole_moment(mol, "u").spatial[0]
    backend = _ready(qapp)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_shapes([annotation])
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) == 1)
    arrow = _drawn(qapp, backend)[0]

    positions = mol.GetConformer().GetPositions()
    span = max(
        math.dist(tuple(positions[i]), tuple(positions[j]))
        for i in range(len(positions))
        for j in range(i + 1, len(positions))
    )
    expected = max(MIN_ARROW_LENGTH, ARROW_SPAN_FRACTION * span)
    drawn_length = math.dist(arrow["start"], arrow["end"])
    assert drawn_length == pytest.approx(expected, abs=1e-6)
    midpoint = [(s + e) / 2 for s, e in zip(arrow["start"], arrow["end"])]
    assert midpoint == pytest.approx(list(annotation.anchor), abs=1e-6)


def test_the_cone_wireframe_keeps_its_fixed_convention(qapp):
    """16 generatrices, a closed 32-segment base circle, nothing filled --
    deterministic so screenshots and geometry tests cannot drift."""
    mol = _with_conformer("c1ccccc1P(c1ccccc1)c1ccccc1")
    annotation = compute_steric_analysis(mol, "u").spatial[0]
    backend = _ready(qapp)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_shapes([annotation])
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) > 0)
    drawn = _drawn(qapp, backend)
    assert sum(1 for d in drawn if d["kind"] == "cone-generatrix") == CONE_GENERATRICES
    circle = [d for d in drawn if d["kind"] == "cone-circle"]
    assert len(circle) == CONE_CIRCLE_SEGMENTS
    # Closed: the last segment ends where the first began.
    assert circle[-1]["end"] == pytest.approx(circle[0]["start"], abs=1e-9)
    # Every generatrix has the annotation's slant length, from the apex.
    for generatrix in (d for d in drawn if d["kind"] == "cone-generatrix"):
        assert math.dist(generatrix["start"], generatrix["end"]) == pytest.approx(
            annotation.length, abs=1e-6
        )


def test_all_annotations_of_one_result_render_together(qapp):
    """`spatial` is a tuple and the render path honours it -- without this
    the API is quietly a singleton."""
    mol = _with_conformer("CO")
    arrow = compute_dipole_moment(mol, "u").spatial[0]
    axes = compute_geometry_analysis(mol, "u").spatial[0]
    backend = _ready(qapp)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_shapes([arrow, axes])
    assert _wait_until(
        qapp,
        lambda: {d["kind"] for d in _drawn(qapp, backend)} == {"arrow", "axis"},
    )
    assert sum(1 for d in _drawn(qapp, backend) if d["kind"] == "axis") == 3


def test_a_later_visualization_does_not_strip_the_shape_labels(qapp):
    """3Dmol has ONE label collection and no way to remove a subset, so
    `applyLabels`' `removeAllLabels()` takes the shape captions with it.

    Measured before the fix: applying a visualization after the dipole
    arrow took the page's labels from ["1.58 D"] to ["ATOMLBL"] -- the
    arrow still drawn, its magnitude caption gone. Unreachable from the
    spatial dialog (which applies no visualization) and squarely in the
    way of drawing shapes in the main viewer, which applies them
    routinely.
    """
    from openchem.ui.visualization import VisualizationLayer

    label_texts = (
        "JSON.stringify(viewer.labels.map(function (l) "
        "{ return (l.stylespec && l.stylespec.text) || l.text || ''; }))"
    )
    mol = _with_conformer("CO")
    annotation = compute_dipole_moment(mol, "u").spatial[0]
    backend = _ready(qapp)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    backend.apply_shapes([annotation])
    assert _wait_until(qapp, lambda: len(_drawn(qapp, backend)) == 1)
    assert annotation.label in json.loads(_run_js(qapp, backend, label_texts))

    backend.apply_visualization(
        VisualizationLayer(name="x", atom_colors={0: "#ff0000"}, atom_labels={0: "ATOMLBL"})
    )
    assert _wait_until(
        qapp, lambda: "ATOMLBL" in json.loads(_run_js(qapp, backend, label_texts))
    ), "the atom label never arrived, so this proves nothing about the shape label"
    texts = json.loads(_run_js(qapp, backend, label_texts))
    assert annotation.label in texts, (
        f"the arrow's caption was stripped by the visualization: {texts}"
    )
    # And the arrow itself is still drawn, not merely re-labelled.
    assert len(_drawn(qapp, backend)) == 1


def test_a_lone_atom_has_no_axes_to_declare():
    """`_principal_axes` returns the IDENTITY for fewer than two atoms --
    a placeholder, not a measurement. Drawing it would put three
    meaningless unit axes on a single sphere, so the annotation is
    withheld and the fields stay None."""
    from openchem.chem.projection_geometry import shape_descriptors

    helium = Chem.AddHs(Chem.MolFromSmiles("[He]"))
    AllChem.EmbedMolecule(helium, randomSeed=1)
    shape = shape_descriptors(helium)
    assert shape.principal_axes is None
    assert compute_geometry_analysis(helium, "u").spatial == ()


# --- gallery: per-cell ownership ---------------------------------------------
#
# These drive the grid, which `$3Dmol.createViewerGrid` cannot build under
# Qt's offscreen platform -- see the ladder in
# `tests/test_mol3d_viewer_backend.py`, where every capability underneath
# works and only the grid call throws. They take the shared `grid_display`
# fixture from `tests/conftest.py`, which pairs that admitted platform gate
# with a MEASURED WebGL check so a GPU-less machine skips rather than fails.
# This file used to carry its own private copy of the predicate.


def _drawn_cell(qapp, backend, cell_index):
    raw = _run_js(
        qapp, backend, f"JSON.stringify(drawnGridShapes[{cell_index}] || [])"
    )
    return json.loads(raw) if raw else []


def _sized_backend(qapp) -> Mol3DViewerBackend:
    """A page-ready backend whose widget has a real, settled viewport.

    `drawWhenSized` waits for a real viewport and a grid built into a
    zero-sized box produces no cells, so this follows
    `test_mol3d_viewer_backend.py::_grid_backend` rather than inventing a
    second setup that would drift from it.

    Split out from `_grid_of_two` because the build-race guards below
    need this WITHOUT a grid already up -- the wait is the very thing
    they must not do.
    """
    backend = Mol3DViewerBackend()
    backend.widget().resize(800, 600)
    backend.widget().show()
    assert _wait_until(qapp, lambda: backend._page_ready, timeout_seconds=PAGE_READY_TIMEOUT_SECONDS)
    _wait_until(qapp, lambda: False, timeout_seconds=1.0)
    return backend


def _two_conformers() -> tuple[Chem.Mol, Chem.Mol]:
    return _with_conformer("CO", seed=1), _with_conformer("CO", seed=9)


def _entries(*mols: Chem.Mol) -> list[tuple[str, str]]:
    return [(Chem.MolToMolBlock(mol), str(i + 1)) for i, mol in enumerate(mols)]


def _cells_drawn(qapp, backend) -> object:
    return _run_js(qapp, backend, "document.querySelectorAll('.cell-overlay').length")


def _label_texts(qapp, backend, cell_index: int) -> list[str]:
    """Every 3Dmol label on one cell, by text.

    3Dmol keeps them in one flat collection per viewer, which is the
    whole subject of `test_a_cell_atom_label_is_stripped_by_a_shape_redraw`
    below.
    """
    raw = _run_js(
        qapp,
        backend,
        f"JSON.stringify((gridCells[{cell_index}].labels || [])"
        f".map(function (l) {{ return String(l.text); }}))",
    )
    return json.loads(raw) if raw else []


def _grid_of_two(qapp):
    """A real two-cell grid, sized, shown, and WAITED FOR."""
    backend = _sized_backend(qapp)
    first, second = _two_conformers()
    backend.load_conformer_grid(_entries(first, second), 1, 2)
    assert _wait_until(
        qapp,
        lambda: _cells_drawn(qapp, backend) == 2,
        timeout_seconds=20,
    ), "the gallery never drew its cells"
    return backend, first, second


def test_each_cell_draws_its_own_conformers_annotation(qapp, grid_display):
    backend, first, second = _grid_of_two(qapp)
    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)
    backend.apply_grid_shapes(1, compute_dipole_moment(second, "u").spatial)
    assert _wait_until(
        qapp, lambda: len(_drawn_cell(qapp, backend, 0)) == 1 and len(_drawn_cell(qapp, backend, 1)) == 1
    )
    # Different conformers, so genuinely different geometry -- if the
    # cells shared a payload these would be identical.
    assert _drawn_cell(qapp, backend, 0)[0]["end"] != _drawn_cell(qapp, backend, 1)[0]["end"]


def test_clearing_one_cell_leaves_its_neighbour_drawn(qapp, grid_display):
    """Per-cell ownership: replacing a cell's conformer must not wipe the
    annotations its neighbours are still correctly showing."""
    backend, first, second = _grid_of_two(qapp)
    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)
    backend.apply_grid_shapes(1, compute_dipole_moment(second, "u").spatial)
    assert _wait_until(qapp, lambda: len(_drawn_cell(qapp, backend, 1)) == 1)

    backend.apply_grid_shapes(0, ())
    assert _wait_until(qapp, lambda: _drawn_cell(qapp, backend, 0) == [])
    assert len(_drawn_cell(qapp, backend, 1)) == 1, "clearing cell 0 wiped cell 1"


def test_clear_all_is_the_only_thing_that_empties_every_cell(qapp, grid_display):
    backend, first, second = _grid_of_two(qapp)
    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)
    backend.apply_grid_shapes(1, compute_dipole_moment(second, "u").spatial)
    assert _wait_until(qapp, lambda: len(_drawn_cell(qapp, backend, 0)) == 1)
    backend.clear_all_grid_shapes()
    assert _wait_until(
        qapp, lambda: _drawn_cell(qapp, backend, 0) == [] and _drawn_cell(qapp, backend, 1) == []
    )


def test_clearing_every_cell_takes_the_arrow_CAPTIONS_with_it(qapp, grid_display):
    """The mirror said empty while the screen still showed the numbers.

    `clearAllGridShapes` had its own clearing loop calling
    `removeAllShapes()` and not `removeAllLabels()`, so unticking "Show
    shapes" in the gallery removed every arrow and left "1.14 D" floating
    over a structure with nothing drawn on it. Found by driving the app.

    **THE EXISTING GUARD ABOVE COULD NOT SEE IT**, and that is the lesson
    worth keeping: `_drawn_cell` reads `drawnGridShapes`, the page's own
    mirror, which that function emptied perfectly correctly. A mirror is
    a record of intent; the labels are what is on the screen.
    """
    backend, first, second = _grid_of_two(qapp)
    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)
    backend.apply_grid_shapes(1, compute_dipole_moment(second, "u").spatial)
    assert _wait_until(qapp, lambda: bool(_label_texts(qapp, backend, 0))), (
        "no caption was ever drawn, so its removal proves nothing"
    )

    backend.clear_all_grid_shapes()
    assert _wait_until(qapp, lambda: _drawn_cell(qapp, backend, 0) == [])
    assert _label_texts(qapp, backend, 0) == [], (
        "the arrow was removed and its caption was left behind"
    )
    assert _label_texts(qapp, backend, 1) == [], (
        "cell 1 kept its caption; clear-all reached only some cells"
    )


# --- the grid BUILD, which the three above deliberately wait past -----------
#
# `_grid_of_two` waits for `.cell-overlay` before applying anything, so
# every guard built on it exercises a grid that already exists. The
# window it skips is where the feature actually lives: `loadGrid` resets
# `gridShapes` synchronously and then builds inside `whenGridSized`, which
# polls at 25 ms and wants the height repeated across two frames, while
# the overlay's recompute is ~5 ms. **The answer normally arrives before
# the cells do.** These two hold that window.


def test_a_shape_applied_while_the_grid_is_building_is_still_drawn(qapp, grid_display):
    """THE FIRST RENDER, which is the case the whole replay exists for.

    `drawCellShapes` cannot draw into a cell that does not exist yet, so
    without `loadGrid` replaying what accumulated during the build, the
    first page of a gallery draws nothing at all -- and only some later
    redraw appears to fix it.
    """
    backend = _sized_backend(qapp)
    first, second = _two_conformers()
    backend.load_conformer_grid(_entries(first, second), 1, 2)
    # **NO WAIT HERE, and no `_run_js` either** -- that pumps the event
    # loop, which would let the grid build and quietly turn this into a
    # copy of the tests above. The marker is queued as a fire-and-forget
    # script instead, so it records the page's state in the page's own
    # ordering, and the setup is asserted after the fact.
    backend._page.runJavaScript("window.__cellsWhenApplied = gridCells.length;")
    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)

    assert _wait_until(
        qapp, lambda: len(_drawn_cell(qapp, backend, 0)) == 1, timeout_seconds=20
    ), "a shape applied while the grid was building was never drawn"
    assert _run_js(qapp, backend, "window.__cellsWhenApplied") == 0, (
        "the grid had already been built when the shape was applied, so this "
        "test never entered the window it is named for"
    )


def test_a_shape_queued_against_a_replaced_grid_is_never_drawn(qapp, grid_display):
    """The other half: the replay must not resurrect the previous grid's.

    Two `loadGrid` calls in flight at once leave TWO `whenGridSized`
    polls armed, because each closes over its own state. Without the
    generation counter the older callback still fires, rebuilds the cells
    from ITS conformers, and then replays `gridShapes` -- so a shape
    belonging to a grid the user already left is drawn onto structures it
    does not describe. It corrects itself when the newer callback lands,
    which is not a defence: a plausible picture of the wrong geometry is
    the thing this feature exists to prevent.
    """
    backend = _sized_backend(qapp)
    first, second = _two_conformers()
    backend.load_conformer_grid(_entries(first, second), 1, 2)
    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)
    backend._page.runJavaScript("window.__cellsWhenReplaced = gridCells.length;")
    backend.load_conformer_grid(_entries(second, first), 1, 2)

    assert _wait_until(
        qapp, lambda: _cells_drawn(qapp, backend) == 2, timeout_seconds=20
    ), "the replacement gallery never drew its cells"
    # Long enough for the SUPERSEDED build to fire if it is going to --
    # without this the assertion below could pass simply by looking too
    # early, which is how a race guard becomes decoration.
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)

    assert _run_js(qapp, backend, "window.__cellsWhenReplaced") == 0, (
        "the first grid had already built when it was replaced, so the "
        "superseded-build path was never entered"
    )
    assert _drawn_cell(qapp, backend, 0) == [] and _drawn_cell(qapp, backend, 1) == [], (
        "a shape queued against the grid that was replaced was drawn into the "
        "grid that replaced it"
    )
    # **AND THE SUPERSEDED BUILD NEVER RAN AT ALL.** Two `loadGrid` calls
    # leave two `whenGridSized` polls armed, each closing over its own
    # state, so without the generation guard BOTH build -- the older one
    # first, from its own conformers, replaying whatever `gridShapes`
    # holds by then. It is overtaken microseconds later, which is why the
    # assertions above cannot see it and why this one exists: the cost is
    # a whole `createViewerGrid` (91 ms at 4 cells, 175 ms at 12) for
    # every page somebody paged through.
    assert _run_js(qapp, backend, "gridBuilds") == 1, (
        "the superseded grid was built as well as the one that replaced it"
    )


def test_a_cell_atom_label_is_stripped_by_a_shape_redraw(qapp, grid_display):
    """A LIMITATION TEST. It asserts today's DEFECT, on purpose.

    3Dmol keeps ONE label collection per viewer with no way to remove a
    subset, so `drawCellShapes` clears the lot and puts back only the
    shape captions. The single view has the same constraint and solves
    it -- `applyLabels` redraws the shapes afterwards, and the comment
    there records the measurement that forced it. A gallery cell has no
    equivalent, which is harmless only because nothing gives a cell atom
    labels today.

    **IF GRID ATOM LABELS ARE EVER IMPLEMENTED, RETIRE THIS TEST** and
    put a restoration test in its place. Do NOT relax the assertion to
    make it pass: red here means labels were given to cells without a way
    back, which is exactly what it is watching for. Same idiom as
    `test_open_babel_really_does_lose_an_uppercase_symbol_without_the_fix`.
    """
    backend, first, _second = _grid_of_two(qapp)
    _run_js(
        qapp,
        backend,
        "gridCells[0].addLabel('ATOMLBL', {position: {x: 0, y: 0, z: 0}});"
        "gridCells[0].render(); 1",
    )
    assert _label_texts(qapp, backend, 0) == ["ATOMLBL"], (
        "the marker label was never added, so this test cannot observe its loss"
    )

    backend.apply_grid_shapes(0, compute_dipole_moment(first, "u").spatial)
    assert _wait_until(qapp, lambda: len(_drawn_cell(qapp, backend, 0)) == 1)

    texts = _label_texts(qapp, backend, 0)
    assert "ATOMLBL" not in texts, (
        "a cell kept its atom label through a shape redraw -- if a restore "
        "path was added, retire this test rather than weakening it"
    )
    assert texts, (
        "the shape's OWN caption was lost too, which is a different and worse "
        "bug than the one this test documents"
    )
