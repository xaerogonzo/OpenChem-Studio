# Task 1 Report: Domain ionization uniqueness

## Status

DONE

## Summary

Added `IonizationRefusal` and `choose_ionization` to `src/openchem/domain/salt_stoichiometry.py` and three contract tests in `tests/test_salt_stoichiometry.py`. Domain layer treats candidate strings as opaque identities; empty input refuses `net_charge_only`, multiple distinct strings refuse `ambiguous_microspecies`, and a single unique candidate is returned. Duplicate identical strings collapse via `dict.fromkeys`.

## TDD evidence

### RED (Step 2)

**Command:**

```text
uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_one_structure_at_the_requested_state_is_accepted tests/test_salt_stoichiometry.py::test_a_net_charge_with_no_structure_is_refused tests/test_salt_stoichiometry.py::test_two_structures_at_the_same_charge_are_not_auto_picked -v
```

**Outcome:** Exit code 4; collection error as expected.

```text
ImportError: cannot import name 'IonizationRefusal' from 'openchem.domain.salt_stoichiometry'
```

### GREEN (Step 4)

**Command (three new tests):**

```text
uv run --no-sync pytest tests/test_salt_stoichiometry.py::test_one_structure_at_the_requested_state_is_accepted tests/test_salt_stoichiometry.py::test_a_net_charge_with_no_structure_is_refused tests/test_salt_stoichiometry.py::test_two_structures_at_the_same_charge_are_not_auto_picked -v
```

**Outcome:** `3 passed in 0.20s`

**Command (full module):**

```text
uv run --no-sync pytest tests/test_salt_stoichiometry.py -v --tb=no -q
```

**Outcome:** `23 passed in 0.24s`

## Commit

```text
Refuse a salt ionization that is only a net charge or several microspecies.
```

`5c7616e6` — Refuse a salt ionization that is only a net charge or several microspecies.

## Files changed

| File | Change |
|------|--------|
| `src/openchem/domain/salt_stoichiometry.py` | `IonizationRefusal`, `choose_ionization` with `#:` comments |
| `tests/test_salt_stoichiometry.py` | Three tests + imports |

## Concerns

None.
