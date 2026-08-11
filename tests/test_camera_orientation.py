"""The camera-to-coordinates rotation, and the ways it can be plausibly wrong.

"Use in 2D Editor" hands the drawing the conformer *as oriented on screen*,
so a rotation matrix derived from the viewer's camera gets baked into
coordinates. Every failure available here produces output that looks
completely reasonable:

- baking the camera's ZOOM in rescales the molecule
- baking its PAN in displaces it
- a mirrored matrix preserves every interatomic distance, so nothing
  measuring geometry can see it
- the inverse rotation is a perfectly good rotation, just not the one on
  screen

**The point set is deliberately asymmetric.** A symmetric one makes a
reflected or inverted transform look correct, which is the whole reason a
tetrahedron of unrelated points is used rather than a molecule.
"""

from __future__ import annotations

import math

import pytest

from openchem.chem.camera_orientation import (
    IDENTITY,
    VIEW_LENGTH,
    camera_to_model_transform,
    determinant,
    rotate,
)

#: No symmetry, no coplanarity, no repeated distances.
ASYMMETRIC = [(0.0, 0.0, 0.0), (1.0, 2.0, 0.0), (-1.0, 0.0, 3.0), (2.0, -1.0, 1.0)]

_HALF = math.sqrt(0.5)
#: 90 degrees about +y, as a half-angle quaternion in (x, y, z, w) order.
ABOUT_Y_90 = [0.0, 0.0, 0.0, 0.0, 0.0, _HALF, 0.0, _HALF]
#: The same rotation seen from a panned, zoomed camera.
ABOUT_Y_90_ZOOMED = [11.0, -4.0, 2.5, 137.0, 0.0, _HALF, 0.0, _HALF]


def _signed_volume(points) -> float:
    """Positive or negative according to handedness; unchanged by any
    proper rotation, sign-flipped by any reflection."""
    o, a, b, c = points[:4]
    u = tuple(a[i] - o[i] for i in range(3))
    v = tuple(b[i] - o[i] for i in range(3))
    w = tuple(c[i] - o[i] for i in range(3))
    cross = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    return sum(cross[i] * w[i] for i in range(3))


# --- handedness --------------------------------------------------------------


@pytest.mark.parametrize(
    "view",
    [
        pytest.param(ABOUT_Y_90, id="90 about y"),
        pytest.param([0.0] * 4 + [0.5, 0.5, 0.5, 0.5], id="120 about the diagonal"),
        pytest.param([0.0] * 4 + [0.183, -0.365, 0.548, 0.730], id="an arbitrary one"),
    ],
)
def test_the_transform_is_a_proper_rotation(view):
    """`det(R) = +1`. A reflection has -1 and is otherwise indistinguishable
    from a rotation by anything that measures distances."""
    assert determinant(camera_to_model_transform(view)) == pytest.approx(1.0, abs=1e-9)


def test_chirality_survives_the_transform(qapp=None):
    """The same guarantee stated on the points rather than the matrix,
    because that is what actually reaches a molecule.

    CIP labels are NOT a sufficient check for this -- a mirror can leave
    particular assignments intact -- which is why the invariant is signed
    volume.
    """
    before = _signed_volume(ASYMMETRIC)

    after = _signed_volume(rotate(ASYMMETRIC, camera_to_model_transform(ABOUT_Y_90)))

    assert before * after > 0
    assert after == pytest.approx(before, rel=1e-9)


# --- only the orientation may reach the coordinates --------------------------


def test_zoom_and_pan_cannot_reach_the_coordinates():
    """THE SILENT CORRUPTION THIS MODULE EXISTS TO PREVENT.

    The zoom and the pan sit in the same array as the orientation. Using
    either would rescale or displace the structure -- producing a molecule
    that is still recognisably itself and no longer the right size or in
    the right place.
    """
    plain = rotate(ASYMMETRIC, camera_to_model_transform(ABOUT_Y_90))
    zoomed = rotate(ASYMMETRIC, camera_to_model_transform(ABOUT_Y_90_ZOOMED))

    for a, b in zip(plain, zoomed):
        assert a == pytest.approx(b, abs=1e-12)


def test_the_transform_preserves_every_distance():
    """A rotation is rigid. Necessary but NOT sufficient -- a reflection
    passes this too, which is what the handedness tests are for."""
    matrix = camera_to_model_transform(ABOUT_Y_90)
    turned = rotate(ASYMMETRIC, matrix)

    for i in range(len(ASYMMETRIC)):
        for j in range(i + 1, len(ASYMMETRIC)):
            assert math.dist(turned[i], turned[j]) == pytest.approx(
                math.dist(ASYMMETRIC[i], ASYMMETRIC[j]), abs=1e-9
            )


def test_a_rotation_actually_rotates():
    """The obvious thing, asserted so the invariants above cannot all be
    satisfied by returning the identity -- which is rigid, proper, and
    entirely zoom-independent."""
    matrix = camera_to_model_transform(ABOUT_Y_90)

    # 90 degrees about +y sends +x to -z and +z to +x.
    assert rotate([(1.0, 0.0, 0.0)], matrix)[0] == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
    assert rotate([(0.0, 0.0, 1.0)], matrix)[0] == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)


def test_two_quarter_turns_make_a_half_turn():
    """Composition, which pins the ANGLE as well as the axis -- a matrix
    built from the half-angle used as a full angle would still rotate about
    y, still be proper, and still be rigid."""
    quarter = camera_to_model_transform(ABOUT_Y_90)
    half = camera_to_model_transform([0.0] * 4 + [0.0, 1.0, 0.0, 0.0])

    once = rotate(ASYMMETRIC, quarter)
    twice = rotate(once, quarter)

    for a, b in zip(twice, rotate(ASYMMETRIC, half)):
        assert a == pytest.approx(b, abs=1e-9)


# --- it declines rather than guessing ----------------------------------------


@pytest.mark.parametrize(
    "view",
    [
        pytest.param(None, id="no view at all"),
        pytest.param([], id="empty"),
        pytest.param([0.0] * (VIEW_LENGTH - 1), id="too short"),
        pytest.param([0.0] * VIEW_LENGTH, id="the all-zero quaternion 3Dmol reports pre-draw"),
    ],
)
def test_an_unusable_view_gives_the_identity(view):
    """Drawing the structure unrotated is a sane answer; refusing would
    mean the button did nothing, which is the failure this whole line of
    work keeps finding."""
    assert camera_to_model_transform(view) == IDENTITY


def test_an_unnormalised_quaternion_is_normalised_rather_than_refused():
    """Floating point drift over many rotations leaves the norm slightly
    off 1, and a matrix built from an unnormalised quaternion silently
    scales -- exactly the corruption this module is about."""
    scaled = [0.0] * 4 + [value * 3.0 for value in ABOUT_Y_90[4:]]

    assert determinant(camera_to_model_transform(scaled)) == pytest.approx(1.0, abs=1e-9)
    for a, b in zip(
        rotate(ASYMMETRIC, camera_to_model_transform(scaled)),
        rotate(ASYMMETRIC, camera_to_model_transform(ABOUT_Y_90)),
    ):
        assert a == pytest.approx(b, abs=1e-9)


# --- the direction, MEASURED against the real bundle -------------------------


def _viewer_showing_aspirin(qapp):
    """A real 3Dmol viewer with a rigid, asymmetric molecule on screen."""
    import time

    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

    def wait(predicate, seconds: float = 20) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            qapp.processEvents()
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def run_js(script, seconds: float = 8):
        out: dict[str, object] = {}
        backend._page.runJavaScript(script, lambda v: out.__setitem__("v", v))
        wait(lambda: "v" in out, seconds)
        return out.get("v")

    backend = Mol3DViewerBackend()
    # Sized and shown: `drawWhenSized` waits for a real viewport, so an
    # unshown view never draws and `modelToScreen` has nothing to project
    # onto.
    backend.widget().resize(600, 500)
    backend.widget().show()
    assert wait(lambda: backend._page_ready)

    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)
    mol = Chem.RemoveHs(mol)
    backend.load_conformer(Chem.MolToMolBlock(mol))
    assert wait(lambda: run_js("(typeof viewer !== 'undefined') ? 1 : 0") == 1)
    wait(lambda: False, 2.0)

    conformer = mol.GetConformer()
    points = [
        (conformer.GetAtomPosition(i).x,
         conformer.GetAtomPosition(i).y,
         conformer.GetAtomPosition(i).z)
        for i in range(mol.GetNumAtoms())
    ]
    return backend, run_js, points


def _screen_agreement(screen, candidate) -> float:
    """How well a candidate's x,y matches where atoms really are drawn.

    Compared as the direction of the displacement between successive
    atoms, which cancels the unknown zoom and pan. Screen y grows
    DOWNWARD, hence the flip.
    """
    total = count = 0.0
    for i in range(len(candidate) - 1):
        j = i + 1
        sx = screen[j][0] - screen[i][0]
        sy = -(screen[j][1] - screen[i][1])
        cx = candidate[j][0] - candidate[i][0]
        cy = candidate[j][1] - candidate[i][1]
        ns, nc = math.hypot(sx, sy), math.hypot(cx, cy)
        if ns < 1e-6 or nc < 1e-6:
            continue
        total += (sx * cx + sy * cy) / (ns * nc)
        count += 1
    return total / count if count else 0.0


@pytest.mark.parametrize(
    "degrees,axis",
    [
        pytest.param(70, "y", id="about y"),
        pytest.param(40, "x", id="about x"),
        pytest.param(55, "z", id="about z"),
    ],
)
def test_the_matrix_matches_where_atoms_are_actually_drawn(qapp, degrees, axis):
    """**THE DIRECTION IS MEASURED, AND THE OBVIOUS ORACLE IS WRONG.**

    `camera_to_model_transform` claims `matrix @ point` gives the point as
    the camera sees it. Its transpose is an equally valid rotation --
    proper, rigid, chirality-preserving -- so every other test in this file
    passes against it, and only the page can tell them apart.

    The first attempt asked 3Dmol to apply the quaternion itself, via
    `$3Dmol.Vector3.applyQuaternion`. **That disagreed**, and it is the
    oracle that is wrong: for `q = (0, sin35, 0, cos35)` it returns the
    -70 degree rotation where the standard convention gives +70. Reading
    an API's semantics was exactly what the coordinate-frame contract says
    not to do.

    So this asks where the atoms are actually DRAWN, through
    `modelToScreen`. Measured, matrix against transpose:

        70 deg about y    +0.9989   vs   +0.5441
        40 deg about x    +0.9994   vs   +0.6598
        55 deg about z    +0.9993   vs   -0.3351

    Compared by direction rather than position, so the zoom and pan
    cancel. The threshold is loose rather than exact because
    `modelToScreen` includes the perspective divide, which distorts a pure
    rotation for atoms at different depths.

    Each case gets a FRESH viewer. An earlier version rotated one viewer
    through all three in turn and scored 0.83 on the x case, because the
    rotations composed -- a measurement of something nobody was asking
    about.
    """
    import json

    backend, run_js, points = _viewer_showing_aspirin(qapp)
    run_js(f"viewer.rotate({degrees}, '{axis}'); viewer.render(); 1")

    view = json.loads(run_js("JSON.stringify(viewer.getView())"))
    screen = json.loads(run_js("""
      JSON.stringify(viewer.getModel().selectedAtoms({}).map(function(a){
        var s = viewer.modelToScreen({x: a.x, y: a.y, z: a.z});
        return [s.x, s.y];
      }))
    """, seconds=12))

    matrix = camera_to_model_transform(view)
    ours = _screen_agreement(screen, rotate(points, matrix))
    transposed = _screen_agreement(screen, rotate(points, tuple(zip(*matrix))))

    print(f"\n  {degrees} about {axis}: matrix {ours:+.4f}  transpose {transposed:+.4f}")

    assert ours > 0.8, f"the matrix does not describe what is on screen ({ours:+.4f})"
    assert ours > transposed + 0.3, (
        f"matrix {ours:+.4f} and transpose {transposed:+.4f} are too close to "
        f"tell apart; this rotation cannot settle the direction"
    )


# --- the editor's drag angles ------------------------------------------------


def test_the_drag_rotation_is_proper_and_rigid():
    """Same guarantees as the camera transform, on the other entry point.
    A reflection here would mirror the molecule in the editor."""
    from openchem.chem.camera_orientation import rotation_from_degrees

    for x, y in [(0, 0), (45, 0), (0, 45), (45, 45), (-30, 120), (17, -160)]:
        matrix = rotation_from_degrees(x, y)
        assert determinant(matrix) == pytest.approx(1.0, abs=1e-9), (x, y)
        turned = rotate(ASYMMETRIC, matrix)
        for i in range(len(ASYMMETRIC)):
            for j in range(i + 1, len(ASYMMETRIC)):
                assert math.dist(turned[i], turned[j]) == pytest.approx(
                    math.dist(ASYMMETRIC[i], ASYMMETRIC[j]), abs=1e-9
                )


def test_no_drag_is_the_identity():
    """So entering the mode and letting go changes nothing at all --
    which is what makes a zero-distance drag a zero-step operation."""
    from openchem.chem.camera_orientation import rotation_from_degrees

    assert rotate(ASYMMETRIC, rotation_from_degrees(0.0, 0.0)) == pytest.approx(
        [pytest.approx(point) for point in ASYMMETRIC]
    )


def test_the_composition_order_is_x_then_y_and_it_MATTERS():
    """**BOTH ORDERS ARE PROPER ROTATIONS AND THEY DIFFER.**

    45 degrees about x then 45 about y does not land where the reverse
    does, and either feels natural until somebody tries it. The order is
    documented in `rotation_from_degrees` and pinned here, on an
    asymmetric fixture so the two cannot coincide by symmetry.
    """
    from openchem.chem.camera_orientation import (
        _about_x,
        _about_y,
        _multiply,
        rotation_from_degrees,
    )

    combined = rotation_from_degrees(45, 45)
    x_then_y = _multiply(_about_x(math.radians(45)), _about_y(math.radians(45)))
    y_then_x = _multiply(_about_y(math.radians(45)), _about_x(math.radians(45)))

    assert rotate(ASYMMETRIC, combined) == pytest.approx(
        [pytest.approx(p) for p in rotate(ASYMMETRIC, x_then_y)]
    )
    # The guard that makes the assertion above mean something: if the two
    # orders agreed, pinning one would be pinning nothing.
    assert rotate(ASYMMETRIC, x_then_y)[1] != pytest.approx(
        rotate(ASYMMETRIC, y_then_x)[1], abs=1e-6
    )


def test_a_horizontal_drag_spins_and_a_vertical_drag_tips():
    """Which angle drives which axis, asserted so a transposition cannot
    hide -- it would still be a proper, rigid rotation."""
    from openchem.chem.camera_orientation import rotation_from_degrees

    # About y (a horizontal drag): +x goes towards -z, y is untouched.
    spun = rotate([(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], rotation_from_degrees(0, 90))
    assert spun[0] == pytest.approx((0.0, 0.0, -1.0), abs=1e-9)
    assert spun[1] == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)

    # About x (a vertical drag): +y goes towards +z, x is untouched.
    tipped = rotate([(0.0, 1.0, 0.0), (1.0, 0.0, 0.0)], rotation_from_degrees(90, 0))
    assert tipped[0] == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert tipped[1] == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)
