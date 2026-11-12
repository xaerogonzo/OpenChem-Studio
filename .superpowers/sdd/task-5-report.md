# Task 5 report — Chem net-charge enumeration without auto-pick

**Status:** GREEN  
**Commit:** `638e5ed5` — List ionization microspecies at a charge; never pick among several.  
**Branch:** `cursor/salt-composition-slice-3`

## RED

`uv run --no-sync pytest tests/test_salt_ionization.py -v`  
Exit 2. Collection error, the missing name:

```
E   ImportError: cannot import name 'select_by_net_charge' from 'openchem.chem.salt_ionization'
ERROR tests/test_salt_ionization.py
1 error in 0.46s
```

## GREEN

Same command after `structures_at_net_charge` and `select_by_net_charge`:

```
tests/test_salt_ionization.py::test_deprotonating_acetic_acid_updates_hydrogen_and_charge PASSED
tests/test_salt_ionization.py::test_protonating_pyridine_updates_hydrogen_and_charge PASSED
tests/test_salt_ionization.py::test_a_bad_atom_index_is_refused PASSED
tests/test_salt_ionization.py::test_acetic_acid_at_minus_one_is_acetate PASSED
tests/test_salt_ionization.py::test_acetic_acid_at_plus_one_is_net_charge_only PASSED
tests/test_salt_ionization.py::test_two_inequivalent_sites_at_the_same_charge_are_not_picked PASSED
6 passed in 0.18s
```

## Notes

- `select_by_net_charge` is `choose_ionization(structures_at_net_charge(...))`. Uniqueness is that function’s job. No ranking, no tautomer canonicalization.
- 4-hydroxybenzoic acid (`O=C(O)c1ccc(O)cc1`) stayed two graphs at −1. Tyrosol was not substituted.
- A loop over every heavy atom fails the acetic tests on this RDKit pin. Sanitized extras are `[CH2-]C(=O)O` at −1 and `CC(O)=[OH+]` plus `CC(=O)[OH2+]` at +1. Enumeration therefore only offers heteroatom acids (N, O, P, S with a hydrogen) and N/P bases, and it will still protonate an existing anion or deprotonate an existing cation. A person can still name any atom through `apply_site_transform`.
- No pKa import.
