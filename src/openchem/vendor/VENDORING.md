# Vendored third-party code

## `iupac_namer` — structure-to-IUPAC-name engine

| | |
|---|---|
| upstream | https://github.com/leehiufung911/open-iupac-namer |
| commit | `c3eac17ffd110c7c5dd37aaad2955e06cf8c9303` |
| licence | MIT — see `LICENSE.open-iupac-namer` (copyright retained) |
| vendored | 2026-08-01 |
| fork | https://github.com/xaerogonzo/open-iupac-namer (this project's fixes, standalone) |
| fork commit | `bafeba4` — synced 2026-09-21, corresponding to this repository's `naming-round-8` (branch head `16374577`): naming round 8 (the exo-skeleton parent candidate and the site-level charge ledger, condensed guanidines and ureas, protonated azoles and cations, pseudoketones via `context_indices`, the nitric and carbonic ester generators, and the limitations pass) on top of round 7's `85f7793`. Standalone suite 6,457 passed / 14 xfailed / 0 failed (the two RDKit-2026 trindene failures recorded at round 7 did not fail in this run). The fork's `tests/test_charge_ownership.py` still differs deliberately (it reads `tests/charged_panel_smiles.json`, and carries this round's two moved rows), and `tests/test_namer_probe_shapes.py` is a fork variant that reads names back through OPSIN directly, because the fork has no application layer; the panel and the round-8 addendum panel tests stay here |
| fork commit | `1a731c6` — synced 2026-09-22, corresponding to this repository's `naming-round-9` (base tree `470ff2c`): naming round 9 (9 of 13 admitted-ledger findings — carbodiimide, carbamimidoyl-locant, naphthalene-ring-drop, sulfinyl-bromide, phosphine-oxide-trihydrazide, peptide-acyl-naming, and the alkynyl-dianion/phosphide-anion/imine-anion charge classifiers). Numstat audit `+629/-21` matched the port tool's own reported total exactly (4 files merged clean, 1 new file, `iupac_namer/perception/fg/peptide_acyl.py`). Standalone suite 6,506 passed / 15 xfailed / 2 failed; both failures are the SAME RDKit-2026-dependent trindene indicated-hydrogen mismatches noted at the prior sync (`test_carbocyclic_indicated_h.py`) — reproduced on the pre-round-9 baseline too, confirmed unrelated to this port and out of scope for it. `tests/fixtures/naming_cation_shapes.txt`'s glycylglycine row moved out of its "OPEN" section (round 9's own peptide-acyl work reaches the retained form for it now) |
| fork commit | `0914606` — synced 2026-09-23, corresponding to this repository's `naming-round-10` (base tree `92782b0`, the round-9 merge — the fork's prior sync base, `470ff2c`, refers to THIS repository's commit as of the round-9 port, not the fork's own `1a731c6`, a naming trap worth restating for the next round): naming round 10, all 4 of round 9's deferred items closed (phenothiazine-dye-locant, spiro-xanthene-dye-locant, charge-polycarbocation's wrong-molecule half, carbamimidate-oxime-swap), plus a regression from the phenothiazine fix (arsanthrene) caught by the standalone suite and fixed before this sync. Numstat audit `+139/-13` matched the port tool's own reported total exactly (6 files merged clean, 0 new files). Standalone suite 6,525 passed / 15 xfailed / 2 failed; both failures are the SAME pre-existing RDKit-2026-dependent trindene indicated-hydrogen mismatches noted at every prior sync — confirmed unrelated to this port. PR: https://github.com/xaerogonzo/open-iupac-namer/pull/2 |
| fork commit | `a99bda3` — synced 2026-09-23, corresponding to this repository's `naming-round-11` (base tree `575b5037`, the round-10 merge — the fork's prior sync base is round 10's OWN merge commit here, not round 10's fork commit `0914606`; restating the same naming trap every prior row has needed to, since it recurs each round): naming round 11, 2 fixes (ketone-parent enclosure D-143; carbamimidoyl N'/N,N split D-091v, moved from open), plus 2 backlog rows re-verified and found already resolved by other rounds' own work (ring-nitrogen acyl on a ring/chain parent; the citrate-trianion/biguanidium-dication charge ledger) and 1 re-diagnosed deeper and re-deferred (a charged acid group inside a carved substituent — broader than previously documented, affects carboxylate the same way as sulfonate). Numstat audit `+178/-69` matched the port tool's own reported total exactly (3 files merged clean, 0 new files); `tests/fixtures/naming_cation_shapes.txt`'s pinned ketone row was NOT auto-ported (the port tool does not track this file) and was updated by hand to match, same 1-line change as this repository's own fixture. Standalone suite 6,524 passed / 14 xfailed / 2 failed; both failures are the SAME pre-existing RDKit-2026-dependent trindene indicated-hydrogen mismatches noted at every prior sync — confirmed unrelated to this port. PR: https://github.com/xaerogonzo/open-iupac-namer/pull/3 |
| fork commit | `a5ee3a9` — synced 2026-09-23, corresponding to this repository's `naming-round-12` (base tree `fcb35a19`, the round-11 merge — the fork's prior sync base is round 11's OWN merge commit here, not round 11's fork commit `a99bda3`; the same naming trap every prior row has restated): naming round 12, D-144 fixed (a charged acid group inside a substituent is now `carboxylatomethyl`/`sulfonatomethyl`, not `oxido`/`oxo` atom by atom), and the round-11 fused-aromatic-ring-cation census signal triaged and NOT admitted (largest single ring system 4/2000, under the floor). Numstat audit `+24/0` on the engine matched the port tool's own total exactly (2 files merged clean, 0 new files); `tests/fixtures/naming_cation_shapes.txt`'s pinned sulfonate row was NOT auto-ported (the port tool does not track this file) and was updated by hand, the same one-line change as this repository's own fixture. Standalone suite 6,560 passed / 14 xfailed / 0 failed, run under the main repository's interpreter (RDKit 2025.09.6), so it is not directly comparable to the round-11 row's environment-dependent 2 failures. PR: https://github.com/xaerogonzo/open-iupac-namer/pull/4 |
| fork commit | `956793c` — synced 2026-09-24, corresponding to this repository's `naming-round-13` (base tree `44cd2faf`, the round-12 merge — the fork's prior sync base is round 12's OWN merge commit here, not round 12's fork commit `a5ee3a9`; the same naming trap every prior row has restated): naming round 13, D-145 to D-148 (a wrong ring locant on a heterocyclic substituent: the senior heteroatom at locant 1 for a monocyclic ring, a hard-coded curated locant no longer returned for every attachment with an `atom_locants` table for benzodioxine, and the curated 1,2,5-oxadiazole row re-keyed from 1,2,3-oxadiazole's SMILES), D-149 and D-150 (a demoted ketone no longer claims its aryl or cycloalkyl carbon), and D-151 recorded OPEN. Numstat audit `+48/-2` on the engine and data matched the port tool's own total exactly (4 files merged clean, 0 new files); the vendored `test_retained_rings.py`, which had pinned the wrong 1,2,5-oxadiazole pair, is corrected with the data. This round changed no pinned-shapes fixture, so nothing needed a hand update there. Skipped as app-only (not ported, correctly): `test_naming_providers.py`, the census scan and ring-sweep tests, the census-lock test and the consumer manifest. Standalone suite 6,637 passed / 15 xfailed / 0 failed, run under this repository's interpreter (RDKit 2025.09.6), so it is not directly comparable to the round-11 row's environment-dependent 2 failures. `git grep -i openchem` over the fork's `*.py` files finds one pre-existing comment and nothing the round added. PR: https://github.com/xaerogonzo/open-iupac-namer/pull/5 |
| fork commit | `994183e` — synced 2026-09-24, corresponding to this repository's `naming-round-14` (base tree `a66644c3`, the round-13 merge — the fork's prior sync base is round 13's OWN merge commit here, not round 13's fork commit `956793c`; the same naming trap every prior row has restated): naming round 14, D-151/D-152 (a sulfonamide on a ring nitrogen is the prefix `<ring>-N-sulfonyl`; the sulfamoyl prefix gives each N-substituent its own locant), D-154 to D-157 (ring cations with no name, four roots, bicyclic systems only), D-158/D-159 (stereo kept on a retained ring substituent and on a spiro parent at a plain locant), D-160/D-161 (derived locant tables for heptacene to nonacene and the phenes, and three partial tables), D-153 (an aromatic non-benzene carbocycle is no longer named saturated) and D-162 recorded OPEN. Numstat audit `+222/-29` on the engine and data matched the port tool's own total exactly (6 files merged clean, 0 new files). Skipped as app-only (not ported, correctly): `test_naming_providers.py`; `test_namer_known_defects.py` reads the application in this repository, so its round-14 rows were hand-ported (1,255 passed / 15 xfailed under this repository's interpreter; the one test that reads this repository's `tools/` directory is omitted). `git grep -i openchem` over the fork's `*.py` files finds one pre-existing comment and nothing the round added. PR: (see the fork's naming-round-14 pull request) |
| fork commit | `5e69da0` — synced 2026-09-24, corresponding to this repository's `naming-round-15` (base tree `4a098933`, the round-14 merge — the fork's prior sync base is round 14's OWN merge commit here, not round 14's fork commit `994183e`; the same naming trap every prior row has restated): naming round 15, D-163 (a nitro group on a RING nitrogen is a nitro prefix, not an azanium parent: a second `nitro` entry, `[NX3+](=O)([O-])[#7;R]`, because widening the existing pattern drops the attachment context the plain `[#6]` atom carries), and acyclic N-nitro and N-nitroso recorded OPEN. Port tool: 1 file merged clean (`data/functional_groups.json`, +5), 0 new files, numstat `+5/-0` on the data. `test_namer_known_defects.py` reads the application in this repository, so its nine D-163 rows were hand-ported (fork suite: 6817 passed / 15 xfailed under this repository's interpreter). `git grep openchem` over the fork's package, data and tests is empty. PR: https://github.com/xaerogonzo/open-iupac-namer/pull/7 |
| fork commit | `75d0b04` — synced 2026-09-25, corresponding to this repository's `naming-round-16` (base `8b166647`, the round-15 merge): naming round 16, D-164 and D-165 (a nitro or nitroso group on an ACYCLIC nitrogen: amine and amide entries whose nitrogen requires a nitro/nitroso neighbour by a recursive constraint, an acyclic `nitro` prefix group, a small-fragment prefix keyed by attachment element, no `-amine` suffix on a heteroatom-chain parent's own nitrogen, and the urea and guanidine routes treating a nitro/nitroso nitrogen as a substituent), with nitramide and N-nitro/N-nitroso carbamates recorded OPEN (D-166, D-167). Port tool: 2 files merged clean (`data/functional_groups.json` +97, `iupac_namer/engine.py` +35/-3; the audit numstat matches this repository's +132/-3), 0 new files. `test_namer_known_defects.py` reads the application in this repository, so its 18 fixed rows and 3 open rows were hand-ported (fork suite: 6874 passed / 18 xfailed under this repository's interpreter). `git grep openchem` over the fork's package, data and tests is empty. PR: https://github.com/xaerogonzo/open-iupac-namer/pull/8 |
| fork commit | `4190819` — synced 2026-09-25, corresponding to this repository's `naming-round-17` (base `b99321ce`, the round-16 merge): naming round 17, D-166 and D-167 (nitramide and nitrous amide as the PARENTS of the acyclic nitramines and nitrosamines, per P-67.1.2.6.3 pdf p. 708: `_name_nitramide_functional_parent` on `_name_n_core_parent`; N-nitro and N-nitroso carbamates: the carbamate split no longer takes a nitro nitrogen for a carbazate's, and `is_nitro_or_nitroso_nitrogen` moves to `types.py`). `engine.py` and `types.py` merged clean with `tools/fork_port.py` (numstat +121/-19 on both sides); `tests/test_namer_known_defects.py` is hand-patched in the fork, and the fork's CHANGELOG and KNOWN_LIMITATIONS are written there. The fork's own suite: 6901 passed, 2 failed (`test_carbocyclic_indicated_h.py` trindene cases, which fail identically on the fork's untouched base under that venv's RDKit 2026.03.6 and pass here under 2025.09.6) |
| fork commit | `20054a7` — synced 2026-09-26, corresponding to this repository's `naming-round-18` (base `ea2275fe`, the round-17 merge): naming round 18, D-168 (the `-NH-NO2` prefix is `nitramido` and `-NH-NO` is the enclosed `(nitrosoamino)`, P-67.1.4.3.2: `assembly._preferred_prefix_spelling` maps `nitroamino` to `nitramido`, `_name_heteroatom_fv_substituent` has a matching case inside an imino group, `nitrosoamino` leaves `_SIMPLE_PREFIXES`, `nitramido` joins `_LEADING_PREFIX_WORDS`) and a round-17 guard tightened (`_is_hydrazone_type_nitrogen`: a hydrazone of nitramide keeps its hydrazine name). `assembly.py` and `engine.py` merged clean with `tools/fork_port.py` (numstat +46/-5 on both sides); `tests/test_namer_known_defects.py` is hand-patched in the fork, and the fork's CHANGELOG and KNOWN_LIMITATIONS are written there. The fork's own suite: 6923 passed, 2 failed (the same two `test_carbocyclic_indicated_h.py` trindene cases as round 17, which fail on the fork's untouched base under that venv's RDKit 2026.03.6) |
| fork commit | `8e7aab4` — synced 2026-09-26, corresponding to this repository's `naming-round-19` (base `7562a6af`, the round-18 merge): naming round 19, D-169 (nitric and nitrous HYDRAZIDES as parents, P-67.1.2.6.3: `_name_nitric_hydrazide_functional_parent` on `_name_n_core_parent` with fixed `N` / `N'` labels, and `allow_ylidene` so N' can carry a hydrazone's double-bonded substituent; it declines for a hydrazide-class or senior group elsewhere, a carbon acid derivative next to the nitrogen or on the hydrazone carbon, a triazane and a ring nitrogen). `engine.py` merged clean with `tools/fork_port.py` (numstat +103/-2 on both sides); `tests/test_namer_known_defects.py` is hand-patched in the fork, and the fork's CHANGELOG and KNOWN_LIMITATIONS are written there. The fork's own suite on its first run: 6956 passed, 15 failed — the same two `test_carbocyclic_indicated_h.py` trindene cases as rounds 17 and 18 (the fork venv's RDKit 2026.03.6), and thirteen new control rows whose inline import named the app's package; the import was removed and the known-defects file passes in full (1323 passed) |
| offered upstream | https://github.com/leehiufung911/open-iupac-namer/pull/1 |

### Why vendored rather than depended on

It is abandoned. Created 2026-05-24, last pushed 2026-05-24, three commits,
one author, no forks, no issues, and never published to PyPI. There is no
upstream to track and no release to pin, so depending on a git URL would give
all the fragility of a fork with none of the control.

It is also the best structure-to-name engine that exists in the open. Measured
against this project's own corpus (`benchmarks/naming`) it scored **120/124
with stereochemistry 11/11** as vendored, beating the leading ML alternative by
26 points while needing nothing beyond RDKit and running 16x faster. (The
corpus has since grown to 181 with charged species, ring N-oxides,
substituted guanidiniums and tautomer pairs the original set could not see;
on the 165-row revision the engine as vendored scored 148 and now scores 164,
and on the current 187-row revision it scores **187/187**, 98 of them
PubChem's string exactly (measured 2026-09-17) — see `BENCHMARK_HISTORY.md`.) That
benchmark was built before this engine was found, so the result is independent
of anything upstream chose to measure.

### What was changed

At vendoring time, deliberately minimal:

1. **Imports re-homed.** 302 occurrences of `iupac_namer.` became
   `openchem.vendor.iupac_namer.` across 33 modules, so the package does not
   claim a top-level name. Purely mechanical, applied by regex.
2. **Nothing else.** In particular the `data/` directory is kept as a SIBLING
   of the package, exactly as upstream lays it out, because data files are
   resolved from several different module depths (`data_loader.py` walks up
   two levels, `perception/fg/acid_infix_composition.py` walks up four).
   Mirroring the layout means zero path patches; moving `data/` inside the
   package required patching each resolver and broke on the second one.

Since then the engine has been changed on its merits — this project is its
maintainer now, not a downstream consumer. **`CHANGELOG.md` is the record**;
`KNOWN_LIMITATIONS.md` is what is still wrong; `BENCHMARK_HISTORY.md` tracks
the score per change. Keeping the diff against upstream small stopped being a
goal once it was established that there is no upstream to diff against.

`docs/` carries upstream's architecture documentation (~3,000 lines), which is
the main reason this is maintainable by someone who did not write it.

### Known state

Upstream's own suite as received: **2,907 passing, 12 failing**, plus one file
that would not collect at all — `test_fr_orientation_numbering.py`,
`test_retained_rings.py` and `test_skeletal_chain_replacement.py` all import
`tests.audit._audit_helpers`, and `tests/audit/` is absent from the repository.

That helper has been reconstructed (`tests/vendor/iupac_namer/audit/`) from how
the callers use it and from the engine's own stated correctness criterion: a
name is right when parsing it back yields the structure it came from. Writing
it fixed **7 of the 12 failures** — those tests were failing because of the
missing module, not on their merits.

Current state: **3,380 passing, 0 failing, 16 skipped** in ~10 minutes
(measured 2026-09-18, naming round 3).

The five that were still failing turned out not to be engine defects: they
asserted a non-minimal lambda numbering and three general-nomenclature-only
acylium names, and the engine's output is more correct in each case. See
`CHANGELOG.md` for the reasoning and the rule citations.

Investigating them exposed something worse than a red test, which is now the
main reason this directory carries its own documentation: inputs that name
*successfully* but to the **wrong molecule**. The benzyl cation was named
`methylbenzene` (toluene); the phthaloyl dication `1,2-bis(oxomethyl)benzene`
(phthalaldehyde). **Sixty-six** such cases were fixed by the end of naming
round 2, and round 3's held-out corpus found one more (D-030, a substituted
adamantane). All are pinned in `tests/test_namer_known_defects.py` -- 189 rows
as of round 3, counting the preference fixes and the non-regression rows
guarding the paths each fix could have stolen from. It runs in the DEFAULT suite,
because a wrong-molecule regression must not wait for the 7-minute run.
**None remain open** -- which says what has been looked for, not that none
exists; `KNOWN_LIMITATIONS.md` explains how to look for more.

The benchmark reports **zero wrong structures** across its 187 molecules, and
nothing refused or unparsable. Metformin is scored `tautomer` rather than
`exact`: the engine and the corpus depict the same substance as different
tautomers; see `KNOWN_LIMITATIONS.md`.

Set `OPENCHEM_NAMER_DEBUG=1` to instrument the fall-through that used to cause
this class of failure (`iupac_namer/diagnostics.py`).

Those tests live in `tests/vendor/iupac_namer/` and are **excluded from the
default run**: they take 6.5 minutes against this project's 2 minutes, and
they cover the engine's internals rather than our integration with it. Run
them explicitly when changing anything under `vendor/`:

```bash
uv run pytest tests/vendor -q
```

Our own coverage of the integration is in `tests/test_naming_providers.py`,
and `benchmarks/naming` is the regression check on naming quality.

### Upgrading

**The fork is the upstream now.** Everything in `CHANGELOG.md` was published to
https://github.com/xaerogonzo/open-iupac-namer as a standalone package — the
same code with the import rewrite of step 1 reversed — and offered to the
original author as
[PR #1](https://github.com/leehiufung911/open-iupac-namer/pull/1). He may never
see it; that changes nothing about what to do here.

To re-vendor from the fork, or from the original repository if it ever revives,
apply step 1 to a fresh checkout:

```python
re.sub(r"\b(from|import) iupac_namer\b", r"\1 openchem.vendor.iupac_namer", text)
```

and its exact inverse to go the other way. That is still the whole transform;
nothing else diverges. Then re-run `benchmarks/naming` before accepting the
change — the benchmark, not the diff, is what says whether it got better.

### Pushing a change OUT to the fork: merge, never copy

**A STRAIGHT COPY OF THE REWRITTEN FILE CLOBBERS THE FORK'S OWN PROSE**, and
it did on 2026-09-17: `tests/test_namer_known_defects.py` explains OpenChem's
default-versus-vendored suite split here and its SINGLE suite there, and the
copy replaced three of its sentences with ours. The diff showed it (deletions
of prose nobody had edited), which is the only reason it was caught.

So port each file as a THREE-WAY MERGE, with `git merge-file`:

    ours    the fork's committed file
    base    the repo's file BEFORE the change, import-rewritten
    theirs  the repo's file at the new commit, import-rewritten

The rewrite for `base` and `theirs` is the inverse import substitution above
plus the two other deliberate differences that touch file CONTENT
(`OPENCHEM_NAMER_DEBUG` -> `IUPAC_NAMER_DEBUG`, and the repo-relative path to
`KNOWN_LIMITATIONS.md`). `tools/` holds no script for this; the one used is
recorded in the PR.

Then AUDIT before pushing, because "it merged" is not "only the intended
changes crossed":

* **The port must cover the test files that live in the DEFAULT suite here
  and in the fork's single suite**, not only `tests/vendor/`. Today those are
  `tests/test_namer_known_defects.py` and `tests/test_namer_preference_key.py`.
  Round 5 missed the second one and the fork's stale copy failed 24 times
  against a correctly ported engine — a 22-minute suite run to learn it.
  Derive the list rather than trusting this sentence: for each `tests/*.py`
  in the fork, check whether a file of that name exists in this repository's
  `tests/`, and port the intersection.
* `git diff --numstat <pinned fork commit>` in the fork must list exactly the
  files the OpenChem branch touched under `vendor/`, and nothing else.
* `git grep openchem -- iupac_namer data tests` must be empty.
* The deletions in that diff must all be real code changes. Prose
  disappearing is the clobber above.
* Install it standalone and run its own suite: `uv venv`,
  `uv pip install -e ".[test]"`, `pytest -q` with a JRE on PATH (py2opsin
  shells out to a bare `java`, so the managed runtime under the app's data
  directory is invisible to it unless PATH says otherwise).

The fork's CHANGELOG and KNOWN_LIMITATIONS are WRITTEN, not copied: they
describe a package with one suite, its own paths and no application around it.

Three things in the fork differ from what is here, and they are deliberate, so
do not "fix" them on the way back in:

* `OPENCHEM_NAMER_DEBUG` is `IUPAC_NAMER_DEBUG` there — an OpenChem-branded
  environment variable has no business in someone else's package.
* `tests/audit/_audit_helpers.py` calls `py2opsin` directly instead of
  `openchem.chem.naming_providers`, which cannot exist standalone. `py2opsin`
  is already in upstream's `test` extra, and the fork's copy skips rather than
  fails when it is unavailable, matching the rest of that suite.
* `tests/test_namer_known_defects.py` lives beside the vendored tests there
  rather than in the default suite, because the fork has only one suite. Here
  it stays in the default run for the reason its docstring gives.
* `tests/test_namer_cyanic_perception.py` exists in both, and is NOT the same
  file. Here it reads `openchem.chem.structure_annotation.perceive`; there it
  reads the engine's own `iupac_namer.perception.Perception`, since the
  annotation layer cannot exist standalone. Port changes to it by hand, never
  through the merge script (which does not list it, deliberately).

Known, and not ours: on **RDKit 2026.3.4** the two `test_trindene_indicated_h`
cases fail with `Can't kekulize mol`. That reproduces on unmodified
`c3eac17`, so it is an RDKit change rather than anything either repository did.
This project pins 2025.9.6, where the suite is green.

## `chembl_structure_pipeline` — ChEMBL's GetParent rule, and its lists

| | |
|---|---|
| upstream | https://github.com/chembl/ChEMBL_Structure_Pipeline |
| commit | `d252cd22d67674da4fa607b761c5b5a144cfdf07` (release 1.2.4 line) |
| licence | MIT — see `chembl_structure_pipeline/LICENSE.chembl-structure-pipeline` (copyright retained) |
| vendored | 2026-09-19, round 5 branch S2 |
| files | `salts.smi` (sha256 `ee021b99…99a5`, 163 lines), `solvents.smi` (sha256 `3ff218cc…ac96`, 9 lines), and `getparent.py` |

**What it is for.** Which component of a salt a compound property describes.
ChEMBL computes every calculated property except the full weight and formula
on the parent structure (ChEMBL 37 schema documentation, COMPOUND_PROPERTIES),
and Bento et al. 2020 (J Cheminform 12:51, CC-BY) document the rule;
`chem/components.py` applies it per calculator scope.

**Why vendored rather than depended on.** Two list files and three functions
are what is used; the package brings the whole standardiser with it. The
rule is taken VERBATIM rather than re-derived because its special cases are
the point: a fragment is a salt only if it matches a list entry atom for atom
and bond for bond; when every fragment is a salt, nothing is stripped (sodium
acetate, NaCl); identical fragments are merged; a transition metal or more
than seven borons sets the exclusion flag.

**What was changed.** `getparent.py` is `get_fragment_parent_mol` and
`uncharge_mol` from `standardizer.py`, and `exclude_flag` with `METAL_LIST`
from `exclude_flag.py`, byte-for-byte; the three edits are marked
`OpenChem:` in the file: the data directory, the inlined `exclude_flag`, and
the module docstring. One decision is ours and lives in `chem/components.py`,
not here: the rule is applied only to MORE THAN ONE component, as the paper
applies GetParent "to just those compounds", because the function also
neutralises a single component and would turn a drawn zwitterion neutral.

**Upgrading.** Fetch the three source files at the new commit, re-extract the
same functions, and diff; then run `tests/test_multicomponent_scope.py`,
whose panel rows (metformin pamoate, where the counter-ion is the LARGER
component, and sodium acetate, where every component is listed) pin both
special cases.
