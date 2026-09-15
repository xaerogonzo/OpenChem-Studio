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
import rdkit
from rdkit import Chem

from openchem.chem.charge_evaluation import CHARGE_MODEL_LABELS, GASTEIGER, ChargeEvaluation, evaluate_charges
from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.chem.calculator_options import decimals
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import ArrowAnnotation, ReportResult, valid_spatial_annotation
from openchem.chem.report_adapter import report_from_fields

#: The application benchmark's sentence per charge model
#: (benchmarks/charges/consumers/dipole_benchmark.py, experiment E2 B), copied
#: from its measured output of 2026-09-15 and pinned by a test against that
#: CSV. Reported, never used to choose a default.
_BENCHMARK_SCOPE = "15 molecules of gasteiger1985 Table I on OpenChem conformers"
DIPOLE_BENCHMARK: dict[str, str] = {
    "gasteiger": f"Against experiment ({_BENCHMARK_SCOPE}): mean absolute error 0.79 D over 15.",
    "eem_bultinck2002_part1": (f"Against experiment ({_BENCHMARK_SCOPE}): mean absolute error 1.79 D over the 14 it "
                               "covers; it overestimates polar molecules."),
    "qeq_rg1991_lambda_half_h_experimental": (f"Against experiment ({_BENCHMARK_SCOPE}): mean absolute error 1.69 D "
                                              "over 15; it overestimates polar molecules."),
}

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


def dipole_from_charges(mol: Chem.Mol, charges: dict[int, float]) -> tuple[np.ndarray, float, bool]:
    """(vector in Debye, magnitude, origin_independent) from charges keyed by `mol`'s atoms.

    EVERY ATOM must have a charge, for the reason `electrostatic_potential_for_conformer`
    gives: a missing one is a net charge the molecule does not have, not a
    smaller effect.
    """
    conformer = _require_conformer(mol)
    missing = [i for i in range(mol.GetNumAtoms()) if i not in charges]
    if missing:
        raise ValueError(f"no charge for {len(missing)} of {mol.GetNumAtoms()} atoms (first: index {missing[0]})")
    positions = conformer.GetPositions()
    values = np.array([charges[i] for i in range(mol.GetNumAtoms())])
    relative = positions - centre_of_mass(mol)
    vector = (values[:, None] * relative).sum(axis=0) * _E_ANGSTROM_TO_DEBYE
    total_charge = Chem.GetFormalCharge(mol)
    return vector, float(np.linalg.norm(vector)), total_charge == 0


def dipole_vector(mol: Chem.Mol, charge_model: str = GASTEIGER) -> tuple[np.ndarray, float, bool]:
    """Returns (vector in Debye, magnitude, origin_independent) under `charge_model`.

    `origin_independent` is False for a charged species, where the value
    depends on where the origin is placed. Raises `ChargesRefused` when the
    model declines the molecule; it never substitutes another model.

    Gasteiger's charges are exactly the ones this function computed before
    other models existed (NaN for an unparameterised atom as zero), which
    `tests/test_charge_consumers.py` pins.
    """
    _require_conformer(mol)
    evaluation = evaluate_charges(mol, charge_model)
    if evaluation.charges is None:
        raise ChargesRefused(evaluation)
    return dipole_from_charges(mol, evaluation.charges)


class ChargesRefused(Exception):
    """The chosen charge model declined this molecule; carries its own evaluation."""

    def __init__(self, evaluation: ChargeEvaluation) -> None:
        super().__init__(evaluation.message or evaluation.refusal)
        self.evaluation = evaluation


def compute_dipole_moment(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "charge" category's Dipole Moment calculator. Needs a conformer:
    a dipole is a property of a 3D arrangement, and computing one from flat
    2D coordinates would produce a confident, meaningless number."""
    charge_model = str((parameters or {}).get("charge_model", GASTEIGER))
    label = CHARGE_MODEL_LABELS.get(charge_model, charge_model)
    try:
        _require_conformer(mol)
        evaluation = evaluate_charges(mol, charge_model, molecule_uuid)
        if evaluation.charges is None:
            raise ChargesRefused(evaluation)
        vector, magnitude, origin_independent = dipole_from_charges(mol, evaluation.charges)
    except NoConformerError as exc:
        return report_from_fields(
            alert_id="dipole_moment",
            name="Dipole Moment",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="charge",
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="rdkit", parameters={"charge_model": charge_model}),
        )
    except ChargesRefused as refused:
        # THE MODEL'S OWN REFUSAL, NAMED, AND NOT A FAULT. Never Gasteiger's
        # dipole under an EEM or QEq heading, which is the one thing a
        # charge-model choice must not do quietly.
        result = report_from_fields(
            alert_id="dipole_moment",
            name=f"Dipole Moment ({label})",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="charge",
            cache_state=CacheState.FAILED,
            error=f"{label} declined this molecule: {refused.evaluation.message or refused.evaluation.refusal}",
            provenance=Provenance(created_by="core", method=charge_model,
                                  parameters={"charge_model": charge_model, "refusal": refused.evaluation.refusal}),
        )
        return dataclasses.replace(result, inapplicable=True)

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
    if charge_model == GASTEIGER:
        lines.append(
            "From Gasteiger (PEOE) partial charges and this conformer's geometry. Direction and "
            "symmetry are reliable; the magnitude inherits the charge model's accuracy."
        )
    else:
        lines.append(
            f"From {label} partial charges on this conformer's geometry. Direction and symmetry are "
            "reliable; the magnitude inherits the charge model's accuracy."
        )
        lines.extend(evaluation.notes)
    benchmark = DIPOLE_BENCHMARK.get(charge_model)
    if benchmark is not None:
        lines.append(benchmark)
    result = report_from_fields(
        alert_id="dipole_moment",
        name="Dipole Moment" if charge_model == GASTEIGER else f"Dipole Moment ({label})",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="charge",
        provenance=Provenance(
            created_by="core",
            method="rdkit" if charge_model == GASTEIGER else charge_model,
            parameters={
                "debye": magnitude,
                "vector": [float(v) for v in vector],
                "origin_independent": origin_independent,
                "charge_model": charge_model,
                "charge_parameter_checksum": evaluation.parameter_checksum,
                "charge_source": evaluation.source_key,
                "claim_kind": evaluation.claim_kind,
                "rdkit_version": rdkit.__version__,
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
