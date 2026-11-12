### Spec Compliance

- Spec compliant. One commit, `e3d57b87`, on base `7b87e211`, message `Record slice 3 of salt composition in the changelog and the file map.`
- This review did not re-run pytest. The implementer report states the brief's tests, the shard-pin workflow test, and the two reachability tests were **84 passed** after the `#:` fix. The changelog body, headings, shard table, and chem count were checked against the tree in this review.

Checked against the brief:

- `changelog.d/202611111916-salt-composition-slice-3-3717.md` is titled `### Salt composition, slice 3 (library, no UI)`. Slice 1 is `### Salt composition (library, no UI)` and slice 2 is `### Salt composition, slice 2 (library, no UI)`. `CHANGELOG.md` has no `### Salt composition` heading. The bullet is the brief's text, including `pka_compatible` never feeding `balance_two`, and still no panel and not a crystal.
- `docs/SALT_COMPOSITION_DESIGN.md` status names slice 3 (ionization, a cited ion catalog, pKa evidence) and still says Mode C and UI are not authorized.
- `docs/ROADMAP.md` names slice 3 the same way: fully specified ionization, a small cited ion catalog, `pka_compatible` as named-step evidence, library-only, no panel, Mode C not authorized.
- `docs/README.md` salt row says slice 1–3 library code, no UI.
- `CLAUDE.md` Key Files names `salt_evidence.py`, `salt_ionization.py`, and `ionic_species.py`, and says the pKa evidence never feeds the solver.
- `docs/ARCHITECTURE.md` states **167 modules, counted 2026-11-11**. A top-level `src/openchem/chem/*.py` walk is 167 files and no package `__init__.py` (183 paths under `chem/`, 16 of them in `regulatory/`, `dreiding/`, and `checkers/`). `salt_ionization.py` and `ionic_species.py` are named beside `salt_mode_a.py`, with no-UI descriptions.
- `python tools/suite_shards.py --pin-new` with no `--splits`. `tests.yml` matrix is `shard: [1, 2, 3, 4, 5, 6, 7, 8]`, so `ci_splits()` is 8. The pins file gained three lines and lost none, all under the `"8"` object: `test_salt_ionization.py` → 3, `test_ionic_species.py` → 4, `test_salt_evidence.py` → 7. Each name occurs once. The `"3"` table was not modified.
- `salt_stoichiometry.py` was left unchanged. The brief updates its `REACHED_BY` only if the reachability guard requires it. The report says that guard passed on the existing declaration.
- `salt_evidence.py` gained a `#:` block immediately above `REACHED_BY`. The constant-docs ratchet flags an undocumented constant only in a file that already documents some other constant. This file already documents `ORIGIN_MEASURED`. The new comment matches the wording used on `salt_stoichiometry.py`. The value is still `tooling:` and still names `tests/test_salt_evidence.py`.
- The commit's eight files are the changelog fragment, the five docs, the pins, and `salt_evidence.py`. `.superpowers/` is not in the diff.

### Strengths

- The slice 3 heading cannot collapse into slice 1 or slice 2 when fragments are folded into `[Unreleased]`.
- `--pin-new` wrote the table CI actually runs. The three-way table, which a `--splits=3` pin would have rewritten, is untouched, and existing 8-way pins did not move.
- Mode C and the panel stay unauthorized in the design status and the roadmap bullet, in the same sentences that record slice 3.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

None.

### Recommendations

- Leave `salt_stoichiometry.py` `REACHED_BY` as it stands. The reachability guard accepted it, and the brief only asks for a change when that guard requires one.

### Assessment

**Task quality:** Approved

**Reasoning:** The changelog, the file map, and the status lines record slice 3 as library code: ionization, the cited ion catalog, and pKa evidence that does not feed the solver. The new tests are pinned on the 8-way shard table only, the chem count is 167 with both new modules named, and Mode C and the UI remain unauthorized. Nothing from `.superpowers/` is in the commit.
