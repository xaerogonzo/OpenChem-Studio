### Spec Compliance

- ✅ Spec compliant, with one deliberate departure from the plan’s implementation sentence
- The review package is one commit, `638e5ed5`, on base `5feb4351`, message `List ionization microspecies at a charge; never pick among several.`, touching only `src/openchem/chem/salt_ionization.py` and `tests/test_salt_ionization.py`.
- This review did not re-run pytest. The implementer report states collection failed with `ImportError: cannot import name 'select_by_net_charge'` (exit 2), then `tests/test_salt_ionization.py` `6 passed`.

Checked in the diff and against `choose_ionization` (`salt_stoichiometry.py:202-214`) and `apply_site_transform` (`salt_ionization.py:29-51`):

- `structures_at_net_charge` and `select_by_net_charge` match the mandated signatures (`salt_ionization.py:90-119`). `select_by_net_charge` is `choose_ionization` of that tuple and nothing else.
- Enumeration is single-site: every attempt calls `apply_site_transform` on the original molecule, never on an intermediate, so a second proton is not removed in this pass (`:99-103`).
- Identity refusals are skipped. Keys whose `fragment_formal_charge` is not the target are skipped. Surviving keys are deduped in first-seen order: atom index, and within an atom protonate before deprotonate (`:79-113`).
- Nothing ranks, and nothing calls a tautomer enumerator or `CanonicalRankAtoms`. Identity stays `fragment_key`. Uniqueness stays `choose_ionization`: one key is returned, an empty tuple is `net_charge_only`, two or more distinct keys are `ambiguous_microspecies`.
- The three new tests are the brief’s tests (`test_salt_ionization.py:45-67`). 4-hydroxybenzoic acid was kept; tyrosol was not substituted. No `pka_providers` or `pka_species_ladder` import. `REACHED_BY` is unchanged. Architecture-count edits stay with Task 7.

Departure, accepted: the plan says to try both directions on every heavy atom. That loop cannot satisfy the acetic-acid tests on this RDKit pin. The report’s sanitized extras are a second graph at −1 (`[CH2-]C(=O)O`) and two graphs at +1 (`CC(O)=[OH+]`, `CC(=O)[OH2+]`), so `select_by_net_charge` would return `ambiguous_microspecies` where the tests require acetate and `net_charge_only`. The code therefore offers deprotonation only for N, O, P, or S that already has a hydrogen, and protonation only for N or P, plus protonation of an existing anion and deprotonation of an existing cation (`salt_ionization.py:70-87`). A named atom can still be transformed through `apply_site_transform`. Do not “fix” this back to every heavy atom.

### Strengths

- A unique graph is returned and several graphs are refused, by the existing domain function (`salt_ionization.py:116-119`, `salt_stoichiometry.py:203-214`). The 4-hydroxybenzoic test locks both the list length and `ambiguous_microspecies` (`test_salt_ionization.py:58-67`).
- The acetic +1 test locks an empty candidate list, because `choose_ionization` uses `net_charge_only` only for no keys (`test_salt_ionization.py:51-55`).
- The site filter is local, commented with the three SMILES that forced it, and still single-site (`salt_ionization.py:70-87`).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

- `src/openchem/chem/salt_ionization.py:91-96` — the docstring still reads as every single protonate or deprotonate of a heavy atom. The element filter is only in the comment above `_ACID_ELEMENTS`. A later caller can miss that neutral C–H and neutral oxygen are not candidates.
- `tests/test_salt_ionization.py:63-67` — `len(set(keys)) >= 2` does not name the carboxylate and the phenolate. Any two keys at −1 would pass and still refuse. The assertion is the one the brief wrote.
- `src/openchem/chem/salt_ionization.py:83-86` — protonating an existing anion and deprotonating a cation that is not N, O, P, or S are implemented and untested. The three brief tests use neutral acetic acid and 4-hydroxybenzoic acid, so those two clauses can be dropped without a failing test.

### Recommendations

- Leave the heteroatom filter in place. Widening it to every heavy atom fails `test_acetic_acid_at_minus_one_is_acetate` and `test_acetic_acid_at_plus_one_is_net_charge_only`.
- Halide parents (`Cl`, `Br`, `I`) are Task 6 catalog rows, not products of this enumerator. F, Cl, Br, and I are outside `_ACID_ELEMENTS`. That is consistent with the comment as written; it is not a Task 5 test failure.

### Assessment

**Task quality:** Approved

**Reasoning:** Candidates at one charge are listed from single-site transforms and `choose_ionization` either keeps the only graph or refuses, with no tautomer pass. The element filter is the adjustment that makes the mandated acetic-acid results true on this RDKit pin, and it is documented in the module and the implementer report.
