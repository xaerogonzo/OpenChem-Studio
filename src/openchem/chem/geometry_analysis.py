"""3D geometric properties of a conformer.

Requires real 3D coordinates -- everything here is meaningless on the flat
2D editor structure, so each function raises rather than silently
returning a number computed from a degenerate geometry.

ON "DREIDING ENERGY": Marvin's Geometry plugin reports a Dreiding force
field energy, and for a long time this module could not. Neither RDKit
nor OpenBabel implements Dreiding (checked: OpenBabel offers GAFF,
Ghemical, MMFF94, MMFF94s and UFF), so the note here used to say the
number was unobtainable.

**It is obtainable, and it is now reported.** `chem/dreiding/` implements
the force field from the primary source (Mayo, Olafson & Goddard 1990)
and reproduces all eight rotational barriers the paper computes with
DREIDING itself -- its Table XI -- to a worst deviation of 0.008
kcal/mol. Those are the paper's own calculated values rather than
experiment, which is what makes them a test of the implementation with
nothing left ambiguous. `docs/DREIDING_ASSESSMENT.md` has the table.

All three energies are reported side by side and **none of them is
comparable to another**: they are three different scales, and each fact
says so. Dreiding carries two further caveats of its own -- it is
computed without charges or an explicit hydrogen-bond term, which is the
configuration the paper reports its own results in.

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
from openchem.chem.dreiding import UntypedAtomError, dreiding_energy
from openchem.chem.projection_geometry import (
    _FRAGMENT_CONTACT_FLOOR,
    closest_fragment_approach,
    shape_descriptors,
)
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
    """MMFF94, UFF and Dreiding energies of the CURRENT geometry, kcal/mol.

    Any of the three can be `None`, and that is the honest answer rather
    than a gap to fill: MMFF has no parameters for some elements,
    Dreiding covers 37 atom types and refuses outside them, and
    substituting one field's number for another's would be meaningless
    because **they are on different scales and cannot be compared**.
    """
    _require_conformer(mol)
    energies: dict[str, float | None] = {"mmff94": None, "uff": None, "dreiding": None}
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
    try:
        # Dreiding needs EXPLICIT hydrogens -- its united-atom types are a
        # separate parameterisation, not this one with the hydrogens
        # dropped. A conformer generated by this app always has them,
        # since the embedder needs them too, so this is a guard rather
        # than a common path.
        energies["dreiding"] = dreiding_energy(mol).total
    except (UntypedAtomError, ValueError, RuntimeError, KeyError):
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

    # The shape half of Marvin's Geometry plugin. Volume and surface come
    # from `surface_analysis`, which already reports them -- repeating a
    # number in two panels invites the two to drift apart, which is the
    # failure a shared module exists to prevent.
    on_principal_planes = [
        "Measured on the three principal planes rather than optimised over "
        "all orientations, so a shape whose true extreme lies off-axis "
        "reads slightly high.",
    ]
    # A structure drawn as two species and given a conformer comes back
    # with the fragments packed at the origin -- `EmbedMolecule` applies no
    # constraints between them. Their spheres then fuse and every shape
    # figure is too SMALL, by 21-44% on the cases measured. Reported, not
    # suppressed: a genuine short contact is legitimate, and the number is
    # only misleading if nobody says which situation this is.
    approach = closest_fragment_approach(mol)
    if approach is not None and approach < _FRAGMENT_CONTACT_FLOOR:
        on_principal_planes.append(
            f"This structure has separate fragments only {approach:.2f} A apart, "
            "which is closer than any real contact -- 3D generation does not "
            "push disconnected fragments apart. Their surfaces overlap, so "
            "every figure here is smaller than the true one. Position the "
            "fragments deliberately before trusting these."
        )
    on_principal_planes = tuple(on_principal_planes)
    shape = shape_descriptors(mol)
    for label, value in (
        ("Min projection area", shape.min_projection_area),
        ("Max projection area", shape.max_projection_area),
    ):
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label=label,
                value=value,
                display_value=f"{value:.{places}f}",
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                units="A^2",
                limitations=on_principal_planes,
            )
        )
    for label, value in (
        ("Min projection radius", shape.min_projection_radius),
        ("Max projection radius", shape.max_projection_radius),
    ):
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label=label,
                value=value,
                display_value=f"{value:.{places}f}",
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                units="A",
                limitations=on_principal_planes,
            )
        )

    # **A FORCE FIELD ENERGY IS ONLY COMPARABLE TO ITSELF**, and with
    # three of them on screen that is the thing a reader most needs
    # telling. Carried per fact rather than as a line of prose, so it
    # travels with the number into the tooltip and every export.
    incomparable = (
        "A force field energy has no absolute meaning: compare it only "
        "with the SAME force field on a conformer of the SAME molecule. "
        "MMFF94, UFF and Dreiding are on three different scales.",
    )
    # Dreiding earns a second caveat of its own -- what it leaves out.
    dreiding_caveats = incomparable + (
        "Computed without charges or an explicit hydrogen-bond term, "
        "which is the configuration the DREIDING paper reports its own "
        "results in. A polar molecule is therefore missing an "
        "electrostatic contribution.",
        "Validated against all eight rotational barriers the paper "
        "computes with DREIDING (its Table XI), worst deviation 0.008 "
        "kcal/mol.",
    )
    for key, label in (
        ("mmff94", "MMFF94 energy"),
        ("uff", "UFF energy"),
        ("dreiding", "Dreiding energy"),
    ):
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
                limitations=dreiding_caveats if key == "dreiding" else incomparable,
            )
        )
    if all(energies[key] is None for key in ("mmff94", "uff", "dreiding")):
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
