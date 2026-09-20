# Vendored third-party code

## `iupac_namer` — structure-to-IUPAC-name engine

| | |
|---|---|
| upstream | https://github.com/leehiufung911/open-iupac-namer |
| commit | `c3eac17ffd110c7c5dd37aaad2955e06cf8c9303` |
| licence | MIT — see `LICENSE.open-iupac-namer` (copyright retained) |
| vendored | 2026-08-01 |
| fork | https://github.com/xaerogonzo/open-iupac-namer (this project's fixes, standalone) |
| fork commit | `7a82eb0` — synced 2026-09-20, corresponding to this repository's `naming-cyano` (PR #136, master `4a9dfec`): naming round 6 on top of round 5's `9967a62` and its follow-up `dedf2e8`. Standalone suite 5,086 passed / 18 xfailed / 2 failed, the two known RDKit-2026 trindene cases, unchanged from round 5's 5,012 / 2 |
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
