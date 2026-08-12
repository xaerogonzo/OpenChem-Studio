"""Molecular surface areas from a 3D conformer.

Solvent-accessible surface area comes from RDKit's `rdFreeSASA`, which
writes a per-atom `SASA` property on every atom as a side effect of the
total -- so the per-atom breakdown Marvin shows costs nothing extra.

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
from rdkit.Chem import AllChem, rdFreeSASA

from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.chem.calculator_options import atom_basis_of, decimals
from openchem.chem.projection_geometry import van_der_waals_volume
from openchem.domain.common import ATOM_BASIS, TOTAL, CacheState, Provenance, declare_total
from openchem.domain.report import ReportResult
from openchem.chem.report_adapter import report_fields
from openchem.domain.scientific_result import PerAtomDataset

# Same set pose_analysis.py treats as hydrogen-bond capable -- one
# definition of "polar" across the codebase rather than two that drift.
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


def per_atom_sasa(mol: Chem.Mol) -> dict[int, float]:
    """Solvent-accessible surface area per atom, Å².

    `CalcSASA` must be called for the per-atom `SASA` properties to exist;
    reading them without it silently yields nothing.
    """
    _require_conformer(mol)
    radii = rdFreeSASA.classifyAtoms(mol)
    rdFreeSASA.CalcSASA(mol, radii)
    return {
        atom.GetIdx(): float(atom.GetProp("SASA")) if atom.HasProp("SASA") else 0.0
        for atom in mol.GetAtoms()
    }


def surface_areas(mol: Chem.Mol) -> dict[str, float]:
    """Total accessible surface plus Marvin's four sub-splits, and the
    van der Waals volume."""
    areas = per_atom_sasa(mol)
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
        # Was `AllChem.ComputeMolVolume(mol)` -- the GRID routine, which
        # measures about 0.5% high on aspirin and 5% low on a lone atom.
        # `van_der_waals_volume` returns the analytic one and cross-checks
        # it against that same grid, so this is the identical quantity
        # computed exactly rather than a second, disagreeing estimate.
        "vdw_volume": van_der_waals_volume(mol)[0],
    }


def compute_surface_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "surface" category's Molecular Surface Area (3D) calculator."""
    try:
        areas = surface_areas(mol)
    except NoConformerError as exc:
        return _report(
            alert_id="surface_analysis",
            name="Molecular Surface Area (3D)",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="surface",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )
    places = decimals(parameters)
    return _report(
        alert_id="surface_analysis",
        name="Molecular Surface Area (3D)",
        molecule_uuid=molecule_uuid,
        matched=[
            f"ASA (solvent accessible): {areas['asa']:.{places}f} Å²",
            f"ASA+ (positively charged atoms): {areas['asa_positive']:.{places}f} Å²",
            f"ASA- (negatively charged atoms): {areas['asa_negative']:.{places}f} Å²",
            f"ASA_H (hydrophobic): {areas['asa_hydrophobic']:.{places}f} Å²",
            f"ASA_P (polar): {areas['asa_polar']:.{places}f} Å²",
            f"van der Waals volume: {areas['vdw_volume']:.{places}f} Å³",
        ],
        category="surface",
        provenance=Provenance(created_by="core", method="rdkit"),
    )


def compute_sasa_dataset(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """Per-atom accessible surface area -- which atoms are actually exposed
    to solvent, projected onto the 2D depiction and the 3D surface."""
    _places = decimals(parameters)
    try:
        values = per_atom_sasa(mol)
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
