# Architecture

## Layering

Strict one-directional dependency flow. UI code never imports `rdkit` or
`openbabel` directly — enforced by a test (`tests/test_layering.py`) that
scans `app/` and `ui/` for those imports.

```
UI (widgets/panels)
   |  dispatches
   v
Commands (QUndoCommand — undo/redo, and the future scripting/automation surface)
   |  call
   v
Services (async, progress-aware, publish typed Events)
   |  operate on
   v
Domain models (pure dataclasses, no RDKit/Qt — referenced everywhere by UUID)
   |  realized by
   v
Chem engine (the ONLY layer that imports rdkit / openbabel)
```

Events flow orthogonally to this stack: services publish typed `Event`
objects (`src/openchem/events/events.py`) on a typed `EventBus`
(`src/openchem/events/base.py`); UI panels — and eventually plugins —
subscribe by event type rather than by ad-hoc signal name.

## Package map

| Package | Responsibility |
|---|---|
| `openchem.domain` | Pure data: `MoleculeModel`, `ProjectModel`, `DescriptorValue`. No RDKit, no Qt. Molecules are identified by UUID, never filename or list position. |
| `openchem.chem` | `ChemistryEngine` (MoleculeModel <-> RDKit Mol, canonicalization to SMILES/InChI/InChIKey), `DescriptorProvider` implementations, `Importer`/`Exporter` backends. The only place `rdkit`/`openbabel` are imported. |
| `openchem.services` | `DescriptorService`, `ImportService`, `ExportService`, `ProjectService`, plus `ProgressHandle` for cancellable/progress-reporting long operations. Own the `QThreadPool`-based async execution and publish events. |
| `openchem.commands` | `QUndoCommand` subclasses wrapping service calls, giving undo/redo for structure edits and project operations from day one. |
| `openchem.plugins` | Interfaces only (`Plugin`, `DescriptorProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`). No discovery/loading yet — that arrives with the Phase 4 plugin loader described in ROADMAP.md. |
| `openchem.app` | Composition: `MainWindow`, typed `Settings`, `SessionManager`, structured logging setup. |
| `openchem.ui` | Widgets and dock panels. `EditorBackend` is an interface; `KetcherEditorBackend` (QWebEngineView + QWebChannel around the Ketcher build in `resources/ketcher/dist/`) is the only current implementation — the 2D editor is swappable without touching chemistry code. |

`tools/ketcher-host/` is a small separate Node/Vite project (not part of the
Python package) that builds the static Ketcher bundle vendored into
`src/openchem/resources/ketcher/dist/`. Rebuild it with
`npm install && npm run build` in that directory after bumping the
`ketcher-react`/`ketcher-standalone` versions in its `package.json`. See the
comments in `tools/ketcher-host/vite.config.js` for why the config looks the
way it does — bundling Ketcher under Vite requires specific
`commonjsOptions`/`define` workarounds (raw `require`/`global` references
inside `ketcher-core`'s bundled Raphael.js — see
[epam/ketcher#5565](https://github.com/epam/ketcher/issues/5565)) and
minification must stay off (it reintroduces a temporal-dead-zone bug from
`ketcher-core`'s circular imports once variable names are mangled).

## Design decisions worth remembering

- **Descriptors are not cached on the molecule.** `DescriptorValue` records
  (id, name, units, category, provider, value, timestamp, cache_state) live
  in the descriptor service/providers, so a future plugin-provided descriptor
  is indistinguishable in shape from a built-in RDKit one.
- **Descriptor computation is async even though it's currently fast.**
  `DescriptorService` tracks each value through `Queued -> Running ->
  Completed|Failed` on a `QThreadPool`, so slow future providers (docking,
  ORCA, AI) don't need a different code path.
- **Projects never serialize an RDKit `Mol` object.** `MoleculeModel` stores
  a molblock plus canonical SMILES/InChI/InChIKey and metadata; RDKit
  reconstructs the `Mol` on demand via `ChemistryEngine`.
- **Open Babel is a fallback, not a foundation.** `chem/io_backends.py` tries
  the RDKit importer/exporter first for every format and only instantiates
  (and imports) `openbabel` when RDKit lacks support for that format.
- **`ProjectModel` carries `project_version` / `application_version` /
  `schema_version`** from the start so a future format change is a migration
  in `ProjectService`, not a breaking change.

## Known TODOs

- `build.ps1` / `build.bat` are generic Nuitka packaging templates left over
  from project scaffolding (tkinter/pystray profile). They need a PySide6
  Nuitka profile (swap `--enable-plugin=tk-inter` for the PySide6 plugin,
  drop `pystray`, add RDKit/Open Babel data-file includes) before they can
  package this application. Not needed until an actual release build.
- Plugin *discovery/loading* (reading a `plugins/` directory, hot-loading)
  is intentionally not implemented yet — only the interfaces exist.
- `ConformerService` / `SimilarityService` don't exist yet; they belong to
  later roadmap phases (3D viewer, similarity search) and would currently
  have no callers.
