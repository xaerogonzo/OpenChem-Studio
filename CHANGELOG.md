# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Atom numbers on the 2D editor.** View ▸ 2D Structure Display ▸ Atom
  Numbers offers *Drawing atom numbers* (the atom's position in the drawing,
  from 1 — the same number the Atom Inspector's `#` column shows) and *IUPAC
  locants* (the naming engine's numbering). The status bar says how many atoms
  were numbered and where the numbering came from; a structure named by a
  retained name gets none, which it says rather than leaving a blank canvas.
  The numbers are recomputed when the structure changes and add nothing to the
  undo stack, and a set of labels is drawn only if it is for the structure on
  the canvas -- the payload carries a structure key the page checks, so labels
  computed just before an edit are refused rather than drawn on the wrong
  atoms.
- **The Atom Inspector has a Locant column**, filled from the same numbering
  the canvas draws. Blank means the atom has no locant; "?" means the
  numbering could not be computed, with the reason on the cell.

### Changed

- **Functional Groups reports ring amines, ring systems and structural
  features, each labelled with the detector that found it.** A fentanyl used
  to show one group and a tryptamine none, because the naming engine's
  detector answers a nomenclature question: a ring nitrogen is named by its
  ring, and an ether has no group form at all. It now merges that detector
  with the engine's new ring-amine and aromatic-N-H perception, a pattern
  catalogue (ether, thioether, ammonium, quaternary ammonium) and the ring
  systems already perceived — so fentanyl shows its amide, its piperidine
  amine and both phenyl rings, and MPMI its pyrrolidine amine, its indole N-H
  and both rings. Tick "Suffix-eligible groups only" for the old, narrower
  list.
- **The always-on RDKit fragment counter is now "Fragment Counts"**
  (`fragment_counts`). It shared the id `functional_groups` with the
  calculator above, and results are stored by id — so each overwrote the
  other, in the session and in saved projects. Projects saved with the old id
  are migrated on load.

- **Partial Charge (3D) has a pH-dependent option; the separate
  "Partial Charge (3D, pH-dependent)" calculator is gone.** Tick it to compute
  the charges on the dominant ionization state at the pH beside it; the pH box
  is greyed out, and ignored, while the option is off. Results saved by the old
  pH calculator are not restored (rerun it; it takes under a second), and
  results from the plain 3D calculator are unaffected.
- **The Calculator Inspector is easier to read, for every per-atom
  calculator.** It opens larger, with draggable dividers and maximise and
  minimise buttons; turns the 3D molecule to face you; labels heavy atoms in 3D
  (and N/O/S hydrogens too in 2D) in larger text; shows any atom's value on
  hover in 3D; and adds a sortable, filterable table of every value whose rows
  highlight their atom in both pictures. Copy All includes the table.
- **The 2D depiction no longer marks an ammonium nitrogen as a stereocentre.**
  A protonated amine inverts; the hashed bond it was drawn with said otherwise.

### Fixed

- **Silyl groups are named `silyl`, and a single-atom parent no longer
  invents a locant.** `(trimethylsilan-1-yl)methanamine` becomes
  `(trimethylsilyl)methanamine` -- the prefix every chemist writes for a TMS
  group -- and betaine's `2-(trimethylazanium-1-yl)acetate` becomes
  `2-(trimethylazaniumyl)acetate`. One rule governs both directions: a
  single-atom parent must not cite the locant, while a polycyclic one like
  adamantane must, and the engine had each of them the wrong way round.
- **Organosilicon, phosphorus and iodine compounds get the right parent.**
  `trimethyl(phenyl)silane`, `triphenylphosphane` and `diphenyliodanium`
  replace `(trimethylsilan-yl)benzene`, `(diphenylphosphan-yl)benzene` and
  `(phenyliodaniumyl)benzene`. The rule was never in doubt -- silicon
  outranks carbon, so the silane is the parent -- but the engine never got
  to apply it: the plan search spent its whole budget enumerating numberings
  of the benzene ring, and no silicon candidate was ever proposed. A third
  of the benchmark was naming from a truncated search like this. The budget
  is now split so one candidate parent cannot consume what another needs,
  and naming the whole 227-molecule benchmark still takes about seven
  seconds.

- **A correct name is no longer withheld when two calculations overlap.**
  The name verifier shells out to OPSIN, which wrote its input to one fixed
  filename shared by every caller, so two naming calculations in flight
  together clobbered each other -- 5 of 16 concurrent calls came back
  correct. A lost call reads as "this name does not parse", which the app
  correctly treats as grounds to withhold the name, so the failure looked
  like the namer being unable to name something it names fine.
- **Naproxen is now named exactly as PubChem names it**, and so is every
  other substituent on a fused ring. The engine said
  `2-(2-methoxynaphthalen-6-yl)propanoic acid` where the preferred name is
  `2-(6-methoxynaphthalen-2-yl)propanoic acid`: both denote naproxen, which
  is why the benchmark accepted it for months. A substituent's attachment
  point takes the lowest available locant, ahead of any substituent prefix,
  and on a fused ring the usual answer of 1 is not available at all — the
  code asked for 1, found nothing, and then stopped applying the rule
  instead of applying it to the positions that were available. Checked
  across naphthalene, anthracene, phenanthrene and quinoline, where the
  right locant differs per skeleton.

- **A substituted adamantane was named as a different compound**, and it was
  found by a corpus chosen before the engine was consulted.
  `1-(2-cyclohexyladamantan-5-yl)-N-methylpropan-2-amine` denotes
  `HQMBUZVFGUDZCC`, not the `RNYOSRZCHQLRMT` it was given: in adamantane
  numbering locant 2 is adjacent to 1 and 3, never to 5, so that pair of
  locants describes a constitutional isomer rather than a non-preferred
  name. Bare adamantyl was always right — the defect needs a second ring
  substituent to appear — which is why the 187-molecule regression corpus
  scores 187/187 both before and after the fix. The new held-out corpus
  (40 molecules drawn by a fixed PubChem CID stride, admitted by a filter
  settled in advance, engine never consulted) found it on its first run and
  now scores 40/40. A substituent's free valence takes the lowest locant
  consistent with the ring numbering, and bridged rings were the one ring
  class still deciding that by a tie-break rather than by the rule.
  Correcting it exposed a second defect underneath: the `-yl` suffix dropped
  locant 1 from stems that cannot absorb it, which also leaves five
  organoelement names better formed than before.

- **Names for substituents: a wrong stereodescriptor, a wrong prefix order and
  a wrong locant.** All three were reported from one screenshot and none was
  visible to the naming benchmark, which scores by parsing a name back.
  MPMI's R centre was named (S) — and every E/Z inside a substituent was
  inverted — because a nested carve recomputed CIP on the capped fragment.
  Acetyl fentanyl was named
  `N-[1-(2-phenylethyl)piperidin-4-yl]-N-phenylacetamide`, because a nested
  bracket reached the alphabetisation key and sorts before every letter;
  `dimethylamino` was filed under m. And a pyrrolidinyl substituent was
  numbered `-5-yl` instead of `-2-yl`, because the free valence was scored
  nowhere and a symmetry tie decided it. Nicotine, in the benchmark corpus,
  had the same locant defect.
- **A name whose stereochemistry contradicts the structure is now withheld.**
  Any stereo difference over a matching skeleton was reported as "does not
  express stereochemistry present in the structure", so a name for the other
  enantiomer was shown with a soft note. Omitted, added and contradicted
  stereochemistry are now separate verdicts.

- **The pH-dependent 3D charges were drawn on the wrong structure.** Both
  pictures showed the conformer as drawn, so a protonated amine's N-H never
  appeared, and for an acid whose removed hydrogen was not the last atom every
  later value was drawn on the next atom. The result now carries the structure
  it was computed on, and the Inspector draws that, in 2D as well as 3D -- so
  the 2D pane no longer refuses a molecule with two symmetric rings.
- **QEq results were never saved in a project.** A numpy number in their
  record was refused by the project file's encoder, logged as "Not saving",
  and the result was recomputed on every open.

### Added

- **Charge ▸ Partial Charge (3D): Ionescu 2013's EEM, two of its 24 models.**
  The Mulliken gas-phase models at 6-31G\* and 6-31G\*\*, for H, C, N, O, S
  and Ca. The implementation reproduces the paper's own EEM charges on its
  protein fragments and two test proteins (36 of 36 model-by-dataset rows),
  and that is the whole of its validation.
  - **On anything that is not a protein fragment it is an extrapolation**, and
    every result says so on screen. It can be wrong in sign without refusing.
  - **Two refusals, both from measurements.** A sulfur bonded to oxygen is
    refused: every sulfoxide, sulfone and sulfonamide checked came back wrong
    by 0.84 to 1.75 e. A charge beyond 2.051 e, the most the model reaches on
    its own validation proteins, is refused as a runaway solve.
  - **Its energy has no minimum when sulfur is present**, because the paper's
    sulfur hardness is negative; the result says when that is the case.
  - The other 22 models are not offered: only these two were measured off
    their protein domain. Why, and why the guards above amount to a patch
    stack worth reworking, is in
    `benchmarks/charges/models/ionescu_src_preregistration.md`.

- **Partial charges for a crystal (EQeq).** Opening a CIF now reports the
  charge on every atom of the unit cell, by element, with the spread beside
  the mean. It is the first calculation in the application that is about a
  periodic solid rather than a molecule.
  - Validated against the twelve MOFs the method was published with: every one
    of their 3,452 atoms reproduces the published charge. Ten of the twelve do
    so again through the application's own path; the other two depend on atoms
    written outside their unit cell, which a CIF does not carry, and the report
    says when a file does that.
  - A disordered structure, an element the sources do not parameterise, and a
    cell over the report's size budget are each refused with the reason rather
    than approximated. Four of the six CIFs shipped as test fixtures refuse for
    partial occupancy, which is the honest state of this method on real files.
  - **Not DFT charges**: the method's own paper puts them 0.11 to 0.24 e per
    atom away from ESP-derived ones, and that number travels with every result.

- **Dipole Moment and the ESP comparison can use EEM or QEq charges.**
  - Gasteiger stays the default.
  - A model that declines a molecule (EEM on chlorine, QEq on LiH) is shown
    as not applicable with its reason, never computed with another model.
  - Each dipole states its model's error against 15 experimental dipoles on
    the application's own conformers: Gasteiger 0.79 D, EEM 1.79 D, QEq
    1.69 D. Both 3D models overestimate polar molecules.

### Fixed

- **A 3D per-atom value could appear on the wrong atom.**
  - After an edit that keeps the molecule but renumbers its atoms (erasing
    and redrawing one), the Atom Inspector could show one atom's 3D charge
    or surface area on another. Ethanol's oxygen showed a carbon's charge.
  - Values are now placed on the atom they were computed for, and when that
    cannot be known the atom says so.
  - The Calculator Inspector also shows 3D values on the conformer they came
    from, and colours an EEM or QEq result's potential surface with its own
    charges.

### Added

- **Charge ▸ Partial Charge (3D, pH-dependent).** The geometry-dependent
  charges, computed on the dominant ionization state at a pH instead of the
  structure as drawn. The state is carried onto the stored conformer rather
  than rebuilt: every heavy atom and every hydrogen it keeps holds its
  coordinates exactly, and only hydrogens the state adds are placed, by MMFF94
  with every other atom held fixed. Ionization states only, never tautomers.
  It refuses instead of choosing when a proton leaves an atom whose hydrogens
  are not equivalent — a CH₂ next to a stereocentre, say — because which one
  goes is not determined by the structure. It is a separate calculator from
  the plain 3D one so that results saved under that one keep their identity.

- **Charge ▸ Partial Charge (3D): QEq beside EEM.** Rappé–Goddard charge
  equilibration can now be chosen as the method. It ships under a stated
  scope rather than the gate it originally failed: λ = ½ with the
  experimental hydrogen parameters, refusing molecules whose iteration does
  not settle or whose solution reaches a charge bound, and noting silicon
  as a disagreement with the 1991 paper. Its integrals are now evaluated in
  closed form: a 76-atom drug takes under half a second instead of minutes,
  with the same charges.
- **Charge ▸ Partial Charge (3D, EEM).** Partial charges that depend on the
  conformer's geometry, by Bultinck's electronegativity equalization with the
  parameters that paper publishes (H, C, N, O, F). They are computed on the
  stored conformer as it is, with its own hydrogens and net charge. Open
  Babel's "Bultinck" EEM file turned out to hold a different parameter set,
  so it is not used. Rappé–Goddard QEq was implemented too and was at first
  not offered (it is now; see the entry above): it reproduces the paper's
  halides but not all its hydrogen charges. Its
  solver now uses λ = ½ for every element, the rounding the paper's text
  describes, which reproduces 66 of 76 of its polyatomic charges; the
  choice was made after comparing, and is recorded as such.
  Why LiH and SiH₄ still miss is now measured rather than guessed: LiH's
  printed charge is not a solution of the paper's equations, and a 1996
  paper from the same group contradicts the printed silane sign. That 1996
  paper's disiloxane charges are reproduced to 0.002 e by the adopted λ = ½.
  Repeating the paper's own hydrogen fit also failed. Under the shipped
  equations and eight other pre-registered readings of them, neither
  published hydrogen parameter pair comes back. So the reason for LiH and
  the HF-fitted set is still not found, and nothing shipped changes.
  Nor is geometry the reason. Cioslowski's LiH reference charge was
  recomputed to 5e-5 from his own definition and basis. His slightly
  longer LiH bond leaves the fit unchanged, and a sweep of methanol and
  formamide structures brings only one near-miss into tolerance.
  The EEM has also been checked against a study it was never fitted to:
  Mathieu 2007's correlations on 194 molecules are all reproduced, and on 55
  reaction transition states five of six are. The miss is fluorine, which
  that set has only five atoms of.

### Fixed

- **Three records said the EQeq paper's supplement held data it does not.**
  `docs/sources.toml`, the model triage and the roadmap each stated that
  Wilmer 2012's supporting information gives the ionisation table (S2) and
  the 12 MOFs' per-atom charges (S5). The held PDF shows S2 only as plots and
  S5 as a one-line pointer to a zip; the table, the structures, the charges
  and the source code are accompanying files. The periodic feasibility check
  that found this is at `benchmarks/charges/periodic/FEASIBILITY.md`. The
  structures and their per-atom charges have since been fetched, so its outcome
  is now FEASIBLE with the ionisation table as a named substitution; what the
  PDF alone contains is unchanged.

- **The EEM element triage now has one exactly reproducible source.** Ionescu
  et al. 2013's twelve element-typed EEM models were reproduced from their
  published parameters on their own structures: every atom of the training set
  and of both test proteins, with the test proteins agreeing to the charge
  file's own printing precision. Two conventions the paper leaves ambiguous
  were identified by that reproduction rather than assumed — its distances are
  in angstrom, and the correlation it prints is the squared Pearson
  coefficient, which its own equation 7 contradicts. The record is TRIAGE
  check 2.8, and the models are a candidate for shipping under their own keys,
  in the protein-fragment domain they were fitted for.

- **SQE's misses now have a measured cause, and it is not where it was
  looked for.** Mathieu 2007 says its C and λ came from minimising its own
  error measure, so that point should sit at the bottom of ours. Measured: it
  does not. Our error falls 3.8% by moving to C = 56.8 eV while λ barely moves
  (0.8147 against the paper's 0.816), and the curvature at the printed point
  is indefinite, so the instrument declines to certify stationarity either
  way. Three candidate causes are ruled out — the numerical solver, the
  Coulomb kernel's form, and the parameter set, since the paper's second
  printed model misses in the same direction. The record is TRIAGE check 2.6.

- **A 3D result could name a conformer it was not computed on.** Which
  conformer a calculation used was read after the calculation finished, so a
  conformer search landing mid-run filed the result under the new conformer
  beside the old one's fingerprint. It is now read when the input is resolved.

- **A long value in Results left a blank gap under it.** A wrapped value kept
  the height its text would need in a column 100 px wide, so the charges'
  six-line Finding took seventeen lines of space and a one-line value could
  take three. Every value row in Results and the Atom Inspector is now exactly
  as tall as its text, and rows follow the panel back down when it is widened
  again. The explanatory hints in Properties sections, such as the one under
  NMR, had the same gap and lose it too.

- **The Atom Inspector showed QM NMR shifts computed for an earlier
  conformer.** ORCA spectra carried no record of the structure they were
  computed on, so they were shown unchecked. Each spectrum is now stamped
  with the conformer it was submitted with, or for a Boltzmann average the
  exact conformer set, and is withheld once that changes, with the line
  above the facts saying "computed for an earlier conformer". The run's
  method, charge and multiplicity are recorded with it. A conformer with no
  3D coordinates is now refused before ORCA runs; it used to be sent as a flat
  geometry.

- **A drawing carrying atom-map numbers broke the pH-dependent protonation.**
  The map numbers were written into the structure handed to Dimorphite-DL,
  which then returned no state at all for a mapped imidazole, and every atom
  of the result lost its map. Libraries now get an unmapped copy, and each
  atom's map is restored on the way back; the pKa sidecar is handed no map
  numbers either.

- **Results docked across the top still scrolled.** At 190 px the reader
  needed 234 px and had about 162, all of the difference its own chrome. The
  **↗** pop-out button now sits in the Results title bar beside float and
  close instead of on a row of its own, the bold title that repeated the
  **Showing** box is no longer drawn, and a short reader gives up its margins
  and tightens its spacing. It now needs 152 px, and an ordinary dock keeps
  its normal spacing. A folded note given a height between whole lines also
  no longer draws its last line cut in half.

- **A new conformer search did not refresh the Atom Inspector.** Its report
  cache was keyed on the drawing alone, so anything computed on a conformer
  kept its old value on screen until the drawing changed. The cache now
  follows the conformers too.

- **pH-dependent partial charges were on the wrong atoms.** The dominant
  protonation state came back from a SMILES round trip in the library's own
  atom order, and the charges were numbered by that order. On the reported
  O-O-C=N ring, nitrogen's +0.00 was shown on an oxygen. The protonated form
  is now renumbered back into the drawing's order before anything is
  computed on it, and every per-atom result that uses it (Hückel π density,
  Lewis sites under "major microspecies") benefits. Measured over 126
  molecule/pH pairs: each comes back as the same molecule the library chose,
  in the drawn order, stereo included. Two cases now refuse rather than
  guess: a drawn hydrogen that the protonated form removes, and two
  equivalent sites of which only one is protonated.

- **The Atom Inspector showed an earlier structure's per-atom values.** After
  an edit, a charge computed for the previous drawing was still laid over the
  current atoms, where the same number can name a different atom. Each
  per-atom result now carries the identity of the structure it was computed
  on. The inspector withholds one that does not match, and says so in the
  line above the facts ("computed for an earlier structure"); undoing back to
  that structure brings the values back without recomputing. The Results
  panel still shows the old result, marked stale.

- **Results squeezed its facts to a couple of rows in a narrow panel.** With
  Results beside Properties, the list of result names above the facts and the
  explanatory note below them took their full height, and the filter box was
  cut to "Filter f...". Measured in the running app, the reader needed 1634
  px of height before this change and 277 px after. Long notes now fold to
  three lines with **More** / **Less**, give way to one line when a panel is
  short, and never take the facts' last few rows. The filter box gets its own
  row when the panel is narrow, and in a wide panel the results filter shares
  the "Showing:" row. Copy report still carries every word.

- **Opening a result's inspector held up every other panel.** When a
  calculator you ran finished, its Calculator Inspector opened from inside
  the event delivery, so panels that listen after Properties -- the Atom
  Inspector among them -- did not receive the result until that dialog was
  closed. The dialog now opens once every panel has the result.

- **Units were printed twice** in the Atom Inspector ("-0.1394 e e") and in
  Solubility's adjustment limit ("... sampled pH values logS"). Measured
  over 1170 fact lines from 68 calculators: no other fact did this.

- **3D rotation mode could be entered and not left.** Turning it off hid the
  bar and told the page nothing, so the full-canvas overlay stayed up
  swallowing every click -- and turning it off also HID the Cancel button
  that was the only thing calling the exit. There are four ways out now: any
  of the four controls that turn it on, **Escape** from anywhere in the
  window, and **Done** on the banner over the canvas itself. Cancel still
  discards; everything else keeps the turn, and Cancel now puts the
  *structure* back rather than only the page -- it had been restoring the
  canvas while the model kept the rotation.

- **Conformer generation returned a different count every run.** The same
  molecule gave 6, then 9, then 8, then 7: the search was unseeded, and one
  run of a fixed number of embeddings finds only part of what is there
  (measured: 80% of the discovered set, a different 80% each time). It is
  seeded now and samples in batches until new shapes stop appearing.
  Measured on the reported molecule: 9 every run. On a flexible drug-like
  molecule the count rose from 20-21 to 26-27. It is slower -- about 40 s
  against 8 s on the reported case -- and it shows progress and can be
  cancelled.

  The **Details** dialog after a run now says *why* the search stopped, and
  explains the commoner question directly: asking for 20 and getting 9 means
  9 distinct shapes were found, not that anything failed.

- **The NMR calibration was fitted on whichever cyclohexane turned up.**
  Reference geometries were built from a single unseeded embedding, and
  cyclohexane's twist-boat (5.93 kcal/mol above the chair, and not what its
  experimental shift describes) came up about one run in three. Reference
  geometries are now the lowest-energy of several, and reproducible.

- **A run of conformer searches dropped the results of the drawing on
  screen.** Results are kept for the last eight versions of each molecule so
  an undo does not recompute, but drawings and conformers shared one count.
  Every conformer search reruns the descriptors on the new geometry, so eight
  searches in a row pushed out the drawing's results, including calculations
  run by hand, which nothing reruns. They are now counted separately.

### Changed

- **Settings, in one window: Edit ▸ Settings… (Ctrl+,).**
  - Four behaviours that were fixed choices are now settings:
    - whether choosing a panel from the rail hides the others;
    - whether recovery copies of unsaved work are written;
    - how long after a change a copy is written;
    - how many versions of each molecule keep their results.
  - Every default is what the app already did, and changes apply as you make
    them. Lowering the versions kept asks first, and says how many result sets
    it would remove.
  - Each kind of file dialog's remembered folder can be forgotten from there.
  - **External Tools is now a section of the same window.** Tools ▸ External
    Tools… and the Docking and Quantum Chemistry Configure buttons open it,
    on their own tool's tab.
  - A setting for results computed by an earlier version of the app was
    planned and is not in this release. It needs those results labelled with
    their version first, and they are not yet.

- **"Add to Project" is now "Send to 2D Editor".** Picking a tautomer or
  stereoisomer out of a generated set and working on it has been possible
  since that grid was built -- it adds the structure as a new molecule,
  leaves the one you have alone, and is undoable -- but the label described
  the mechanism rather than the destination, so nobody looking for a way to
  edit a tautomer would have found it. Same behaviour, plus it now reveals
  the editor instead of leaving you on whichever tab you were on.

  The **Results panel** says so too: a structure-set result's button reads
  **Send to 2D Editor...** rather than "Open in Calculator Inspector". Four
  kinds open that window and naming it is right for three of them; a set of
  tautomers goes there to be picked from, which the label never said.

### Added

- **An ionization-model cross-check on the pH-dependent charges and logD.**
  The charges use Dimorphite-DL's dominant form and logD uses pkasolver's
  pKa values, and on some molecules the two disagree about a site's
  protonation (on the O-O-C-N ring at pH 7.4, pkasolver says neutral and
  Dimorphite protonates the nitrogen). With the pkasolver sidecar installed,
  both results now name each such atom, with the pKa and its distance from
  the pH. No number changes, and neither model is declared right. pkasolver's
  answer for a structure is kept for the session, so logD, solubility, pKa and
  the charges share one call (about 3 s) instead of each paying for it.

- **LogD draws the curve it lies on.** Running **LogD (pH-dependent)** now
  gives the value at your pH and the LogD-vs-pH curve together; hover the
  curve to read logD at any sampled pH and click to keep the reading. The pH
  you asked for is one of the samples, so the kept reading there is the same
  number as the value above it. **LogD vs pH** is retired as a separate
  calculator -- a search for it still finds LogD. The value itself is
  unchanged on every branch (checked against the previous implementation's
  numbers); without a pKa sidecar it stays the labelled approximation and
  draws no curve.

- **Switch Solubility's units in the Results panel without running it
  again.** A **Units** box (log mol/L, mg/mL, mol/L) changes the chart, the
  rows, Copy report and a saved picture together. The calculator's own
  **Units** setting is gone: every unit was already being computed, so it was
  a display choice dressed as a calculation parameter. Any result can now
  declare several renderings like this; the panel offers the switch only
  when the declaration holds together, and says why when it does not.

- **Partial Charge (pH-dependent) offers MMFF94 beside Gasteiger.** Choose
  the method in the calculator's settings. MMFF94's charges were checked
  against the table Halgren published with the force field: RDKit
  reproduces every printed charge and atom type for 19 of its 20 molecules
  and ions, and the 20th disagrees with the same table's acetate row. The
  two methods are different models and give different numbers for the same
  atom. Running it again with the other method replaces the result, as
  changing the pH does. Open Babel's EEM and QEq are recorded as deferred in
  the roadmap, with the reasons.

- **Structure > Redraw in 2D**, the way back from **Use in 2D Editor**. That
  button brings a conformer across as a projection of the real geometry,
  which for a caged molecule can be unreadable -- and neither of the two
  actions people reach for first is the answer. **Clean Up** flattens the
  third dimension and keeps the overlapping positions; **Layout** re-reads
  the drawing, and on a projection whose atoms overlap that was measured
  changing the compound. Redraw in 2D reads the structure instead, keeps
  your generated conformers, and Ctrl+Z puts the 3D drawing back. It is on
  the Structure menu and the canvas right-click menu.

- **Mass spectrometry, as a capability rather than a feature.** Elemental
  Analysis draws the molecular ion's natural-abundance isotope envelope
  beside its percentages -- the picture MarvinSketch's own window shows --
  and a new **Mass Spectrum** calculator carries the ionisation modes: eight
  ions from a closed vocabulary, unit or exact resolution, and a minimum
  reported intensity. Both call ONE engine, so the envelope cannot differ
  between them.

  An ion's identity is a **composition plus a charge**, never a scalar mass
  delta. A scalar expresses `[M+H]+` and `[M+Na]+` and cannot express
  `[M+Cl]-`: an adduct with its own isotopes contributes its own envelope and
  a number has nowhere to put it. `[M+2H]2+` is in the first vocabulary for a
  related reason -- nominal binning divides the isotope shift by the charge, so
  an implementation that adds the shift straight to m/z works at every
  singly-charged fixture and silently mis-draws every ESI spectrum.

  The caption says CALCULATED and never "theoretical spectrum". `SpectrumBasis`
  is measured / calculated / predicted, declared by the producer and reaching
  the screen, so a future predicted fragmentation spectrum cannot render as
  this one does. EI fragmentation, MS/MS, fine structure and GC retention
  indices are on the roadmap behind explicit acceptance gates, and nothing here
  implements any of them.

- **A producer-declared chart channel on `ReportResult`.** A calculator may
  declare a chart the way it can already declare a 3D annotation: a closed set
  of kinds, a structural validator that fails closed, and a renderer that
  refuses a malformed annotation rather than repairing it. The view derives
  nothing -- a report whose facts contain `"C: 55.34%"` and no declared chart
  renders no chart.

- **One results window per molecule, modeless and live.** "Details..." used to
  open one calculator's report, so running a second calculator replaced the
  first window with the second and the search box built for a hundred facts was
  being handed four. Every existing button now arrives at one window holding
  everything computed for that structure, focused on the report whose button was
  pressed. Results for an earlier revision of the structure are marked stale and
  kept, never silently served and never silently blanked.

### Fixed

- **The isotope fold was exponential in the atom count**, so Elemental Analysis
  could not answer for most drug-sized molecules: aspirin took 4.1 seconds and
  ibuprofen never returned. Every isotopologue was kept as its own branch and
  merged only at the end, making the entry count `k^n` in the ATOM count --
  10.6 million branches for aspirin, 19 billion for ibuprofen -- and all of them
  were then averaged away. Merging inside the fold is exact rather than an
  approximation, because a probability-weighted mean is linear, so the reported
  distribution is unchanged and the rendered chart is byte-identical. Aspirin
  now takes 0.2 ms.

- **`MassPeak.mz` documented a fine structure the engine does not resolve.** At
  exact resolution it carries the probability-weighted mean exact m/z of its
  nominal bin, not one isotopologue's: M+1 of a CHNO molecule is 13C, 17O and
  2H at three different exact masses reported as one peak. The contract says so
  now, and telling them apart is the roadmap's fine-structure entry.

- **The ligand was prepared at neutral pH while the receptor was prepared
  at 7.4.** Ligand preparation called a bare `mol.addh()` -- Open Babel's
  hydrogen addition with pH correction *off* -- while the receptor path had
  been moved off that same call and the ligand path was left behind. The
  consequence is not cosmetic: a basic amine reached Vina typed `NA`, a
  hydrogen-bond **acceptor**, where the pH 7.4 ammonium is `N` plus an `HD`
  polar hydrogen, a **donor**. Measured on three anilidopiperidines, every
  one went from net charge 0 with an acceptor nitrogen to +1 with a donor.
  The pH control governs both now, and is labelled and documented as doing
  so.
- **A docking result recorded settings it had not used.** Scoring function,
  exhaustiveness and seed were written as the fixed literals `"vina"`, `8`
  and `None`, describing the defaults the code happened to hold rather than
  the run -- and one of them was a second copy of a default this release
  moves. They are read back from the run itself now.

### Added

- **Exhaustiveness, scoring function and random seed are settable**, in a
  new *Search* group in the Docking panel. All three were previously fixed
  in code.
- **Vinardo** is offered beside Vina as a scoring function. Its scores are
  on a different scale from Vina's and must never share a ranking, so the
  function used is shown and stored with every result.
- **A warning when the ligand is longer than the search box's shortest
  side**, which excludes whole orientations from the search. Reported,
  never silently resized -- a box that quietly grew would change what was
  docked without saying so.
- **The seed is chosen and recorded rather than left to Vina**, so a run can
  be repeated afterwards rather than only when someone thought to pin it in
  advance. Under the same Vina version and settings; the engine version is
  stored beside it for that reason.

### Changed

- **The default exhaustiveness is 25, up from 8.** A published study of
  1, 8, 25, 50, 75 and 100 found Vina's default of 8 "performs well
  overall" and that median pose error "changes little with values higher
  than 25", recommending 8 with 25 as the resources-available option. 25 is
  that value -- a documented choice, not one shown to be best for these
  receptors. 8, 16 and 32 remain selectable.
- **The docking limitations now say what Vina is and is not good at.**
  Published benchmarks place it strong at finding the right pose and weak at
  ranking affinities, so a set of close analogues scoring within a few
  tenths of a kcal/mol is expected behaviour rather than a result about
  those molecules.

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

- **The pH-dependent protonation state was chosen by the process hash
  seed.** `protonate_at_ph` took the first entry of Dimorphite-DL's
  output, which *enumerates* microspecies rather than ranking them and
  orders them by a set iteration. Measured on one molecule at pH 7.4,
  eight separate processes returned net charges of **0, +1 and +2**, and
  logD ranged **1.68 to 4.38** — a factor of 500 in partition
  coefficient. It reached six calculators: logD, the pH curves,
  electronic properties, the charge and ESP surfaces, and the shared
  "molecule at this pH" helper. The dominant state is now requested
  explicitly and the selection is sorted, so the answer cannot depend on
  arrival order.
- **Every tertiary amide was protonated at pH 7.4.** Dimorphite-DL's
  amine rule matches any nitrogen bonded to an aliphatic carbon (pKa
  8.16) with no exclusion for an adjacent carbonyl, while its amide rule
  requires an N–H — so a tertiary amide matched neither. Measured over
  sixteen drug-like molecules with literature charge states, five were
  wrong and every one was that class: DMF, DEET, N,N-dimethylacetamide,
  N-methylpyrrolidone and fentanyl. That one protonation is now removed
  and the atoms are reported; nothing else the library does is changed.
- **A correct refusal looked like a crash.** *Detonation
  (Kamlet–Jacobs)* and *Thermophysical (Joback)* both refuse for correct,
  permanent reasons — Joback's table has no ring tertiary amine group,
  and Kamlet–Jacobs needs a measured loading density no structure can
  supply — and both rendered with the same red ✕ as a genuine failure.
  A producer now declares whether a failure is a fault or a limit of the
  method, and the two are styled differently. "Needs a 3D conformer"
  stays a fault, because it names something the user can do.
- **The Calculator Inspector did not say what it was showing.** It
  rendered neither the calculator's name nor the fact that a charge
  calculation had protonated the molecule, so "Net calculated charge:
  1.00 e" sat beside a Properties panel reading "Total charge 0" for the
  same neutral structure with nothing relating the two. Both are shown
  now, and the species is declared by the producer rather than inferred
  from the numbers.
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
