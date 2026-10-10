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

from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.calculator_options import decimals
from openchem.chem.dreiding import UntypedAtomError, dreiding_energy
from openchem.chem.geometry_options import (
    POLICY_ALWAYS,
    POLICY_IF_2D,
    GeometryOptions,
    geometry_options,
)
from openchem.chem.geometry_preparation import (
    LowestConformer,
    Optimised,
    geometry_fingerprint,
    level_name,
    lowest_energy_conformer,
    optimised_copy,
)
from openchem.chem.projection_geometry import (
    _FRAGMENT_CONTACT_FLOOR,
    closest_fragment_approach,
    shape_descriptors,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.result_store import GEOMETRY_METHOD
from openchem.domain.report import Fact, FactCategory, ReportResult, AxesAnnotation, valid_spatial_annotation
from openchem.domain.structure_issue import Basis


class NoConformerError(ValueError):
    """Raised when a geometry calculation is attempted on a structure with
    no real 3D coordinates."""


def _require_conformer(mol: Chem.Mol) -> Chem.Conformer:
    if mol.GetNumConformers() == 0:
        raise NoConformerError(
            "This calculation needs a 3D conformer. Generate one with "
            "Structure ▸ Generate Conformers... first."
        )
    conformer = mol.GetConformer()
    if not conformer.Is3D():
        raise NoConformerError(
            "The available conformer is 2D. Generate a real 3D one with Structure ▸ Generate Conformers...."
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


def _failed(molecule_uuid: str, error: str) -> ReportResult:
    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="geometry_analysis",
        name="Geometry",
        category="geometry",
        cache_state=CacheState.FAILED,
        error=error,
        provenance=Provenance(created_by="core", method="rdkit"),
    )


def _is_3d(mol: Chem.Mol) -> bool:
    return mol.GetNumConformers() > 0 and mol.GetConformer().Is3D()


def _select_geometry(mol: Chem.Mol, options: GeometryOptions) -> tuple[Chem.Mol, LowestConformer | None]:
    """The geometry every number is measured on, and the search that chose it (None if none ran).

    `never` keeps the old rule: the conformer as given, and a 2D structure is refused. The other
    two generate a lowest-of-N conformer on a COPY. Raises `NoConformerError` when there is no
    geometry to measure and none could be made.
    """
    supplied = _is_3d(mol)
    generate = options.conformer_policy == POLICY_ALWAYS or (
        options.conformer_policy == POLICY_IF_2D and not supplied
    )
    if not generate:
        _require_conformer(mol)
        return mol, None
    found = lowest_energy_conformer(
        mol, options.conformer_count, options.optimisation_limit, include_supplied=supplied
    )
    if found is None:
        raise NoConformerError(
            "No 3D conformer could be generated for this structure, so there is nothing to measure."
        )
    return found.mol, found


def compute_geometry_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "geometry" category's calculator.

    Returns FACTS, not a list of strings. Each carries its own units and
    basis, which a `matched` line could not: "Max radius (from centroid):
    2.35 A" was one opaque string, and the panel rendered eight of them as
    "8 alert(s)" in warning red.

    **WHICH GEOMETRY EACH NUMBER IS MEASURED ON is a choice the person can make** (see
    `geometry_options`): the conformer as it is, the lowest of several generated, and, for the
    MMFF94 energy and for the projections separately, a relaxed copy of it. Whatever was done is
    stated in the facts and recorded in the provenance, and nothing ever moves the stored
    geometry.
    """
    places = decimals(parameters)
    options = geometry_options(parameters)
    try:
        selected, search = _select_geometry(mol, options)
    except NoConformerError as exc:
        return _failed(molecule_uuid, str(exc))

    relaxed: Optimised | None = None
    if options.optimise_mmff or options.optimise_projection:
        relaxed = optimised_copy(selected, options.optimisation_limit)
    shape_mol = relaxed.mol if (relaxed is not None and options.optimise_projection) else selected
    try:
        radii = molecular_radii(shape_mol)
        energies = force_field_energies(selected)
        shape = shape_descriptors(shape_mol, radius_scale=options.radius_scale)
    except NoConformerError as exc:
        return _failed(molecule_uuid, str(exc))

    mmff_label = "MMFF94 energy"
    mmff_note: str | None = None
    if options.optimise_mmff and relaxed is not None:
        if relaxed.force_field == "MMFF94":
            energies["mmff94"] = relaxed.energy
            mmff_label = "MMFF94 energy (optimised)"
            if not relaxed.converged:
                mmff_note = (
                    "The optimiser did not settle at this limit, so this is the energy of the last "
                    "geometry it reached, not of a minimum."
                )
        else:
            energies["mmff94"] = None
            mmff_note = "Optimisation was asked for, but MMFF94 has no parameters for this molecule."

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

    # THE SHADOW. The area at each orientation is exact; which orientation is the extreme is searched
    # (`projection_search`). The radius, the size and the radii they use are defined here because
    # ChemAxon documents none of them.
    scale_note = (
        f"Van der Waals radii scaled by {options.radius_scale:g}."
        if options.radius_scale != 1.0
        else "Bondi van der Waals radii."
    )
    searched = (
        "Found by searching "
        f"{shape.orientations_searched} viewing directions (sampled over the hemisphere, then the "
        "best refined to about 0.006 degree); the area at each direction is exact. A search can "
        "in principle settle on a local extreme, though it matched a sweep of 6000 directions on "
        "every molecule measured.",
        scale_note,
    )
    meaning = {
        "Min projection area": "The smallest area the shadow takes over all viewing directions (union of the atoms' circles).",
        "Max projection area": "The largest area the shadow takes over all viewing directions (union of the atoms' circles).",
        "Min projection radius": "Radius of the smallest circle that encloses the shadow in the minimum-area view: the round hole it passes through.",
        "Max projection radius": "Radius of the smallest circle that encloses the shadow in the maximum-area view: the round hole it passes through.",
        "Size perpendicular to the min projection": "The extent of the molecule along the minimum-area viewing direction, surface to surface.",
        "Size perpendicular to the max projection": "The extent of the molecule along the maximum-area viewing direction, surface to surface.",
    }
    # A fragment pair packed together makes every shape figure too small -- see `closest_fragment_approach`.
    # Reported, not suppressed: a genuine short contact is legitimate.
    approach = closest_fragment_approach(shape_mol)
    crowded: tuple[str, ...] = ()
    if approach is not None and approach < _FRAGMENT_CONTACT_FLOOR:
        crowded = (
            f"This structure has separate fragments only {approach:.2f} A apart, "
            "which is closer than any real contact -- 3D generation does not "
            "push disconnected fragments apart. Their surfaces overlap, so "
            "every figure here is smaller than the true one. Position the "
            "fragments deliberately before trusting these.",
        )
    for label, value, units in (
        ("Min projection area", shape.min_projection_area, "A^2"),
        ("Max projection area", shape.max_projection_area, "A^2"),
        ("Min projection radius", shape.min_projection_radius, "A"),
        ("Max projection radius", shape.max_projection_radius, "A"),
        ("Size perpendicular to the min projection", shape.min_projection_size, "A"),
        ("Size perpendicular to the max projection", shape.max_projection_size, "A"),
    ):
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label=label,
                value=value,
                display_value=f"{value:.{places}f}",
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                units=units,
                limitations=(meaning[label], *searched, *crowded),
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
        ("mmff94", mmff_label),
        ("uff", "UFF energy"),
        ("dreiding", "Dreiding energy"),
    ):
        if energies[key] is None:
            continue
        converted = options.convert(energies[key])
        extra = (mmff_note,) if (key == "mmff94" and mmff_note) else ()
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label=label,
                value=converted,
                display_value=f"{converted:.{places}f}",
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                units=options.unit_label,
                limitations=(dreiding_caveats if key == "dreiding" else incomparable) + extra,
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

    # WHAT WAS DONE TO THE GEOMETRY, stated as facts so it travels with the numbers.
    if search is not None:
        low, high = (options.convert(v) for v in search.energy_range)
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label="Conformer used",
                value=None,
                display_value=(
                    f"Lowest of {search.ranked} ranked ({search.candidates} tried"
                    f"{', including the one supplied' if search.generated < search.candidates else ''}); "
                    f"{search.force_field} {options.convert(search.energy):.{places}f} {options.unit_label}, "
                    f"range {low:.{places}f} to {high:.{places}f}"
                    f"{'; the supplied geometry won' if search.supplied_won else ''}."
                ),
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                limitations=(
                    "The lowest energy among the candidates tried, under one force field, from one "
                    "seeded random search. It is NOT the global minimum of the molecule, and a "
                    "different candidate count can give a different answer.",
                ),
            )
        )
    if relaxed is not None:
        used_for = " and ".join(
            part for part, on in (("the MMFF94 energy", options.optimise_mmff), ("the projections", options.optimise_projection)) if on
        )
        facts.append(
            Fact(
                category=FactCategory.GEOMETRY,
                label="Geometry relaxed for",
                value=None,
                display_value=(
                    f"{used_for}: {relaxed.force_field or 'no force field'}, "
                    f"{level_name(options.optimisation_limit).lower()} limit, "
                    f"{'settled' if relaxed.converged else 'did not settle'}."
                ),
                source="Geometry",
                basis=Basis.DETERMINISTIC,
                limitations=(
                    "A relaxed COPY. The stored conformer is not moved, so the structure on screen "
                    "is not the one these numbers describe.",
                ),
            )
        )

    # THE AXES, exactly as the projections were measured -- but ONLY when they were measured on the
    # geometry on screen. On a relaxed copy or a regenerated conformer the coordinates differ, and an
    # arrow drawn from the measured frame would sit in the wrong place on the displayed structure.
    spatial = ()
    if shape.principal_axes is not None and shape_mol is mol:
        annotation = AxesAnnotation(
            origin=shape.centroid,
            axes=shape.principal_axes,
            extents=shape.axis_half_spans,
            labels=tuple(
                f"{name}: shadow r {radius:.1f} A"
                for name, radius in zip(("a", "b", "c"), shape.projection_radii)
            ),
        )
        if valid_spatial_annotation(annotation):
            spatial = (annotation,)

    recorded: dict[str, Any] = {
        "method": GEOMETRY_METHOD,
        "energy_unit": options.unit_label,
        "conformer_policy": options.conformer_policy,
        "optimise_mmff": options.optimise_mmff,
        "optimise_projection": options.optimise_projection,
        "optimisation_limit": level_name(options.optimisation_limit),
        "radius_scale": options.radius_scale,
        "orientations_searched": shape.orientations_searched,
        "input_geometry": geometry_fingerprint(mol),
        "measured_geometry": geometry_fingerprint(shape_mol),
    }
    if search is not None:
        recorded.update(
            {
                "conformer_count": options.conformer_count,
                "conformers_tried": search.candidates,
                "conformers_ranked": search.ranked,
                "search_seed": search.seed,
                "search_force_field": search.force_field,
                "supplied_geometry_won": search.supplied_won,
            }
        )
    if relaxed is not None:
        recorded.update({"relaxation_force_field": relaxed.force_field, "relaxation_settled": relaxed.converged})
    return ReportResult(
        molecule_uuid=molecule_uuid,
        report_id="geometry_analysis",
        name="Geometry",
        category="geometry",
        facts=tuple(facts),
        spatial=spatial,
        provenance=Provenance(created_by="core", method="rdkit", parameters=recorded),
    )
