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

import dataclasses
from typing import Any

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdPartialCharges

from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import ArrowAnnotation, ReportResult, valid_spatial_annotation
from openchem.chem.report_adapter import report_fields

# elementary charge * angstrom -> Debye. 1 D = 3.33564e-30 C*m;
# e*A = 1.602176634e-19 * 1e-10 C*m.
_E_ANGSTROM_TO_DEBYE = 1.602176634e-19 * 1e-10 / 3.33564e-30


def centre_of_mass(mol: Chem.Mol) -> np.ndarray:
    """Mass-weighted centroid of the current conformer, in Angstrom.

    Public because it is both the origin the dipole is computed about and
    the anchor the drawn arrow hangs on -- one function, so the two cannot
    drift apart.
    """
    conformer = _require_conformer(mol)
    positions = conformer.GetPositions()
    masses = np.array([atom.GetMass() for atom in mol.GetAtoms()])
    return (positions * masses[:, None]).sum(axis=0) / masses.sum()


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

    relative = positions - centre_of_mass(charged)

    vector = (charges[:, None] * relative).sum(axis=0) * _E_ANGSTROM_TO_DEBYE
    total_charge = Chem.GetFormalCharge(mol)
    return vector, float(np.linalg.norm(vector)), total_charge == 0


def compute_dipole_moment(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "charge" category's Dipole Moment calculator. Needs a conformer:
    a dipole is a property of a 3D arrangement, and computing one from flat
    2D coordinates would produce a confident, meaningless number."""
    try:
        vector, magnitude, origin_independent = dipole_vector(mol)
    except NoConformerError as exc:
        return _report(
            alert_id="dipole_moment",
            name="Dipole Moment",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="charge",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit"),
        )

    places = decimals(parameters)
    lines = [
        f"Dipole: {magnitude:.{places}f} Debye",
        f"Dipole X: {vector[0]:+.{places}f} Debye",
        f"Dipole Y: {vector[1]:+.{places}f} Debye",
        f"Dipole Z: {vector[2]:+.{places}f} Debye",
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
    result = _report(
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
    # THE ARROW, only when there is one. A magnitude that rounds to zero
    # at the displayed precision means the direction is numerical noise --
    # a symmetric molecule's "dipole" points wherever float error leans --
    # and drawing noise dresses it up as a result. Tying the rule to the
    # DISPLAYED precision keeps text and picture coherent: "Dipole: 0.00"
    # beside an arrow would be the panel disagreeing with itself.
    #
    # The vector is in DEBYE and the anchor in Angstrom, per the
    # `ArrowAnnotation` contract: the renderer owns the display scaling,
    # and the anchor (the centre of mass the dipole was computed about)
    # is a display choice, not physics -- a neutral molecule's dipole is
    # origin-independent.
    if round(magnitude, places) > 0:
        annotation = ArrowAnnotation(
            anchor=tuple(float(v) for v in centre_of_mass(mol)),
            vector=tuple(float(v) for v in vector),
            units="D",
            label=f"{magnitude:.{places}f} D",
        )
        if valid_spatial_annotation(annotation):
            result = dataclasses.replace(result, spatial=(annotation,))
    return result


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
