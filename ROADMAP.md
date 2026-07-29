# Roadmap

## Phase 1 — Application shell (in progress)
- [x] PySide6 `QMainWindow`, menu system, dockable panel layout
- [x] Project system (`ProjectModel` + `ProjectService`, `.ocsproj` JSON)
- [x] Settings (typed `QSettings` wrapper)
- [x] Session manager

## Phase 2 — Molecule editor + RDKit integration (in progress)
- [x] Embedded 2D editor (Ketcher, via `QWebEngineView`/`QWebChannel`, behind an `EditorBackend` interface)
- [x] RDKit integration (`ChemistryEngine`, canonicalization)
- [x] Live property panel (async `DescriptorService`, no manual refresh)
- [x] File import/export (MOL, MOL2, SDF, PDB, XYZ, CML, SMILES, InChI — RDKit first, Open Babel fallback)

## Phase 3 — 3D visualization
- [x] Conformer generation, geometry optimization (`ConformerService`, RDKit ETKDGv3 + MMFF94/UFF)
- [x] 3D viewer (3Dmol.js, via `QWebEngineView`/`QWebChannel`, behind a `ViewerBackend` interface)
- [x] Measurement tools (click two atoms for a distance readout, via `MeasurementService`)

## Phase 4 — Plugin architecture
- [x] Plugin interfaces (`openchem.plugins.interfaces`) — `Plugin`, `DescriptorProvider`,
      `ConformerProvider`, `PanelProvider`, `MenuProvider`, `Importer`, `Exporter`
- [x] Plugin discovery + loader (`PluginManager`, manifest-based metadata, dependency
      topological sort, transactional activate/rollback, decoupled from `MainWindow`
      via the `UIRegistry` protocol)
- [x] Plugin SDK docs (`PLUGIN_SDK.md`, plus a worked example at
      `examples/plugins/hello_plugin/`)
- [x] Hot loading (recursive `QFileSystemWatcher` + debounce, per-plugin enable/disable
      persisted in Settings)

## Phase 5 — AI assistant
- [x] Context-aware chemistry explanations (bundled `plugins/ai_assistant/` plugin,
      multi-provider — Anthropic, OpenAI, local/Ollama — via a small `AIProvider`
      abstraction; context built purely from events, same pattern as `PropertyPanel`)
- [x] Workflow assistance via canned, pre-filled prompts ("Explain Selected Molecule",
      "Generate Molecule Report") — user still clicks Send, nothing fires over the
      network on its own
- [x] Documentation generation (the "report" prompt above, over the same chat pipeline)
- [x] Credential storage via a new `context.secrets` namespace (`PluginContext`), backed
      by the OS keychain (`keyring`), namespaced per-plugin
- [ ] *Deferred*: constrained tool-calling loop (the assistant requesting safe read
      operations like SMARTS validation itself) — logged for a future phase, not built
- [ ] *Deferred*: response streaming — a complete reply is shown when it arrives, not
      token-by-token; the async `QRunnable` plumbing would support adding it later

## Phase 6 — Scientific extensions
- [ ] PubChem / ChEMBL search
- [ ] ORCA integration
- [ ] Molecular docking
- [ ] Reaction prediction / machine learning models
- [ ] Mol*-based macromolecule/crystallography viewer — a second `ViewerBackend`
      implementation (`src/openchem/ui/viewer_backend.py`) added as a sibling to
      Phase 3's 3Dmol.js-based `Mol3DViewerBackend`, not a replacement for it.
      Right tool for large biomolecular/PDB/crystal structures, which is also
      where this phase's PubChem/ChEMBL/docking work will actually produce
      structures worth viewing that way. No changes needed to domain/services/
      commands to add it — see ARCHITECTURE.md.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the codebase is structured to
make Phases 3-6 additive rather than requiring a rewrite.
