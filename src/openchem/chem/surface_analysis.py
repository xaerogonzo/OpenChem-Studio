"""Molecular surface areas from a 3D conformer.

Solvent-accessible surface area is computed by `chem/sasa.py` (Shrake-Rupley on a deterministic
point set, about 0.3% from a 200,000-point reference); it yields one area per atom, so the per-atom
breakdown Marvin shows costs nothing extra.

**THE RADII ARE PASSED IN, AND THAT IS NOT A DETAIL.** Until 2026-10-10 this called
`rdFreeSASA.classifyAtoms(mol)` and used what came back. That classifier looks atoms up by
PDB residue and atom NAME, and a molecule that did not come from a PDB file has neither, so it
returned a radius of ZERO for every atom. The calculation then ran on points: ethanol read 97 A^2
where Bondi radii give 199, benzene 127 where they give 234, water 41 where they give 124 -- a
fraction of the true figure, plausible-looking, and ordered correctly (a longer chain still read
larger), which is why the tests that compared one molecule with another never noticed. The radii
are now RDKit's own Bondi table, the same one the van der Waals volume, surface and projections
use, so there is one definition of "how big is an atom" across the application.

Marvin additionally splits the accessible surface into ASA+/ASA- (by
partial-charge sign) and ASA_H/ASA_P (hydrophobic vs polar). Both are
sums of the same per-atom values over different atom subsets, so they come
essentially free once the per-atom areas exist. The polarity split uses
the same "polar element" notion `pose_analysis` already applies to hydrogen
bonding (N/O/F, plus hydrogens attached to them), rather than inventing a
second definition.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.chem.calculator_options import (
    atom_basis_of,
    decimals,
    microspecies_note,
    microspecies_parameters,
)
from openchem.chem.projection_geometry import van_der_waals_surface_area, van_der_waals_volume
from openchem.chem.protonation_geometry import protonate_conformer
from openchem.chem.sasa import accessible_areas
from openchem.domain.calculator import CalculatorParameter
from openchem.domain.common import ATOM_BASIS, TOTAL, CacheState, Provenance, declare_total
from openchem.domain.result_store import SURFACE_METHOD as _SURFACE_METHOD
from openchem.domain.report import ReportResult
from openchem.chem.report_adapter import report_from_fields
from openchem.domain.scientific_result import PerAtomDataset

#: The probe radius, in Angstrom: a water molecule's, which is what "solvent accessible" means by
#: default and what ChemAxon's `asa` takes as its default.
DEFAULT_SOLVENT_RADIUS = 1.4

#: The bounds a probe radius may take. Zero is the van der Waals surface itself (nothing probes it);
#: five is larger than any solvent molecule worth asking about, and keeps a typo from becoming a
#: surface that covers the molecule.
_MIN_SOLVENT_RADIUS = 0.0
#: The largest probe radius accepted, in Angstrom (the reason is in the block above).
_MAX_SOLVENT_RADIUS = 5.0

#: RDKit's periodic table, asked for its Bondi van der Waals radii.
_PERIODIC_TABLE = Chem.GetPeriodicTable()

#: Declared with the other result methods in `result_store`, which must not import this layer.
SURFACE_METHOD = _SURFACE_METHOD


def solvent_radius_parameter() -> CalculatorParameter:
    return CalculatorParameter(
        name="solvent_radius", label="Solvent probe radius (A)", kind="float",
        default=DEFAULT_SOLVENT_RADIUS, minimum=_MIN_SOLVENT_RADIUS, maximum=_MAX_SOLVENT_RADIUS,
    )


def surface_parameters() -> list[CalculatorParameter]:
    """The settings of the whole-molecule surface calculator, after Decimal places."""
    return [solvent_radius_parameter(), *microspecies_parameters()]


def solvent_radius(parameters: dict[str, Any] | None) -> float:
    """The probe radius asked for; anything unusable is the default rather than an error."""
    try:
        value = float((parameters or {}).get("solvent_radius", DEFAULT_SOLVENT_RADIUS))
    except (TypeError, ValueError):
        return DEFAULT_SOLVENT_RADIUS
    if not _MIN_SOLVENT_RADIUS <= value <= _MAX_SOLVENT_RADIUS:
        return DEFAULT_SOLVENT_RADIUS
    return value


def atomic_radii(mol: Chem.Mol) -> list[float]:
    """The van der Waals radius of every atom, RDKit's Bondi table: one definition across the app."""
    return [_PERIODIC_TABLE.GetRvdw(atom.GetAtomicNum()) for atom in mol.GetAtoms()]


#: Same set pose_analysis.py treats as hydrogen-bond capable -- one
#: definition of "polar" across the codebase rather than two that drift.
_POLAR_ELEMENTS = {"N", "O", "F"}


def _is_polar(atom: Chem.Atom) -> bool:
    if atom.GetSymbol() in _POLAR_ELEMENTS:
        return True
    # A hydrogen is polar when it sits on a polar heavy atom (O-H, N-H) --
    # it is the hydrogen-bond donor, and counting it as hydrophobic would
    # misattribute a hydroxyl's surface.
    if atom.GetSymbol() == "H":
        return any(neighbor.GetSymbol() in _POLAR_ELEMENTS for neighbor in atom.GetNeighbors())
    return False


def per_atom_sasa(mol: Chem.Mol, probe: float = DEFAULT_SOLVENT_RADIUS) -> dict[int, float]:
    """Solvent-accessible surface area per atom, Å², for a probe of radius `probe`.

    `CalcSASA` must be called for the per-atom `SASA` properties to exist;
    reading them without it silently yields nothing. Lee-Richards slicing, so a diatomic is within
    about 1% of its closed form and a lone sphere is exact.
    """
    conformer = _require_conformer(mol)
    areas = accessible_areas(conformer.GetPositions(), atomic_radii(mol), probe)
    return {atom.GetIdx(): float(areas[atom.GetIdx()]) for atom in mol.GetAtoms()}


def surface_areas(mol: Chem.Mol, probe: float = DEFAULT_SOLVENT_RADIUS) -> dict[str, float]:
    """Total accessible surface plus Marvin's four sub-splits, the van der Waals surface and the
    van der Waals volume."""
    areas = per_atom_sasa(mol, probe)
    total = sum(areas.values())

    # Gasteiger charges for the +/- split. Computed on a copy so the
    # caller's molecule doesn't silently acquire charge properties.
    charged = Chem.Mol(mol)
    try:
        AllChem.ComputeGasteigerCharges(charged)
        charges = {
            atom.GetIdx(): float(atom.GetProp("_GasteigerCharge"))
            for atom in charged.GetAtoms()
            if atom.HasProp("_GasteigerCharge")
        }
    except (ValueError, RuntimeError):
        charges = {}

    positive = sum(area for index, area in areas.items() if charges.get(index, 0.0) > 0)
    negative = sum(area for index, area in areas.items() if charges.get(index, 0.0) < 0)
    polar = sum(area for index, area in areas.items() if _is_polar(mol.GetAtomWithIdx(index)))
    hydrophobic = total - polar

    return {
        "asa": total,
        "asa_positive": positive,
        "asa_negative": negative,
        "asa_hydrophobic": hydrophobic,
        "asa_polar": polar,
        # The surface of the fused spheres themselves, no probe: Marvin's `vdwsa`.
        "vdw_area": van_der_waals_surface_area(mol),
        # Was `AllChem.ComputeMolVolume(mol)` -- the GRID routine, which
        # measures about 0.5% high on aspirin and 5% low on a lone atom.
        # `van_der_waals_volume` returns the analytic one and cross-checks
        # it against that same grid, so this is the identical quantity
        # computed exactly rather than a second, disagreeing estimate.
        "vdw_volume": van_der_waals_volume(mol)[0],
    }


def _surface_failure(molecule_uuid: str, error: str) -> ReportResult:
    return report_from_fields(
        alert_id="surface_analysis",
        name="Molecular Surface Area (3D)",
        molecule_uuid=molecule_uuid,
        matched=[],
        category="surface",
        cache_state=CacheState.FAILED,
        error=error,
        provenance=Provenance(created_by="core", method="rdkit"),
    )


def compute_surface_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "surface" category's Molecular Surface Area (3D) calculator.

    Two options beyond the decimals, both ChemAxon's: the solvent probe's radius, and the major
    microspecies at a pH. **The microspecies changes the structure, so the geometry is the stored
    conformer's with its protons moved** (`protonation_geometry`): every heavy atom keeps its
    coordinates and only a hydrogen the new state adds is placed. A structure for which that cannot
    be done is a refusal that says why, never a surface of a different molecule.
    """
    parameters = parameters or {}
    places = decimals(parameters)
    probe = solvent_radius(parameters)
    notes: list[str] = []
    recorded: dict[str, Any] = {"solvent_radius": probe, "radii": "bondi", "method": SURFACE_METHOD}
    try:
        _require_conformer(mol)
        if parameters.get("major_microspecies"):
            ph = float(parameters.get("pH", 7.4))
            state = protonate_conformer(mol, ph)
            if state.refusal:
                return _surface_failure(
                    molecule_uuid, state.message or "The structure at that pH could not be built from this conformer."
                )
            mol = state.mol
            notes = microspecies_note(parameters)
            notes.append(
                "That differs from the structure as it is." if state.changed
                else "That is the structure as it is: it is already the dominant form at this pH."
            )
            recorded.update({"major_microspecies": True, "pH": ph, "state_changed": bool(state.changed)})
        areas = surface_areas(mol, probe)
    except NoConformerError as exc:
        return _surface_failure(molecule_uuid, str(exc))
    asa = "ASA (solvent accessible)" if probe == DEFAULT_SOLVENT_RADIUS else f"ASA (solvent accessible, {probe:g} Å probe)"
    return report_from_fields(
        alert_id="surface_analysis",
        name="Molecular Surface Area (3D)",
        molecule_uuid=molecule_uuid,
        matched=[
            f"{asa}: {areas['asa']:.{places}f} Å²",
            f"ASA+ (positively charged atoms): {areas['asa_positive']:.{places}f} Å²",
            f"ASA- (negatively charged atoms): {areas['asa_negative']:.{places}f} Å²",
            f"ASA_H (hydrophobic): {areas['asa_hydrophobic']:.{places}f} Å²",
            f"ASA_P (polar): {areas['asa_polar']:.{places}f} Å²",
            f"van der Waals surface area: {areas['vdw_area']:.{places}f} Å²",
            f"van der Waals volume: {areas['vdw_volume']:.{places}f} Å³",
            *notes,
        ],
        category="surface",
        provenance=Provenance(created_by="core", method="rdkit", parameters=recorded),
    )


def compute_sasa_dataset(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """Per-atom accessible surface area -- which atoms are actually exposed
    to solvent, projected onto the 2D depiction and the 3D surface."""
    _places = decimals(parameters)
    probe = solvent_radius(parameters)
    try:
        values = per_atom_sasa(mol, probe)
    except NoConformerError as exc:
        return PerAtomDataset(
            property_id="atom_sasa",
            name="Accessible Surface Area (per atom)",
            units="Å²",
            method="rdkit",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit", parameters={"decimal_places": _places}),
        )
    return PerAtomDataset(
        property_id="atom_sasa",
        name="Accessible Surface Area (per atom)",
        units="Å²",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={
                "decimal_places": _places,
                "solvent_radius": probe,
                "radii": "bondi",
                "method": SURFACE_METHOD,
                ATOM_BASIS: atom_basis_of(mol),
                # SASA really is additive over atoms -- the accessible
                # surface is partitioned between them with nothing left
                # over -- so here the sum IS the molecular quantity. It
                # still has to be declared: a consumer may not work that
                # out from the numbers, and "Overall: 220.7" never said
                # what 220.7 was.
                TOTAL: declare_total(
                    sum(values.values()),
                    "Total accessible surface area",
                    units="Å²",
                    basis=atom_basis_of(mol),
                ),
            },
        ),
    )
