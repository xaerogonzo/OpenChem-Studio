# Contributing

Contributions are welcome. This project has one unusual rule, and it is the
one worth reading before anything else.

## Claims are measured, not asserted

If a change introduces a formula, a threshold, a parser regex, a model or a
scoring rule, it needs a measurement against a primary source or a real run,
and the measurement goes in the pull request.

The corollary matters just as much: **"I built it, I measured it, it was not
better, so I am not shipping it" is a completely acceptable outcome for a
pull request** — and a genuinely useful one. Several features here were
taken that far and dropped: Miller polarizability, HLB, the TSEI steric
index, a trained NMR shift model, PDBFixer-based residue repair. Each
refusal is recorded in the code where the feature would have gone, with the
numbers, so nobody re-derives it. A PR that adds such a record is a
contribution, not a failure.

If something cannot be validated, say so and leave it out rather than
shipping it with a plausible-looking number attached.

## Running the tests

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

**Invoke pytest as a module, and redirect to a file rather than piping.**
Piping has hung the suite for ~40 minutes at almost no CPU, twice. A clean
run is about 1m40s.

You need the optional extras installed, or ~40 tests fail on missing imports
and it looks like something is badly broken when nothing is:

```bash
uv sync --extra ai --extra network --extra openbabel
```

Not `--all-extras` — that pulls in the `docking` extra, whose `vina` wheel
builds from source and needs Boost.

The vendored nomenclature engine has ~3,200 tests of its own, excluded from
the default run. Run them (with Java on PATH) whenever you touch anything
under `src/openchem/vendor/`:

```bash
uv run --no-sync python -u -m pytest tests/vendor -q
```

## The naming benchmark is the arbiter for naming

Any change under `src/openchem/vendor/` gets scored against
[`benchmarks/naming/`](benchmarks/naming/) — 181 molecules, judged by OPSIN
round-trip rather than string equality. Current baseline: **180/181**.

If a change drops that number, it outranks any number of narrow tests it
fixed. The benchmark has twice overturned a conclusion reached without it.

## Testing traps specific to this codebase

A few things here look correct and are not. `CLAUDE.md` documents them in
full; the short version:

- **`repaint()` does not paint a widget that was never shown.** A paint test
  that constructs a widget and calls `repaint()` exercises nothing. Use the
  `painted()` / `ink()` helpers in `tests/conftest.py`.
- **"Some pixel is non-transparent" proves nothing** — these widgets fill an
  opaque background before their first mark. Hold the axes fixed and vary
  only the content.
- **The test suite must not touch the real registry.** An autouse fixture
  redirects `QSettings` to a file under `tmp_path`. If you change it, verify
  by counting keys, not by reading the code — the previous version looked
  correct and deposited 84 junk keys per run.
- **`QWebEngineView` spawns Chromium helpers** that must be disposed between
  tests. The autouse `dispose_web_engine_views` fixture does this; read its
  docstring before changing it, since two plausible implementations of it
  crash.

## Architecture rules

- UI code must never import `rdkit` or `openbabel` directly. `chem/` is the
  only place those are imported. This is enforced by
  `tests/test_layering.py`.
- Structure-modifying user actions go through a `QUndoCommand` in
  `openchem.commands`, so undo/redo stays correct.
- Never store a raw RDKit `Mol` in a project file — persist molblock plus
  canonical identifiers and rebuild.
- New calculation sources implement the existing provider interfaces rather
  than bolting caching onto the models.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the reasoning.

## Comments

Comments explain **why**, especially where something is non-obvious or was
got wrong once. A comment restating the code is noise, and will be asked
about in review.

## Reporting a bug

Use **Help > About** and click Copy. It reports the version, the build
commit, library versions and which external tools are detected — which is
most of what a bug report needs and saves a round trip.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
