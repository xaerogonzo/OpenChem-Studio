import pytest

from openchem.domain.salt_evidence import (
    ORIGIN_MEASURED,
    VERDICT_INCOMPARABLE,
    VERDICT_MISSING,
    VERDICT_NOT_ASSESSED,
    VERDICT_RECORDED,
    VERDICT_WRONG_STEP,
    PkaValue,
    assess_pka_compatible,
)


def _acetic() -> PkaValue:
    return PkaValue(4.76, ORIGIN_MEASURED, "water", 298.15, None, None, "acetic_acid_h1")


def _pyridinium() -> PkaValue:
    return PkaValue(5.23, ORIGIN_MEASURED, "water", 298.15, None, None, "pyridine_bh1")


def test_already_charged_input_is_not_assessed() -> None:
    result = assess_pka_compatible(
        already_charged=True,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=_acetic(),
        conjugate_acid=_pyridinium(),
    )
    assert result.verdict == VERDICT_NOT_ASSESSED
    assert result.delta is None


def test_missing_pka_is_missing_not_invented() -> None:
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=_acetic(),
        conjugate_acid=None,
    )
    assert result.verdict == VERDICT_MISSING
    assert result.delta is None


def test_delta_is_conjugate_acid_minus_acid() -> None:
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=_acetic(),
        conjugate_acid=_pyridinium(),
    )
    assert result.verdict == VERDICT_RECORDED
    assert result.delta == pytest.approx(0.47)


def test_sulfate_must_not_reuse_the_first_sulfuric_pka() -> None:
    sulfuric_h1 = PkaValue(-3.0, ORIGIN_MEASURED, "water", 298.15, None, None, "sulfuric_h1")
    pyridine = _pyridinium()
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="sulfuric_h2",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=sulfuric_h1,
        conjugate_acid=pyridine,
    )
    assert result.verdict == VERDICT_WRONG_STEP
    assert result.delta is None


def test_bh2_must_not_reuse_the_first_conjugate_acid_pka() -> None:
    bh1 = PkaValue(9.9, ORIGIN_MEASURED, "water", 298.15, None, None, "en_bh1")
    acetic = _acetic()
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="en_bh2",
        acid=acetic,
        conjugate_acid=bh1,
    )
    assert result.verdict == VERDICT_WRONG_STEP


def test_different_media_are_incomparable() -> None:
    dmso = PkaValue(12.3, ORIGIN_MEASURED, "DMSO", 298.15, None, None, "acetic_acid_h1")
    result = assess_pka_compatible(
        already_charged=False,
        proposed_acid_step_id="acetic_acid_h1",
        proposed_conjugate_acid_step_id="pyridine_bh1",
        acid=dmso,
        conjugate_acid=_pyridinium(),
    )
    assert result.verdict == VERDICT_INCOMPARABLE
    assert result.delta is None
