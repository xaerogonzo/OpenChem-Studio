"""QC dipole magnitude and optional vector from engine stdout.

Printed XYZ is atomic units; printed tot / Magnitude (Debye) is Debye.
The vector is attached only when a last complete block validates; a finite
printed magnitude is still stored when the vector is unusable.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import NamedTuple

from rdkit import Chem

from openchem.chem.calculator_options import DEFAULT_DECIMAL_PLACES
from openchem.chem.dipole import _E_ANGSTROM_TO_DEBYE, centre_of_mass
from openchem.chem.submitted_structure import submitted_structure_identity
from openchem.domain.common import CacheState, Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.report import ArrowAnnotation, valid_spatial_annotation

#: Psi4's printed conversion from e a0 to Debye; ORCA and xtb print XYZ in a.u.
AU_TO_DEBYE = 2.5417464519
#: Provenance: engine evaluated the dipole about the centre of mass.
VECTOR_ORIGIN_COM = "center_of_mass"
#: Provenance: engine evaluated the dipole about the job Cartesian origin.
VECTOR_ORIGIN_CARTESIAN = "cartesian_origin"
#: Provenance: components are in the job coordinate axes, not a rotated CMA frame.
VECTOR_FRAME_JOB = "job_cartesian"
#: Absolute slack for |v| vs printed Debye (xtb prints three decimals on tot).
VECTOR_NORM_ABS = 0.005
#: Relative slack; ORCA prints more digits than GFN tables.
VECTOR_NORM_REL = 0.002

#: Last complete ORCA `Total Dipole Moment` plus `Magnitude (Debye)` in that same block.
_ORCA_BLOCK_RE = re.compile(
    r"Total Dipole Moment\s+:\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)"
    r".*?Magnitude \(Debye\)\s+:\s+(-?\d+\.\d+)",
    re.DOTALL,
)
#: ORCA input-echo `Choice of electric origin` line that stamps COM vs unknown.
_ORCA_ELECTRIC_ORIGIN_RE = re.compile(
    r"Choice of electric origin\s+\.\.\.\s+([^\r\n]+)",
)
#: Last Psi4 `Multipole Moments` dipole: Total XYZ then Magnitude, all a.u.
_PSI4_BLOCK_RE = re.compile(
    r"Multipole Moments:.*?"
    r"Dipole X\s+:\s+\S+\s+\S+\s+(-?\S+)\s*\n"
    r"\s*Dipole Y\s+:\s+\S+\s+\S+\s+(-?\S+)\s*\n"
    r"\s*Dipole Z\s+:\s+\S+\s+\S+\s+(-?\S+)\s*\n"
    r"\s*Magnitude\s+:\s+(\S+)",
    re.DOTALL,
)
#: Psi4 `Properties will be evaluated at x, y, z [a0]`; `(0,0,0)` is cartesian origin.
_PSI4_ORIGIN_RE = re.compile(
    r"Properties will be evaluated at\s+(-?\d+\.\d+),\s+(-?\d+\.\d+),\s+(-?\d+\.\d+)\s+\[a0\]",
)
#: GFN1 `dipole moment from electron density` XYZ in a.u. and `total (Debye)`.
_XTB_GFN1_RE = re.compile(
    r"dipole moment from electron density \(au\).*?"
    r"(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+total \(Debye\):\s+(-?\d+\.\d+)",
    re.DOTALL | re.IGNORECASE,
)
#: GFN2 `molecular dipole` `full` row XYZ and tot (Debye); never the `q only` row.
_XTB_GFN2_RE = re.compile(
    r"molecular dipole:\s*\n[^\n]*tot \(Debye\)[^\n]*\n"
    r"[^\n]*q only:[^\n]*\n"
    r"\s*full:\s+(-?\S+)\s+(-?\S+)\s+(-?\S+)\s+(-?\d+\.\d+)",
    re.IGNORECASE,
)


def au_components_to_debye(x_au: float, y_au: float, z_au: float) -> tuple[float, float, float]:
    """Three a.u. components as Debye."""
    return (x_au * AU_TO_DEBYE, y_au * AU_TO_DEBYE, z_au * AU_TO_DEBYE)


def vector_matches_magnitude(vector_debye: tuple[float, float, float], magnitude_debye: float) -> bool:
    """Whether hypot(vector) agrees with the printed Debye magnitude."""
    if not math.isfinite(magnitude_debye):
        return False
    if any(not math.isfinite(part) for part in vector_debye):
        return False
    norm = math.hypot(vector_debye[0], math.hypot(vector_debye[1], vector_debye[2]))
    allowed = max(VECTOR_NORM_ABS, VECTOR_NORM_REL * max(abs(magnitude_debye), 1.0))
    return abs(norm - magnitude_debye) <= allowed


def dipole_descriptor(
    provider_id: str,
    molecule_uuid: str,
    magnitude_debye: float | None,
    provenance: Provenance,
    mol: Chem.Mol,
    *,
    vector_au: tuple[float, float, float] | None = None,
    vector_origin: str | None = None,
) -> DescriptorValue | None:
    """`{provider}.dipole_moment` in Debye; vector provenance only when complete."""
    if magnitude_debye is None or not math.isfinite(magnitude_debye):
        return None
    parameters = {
        **provenance.parameters,
        "origin_independent": Chem.GetFormalCharge(mol) == 0,
    }
    if (
        vector_au is not None
        and vector_origin in {VECTOR_ORIGIN_COM, VECTOR_ORIGIN_CARTESIAN}
        and all(math.isfinite(part) for part in vector_au)
    ):
        vector_debye = au_components_to_debye(*vector_au)
        if vector_matches_magnitude(vector_debye, magnitude_debye):
            parameters["vector"] = [float(part) for part in vector_debye]
            parameters["vector_origin"] = vector_origin
            parameters["vector_frame"] = VECTOR_FRAME_JOB
    return DescriptorValue(
        descriptor_id=f"{provider_id}.dipole_moment",
        name="Dipole",
        units="Debye",
        category="quantum_chemistry",
        provider=provider_id,
        molecule_uuid=molecule_uuid,
        value=magnitude_debye,
        timestamp=provenance.timestamp,
        cache_state=CacheState.COMPLETED,
        provenance=replace(provenance, parameters=parameters),
    )


def parse_orca_dipole(output_text: str) -> tuple[float | None, tuple[float, float, float] | None, str | None]:
    """Last complete ORCA dipole: Debye magnitude, a.u. XYZ, origin vocabulary."""
    matches = list(_ORCA_BLOCK_RE.finditer(output_text))
    if not matches:
        return None, None, None
    match = matches[-1]
    magnitude = float(match.group(4))
    vector_au = (float(match.group(1)), float(match.group(2)), float(match.group(3)))
    origin_hits = list(_ORCA_ELECTRIC_ORIGIN_RE.finditer(output_text, 0, match.start()))
    origin = None
    if origin_hits:
        label = origin_hits[-1].group(1).strip().lower()
        if label in {"center of mass", "centre of mass"}:
            origin = VECTOR_ORIGIN_COM
    return magnitude, vector_au, origin


def parse_psi4_dipole(output_text: str) -> tuple[float | None, tuple[float, float, float] | None, str | None]:
    """Last complete Multipole Moments block: Total XYZ and Magnitude in a.u."""
    matches = list(_PSI4_BLOCK_RE.finditer(output_text))
    if not matches:
        return None, None, None
    match = matches[-1]
    try:
        x_au, y_au, z_au = float(match.group(1)), float(match.group(2)), float(match.group(3))
        magnitude_au = float(match.group(4))
    except ValueError:
        return None, None, None
    if not math.isfinite(magnitude_au):
        return None, None, None
    origin_hits = list(_PSI4_ORIGIN_RE.finditer(output_text, 0, match.start()))
    origin = None
    if origin_hits:
        ox, oy, oz = (float(origin_hits[-1].group(i)) for i in (1, 2, 3))
        if max(abs(ox), abs(oy), abs(oz)) < 1e-8:
            origin = VECTOR_ORIGIN_CARTESIAN
    magnitude = magnitude_au * AU_TO_DEBYE
    return magnitude, (x_au, y_au, z_au), origin


def parse_xtb_dipole(output_text: str) -> tuple[float | None, tuple[float, float, float] | None, str | None]:
    """Last GFN1 or GFN2 dipole occurrence; `full` row for GFN2, never `q only`."""
    candidates: list[tuple[int, float, tuple[float, float, float]]] = []
    for match in _XTB_GFN1_RE.finditer(output_text):
        candidates.append(
            (
                match.start(),
                float(match.group(4)),
                (float(match.group(1)), float(match.group(2)), float(match.group(3))),
            )
        )
    for match in _XTB_GFN2_RE.finditer(output_text):
        try:
            vector = (float(match.group(1)), float(match.group(2)), float(match.group(3)))
        except ValueError:
            continue
        candidates.append((match.start(), float(match.group(4)), vector))
    if not candidates:
        return None, None, None
    candidates.sort(key=lambda item: item[0])
    _start, magnitude, vector_au = candidates[-1]
    return magnitude, vector_au, VECTOR_ORIGIN_CARTESIAN


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
    input_identity = submitted_structure_identity(input_block)
    output_identity = submitted_structure_identity(block)
    if not input_identity or input_identity != output_identity:
        return None
    return block


class _ComReferencedDipole(NamedTuple):
    vector: tuple[float, float, float]
    magnitude: float


def com_referenced_dipole_debye(run, molblock: str | None) -> float | None:
    """Debye magnitude under the COM convention, or None. Does not rewrite the stored descriptor."""
    descriptor = _unique_dipole_descriptor(run)
    stored = _stored_debye(descriptor)
    if stored is None:
        return None
    charge = int(getattr(run, "charge", 0) or 0)
    if charge == 0:
        return stored
    normalized = _com_referenced_dipole(run, molblock)
    return None if normalized is None else normalized.magnitude


def dipole_arrow_for_run(run, molblock: str | None) -> ArrowAnnotation | None:
    """COM-referenced Debye arrow for `{provider}.dipole_moment`, or nothing."""
    if not molblock:
        return None
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return None
    normalized = _com_referenced_dipole(run, molblock)
    if normalized is None:
        return None
    if round(normalized.magnitude, DEFAULT_DECIMAL_PLACES) <= 0:
        return None
    com = centre_of_mass(mol)
    annotation = ArrowAnnotation(
        anchor=tuple(float(part) for part in com),
        vector=tuple(float(part) for part in normalized.vector),
        units="D",
        label=f"{normalized.magnitude:.{DEFAULT_DECIMAL_PLACES}f} D",
    )
    if not valid_spatial_annotation(annotation):
        return None
    return annotation


def _com_referenced_dipole(run, molblock: str | None) -> _ComReferencedDipole | None:
    descriptor = _unique_dipole_descriptor(run)
    stored = _stored_debye(descriptor)
    if descriptor is None or stored is None:
        return None
    params = getattr(getattr(descriptor, "provenance", None), "parameters", None) or {}
    origin = params.get("vector_origin")
    frame = params.get("vector_frame")
    if frame != VECTOR_FRAME_JOB:
        return None
    if origin not in {VECTOR_ORIGIN_COM, VECTOR_ORIGIN_CARTESIAN}:
        return None
    vector = _three_finite(params.get("vector"))
    if vector is None:
        return None
    if not vector_matches_magnitude(vector, stored):
        return None
    charge = int(getattr(run, "charge", 0) or 0)
    if origin == VECTOR_ORIGIN_COM or charge == 0:
        return _ComReferencedDipole(vector, stored)
    if not molblock:
        return None
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return None
    try:
        com = centre_of_mass(mol)
    except Exception:  # noqa: BLE001 — unusable geometry is fail-closed
        return None
    translated = tuple(
        float(vector[i] - charge * _E_ANGSTROM_TO_DEBYE * float(com[i]))
        for i in range(3)
    )
    if any(not math.isfinite(part) for part in translated):
        return None
    magnitude = math.hypot(translated[0], math.hypot(translated[1], translated[2]))
    if not math.isfinite(magnitude):
        return None
    return _ComReferencedDipole(translated, magnitude)


def _unique_dipole_descriptor(run) -> DescriptorValue | None:
    provider = str(getattr(run, "provider", "") or "")
    wanted = f"{provider}.dipole_moment"
    matches: list[DescriptorValue] = []
    for item in list(getattr(run, "results", {}).get("descriptors") or ()):
        if (
            isinstance(item, DescriptorValue)
            and getattr(item, "descriptor_id", "") == wanted
            and getattr(item, "provider", "") == provider
        ):
            matches.append(item)
    if len(matches) != 1:
        return None
    return matches[0]


def _stored_debye(descriptor: DescriptorValue | None) -> float | None:
    if descriptor is None or descriptor.units != "Debye":
        return None
    value = descriptor.value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


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
