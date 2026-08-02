# OpenChem Studio — notes for Claude

## Running the tests

**Use `python -m pytest`, redirected to a file. Not `pytest -q` through a pipe.**

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

The suite takes **~2m45s** and ends at roughly `1177 passed, 2 skipped`.

This form is not a preference. `uv run --no-sync pytest -q ... | tail` has hung
twice, both times sitting at **~22 seconds of CPU across 40+ minutes of wall
clock** — blocked, not working, and producing no output to suggest otherwise.
The bad form goes through the `pytest.exe` console-script shim, which under
`uv run` spawns an extra nested process (`uv.exe → pytest.exe → python.exe →
python.exe`); the good form invokes pytest as a module and writes to a file
instead of a pipe.

The mechanism is **not fully root-caused**. What is established is that the
module-plus-file form has never hung and the shim-plus-pipe form has hung
twice. If you want to spend time pinning it down, do that deliberately —
do not "just try `pytest -q` once to see", because the failure costs 40
minutes of wall clock and looks exactly like a slow test run.

Related trap: the first hang was misdiagnosed as a bad shell wait-loop
(`until grep -q "passed|failed"`, which never matched because `-q` buffers).
That explanation was wrong, and accepting it cost a second 40-minute hang
later the same day.

### One known-flaky test

`tests/test_mol3d_viewer_backend.py::test_apply_visualization_sets_atom_colors`
fails intermittently on `QWebEngineView` readiness and passes in isolation.
Sometimes a sibling test in that file fails instead. Re-run the file alone
before treating it as a regression.

### The vendored nomenclature engine's own suite

`tests/vendor/` holds ~3,200 tests belonging to the vendored IUPAC namer. They
are **excluded from the default run** (`norecursedirs` in `pyproject.toml`)
because they take ~10 minutes against the main suite's 3, and they cover that
engine's internals rather than our integration with it.

Run them whenever you change anything under `src/openchem/vendor/`:

```bash
export PATH="/d/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre/bin:$PATH"
uv run --no-sync python -u -m pytest tests/vendor -q > /tmp/vendor.log 2>&1; tail -4 /tmp/vendor.log
```

Expect `3193 passed, 16 skipped`.

**Java must be on PATH** for these, and for any test that touches OPSIN. The
app injects its managed Temurin per-subprocess (`naming_providers._java_on_path`),
but py2opsin shells out to a bare `java` and pytest does not inherit that.
Without it you get a bare `FileNotFoundError` naming neither Java nor OPSIN.

## The naming benchmark

`benchmarks/naming/` is the regression check on naming quality — 181 molecules,
scored by OPSIN round-trip rather than string equality. It is the arbiter for
"is this naming engine better", and it has twice overturned a conclusion
reached without it.

Generate fresh predictions, then score them:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
from openchem.vendor.iupac_namer import name_smiles
rows = json.loads(Path("benchmarks/naming/corpus.json").read_text(encoding="utf-8"))
preds = []
for r in rows:
    try: preds.append(str(name_smiles(r["smiles"]) or ""))
    except Exception as e: preds.append(f"<ERROR {type(e).__name__}>")
Path("benchmarks/naming/predictions_check.json").write_text(
    json.dumps({"check": {"predictions": preds}}, indent=1), encoding="utf-8")
PY
uv run --no-sync python benchmarks/naming/score.py benchmarks/naming/predictions_check.json
```

Current: **180/181**. If a change under `src/openchem/vendor/` drops this, that
outranks any number of narrow tests it fixed.

`score.py` takes exactly one predictions file. The committed
`predictions_full.json` and `predictions_deterministic.json` were recorded
against the older 124-molecule corpus and will now be **refused** by the
length guard rather than silently mis-scored — that guard is deliberate, not a
bug. They are kept as the record of what the ML alternatives scored at the
time; compare them only against the corpus revision they were made for.

## Verification standard

This project's convention, established across many sessions: **claims are
measured, not asserted.** Before shipping a formula, a threshold, a parser
regex or a model, verify it against a primary source or a real run and record
what was checked. Several things were deliberately NOT shipped because they
could not be validated (Miller polarizability, HLB, TSEI) — that is a normal
outcome here, not a failure.

Comments explain **why**, especially where something is non-obvious or was got
wrong once. A comment restating the code is noise.
