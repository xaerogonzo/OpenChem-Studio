"""Molecular shape from the van der Waals surface: volume, area, extent.

The descriptors the reference editor's Geometry plugin reports beside its
energies -- van der Waals volume, minimal and maximal projection area and
radius -- and the ones a chemist reaches for when asking "will this fit".

**Every number here is validated against a case with a known answer.**
The reference editor's own figures cannot serve: we do not have its conformer, and
asserting against numbers from a different geometry is the "fixture typed
from memory" trap this project has already paid for once. So the
references are analytic -- one atom is a sphere, so its volume is
4/3 pi r^3, its surface 4 pi r^2 and its shadow a circle of pi r^2.

## THE RADII, AND WHY THE VOLUME IS NOT RDKIT'S ROUTINE ANY MORE (method v3, 2026-10-11)

The radii are Bondi's own list, extended by Mantina et al. for the elements he gave none for, and RDKit's table only for
what neither covers (`chem/vdw_radii.py`; `docs/VDW_RADII_ASSESSMENT.md`). `DoubleCubicLatticeVolume` and
`ComputeMolVolume` take no radii, so they cannot be told to use that list, and the volume is now `sasa.enclosed_volume`
(the divergence theorem over the same surface points the areas use) with `sasa.grid_volume` as the independent check.
Measured on six molecules against a 0.03 angstrom grid: the new volume within 0.25%, DCLV within 1.2%. The analysis below
is why DCLV was chosen in the first place and is kept because it is why the probe radius must be passed explicitly there.

## Which routine WAS authoritative, and why it was not the obvious one

RDKit has two, and the plan named the wrong one as primary. Measured on a
single helium atom against the analytic 11.4940 A^3:

    DoubleCubicLatticeVolume(probeRadius=0.0)   11.4940     exact
    ComputeMolVolume(gridSpacing=0.2)           10.9200     -4.99%
    ComputeMolVolume(gridSpacing=0.1)           11.4590     -0.30%   0.11 s
    ComputeMolVolume(gridSpacing=0.05)          11.4889     -0.04%   0.89 s

DCLV is ANALYTIC -- it agrees to four decimals and returns instantly --
while `ComputeMolVolume` counts grid points and pays for accuracy in
seconds. So DCLV is the answer and `ComputeMolVolume` is the independent
cross-check, which is the reverse of the obvious reading of their names.

**`DoubleCubicLatticeVolume` DEFAULTS TO A 1.4 A SOLVENT PROBE**, and
that is the trap worth knowing. Left at its default it returns 91.95 for
helium -- the volume of a sphere of radius 1.4 + 1.4 -- which is a
solvent-accessible volume, not a van der Waals one. It is a 700% error
that looks like a plausible number for a bigger molecule. `probeRadius=0`
is not a tuning knob here; it is the difference between two different
quantities.

The probe volume is genuinely wanted too, so it is computed deliberately
and reported under its own name rather than being confused for this one.

## What is searched, said plainly

The minimal and maximal projection are found by SEARCHING the orientations
(`projection_search`): the area at each is exact, and the extreme is the best
of a sampling of the sphere refined locally. An earlier version measured on
the three principal planes and called the smaller "minimal", which read
slightly high -- benzene 20.07 A^2 there, 18.76 A^2 searched. The principal
axes are still computed, because the drawn axes on the 3D view are the
principal ones, but no reported extreme comes from them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from rdkit import Chem

from openchem.chem.projection_search import projection_at, projection_extremes
from openchem.chem.sasa import accessible_areas, enclosed_volume, grid_volume
from openchem.chem.vdw_radii import bondi_radius

#: The conventional water probe, in Angstrom. Used ONLY for the
#: deliberately solvent-accessible figures.
_SOLVENT_PROBE = 1.4

#: How far the two volume routines may differ before the disagreement is
#: worth reporting. Measured across ten molecules, the grid routine's own
#: error is worst where the surface-to-volume ratio is highest:
#:
#:      He           4.99%      ethanol       1.53%
#:      water        1.19%      naphthalene   1.45%
#:      methane      0.43%      aspirin       0.52%
#:
#: So 3% clears every BONDED molecule by better than 2x. A lone atom can
#: exceed it -- the grid check is weakest precisely where the analytic
#: answer is most certain, since a single sphere is the one case with an
#: exact closed form. That is a limitation of the check, not of the value.
_VOLUME_TOLERANCE = 0.03


class NoConformerError(ValueError):
    """Raised when a shape calculation is attempted with no 3D geometry."""


@dataclass(frozen=True)
class ShapeDescriptors:
    """What can honestly be said about a conformer's shape.

    `volume_disagreement` is carried rather than hidden. Two independent
    routines computing the same quantity is a free check, and when they
    part company the reader should be told instead of being handed
    whichever one happened to run last.
    """

    volume: float
    surface_area: float
    solvent_accessible_volume: float
    solvent_accessible_surface_area: float
    #: Relative difference between the analytic and grid volumes.
    volume_disagreement: float
    min_projection_area: float
    max_projection_area: float
    #: Radius of the smallest circle enclosing the shadow at that orientation.
    min_projection_radius: float
    max_projection_radius: float
    #: The viewing directions the extremes were found along (unit vectors, the conformer's
    #: frame; the sign is arbitrary because a shadow is the same from both sides) and the
    #: extent of the molecule along each, surface to surface.
    min_projection_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    max_projection_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    min_projection_size: float = 0.0
    max_projection_size: float = 0.0
    #: How many orientations the search computed an area for.
    orientations_searched: int = 0
    #: The multiplier the van der Waals radii carried in the projection figures.
    radius_scale: float = 1.0
    #: The drawing half: the exact signed principal axes the projections
    #: above were measured along (widest atom spread first), the unweighted
    #: centroid they pass through, the half-span of atom centres along
    #: each, and each axis's own shadow radius, index-aligned with the
    #: axes. **Taken from the same arrays the numbers came from, never
    #: re-derived by a consumer**: an eigenvector's sign is arbitrary, so
    #: recomputing could flip a drawn direction while every reported
    #: number stayed identical. `None` when fewer than two atoms exist and
    #: the axes would be the identity placeholder rather than a
    #: measurement.
    centroid: tuple[float, float, float] | None = None
    principal_axes: tuple[tuple[float, float, float], ...] | None = None
    axis_half_spans: tuple[float, ...] | None = None
    projection_radii: tuple[float, ...] | None = None

    @property
    def volumes_agree(self) -> bool:
        return self.volume_disagreement <= _VOLUME_TOLERANCE


def _positions_and_radii(mol: Chem.Mol, conformer_id: int = -1):
    if mol.GetNumConformers() == 0:
        raise NoConformerError(
            "This calculation needs a 3D conformer. Generate one with "
            "Structure ▸ Generate Conformers... first."
        )
    conformer = mol.GetConformer(conformer_id)
    if not conformer.Is3D():
        raise NoConformerError(
            "The available conformer is 2D, which has no shape to measure. "
            "Generate a real 3D conformer with Structure ▸ Generate Conformers...."
        )
    positions = np.array(conformer.GetPositions(), dtype=float)
    radii = np.array([bondi_radius(atom.GetAtomicNum()) for atom in mol.GetAtoms()], dtype=float)
    return positions, radii


#: Below this, in Angstrom, two atoms of different fragments are closer
#: than any real contact -- H-H is 0.74 -- so they are interpenetrating.
#: The same threshold `estimate_led_cost_for` refuses on, and for the same
#: reason.
_FRAGMENT_CONTACT_FLOOR = 0.7


def closest_fragment_approach(mol: Chem.Mol, conformer_id: int = -1) -> float | None:
    """Nearest distance between atoms of two different fragments, or None.

    **`EmbedMolecule` does not separate disconnected fragments**, which is
    recorded in this project's notes as an error that produced a
    +40000 kcal/mol interaction energy nobody flagged. It bites shape just
    as hard and much more quietly: with two fragments packed at the origin
    their spheres fuse, and the volume comes out far too SMALL. Measured on
    conformers straight from the embedder:

        water dimer   21% of the volume lost
        NaCl          30%
        NH3 + BH3     44%

    A wrong number that is merely smaller is exactly the kind that gets
    believed, so the caller is told rather than the value being suppressed
    -- a real crystal contact is legitimately short, and refusing outright
    would be wrong for it.
    """
    fragments = Chem.GetMolFrags(mol)
    if len(fragments) < 2:
        return None
    positions = np.array(mol.GetConformer(conformer_id).GetPositions(), dtype=float)
    best = math.inf
    for index, fragment in enumerate(fragments):
        others = [i for group in fragments[index + 1 :] for i in group]
        if not others:
            continue
        deltas = positions[list(fragment)][:, None, :] - positions[others][None, :, :]
        best = min(best, float(np.sqrt((deltas**2).sum(axis=2)).min()))
    return None if best is math.inf else best


def van_der_waals_volume(mol: Chem.Mol, conformer_id: int = -1) -> tuple[float, float]:
    """The volume enclosed by the fused vdW spheres, and the disagreement.

    Returns `(volume, relative_disagreement)`. The volume is the divergence-theorem
    one over the surface points; the disagreement is how far the independent grid
    count landed from it, as a fraction. A disagreement above `_VOLUME_TOLERANCE` means
    something is wrong with the geometry, not with the caller.
    """
    positions, radii = _positions_and_radii(mol, conformer_id)  # raises if there is no 3D geometry
    volume = enclosed_volume(positions, radii)
    if volume <= 0:
        return volume, 0.0
    return volume, abs(grid_volume(positions, radii) - volume) / volume


def van_der_waals_surface_area(mol: Chem.Mol, conformer_id: int = -1) -> float:
    """The area of the surface of the fused van der Waals spheres, in A^2.

    The area partner of `van_der_waals_volume`, with the same radii, computed by `chem/sasa` at
    probe 0. **NOT the double-cubic-lattice surface**: that is a lattice method, 1.1% high for
    benzene and ethanol at probe 0 and 4.5% high at a 1.4 A probe (measured 2026-10-10 against a
    200,000-point reference), and this application should have one surface routine, not two that
    disagree. A lone sphere gives 4 pi r^2 exactly.
    """
    positions, radii = _positions_and_radii(mol, conformer_id)
    return float(accessible_areas(positions, radii, 0.0).sum())


def _principal_axes(positions: np.ndarray) -> np.ndarray:
    """The three principal axes of the atom cloud, widest spread first.

    Deliberately UNWEIGHTED by mass: this is about the shape a molecule
    presents, not where its mass sits, and a single bromine would
    otherwise drag the axes towards itself and rotate a projection that
    has nothing to do with mass.
    """
    if len(positions) < 2:
        return np.eye(3)
    centred = positions - positions.mean(axis=0)
    # The epsilon keeps a planar or linear molecule from producing a
    # singular covariance, where the eigenvectors are arbitrary.
    _values, vectors = np.linalg.eigh(np.cov(centred.T) + np.eye(3) * 1e-12)
    return vectors.T[::-1]


def shape_descriptors(
    mol: Chem.Mol, conformer_id: int = -1, radius_scale: float = 1.0
) -> ShapeDescriptors:
    """Volume, surface, and the projection extremes over every orientation.

    `radius_scale` multiplies the van der Waals radii in the PROJECTION figures only (area,
    radius, size). The volume and surface are those of the unscaled radii: they are different
    quantities, and a caller asking for a bigger shadow has not asked for a bigger molecule.
    """
    if not radius_scale > 0:
        raise ValueError(f"The radius scale must be positive, got {radius_scale!r}.")
    positions, radii = _positions_and_radii(mol, conformer_id)
    volume, disagreement = van_der_waals_volume(mol, conformer_id)

    # The solvent-accessible VOLUME is the same routine with the probe on; the SURFACES are `chem/sasa`'s too.
    solvated = enclosed_volume(positions, radii, _SOLVENT_PROBE)

    axes = _principal_axes(positions)
    scaled = radii * radius_scale
    along_axes = [projection_at(positions, scaled, axis) for axis in axes]
    extremes = projection_extremes(positions, scaled)
    # The drawing half, from the SAME arrays the numbers above came from.
    # `positions.mean` is the identical centring `_principal_axes` used,
    # so the drawn axes pass through the point the measurement pivoted on.
    if len(positions) >= 2:
        centroid = positions.mean(axis=0)
        centred = positions - centroid
        spatial = {
            "centroid": tuple(float(v) for v in centroid),
            "principal_axes": tuple(tuple(float(v) for v in axis) for axis in axes),
            "axis_half_spans": tuple(float(np.abs(centred @ axis).max()) for axis in axes),
            "projection_radii": tuple(float(shadow.radius) for shadow in along_axes),
        }
    else:
        spatial = {}
    return ShapeDescriptors(
        volume=volume,
        surface_area=float(accessible_areas(positions, radii, 0.0).sum()),
        solvent_accessible_volume=float(solvated),
        solvent_accessible_surface_area=float(accessible_areas(positions, radii, _SOLVENT_PROBE).sum()),
        volume_disagreement=disagreement,
        min_projection_area=extremes.minimum.area,
        max_projection_area=extremes.maximum.area,
        min_projection_radius=extremes.minimum.radius,
        max_projection_radius=extremes.maximum.radius,
        min_projection_direction=extremes.minimum.direction,
        max_projection_direction=extremes.maximum.direction,
        min_projection_size=extremes.minimum.size,
        max_projection_size=extremes.maximum.size,
        orientations_searched=extremes.orientations,
        radius_scale=float(radius_scale),
        **spatial,
    )
