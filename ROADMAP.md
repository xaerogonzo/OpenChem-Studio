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
- [ ] Conformer generation, geometry optimization (`ConformerService`)
- [ ] 3D viewer (py3Dmol / Mol* / optional VTK)
- [ ] Measurement tools

## Phase 4 — Plugin architecture
- [x] Plugin interfaces defined (`openchem.plugins.interfaces`) — no loader yet
- [ ] Plugin discovery + loader
- [ ] Plugin SDK docs
- [ ] Hot loading

## Phase 5 — AI assistant
- [ ] Context-aware chemistry explanations
- [ ] Workflow assistance / SMARTS/query generation
- [ ] Documentation generation

## Phase 6 — Scientific extensions
- [ ] PubChem / ChEMBL search
- [ ] ORCA integration
- [ ] Molecular docking
- [ ] Reaction prediction / machine learning models

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the codebase is structured to
make Phases 3-6 additive rather than requiring a rewrite.
