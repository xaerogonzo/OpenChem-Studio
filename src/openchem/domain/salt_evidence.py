"""pKa as an independent salt-composition claim, never a solver input."""

from __future__ import annotations

from dataclasses import dataclass

#: Measured value supplied by the caller. Not a model output.
ORIGIN_MEASURED = "measured"
#: Predicted value supplied by the caller. This module does not run a model.
ORIGIN_PREDICTED = "predicted"

#: Already ionic; the drawing is the state.
VERDICT_NOT_ASSESSED = "not_assessed"
#: A required pKa was not supplied.
VERDICT_MISSING = "missing"
#: Media or temperatures do not match, so ΔpKa is not a constant.
VERDICT_INCOMPARABLE = "incomparable"
#: A value's step_id is not the proposed microspecies.
VERDICT_WRONG_STEP = "wrong_step"
#: Both values named the proposed steps under comparable conditions.
VERDICT_RECORDED = "recorded"


@dataclass(frozen=True)
class PkaValue:
    value: float
    origin: str
    medium: str
    temperature_k: float | None
    ionic_strength: float | None
    uncertainty: float | None
    step_id: str


@dataclass(frozen=True)
class PkaCompatibility:
    verdict: str
    delta: float | None
    acid: PkaValue | None
    conjugate_acid: PkaValue | None
    reason: str


@dataclass(frozen=True)
class EvidenceRecord:
    charge_valid: bool
    structurally_consistent: bool
    pka_compatible: PkaCompatibility
    experimentally_established: None


def assess_pka_compatible(
    *,
    already_charged: bool,
    proposed_acid_step_id: str,
    proposed_conjugate_acid_step_id: str,
    acid: PkaValue | None,
    conjugate_acid: PkaValue | None,
) -> PkaCompatibility:
    if already_charged:
        return PkaCompatibility(
            VERDICT_NOT_ASSESSED,
            None,
            None,
            None,
            "Already-charged input is not pKa-assessed; the state is in the drawing.",
        )
    if acid is None or conjugate_acid is None:
        return PkaCompatibility(
            VERDICT_MISSING,
            None,
            acid,
            conjugate_acid,
            "pKa was not assessed because a value for the proposed step is missing.",
        )
    if acid.step_id != proposed_acid_step_id or conjugate_acid.step_id != proposed_conjugate_acid_step_id:
        return PkaCompatibility(
            VERDICT_WRONG_STEP,
            None,
            acid,
            conjugate_acid,
            "pKa step identity does not match the proposed microspecies.",
        )
    if acid.medium != conjugate_acid.medium or acid.temperature_k != conjugate_acid.temperature_k:
        return PkaCompatibility(
            VERDICT_INCOMPARABLE,
            None,
            acid,
            conjugate_acid,
            "pKa values are not from comparable conditions.",
        )
    return PkaCompatibility(
        VERDICT_RECORDED,
        conjugate_acid.value - acid.value,
        acid,
        conjugate_acid,
        "ΔpKa = pKa(BH+) − pKa(HA) under the stated conditions; this is not a crystal.",
    )
