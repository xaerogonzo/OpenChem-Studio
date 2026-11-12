### Task 7: Changelog, shards, architecture, design status

**Files:**
- Create: changelog fragment via `tools/changelog.py new salt-composition-slice-3`
- Modify: `docs/SALT_COMPOSITION_DESIGN.md` status line — slice 3 adds ionization, catalog, pKa evidence; Mode C/UI still not authorized
- Modify: `docs/ROADMAP.md` salt-composition bullet
- Modify: `CLAUDE.md` Key Files salt line — mention `salt_ionization.py`, `salt_evidence.py`, `ionic_species.py`
- Modify: `docs/ARCHITECTURE.md` — chem count 165 → 167; name `salt_ionization.py` and `ionic_species.py` beside `salt_mode_a.py`
- Modify: `docs/README.md` salt row if it still says slice 1–2 only
- Modify: `tools/suite-shard-pins.json` via `--pin-new` **without** `--splits=3`
- Modify: `src/openchem/domain/salt_stoichiometry.py` `REACHED_BY` to also name new tests if the reachability guard requires it

**Interfaces:** none

- [ ] **Step 1: Changelog fragment** titled `### Salt composition, slice 3 (library, no UI)` so it does not collide with slice 1/2 headings.

Body:

```markdown
### Salt composition, slice 3 (library, no UI)

- Fully specified ionization (site transforms; net charge alone refused;
  several microspecies at one charge listed, not picked), two supplied ions
  as given, a small cited ion catalog, and `pka_compatible` as named-step
  evidence that never feeds `balance_two`. Still no panel and not a crystal.
```

- [ ] **Step 2: Pin** `python tools/suite_shards.py --pin-new`

- [ ] **Step 3: Docs + architecture count.** Run:

`uv run --no-sync pytest tests/test_docs_are_current.py::test_the_architecture_module_count_is_live tests/test_docs_are_current.py::test_every_chem_module_is_named_in_the_package_map tests/test_layering.py tests/test_salt_stoichiometry.py tests/test_salt_evidence.py tests/test_salt_ionization.py tests/test_ionic_species.py tests/test_constant_docs.py::test_no_constant_has_fallen_out_of_documentation tests/test_changelog_fragments.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add changelog.d docs/SALT_COMPOSITION_DESIGN.md docs/ROADMAP.md docs/ARCHITECTURE.md docs/README.md CLAUDE.md tools/suite-shard-pins.json src/openchem/domain/salt_stoichiometry.py
git commit -m "Record slice 3 of salt composition in the changelog and the file map."
```

---
