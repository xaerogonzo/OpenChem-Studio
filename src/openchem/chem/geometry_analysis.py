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

ON STERIC HINDRANCE: two real measures now ship, in `chem/steric.py`
-- the exact cone angle and percent buried volume. What unblocked them
was not new code but the realisation that the earlier validation used
the wrong reference: those numbers were being compared against Tolman's
CPK-model values, when the quantity being computed is the EXACT cone
angle, a different (and better-posed) definition. See that module for
the measured results and the geometry caveat.

The TOPOLOGICAL steric effect index stays absent -- see
`topology_analysis`. Unlike these two it has no single definition to
implement.
"""

from __future__ import annotations

import math
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis


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
) -> ReportResult:
    """The "geometry" category's calculator.

    Returns FACTS, not a list of strings. Each carries its own units and
    basis, which a `matched` line could not: "Max radius (from centroid):
    2.35 A" was one opaque string, and the panel rendered eight of them as
    "8 alert(s)" in warning red.
    """
    places = decimals(parameters)
    try:
        radii = molecular_radii(mol)
        energies = force_field_energies(mol)
    except NoConformerError as exc:
        return ReportResult(
            molecule_uuid=molecule_uuid,
            report_id="geometry_analysis",
            name="Geometry",
            category="geometry",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    def _radius(label: str, key: str) -> Fact:
        return Fact(
            category=FactCategory.GEOMETRY,
            label=label,
            value=radii[key],
            display_value=f"{radii[key]:.{places}f}",
            source="Geometry",
            basis=Basis.DETERMINISTIC,
            units="A",
        )

    facts = [
        _radius("Max radius (from centroid)", "max_radius"),
        _radius("Min radius (from centroid)", "min_radius"),
        _radius("Mean radius (from centroid)", "mean_radius"),
    ]

    # NAMED EXPLICITLY so nobody reads these as Marvin's Dreiding value.
    # That caveat used to be an extra line of prose in `matched`; as a
    # per-fact limitation it travels with the number it qualifies, into
    # the tooltip and every export.
    not_dreiding = (
        "MMFF94/UFF, not Dreiding. Not comparable to MarvinSketch's "
        "Geometry plugin, which reports a Dreiding energy RDKit cannot "
        "compute.",
    )
    for key, label in (("mmff94", "MMFF94 energy"), ("uff", "UFF energy")):
        if energies[key] is None:
            continue
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label=label,
                value=energies[key],
                display_value=f"{energies[key]:.{places}f}",
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                units="kcal/mol",
                limitations=not_dreiding,
            )
        )
    if energies["mmff94"] is None and energies["uff"] is None:
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label="Force field energy",
                value=None,
                display_value="No force field parameters for this molecule.",
                source="Geometry",
                basis=Basis.DETERMINISTIC,
            )
        )

    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="geometry_analysis",
        name="Geometry",
        category="geometry",
        facts=tuple(facts),
        provenance=Provenance(created_by="core", method="rdkit"),
    )
