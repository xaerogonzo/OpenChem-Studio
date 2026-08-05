# Quickstart

Two ways to run OpenChem Studio: from a release build, or from source.

## From a release build

Windows, no Python required, fully offline. Download the zip from the
[Releases page](https://github.com/xaerogonzo/OpenChem-Studio/releases),
unzip it anywhere, and run `OpenChemStudio.exe`.

**Ship or keep the whole directory.** The `.exe` on its own does nothing —
it needs the `_internal\` tree beside it. The build is ~650 MB, almost all of
it PySide6: QtWebEngine is a full Chromium, and the app hosts three web views
(Ketcher for 2D editing, 3Dmol and Mol\* for 3D). That size is expected.

## From source

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync --extra ai --extra network --extra openbabel
uv run python -m openchem.main
```

Not `--all-extras`: that pulls in the `docking` extra, whose `vina` wheel
builds from source and needs Boost. Docking works fine through the Vina
*executable* instead, configured under Tools > External Tools — the Python
binding is an alternative, not a requirement.

<!-- help:where-data-lives -->
## Where data lives

Anything the app downloads or installs — the NMR index, sidecar Python
environments, ORCA scratch space, cached receptors — goes to a **data
directory**, never into the application folder. This is what lets a frozen
build stay read-only and a source checkout stay clean.

The default on Windows is `%LOCALAPPDATA%\OpenChemStudio`. To put it
somewhere else (a bigger drive, usually — the sidecars are gigabytes), use
**Tools > External Tools > Storage**, which writes a pointer file so the
choice survives reinstalls.

<!-- help:installing-external-tools -->
## Optional external tools

All seven are installed from **Tools > External Tools**, and none of them are
required. A missing tool degrades to a labelled "not installed" state rather
than an error.

| Tab | What it gives you | Notes |
|---|---|---|
| AutoDock Vina | molecular docking | point it at a `vina*.exe` you downloaded |
| ORCA | ab initio QM, NMR shielding, geometry optimisation | install path must have **no spaces** |
| pkasolver (pKa) | numeric pKa, true Henderson–Hasselbalch logD | one-click sidecar install (~1 GB, its own Python) |
| ADMET (hERG/CYP) | ML ADMET predictions | one-click sidecar install (torch, ~1 GB) |
| Java (Temurin) | OPSIN name parsing and naming round-trip checks | one-click JRE download |
| NMR Database | the HOSE-code shift lookup and the hybrid predictor | downloads nmrshiftdb2 (~152 MB), indexes it, then discards the download — the ~15 MB index is what stays |
| Storage | move the data directory, and uninstall any sidecar | |

## Running the tests

```bash
uv run --no-sync python -u -m pytest -q > /tmp/suite.log 2>&1; tail -5 /tmp/suite.log
```

**Invoke pytest as a module, and redirect to a file rather than piping.**
`uv run pytest -q ... | tail` has hung for ~40 minutes at almost no CPU, twice.
Redirecting also lets you watch progress while the run is going. A clean run
is roughly 1m40s.

The suite needs the optional extras installed, or ~40 tests fail on missing
imports and it looks like something is badly broken when nothing is.

The vendored nomenclature engine ships ~3,200 tests of its own, excluded from
the default run because they take ~10 minutes and cover that engine's
internals rather than our integration with it. Run them whenever you change
anything under `src/openchem/vendor/`, with Java on PATH:

```bash
uv run --no-sync python -u -m pytest tests/vendor -q
```

## The naming benchmark

The regression check on naming quality — 181 molecules, scored by OPSIN
round-trip rather than string equality. It is the arbiter for any change to
the naming engine, and it has twice overturned a conclusion reached without
it. See [`benchmarks/naming/README.md`](../benchmarks/naming/README.md) for
how to generate predictions and score them.

## Building a distributable

```powershell
uv sync --extra ai --extra network --extra openbabel --group build
.\build.ps1
```

Produces `dist\OpenChemStudio\`. The script does more than run PyInstaller:
it refuses to build over a running copy, stages `plugins\` and the
documentation beside the `.exe`, and then verifies that every payload item
which fails *silently* at runtime is actually present. A build that merely
compiled proves nothing — that check is why it exists.

`packaging/openchem.spec` is the real build definition, with a comment
explaining each bundled item.

## Getting help while you use it

Press **F1** for help on whatever panel you are working in, or click the
**?** in a panel's title bar. The help window renders the documents in this
directory directly, so what it shows and what you are reading now are the
same text.

## Next

- [User Guide](USER_GUIDE.md) — what each panel does and how to work with it
- [Validation](VALIDATION.md) — the benchmark numbers and how they were measured
- [Scientific Limitations](SCIENTIFIC_LIMITATIONS.md) — what each prediction can and cannot tell you
- [Architecture](ARCHITECTURE.md) — internal design
- [Plugin SDK](PLUGIN_SDK.md) — writing a plugin
