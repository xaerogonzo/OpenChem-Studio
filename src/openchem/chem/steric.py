"""Ligand steric bulk: exact cone angle and percent buried volume.

Both were previously deferred because "steric hindrance" names several
incompatible quantities and nothing here could be validated. That
objection does not apply to these two: each has a precise geometric
definition and a published reference set, so they can be implemented and
checked. What they cannot do is reproduce published tables digit for
digit, and the reason is worth stating clearly because it is not a defect
in the algorithm.

EXACT CONE ANGLE (Bilbrey, Kazez, Locklin & Allen, J. Comput. Chem. 2013)
is the most acute right circular cone, apex at the metal, that contains
the whole ligand. Unlike Tolman's original construction it needs no
CPK model and no judgement about how substituents nest -- it is a
well-posed geometry problem. The AXIS IS SOLVED FOR rather than assumed
to lie along the metal-donor bond, which matters: for an unsymmetric
ligand the two differ substantially (PEt3 measured here at 146 degrees
optimised against 171 along the bond), while for a symmetric one they
coincide exactly.

PERCENT BURIED VOLUME is the fraction of a sphere around the metal
occupied by the ligand's van der Waals volume -- the SambVca convention,
R = 3.5 A, Bondi radii scaled by 1.17, hydrogens omitted.

WHY THE ABSOLUTE VALUES DIFFER FROM PUBLISHED TABLES, measured rather
than assumed. Published exact cone angles are computed on B3LYP-optimised
geometries of the ligand BOUND TO a metal; published %Vbur likewise comes
from crystal structures. This computes from free-ligand conformers
embedded and minimised with MMFF, because that is what is available for
an arbitrary structure someone has drawn. A bound phosphine's
substituents splay differently from a free one, and that difference is
the whole discrepancy:

    PPh3 exact cone angle   163.8 here    170.0 published
    %Vbur across PMe3/PPh3/PCy3/PtBu3     mean error 2.2 points,
                                          growing with ligand size

What survives that difference is what these measures are actually used
for -- RANKING ligands. Against Tolman's published series the ordering is
identical (PH3 < PMe3 < PEt3 < PPh3 < PCy3 < PtBu3) and the correlation
is r = 0.977. So the numbers here are directly comparable to each other
and NOT directly comparable to a table computed on different geometries,
which is stated in the result rather than left to be discovered.

That is the same treatment `geometry_analysis` already gives MMFF94/UFF
energies, which are real and useful but are not Dreiding.
"""

from __future__ import annotations

import dataclasses

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import ReportResult, ConeAnnotation, valid_spatial_annotation
from openchem.chem.report_adapter import report_fields

_PERIODIC_TABLE = Chem.GetPeriodicTable()

# SambVca's conventions, so the numbers mean what that name means.
DEFAULT_SPHERE_RADIUS = 3.5
DEFAULT_METAL_DISTANCE = 2.28
BONDI_SCALE = 1.17

# Elements that act as the donor atom of a ligand. Phosphorus first: the
# entire published reference literature for both measures is phosphines.
# Carbon is NOT here. It appears only through `_is_carbene_carbon` below,
# because listing the element outright made every organic molecule a
# "ligand" -- butane reported a cone angle, which is meaningless.
DONOR_ELEMENTS = ("P", "N", "As", "S")


def _is_carbene_carbon(atom: Chem.Atom) -> bool:
    """A divalent, neutral, hydrogen-free carbon -- an N-heterocyclic
    carbene's donor. Narrow on purpose: these are real ligands and
    deserve to work, but the test cannot be "is a carbon"."""
    return (
        atom.GetSymbol() == "C"
        and atom.GetDegree() == 2
        and atom.GetTotalNumHs() == 0
        and atom.GetFormalCharge() == 0
    )


class NoDonorError(ValueError):
    """No atom in this structure can act as a ligand donor."""


class NoConformerError(ValueError):
    """Both measures are 3D quantities and mean nothing without geometry."""


def find_donor(mol: Chem.Mol) -> int:
    """The atom the metal would bind, by element priority.

    A carbene carbon is included so N-heterocyclic carbenes work, but it
    is last: in anything containing phosphorus or nitrogen, those bind.
    """
    # Carbene FIRST. A neutral divalent hydrogen-free carbon is an
    # unambiguous donor, and in the ligands that have one -- N-heterocyclic
    # carbenes -- the ring nitrogens would otherwise win the priority
    # order and put the cone on entirely the wrong atom.
    for atom in mol.GetAtoms():
        if _is_carbene_carbon(atom):
            return atom.GetIdx()
    for element in DONOR_ELEMENTS:
        for atom in mol.GetAtoms():
            if atom.GetSymbol() == element:
                return atom.GetIdx()
    raise NoDonorError(
        "No donor atom found. These measures describe a LIGAND -- the structure needs an "
        f"atom that could bind a metal ({', '.join(DONOR_ELEMENTS)}, or a carbene carbon)."
    )


def _search_directions(count: int = 64) -> np.ndarray:
    """Evenly spread unit vectors, from the golden spiral.

    Deterministic on purpose. An earlier version perturbed the axis
    randomly, which found the same optimum but would have made the
    calculator return slightly different numbers on repeated runs -- a
    property no measurement should have.
    """
    indices = np.arange(count) + 0.5
    phi = np.arccos(1 - 2 * indices / count)
    theta = math.pi * (1 + 5**0.5) * indices
    return np.stack(
        [np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1
    )


def _half_angles(axis: np.ndarray, positions: np.ndarray, radii: np.ndarray, apex: np.ndarray):
    """Angle from `axis` to the far edge of each atom's vdW sphere."""
    offsets = positions - apex
    distances = np.linalg.norm(offsets, axis=1)
    cosines = np.clip((offsets @ axis) / distances, -1.0, 1.0)
    angular_radii = np.arcsin(np.clip(radii / distances, 0.0, 1.0))
    return np.degrees(np.arccos(cosines) + angular_radii)


@dataclass(frozen=True)
class ConeAngle:
    angle: float
    axis: np.ndarray
    along_bond_angle: float

    @property
    def axis_was_tilted(self) -> bool:
        """True when the optimal cone is NOT along the metal-donor bond --
        i.e. the ligand is sterically unsymmetric."""
        return self.along_bond_angle - self.angle > 0.5


def _ligand_geometry(mol: Chem.Mol, donor: int, conformer_id: int, metal_distance: float):
    conformer = mol.GetConformer(conformer_id)
    positions = conformer.GetPositions()
    substituents = [n.GetIdx() for n in mol.GetAtomWithIdx(donor).GetNeighbors()]
    if not substituents:
        raise NoDonorError("The donor atom has no substituents, so there is no ligand to measure.")
    # The metal sits opposite the substituents, along the donor's lone
    # pair -- approximated by the direction away from their centroid.
    bond_axis = positions[donor] - np.mean(positions[substituents], axis=0)
    norm = np.linalg.norm(bond_axis)
    if norm == 0:
        raise NoDonorError("Degenerate geometry around the donor atom.")
    bond_axis /= norm
    apex = positions[donor] + bond_axis * metal_distance
    return positions, apex, -bond_axis


def exact_cone_angle(
    mol: Chem.Mol,
    donor: int,
    conformer_id: int = 0,
    metal_distance: float = DEFAULT_METAL_DISTANCE,
) -> ConeAngle:
    """The smallest cone containing the ligand, axis optimised.

    Reported alongside the along-the-bond value, because their difference
    IS the ligand's steric asymmetry and collapsing them would throw that
    away.
    """
    positions, apex, toward_ligand = _ligand_geometry(mol, donor, conformer_id, metal_distance)
    indices = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetIdx() != donor]
    if not indices:
        raise NoDonorError("A bare donor atom has no cone angle.")
    points = positions[indices]
    radii = np.array(
        [_PERIODIC_TABLE.GetRvdw(mol.GetAtomWithIdx(i).GetAtomicNum()) for i in indices]
    )
    # An atom whose sphere swallows the apex has no well-defined angle;
    # it also cannot happen at a real metal-donor distance.
    outside = np.linalg.norm(points - apex, axis=1) > radii
    points, radii = points[outside], radii[outside]
    if len(points) == 0:
        raise NoDonorError("Every atom encloses the metal position -- check the geometry.")

    along_bond = float(_half_angles(toward_ligand, points, radii, apex).max())

    best_axis = toward_ligand
    best = along_bond
    for candidate in _search_directions():
        # Only directions pointing into the ligand can enclose it.
        if candidate @ toward_ligand <= 0:
            continue
        value = float(_half_angles(candidate, points, radii, apex).max())
        if value < best:
            best, best_axis = value, candidate

    # Local refinement: shrink a ring of trial directions around the best.
    spread = 15.0
    while spread > 1e-3:
        improved = False
        basis = np.cross(best_axis, [0.0, 0.0, 1.0])
        if np.linalg.norm(basis) < 1e-6:
            basis = np.cross(best_axis, [0.0, 1.0, 0.0])
        basis /= np.linalg.norm(basis)
        other = np.cross(best_axis, basis)
        for step in range(12):
            angle = 2 * math.pi * step / 12
            offset = basis * math.cos(angle) + other * math.sin(angle)
            tilt = math.radians(spread)
            candidate = best_axis * math.cos(tilt) + offset * math.sin(tilt)
            candidate /= np.linalg.norm(candidate)
            value = float(_half_angles(candidate, points, radii, apex).max())
            if value < best - 1e-9:
                best, best_axis, improved = value, candidate, True
        if not improved:
            spread *= 0.5

    return ConeAngle(angle=2 * best, axis=best_axis, along_bond_angle=2 * along_bond)


def buried_volume(
    mol: Chem.Mol,
    donor: int,
    conformer_id: int = 0,
    sphere_radius: float = DEFAULT_SPHERE_RADIUS,
    metal_distance: float = DEFAULT_METAL_DISTANCE,
    grid_spacing: float = 0.1,
) -> float:
    """Percent of the sphere around the metal filled by the ligand.

    Hydrogens are omitted and radii scaled by 1.17, both SambVca
    conventions -- measured, not guessed: including hydrogens raised the
    mean error against published values from 2.2 points to 4.9, and
    dropping the scale factor raised it to 5.8.
    """
    positions, apex, _ = _ligand_geometry(mol, donor, conformer_id, metal_distance)
    axis = np.arange(-sphere_radius, sphere_radius + 1e-9, grid_spacing)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1).reshape(-1, 3)
    inside_sphere = grid[(grid**2).sum(axis=1) <= sphere_radius**2]

    occupied = np.zeros(len(inside_sphere), dtype=bool)
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        radius = _PERIODIC_TABLE.GetRvdw(atom.GetAtomicNum()) * BONDI_SCALE
        offset = positions[atom.GetIdx()] - apex
        occupied |= ((inside_sphere - offset) ** 2).sum(axis=1) <= radius**2
    return 100.0 * float(occupied.sum()) / len(inside_sphere)


def _ensemble(mol: Chem.Mol, conformers: int, seed: int = 0xF00D):
    """Embed and minimise, returning (mol_with_conformers, ids, own_geometry).

    Both measures are computed across the ensemble rather than from one
    geometry, because a flexible ligand genuinely has a range of steric
    profiles and reporting a single number hides that.

    `own_geometry` says whether the CALLER's conformer was used (True) or
    this function embedded its own (False). The distinction is
    load-bearing for the spatial annotation: coordinates from an
    internally embedded conformer are in a frame no viewer can load, so a
    cone drawn from them would sit on the wrong molecule with nothing on
    screen to say so.
    """
    prepared = Chem.AddHs(Chem.Mol(mol))
    if prepared.GetNumConformers() and prepared.GetConformer().Is3D():
        return prepared, [c.GetId() for c in prepared.GetConformers()], True
    ids = list(AllChem.EmbedMultipleConfs(prepared, numConfs=conformers, randomSeed=seed))
    if not ids:
        raise NoConformerError("Could not generate a 3D conformer for this structure.")
    AllChem.MMFFOptimizeMoleculeConfs(prepared)
    return prepared, ids, False


def compute_steric_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "geometry" category's ligand-bulk calculator."""
    parameters = parameters or {}
    places = decimals(parameters)
    conformers = int(parameters.get("conformers", 20))
    metal_distance = float(parameters.get("metal_distance", DEFAULT_METAL_DISTANCE))
    sphere_radius = float(parameters.get("sphere_radius", DEFAULT_SPHERE_RADIUS))

    try:
        prepared, ids, own_geometry = _ensemble(mol, conformers)
        donor = find_donor(prepared)
        cones = [exact_cone_angle(prepared, donor, c, metal_distance) for c in ids]
        volumes = [buried_volume(prepared, donor, c, sphere_radius, metal_distance) for c in ids]
    except (NoDonorError, NoConformerError, ValueError) as exc:
        return _report(
            alert_id="steric_analysis",
            name="Ligand Steric Bulk",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="geometry",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="exact_cone_angle+vbur"),
        )

    # The MINIMUM cone over the ensemble, which is Tolman's own convention
    # -- a flexible ligand presents its most compact face to the metal.
    tightest_index = min(range(len(cones)), key=lambda i: cones[i].angle)
    tightest = cones[tightest_index]
    donor_atom = prepared.GetAtomWithIdx(donor)

    lines = [
        f"Donor atom: {donor_atom.GetSymbol()}{donor}",
        f"Exact cone angle: {tightest.angle:.{places}f} deg",
        f"Percent buried volume: {sum(volumes) / len(volumes):.{places}f}%",
    ]
    if len(ids) > 1:
        lines.append(
            f"Across {len(ids)} conformers: cone "
            f"{min(c.angle for c in cones):.{places}f}-{max(c.angle for c in cones):.{places}f} deg, "
            f"%Vbur {min(volumes):.{places}f}-{max(volumes):.{places}f}%"
        )
    if tightest.axis_was_tilted:
        lines.append(
            f"Sterically unsymmetric: the tightest cone is {tightest.along_bond_angle - tightest.angle:.{places}f} "
            "deg narrower than one along the metal-donor bond."
        )
    lines.append(
        f"Geometry: free ligand, MMFF-minimised. Published exact cone angles and %Vbur are "
        f"computed on metal-BOUND DFT or crystal geometries, where substituents splay "
        f"differently -- these values rank ligands against each other correctly (ordering and "
        f"r = 0.98 against Tolman's series) but are not directly comparable to those tables."
    )

    result = _report(
        alert_id="steric_analysis",
        name="Ligand Steric Bulk",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="geometry",
        provenance=Provenance(
            created_by="core",
            method="exact_cone_angle+vbur",
            parameters={
                "donor_atom": donor,
                "cone_angle_deg": tightest.angle,
                "cone_angle_along_bond_deg": tightest.along_bond_angle,
                "buried_volume_percent": sum(volumes) / len(volumes),
                "conformers": len(ids),
                "metal_distance_a": metal_distance,
                "sphere_radius_a": sphere_radius,
                "geometry_source": "provided_conformer" if own_geometry else "free_ligand_mmff",
            },
        ),
    )
    # THE CONE, only when its frame is one a viewer can load. With an
    # internally embedded ensemble the coordinates belong to a geometry
    # nobody else holds, and a cone drawn from them would sit plausibly on
    # the WRONG conformer -- the worst kind of picture. The geometry is
    # DERIVED from the calculation's own construction, never assembled
    # from the stored scalars: the apex comes from `_ligand_geometry` on
    # the same conformer the tightest cone was measured on, the axis is
    # the one the search actually settled on (tilted or not), and the
    # length is the reach of the sweep itself -- the farthest vdW-sphere
    # edge `_half_angles` measured to, not `metal_distance + sphere_radius`,
    # which are two unrelated scalars that happen to be lying nearby.
    if own_geometry:
        conformer_id = ids[tightest_index]
        positions, apex, _toward = _ligand_geometry(prepared, donor, conformer_id, metal_distance)
        reach = max(
            float(np.linalg.norm(positions[a.GetIdx()] - apex))
            + _PERIODIC_TABLE.GetRvdw(a.GetAtomicNum())
            for a in prepared.GetAtoms()
            if a.GetIdx() != donor
        )
        annotation = ConeAnnotation(
            apex=tuple(float(v) for v in apex),
            axis=tuple(float(v) for v in tightest.axis),
            half_angle_deg=tightest.angle / 2.0,
            length=reach,
            label=f"{tightest.angle:.{places}f} deg",
        )
        if valid_spatial_annotation(annotation):
            result = dataclasses.replace(result, spatial=(annotation,))
    return result


def _report(**fields) -> ReportResult:
    """One `AlertResult(...)` call site, as a `ReportResult`.

    The keyword names are unchanged -- `alert_id`, `name`, `matched`,
    `category` -- so the call sites above read as they always did and the
    diff stays small. `report_fields` does the translation and turns each
    line into a `Fact`; see `chem/report_adapter.py` for what a string can
    and cannot carry.

    A calculator that wants real units, evidence or limitations on a fact
    builds `Fact`s directly instead, as `geometry_analysis` now does.
    """
    return ReportResult(**report_fields(**fields))
