# Task 3 report — Domain workflow 2 (two supplied ions)

## RED

Command:

```text
uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_sodium_and_acetate_as_given_ions_balance_one_to_one tests/test_salt_stoichiometry.py::test_a_neutral_passed_to_supplied_ions_is_refused tests/test_salt_evidence.py::test_supplied_ions_do_not_assess_pka -q
```

Outcome: `ImportError: cannot import name 'compose_supplied_ions'` (stoichiometry module failed to collect). `test_supplied_ions_do_not_assess_pka` alone: **1 passed** (documents existing `already_charged` → `VERDICT_NOT_ASSESSED` behaviour; independent of `compose_supplied_ions`).

## GREEN

Command:

```text
uv run --no-sync pytest tests/test_salt_stoichiometry.py tests/test_salt_evidence.py -q
```

Outcome: **32 passed** in 0.32s.

## Implementation

- Added `compose_supplied_ions` in `src/openchem/domain/salt_stoichiometry.py`: requires both `KIND_ION`, refuses otherwise with `missing_proton_source`, else `balance_two` → `ModeAComposition` (no `formula_unit_conserved`, no `assess_pka_compatible`).
- Tests in `tests/test_salt_stoichiometry.py` and `tests/test_salt_evidence.py` per task brief.
