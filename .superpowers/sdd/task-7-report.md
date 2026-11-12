# Task 7 report

Branch: `cursor/salt-composition-slice-3`
Commit: `e3d57b87` — Record slice 3 of salt composition in the changelog and the file map.

Not committed: `.superpowers/`, `docs/superpowers/plans/2026-11-11-salt-composition-slice-3.md`.

## What changed

- Changelog fragment `changelog.d/202611111916-salt-composition-slice-3-3717.md`, heading `### Salt composition, slice 3 (library, no UI)`.
- `docs/SALT_COMPOSITION_DESIGN.md` status: slice 3 adds ionization, a cited ion catalog, and pKa evidence; Mode C and UI still not authorized.
- `docs/ROADMAP.md` salt-composition bullet names slice 3 the same way.
- `docs/README.md` salt row now says slice 1–3.
- `CLAUDE.md` Key Files line names `salt_evidence.py`, `salt_ionization.py`, and `ionic_species.py`.
- `docs/ARCHITECTURE.md`: chem count **165 → 167** (live glob is 167). `salt_ionization.py` and `ionic_species.py` are named beside `salt_mode_a.py`.
- `tools/suite-shard-pins.json`: `--pin-new` with no `--splits` wrote the three new tests into the **8-way** table only (`ci_splits()` from `tests.yml` shard `[1..8]`). Shards: `test_salt_ionization.py` → 3, `test_ionic_species.py` → 4, `test_salt_evidence.py` → 7. The `"3"` table was not modified.
- `src/openchem/domain/salt_evidence.py`: `REACHED_BY` was already present; a `#:` comment was added because the constant-docs ratchet reported it undocumented. `salt_stoichiometry.py` was left unchanged: the reachability guard passed with its existing `REACHED_BY`.

## Commands and outcomes

1. `uv run --no-sync python tools/changelog.py new salt-composition-slice-3` — exit 0, created `changelog.d/202611111916-salt-composition-slice-3-3717.md`.
2. `uv run --no-sync python tools/suite_shards.py --pin-new` — exit 0, `pinned 3 new file(s) where they already sit: tests/test_ionic_species.py, tests/test_salt_evidence.py, tests/test_salt_ionization.py`.
3. First guard run (before the `#:` fix): `uv run --no-sync pytest tests/test_constant_docs.py::test_no_constant_has_fallen_out_of_documentation tests/test_calculator_reachability.py::test_every_module_is_statically_reachable_or_declares_why_not tests/test_calculator_reachability.py::test_a_declared_entry_surface_is_not_an_unconditional_exemption -q --tb=line` — 1 failed, 2 passed. Failure: `src/openchem/domain/salt_evidence.py::REACHED_BY` lost its `#:` documentation. Reachability passed.
4. After the comment: `uv run --no-sync pytest` of the brief's tests plus `tests/test_suite_shards.py::test_the_workflow_runs_exactly_the_shards_the_committed_pins_cover` and the two reachability tests above — **84 passed** in 12.13s, exit 0.

Brief tests included: architecture module count, every chem module named, layering, salt stoichiometry, salt evidence, salt ionization, ionic species, constant-docs ratchet, changelog fragments.

## Explicit-hydrogen ionization fix

Commit: `fed14181` — Count bonded hydrogens when ionizing a site.

`apply_site_transform` counted hydrogens with `GetTotalNumHs()`, which ignores neighboring hydrogen atoms. After `Chem.AddHs` the acetic OH reported 0 hydrogens. Deprotonation now deletes one bonded H atom; protonation adds a hydrogen atom instead of stacking an explicit-H property. `Chem.RemoveHs` then makes the fragment key the implicit acetate key. Later indexes in `ionize_at_sites` are positions on that updated mol. Net-charge listing still tries N/O/P/S only.

### RED

`uv run --no-sync python -m pytest tests/test_salt_ionization.py::test_deprotonating_explicit_hydrogen_acetic_acid_removes_the_bonded_hydrogen tests/test_salt_ionization.py::test_protonating_explicit_hydrogen_oxygen_does_not_stack_a_hydrogen_property -q --tb=line`

```
FF                                                                       [100%]
E   AttributeError: 'IdentityRefusal' object has no attribute 'GetAtoms'
E   assert 1 == 2
2 failed in 0.23s
```

Deprotonation returned `invalid_site`. Protonation left one bonded hydrogen (the added hydrogen was an explicit-H property).

### GREEN

`uv run --no-sync python -m pytest tests/test_salt_ionization.py -q --tb=short`

```
........                                                                 [100%]
8 passed in 0.16s
```

Exit 0. The implicit-H acetic deprotonation test is among the eight.
