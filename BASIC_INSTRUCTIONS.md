# OpenChem Studio — Basic Instructions

@D:\Claude Co worker\Token Save Manager Source\templates\project-baseline.md

---

## Project Overview

**Name:** OpenChem Studio
**Stack:** Python 3.11+, PySide6 (+ PySide6-Addons/QWebEngine), RDKit, Open Babel (optional extra), uv for dependency management, pytest for testing
**Entry point:** `uv run python -m openchem.main` (also installed as the `openchem` console script)
**Purpose:** Open-source, plugin-based chemistry workstation — a modern, extensible replacement for proprietary molecular editors like MarvinSketch.

---

## Project Structure

- `src/openchem/` — application source, `src`-layout package (see ARCHITECTURE.md for the full layered package map: `domain/`, `chem/`, `services/`, `commands/`, `plugins/`, `app/`, `ui/`, `events/`, `resources/ketcher/`, `vendor/` — third-party code owned in-tree)
- `tests/` — pytest suite (chemistry engine, services, commands, layering rule). `tests/vendor/` holds the vendored nomenclature engine's own ~3,200 tests and is excluded from the default run
- `benchmarks/naming/` — the naming regression benchmark, 181 molecules scored by OPSIN round-trip; the arbiter for any change to naming
- `pyproject.toml` / `uv.lock` — uv-managed dependencies
- `build.ps1` / `build.bat` — Nuitka packaging scripts; currently a generic template, not yet adapted for PySide6 (see TODO in ARCHITECTURE.md)
- `.tokensave/`, `.codegraph/` — code-graph indexes, already initialized against this repo

---

## Documentation Files

| File | Location | Purpose |
|---|---|---|
| README.md | `/README.md` | Project intro, dev setup |
| ARCHITECTURE.md | `/ARCHITECTURE.md` | Layered architecture, package map, design decisions, known TODOs |
| ROADMAP.md | `/ROADMAP.md` | Phased development plan, plus resolved investigations (naming) and documented extension points |
| CLAUDE.md | `/CLAUDE.md` | How to run the tests here, and the traps that cost real time |
| VENDORING.md | `/src/openchem/vendor/VENDORING.md` | What is vendored, from where, at which commit, and what was changed |
| LICENSE | `/LICENSE` | GPL-3.0-or-later (required for optional Open Babel bindings use) |

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full picture. In short:

```
UI -> Commands (QUndoStack) -> Services (async, typed events) -> Domain models (UUID-identified) -> Chem engine (sole RDKit/Open Babel import site)
```

UI code must never import `rdkit` or `openbabel` directly — this is enforced
by `tests/test_layering.py`.

---

## Key Files

- `src/openchem/main.py` / `bootstrap.py` — composition root, DI wiring
- `src/openchem/chem/engine.py` — the only RDKit touchpoint for molecule conversion/canonicalization
- `src/openchem/services/descriptor_service.py` — async descriptor computation (Queued/Running/Completed/Failed)
- `src/openchem/ui/widgets/ketcher_editor_backend.py` — the embedded 2D editor, behind the `EditorBackend` interface
- `src/openchem/chem/naming_providers.py` — structure <-> name; the only entry point to the vendored nomenclature engine
- `src/openchem/net.py` — every outbound HTTP request, so each one identifies the app (a missing User-Agent is a 403 on some hosts)

---

## Project-Specific Rules

- New descriptor sources (including future plugins) implement `DescriptorProvider` from `openchem.plugins.interfaces` / `openchem.chem.descriptor_providers` — never bolt caching onto `MoleculeModel` directly.
- Never store a raw RDKit `Mol` in a `.ocsproj` project file — persist molblock + canonical SMILES/InChI/InChIKey + metadata, and reconstruct via `ChemistryEngine`.
- Structure-modifying user actions go through a `QUndoCommand` in `openchem.commands` so undo/redo stays correct — don't mutate `MoleculeModel`/`ProjectModel` directly from UI code.
