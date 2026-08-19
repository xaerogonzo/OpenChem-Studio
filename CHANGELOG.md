# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The periodic table answers nuclear questions.** Tabs for *Facts*,
  *Atom*, *Isotopes* and *Decay*. The Isotopes tab lists every nuclear
  state of the selected element with its natural abundance, half-life,
  decay modes and branchings, and spin/parity — 5,684 states from a
  committed NUBASE2020 snapshot. Two new colour modes shade the whole
  table by stability and by longest-lived radioactive isotope.
- **Decay chains, drawn on the chart of the nuclides.** Neutrons across,
  protons up, so alpha decay is two cells down and two left and
  uranium-238 comes out as the staircase textbooks draw. Line weight is
  the branching ratio, nothing is omitted, and clicking any box follows
  the chain from there. Metastable states stack inside their own cell.
- **Set an isotope from the table, keeping your geometry.** Pick an atom
  and a row and *Apply* labels it — or every atom of that element, in one
  undo entry. Labelling an atom moves nothing, so generated conformers
  survive it.
- **Click an element, then click the canvas.** Selecting an element in
  the periodic table arms the editor, so placing an atom is two clicks
  and no dialog. A chosen isotope rides along, and the status bar says
  what is armed because arming is otherwise invisible.
- **Right-click an atom in the 2D editor** for *Isotopes…*, *Show in Atom
  Inspector*, and Ketcher's own *Edit…*. Right-clicking empty canvas
  still opens the editor's own menu unchanged.
- **The Lewis diagram zooms and scrolls**, draws a faint guide under
  every bond so the skeleton stays visible, and is laid out by whichever
  of two engines gives the roomier result for that molecule.

- **Every interactive control can say what it means.** A control now
  declares a *help contract* — what it does, at what tier of care, and
  where any external claim came from — of which the tooltip is one
  rendering. 287 contracts cover the Quantum Chemistry panel, the whole
  menu bar, the Properties panel, the Docking panel and the shared dock
  title bar; `tools/list_tooltips.py` queries them and reports what is
  still undocumented. Prompted by there being nothing in the application
  that could say what the pose table's *RMSD l.b.* column meant.
- **The docking search box can be derived from the receptor's own bound
  ligand.** *Derive from ligand...* lists what is bound in the structure
  and boxes the copy you pick; choosing a receptor from the library places
  the box on its annotated site automatically.

### Fixed

- **The orbital diagram silently dropped electrons.** It packed rows
  against the widget's height and stopped when it ran out, so polonium's
  panel ended at `5s` — **22 of its 84 electrons undrawn** — while the
  configuration string directly above printed `[Xe] 4f14 5d10 6s2 6p4` in
  full. The string and the picture disagreed and the picture lost
  quietly. The diagram now reports the height it needs and scrolls.
- **34 of 118 elements were drawn with no nucleus at all.** Every element
  with no naturally occurring isotope — technetium, promethium, polonium,
  astatine and everything above radon bar thorium and uranium. Refusing
  to invent a neutron count was right; refusing to draw the protons was
  not, and the two refusals no longer collapse into one.
- **"Typical valences" was RDKit's implicit-hydrogen model wearing a
  chemistry label.** It reported one typical valence for bromine and
  three for iodine, where both do 1/3/5/7. Relabelled to say what it is.
- **A 32-electron shell drew as a solid band**, because a fixed dot
  radius leaves uranium's N shell half a pixel between electrons. The
  radius is scaled against the arc each electron has to itself.
- **The facts table was squeezed off the bottom of the dialog**, and on a
  1366×768 laptop the action row sat 105 px below the screen with no way
  to resize — a `QTabWidget` takes the maximum minimum over its pages, so
  one tab's floor set it for all four. The dialog also gains a maximise
  button and a size grip.

- **The docking search box had never actually been placed.** The panel
  read the annotated ligand only in order to *strip* it, so every run used
  the constructor default of `(0, 0, 0)` — measured at **55.1 Å from the
  real site** on 5-HT2A (6WGT). A box far from the site is still allowed,
  because blind and allosteric docking are real uses, but it is no longer
  silent.
- **The 3D viewer was showing a different copy of the receptor from the
  one being docked.** Mol\* built *biological assembly 1* while docking
  runs against the deposited coordinates; on 6WGT that is chain A against
  chain B, so the search box was drawn about 43 Å from anything on screen.
  The viewer now shows the deposited model.
- **Interaction colouring painted every copy of a residue.** Contacts were
  named by residue name and number alone, so on a structure with several
  copies of the receptor `GLN72` highlighted all of them — 370 of 6WGT's
  388 residue keys collide across chains. The colouring now names the
  chain the pose was computed against.
- **Menu entries showed no help at all.** Qt does not display a menu
  item's tooltip unless asked, so the menu bar's explanations were
  invisible.
- **CIP stereo descriptors on the 2D canvas now follow the structure.**
  *Calculate CIP Stereo Descriptors* was a one-shot calculation, so
  editing a molecule while the labels were on left the old `(R)`/`(S)`
  and `(E)`/`(Z)` on screen until it was clicked again — a descriptor
  could outlive the centre it described. It is now a checkable **Show CIP
  Stereo Descriptors (R/S, E/Z)** toggle that recomputes on every edit and
  clears when switched off.
- **Lone pairs now follow an edit made on the canvas.** The overlay was
  refreshed on selection, undo, paste and adopt but not when the user drew
  on the canvas, and its counts are keyed on molfile position — so after
  deleting an atom the dots were drawn on the wrong atoms.

### Changed

- Showing or hiding the stereo descriptors no longer counts as a structure
  edit: it adds nothing to the undo stack and does not clear conformers.
  Ketcher's own *Calculate CIP* button does both.
- The docking panel reports where the search box sits relative to the
  annotated site before each run, and says which ligand defined it.
- Vina's scoring error is quoted with the paper behind it rather than from
  memory: a standard error of 2.85 kcal/mol on the authors' own
  190-complex set.

## [0.10.0] — 2026-08-17

328 commits since 0.9.0. Summarised by capability; the git log is the
per-commit record.

### Added

**Solubility**
- A **Solubility** category in the Properties panel: intrinsic solubility
  in logS / mg·mL⁻¹ / mol·L⁻¹, a Low/Moderate/High category, solubility at
  a chosen pH, and a pH–solubility curve. The baseline is ESOL; a pKa can
  be typed in and overrides the predictor.
- A **BCS high-solubility screening estimate** against the ICH M9 window
  (pH 1.2–6.8, ≤ 250 mL). It is bounded rather than capped: the dose number
  is sandwiched between the solubility floor and the uncapped
  Henderson–Hasselbalch ceiling, and PASS or FAIL is reported only when
  both bounds agree. Four of five reference drugs get a sound verdict where
  a capped version returned one blank class.
- **Solubility in 91 non-aqueous solvents**, via Abraham's solvation
  equation. Both halves are looked up rather than predicted — measured
  solvent coefficients and measured solute descriptors — so a compound
  nobody has measured is refused by name, and two literature sources that
  disagree by more than a factor of ten in the answer are refused rather
  than averaged.
- Salt precipitation is bounded by Avdeef's cited *sdiff 3–4* rule
  (4 log units for an acid, 3 for a base in 0.15 M NaCl), replacing a
  symmetric constant that had been inferred from a screenshot.
- Two benchmark corpora with **de-leaking**: the Solubility Challenge
  (Llinàs 2008) and its 2020 tight set, scored against ESOL with the
  General Solubility Equation as a published baseline.

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

- **The solubility benchmark double-counted three polymorph pairs**, and
  the published Solubility Challenge figures moved as a result. SC-1
  carries chlorprothixene, sulindac and phthalic acid twice each — one
  InChIKey, two solid forms, differing by up to 0.88 log. ESOL predicts one
  number per *structure* and has no representation in which the forms
  differ, so scoring both counted those compounds twice **and** charged the
  polymorph gap to the model as prediction error. They are refused now, the
  same way ampholytes are:

  | stratum | was | now |
  | --- | --- | --- |
  | all | n=67, bias −0.20 | n=61, bias −0.17 |
  | acid | n=22, bias +0.06 | n=18, bias +0.26 |
  | base | n=29, bias −0.52 | n=27, bias **−0.59** |

  Found when `benchmarks/solubility/base_bias.py` halted on the
  contradiction rather than averaging it away. The superseded numbers
  appear in PR #28's body, which is immutable history — these are the
  current ones.

- **Multi-site ionization composes multiplicatively, not additively.** The
  Henderson–Hasselbalch factor was computed as `log10(1 + Σ terms)` where
  it should be `Σ log10(1 + term)`, so a molecule with two or more
  ionizable centres never reached the doubly-ionized scaling. Measured on a
  pKa 3.0/4.5 diacid at pH 8, the old form understated the adjustment by
  **3.49 log units**. This reached logD, the logD curve, CNS MPO and the
  BBB descriptors as well as solubility. Monoprotic answers are unchanged,
  which is why it survived so long — and the correct form was already
  present one module away, in the pH-curve microspecies code.
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

**Provenance**
- **[docs/SOURCES.md](docs/SOURCES.md)** — every paper, dataset, legal text,
  standard and bundled library this project rests on, with what uses it and
  how far the citation has been checked. Generated from `docs/sources.toml`
  and guarded, so a citation that bypasses it, an entry for a deleted
  feature, or a bundled library with no licence file all fail the suite.
  60 sources; `citation` means the reference is right,
  `citation_and_claim` means the number this project *uses* was checked
  against the source.
- **Ketcher's licence, which had never shipped**, plus
  `THIRD-PARTY-NOTICES.txt` generated from the lockfile for the 318
  further packages inside its bundle. Their notices are not recoverable
  from the artifact — the build strips comments, so two banners survive in
  35 MB — so they are produced from `package-lock.json` and the licence
  files in `node_modules/`.

**Elsewhere**
- A `?` on every panel, with help search that reads the document text
  rather than only the headings.
- A periodic table that answers questions; a Structure menu and context
  menus; batch operations over the project.
- Plugins can contribute reaction templates.

### Fixed

- **A Drago E/C parameter was wrong, and only the paper could say so.**
  Methylamine's `C_B` shipped as 3.13 where Vogel & Drago 1996 Table 1
  prints 3.12 — 52 of the 53 shipped parameters matched. It never showed
  up because the validation averages eight adducts and cannot see one
  value 0.01 out.
- **`electronegativity.json` claimed the Allred set is "reproduced in the
  CRC Handbook".** Against table 9-103 of the 97th edition, 72 of 85 agree
  and 13 do not, because that table gives values for the most common
  oxidation state — a different quantity. No shipped value was wrong; the
  word was.
- **The documentation guard was checking the machine, not the
  repository.** It enumerated files with `rglob` over the whole tree —
  38,680 files against git's 1,021 — so a cited path resolved if anything
  in `.venv` matched it. It asks `git ls-files` now, and is 120× faster.
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

[0.10.0]: https://github.com/xaerogonzo/OpenChem-Studio/releases/tag/v0.10.0
[0.9.0]: https://github.com/xaerogonzo/OpenChem-Studio/releases/tag/v0.9.0
