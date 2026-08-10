# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

155 commits since 0.9.0. Summarised by capability, matching the entry
below; the git log is the per-commit record.

### Added

**Working with conformers**
- Conformers are superimposed on the lowest-energy one for display, and
  stepping between them keeps the camera where you put it — so flipping
  through a set shows the difference in shape and nothing else. The stored
  coordinates are untouched; the superposition is recomputed for viewing.
- The energy shown is relative to the lowest rather than the raw
  force-field number, with the absolute in the tooltip.
- **Use in 2D Editor** hands the editor the 3D structure *as you have it
  rotated*, keeping z, so the canvas shows a projection of the geometry
  you were looking at. Crossing bonds are what that looks like. Ketcher
  holds those coordinates through subsequent edits.
- An angle whose projection puts atoms on top of each other is reported
  rather than silently replaced with a tidier one.

### Fixed

- A drawing derived from a conformer no longer loses its chiral flag,
  which had it describing a resolved molecule as a relative arrangement
  ("AND Enantiomer" rather than "ABS") while its SMILES kept the
  stereocentre.
- The Atom Inspector no longer raises when the structure changes while an
  atom is selected — a stale index reached RDKit and unwound the whole
  event dispatch.


**Crystallography**
- Open a CIF, draw its unit cell, and report what the structure is.
- A crystal is a first-class project object — renameable, deletable,
  undoable — and stores its CIF *text*, so a later reader improvement
  reaches projects already saved.
- Clicking a site in the cell answers what that site is: the coordination
  polyhedron named from real angles, with the tolerance derived from the
  reference geometries rather than chosen.
- Lattice energy for salts with complex ions, from formula-unit volume
  rather than from ionic radii, so nitrates and hexachlorometallates are
  answerable at all.
- Ion charges are read from the CIF where the deposit states them.

**Biological assemblies**
- Read, validate and *build* the assembly a depositor annotated, from
  both PDB `REMARK 350` and mmCIF `_pdbx_struct_oper_list`.
- Dock against the built assembly, opt-in and with no silent fallback.
- An external gate scores what is built against RCSB's own generated
  assemblies.

**Chemistry**
- Lewis acid/base adduct prediction on evidence rather than a score, with
  conceptual-DFT descriptors and ΔSCF (Koopmans inverts the ammonia /
  phosphine ordering, so it is reported with that caveat attached).
- Metallocenes drawn the way people actually draw them — bonds from the
  metal to both rings — are now perceived, by normalising the drawing
  rather than forking the vendored engine.
- Oxidation states, built around refusing to answer where it cannot.
- A molecule analysis engine, with the Structure Check panel as its first
  consumer.

**Elsewhere**
- A `?` on every panel, with help search that reads the document text
  rather than only the headings.
- A periodic table that answers questions; a Structure menu and context
  menus; batch operations over the project.
- Plugins can contribute reaction templates.

### Fixed

- **The same deposit loaded as mmCIF and as PDB was not the same
  receptor.** Two-letter element symbols (Zn, Cl, Fe, Se, Na) were
  silently dropped from mmCIF because the element lookup is
  case-sensitive and the PDB archive writes them uppercase; which copy of
  a repeated ligand defined the docking box depended on chain labels that
  mean different things in the two formats; and no hydrogens were added
  to an mmCIF receptor at all. Prepared-receptor parity across the 48
  curated targets went from **0 of 48 to 38 of 48**; the remainder differ
  only in polar hydrogens and nitrogen typing, which is documented rather
  than claimed fixed. See `docs/VALIDATION.md`.
- The conformer de-duplication threshold had been calibrated on a
  molecule whose distance distribution is bimodal, and did not
  generalise.
- Results were cached under a key that survived editing the molecule.
- The docking box was drawn around a ligand that was then left in it.
- Undo now reaches the panels and the docking poses, not just the
  project; the undo stack belongs to the document, and unsaved work is
  asked about.
- Numerous Qt lifetime bugs that crashed the test suite: self-capturing
  lambdas leaking their widgets, the undo stack making window destruction
  fatal, and garbage collection running inside another test's event
  dispatch.

## [0.9.0] — 2026-08-04

First public release. The history behind it is 153 commits; this entry
summarises by capability rather than listing them, because a per-commit log
of the whole project is not what a changelog is for.

Versioned 0.9.0 rather than 1.0.0 deliberately: the functionality is
extensive and benchmarked, but the project has essentially one user, no
continuous integration, and packaging verified only on Windows.

### Added

**Structure editing and visualisation**
- 2D structure editor (Ketcher), with its native actions — Aromatize,
  Layout, Clean Up, Calculate CIP, Check Structure, explicit hydrogens —
  reachable from the application's own menus.
- 3D conformer viewer (3Dmol) with style switching, conformer navigation,
  distance/angle measurement, and molecular surfaces (vdW, SAS, MS).
- Macromolecule viewer (Mol\*) with cartoon representations and per-residue
  colouring.
- Visualisation layers that composite: per-atom colouring, per-residue
  colouring, surfaces, and continuous scalar fields painted onto a surface.
- Continuous 2D property heat maps alongside discrete atom colouring.

**Calculators**
- 46 calculators across 23 categories, driven by a registry so a new one is
  a registration rather than a UI change: physicochemical, identity,
  topology (Wiener, Randić, Balaban, Platt, Szeged, Harary), 3D geometry,
  surface area, stereochemistry, medicinal chemistry (Lipinski, Veber,
  Ghose, Egan, Pfizer 3/75, GSK 4/400, Rule of Three, QED, PAINS, BRENK),
  ADMET, Hückel π systems, dipole, CNS MPO, polarizability, steric
  parameters (exact cone angle, percent buried volume), substructure search,
  interaction analysis, structure generators and Markush enumeration.
- A generic settings dialog built from each calculator's declared
  parameters, and an inspector showing 2D and 3D projections of per-atom
  results from one shared colour scale.
- pH-dependent calculators — charge, logD, TPSA, microspecies — and pH-curve
  charts.

**Docking**
- Molecular docking via AutoDock Vina, with per-pose interaction analysis
  covering hydrogen bonds, salt bridges, π-stacking, cation-π, hydrophobic
  contacts and metal coordination, painted onto the receptor.
- A curated library of 49 receptors with binding-site boxes already located
  and validated by redocking.
- A structure contents dialog listing chains and residues, with chain
  exclusion before docking.
- Search boxes derivable from a bound ligand.

**Quantum chemistry and NMR**
- ORCA integration for single point, geometry optimisation, frequencies,
  NMR shielding and spin–spin coupling.
- TMS reference calibration, cached per method/basis, plus empirical linear
  scaling of computed shieldings, CPCM solvent and Boltzmann conformer
  averaging.
- An nmrshiftdb2 HOSE-code shift lookup with measured per-band error, built
  from a one-click download.
- A hybrid predictor selecting between lookup and ab initio per atom on
  measured expected error.
- 1D signal view with equivalence grouping, integration, first-order
  multiplicity and diastereotopic splitting; HSQC/HMBC/COSY correlation
  tables, scatter plots and contour rendering.

**Naming**
- A vendored deterministic IUPAC naming engine, working offline, with every
  generated name verified by OPSIN round-trip.
- PubChem lookup and OPSIN name-to-structure import, each labelled with its
  source and exactness rather than merged.

**Structure I/O**
- PDB, mmCIF, BinaryCIF and gzip, detected by content rather than extension.
- Deposited biological assemblies rather than only the asymmetric unit.

**Sidecars and infrastructure**
- One-click installation for pkasolver, ADMET-AI, a Temurin JRE and the NMR
  index, each into a configurable, movable data directory, each individually
  removable.
- A job system with progress and cancellation, a jobs panel, and on-disk
  logging so a failure outlives its session.
- A plugin system loading plugins as source beside the application; AI
  assistant, database search and reaction prediction ship with it.
- PyInstaller packaging into a one-directory Windows build that requires no
  Python, with a verification step for every payload item that fails
  silently at runtime.
- An About dialog reporting version, build commit, library versions and
  detected external tools, with a Copy button for bug reports.

**Benchmarks**
- A permanent naming benchmark: 181 molecules scored by OPSIN round-trip.
- NMR benchmarks including a held-out nmrshiftdb2 split and DELTA50 as
  external ground truth, scoring selection accuracy and regret rather than
  MAE alone.
- Docking redocking validation across the receptor catalogue.
- ADMET benchmarks that measure the size confound rather than reporting
  around it.

### Changed

- NMR band error constants now have one owner rather than two copies that
  had drifted apart.
- The hybrid NMR predictor no longer refuses a merge on calibration
  disagreement; it reports the calibration check instead. DELTA50 showed the
  gate cost a real gain and prevented no measured harm.
- External tool configuration points at a folder rather than a buried
  executable.
- Every outbound HTTP request identifies the application — a missing
  User-Agent was a 403 on some hosts.
- Reference documentation moved into `docs/`.

### Fixed

- **The receptor Vina docks and the receptor the analysis reads back are now
  the same receptor.** Five separate instances of this bug class were closed:
  stripped residues, alternate locations in mmCIF as well as PDB,
  symmetry-generated copies, excluded chains, and one untyped atom that made
  Vina reject an entire receptor.
- Multimeric receptors: every subunit is now seen.
- Residue numbering in interaction analysis.
- The ESP surface was computed for a molecule carrying a net charge it does
  not have — an incomplete charge map is now refused rather than defaulted.
- Per-atom polarizability overran the atom-colour range.
- A Hückel π-electron count that ignored formal charge, so cyclopentadienyl
  anion and tropylium cation — the two textbook aromatic ions — were both
  wrong.
- HOSE environments are coded from the heavy-atom view, merging two
  vocabularies that had been kept apart.
- The frozen build was broken, and the ADMET runner was never bundled.
- ORCA's scratch directory is kept space-free, as the code already claimed.
- Open Babel's format plugins are bundled, without which docking dies with
  an error naming neither Open Babel nor a file.
- Sidecar re-runs repair a partial install rather than failing on step one.
- The test suite no longer writes settings into the Windows registry, and no
  longer hangs — the cause was accumulating QtWebEngine helper processes.

### Removed

- STOUT — dead upstream, and superseded by the vendored deterministic namer,
  which is more accurate, has no ML dependencies and runs 16× faster.
- The empirical SMARTS NMR estimator, replaced by the nmrshiftdb2 lookup.
- The 3D viewer's "Color by" dropdown, superseded by the registry-driven
  calculator inspector.

### Measured and deliberately not shipped

Recorded here because it is part of the release, not an omission from it:
Miller polarizability, HLB, the TSEI steric index, a trained NMR shift
model, and PDBFixer-based missing-residue repair were each built far enough
to be measured and then dropped. See
[docs/VALIDATION.md](docs/VALIDATION.md).

[0.9.0]: https://github.com/xaerogonzo/OpenChem-Studio/releases/tag/v0.9.0
