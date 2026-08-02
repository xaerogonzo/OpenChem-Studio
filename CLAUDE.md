# OpenChem Studio — notes for Claude

## Running the tests

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

A clean run is **~2m45s**, ending at roughly `1177 passed, 2 skipped`. Writing
to a file rather than a pipe is worth doing because it lets you watch progress
while it runs — but it is **not** what determines whether the run finishes.

### The suite can hang, and it is not the invocation

**`QtWebEngineProcess.exe` instances accumulate and are never torn down.**
A hung run was caught with **91 of them alive**, all children of the pytest
process, all spawned within about six seconds of each other. The Python
process sat at **14 seconds of CPU** while wall clock passed 40 minutes:
blocked, not working, and producing no output to suggest otherwise.

Every `QWebEngineView` a test constructs spawns a set of Chromium helper
processes. Nothing disposes of them between tests, so they pile up until
something — handles, memory, a port — gives out and the run stops dead,
always around the webview-heavy tests at roughly 30%.

They ARE reaped when the pytest process exits: a successful run leaves zero
behind, verified. That is why this stayed invisible for so long — there is no
wreckage to find afterwards, only during. Check while a run is in flight, not
after it.

This also explains the "flaky" webview test below. Same root cause, two faces:
under resource pressure the view sometimes fails to become ready (an `F`) and
sometimes never returns at all (the hang). Whether a run finishes depends on
machine state, not on how pytest was invoked.

**If a run stalls**, check before assuming it is slow:

```bash
# Blocked, not busy, if CPU stays flat while wall clock climbs.
powershell "Get-CimInstance Win32_Process -Filter \"Name='QtWebEngineProcess.exe'\" | Measure-Object | Select-Object Count"
powershell "Get-Process QtWebEngineProcess | Stop-Process -Force"
```

**Two wrong explanations were believed before this one** — record them so a
third does not get invented:

1. A bad shell wait-loop (`until grep -q "passed|failed"`, which never matched
   because `-q` buffers). Wrong, and accepting it cost a second 40-minute hang
   the same day.
2. The `pytest.exe` console-script shim under `uv run` spawning an extra
   nested process. Plausible, written into this file as near-fact, and also
   wrong — the module form hung the very next run. The shim was correlation.

The real fix is disposing of web views in test teardown. Until that is done,
a hang is a resource leak to be killed and re-run, not a mystery.

### One known-flaky test — the same leak, milder

`tests/test_mol3d_viewer_backend.py::test_apply_visualization_sets_atom_colors`
fails intermittently on `QWebEngineView` readiness and passes in isolation.
Sometimes a sibling test in that file fails instead — which is the tell that
the test is not what is wrong. It is the leak above, caught at the point where
starting one more Chromium process is slow rather than impossible.

Re-run the file alone before treating it as a regression. Fixing the teardown
should fix this too; if it does not, then there is a second, real bug here.

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
