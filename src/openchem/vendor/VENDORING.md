# Vendored third-party code

## `iupac_namer` — structure-to-IUPAC-name engine

| | |
|---|---|
| upstream | https://github.com/leehiufung911/open-iupac-namer |
| commit | `c3eac17ffd110c7c5dd37aaad2955e06cf8c9303` |
| licence | MIT — see `LICENSE.open-iupac-namer` (copyright retained) |
| vendored | 2026-08-01 |

### Why vendored rather than depended on

It is abandoned. Created 2026-05-24, last pushed 2026-05-24, three commits,
one author, no forks, no issues, and never published to PyPI. There is no
upstream to track and no release to pin, so depending on a git URL would give
all the fragility of a fork with none of the control.

It is also the best structure-to-name engine that exists in the open. Measured
against this project's own 124-molecule corpus (`benchmarks/naming`) it scores
**120/124 with stereochemistry 11/11**, beating the leading ML alternative by
26 points while needing nothing beyond RDKit and running 16x faster. That
benchmark was built before this engine was found, so the result is independent
of anything upstream chose to measure.

### What was changed

Deliberately minimal, so the diff against upstream stays reviewable:

1. **Imports re-homed.** 302 occurrences of `iupac_namer.` became
   `openchem.vendor.iupac_namer.` across 33 modules, so the package does not
   claim a top-level name. Purely mechanical, applied by regex.
2. **Nothing else.** In particular the `data/` directory is kept as a SIBLING
   of the package, exactly as upstream lays it out, because data files are
   resolved from several different module depths (`data_loader.py` walks up
   two levels, `perception/fg/acid_infix_composition.py` walks up four).
   Mirroring the layout means zero path patches; moving `data/` inside the
   package required patching each resolver and broke on the second one.

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

Current state: **2,940 passing, 5 failing, 16 skipped** in ~7 minutes. The
remaining five are narrow — cyclotriphosphazene lambda-valence naming (2) and
polycharged acylium cations (3) — and none touch the core naming path.

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

There is no upstream to upgrade from. If it ever revives, re-apply step 1 to a
fresh checkout and re-run `benchmarks/naming` before accepting the change —
the benchmark, not the diff, is what says whether it got better.
