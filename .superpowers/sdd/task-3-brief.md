### Task 3: Domain workflow 2 — two supplied ions

**Files:**
- Modify: `src/openchem/domain/salt_stoichiometry.py`
- Modify: `src/openchem/domain/salt_evidence.py` (optional helper `evidence_for_supplied_ions`)
- Test: `tests/test_salt_stoichiometry.py`, `tests/test_salt_evidence.py`

**Interfaces:**
- Consumes: `ModeASpecies`, `KIND_ION`, `balance_two`, `assess_pka_compatible`
- Produces:

```python
def compose_supplied_ions(
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    ...
```

Two `KIND_ION` species, opposite signs, `balance_two`, **no** formula-unit conservation against neutrals (no transfer was modelled). Mixing a molecular neutral with a supplied ion remains `missing_proton_source` on `compose_mode_a` (already shipped). Do not add a neutralization path.

- [ ] **Step 1: Write the failing tests**

```python
from openchem.domain.salt_evidence import VERDICT_NOT_ASSESSED, assess_pka_compatible
from openchem.domain.salt_stoichiometry import (
    KIND_ION,
    KIND_MOLECULAR_NEUTRAL,
    ModeASpecies,
    compose_supplied_ions,
)


def test_sodium_and_acetate_as_given_ions_balance_one_to_one() -> None:
    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
    acetate = ModeASpecies("CC(=O)[O-]", -1, KIND_ION, (("C", 2), ("H", 3), ("O", 2)))
    result = compose_supplied_ions(sodium, acetate)
    assert result.cation_count == 1
    assert result.anion_count == 1
    assert result.charge_valid is True


def test_supplied_ions_do_not_assess_pka() -> None:
    result = assess_pka_compatible(
        already_charged=True,
        proposed_acid_step_id="x",
        proposed_conjugate_acid_step_id="y",
        acid=None,
        conjugate_acid=None,
    )
    assert result.verdict == VERDICT_NOT_ASSESSED


def test_a_neutral_passed_to_supplied_ions_is_refused() -> None:
    acetic = ModeASpecies("CC(=O)O", 0, KIND_MOLECULAR_NEUTRAL, (("C", 2), ("H", 4), ("O", 2)))
    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
    refused = compose_supplied_ions(sodium, acetic)
    assert refused.code == "missing_proton_source"
```

- [ ] **Step 2: Run the new tests**

Expected: FAIL with `ImportError` for `compose_supplied_ions`.

- [ ] **Step 3: Write minimal implementation**

```python
def compose_supplied_ions(
    cation: ModeASpecies,
    anion: ModeASpecies,
) -> ModeAComposition | ModeARefusal:
    if cation.kind != KIND_ION or anion.kind != KIND_ION:
        return ModeARefusal(
            code="missing_proton_source",
            reason=(
                "A molecular neutral plus a supplied ion does not provide "
                "the protons for a transfer; supply both ions as given."
            ),
        )
    balanced = balance_two(
        ChargedSpecies(cation.identity, cation.charge),
        ChargedSpecies(anion.identity, anion.charge),
    )
    if isinstance(balanced, BalanceRefusal):
        return ModeARefusal(code=balanced.code, reason=balanced.reason)
    return ModeAComposition(
        cation_count=balanced.cation_count,
        anion_count=balanced.anion_count,
        charge_valid=True,
    )
```

Do not call `formula_unit_conserved`. Do not call `assess_pka_compatible` from this function.

- [ ] **Step 4: Run the new tests plus `tests/test_salt_stoichiometry.py` and `tests/test_salt_evidence.py`**

Expected: PASS (including existing Mode A tests).

- [ ] **Step 5: Commit**

```bash
git add src/openchem/domain/salt_stoichiometry.py tests/test_salt_stoichiometry.py tests/test_salt_evidence.py
git commit -m "Compose two supplied ions as given, without inventing protons or a pKa."
```

---

