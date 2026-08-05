# Vendored third-party code

## `iupac_namer` — structure-to-IUPAC-name engine

| | |
|---|---|
| upstream | https://github.com/leehiufung911/open-iupac-namer |
| commit | `c3eac17ffd110c7c5dd37aaad2955e06cf8c9303` |
| licence | MIT — see `LICENSE.open-iupac-namer` (copyright retained) |
| vendored | 2026-08-01 |
| fork | https://github.com/xaerogonzo/open-iupac-namer (this project's fixes, standalone) |
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
and on the current 181-row revision it scores **181/181** —
see `BENCHMARK_HISTORY.md`.) That
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

Current state: **3,300 passing, 0 failing, 17 skipped** in ~8 minutes.

The five that were still failing turned out not to be engine defects: they
asserted a non-minimal lambda numbering and three general-nomenclature-only
acylium names, and the engine's output is more correct in each case. See
`CHANGELOG.md` for the reasoning and the rule citations.

Investigating them exposed something worse than a red test, which is now the
main reason this directory carries its own documentation: inputs that name
*successfully* but to the **wrong molecule**. The benzyl cation was named
`methylbenzene` (toluene); the phthaloyl dication `1,2-bis(oxomethyl)benzene`
(phthalaldehyde). **Sixty-six** such cases have been fixed and are pinned in
`tests/test_namer_known_defects.py`, alongside 33 non-regression rows guarding
the paths the fixes could have stolen from. It runs in the DEFAULT suite,
because a wrong-molecule regression must not wait for the 7-minute run.
**None remain open** -- which says what has been looked for, not that none
exists; `KNOWN_LIMITATIONS.md` explains how to look for more.

The benchmark now reports **zero wrong structures** across its 181 molecules,
and nothing refused or unparsable. The single remaining failure is metformin,
where the engine and the corpus depict the same substance differently; see
`KNOWN_LIMITATIONS.md`.

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

Known, and not ours: on **RDKit 2026.3.4** the two `test_trindene_indicated_h`
cases fail with `Can't kekulize mol`. That reproduces on unmodified
`c3eac17`, so it is an RDKit change rather than anything either repository did.
This project pins 2025.9.6, where the suite is green.
