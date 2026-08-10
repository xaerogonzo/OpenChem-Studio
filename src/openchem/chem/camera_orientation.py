"""The rotation a 3D viewer camera applies, as a matrix.

Used to hand the 2D editor the conformer *as it is currently oriented on
screen* -- so the drawing is a projection of the geometry the user arranged,
which is what MarvinSketch does when it draws buckminsterfullerene in
perspective inside a 2D editor.

**THE COORDINATE-FRAME CONTRACT**, written down because six frames are in
play (raw ETKDG, display-aligned, viewer world, camera, adopted, Ketcher)
and the failure mode is a transform that looks entirely plausible while
being mathematically backwards:

- Units are Angstrom throughout. **Nothing here rescales**, which is why
  the camera's zoom and position are read and discarded rather than never
  read: they are present in the same array and the temptation is to use
  them.
- Molfile coordinates are right-handed and every transform here is a
  PROPER rotation. `determinant` is asserted to be +1 rather than assumed,
  because a reflection preserves every interatomic distance and so hides
  from any distance-based check.
- **The direction is model -> view.** `matrix @ model_point` gives the
  point as the camera sees it, so applying it to a molecule's coordinates
  bakes in the orientation on screen.

**THAT DIRECTION IS MEASURED, AND THE OBVIOUS ORACLE IS WRONG.** The first
check asked 3Dmol to apply the quaternion itself, through
`$3Dmol.Vector3.applyQuaternion`, and it disagreed -- for
`q = (0, sin35, 0, cos35)` that method returns the -70 degree rotation
where the standard convention gives +70. It is the oracle that is wrong,
and reading an API's semantics is exactly what this contract says not to
do. Settled instead against where atoms are really drawn, via
`modelToScreen`, agreement of this matrix against its transpose:

    70 deg about y    +0.9989   vs   +0.5441
    40 deg about x    +0.9994   vs   +0.6598
    55 deg about z    +0.9993   vs   -0.3351

`tests/test_camera_orientation.py` keeps that measurement.

No RDKit here: this is arithmetic on numbers, and keeping it that way is
what lets it be tested without a molecule or a Qt event loop.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: What `viewer.getView()` returns:
#:
#:     [0..2]  model group position -- where the scene has been panned to
#:     [3]     rotation group z     -- the zoom
#:     [4..7]  rotation quaternion  -- x, y, z, w
#:
#: Confirmed against the real vendored bundle: rotating the viewer 70
#: degrees about y gave `[0, 0, 0, 0, 0, 0.574, 0, 0.819]`, and
#: sin(35 deg) = 0.5736 with cos(35 deg) = 0.8192 -- a half-angle
#: quaternion in (x, y, z, w) order, with the first four entries untouched
#: by a pure rotation.
VIEW_LENGTH = 8
_QUATERNION_SLICE = slice(4, 8)

#: A quaternion shorter than this is not a rotation at all -- 3Dmol reports
#: all-zero before the first draw. Identity is the honest answer there.
_MIN_NORM = 1e-9

Matrix3 = tuple[tuple[float, float, float], ...]

IDENTITY: Matrix3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def camera_to_model_transform(view: Sequence[float] | None) -> Matrix3:
    """The rotation matrix for a 3Dmol `getView()` array.

    **Only the orientation is read.** The camera's pan and zoom are in the
    same array and mean nothing about the molecule's shape; baking either
    into coordinates would rescale or displace the structure while leaving
    it looking entirely reasonable. `view[0:4]` is deliberately never
    touched, and a test asserts that two views differing only in those
    entries produce identical output.

    Returns the identity for anything unusable -- a missing view, a wrong
    length, or the all-zero quaternion 3Dmol reports before its first
    draw -- because "draw it unrotated" is a sane structure and refusing
    would mean the button did nothing.
    """
    if view is None or len(view) != VIEW_LENGTH:
        return IDENTITY
    x, y, z, w = (float(value) for value in view[_QUATERNION_SLICE])
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < _MIN_NORM:
        return IDENTITY
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    # The standard quaternion-to-matrix form for v' = R v, matching what
    # THREE.js's applyQuaternion does -- and 3Dmol's vector math is
    # derived from THREE.js. Verified against the live page rather than
    # taken on trust.
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def determinant(matrix: Matrix3) -> float:
    """+1 for a proper rotation, -1 for one with a reflection in it.

    Exposed rather than kept private because it is the only cheap check
    that catches a mirrored transform: reflections preserve every
    interatomic distance, so nothing measuring geometry can see one.
    """
    (a, b, c), (d, e, f), (g, h, i) = matrix
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def rotate(
    points: Sequence[Sequence[float]], matrix: Matrix3
) -> list[tuple[float, float, float]]:
    """Apply `matrix` to each (x, y, z), returning new points.

    About the ORIGIN, not about the molecule's centroid: the caller decides
    what the origin means. For a conformer the centroid is the natural
    choice and the caller centres first -- doing it here would silently
    translate structures whose position the caller cared about.
    """
    return [
        (
            matrix[0][0] * p[0] + matrix[0][1] * p[1] + matrix[0][2] * p[2],
            matrix[1][0] * p[0] + matrix[1][1] * p[1] + matrix[1][2] * p[2],
            matrix[2][0] * p[0] + matrix[2][1] * p[1] + matrix[2][2] * p[2],
        )
        for p in points
    ]
