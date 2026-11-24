"""Quantum-history dipole overlay on that run's geometry, not a live calculator."""

from __future__ import annotations

import math

from rdkit import Chem

from openchem.chem.calculator_options import DEFAULT_DECIMAL_PLACES
from openchem.chem.dipole import _E_ANGSTROM_TO_DEBYE, centre_of_mass
from openchem.chem.qc_dipole import (
    VECTOR_FRAME_JOB,
    VECTOR_ORIGIN_CARTESIAN,
    VECTOR_ORIGIN_COM,
    vector_matches_magnitude,
)
from openchem.domain.report import ArrowAnnotation, valid_spatial_annotation

#: Jobs whose overlay geometry is the stored output conformer, never the input molblock.
_OPT_TYPES = frozenset({"opt", "opt_freq"})


def run_geometry_molblock(run, molecule) -> str | None:
    """Exact molblock this Quantum run owns, or None. Never the canonical conformer."""
    if getattr(run, "calc_type", "") == "sp":
        return _usable_molblock(getattr(run, "input_molblock", "") or "")
    if getattr(run, "calc_type", "") not in _OPT_TYPES:
        return None
    conformer_id = getattr(run, "output_conformer_id", None)
    if not conformer_id or molecule is None:
        return None
    found = None
    for conformer in getattr(molecule, "conformers", ()) or ():
        if getattr(conformer, "conformer_id", None) == conformer_id:
            found = getattr(conformer, "molblock", "") or ""
            break
    block = _usable_molblock(found or "")
    if block is None:
        return None
    input_block = getattr(run, "input_molblock", "") or ""
    input_mol = Chem.MolFromMolBlock(input_block, removeHs=False) if input_block.strip() else None
    if input_mol is not None:
        output_mol = Chem.MolFromMolBlock(block, removeHs=False)
        if output_mol is None or output_mol.GetNumAtoms() != input_mol.GetNumAtoms():
            return None
    return block


def dipole_arrow_for_run(run, molblock: str | None) -> ArrowAnnotation | None:
    """COM-referenced Debye arrow for `{provider}.dipole_moment`, or nothing."""
    if not molblock:
        return None
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return None
    descriptor = _dipole_descriptor(run)
    if descriptor is None:
        return None
    params = getattr(getattr(descriptor, "provenance", None), "parameters", None) or {}
    raw = params.get("vector")
    origin = params.get("vector_origin")
    frame = params.get("vector_frame")
    if frame != VECTOR_FRAME_JOB:
        return None
    if origin not in {VECTOR_ORIGIN_COM, VECTOR_ORIGIN_CARTESIAN}:
        return None
    vector = _three_finite(raw)
    if vector is None:
        return None
    magnitude = descriptor.value
    if not isinstance(magnitude, (int, float)) or isinstance(magnitude, bool) or not math.isfinite(magnitude):
        return None
    if descriptor.units != "Debye":
        return None
    if not vector_matches_magnitude(vector, float(magnitude)):
        return None
    if round(float(magnitude), DEFAULT_DECIMAL_PLACES) <= 0:
        return None
    charge = int(getattr(run, "charge", 0) or 0)
    if origin == VECTOR_ORIGIN_CARTESIAN and charge != 0:
        com = centre_of_mass(mol)
        vector = tuple(
            float(vector[i] - charge * _E_ANGSTROM_TO_DEBYE * float(com[i]))
            for i in range(3)
        )
    elif origin == VECTOR_ORIGIN_CARTESIAN and charge == 0:
        pass
    elif origin == VECTOR_ORIGIN_COM:
        pass
    else:
        return None
    com = centre_of_mass(mol)
    annotation = ArrowAnnotation(
        anchor=tuple(float(part) for part in com),
        vector=tuple(float(part) for part in vector),
        units="D",
        label=f"{float(magnitude):.{DEFAULT_DECIMAL_PLACES}f} D",
    )
    if not valid_spatial_annotation(annotation):
        return None
    return annotation


def _dipole_descriptor(run):
    provider = str(getattr(run, "provider", "") or "")
    wanted = f"{provider}.dipole_moment"
    for item in list(getattr(run, "results", {}).get("descriptors") or ()):
        if (
            getattr(item, "descriptor_id", "") == wanted
            and getattr(item, "provider", "") == provider
        ):
            return item
    return None


def _three_finite(raw) -> tuple[float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    parts = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        parts.append(float(value))
    return (parts[0], parts[1], parts[2])


def _usable_molblock(molblock: str) -> str | None:
    if not molblock.strip():
        return None
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None or mol.GetNumAtoms() == 0 or mol.GetNumConformers() == 0:
        return None
    positions = mol.GetConformer().GetPositions()
    if not all(math.isfinite(float(part)) for row in positions for part in row):
        return None
    return molblock
