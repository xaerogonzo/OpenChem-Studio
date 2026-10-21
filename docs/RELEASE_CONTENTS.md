# What is in a release, and what is not

A release is the Windows zip `OpenChemStudio-v<version>-windows-x64.zip` that
`build.ps1 -Release` makes (see [ARCHITECTURE.md](ARCHITECTURE.md), "Packaging").
This page is the map: what is in it, who reads each part, and what stays in the
repository. It is checked by `tests/test_release_contents.py`, so a new top-level
folder or a change to what the build refuses cannot go unrecorded.

The principle is the usual one: **a release holds what a user needs to run the
program, plus the documents a person might read. Everything about building and
testing it stays out.**

## Inside the zip

The zip has one folder, `OpenChemStudio-v<version>\`. Sizes are from the
v0.10.0 build (about 720 MB unpacked, 3,448 files); almost all of it is the
Qt/Chromium runtime.

| Where | What | Size | Does the app read it? | Safe for a user to edit? |
|---|---|---|---|---|
| `OpenChemStudio.exe` | The launcher and the compiled application (every `.py` of ours is frozen into its archive, including the generated `_help_bundle` and `_integrity` modules) | 20 MB | It is the app | No |
| `_internal\PySide6\` | Qt 6 and QtWebEngine (a full Chromium) | 503 MB | Yes | No |
| `_internal\openchem\resources\` | The three web views: Ketcher (2D editor), Mol* and 3Dmol (3D) | 46 MB | Yes | No |
| `_internal\openchem\chem\data\` | The application's own data tables (`elements.json` and the other element, charge-model and solubility tables, the generated regulatory rulesets). Never `regulatory\sources\`, which is the hand-edited input | 4 MB | Yes, and the install check hashes every file | No: a changed or missing file is reported at startup |
| `_internal\openchem\vendor\` | The vendored IUPAC namer's data and ChEMBL's salt and solvent lists | 1 MB | Yes | No |
| `_internal\openchem\chem\*_runner.py` | Scripts handed to a separate interpreter (pKa, ADMET, the route planner) | small | Yes | No |
| `_internal\` (rdkit, openbabel, numpy, py2opsin, PIL and other libraries) | Third-party packages and their data, including OPSIN's jar | about 130 MB | Yes | No |
| `plugins\` | The bundled plugins, as **source**, so a person can add or change one without Python | 0.2 MB | Yes | **Yes, by design** |
| `docs\` | The whole `docs/` tree, as files for people to read | 4.7 MB | **No** | Yes, and nothing breaks |
| `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff` | For people | small | No | Yes |
| `LICENSE` | GPL-3.0-or-later, which a copy of this software must carry | small | No | Please do not |

The four help documents (`QUICKSTART`, `USER_GUIDE`, `SCIENTIFIC_LIMITATIONS`,
`CALCULATOR_REFERENCE`) are **not** loose files in the release. They are
compressed into the exe's archive, so saving over a copy of them cannot change
the Help window. The `docs\` folder beside the exe is a human-readable copy of
the same text and more.

Left out on purpose, so they cannot be shipped by mistake: the build refuses an
archive that holds `__pycache__`, a loose `_internal\openchem\docs\`,
`_help_bundle.py`, `_integrity.py` or `_build_stamp.py`.

What the user owns is **not** in the install at all: projects, settings, logs,
caches, downloaded tools and models live in the data directory
(`%LOCALAPPDATA%\OpenChemStudio` by default; it can be moved, and
`OPENCHEM_DATA_ROOT` overrides it; see `src/openchem/paths.py`), so
replacing or deleting the install loses none of it.

## The installer

Beside the zip, a release also offers `OpenChemStudio-v<version>-windows-x64-setup.exe`
(built from `packaging/openchem.iss`; the script is not inside it or the zip). It
installs the **same tree as the zip**, so everything in the first table applies; what
differs is how:

- **Per-user or all-users**, chosen by the person at the start. Per-user needs no
  administrator and installs under their own profile; all-users installs under
  Program Files and asks for elevation.
- **Upgrade in place.** Installing a newer version over an older one replaces it and
  first deletes the old `_internal` folder, so no stale file survives. `plugins\` is
  never cleared, because people add their own there.
- **Uninstall asks.** After removing the program it shows two unticked boxes: remove
  the settings and window layout (a registry key), and remove the caches, downloaded
  tools and recovery copies (the default data folder). Saved project files are never
  touched. A data folder the person moved elsewhere is only reported, never deleted.
- **Not code-signed yet**, so Windows SmartScreen may warn on first run.

## The repository's top level

Every tracked top-level entry, and whether it reaches a release.

| Entry | In the release? | Why |
|---|---|---|
| `src` | Yes, frozen into the exe, plus the data files above | The application |
| `plugins` | Yes, as source beside the exe | Plugins load from source by design |
| `docs` | Yes, copied beside the exe | For people |
| `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, `LICENSE` | Yes | For people, and the licence |
| `tests` | **No** | Build-time and development only |
| `benchmarks` | **No** | Measurements and drive scripts, development only (the frozen smoke script is read from here by the build, not shipped) |
| `tools` | **No** | Build and maintenance scripts |
| `packaging` | **No** | The PyInstaller spec and launcher and the installer script: they make the release files, they are not in them |
| `build.ps1`, `build.bat`, `run.bat` | **No** | Build and run helpers |
| `examples` | **No** | Plugin examples for developers |
| `scripts`, `spikes`, `prof.out` | **No** | Probes and experiments |
| `pyproject.toml`, `uv.lock`, `.python-version` | **No** | Development environment; the frozen app carries its own Python |
| `CLAUDE.md`, `BASIC_INSTRUCTIONS.md`, `project-baseline.md`, `.agent-tool.json`, `.codegraph` | **No** | Instructions and indexes for development tooling |
| `.github`, `.gitignore`, `.gitattributes` | **No** | Repository configuration |

## What the release is checked against

- `build.ps1` asserts the files that must exist, that nothing which must not be
  loose is, and that the data manifest matches the built tree.
- `tools/frozen_smoke.py` launches the built exe, and again the extracted zip.
- `tools/make_release_zip.py` validates the archive inventory (one versioned
  folder, required files present, nothing forbidden) before promoting it.
- `tools/drive_installer.py` installs the compiled installer for real, runs the
  installed app through the smoke test, upgrades and uninstalls it.

## Keeping this page true

`tests/test_release_contents.py` fails when a tracked top-level entry has no row
above, when a "No" entry is named as a source of release data in the spec or the
build script, and when the loose files the build refuses are not listed here. If
it fails, the fix is to say here what the new thing is and whether it ships.
The sizes are a snapshot of one build, not a check.
