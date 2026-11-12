### Spec Compliance

- ✅ Spec compliant
- ⚠️ Cannot verify from diff: that `5c7616e6` is on `cursor/salt-composition-slice-3` cut from `origin/master` after #583. The package shows that one commit on base `24775f03` with the mandated message. The controller should confirm the branch.

Checked in the diff:

- `IonizationRefusal` (`code`, `reason`) and `choose_ionization(candidates) -> str | IonizationRefusal` match the mandated interface (`src/openchem/domain/salt_stoichiometry.py:136-138`, `:177`).
- An empty list returns `net_charge_only` (`:179-183`). One identity is returned (`:189`). Two distinct identities return `ambiguous_microspecies` and no string is chosen (`:184-188`). The caller already holds the candidate list; the mandated type does not echo it.
- Identical duplicates collapse with `dict.fromkeys` (`:178`).
- The domain diff adds no imports. The new lines do not reference RDKit, Open Babel, PySide6, `openchem.chem`, UI, Mode C, or a pKa sidecar.
- The new function has its `#:` block (`:175-176`). No new constants were added.
- The diff does not treat a charge-valid composition as an isolable salt.
- The three tests call the real function and match the brief (`tests/test_salt_stoichiometry.py:173-185`).
- No extra behavior beyond the brief.

### Strengths

- The helper is the brief’s function: opaque strings, a typed refusal, and order-preserving collapse of identical identities.
- Ambiguous input returns `IonizationRefusal` rather than a selected structure (`salt_stoichiometry.py:184-188`; asserted at `test_salt_stoichiometry.py:182-185`).
- The existing whole-file `rdkit` scan still covers this module (`test_salt_stoichiometry.py` after the new tests).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

- `src/openchem/domain/salt_stoichiometry.py:178` — identical duplicates count as one structure, and none of the three tests passes a repeated identity. A change that treated `["A", "A"]` as `ambiguous_microspecies` would still pass. Add `assert choose_ionization(["CC(=O)[O-]", "CC(=O)[O-]"]) == "CC(=O)[O-]"`.

### Assessment

**Task quality:** Approved

**Reasoning:** The domain helper matches the contract: one identified structure is accepted, a net charge with no structure is refused, and several distinct structures are refused rather than picked, with no chemistry imports. The duplicate-collapse path is implemented and untested.
