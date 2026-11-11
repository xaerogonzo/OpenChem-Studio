"""Counts and charges from a molblock already held by the Inspector.

Observational: parse what is stored. Do not protonate, embed, or charge.
Unavailable measurements are ``None``, never zero.
"""

from __future__ import annotations

from typing import Any

from openchem.chem.engine import ChemistryEngine, InvalidStructureError

#: Z-span above this (Å) is treated as genuine 3D coordinates, not a flat drawing.
Z_SPAN_3D_ANGSTROM = 1e-3


def summarize_molblock(
    engine: ChemistryEngine,
    molblock: str | None,
    *,
    with_coordinates: bool = False,
) -> dict[str, Any]:
    """Facts about one molblock. ``present`` is whether text was supplied."""
    empty = {
        "present": False,
        "parse_ok": None,
        "atom_count": None,
        "heavy_atom_count": None,
        "explicit_hydrogen_count": None,
        "net_formal_charge": None,
    }
    if with_coordinates:
        empty["has_3d_coordinates"] = None
        empty["z_span_angstrom"] = None
    if not molblock:
        return empty
    summary: dict[str, Any] = {
        "present": True,
        "parse_ok": False,
        "atom_count": None,
        "heavy_atom_count": None,
        "explicit_hydrogen_count": None,
        "net_formal_charge": None,
    }
    if with_coordinates:
        summary["has_3d_coordinates"] = None
        summary["z_span_angstrom"] = None
    try:
        mol = engine.mol_from_molblock(molblock)
    except (InvalidStructureError, Exception):  # noqa: BLE001 - a dump must not abort the drive
        return summary
    atoms = list(mol.GetAtoms())
    summary["parse_ok"] = True
    summary["atom_count"] = mol.GetNumAtoms()
    summary["heavy_atom_count"] = sum(1 for atom in atoms if atom.GetAtomicNum() > 1)
    summary["explicit_hydrogen_count"] = sum(1 for atom in atoms if atom.GetAtomicNum() == 1)
    summary["net_formal_charge"] = sum(atom.GetFormalCharge() for atom in atoms)
    if with_coordinates:
        if mol.GetNumConformers() == 0:
            summary["has_3d_coordinates"] = False
            summary["z_span_angstrom"] = None
        else:
            zs = [float(mol.GetConformer().GetAtomPosition(i).z) for i in range(mol.GetNumAtoms())]
            span = max(zs) - min(zs) if zs else 0.0
            summary["z_span_angstrom"] = span
            summary["has_3d_coordinates"] = span > Z_SPAN_3D_ANGSTROM
    return summary


def same_if_both(left: int | None, right: int | None) -> bool | None:
    """Equality when both sides were measured; otherwise ``None``."""
    if left is None or right is None:
        return None
    return left == right
