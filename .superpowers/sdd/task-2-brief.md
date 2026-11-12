### Task 2: Domain pKa evidence (annotation only)

**Files:**
- Create: `src/openchem/domain/salt_evidence.py`
- Test: `tests/test_salt_evidence.py`

**Interfaces:**
- Consumes: nothing from `balance_two`
- Produces:

```python
ORIGIN_MEASURED = "measured"
ORIGIN_PREDICTED = "predicted"

VERDICT_NOT_ASSESSED = "not_assessed"
VERDICT_MISSING = "missing"
VERDICT_INCOMPARABLE = "incomparable"
VERDICT_WRONG_STEP = "wrong_step"
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
    ...
```

`ΔpKa = pKa(BH+) − pKa(HA)` when both values are recorded under comparable conditions and each `step_id` matches the proposed microspecies. Store `delta`; do not turn it into `supported`.

Comparable: same `medium` string, and `temperature_k` equal (including both `None`). Ionic strength may differ without forcing `incomparable` (the record still carries both values). Mixed `measured`/`predicted` origin is still `recorded` if conditions match; the origins stay on the values.

- [ ] **Step 1: Write the failing tests**

```python
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
```

Add `import pytest` at the top of the test file.

The numbers 4.76 / 5.23 / 0.47 are **fixtures for the arithmetic**, not handbook claims. Do not write them into shipped JSON.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_salt_evidence.py -v`

Expected: FAIL with `ModuleNotFoundError` for `openchem.domain.salt_evidence`.

- [ ] **Step 3: Write minimal implementation**

```python
"""pKa as an independent salt-composition claim, never a solver input."""

from __future__ import annotations

from dataclasses import dataclass

REACHED_BY = (
    "tooling: consumed by tests/test_salt_evidence.py; evidence is not "
    "on the window yet"
)

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
```

`balance_two` must not be imported here. Tests must not import `openchem.chem.pka_providers`.

- [ ] **Step 4: Run `tests/test_salt_evidence.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_evidence.py tests/test_salt_evidence.py
git commit -m "Record salt pKa as a named step under comparable conditions, not a proof."
```

---

