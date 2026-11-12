# Task 6 report — Cited ion catalog

**Status:** GREEN  
**Commit:** `7b87e211` — Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart.  
**Branch:** `cursor/salt-composition-slice-3`

## RED

`uv run --no-sync pytest tests/test_ionic_species.py -q --tb=line`  
Exit 2. Collection error, the module did not exist yet:

```
E   ModuleNotFoundError: No module named 'openchem.chem.ionic_species'
ERROR tests/test_ionic_species.py
1 error in 0.56s
```

## GREEN

Same file after the loader, the JSON, and the charge check:

```
tests/test_ionic_species.py::test_hydrogen_sulfate_and_sulfate_are_different_rows PASSED
tests/test_ionic_species.py::test_every_row_round_trips_to_its_charge_and_key PASSED
tests/test_ionic_species.py::test_catalog_is_not_a_pharma_whitelist PASSED
tests/test_ionic_species.py::test_load_refuses_a_charge_that_disagrees_with_the_graph PASSED
4 passed in 0.92s
```

`tests/test_sources_are_current.py` was run with the catalog tests. One failure before the JSON was in the index: `salt_ion_catalog: used_by src/openchem/chem/data/ionic_species.json is not tracked by git`. After `git add` of that file, `test_every_used_by_path_is_tracked_in_git` plus the four catalog tests: 5 passed in 1.00s. `docs/SOURCES.md` was regenerated with `uv run --no-sync python tools/build_sources_doc.py` (327 sources) and is in the commit.

## What shipped

Twelve rows. `ion_smiles` is the `fragment_key` of `MolFromSmiles`, which rewrote hydrogen sulfate, sulfate, the three phosphates, and nitrate. Hydrogen sulfate is `O=S(=O)([O-])O` (charge −1) and sulfate is `O=S(=O)([O-])[O-]` (charge −2). Load raises `ValueError` naming the id when `charge` is not `fragment_formal_charge`, and also when the stored SMILES is not the fragment key. `REACHED_BY` is `tooling:`. No pKa field and no DOI in the JSON.

`docs/sources.toml` key `salt_ion_catalog`: `identifier_type = "bibliographic"`, `identifier = "OpenChem Studio v1 salt ion catalog"`. The same structures-only paragraph is both `reason` (as specified) and `note`, because `tools/build_sources_doc.py` prints `reason` only when status is not `shipped`. The generated page shows that paragraph and no DOI.

## Concerns

- `parent_smiles` stays the brief's written SMILES. For the sulfur, phosphorus, and nitrate parents that is not the `fragment_key` form (`OS(=O)(=O)O` versus `O=S(=O)(O)O`, `OP(=O)(O)O` versus `O=P(O)(O)O`, `O[N+](=O)[O-]` versus `O=[N+]([O-])O`). Ion identity uses `ion_smiles`.
- `tests/test_calculator_reachability.py::test_no_module_level_function_is_referenced_only_by_its_own_def` fails on `chem/salt_ionization.py::ionize_at_sites`. That name occurs only on its `def`. It was already on the branch and this catalog does not call it. The rest of that run was 496 passed, 1 skipped, that one failure, plus the untracked-`used_by` failure above.
- Full `uv run --no-sync pytest` without the repo root on `PYTHONPATH` stopped at collection: 62 errors, `No module named 'tests'`. With `PYTHONPATH` set to this worktree, the unsharded suite was about 5% after 12 minutes and was stopped. CI runs that suite as eight shards. This is not a catalog result. PySide6 imports from this worktree's venv, so the main-checkout venv fallback was not needed.
