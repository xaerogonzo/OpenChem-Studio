### Spec Compliance

- ✅ Spec compliant
- The review package is one commit, `5feb4351`, on base `abb7d6c1`, message `Ionize a named atom by moving both its hydrogens and its formal charge.`, touching only `src/openchem/chem/salt_ionization.py` and `tests/test_salt_ionization.py`.
- This review did not re-run pytest. The implementer report states `tests/test_salt_ionization.py` failed at collection with `ModuleNotFoundError: No module named 'openchem.chem.salt_ionization'` and then `3 passed`.

Checked in the diff and against the existing types:

- `SiteTransform`, `apply_site_transform`, and `ionize_at_sites` match the mandated bodies (`salt_ionization.py:19-63`).
- The molecule is copied with `Chem.Mol(mol)` before either edit (`salt_ionization.py:30`). Direction and atom-index checks run before that copy (`:26-29`). A deprotonation with no hydrogen returns `invalid_site` before the copy is edited (`:37-39`).
- Protonate sets explicit hydrogens to `GetTotalNumHs() + 1` and formal charge to `z + 1`. Deprotonate requires `GetTotalNumHs() >= 1`, then sets explicit hydrogens to `total - 1` and formal charge to `z - 1`. Both set `SetNoImplicit(True)` and sanitize (`:32-46`).
- A bad direction or an index outside the parent is `IdentityRefusal(code="invalid_site")` (`:26-29`). A sanitize failure is `unsanitizable` (`:43-46`).
- `REACHED_BY` is kind `tooling` and names `tests/test_salt_ionization.py` (`:13-16`). The new module is not imported from `openchem.main`.
- Imports are `rdkit.Chem`, `IdentityRefusal` and `fragment_key` from `salt_components`, and `IonizationRefusal` and `choose_ionization` from `domain.salt_stoichiometry` (`:10-11`). `choose_ionization` already accepts `Sequence[str]` and returns `str | IonizationRefusal` (`salt_stoichiometry.py:202`). No `pka_providers` or `pka_species_ladder` import.
- The diff does not edit `docs/ARCHITECTURE.md`, `CLAUDE.md`, or the architecture-count tests. Those stay with Task 7.
- The three tests are the brief’s tests (`test_salt_ionization.py:11-36`). Acetic acid asserts charge `-1`, key `CC(=O)[O-]`, and parent charge `0`. Pyridine asserts charge `1` and the brief’s `[nH+]` / literal key check. Index `99` asserts `invalid_site`.

### Strengths

- Both directions move hydrogen count and formal charge on a copy, then sanitize (`salt_ionization.py:30-46`). The acetic-acid test locks the carboxylate key and the parent charge (`test_salt_ionization.py:18-22`).
- Selection stays in domain `choose_ionization`. `ionize_at_sites` applies the named sites and passes the one resulting `fragment_key` (`salt_ionization.py:60-63`).
- The module is the brief’s file: no ladder, no net-charge enumeration, and no architecture-count edit.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

- `tests/test_salt_ionization.py:25-30` — the pyridine assertion is the brief’s `[nH+] in key or key == "c1cc[nH+]cc1"`. A key that merely contains `[nH+]` passes, and the test does not check that the parent charge stays `0`. The report says this pin’s key is the literal.
- `src/openchem/chem/salt_ionization.py:26-46` and `:50-63` — `invalid_site` for a bad direction, `invalid_site` for an atom with no hydrogen, `unsanitizable`, and `ionize_at_sites` are implemented and untested. The brief’s three tests call `apply_site_transform` only. One successful key cannot produce `IonizationRefusal`; `choose_ionization` refuses only an empty list or more than one distinct identity (`salt_stoichiometry.py:203-214`).

### Assessment

**Task quality:** Approved

**Reasoning:** The transform copies the parent and updates both the hydrogen count and the formal charge, identity goes through `fragment_key` and the existing `choose_ionization`, and the pKa ladder and the architecture count stay out of this commit. The untested refusal branches and `ionize_at_sites` are the brief’s own test list, not a departure from it.
