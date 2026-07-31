"""Molecular dipole moment from partial charges and 3D geometry.

mu = SUM q_i * r_i, converted to Debye. Reported as a vector plus its
magnitude, matching what MarvinSketch's Dipole Moment plugin shows.

ORIGIN DEPENDENCE, and why it does not matter here: a point-charge dipole
only has a well-defined value independent of origin when the total charge
is zero. For a charged species it shifts with the choice of origin, so the
centre of mass is used and the ambiguity is stated in the result rather
than being silently swept away by picking an origin and not saying so.

THE CHARGE MODEL IS THE ANSWER'S LIMIT. These are Gasteiger (PEOE)
charges, not ab initio ones, so the number is only as good as that model.
Magnitudes typically land in the right range but are not expected to match
experiment closely -- 1,1-dichloroethene comes out near Marvin's own
Gasteiger-based figure rather than near the experimental value, because
both tools are computing the same approximation. The direction and the
symmetry behaviour are much more reliable than the magnitude, which is why
a symmetric molecule giving ~0 is the test that actually validates this.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdPartialCharges

from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import AlertResult

# elementary charge * angstrom -> Debye. 1 D = 3.33564e-30 C*m;
# e*A = 1.602176634e-19 * 1e-10 C*m.
_E_ANGSTROM_TO_DEBYE = 1.602176634e-19 * 1e-10 / 3.33564e-30


def dipole_vector(mol: Chem.Mol) -> tuple[np.ndarray, float, bool]:
    """Returns (vector in Debye, magnitude, origin_independent).

    `origin_independent` is False for a charged species, where the value
    depends on where the origin is placed.
    """
    conformer = _require_conformer(mol)
    charged = Chem.Mol(mol)
    rdPartialCharges.ComputeGasteigerCharges(charged)

    positions = conformer.GetPositions()
    charges = np.array(
        [
            atom.GetDoubleProp("_GasteigerCharge") if atom.HasProp("_GasteigerCharge") else 0.0
            for atom in charged.GetAtoms()
        ]
    )
    # NaNs appear for atoms Gasteiger has no parameters for; treating them
    # as zero is wrong but silent, so they are zeroed AND flagged by the
    # caller through a total-charge mismatch.
    charges = np.nan_to_num(charges)

    masses = np.array([atom.GetMass() for atom in charged.GetAtoms()])
    centre_of_mass = (positions * masses[:, None]).sum(axis=0) / masses.sum()
    relative = positions - centre_of_mass

    vector = (charges[:, None] * relative).sum(axis=0) * _E_ANGSTROM_TO_DEBYE
    total_charge = Chem.GetFormalCharge(mol)
    return vector, float(np.linalg.norm(vector)), total_charge == 0


def compute_dipole_moment(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "charge" category's Dipole Moment calculator. Needs a conformer:
    a dipole is a property of a 3D arrangement, and computing one from flat
    2D coordinates would produce a confident, meaningless number."""
    try:
        vector, magnitude, origin_independent = dipole_vector(mol)
    except NoConformerError as exc:
        return AlertResult(
            alert_id="dipole_moment",
            name="Dipole Moment",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="charge",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    lines = [
        f"Dipole: {magnitude:.2f} Debye",
        f"Dipole X: {vector[0]:+.2f} Debye",
        f"Dipole Y: {vector[1]:+.2f} Debye",
        f"Dipole Z: {vector[2]:+.2f} Debye",
    ]
    if not origin_independent:
        lines.append(
            "This species carries a net charge, so its dipole depends on the choice of "
            "origin -- computed here about the centre of mass."
        )
    lines.append(
        "From Gasteiger (PEOE) partial charges and this conformer's geometry. Direction and "
        "symmetry are reliable; the magnitude inherits the charge model's accuracy."
    )
    return AlertResult(
        alert_id="dipole_moment",
        name="Dipole Moment",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="charge",
        provenance=Provenance(
            created_by="core",
            method="rdkit",
            parameters={
                "debye": magnitude,
                "vector": [float(v) for v in vector],
                "origin_independent": origin_independent,
            },
        ),
    )
