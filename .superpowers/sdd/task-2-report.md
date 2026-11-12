# Task 2 report — Domain pKa evidence (annotation only)

## Status

Complete. TDD RED → GREEN on `tests/test_salt_evidence.py`; committed on `cursor/salt-composition-slice-3`.

## RED (Step 2)

Command:

```text
uv run --no-sync pytest tests/test_salt_evidence.py -v
```

Outcome (before implementation):

```text
ModuleNotFoundError: No module named 'openchem.domain.salt_evidence'
ERROR collecting tests/test_salt_evidence.py
```

## GREEN (Step 4)

Same command after adding `src/openchem/domain/salt_evidence.py`:

```text
6 passed in 0.15s
```

Tests:

- `test_already_charged_input_is_not_assessed`
- `test_missing_pka_is_missing_not_invented`
- `test_delta_is_conjugate_acid_minus_acid`
- `test_sulfate_must_not_reuse_the_first_sulfuric_pka`
- `test_bh2_must_not_reuse_the_first_conjugate_acid_pka`
- `test_different_media_are_incomparable`

## Deliverables

| File | Role |
|------|------|
| `src/openchem/domain/salt_evidence.py` | Constants, `PkaValue`, `PkaCompatibility`, `EvidenceRecord`, `assess_pka_compatible` |
| `tests/test_salt_evidence.py` | Six unit tests with injected `PkaValue` fixtures (not handbook claims) |

## Constraints checked

- No import of `balance_two`.
- Tests do not import `openchem.chem.pka_providers` or `rdkit`.
- ΔpKa = conjugate_acid.value − acid.value only when step ids and comparable medium/temperature match.
- Mixed measured/predicted origin not tested here; design allows `VERDICT_RECORDED` when conditions match (origins remain on values).

## Commit

Message (verbatim from brief):

```text
Record salt pKa as a named step under comparable conditions, not a proof.
```

## Concerns

None blocking. `EvidenceRecord` is defined but not exercised until a later slice wires full evidence. Ionic-strength mismatch is intentionally not `incomparable` (not covered by tests yet).
