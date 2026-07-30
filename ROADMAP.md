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
      multi-provider — Anthropic, OpenAI, local/Ollama, plus a `ClaudeCLIProvider`
      added in Phase 7 for claude.ai subscription users (Pro/Max) with no separate
      Anthropic API key, driving a locally-logged-in `claude` CLI headless (`claude
      -p`, all tools disabled) — via a small `AIProvider` abstraction; context built
      purely from events, same pattern as `PropertyPanel`)
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
Five largely independent sub-phases, built and verified in order (6.1-6.5).

- [x] 6.1 — PubChem / ChEMBL search (bundled `plugins/database_search/` plugin,
      `DatabaseSearchProvider` ABC generic over "a chemical database with a REST
      API" — `PubChemProvider`/`ChEMBLProvider` today, room for PDB/DrugBank/
      BindingDB/local later). Search results import as a new molecule via
      `context.molecules.add(...)`.
- [x] 6.2 — Reaction prediction (bundled `plugins/reaction_prediction/` plugin):
      `RDKitTemplateProvider` (deterministic, zero-config, bundled + user-data-dir
      reaction-SMARTS templates) and an optional `RemoteReactionAPIProvider`
      (documented default target: IBM RXN for Chemistry, kept genuinely
      configurable, not hardcoded — its exact request/response contract was not
      verified against a live account).
- [x] 6.3 — Mol*-based macromolecule/crystallography viewer: `MolStarViewerBackend`,
      a second `ViewerBackend` implementation (`src/openchem/ui/viewer_backend.py`)
      added as a sibling to 3Dmol.js's `Mol3DViewerBackend`, not a replacement —
      right tool for large biomolecular/PDB/crystal structures. New
      `MacromoleculeModel` domain type (deliberately not RDKit-Mol-backed) and
      "Import Macromolecule..." action.
- [x] 6.4 — Molecular docking via AutoDock Vina: `DockingProvider` ABC +
      `VinaDockingProvider`, receptor from a `MacromoleculeModel` (6.3), results
      rendered in the Mol* viewer alongside the receptor. Vina itself runs through
      a `VinaEngine` abstraction (`PythonVinaEngine` / `ExecutableVinaEngine`,
      auto-selected) after the `vina` PyPI package turned out to have no
      prebuilt Windows wheel.
- [x] 6.5 — ORCA quantum chemistry integration (single-point energy, geometry
      optimization, opt+freq thermochemistry): `QuantumEngineProvider` ABC +
      `OrcaQuantumEngineProvider`, run via `QuantumChemistryService` — the one
      service in this codebase using `QProcess` on the GUI thread instead of
      `QRunnable`/`QThreadPool`, for real cancellation and live-streamed output.
- [ ] *Deferred*: a `ReceptorPreparationPipeline` for proper docking receptor/ligand
      prep (protonation states, waters/cofactors, missing-residue repair) — 6.4
      ships with Open Babel's default hydrogen-addition prep only.
- [ ] *Deferred*: a central `JobManager` unifying scheduling across
      descriptors/conformers/docking/quantum-chemistry — a likely Phase 7+
      "Calculation Framework" consolidation target; Phase 6 services were kept
      deliberately thin and structurally uniform so that unification is easier
      later, not harder.
- [ ] *Deferred*: full mmCIF/BinaryCIF/MMTF ingestion beyond raw PDB text, rich
      per-pose docking interaction analysis (H-bonds/clashes/pharmacophore),
      plugin-provided reaction templates, and retrofitting the new `Provenance`
      dataclass onto Phase 1-5 models — all explicitly logged as real gaps, not
      silently dropped. See ARCHITECTURE.md's design-decisions section.

## Phase 7 — Stabilization (real-world usage fixes)

First hands-on use of the built app (a real installed Vina executable, a
real window on a real screen) surfaced problems Phase 6's scripted/mocked
verification never exercised.

- [x] 7.1 — GUI layout: the six right-side dock panels (Properties, Docking,
      Quantum Chemistry, plus every plugin panel) all landed in the same
      `RightDockWidgetArea` with no tabbing, so they visually overlapped at
      anything less than a very tall window. Now `tabifyDockWidget`'d into
      one tab group. `Settings.window_geometry`/`window_state` (present
      since an earlier phase but never called) are now actually wired to
      `MainWindow.closeEvent`/init, so window size and dock layout persist
      across restarts.
- [x] 7.2 — Empty-state bugs: a brand-new/loaded-empty project now
      auto-creates and selects a blank molecule (previously nothing was
      selected, so the 2D editor's target stayed `None` and every edit was
      silently discarded until the user did File > New Molecule by hand).
      Added `EditorBackend.clear()` so switching to no-molecule/no-structure
      actually empties the canvas instead of leaving a stale drawing behind.
      `DescriptorService` now skips computation entirely for a molecule with
      no structure yet, instead of publishing a permanent "failed" row.
- [x] 7.3 — Real Vina correctness, found via testing against an actual
      installed `vina_1.2.7_win.exe`: receptor PDBQT conversion now passes
      Open Babel's rigid-receptor option (`opt={"r": None}`) — the default
      was emitting `ROOT`/`BRANCH`/`TORSDOF` records as if the whole
      receptor were one flexible ligand. `DockingPanel` now prefers a
      molecule's stored 3D conformer over its raw (possibly 2D, all-zero-z)
      molblock for the ligand, mirroring `QuantumChemistryPanel`'s existing
      pattern.
- [x] 7.4 — External Tools manager (`ExternalToolsDialog`, replacing the
      separate Vina/ORCA "Configure..." dialogs): AutoDock Vina gets a real
      Download/Update button against its public, Apache-2.0-licensed GitHub
      releases, with the exact URL/version/size shown for confirmation
      before anything downloads. ORCA is registration/EULA-gated with no
      public direct-download URL, so it only ever gets a Browse button plus
      a link to the official download page.
- [x] 7.6 — Vina and ORCA verified end-to-end against real installed
      backends (closes issue #2): real docking through `DockingPanel` and
      real single-point/geometry-optimization/opt+freq ORCA runs (with
      correct thermochemistry) through `QuantumChemistryPanel`. Surfaced —
      and fixed — three real bugs no mock/fake engine could have caught:
      `ChemistryEngine.mol_from_molblock` was silently discarding a
      conformer's explicit-hydrogen *positions* on every round-trip
      (RDKit's `removeHs=True` default), `QuantumChemistryPanel` accepted a
      molecule with no 3D conformer at all, and
      `QuantumChemistryService._on_finished` could read a QProcess's output
      before Qt delivered its last buffered chunk. See ARCHITECTURE.md's
      "Known TODOs" for the full detail on each.

## Phase 8 — Interactivity fixes (real-world usage, round 2)

More real usage after Phase 7 landed, surfacing bugs specifically about
things not *responding* to clicks, distinct from Phase 7's layout/backend
issues.

- [x] 8.1 — `DockingPanel`'s receptor/ligand combos and
      `QuantumChemistryPanel`'s molecule combo were only populated when
      `set_project()` ran (project open/new) — a molecule or macromolecule
      added afterward (File > New Molecule, an import, a plugin search
      result, or Phase 7.2's empty-project auto-create) never appeared in
      either dropdown, making them look permanently unusable. `add_molecule`/
      `_import_molecule`/`add_macromolecule` now explicitly refresh both
      panels, the same way they already refreshed the project explorer.
- [x] 8.2 — All three bundled plugins' menu actions ("Explain Selected
      Molecule", "Search Chemical Databases", "Predict Reaction Products")
      only called panel-internal focus/prefill methods, invisible whenever
      that panel was hidden behind another tab in its tabified dock group —
      confirmed live as "clicking the menu item does nothing." Added
      `UIRegistry.reveal_panel()` / `context.panels.reveal()` and wired it
      into all three plugins.
- [x] 8.3 — Small UX fixes found in the same pass: `QuantumChemistryPanel`'s
      "generate a conformer first" message referenced a nonexistent
      "Conformers panel" (it's the 3D Viewer tab's "Generate Conformers..."
      button) — fixed the wording. The AI Assistant's provider Model field
      was a plain text box requiring the exact model id typed from memory —
      now an editable combo box with current per-provider presets.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the codebase is structured to
make Phases 3-6 additive rather than requiring a rewrite.
