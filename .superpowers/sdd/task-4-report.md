# Task 4 report — Chem site transform

**Status:** GREEN  
**Commit:** `5feb4351` — Ionize a named atom by moving both its hydrogens and its formal charge.  
**Branch:** `cursor/salt-composition-slice-3`

## RED

`uv run --no-sync pytest tests/test_salt_ionization.py -v`  
Exit 2. Collection error, the missing module:

```
E   ModuleNotFoundError: No module named 'openchem.chem.salt_ionization'
ERROR tests/test_salt_ionization.py
1 error in 0.61s
```

## GREEN

Same command after `src/openchem/chem/salt_ionization.py`:

```
tests/test_salt_ionization.py::test_deprotonating_acetic_acid_updates_hydrogen_and_charge PASSED
tests/test_salt_ionization.py::test_protonating_pyridine_updates_hydrogen_and_charge PASSED
tests/test_salt_ionization.py::test_a_bad_atom_index_is_refused PASSED
3 passed in 0.18s
```

## Notes

- Parent is copied (`Chem.Mol(mol)`). Acetic acid’s formal charge stays 0.
- Protonate and deprotonate both set explicit hydrogen count and formal charge, then sanitize.
- This RDKit pin’s pyridine key is the literal `c1cc[nH+]cc1` (`fragment_key` of `MolFromSmiles("c1cc[nH+]cc1")`). The brief’s assertion was kept.
- No import of `pka_providers` or `pka_species_ladder`. Identity goes through `fragment_key`. `REACHED_BY` points at the new test.
- `ionize_at_sites` is in the module as specified. The three tests call `apply_site_transform` only.
- Task 5 enumeration (`structures_at_net_charge`, `select_by_net_charge`) was not added.
- Architecture count and the package-map name were left for Task 7. `test_the_architecture_module_count_is_live` and `test_every_chem_module_is_named_in_the_package_map` will fail until then.
