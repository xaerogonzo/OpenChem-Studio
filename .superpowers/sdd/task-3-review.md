### Spec Compliance

- ✅ Spec compliant
- The review package is one commit, `abb7d6c1`, on base `000fddc9`, message `Compose two supplied ions as given, without inventing protons or a pKa.`, touching `src/openchem/domain/salt_stoichiometry.py`, `tests/test_salt_stoichiometry.py`, and `tests/test_salt_evidence.py`. The optional `evidence_for_supplied_ions` helper was left out. `src/openchem/domain/salt_evidence.py` is unchanged.
- This review did not re-run pytest. The implementer report states the new stoichiometry tests failed with `ImportError: cannot import name 'compose_supplied_ions'`, the pKa test alone passed before the composer existed, and then `tests/test_salt_stoichiometry.py` plus `tests/test_salt_evidence.py` were **32 passed**.

Checked in the diff and in the current functions:

- `compose_supplied_ions(cation, anion) -> ModeAComposition | ModeARefusal` matches the mandated body (`salt_stoichiometry.py:115-137`).
- Both arguments must be `KIND_ION`. Any other kind returns `missing_proton_source` with the mandated reason (`salt_stoichiometry.py:119-126`). The neutral-plus-ion test calls that path (`test_salt_stoichiometry.py:173-178`).
- Two ions go through `balance_two` on opaque `ChargedSpecies` charges. A `BalanceRefusal` is copied onto `ModeARefusal`. A balance becomes `ModeAComposition` with `charge_valid=True` (`salt_stoichiometry.py:127-137`). Sodium and acetate assert 1 and 1 (`test_salt_stoichiometry.py:163-170`).
- The new function does not call `formula_unit_conserved`. The only call remains inside `compose_mode_a` (`salt_stoichiometry.py:100`). Element counts on the supplied ions are unused. Sodium (`Na`) and acetate (`C2H3O2`) still compose, so a conservation check of one ion against the other would fail this test.
- `compose_supplied_ions` does not call `assess_pka_compatible`. The domain module has no pKa import. The new evidence test is the brief’s `already_charged=True` call and expects `VERDICT_NOT_ASSESSED` (`test_salt_evidence.py:23-31`).
- `compose_mode_a` is unchanged. A molecular neutral mixed with a supplied ion still returns `missing_proton_source` there (`salt_stoichiometry.py:67-75`; `test_salt_stoichiometry.py:181-189`).
- No neutralization path was added. `KIND_METAL_HYDROXIDE` is still refused only by `compose_mode_a` as `hydroxide_neutralization` (`salt_stoichiometry.py:59-66`; `test_salt_stoichiometry.py:117-125`).
- Domain imports stay `collections.abc`, `dataclasses`, and `math`. The existing source scan still requires the module text to omit `rdkit` (`test_salt_stoichiometry.py:207-212`).

The two stoichiometry tests add `isinstance` checks the brief did not spell out. Those checks match the return types.

### Strengths

- Workflow 2 is a charge balance of two given ions. It does not invent a parent neutral or a proton transfer (`salt_stoichiometry.py:115-137`).
- A neutral handed to that function is `missing_proton_source`, and the older `compose_mode_a` mix stays on the same code (`test_salt_stoichiometry.py:173-178` and `:181-189`).
- The 1:1 success case uses element counts that do not match each other, so the green test fails if formula-unit conservation is applied to the two ions (`test_salt_stoichiometry.py:163-170`).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

- `tests/test_salt_evidence.py:23-31` — `test_supplied_ions_do_not_assess_pka` never calls `compose_supplied_ions`. It repeats the already-charged branch of `assess_pka_compatible` and does not assert `delta is None`. The composer currently has no pKa call; this test would stay green if one were added. That is the test the brief wrote.
- `src/openchem/domain/salt_stoichiometry.py:131-132` — a same-sign or zero-charge pair is returned as `ModeARefusal` from `balance_two` (`not_opposite_signs` at `:169-176`), and neither new test reaches that branch.

### Assessment

**Task quality:** Approved

**Reasoning:** The composer matches the contract: two `KIND_ION` species are balanced as given, a non-ion is `missing_proton_source`, formula-unit conservation and pKa stay out of the function, and `compose_mode_a` still owns the neutral-plus-ion refusal and the hydroxide refusal. The pKa test and the same-sign refusal branch do not lock those edges.
