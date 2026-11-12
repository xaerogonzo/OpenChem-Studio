### Spec Compliance

- ✅ Spec compliant
- The review package is one commit, `000fddc9`, on base `5c7616e6`, message `Record salt pKa as a named step under comparable conditions, not a proof.`, touching only `src/openchem/domain/salt_evidence.py` and `tests/test_salt_evidence.py`.
- This review did not re-run pytest. The implementer report states `tests/test_salt_evidence.py` failed with `ModuleNotFoundError` before the module existed and then `6 passed`.

Checked in the diff (source opened only to resolve two characters the package displayed as `Î”` / `âˆ’`; the file itself has `Δ` and `−`):

- `PkaValue`, `PkaCompatibility`, `EvidenceRecord`, and `assess_pka_compatible` match the mandated fields and keyword-only signature (`salt_evidence.py:29-80`).
- Verdict order is already-charged, then missing, then step identity, then medium and temperature, then recorded (`salt_evidence.py:65-102`).
- `ΔpKa` is `conjugate_acid.value - acid.value` only on the recorded path (`salt_evidence.py:97-102`). The recorded reason states the figure is not a crystal.
- `EvidenceRecord.experimentally_established` is annotated `None` (`salt_evidence.py:49-54`). Nothing in the diff assigns it.
- `charge_valid` is its own field. No path treats a charge-valid composition as an isolable salt, and the string `acid_base_supported` does not appear.
- The module imports `dataclasses` only. It does not import `balance_two`, `openchem.chem`, or RDKit.
- The six tests are the brief’s tests, call `assess_pka_compatible` with injected `PkaValue`s, and do not call `compute_pka` or import `openchem.chem.pka_providers` (`test_salt_evidence.py:1-96`). The 4.76 / 5.23 / 0.47 figures stay in that test file.
- Origin and ionic strength are not read, so a mixed measured/predicted pair and an ionic-strength difference stay `recorded` when medium and temperature match. Both `temperature_k is None` compares equal.

### Strengths

- Step identity is checked against the proposed acid step and the proposed conjugate-acid step before any delta is stored (`salt_evidence.py:81-88`; `test_salt_evidence.py:59-84`).
- A missing value returns `missing` with `delta is None` and does not fill a number (`salt_evidence.py:73-80`; `test_salt_evidence.py:35-44`).
- Different media return `incomparable` with `delta is None` and keep both supplied values (`salt_evidence.py:89-96`; `test_salt_evidence.py:86-96`).
- Already-charged input returns `not_assessed` with `delta is None` even when both pKa values were passed (`salt_evidence.py:65-72`; `test_salt_evidence.py:23-32`).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

- `tests/test_salt_evidence.py` — the six brief tests never vary temperature, origin, or ionic strength. A later change that required a numeric temperature, refused a mixed origin, or treated an ionic-strength difference as `incomparable` would still pass. The same file never builds an `EvidenceRecord`, so a runtime `experimentally_established=True` would also pass.

### Assessment

**Task quality:** Approved

**Reasoning:** The domain helper matches the contract: pKa is a separate annotation, a delta is stored only for the named steps under the same medium and temperature, and already-charged, missing, wrong-step, and incomparable inputs stay without a delta. The untested temperature, origin, ionic-strength, and `EvidenceRecord` edges are specified and implemented, and they are not locked by a test.
