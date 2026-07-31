"""3D geometric properties of a conformer.

Requires real 3D coordinates -- everything here is meaningless on the flat
2D editor structure, so each function raises rather than silently
returning a number computed from a degenerate geometry.

ON "DREIDING ENERGY": Marvin's Geometry plugin reports a Dreiding force
field energy. RDKit does not implement Dreiding. This module reports
MMFF94 and UFF energies instead, LABELLED AS SUCH -- they are real,
well-defined force field energies, but they are not comparable to
Marvin's numbers, and relabelling either as "Dreiding" would produce a
figure that looks authoritative and cross-references to nothing.

ON STERIC HINDRANCE: still absent, but the reason has narrowed and is
worth recording so the next attempt does not start over.

"Steric hindrance" itself names several incompatible quantities. But two
REAL, published, validatable measures exist, and both were implemented
and checked against their literature values:

  Tolman cone angle (Chem. Rev. 1977, 77, 313), M-P 2.28 A --
      PH3 86.4 vs 87, PMe3 117.2 vs 118, PCy3 170.6 vs 170: essentially
      exact. But PPh3 came out 163.8 against Tolman's 145, and P(tBu)3
      193.6 against 182. Tolman folded substituents into their nested
      minimum profile on CPK models; minimising over an MMFF conformer
      ensemble does not reproduce that, and it fails hardest on flexible
      aryl groups -- i.e. on PPh3, the one ligand everybody checks a cone
      angle implementation against.

  Percent buried volume (SambVca; R = 3.5 A, M-P 2.28 A, Bondi radii
  x1.17, hydrogens omitted) --
      PMe3 24.4 vs 26.2, PPh3 30.8 vs 30.1, PCy3 35.5 vs 32.7,
      P(tBu)3 39.7 vs 36.2. Mean absolute error 2.2 points, and the
      residual grows monotonically with ligand size, which points at the
      geometry source: published values come from crystal structures,
      not from an MMFF-optimised ensemble.

Both reproduce the ORDERING correctly (PMe3 < PPh3 < PCy3 < PtBu3), which
is what a steric measure is mostly used for. Neither reproduces absolute
published values closely enough to ship under its own name -- reporting
PCy3 as 35.5 %Vbur when the literature says 32.7 would mislead anyone
comparing against a paper. Shipping it as an unnamed "steric index"
would be worse: unnamed means uncheckable.

The gaps are now specific rather than fundamental (substituent nesting;
crystal vs. force-field geometry), so this is a real candidate to finish,
unlike the topological steric effect index -- see `topology_analysis`.
"""

from __future__ import annotations

import math
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import AlertResult


class NoConformerError(ValueError):
    """Raised when a geometry calculation is attempted on a structure with
    no real 3D coordinates."""


def _require_conformer(mol: Chem.Mol) -> Chem.Conformer:
    if mol.GetNumConformers() == 0:
        raise NoConformerError(
            "This calculation needs a 3D conformer. Switch to the 3D Viewer tab and "
            "click \"Generate Conformers...\" first."
        )
    conformer = mol.GetConformer()
    if not conformer.Is3D():
        raise NoConformerError(
            "The available conformer is 2D. Generate a real 3D conformer from the 3D Viewer tab."
        )
    return conformer


def molecular_radii(mol: Chem.Mol) -> dict[str, float]:
    """Distances from the centroid to the nearest/furthest/mean atom.

    The maximum is the radius of the smallest sphere centred on the
    centroid that contains every atom -- a direct read of overall molecular
    extent, which is what Marvin's Geometry plugin surfaces alongside its
    3D projection.
    """
    conformer = _require_conformer(mol)
    positions = conformer.GetPositions()
    centroid = positions.mean(axis=0)
    distances = [float(((position - centroid) ** 2).sum() ** 0.5) for position in positions]
    return {
        "min_radius": min(distances),
        "max_radius": max(distances),
        "mean_radius": sum(distances) / len(distances),
    }


def force_field_energies(mol: Chem.Mol) -> dict[str, float | None]:
    """MMFF94 and UFF energies of the CURRENT geometry, in kcal/mol.

    Not Dreiding (see the module docstring). Either can be `None`: MMFF
    has no parameters for some elements, and returning None is honest
    where substituting the other force field's number silently would not
    be -- they are on different scales.
    """
    _require_conformer(mol)
    energies: dict[str, float | None] = {"mmff94": None, "uff": None}
    try:
        properties = AllChem.MMFFGetMoleculeProperties(mol)
        if properties is not None:
            field = AllChem.MMFFGetMoleculeForceField(mol, properties)
            if field is not None:
                energies["mmff94"] = float(field.CalcEnergy())
    except (ValueError, RuntimeError):
        pass
    try:
        if AllChem.UFFHasAllMoleculeParams(mol):
            field = AllChem.UFFGetMoleculeForceField(mol)
            if field is not None:
                energies["uff"] = float(field.CalcEnergy())
    except (ValueError, RuntimeError):
        pass
    return energies


def bond_length(mol: Chem.Mol, atom_a: int, atom_b: int) -> float:
    return float(rdMolTransforms.GetBondLength(_require_conformer(mol), atom_a, atom_b))


def bond_angle(mol: Chem.Mol, atom_a: int, atom_b: int, atom_c: int) -> float:
    """Angle a-b-c in degrees, with `atom_b` at the vertex."""
    return float(rdMolTransforms.GetAngleDeg(_require_conformer(mol), atom_a, atom_b, atom_c))


def dihedral_angle(mol: Chem.Mol, atom_a: int, atom_b: int, atom_c: int, atom_d: int) -> float:
    """Torsion a-b-c-d in degrees. Anti-butane is 180 (confirmed live)."""
    return float(rdMolTransforms.GetDihedralDeg(_require_conformer(mol), atom_a, atom_b, atom_c, atom_d))


def compute_geometry_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "geometry" category's calculator."""
    places = decimals(parameters)
    try:
        radii = molecular_radii(mol)
        energies = force_field_energies(mol)
    except NoConformerError as exc:
        return AlertResult(
            alert_id="geometry_analysis",
            name="Geometry",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="geometry",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    lines = [
        f"Max radius (from centroid): {radii['max_radius']:.{places}f} Å",
        f"Min radius (from centroid): {radii['min_radius']:.{places}f} Å",
        f"Mean radius (from centroid): {radii['mean_radius']:.{places}f} Å",
    ]
    # Named explicitly so nobody reads these as Marvin's Dreiding value.
    if energies["mmff94"] is not None:
        lines.append(f"MMFF94 energy: {energies['mmff94']:.{places}f} kcal/mol")
    if energies["uff"] is not None:
        lines.append(f"UFF energy: {energies['uff']:.{places}f} kcal/mol")
    if energies["mmff94"] is None and energies["uff"] is None:
        lines.append("No force field parameters available for this molecule.")
    else:
        lines.append("(MMFF94/UFF — not Dreiding; values are not comparable to MarvinSketch's.)")

    return AlertResult(
        alert_id="geometry_analysis",
        name="Geometry",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="geometry",
        provenance=Provenance(created_by="core", method="rdkit"),
    )
