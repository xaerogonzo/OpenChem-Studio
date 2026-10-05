# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Tautomer NMR (P5), step 4 of 5: the viewer

- **Tautomer peaks drawn over the 1D spectrum.** `NmrSpectrumWidget` draws one trace per tautomer (its own colour, sticks as tall as the hydrogens they stand for, on the molecule's own scale; labile N/O/S hydrogens dashed) and the fast-exchange average (near-black, thicker, with a dot). View state like the measured reference: never on a shielding axis, never touching a signal, and it works for a molecule with no spectrum of its own. `TautomerOverlayControls` lists a checkbox per trace with its population (only when validated) or relative energy, the average's row (disabled, with the reason, when unavailable), what the average covers, and what it leaves out, with the app's one-based atom numbers. `NmrViewWidget.set_tautomer_nmr` wires it to the viewer's nucleus choice.
- **Quantum Chemistry panel**: **Tautomer NMR...** (needs a selected distribution run with stored geometries; confirms the job count and method first), **Average NMR over conformers** (remembered, off by default), and **View Tautomer NMR...** for a stored run; the peaks go over the molecule's referenced spectrum when it has one, otherwise into their own window. Runs appear in the Runs combo as "Tautomer NMR". `chem/tautomer_nmr.tautomer_overlay` builds the traces (pure); a tautomer whose NMR failed is listed with its reason, never silently absent.

### Tautomer NMR (P5), step 3 of 5: the population-weighted fast-exchange average

- **`chem/tautomer_nmr.average_tautomer_nmr(nmr, distribution)`** combines a tautomer NMR result with the distribution's validated populations: a carbon's 13C shift is the weighted mean over the tautomers; a carbon's 1H peak is the weighted mean of its hydrogens' mean shift, only when the carbon has the same number of hydrogens in every tautomer; hydrogens on N, O, S or any heteroatom are never averaged. Each peak left out is returned with its reason, never dropped silently.
- **There is no partial average.** It is unavailable, with the reason, unless the distribution is validated and complete, the NMR result is complete and was computed from that same distribution run, every spectrum is referenced (ppm, not shieldings), the populations sum to one, the structures are stored, and the tautomers' heavy atoms correspond. Hydrogens on one carbon are merged into one peak per tautomer, so diastereotopic hydrogens are not resolved. Mutation-checked.

### CI: a crashed Windows shard is retried once, and said so out loud

- The Windows suite shards die with an access violation and no failed test on about half of master's pushes. A shard that **crashes** (a fatal exception, no pytest summary line, no test reported FAILED or ERROR; decided by `tools/ci_classify_crash.ps1`) is now rerun once, with a warning annotation naming where it died, the crashed attempt's log uploaded, and a notice if the retry passed. A real failure, a timeout, or a crash that repeats still fails the job. Each attempt keeps its own 30-minute budget (the job's limit is 65), so the gate on suite growth is unchanged. The crash annotations are the only record of the crash rate over time, which is how a fix will be judged.

### Tautomer NMR (P5), step 2 of 5: the NMR run over a distribution's tautomers

- **`QuantumChemistryService.request_tautomer_nmr`** runs `nmr` on the optimized geometry each tautomer of a stored distribution kept (its lowest calculated conformer), or, with `per_conformer`, on every succeeded conformer of that stereoisomer, which are then Boltzmann-averaged atom by atom. Sequential, one job slot for the whole run, one `TautomerNmrResultReady` and one stored run (`tautomer_nmr`). Shifts are referenced with the same cached TMS reference or scaling an ordinary NMR calculation uses; with none cached the run stops at its first result and says so, instead of publishing shieldings that read as shifts.
- **Failure handling**: a structure whose output will not parse, or whose stored geometry cannot be read, fails that tautomer and the run continues; one failed conformer fails its tautomer rather than averaging the survivors; a crash or cancellation ends the run with no result. The result is never a `SpectrumComputed`, because its atom indices are the candidates', not the user's molecule's.
- **`chem/tautomer_nmr.py`** chooses the structures from a stored result and reports, never substitutes, a tautomer with no stored geometry or no success. `TautomerNmrResult` round-trips through the project codec. No UI yet (steps 3 and 4).

### Tautomer NMR (P5), step 1 of 5: the design, and keeping each tautomer's optimized geometry

- **`docs/TAUTOMER_NMR_DESIGN.md`**: tautomer peaks on the NMR spectrum, as agreed: one trace per tautomer, plus a population-weighted fast-exchange average trace offered only for a validated, complete result; one geometry per tautomer (its lowest calculated conformer) by default, with per-conformer averaging as an optional, off-by-default setting; and the per-heavy-atom averaging rule, which excludes N/O/S hydrogens and carbons whose hydrogen count changes between tautomers, and names every exclusion.
- **The service now keeps the geometry ORCA's optimization ended at** for each succeeded tautomer candidate (`CandidateResult.optimized_molblock`, and the result entry's `optimized_molblock`); it used to read it and discard it, so a later calculation on a tautomer could only start from the embedded start geometry. No energy, model version or percentage changes.

### Tautomer distribution: a validated model now shows population percentages

- **A population percentage appears, for one model only.** `M062X def2-TZVP` with the default conformer search (revision 5, top-3 of 50 conformers) passed the preregistered validation (#192), and the service now stamps a result `validated` when a validation record matches its exact `model_version` AND the current criteria hashes and the result's candidate set is complete (`chem/tautomer_validation.validation_branch_for`; the record is `chem/data/tautomer_validation_record_v2.json`, derived from the committed artifact and refused if edited). Any other method or basis, the Full ORCA conformers setting, another RDKit release, changed criteria or an incomplete candidate set keeps percentages withheld (an incomplete set of the validated model shows energies as `ranking_only`).
- **What that does and does not mean** is stated in the result text, the User Guide and `docs/VALIDATION.md`: eight small two-state systems (four held out) is a narrow benchmark, not a general probability model.
- The two criteria/record JSONs are bundled in the frozen build (`packaging/openchem.spec`), guarded by a test, because a build missing them would silently read every result as unvalidated.

### Tautomer validation v2: the preregistered run PASSED (nothing wired yet)

- **The criteria-v2 run** (revision 5, `M062X def2-TZVP`, 61 ORCA optimizations, clean tree at `8f03ebb7`) recorded `validation_gate_outcome: passed`: all eight required systems, regression and held-out partitions both, pooled MAE 0.26 kcal/mol, largest per-system maximum error 0.99 (held-out: 0.85). The artifact, with every optimized geometry and conformer-pool record, is `benchmarks/tautomer_validation_v2/`; `docs/VALIDATION.md` states what a four-system, small-heterocycle held-out set does and does not establish.
- **No behaviour changes yet.** Results still compute as `unvalidated` and show no population percentage; the lookup that lets a matching record authorize one is a separate change.
- Adds `docs/LITERATURE_LOG.md`: every paper opened in Phase R, what it was read for and what came of it, including the dead ends.

### Tautomer validation v2: the preregistration (nothing has been run)

- **`chem/data/tautomer_validation_v2.json`** freezes a second attempt at the percentage gate for model revision 5 at `M062X def2-TZVP`, with the same tolerances as v1 (not retuned). Every system carries a `partition`: `regression` (the four v1 systems v4 was shaped on, so a pass is not independent evidence) or `held_out` (indazole, hypoxanthine and both triazoles, frozen in the manifest before v4 existed). The preregistration carries a `design_disclosure` (v4 was designed after v3 failed; the exploratory acetylacetone check; the method screen; the aggregate Goller sentence that was read; the defect fixed as revision 5) and pins the manifest and the method-screen rule by hash. Its declared model string is compared with what the code would run, and the runner refuses on any difference.
- **The closed schema** (`chem/tautomer_validation.py`) now accepts schema version 2 beside 1; v1's three content hashes are unchanged and tested against its artifact.
- **The runner** (`tools/tautomer_validation.py`) prints the ORCA job count before it starts, stores every job's optimized geometry and conformer-pool provenance (revision 3's artifact could not say which minimum a job reached), reports the gate by partition, and refuses the revision-3 file.
- **`benchmarks/tautomer_validation/method_screen/`** commits the rule, scripts, energies and results behind the method choice, with what it does not show. Three newly cited sources are registered (Perry 2025, Ganyecz 2019, Barone 2023).

### Tautomer model revision 5: azole tautomers were being merged into one candidate

- **Fixed: tautomers that differ only in which aromatic ring nitrogen carries the hydrogen were one candidate.** The candidate identity was a hash of the structure's molblock, and a molblock written for the aromatic form carries atoms and bonds but not that hydrogen count, so 1H- and 2H-indazole, 1H- and 4H-1,2,4-triazole, 1H- and 2H-1,2,3-triazole and hypoxanthine's N7-H and N9-H forms hashed identically and were deduplicated. The Tautomer Distribution calculator therefore calculated ONE structure of a two-state azole system and reported it complete (hypoxanthine kept 3 of the 8 states RDKit enumerates). The identity now also hashes the isomeric SMILES, which does carry the hydrogen placement. Found by the preregistered held-out systems' mapping check, which asked whether each reference tautomer was among the enumerated ones. `TAUTOMER_MODEL_REVISION` is 5 (a different deduplication is a different model); no model has been validated, so no percentage is affected.

### Tautomer validation: the held-out manifest, frozen before v4 exists

- **`benchmarks/tautomer_validation/heldout_manifest_v2.json`**: indazole, hypoxanthine, 1,2,3-triazole and 1,2,4-triazole, selected by a written rule that never looks at any model's behaviour, pinned by hash (`tests/test_tautomer_heldout_manifest.py`). Göller 2022's Table 1 fails its own gas/water/delta check for adenine and 1,2,3-triazole, so adenine is excluded and the 1,2,3-triazole reference is Balabin 2009's CCSD(T)/CBS 3.98 kcal/mol (which equals the value Göller's own delta column implies). The SI's structure names fixed a mis-read of the scheme drawing for 1,2,4-triazole. Four sources registered.

### Tautomer distribution model revision 4: a conformer search (no validation claim)

- **A conformer search per stereoisomer** (`chem/tautomer_conformers.py`). Revision 3 optimized one embedded geometry; for acetylacetone that start kept the enol's O-H 4.76 A from the carbonyl and the result sat 14.7 kcal/mol too high (measured, PBE0/def2-TZVP, and the cause of v3's failed preregistered gate). Now 50 ETKDG conformers (seed never 0: `randomSeed=0` returns N identical conformers), MMFF94 (UFF as a stated rule where MMFF has no parameters), the project's own `distinct_conformers` (heavy atoms plus polar H, so OH rotamers stay distinct), then the lowest 3 go to ORCA; a **Full ORCA conformers** checkbox optimizes every distinct one up to 10. Identity is the conformer's recipe, never its rank; a selection is not a truncation, a pool cut at the cap is.
- **The model identity** gains the conformer policy (engine release, effective ETKDG parameters, prune rule, prefilter rule, counts) and `TAUTOMER_MODEL_REVISION = 4`. The two modes are different models, each with its own `model_version`. Results say "lowest calculated conformer", never "lowest-energy conformer".
- **`M062X def2-TZVP`** added to the method presets. It is the method a development-set screen selected (PBE0 and a double hybrid each failed two rankings); that screen is not a validation claim.
- The result table gains Conformer, Conformers selected, Lowest calculated for stereoisomer and Conformer recipe fingerprint columns, and the provenance records every conformer pool (counts, force field, retained and selected recipes).

### Survey items 3-7: IR export, chart zoom, table export, tautomer table

- **IR JCAMP-DX export** (`chem/ir_export.py`, an **Export JCAMP-DX...** button on the IR view): the predicted bands as a labelled peak table (wavenumber, km/mol), predicted and harmonic, with the frequency scaling and any imaginary modes named and the imaginary ones left out. A peak table and not a broadened trace, because the viewer applies no lineshape; this application's own overlay import refuses peak tables by design, so the file is for other tools.
- **Line and scatter charts zoom** with **Ctrl+wheel** (around the cursor), **Shift+wheel** pans the line chart, double-click resets, and the drawing clips to the plot. A plain wheel is deliberately NOT taken: these charts sit in a scrolling reader. The NMR correlation tabs gain a **Reset Zoom** button (enabled only while zoomed). Histograms and stick charts are unchanged.
- **Every result table can be copied or saved:** right-click the Quantum Chemistry spectrum, hybrid and correlation tables and the Docking poses, Interactions, contacts and Alignment tables for **Copy table as CSV** / **Export CSV...** (what the table shows, hidden columns left out, UTF-8 with a BOM, formula-looking cells protected).
- **Tautomer distribution result: Export table (CSV)...** in its dialog, one row per candidate at full precision with the absolute and relative energy, status, stereo search, what qualifies the energy, and the model identity. The population column is blank unless the model is validated, so a file cannot carry a percentage the screen was not allowed to show. Each entry now keeps its absolute energy (additive metadata).
- Item 6 of the survey (reset settings elsewhere) needed no code: no viewer other than the NMR one has persisted settings to reset.

### IR viewer navigation and a right-click picture menu on every plot (survey items 1 and 2)

- **The IR spectrum is navigable.** Wheel-zoom around the cursor, drag to pan, double-click or the new **Reset Zoom** button to restore the full span, a cursor wavenumber readout, and bands outside the window neither drawn nor clickable. Zoom is view state only: a stick's height still means the same intensity at every zoom (the scale is the whole spectrum's strongest band), and a click now registers on release, so a drag no longer selects a band. Reuses the NMR plot's `plot_zoom` arithmetic.
- **Copy Spectrum Image** on the IR view, and a **right-click Copy picture / Save picture** on the IR spectrum, the NMR spectrum, the NMR correlation plot, the pH curve and the other chart widgets, through the same `picture_export` actions the results reader uses (a reader chart keeps its own menu, with no duplicate). A copy now says what it did even where there is no status line.
- Not verified on screen with real fonts (the offscreen renderer has none); the geometry is covered by tests.

### Tautomer distribution: the validation run, outcome `attempted_failed` (Phase O, commit 2 of 2)

- The preregistered gate was run once on commit `239f1e6a` with real ORCA at `PBE0 def2-TZVP` (20 optimizations, every tautomer complete). **It did not pass**: the ranking gate failed on cytosine, acetylacetone and 2-pyridone (acetaldimine passed), so **no population percentage is shown**; results remain `unvalidated`. The artifact is `benchmarks/tautomer_validation/tautomer_validation_artifact.json` and the outcome, with what it does and does not establish, is in `docs/VALIDATION.md`. The acetylacetone enol landing 5.3 kcal/mol above the diketo is consistent with the single-start-geometry limitation but was not verified.

### Tautomer distribution: the validation gate is preregistered (Phase O, commit 1 of 2; branch `tautomer-validation-gate`)

- **The criteria are frozen before any number exists.** `chem/data/tautomer_validation.json` declares the model under test (`PBE0 def2-TZVP`, ORCA 6.1.1, gas phase, electronic energy, no ZPE or thermal terms), the gate rules and tolerances (reference tie 1.0, MAE <= 1.0 and maximum error <= 2.0 kcal/mol, every required system on its own, no compensation between systems) and the reference values, each with its source, DOI, table, units and zero. It is a **closed schema** (an unknown key is refused, so a result cannot be carried in under another name) and `tests/test_tautomer_validation.py` pins its three content hashes. The file contains no computed value; the measured artifact and the gate outcome are the second commit.
- **Four required systems, two optional.** Cytosine (Trygubenko 2002, three application-level tautomers, CCSD(T) at the basis-set limit), acetylacetone (Belova 2014, from the Supporting Information's own energies at MP2/cc-pVTZ, not from its Table 1, which mislabels two B3LYP rows), acetaldimine/vinylamine (Fogarasi 2010, CCSD(T)/cc-pV5Z) and 2-pyridone/2-hydroxypyridine (Goller 2022, Table 4). Formamide and acetaldehyde are reported but never gate. Rotamers and E/Z isomers are not tautomers: a reference tautomer's value is the lowest of its source variants (cytosine 2a/2b is one enol).
- **A reference row that is not the quantity the model computes cannot gate.** A solvent, zero-point or thermal term, a vertical energy or an experimental equilibrium is refused at load, and a row's reference value must agree with the energy difference of the source's own printed absolute energies.
- **Disclosed before the run:** Goller 2022's own PBE0-D3(BJ)/def2-TZVP energies put 2-pyridone below 2-hydroxypyridine, against a reference that puts it above, so the 2-pyridone system is expected to miss the ranking gate. The tolerances were not loosened and the system was not made optional for that reason; a recorded `attempted_failed` is a legitimate outcome here, as it was for Miller polarizability, HLB and TSEI.
- `chem/tautomer_validation.py` holds the comparison as pure functions (tautomer-level energies, rebaselined to the lowest reference-listed tautomer on each side rather than the application's global minimum; one error per reference tautomer, not per pair) and the artifact builder, which keeps `validation_execution_status` (did the experiment run to completion) apart from `validation_gate_outcome` (`passed` / `ranking_only` / `attempted_failed` / `not_evaluable`). `tools/tautomer_validation.py` runs it through the application's own service with real ORCA.

### NMR viewer: a measured JCAMP-DX reference overlay, and export (branch `nmr-viewer-p3`)

- **Import Reference...** draws a measured 1D NMR spectrum (JCAMP-DX, `XYDATA` with a ppm or Hz axis) behind the prediction. It is a separate immutable record (`chem/nmr_measured.py`): provenance (filename, nucleus, frequency, solvent, format) plus a SHA-256 of the **original bytes**, so two different files stay distinguishable even if they render alike. **Scaling is display state** (`set_reference_scale`), the record is never rewritten, and import, scale, peak marks and clear are tested never to change a signal, `coupling_groups`, shift or integral. An FID, a non-NMR file, an Hz axis with no spectrometer frequency or an unknown unit is refused by name; a reference for another nucleus is kept but not drawn, and the note says why. Reference peaks are plain local maxima of the original trace.
- **Export** (a menu) writes the predicted spectrum from the signal list and the viewer's parameters, never from the screen: a JCAMP-DX spectrum that round-trips through this application's own reader, an SD file with explicit hydrogens and per-atom predicted shifts (atom numbers are the molfile's), and a one-page PDF. All three say they are predicted; the JCAMP-DX notes it is a first-order model. The decoupled switch reaches the export.
- Controls moved to a third toolbar row so the first rows stay readable at 1300 px.
- Not covered, by design: NTUPLES / complex (real+imaginary) NMR files and peak-table JCAMP are refused, not guessed at.

### NMR viewer: overlapping signals, explicit H, table views and palettes (branch `nmr-viewer-p2`)

- **Clicking through overlapping multiplets.** `signals_at` returns every signal under the cursor in a deterministic order (nearest, then shift, then atom indices; never container order); the first click selects the nearest and repeat clicks cycle, wrapping. The cycle ends when the cursor leaves the union of the hit regions that began it (measured in ppm, so a resize does not end it), when the view range changes, or when a new spectrum loads. Selection still goes through the existing `_select_signal`.
- **Explicit H** draws the 2D structure's implicit hydrogens as atoms on a copy (`render_2d_svg(explicit_hydrogens=...)`), keeping every heavy-atom index; the molecule, the signals and the selection are untouched.
- **The signal table is now three tabs over the same signals** (Signals, Atoms, Couplings). Every row carries the owning signal's atom-index identity, never a row number, so a selection in any tab resolves to the same signal even after the Signals table is sorted. Atom numbers are the app-wide one-based ones; a signal with no calculated coupling has no Couplings row.
- **Three fixed colour palettes** (default, colour-blind safe, high contrast) for the plot and the structure highlight together; presentation only. Part of the reset defaults. (Not persisted: no viewer setting is, and one that was would be inconsistent.)
- **The controls are now two toolbar rows.** One row overflowed into its "..." menu at 1300 px, hiding the newest controls and both Reset actions; seen only by rendering the whole viewer.

### NMR viewer: legend, Reset Settings, and report links that select the tab (branch `nmr-viewer-p1`)

- **A "Legend" checkbox** draws a key for what is on the plot (predicted signal, selected signal, and the integral and solvent line only while they are shown), in whichever top corner hides less signal. Display-only, off by default, and it never touches a signal.
- **"Reset Settings"** restores every toolbar control to its default and **keeps the zoom**; Reset Zoom keeps the settings. The defaults are one frozen `NmrViewerSettings` (`NMR_VIEWER_DEFAULTS`) read by construction, by Reset and by a test asserting a fresh viewer reports exactly them, so a control added without a default fails loudly instead of surviving a reset.
- **The Molecule Report's "Open IR" / "Open NMR" links now select the matching Quantum Chemistry tab** (they used to reveal the panel only), via `QuantumChemistryPanel.show_spectrum_tab`.

### RDKit tautomer preference ordering, and a heuristic-vs-ORCA cross-check (branch `tautomer-rdkit-ranking`)

- **The RDKit "Tautomers" generator now orders its results by RDKit's own preference score** (`TautomerEnumerator.ScoreTautomer`, the same rules that silently pick the "(canonical)" one) and labels each "heuristic rank N of M". It is not an energy and not a probability: equal scores are a **competition-ranked tie** (10, 10, 5 is rank 1, 1, 3, marked ", tied"), the raw score is stored unrounded, the RDKit version is recorded (the score is implementation-defined), no percentage or bar is drawn, and the shared grid's validated-population `score` field is never used.
- **The ORCA Tautomer Distribution result gains an "RDKit heuristic" line** comparing RDKit's most-preferred tautomer with ORCA's lowest energy, tautomer by tautomer (a multi-stereoisomer tautomer is compared once). The verdict is four-valued, `agrees` / `differs` / `tied` / `indeterminate`, and is `indeterminate` for any incomplete ORCA result. A tie on either side (RDKit scores equal, or ORCA energies within 0.5 kcal/mol, a comparison resolution and not a claim of degeneracy) is `tied`, never `differs`. Informational only: it feeds neither populations nor the validation gate.

### Tautomer Distribution enumerates undrawn stereo and represents a tautomer by its lowest stereoisomer (branch `tautomer-stereo-enumeration`)

- **Replaces #177's single pinned configuration with a real stereo search.** Every unique stereoisomer of each tautomer's undrawn centres and C=C bonds is its own ORCA job; a tautomer's energy is its **lowest successful** stereoisomer. Enantiomer pairs are calculated once (mirror image = tetrahedral tags inverted only, so E/Z isomers and diastereomers are never merged), and a drawn centre keeps its configuration.
- **Stated model assumptions, not implementation details:** one tautomer is one statistical state, enantiomer multiplicity is deduplicated and assigned unit degeneracy, and higher-energy diastereomers contribute no separate weight. They are held as a frozen `ModelPolicy`; the model version (`tautomer-boltzmann-v3|...`) is built from that structured policy, never from the English shown in the result, so rewording prose can not mint a new model.
- **Completeness is a per-tautomer state, `complete` / `incomplete` / `failed`,** and the single authority for whether populations may appear. A failed or dropped stereoisomer makes its tautomer incomplete even if another succeeded; a tautomer over the stereo cap (8 unique jobs, counted AFTER enantiomer deduplication) uses a deterministic fallback configuration and is incomplete even though its optimization succeeded. The energy baseline and a machine-readable `energy_reference` follow completeness, and an incomplete tautomer is never labelled "lowest-energy stereoisomer".
- The cost confirmation names jobs and tautomers and warns before a truncated tautomer is run. The Results panel gains "Tautomers" and "Stereochemistry" lines; the driver's `tautomer_report` can print the per-job table.

### Tautomer Distribution compares candidates in one stereo configuration (branch `tautomer-stereo-honesty`)

- **A molecule with two or more undrawn stereocentres no longer has its tautomers compared across arbitrary diastereomers.** Each candidate was embedded under its own seed, and the embedder picks an arrangement for every element the structure leaves unspecified: measured on 2,3-dimethylcyclohexanone, the keto and enol forms landed on different cis/trans ring configurations across seeds, so the reported gap mixed a tautomer difference with a diastereomer difference nobody asked about. The first candidate that embeds now decides each undrawn element's configuration from its real 3D coordinates, and every later candidate is constrained to match; an element the user drew is never touched. An undrawn C=C (the tautomer enumerator marks a bond it just made as "any", which embedded E and Z across seeds) is fixed the same way.
- **It fixes one configuration; it does not enumerate the others** (that would multiply the ORCA jobs by the number of stereoisomers). So when the fixed choice can move an energy (diastereomers or E/Z, not a lone enantiomer pair, whose energies are identical), the result says so: a "Stereochemistry" line in the Results panel's summary and a sentence in the Quantum Chemistry panel's status line. The label under each structure still shows the stereo as drawn, never the configuration that was pinned.
- The result's model version moves to `tautomer-boltzmann-v2`, since the energies now describe a different, consistent quantity; a stored stamp from v1 can never authorise a percentage under it.

### Runs history refreshes when a run finishes (branch `tautomer-live-drive`)

- **A run that finished while its molecule stayed selected never appeared in the Quantum Chemistry panel's "Runs" list**, and "View Tautomer Distribution..." stayed disabled, until you switched molecules and back. Found by driving the real app with real ORCA (`tautomer_run`/`tautomer_report` steps, `benchmarks/visual/tautomer_distribution_reachability.json`) after the unit tests and a direct-call live check had both passed -- they refreshed the list by hand, which the app never does. The panel now adds a finished run to the list straight away. Every run type had the same gap; it was only visible for tautomer runs because they show a dialog instead of painting the panel's own tabs.
- **A tautomer candidate is no longer labelled with a stereocentre nobody drew.** Racemic propylene glycol came back as `C[C@@H](O)CO`, because the label (and the drawing) were read back off the 3D start geometry, which picks one arrangement for every unspecified centre. Each candidate now carries a flat 2D drawing built from the tautomer before embedding, so an undrawn centre stays undrawn and a drawn one is kept. ORCA still gets the 3D geometry; the energies are unchanged. (A molecule with two or more unspecified centres still has its tautomers compared between arbitrary diastereomers, which can differ in energy -- not addressed here.)
- **The Results panel's entry for an energy-bearing structure set (the ORCA tautomer distribution) now says what it is.** It read "Structures 2" and nothing else: no energies, and none of "not validated" or "incomplete", which were visible only in the dialog. It now shows the relative-energy range, the energy reference, how many candidates were optimized, and whether populations are shown. Its open button, previously labelled "Send to 2D Editor..." although it opens the window with the energies, now reads "View structures and energies...".

### Tautomer Distribution results are now reachable after the fact (branch `orca-wiring-and-nmr-deferred`)

- **The ORCA Tautomer Distribution calculator's result is no longer lost the moment its dialog is closed.** It now records into the same Results panel "Showing:" list the RDKit `enumerate_tautomers` generator's own results already use, survives molecule reselection and project reload, and gets a fixed `set_id`/producer (`orca.tautomer_distribution`) matching its registered calculator id -- a latent mismatch that would have silently filed it under the wrong Properties category the moment it started being recorded.
- **The Quantum Chemistry panel's own "Runs" history gained a matching fix**: selecting a past tautomer-distribution run used to show nothing at all, even though the full result was already retained there. A new "View Tautomer Distribution..." button reopens the exact stored result for the selected run -- never auto-popped, so reselecting an unrelated molecule never interrupts with an unsolicited window.
- The RDKit "Tautomers..." row in Properties now mentions the ORCA-based alternative, and vice versa.

### IR view reachability, and a real Molecule Report bug found while adding it (branch `orca-wiring-and-nmr-deferred`)

- **A full audit of what ORCA can do versus what's reachable from Properties/Results** found one real gap: the vibrational/IR spectrum had no "open it" link the way the NMR spectrum already does. The Molecule Report's spectroscopy section now offers an "Open IR" link, routed to the Quantum Chemistry panel exactly as "Open NMR" already is.
- **While adding it, a real, previously-unknown bug surfaced in the Molecule Report's spectroscopy-fact builder**: it was iterating `context["spectra"]` -- a dict keyed by spectrum type -- directly, which iterates its *keys* rather than the spectrum objects. Every molecule-level spectroscopy fact (NMR included, not just the new IR case) has therefore shown an empty label and "0 predicted shifts" regardless of the real spectrum, silently, since this path was never exercised by a test. Fixed alongside the new IR case, with an explicit regression test for both spectrum types plus an unrecognized-type case that must never be silently routed to NMR.
- Everything else ORCA computes (the seven uniform calc types' scalar descriptors, QM surfaces, LED) was confirmed already correctly wired -- recorded as an audit result, not re-built.

### NMR viewer: a coupled/decoupled display toggle and a first-order pattern tooltip (branch `orca-wiring-and-nmr-deferred`)

- **A "Decoupled" checkbox** on the NMR viewer's toolbar, beside "Smooth rendering" -- a pure display switch collapsing every multiplet to its nominal shift in both sticks and smooth mode, computing nothing new and never touching the stored `coupling_groups`/`multiplicity`.
- **A first-order compound pattern tooltip** ("First-order pattern: qddd"-style) on hover, derived directly from a signal's real `coupling_groups` -- informational only; the Multiplicity column and the underlying `multiplicity` field are unchanged. Uses explicit `QToolTip.showText`/`hideText` rather than the passive `setToolTip()` API, so the tooltip updates immediately when the cursor moves directly between two adjacent signals with no intervening pause over empty space.
- Both were listed as "explicitly deferred" when the NMR splitting-tree fix shipped, pending the `coupling_groups` data they're built from -- both now built on it.

### Tautomer distribution: ORCA-based electronic-energy population estimates (branch `nmr-toolbar-and-tautomers`)

- **A real tautomer distribution/population calculator**, replacing the only thing that existed before: `enumerate_tautomers` silently flagging one tautomer `"(canonical)"` via an RDKit internal heuristic score, with no distribution, no energy, nothing validated. The new "Tautomers..." button on the Quantum Chemistry panel enumerates and deduplicates every distinct tautomer RDKit can reach, embeds each one in 3D with an explicit, recorded seed, and runs a real ORCA geometry optimization on every one of them, sequentially -- one combined result, not one calculation per candidate.
- **This is a gas-phase electronic-energy Boltzmann population *estimate*, not a full equilibrium probability** -- no vibrational, thermal, entropic, or solvent correction, and one optimized minimum per tautomer (no per-tautomer conformer search). A population percentage is only ever shown once checked against real reference data for the exact method/basis/weighting used; until then, each candidate's real relative energy is still shown, just not a population built from it.
- **If any candidate's geometry optimization fails to converge, no percentages are shown for any candidate.** A distribution normalized over only the survivors would be a different, weaker claim than "the distribution" -- the candidates that did succeed still report their real energies, explicitly labelled as relative to the best of the survivors rather than the true minimum, since the failed candidate could have been lower still.
- Built on the existing `chem/boltzmann.py` Boltzmann-weighting function (reused unmodified, not reimplemented) and the existing `QuantumChemistryService` sequential multi-job machinery (`_BoltzmannRun`/`_finish_conformer_job`'s own pattern for "N real ORCA jobs over N candidate structures, one combined result, one `QuantumChemistryRun`"), generalized to tautomer candidates. The result reuses the same `StructureSetResult`/structure-grid view every other generated structure set (tautomers, stereoisomers, resonance forms) already uses.
- Live-verified end to end against a real ORCA install (cyclohexanone's keto/enol tautomers): both candidates optimized and converged, the keto form came back overwhelmingly favoured, as expected. The real scientific validation study (checking computed populations against published reference data at a properly chosen level of theory, the two-gate ranking/quantitative check that decides whether a percentage ever ships) is a separate, substantial piece of work and remains open.

### NMR/IR viewer quality pass: scroll fix, honest multiplets, 1D zoom (branch `nmr-viewer-quality`)

- **Scrolling past a Nucleus/Frequency/Solvent combo box (or a QC panel spin box) on the way down a pop-out no longer silently changes it.**
  A second, different scroll-wheel bug from the one fixed on the branch below: an ordinary unfocused `QComboBox`/`QAbstractSpinBox` accepts a
  wheel event unconditionally in Qt. A new focus-gated `ScrollSafeFilter` lets the event propagate to the parent (so the page scrolls
  normally) unless the control actually has focus.
- **Two real bugs were found and fixed behind what first looked like a UX gap: isopropanol's NMR + Spin-Spin Coupling run showed no
  multiplet splitting at all.** TMS referencing was silently dropping `couplings`/`coupling_error` on every referenced spectrum (a manual
  dataclass reconstruction that never copied them over); separately, coupling extraction wasn't filtering ORCA's full coupling matrix down to
  real structural partners, so a signal's `coupling_hz` could carry chemically-irrelevant values (wrong element, wrong bond distance)
  alongside the real one. Both fixed; the 1D spectrum now states plainly which of three cases is on screen (real coupling, genuinely none
  calculated, or a parser failure) rather than leaving an unsplit "d" to read as a defect.
- **The 1D spectrum can now be zoomed and panned**, matching the 2D correlation plots' own interaction (scroll to zoom around the cursor,
  drag to pan, double-click to reset) via zoom/pan arithmetic extracted into a shared `ui/widgets/plot_zoom.py` that both widgets now use.
  Selecting a signal (a peak click, a table row, or a 3D atom click) also re-centres and zooms on that signal's full multiplet extent by
  default ("Zoom to selection", matching Marvin's own "Zoom Follows Selection" -- an opt-out checkbox, not forced). Both the 1D and 2D plots
  now draw real intermediate numeric ticks at a "nice" spacing instead of only the axis endpoints.
- **The NMR and IR pop-outs are resizable instead of a fixed stack.** Nested `QSplitter`s (NMR: an inner [2D structure | 3D view] pair inside
  an outer [structures | spectrum | table]; IR: the same outer three, with no inner pair since IR has only one structure pane) replace the
  previous plain `QVBoxLayout`/`QHBoxLayout`. The 2D depiction's own large minimum size used to eat most of the default space regardless of
  how the rest of the window resized -- the default split now favours the spectrum instead, with every pane keeping a real minimum so no
  handle can be dragged into an unusably tiny sliver.
- **Every numeric column in the NMR signal table, the IR mode table, and the HSQC/HMBC/COSY and Hybrid tables now sorts by its real value,
  not its printed text** (`SortableItem`, already used elsewhere in the app -- these tables were simply the ones that hadn't adopted it yet).
  A "6H"/"12H" integration or a "9.0"/"18.3" ppm pair now sorts numerically rather than by digit order, and a column mixing real numbers with
  an em dash for "nothing calculated" groups the dashes at one end instead of scattering them by string comparison. Selection survives a sort
  by the row's own logical identity (an atom set, a mode's position in the spectrum, an atom pair) rather than by row position, which a sort
  changes out from under it -- the correlation tables already worked this way by construction; the NMR and IR tables needed the same fix.
  Found and fixed along the way: a freshly created `QHeaderView`'s sort indicator already points at column 0, descending, by Qt's own
  default -- so `setSortingEnabled(True)` after a table's very first population silently pre-sorted it before anyone had clicked anything
  (`docs/gotchas/qt-table-sort-indicator-default.md`).

### NMR multi-group splitting trees, Hz display, spectrum labels (branch `nmr-splitting-tree`)

- **A signal coupling to more than one distinct partner group ("m") now actually draws its real splitting, instead of falling back to one
  unsplit line.** `multiplet_lines()` used to gate rendering entirely on the structural `multiplicity` letter, which maps "m" to "no pattern" by
  construction -- so a signal with real, honest per-partner J values (propylene glycol's methine, coupled to 3 equivalent methyl H's, 2
  diastereotopic CH₂ protons, and the OH) rendered flat even though the table showed the real couplings right next to it. `NMRSignal` gains a
  `coupling_groups` field -- `(partner_count, mean_abs_J_hz)` per real equivalence-group coupling, populated for every signal -- and
  `multiplet_lines()` now cascades across every group into the real first-order product pattern (never inventing a J; only using the real ones
  already present), merging any positions that coincide. Multi-group first-order splitting is rendered from calculated ORCA J values and may
  include symmetry-completed equivalent-partner values when ORCA reports only a subset of an equivalent group -- flagged via
  `coupling_groups_inferred` and a sentence in the existing honest-coupling note, never silently presented as if every member had been directly
  reported. This is a first-order approximation, not a full spin-Hamiltonian simulation -- no roofing, no second-order effects, no magnetic
  nonequivalence. The stored `multiplicity` letter is unchanged ("m" still reads "m", matching Marvin's own choice for genuinely complex cases);
  only what gets drawn changes.
- **The 1D spectrum can show ppm or a Hz frequency offset.** Restricted to a referenced chemical shift -- disabled on a raw-shielding spectrum,
  since isotropic shielding has no reference-frequency relationship to convert through and showing one would look like a fabricated
  experimental number. Axis, ticks, peak labels, the cursor readout, and the signal table's own column all agree and update together; the
  underlying `NMRSignal.shift` is never mutated by the display choice.
- **A live cursor coordinate readout** shows δ/Hz under the mouse while hovering the plot (`setMouseTracking` was missing, so a passive hover
  never fired `mouseMoveEvent` before), tracking the current zoom/pan viewport and clearing outside the actual plot rectangle.
- **Spectrum Labels: None / Chemical shifts / Atom indices**, applied identically to sticks and smooth mode (smooth mode drew no labels at all
  before this). "Atom indices" uses the same one-based display numbering already used throughout the app (Atom Inspector, `report_format.py`),
  not the raw 0-based RDKit index. "None" is the direct fix for two signals close enough to crowd each other's label.

### NMR viewer toolbar: Reset Zoom, Copy Spectrum Image (branch `nmr-toolbar-and-tautomers`)

- **The NMR viewer's loose row of combo boxes and checkboxes is now a `QToolBar`**, carrying every existing control (Nucleus, Frequency,
  Solvent peak, Unit, Labels, Smooth rendering, Relative integral, Zoom to selection) unchanged -- same widgets, same wiring, just a different
  container. Fixed (not movable/floatable), since this toolbar lives inside a docked panel rather than a main window.
- **Reset Zoom** and **Copy Spectrum Image** are two small, previously-missing actions now on that toolbar: Reset Zoom restores the full
  spectrum span (until now only reachable via double-click or wheeling back out); Copy Spectrum Image copies the spectrum plot itself
  (not the structure panes or the table) to the system clipboard as an image.

### Quantum Chemistry panel: run history, chart UX, help, scroll fix (branch `qc-panel-run-history`)

- **A calculation result now survives save/reload, and running a new calc_type no longer discards the last one.** Every ORCA job (NMR,
  IR, Surfaces, Boltzmann-averaged runs counted as one) is recorded as its own durable `QuantumChemistryRun`, kept apart from the generic
  per-calculator revision cache so it is never pruned when the molecule is later edited. A spin-spin coupling parse failure is now its own
  state ("Spin-spin coupling data unavailable") rather than reading identically to "no coupling for this pair."
- **One history picker for the whole panel**, newest first, with delete (project history only -- a reusable wavefunction in the quantum-
  chemistry cache is untouched) and "Compare NMR Shifts..." between two runs, refusing cleanly when their atom numbering cannot be safely
  lined up. Selecting an older run repaints every tab from its own stored geometry, wavefunction and spectra -- it never changes what
  Properties shows as the molecule's current values.
- **The 2D correlation plots (HSQC/HMBC/COSY) can be zoomed and panned** (scroll to zoom around the cursor, drag to pan, double-click to
  reset), and a cross peak can be clicked to select its table row and back, through a stable (atom_a, atom_b) identity rather than nearby
  coordinates. The 1D spectrum has a Sticks/Smooth render toggle (the smooth curve is a Lorentzian convolution whose per-signal area is
  provably proportional to integration) plus an optional cumulative "relative integral" overlay. Each tab now shows a status glyph for the
  active run, "Configure/Calibrate" are collapsed behind a "More" menu, and "Help for this tab" opens documentation specific to whichever
  tab is active (new USER_GUIDE.md sections on raw/TMS/scaled shift referencing, the 2D correlation tabs, and what the Hybrid tab merges).
- **Scrolling over any embedded 3D view (NMR, IR, Surfaces, Alignment, the Calculator Inspector, the main 3D viewer) no longer hijacks a
  scroll meant for the panel it sits in.** A `QWebEngineView` consumes wheel input for its own camera zoom unconditionally -- confirmed with
  a new `OPENCHEM_DRIVE` `wheel_trace` diagnostic that it never reaches a Qt ancestor at all, which no Python-side `wheelEvent` override
  could have fixed. Fixed once, centrally, in `Mol3DViewerBackend`: a wheel over a view that does not have focus scrolls the page instead;
  click into the view first and it zooms, the same two-step gesture every embedded map or 3D view already asks for.
- **A Boltzmann-averaged QC run's descriptors (SCF energy, HOMO/LUMO, dipole, ...) now reach Results too, from the lowest-energy conformer.**
  The "current/latest value" store PropertyPanel reads on reselect/reload above only covered a single (non-averaged) job; a Boltzmann
  sequence discarded every conformer's descriptors once it had used the SCF energy to weight the spectrum. A weighted-average SCF energy is
  also computed (reusing the same population weights `chem/boltzmann.py` uses for the spectrum) but kept in run history only, not yet
  published as a descriptor -- see docs/ROADMAP.md ("What is left, and why each one is left") for the open question that is blocking it.

### NMR: referencing, and what makes it slow (branch `nmr-referencing-and-speed`)

- **A raw NMR result no longer draws as a mirror-image spectrum.** ORCA returns isotropic shielding sigma, and a chemical shift is
  delta = sigma_ref - sigma, so the two run in opposite directions. Until someone pressed Calibrate, the 1D Signals view drew sigma on the
  descending delta axis: aliphatic carbons (high sigma) landed downfield and carbonyls upfield, with a "13C d (ppm)" label. A raw result is now
  drawn ascending, labelled sigma, and its table column says so.
- **The TMS reference now runs by itself.** After an NMR job with no cached reference for that method/basis, the service runs TMS once and
  republishes the same result as delta. The raw result still appears first. A refused or failed reference leaves the raw result, labelled sigma.
- **Recorded, not built: selecting nuclei does not make an NMR run faster.** Measured on Salvinorin A (59 atoms, B3LYP/pcSseg-1, one core,
  ORCA 6.1.1): all nuclei 743 s, 13C only 883 s, 1H only 784 s. The ground-state SCF is 8 to 10 minutes of that and is the same whichever
  nuclei are asked for; the shielding tensors themselves take 4 s. A nuclei control was written and removed for that reason. PBE/pcSseg-1
  took 214 s for 13C (about 4x, accuracy not yet benchmarked).
- **ORCA now uses several cores (Quantum Chemistry panel: "CPU cores").** It ran on one, which is why NMR took 12 minutes. Measured on the
  same Salvinorin A job, all nuclei: 1 core 743 s, 8 cores 97 s, 16 cores 111 s, so the automatic choice (half the logical cores) is capped at
  8; PBE/pcSseg-1 13C on 8 cores took 33 s. Needs Microsoft MPI (`mpiexec`, `winget install Microsoft.msmpi`); without it the box is pinned to 1,
  because a parallel input with no MPI aborts the job rather than running slowly. Benchmarked and NOT offered as a "fast" preset: on DELTA50 13C
  (209 carbons, 47 compounds, scaled against the same 11 standards) PBE/pcSseg-1 has a mean error of 3.33 ppm [95% CI 2.96, 3.72] against
  2.64 [2.28, 2.99] for B3LYP/pcSseg-1. The bar was set before either number existed: within 0.5 ppm. The 0.69 ppm gap misses it, and with
  eight cores B3LYP already takes 97 s where PBE takes 33 s.

### Post-round-14 program: nitramine hotfix, driver ledger, refusal kinds (branches `nitramine-hotfix`, `outcome-model`)

- **Settings > Conformers: an EXPERIMENTAL stop rule, off by default.** "Stop early when the lowest conformers stop changing" ends a search when no new shape would rank among the conformers the run keeps, instead of when no new shape of any energy turns up (higher-energy shapes keep arriving on a flexible molecule, which is why the default rarely stops early there). Measured by replaying 1000-embedding searches of ethylmorphine, phenomorphan and fentanyl on three seeds against the same search run to 1000: it never stopped later than the default, used about a quarter fewer embeddings, and recovered about 18 of the 20 lowest shapes against about 19 (worst run 16 of 20; the single lowest-energy shape was the same in every run). Three molecules is a small sample, hence opt-in. The stop is its own reason in the run's record (`kept_set_steady`, with `stop_rule: kept_set`) and Details says so. Driven through the REAL Settings checkbox on fentanyl in the app: stopped at 600 of 1000 embeddings, 331 distinct, 20 kept, `benchmarks/visual/conformers_early_stop.json`, verdict PASS, setting restored; seven guards were each removed to confirm a test fails.
- **Conformers: a Finish now button, and a readout that says how the search is going.** A conformer search on a flexible molecule can sample for minutes, and the only way out was Cancel, which throws every shape away. **Finish now** (beside Generate Conformers in the 3D viewer, and in a new Finish early column of the Jobs panel) ends the search after the embedding in progress and KEEPS what it found: the shapes so far are de-duplicated, ranked and shown like any run, the run's record says `finished_early`, and Details says so. It is greyed unless a search is running for that molecule, a run with nothing found yet publishes nothing rather than an empty set, and a cancel still outranks it. The readout between the arrows now reads `Sampling shapes 359/1000 - 224 found so far - lowest 20 still changing` (or `unchanged for 150`): "lowest 20" is the number the run keeps, and it says nothing about them until the archive holds that many. **Measured, not assumed:** no stop rule replaces the default, because every rule tried (a quiet batch, no new shape entering the kept set, no gain in the kept energies, sample coverage) sits on one recall-versus-embeddings curve; the one that was never worse than today's is the opt-in experimental setting in the next entry. With that setting off, a search nobody interrupts is unchanged. Driven with `benchmarks/visual/conformers_finish_now.json` on fentanyl (388 of 1000 embeddings, 240 distinct, 20 kept, verdict PASS), and each of six guards was removed to confirm a test fails.
- **A click on a bond can cycle its order (single, double, triple), if you turn it on.** Settings > Drawing, OFF by default, because in the Select tool a click on a bond selects it and cycling takes that away. It reports the same thing the number keys do, so it is one undo entry with the same refusals (aromatic, query, wedge, a broken valence); it acts only in a Select tool, on a click that did not move, and never when an atom is under the pointer or another tool is active. `benchmarks/visual/bond_click_cycle.json` drives it through the real Settings checkbox; the two guards were each removed to confirm they fail it.
- **Settings > Conformers: how many starting structures Automatic tries.** The ceiling was fixed at 1000, about a minute and a half on a flexible drug-like molecule with nothing else running. It is now a setting (10 to 5000, default 1000, so nothing changes until it is lowered). Measured on such a molecule, the conformers within 3 kcal/mol of the best that a search finds are 71% found at 300, 93% at 500 and all at 750, so 500 is roughly half the time for most of them; the setting's tooltip says so. The search does not stop sooner by itself on these molecules: it counts any shape not yet seen, and a flexible molecule keeps producing them.
- **Conformer progress no longer says "933/1000 conformers".** The number was embeddings TRIED against the search's ceiling, and a run that read 933 of 1000 and returned 30 looked like a defect. It now reads `Sampling shapes 933/1000` while the search runs. The search itself is unchanged; see the pull request for what was measured about when it stops.
- **Right-click a panel in the rail to open it beside what is showing, or to lock it open.** A left click still replaces the panel on screen. What was missing was a way to say otherwise: a panel dropped beside another, or in another area, was locked by that drop and then stayed on screen through every later click with nothing saying why, and a click on a locked panel hides nothing. The rail now shows a lock on those panels and its menu has Open beside what is showing, Lock open / Unlock, and Pin to top. Released, a panel stays released until it is moved again.
- **A nitramine crashed the structural-alert pass and took every alert with it.** `fg:hydrazine` matched the N-N bond of `N-[N+](=O)[O-]`, so
  `detect_features` raised `UndeclaredChargeState` and dropped all features for the molecule; the alert pass logged and recorded nothing, so no test
  saw it. A nitramine N-N is no longer a hydrazine, and the same nitro exclusion is applied to the one shared basic-amine SMARTS (which had counted a
  ring N bonded to a nitro N as a base and sent solubility off to predict a pKa that does not exist). Recorded, not fixed: nitroguanidine's NH2 is
  still counted as basic.
- **A driven run now ends in a verdict.** `OPENCHEM_DRIVE` collects every WARNING and traceback the app logs (de-duplicated by logger, exception,
  origin and message), asserts positive expectations (`expect_results`) as well as the absence of errors (`expect_clean`), writes
  `<script>.report.json` and exits non-zero on failure. Each scripted run writes its own `drive-<pid>.log`, because two processes rotating one log
  file is a `PermissionError` on Windows.
- **"Did not produce an answer" is now three different things.** A refusal has a KIND (`domain/refusal_kinds.py`): *limit* (the method does not
  cover the molecule), *needs input* (the method covers it and wants a number only you can give) or *needs setup* (this machine lacks something).
  Two new launcher states, `△ Needs input` and `△ Needs setup`, join the six. Kamlet-Jacobs Detonation, which read "Not applicable" for a method
  that works, now says which inputs it needs and in what units, and names both at once; a compound the method cannot use at all (nitroglycerin is
  over-oxidised) is reported as a limit *before* asking for inputs that could not help. A refusal whose code nobody classified is a fault, not a
  quiet limit.
- **A pKa predictor that ran and returned nothing is "no prediction", not "failed".** `PKaStatus.NO_PREDICTION` separates a working predictor with
  no answer for a structure (a limit of the model) from one that crashed (a fault) and from none configured (needs setup). Solubility now says
  which, and the pH-dependent curves refuse instead of drawing a one-species "curve" from an empty list.
- **A pattern defect now costs one instance, not every feature of the molecule.** The application's feature detection is tolerant: an instance it cannot
  evaluate is skipped, logged once per structure (not once per edit) and recorded as a `Completeness` on Fragment Counts and Functional Groups, so a
  partial "nothing found" is never read as a complete one; the Results reader says so above the facts. The vocabulary's own tests and the census
  keep the strict detector, so a defect stays loud where it can be fixed. The reader's status line now leads a refusal with its kind
  (“Needs input”, “Needs setup”, “Not applicable”) instead of one sentence for all three.
- **Calculators that refuse most of what people draw are no longer offered as everyday equipment.** Every calculator can now declare its support level
  (`domain/calculator_support.py`): a stage (experimental, limited or stable -- the maturity of this application's implementation, never a verdict on the published
  method) and, separately, whether it is offered by default. Thermophysical Properties (Joback) is *limited* and hidden -- measured on 2026-09-24, it refuses
  RDX, HMX and 1,3-dinitro-1,3-diazetidine and runs TNT and PETN -- and Detonation is *stable* and hidden as a specialist calculator. Properties says how many are
  hidden and opens **Settings > Calculators**, which names each with the reason, what it covers and a Learn more button to its own reference section; one setting
  offers them all and a tick offers one, and neither runs anything. The calculator reference states each calculator's level. Sixty-six older calculators are
  listed as not yet classified, and a guard lets that list only shrink.
- **Every calculator has a way to its own help.** Right-click a calculator's button and choose *About this calculator*, press F1 with its button or tick box focused, or use the
  *About this calculator* button in the dialog every calculator opens -- each lands on that calculator's own section of the reference, where the tooltip used to point at the whole
  Properties chapter. A limited or specialist calculator also states its support level and reason in its dialog, where a person who enabled it is about to run it. A new guide,
  *Comparing partial charge models*, says what each of the five charge models needs and refuses; it describes and ranks nothing, and a guard holds it to that.
- **The calculator census.** `tools/calculator_census.py` runs every registered calculator, and the always-on set, over 29 structures chosen for shape (nitramines, energetic materials,
  hydrazines, ring tertiary amines, salts, metals, a peptide, a large molecule) through the application's own service, recording what each returned (ready, limit, needs input,
  needs setup, fault) AND what the application logged while it ran. A guard fails on a fault, an error logged, a calculator that never answered, a refusal code nobody classified, or
  any cell that differs from the committed baseline. Its first run found the experimental NMR database's "not built" refusal and a 3D descriptor's "needs a conformer" reading as
  faults, and eleven calculator-specific refusal codes that read as limits only by a legacy flag; all are classified now. It also reports which calculators refuse a quarter or
  more of the panel as a limit -- a *proposal* for the limited classification, never an assignment.
- **A failure that repeats no longer fills the log.** A traceback that repeats within 30 seconds is printed once, in the file, the console and the in-app Console alike, and
  the log says it repeated: one line at the first repeat, and a count when the failure next appears. "The same failure" is defined once
  (`failure_log.py`: where it was raised, not what it said) and shared with the driven-run ledger, so a verdict and a log cannot disagree about how many
  problems there were.
- **A slow calculation can no longer read as current for a structure it was not computed on.** The calculation and the always-on descriptors were handed the live
  molecule on a worker thread, read it at several different moments while the editor went on changing it, and stamped the result with the structure version
  *when the result came back* -- so a value computed for structure A that finished after an edit to B read as current for B (AqSolDB takes about five
  minutes; a pause-then-refresh recompute makes the window routine). The molecule, its conformers and the structure version are now captured on the calling
  thread (`domain/input_snapshot.py`) and the worker reads nothing else.
- **Every feature pattern was swept over 2,187 structures, and eight defects came out.** `tests/test_feature_vocabulary_sweep.py` runs each structural-feature pattern over the census
  and naming corpora with the strict detector; eight patterns misread a sulfonamide anion, protonated acylguanidines, oximes and acylhydrazones, an oxazolinium and an N-hydroxy nitro
  group. They are recorded in `tests/fixtures/structural_features/known_vocabulary_defects.toml`, which may only shrink; fixing them needs a vocabulary decision and is not done here.
- **What drawing costs is now measured, before anything is changed.** The driven `edit_burst` step records each structural edit's latency, the longest the event loop was blocked and how
  many recalculations a burst caused (`benchmarks/visual/edit_burst_baseline.json`). It is a baseline, not a test: it measures the Python side only, not Ketcher's own JavaScript.
- **Several Calculator Inspectors can stand side by side.** The inspector was a modal window, so comparing two charge methods meant closing the first and remembering it. Each result now
  opens its own window (modeless, titled with the calculator and its method), the same result raises the window already open instead of opening a duplicate, and the cap the Batch panel
  already applies (a Chromium process each) holds here too. `expect_inspectors` in the driver counts them.
- **A "Needs input" or "Needs setup" chip now takes you to where it is fixed.** Those two states say what you have to do, so pressing them no longer just opens a reader that can only
  describe it: "Needs input" opens the calculator's settings with the missing values named above the form and the cursor on the first (nothing runs until you confirm), and "Needs setup"
  opens Settings > External Tools on the tab that sets it up. The chip's tooltip says which before you press. A calculator can now declare a parameter `required` (it has no usable default);
  "Run selected", which uses defaults, skips such a calculator and says what it wants instead of running it to a refusal you did not ask for. Detonation's two inputs, alignment's
  reference and the Lewis adduct's partner are declared this way, and the last two now name the empty field in their refusal.
- **Drawing no longer recomputes everything on every edit.** A canvas edit used to fan out to every descriptor provider, a substance perception and a structure check, so drawing
  lagged (a median 1.1 s per edit on aspirin, the event loop blocked for up to 4 s -- `benchmarks/visual/README.md`). A canvas edit is now `MoleculeChanged(during_edit=True)`: what only has
  to *know* acts at once (the version bumps, so results read Stale immediately), and what *computes* waits for `RecalculationDue`, published by `RecalcScheduler` under a policy chosen in
  Settings > Recalculation: after I pause (default, 800 ms, every edit restarts it), while I draw, or only when I ask (Tools > Recalculate Now, F5). Undo, redo, import and selecting another
  molecule still recompute at once. Two latent races the pause would have widened are closed with it: an alert or descriptor computed for structure A read as current for B whenever an edit
  landed mid-run (they were stamped with arrival time, not dispatch time), and an older run finishing late could replace a newer result. Measured on the maintainer's machine over twelve
  edits of aspirin, a new structure each: edit latency 1,121 ms -> 18 ms (median), the longest the event loop was blocked 3,993 ms -> 93 ms, full recomputations 12 -> 1. A profile of the
  first "after" run found two more costs, both fixed: the Results reader was rebuilt once per descriptor *event* (now once per turn of the event loop), and the Atom Inspector's atom table
  was rebuilt with IUPAC locants on every edit (now at the pause). Both tables are in `benchmarks/visual/README.md`; Ketcher's own JavaScript is not measured.
- **Calculators run from another panel have a real row in Properties.** Vina docking, the seven ORCA jobs and Hardness/Softness were skipped by the launcher and represented by one italic
  sentence naming a panel, so a person looking for an ab initio NMR found a hint and nothing to press. Each now has a row under **Docking**, **Quantum Chemistry** or **Lewis Acid/Base**
  ("NMR (raw shielding) > Quantum Chemistry panel"): a button with no tick box and no status chip, which shows that panel with the calculation already chosen and runs nothing.
  `ServiceExecution` gains a `panel_id`, and a guard holds every one to a panel that exists. The status line beside "Run selected" now says what the tick boxes are for ("Tick boxes to run
  several at once", then "N ticked - runs with default settings") until a real status replaces it. The Properties panel has 22 sections, not 20.
- **Two charge methods can finally be compared.** The result store keeps one result per calculator per structure, so running a second model replaced the first and the two could never be
  on screen together -- the reason comparing methods was hard. The Properties panel now keeps a short pool of the per-atom results a molecule has produced (one per method and parameters),
  and a Calculator Inspector's new **Compare with...** menu offers the others that can honestly be set beside it and opens one table: a row per atom, a column per method, a shaded
  **Spread** and each later method's difference from the first. `domain/compare.py` REFUSES what would publish a wrong difference -- a different molecule, an edit between the runs, a
  drawing beside a conformer, one protonation state beside another, different units or atoms, or the same calculation twice -- and the menu never offers a comparison it would refuse.
  Not saved with the project. Driven on ethanol: EEM against QEq disagree most at the oxygen (0.09 e).
- **A note on what Ketcher does when drawing** (`docs/KETCHER_SPIKE.md`), **corrected the same day.** It first said hover-aware hotkeys were native (hover a bond and press 1/2/3) and that a hover
  could not be produced from automation. Both were wrong. A hover CAN be produced: Ketcher's own tools set it with `editor.hover(editor.findItem(event, null), null, event)`, which needs only a
  client position, and the key has to be dispatched inside the editor's DOM. With that, hovering an atom and pressing `n` replaces it and `/` over a bond opens its properties dialog, **but a
  number over a hovered bond changes nothing** -- the bundle's hotkey table has no bond handler. So bond hover+number and click-to-cycle are new work, recorded as an OPEN item in
  `docs/ARCHITECTURE.md`; `benchmarks/visual/ketcher_hover_keys.json` asserts all three facts, so an editor upgrade that makes a number over a bond native fails it. The `ketcher_hover` step
  now sets the hover this way and asserts the result, instead of sending a real mouse move that never registered.
- **A nitro group on a ring nitrogen is named as a nitro prefix** (naming round 15, D-163). 1,3-Dinitro-1,3-diazetidine, the molecule that started the program, was shown as
  `oxido{3-[oxido(oxo)azaniumyl]-1,3-diazetidin-1-yl}(oxo)azanium`; RDX, HMX, TNAZ, N-nitropyrrolidine and the N-nitro azoles were named the same way. The engine's `nitro`
  pattern needed a carbon neighbour, so the nitro nitrogen was offered as a one-atom azanium parent that outranked the ring. They are now `1,3-dinitro-1,3-diazetidine`,
  `1,3,5-trinitro-1,3,5-triazinane`, `1,3,5,7-tetranitro-1,3,5,7-tetraazocane`, `1,3,3-trinitroazetidine`, `1-nitropyrrolidine`, `1-nitro-1H-imidazole`. Acyclic nitramines
  and N-nitroso compounds are not covered and are recorded as open. None of the existing corpora contained a nitramine, so the standing measures (census, ref-compare, frozen
  populations) all report no change and are not evidence for the fix; the nine new `D-163` rows, verified by OPSIN read-back, are.
- **The chalcogen analogue thiohydrazide, `R-C(=S)-NH-NH2`** (naming round 23, D-179). P-66.3.4 (pdf p. 672), verbatim: "Chalcogen analogues of hydrazides are named substitutively using suffixes formed by functional replacement, i.e., 'thiohydrazide', 'carbothiohydrazide'"; printed `propanethiohydrazide (PIN)` and `benzenecarbothiohydrazide (PIN)`. `fg:hydrazide`'s SMARTS matched only a carbonyl oxygen, so a thiohydrazide was never recognized as the hydrazide class at all (`CC(=S)NN` was `(1-thioxoethyl)hydrazine`). One new `thiohydrazide` FG entry mirrors `hydrazide` exactly, but three engine.py sites keyed on the literal string `"hydrazide"` also needed the new type name: N-substituent carving (Pass 2.5a), N/N' role primes, and the anchor-in-parent guard (without the last, a thiohydrazide inside a longer acid chain briefly double-counted its own carbon -- a WRONG STRUCTURE caught before it shipped). **Measured:** census and the frozen sets 0 changes (the family is rare); ref-compare 2 changes, both the book's own printed examples, 0 violations. Nine guards were each removed in turn and a row failed for eight; one (a double-counting preprocessing step, verified dead behind the anchor guard for every shape tried) is kept only so the function is right on its own, the same reasoning round 19 kept a guard for.
- **Hydrazones of a carbon-acid hydrazide are named on the hydrazide, with an N'-ylidene** (naming round 22, D-171). P-66.3.3 prints the same pattern round 19 built for the nitric/nitrous hydrazide, "N'-hexylidenenitrous hydrazide (PIN)": `CC(=O)NN=CCCCCC` was `1-acetyl-2-hexylidenehydrazine` and is `N'-hexylideneacetohydrazide`. The `fg:hydrazide` SMARTS (`data/functional_groups.json`) required both nitrogens at `NX3` (three connections), which a hydrazone's terminal `=N-` (`NX2`, double-bonded to carbon) failed; the fix is one recursive clause on the terminal nitrogen, `$([NX2;!R]=[#6])`, restricted to a carbon partner so a genuine azo/triazene nitrogen (`-NH-N=N-R`, a different class) is not mistaken for a hydrazone. Everything downstream -- the N/N' prime locants, the ylidene substituent itself -- was already general machinery (Pass 2.5a's "PCG N-substituents"), untouched. **Measured:** census 0 class changes, 40 name changes (39 exact -> exact, 1 same_connectivity -> same_connectivity, all this pattern -- the family is common in drug-like corpora); ref-compare 1 change (a heldout_v5 row, reads back both ways), 0 violations against a manifest; the frozen sets moved on 1 of 1126 and 1 of 40 rows and were scored once in aggregate, every population IDENTICAL to round 21 (`bluebook_frozen` exact 511). Two guards were each removed in turn and a control row failed.
- **Also found, not fixed:** plain thiohydrazides (`CC(=S)NN` is `(1-thioxoethyl)hydrazine`, not `acetothiohydrazide`) are a separate, pre-existing defect -- the `fg:hydrazide` SMARTS matches only `(=O)`, with no chalcogen-generic path the way carboxamide/carbothioamide share one -- recorded in `KNOWN_LIMITATIONS.md` rather than folded into this round.
- **The retained prefixes `benzyl`, `benzylidene`, `benzylidyne` are unenclosed and unsubstituted-only** (naming round 21, D-173). P-29.6.1 (pdf p. 312): "benzyl, benzylidene, benzylidyne are retained preferred prefixes"; printed "2-benzylpyridine (PIN)". `benzyl` (bond order 1) was already right; this round adds `benzylidene`/`benzylidyne` (bond orders 2/3) and reaches two hand-built compound prefixes that bypass the usual spelling substitution entirely, so even plain `benzyl` needed a second fix there. A substituted one (ring or alpha) stays systematic, per the book's own `carboxy(4-carboxyphenyl)methylidene` example. **Measured:** census 0 class changes, 10 name changes (all this family, exact both times); ref-compare 2 changes (one tuning, one the r8 `benzonitrilium` reference row), both read back, 0 violations against a manifest; the frozen set moved on 5 of 1126 rows and was scored once in aggregate: `bluebook_frozen` exact rose 510 -> 511 (one row moved equivalent -> exact), every other bucket unchanged. Ten guards were each removed in turn and a row failed.
- **Amides of the mononuclear halogen oxoacids, `R2N-X` and its `=O` homologues** (naming round 21, D-178). P-62.4 (pdf p. 528): "compounds such as `R-NH-Cl`, `R-NH-NO`, and `R-NH-NO2` are now named as derivatives of amides" -- the same reclassification round 17 built for nitro/nitroso, extended to a halogen. `CCNCl` was `(chloroamino)ethane` and is `ethylhypochlorous amide` (the book's own printed example); the fluorine, bromine and iodine analogues follow by the same rule. Iodine alone climbs the oxidation ladder to `iodous amide` and `iodic amide` (`CNI(=O)=O` had **no name at all** before -- a NAMING ERROR, not merely a non-PIN one); the book's own bromous-amide example (`R-NH-Br=O`) is **not reachable through this engine**, because RDKit's own valence table refuses a neutral tri- or pentavalent chlorine or bromine outright, so that molecule cannot even be constructed here. **Measured:** census and ref-compare 0 changes (no N-halogen structure in either); ten guards were each removed in turn and a row failed.
- **Investigated, not fixed** (`KNOWN_LIMITATIONS.md`): hydrazones of carbon-acid hydrazides (P-66.3.3 names the hydrazide; the FG-detection SMARTS that would need extending is broad enough that a self-contained fix could not be found this round), the azine/triazane/ring-N2 imino cases, the book's own inconsistent `hydrazin-1-yl` locant, a cyano group on cyanamide's own nitrogen competing with a nitro group (P-66.1.6.2's cyanamide is a preselected name of the same class as nitramide, and no printed example resolves the tie), and ethylenedinitramine (a multiplicative parent this route does not build) -- for which a candidate PIN, `ethane-1,2-diylbis(nitramide)`, is now recorded and OPSIN-verified, though not implemented.
- **`=N-NH-R` is `hydrazinylidene`, not `(R-aminoimino)`** (naming round 20, D-170). The Blue Book prints `3-amino-3-hydrazinylidenepropanoic acid (PIN)` (P-66.4.1.2, pdf p. 682) and `nitrosohydrazinylidene (preselected prefix)` (p. 717); the engine read the group as an imino group on an amino group, which OPSIN parses back correctly and which is not the name. `OC(=O)CC(N)=NN` was `3-amino-3-(aminoimino)propanoic acid` and is `3-amino-3-hydrazinylidenepropanoic acid`; `OC(=O)CC(C)=NNC` was `3-(methylaminoimino)butanoic acid` and is `3-(2-methylhydrazinylidene)butanoic acid`; an acyl hydrazone was `3-acetamidoiminobutanoic acid` and is `3-(2-acetylhydrazinylidene)butanoic acid`; round 18's stopgap `(nitramidoimino)acetic acid` is `(nitrohydrazinylidene)acetic acid`. N2's substituents are cited at 2, a lone nitro or nitroso group is unlocanted as the book prints it, and the bare group is unenclosed. An azine, a triazane and a ring nitrogen on N2 keep the imino form. **Measured:** census 2000 rows, 0 changed class and 19 changed names (all this prefix, all exact both times); ref-compare 1712 structures, the same 19 (all in the tuning population, all read back, listed in a manifest, 0 violations); the blind frozen set moved on 14 of 1126 rows and was scored once in aggregate, IDENTICAL to round 19 (`bluebook_frozen` exact 510); the tuning population gained three exact names. Each guard was removed in turn to confirm a row fails (one, the ring test, is an equivalent mutant: a ring N2 is already declined by the substituent walk). Queued, not fixed: hydrazones of carbon acid hydrazides (the census's acyl hydrazones are named on the other parent, an aldehyde or a ring, where the book names the hydrazide).
- **Nitric and nitrous hydrazides are named as such** (naming round 19, D-169). The Blue Book (P-67.1.2.6.3, pdf p. 708) makes them preselected parents, printing `N'-hexylidenenitrous hydrazide (PIN)`. `O2N-NH-NH2` was `nitrohydrazine` and is `nitric hydrazide`; `ON-NH-NH2` was `1-amino-2-oxohydrazine` and is `nitrous hydrazide`; `CNN[N+](=O)[O-]` was `1-methyl-2-nitrohydrazine` and is `N'-methylnitric hydrazide` (N is the nitrogen that bears the nitro or nitroso group, N' the terminal one); a hydrazone was a hydrazine with an ylidene and is `N'-(propan-2-ylidene)nitric hydrazide`; and a hydrazide outranks an alcohol, so `OCCNN[N+](=O)[O-]` is `N'-(2-hydroxyethyl)nitric hydrazide` and not an ethanol. A carbon hydrazide, amide, acid or ester elsewhere, an amidine, guanidine or hydrazonoyl carbon next to the nitrogen, a triazane and a ring nitrogen keep their parents. **Measured:** census 2000 rows, 0 changed class and 1 changed name (a nitrous hydrazide, exact both times); ref-compare 1712 structures, 0 changed; the blind frozen set moved on 1 of 1126 rows and was scored once in aggregate, IDENTICAL to round 18 (`bluebook_frozen` exact 510). A first version named nitroaminoguanidine as a nitric hydrazide, wrong because a guanidine outranks it; a control row caught it and a guard now stops it, and each guard was removed in turn to confirm a row fails. Queued, not fixed: the SUBSTITUENT names of a hydrazone (D-170: `3-amino-3-hydrazinylidenepropanoic acid` is printed, `3-amino-3-(aminoimino)propanoic acid` is written).
- **The `-NH-NO2` prefix is `nitramido` and `-NH-NO` is `(nitrosoamino)`** (naming round 18, D-168). Where a nitramide is not the parent, `OC(=O)c1ccc(N[N+](=O)[O-])cc1` was `4-(nitroamino)benzoic acid` and is `4-nitramidobenzoic acid`, the book's preselected prefix (P-67.1.4.3.2, pdf p. 717: "the substituent group derived from this amide by the loss of one hydrogen atom is called 'nitramido'"); `OC(=O)c1ccc(NN=O)cc1` was `4-nitrosoaminobenzoic acid` and is `4-(nitrosoamino)benzoic acid`, because `nitrosoamino` sat in the list of prefixes that need no enclosing marks though it is a substituted amino group (two of them were `3,5-dinitrosoaminobenzoic acid`, now `3,5-bis(nitrosoamino)benzoic acid`). A round-17 guard was also too loose: a hydrazone of nitramide (`C=N-NH-NO2`) was named as a nitramide with an ylideneamino prefix, and now keeps its hydrazine name until the hydrazide route (D-169) exists. **Measured:** census 2000 rows, 0 changed; ref-compare 1712 structures, 0 changed (no visible population contains either prefix); the blind frozen set moved and was scored once in aggregate, IDENTICAL to round 17 (`bluebook_frozen` exact 510, equivalent 535), so some frozen names changed and no outcome class did. Each of the five changes was removed in turn and a table row failed. Queued, not fixed: the nitric and nitrous hydrazides (D-169).
- **Nitramines and nitrosamines are named as NITRAMIDES and NITROUS AMIDES, the book's PINs** (naming round 17, D-166, D-167). Round 16 named `CN(C)[N+](=O)[O-]` `N-methyl-N-nitromethanamine` and NDMA `N-methyl-N-nitrosomethanamine`; the Blue Book (P-67.1.2.6.3, pdf p. 708) says the preferred names are based on nitric and nitrous AMIDE "in accordance with the seniority order of classes rather than as nitro and nitroso amines", and prints `(chloromethyl)(methyl)nitramide (PIN)` beside the amine form. They are now `dimethylnitramide` and `dimethylnitrous amide`; `H2N-NO2` is `nitramide` (it had no name at all, D-166); an N-nitro or N-nitroso carbamate is `ethyl nitrocarbamate` / `ethyl methyl(nitroso)carbamate` (D-167, was a hydrazine name because the carbamate split took the nitro nitrogen for a carbazate's). A carboxamide, urea, guanidine, carbamate, sulfonamide, acid or ester elsewhere outranks the amide of a mineral acid, so those keep the parent round 16 gave them; a ring nitrogen, a second nitramide group (ethylenedinitramine) and a hydrazine are left as they were. **Measured:** census 2000 rows, 0 changed; ref-compare 1712 structures, 3 names changed, all tuning and each now EQUAL to the name the book prints (`methyl(nitro)nitramide`, `(chloromethyl)(methyl)nitramide`, `isocyanatonitramide`); the blind frozen set moved on 5 of 1126 rows, scored once in aggregate: `bluebook_frozen` exact 506 -> 510, equivalent 539 -> 535, nothing else moved, `heldout_v6` identical. One census row moved on the first attempt (a nitroguanidine hydrazone named as a nitramide, a wrong parent) and a guard now stops it. Found and NOT fixed, queued as D-168: the `-NH-NO2` prefix is `nitramido` in the book and `(nitroamino)` here, and `-NH-NO` lacks its parentheses (`4-nitrosoaminobenzoic acid`). The vendored suite passes (5404), and the fork port follows.
- **Nitramines, nitroguanidine, nitrourea and nitrosamines are named with a nitro or nitroso prefix** (naming round 16, D-164, D-165). Round 15 fixed the ring cases; the acyclic ones
  were `(dimethylamino)(oxido)(oxo)azanium`, `imino{[oxido(oxo)azaniumyl]amino}methanamine` (nitroguanidine) and `1,1-dimethyl-2-oxohydrazine` (NDMA), all of which read back.
  They are now `N-methyl-N-nitromethanamine`, `N-nitroguanidine`, `N-nitrourea`, `N-methyl-N-nitrosomethanamine`, `N-methyl-N-nitroacetamide`. Nitramide itself and N-nitro carbamates
  are recorded as open. One census row moved and every other standing measure reports no change, so they are not evidence for the fix; the 18 new rows are.
- **Pointing at a bond and pressing 1, 2 or 3 sets its order.** Ketcher does nothing with those keys over a bond, so the page reports the hovered bond and the key and the
  application makes the change itself (`ChemistryEngine.edit_bond`, pushed as an `EditStructureCommand`), the way the atom menu's changes are made: one undo step, recalculated
  like any deliberate edit, every other bond and every coordinate untouched (the molfile is edited as drawn rather than sanitised, which would have rewritten a whole kekulé
  ring). Aromatic, query and wedge/hash/either bonds, and a change that would break a valence, are refused with the reason in the status bar; the order a bond already has is
  not an undo entry. Pointing at an atom is untouched. **Settings > Drawing** turns it off. Driven in the running app end to end (`benchmarks/visual/bond_order_keys.json`).
  The Ketcher bundle was rebuilt for this (the main file differs by the new interceptor and two chunk names). **Click-to-cycle is not built:** a click on a bond selects it.
- **The gate retries a crashed chunk five times, not three.** The Windows disposal crash in `test_result_presentation` hits that chunk about 30% of the time on master as well (measured 3/10 there,
  2/10 on this branch), so three in a row -- what one gate saw -- is a few percent of gates; five is a fraction of a percent. Only exit 139 is retried; any other non-zero exit is still a result.
- **Menu shortcuts can be changed: Settings > Keyboard.** Every command in the menus (and Search facts and the Command Palette) is listed with the shortcut it holds; click a box, press
  a combination, and it applies at once, survives a restart, and can be cleared or reset per command or all at once. A combination another command holds is refused and names that command
  rather than being taken from it, and one without Ctrl, Alt or Meta (unless a function key) is refused because the drawing canvas owns the bare letters and digits -- these are the
  window's shortcuts, not the editor's. A stored choice that collides with a key a later release gives another command yields to the shipped default instead of leaving both dead (Qt
  runs neither of two actions on one key). Commands are named by the key their menu contract already used, and a key several actions share (every panel's View entry) by title, in a way
  that does not depend on menu order. Driven in the running app, including the real key press (`benchmarks/visual/keyboard_shortcuts.json`).
- **The atom right-click menu changes the atom.** Ketcher's own menu had these and ours did not, so replacing it took them away: **Change *X* to** C, N, O, S, P, F, Cl, Br, I or H, **Add
  positive / negative charge**, and **Delete this atom**. Each is an edit of the structure by the chemistry engine pushed as one undoable command (`ChemistryEngine.edit_atom`), so it
  recomputes like any deliberate change, recomputes the hydrogens the new atom needs (an oxygen turned nitrogen gains its hydrogens: `CCO` -> `CCN`), and a change that would not be a
  molecule is refused with the reason instead of drawn. A first attempt through Ketcher's own atom and charge tools armed the tool and changed nothing, because its tools read pointer
  state a synthetic event does not carry; driven through the real menu, all three now work (`benchmarks/visual/atom_menu_changes.json`).
- **Right-clicking an atom and choosing Edit... now works.** It opened nothing and logged nothing: the menu dispatched Ketcher's `elementEdit` event itself with a bare object, where
  Ketcher's own callers pass an array of atom objects from the selection and hand the returned promise to an internal function that writes the answer back -- so even a dialog that opened
  could not have applied its result. It now selects the atom and double-clicks it, which runs Ketcher's own path. Driven on the real page: the Atom Properties dialog is up, Cancel leaves the
  structure alone, and Apply of a +1 charge turns ethanol into `CC[OH2+]` as one undo entry that Undo reverses.
- **The Results "Showing" list is readable.** Its popup took the width of the narrow docked box and elided entries such as "Thermophysical Properties (Joback)"; it is now as wide as its
  longest entry, and each entry carries its full text as a tooltip.

### Naming round 14 (branch `naming-round-14`)

- **Census 95.70% -> 97.95% exact** (1914 -> 1959 of 2000 structures; no row left `exact`), candidate wrong structures 0.90% -> 0.60%, embedded errors and
  refusals 1.15% -> 0.45%. The round-13 scan had never been saved and was reconstructed row by row against the r12 baseline first.
- **A sulfonamide on a ring nitrogen** (`4-(piperidine-1-sulfonyl)benzoic acid`): an acid lost its suffix and an ester was named as an ester of the
  piperidine, a different structure. **A sulfamoyl with two different N-substituents** reads `N-cyclohexyl-N-methylsulfamoyl`, not the unparsable
  `N,N-cyclohexylmethylsulfamoyl`.
- **Ring cations that had no name** (four separate roots): fused cations that are not retained rings, a cation drawn on the bridgehead nitrogen,
  a quaternary bridgehead cation with a substituent (and the quinolizidine nitrogen's locant, `4a` -> 5), and a cation inside an acyl prefix that
  lost its charge. Tricyclic cations are deliberately not covered.
- **Stereo no longer dropped** on a retained ring substituent (`[(2R)-oxolan-2-yl]methanol`, 18 census structures) or on a spiro parent at a plain
  locant. **Tropone, tropolone and hinokitiol** are named as the trienones, not as saturated cycloheptanones.
- **Ring locants:** heptacene to nonacene and the phenes now have tables derived from the fusion numbering rules; octahydroindole, the biotin skeleton
  and triazolobenzothiazole have complete tables. The four helicenes are still unnumbered.
- **Recorded, not fixed:** an N-hydroxy-N-alkyl amide inside an ester loses its N-substituent (D-162), and 41 census rows in about ten clusters, each with
  its reason. See `src/openchem/vendor/KNOWN_LIMITATIONS.md`, "Open after naming round 14".

### Naming round 13 (branch `naming-round-13`)

- **A wrong ring locant on a heterocyclic substituent, fixed (27 of the 2000 census structures, 1.35%).** `N-(5-methyl-1,3,4-thiadiazol-3-yl)acetamide`
  is now `...-2-yl...` (a monocyclic ring is numbered with its senior heteroatom at 1; a lower combined heteroatom set had outranked it), a
  benzodioxine benzo carbon is `-6-yl`/`-5-yl` and no longer `-2-yl`, azepane's carbons are no longer `azepan-1-yl`, and 1,2,3-oxadiazole is no
  longer named "1,2,5-oxadiazole" (a data row was keyed on the wrong ring; real furazan is now the systematic `1,2,5-oxadiazole`, as the Blue Book
  gives it). The application already withheld every one of these names; they are now shown.
- **A demoted ketone no longer claims its aryl carbon, fixed (13 census structures embedded an error, and a silent half no read-back can see).**
  `4-(2-oxo-2-phenylethoxy)benzoic acid` is now named instead of failing an ownership check, and `4-oxo-4-phenylbutanoic acid` is no longer
  named `3-carboxy-1-phenylpropan-1-one` (nor its amide `4-amino-4-oxo-1-phenylbutan-1-one`).
- **Measured, then fixed:** the census went from 93.45% to 95.70% of structures whose name reads back exactly, candidate wrong structures from
  2.40% to 0.90%, and embedded errors and refusals from 1.90% to 1.15%. A new ring-locant sweep (`tools/naming_ring_locant_sweep.py`) tested all
  371 curated rings at every attachable position: 295 table-backed rings were clean (0 wrong in 5,681 cases), which located the defects in the
  numbering code and data and not in the locant tables.
- **A correction to round 12's documentation:** the application does not show an embedded engine error as an unverified name; it withholds it,
  and it withholds a name whose read-back is a different structure. Three tests pin each gate on real engine output.
- **Recorded, not fixed:** an ester of an acid that also carries a ring-nitrogen sulfonamide is named as an ester of the piperidine (2 census
  rows, D-151); 11 all-carbon fused rings (acenes, phenes, helicenes) are named with a bare `-yl`; and the ring-cation family is now the largest
  remaining cluster (14 rows, 0.70%). See `src/openchem/vendor/KNOWN_LIMITATIONS.md`, "Open after naming round 13".

### Naming census scan (branch `naming-census-scan`, before round 13)

- **`tools/naming_census_scan.py` names every row of the 2000-structure census sample and reads each name back through
  OPSIN**, classifying each row (exact, same connectivity, a wrong molecule of different or same formula, unparsable, an
  embedded naming error, a refusal) and clustering the embedded-error messages. Run once over the merged round-12 engine
  it found the largest wrong-molecule cluster in the census (a 1,3,4-oxadiazol/thiadiazol-3-yl locant, 21 structures,
  1.05%, present since round 6) that no backlog row had recorded: 93.5% of the sample reads back exactly, 2.4% are
  candidate wrong structures, 1.9% are visible failures. `--compare` shows what moved since a previous scan;
  `--names-only` needs no JRE. Refuses a sample that does not match `census_sample.meta.json`'s hash.

### Naming round 9 (branch `naming-round-9`)

- **A source-backed battery first, then a fixed, ledger-enforced set of fixes:** a Blue Book PDF harvest
  (`bluebook_tuning.json`/`bluebook_frozen.json`, 1129 tuning rows), an ordinary-compound battery (`battery_r9.toml`, 306
  rows across dipeptides, salts, dyes, reagents, drugs and more), and a 2000-row frequency census, run BEFORE any fix; 13
  findings admitted into a hash-frozen ledger (`benchmarks/naming/admissions_r9.toml`), guarded by a check on item count
  and set-immutability that is never pinned to a literal cap number.
- **Wrong molecules fixed, each verified via OPSIN round-trip and a 1129-row stage comparison showing 0 structural
  regressions:** DCC (a carbodiimide) no longer names as a saturated bis-amine; two carboximidamide groups at the same
  ring position no longer collide onto one N/N' pair; a naphthalene-2,3-diyl diacetic acid no longer drops an entire
  fused ring to plain benzene; a sulfinyl bromide with an extra imine substituent no longer silently drops its bromine
  and its S=N bond (now an honest naming failure instead); a P(V) phosphine oxide no longer loses its oxidation state
  to a P(III) phosphanetriyl; an ethynediide dianion, a bicyclic phosphide anion, and an imine-nitrogen anion (butaniminide)
  no longer drop their charges to a neutral structure.
- **A preference gap closed to the book's own worked example:** the retained "-yl" acyl convention for peptide bonds
  (P-103.2.5/P-103.3.2) is now built — a closed, stereo-matched table of the 20 proteinogenic amino acids reaches
  "glycylalanine" for the book's own worked example; 14 of the ordinary-compound battery's 20 dipeptides now use the
  retained form (the other 6 all involve threonine or isoleucine, whose stereo is under-specified in that battery's own
  data, so declining is correct, not a miss).
- **A regression caught and fixed before it ever reached a commit:** a first version of the phosphide-anion classifier
  claimed an acyclic phosphide (`dimethylphosphide`) that already had a correct name through a different route, and
  rendered it wrong; the stage-comparison discipline this round follows caught it immediately, and the classifier is now
  gated to ring phosphorus only, with the regression pinned as a converse test.
- **Not done, recorded with their diagnosis** in `src/openchem/vendor/KNOWN_LIMITATIONS.md` ("Open after naming round 9"):
  a carbamimidate/oxime prefix-bracketing ambiguity (fix identified, deferred for its regression risk across all
  substituent naming), two dye-molecule ring-numbering defects (methylene blue's phenothiazine core, fluorescein's spiro
  xanthene — different root causes, neither yet isolated to a fix), and a polycarbocation needing multiplicative and
  charge-perception machinery to work together (no existing pattern to build from).
- **Instruments added:** `tools/naming_bluebook_harvest.py` (PDF extraction with a stratified hand-check),
  `tools/naming_battery_build.py` (the ordinary-compound battery, dipeptides through ChEMBL drugs), `tools/naming_census_build.py`
  / `naming_census_count.py` (the frequency census), `tools/naming_plan_trace.py` (every ranked candidate plan for a
  structure, the candidate-set proof), a per-row worker-process timeout in `naming_stage_artifact.py` (the coronene hang
  this round's own B1 measurement hit).

### Naming round 10 (branch `naming-round-10`)

- **All 4 items round 9 deferred, closed — each turned out deeper than round 9's own diagnosis:** methylene
  blue's phenothiazine ring now names correctly (`[7-(dimethylamino)phenothiazin-3-ylidene]di(methyl)azanium
  chloride`, matching PubChem's own name verbatim) — the actual bug was a third, unrelated numbering function
  whose aromaticity gate silently dropped the correct locants for charged/conjugated dye structures, not a
  missing table entry. Fluorescein's spiro-xanthene locant is fixed the same way
  (`3',6'-dihydroxyspiro[1,3-dihydro-2-benzofuran-1,9'-xanthene]-3-one`, matching its real IUPAC name) — the
  xanthene ring's own table was structurally incomplete (missing 5 of 14 real positions), which broke the
  spiro-combined numbering entirely. The carbamimidate/oxime bracketing ambiguity is fixed — the engine's
  internal structure was correct the whole time; a narrowly-scoped bracket rule now protects a non-leading
  "-oxy" prefix on a one-carbon parent, closing both the original case and a second, independent instance of
  the same bug found during diagnosis. The polycarbocation classifier now correctly engages instead of
  silently dropping both charges; composing an actual preferred name is still open, so it now raises an
  honest, precedented refusal rather than emitting a wrong molecule.
- **A discovery-only frequency check on the older backlog:** reusing round 9's frozen census sample, 6 more
  shapes from rounds 5-8's open list were measured. Two are genuinely common (a ring-nitrogen acyl on a chain
  parent, over 5x the admission threshold; a multiparent fusion hub, over 2x) and are strong candidates for a
  future round; four are genuinely rare. Nothing here was fixed — see
  `src/openchem/vendor/KNOWN_LIMITATIONS.md`, "Open after naming round 10".

### Naming round 11 (branch `naming-round-11`)

- **Two fixes, each re-verified against the current engine before being admitted:** a one-carbon ketone
  parent with two distinct ring substituents now encloses the second one
  (`(morpholin-4-yl)(phenyl)methanone`, matching P-16.5.1.3.1 — the single most common open shape in the
  backlog, 8.4% of a 2000-structure frequency census); a carbamimidoyl prefix with BOTH nitrogens substituted
  now splits into the book's own printed N'/N,N form (`4-(N'-ethyl-N,N-dimethylcarbamimidoyl)benzoic acid`,
  p. 676 verbatim) instead of the generic, OPSIN-misreadable decomposed form — gated so it does not fire when
  doing so would collide with an adjacent guanidinium group, catching a regression on the metformin-cation
  fixture before it ever reached a commit.
- **Two backlog rows re-tested and found already fixed** by other rounds' own general work, never reflected
  back into the documentation until now: a ring-nitrogen acyl prefix on a chain parent (e.g.
  "piperidine-1-carbonyl"), and the citrate-trianion / biguanidium-dication charge-ledger pair from round 7.
- **One row re-diagnosed to its actual root cause and re-deferred:** a charged acid group inside a carved
  substituent still names wrong (e.g. `sulfonato` emitted as the generic `oxidosulfonyl`), traced to a
  computed-but-never-threaded prefix value between two naming layers — broader than previously documented
  (affects a demoted carboxylate the same way, not only sulfonate) but not rushed given the shared code path.
- **A second census extension:** 6 more still-unmeasured backlog shapes. One (a fused aromatic ring cation)
  clears the frequency floor but needs ring-table triage before it names an actual defect; the other five are
  genuinely rare. See `src/openchem/vendor/KNOWN_LIMITATIONS.md`, "Open after naming round 11".

### Naming round 12 (branch `naming-round-12`)

- **A charged acid group inside a substituent now keeps its charge in the right words.** A carboxylate or
  sulfonate on a substituent chain was named atom by atom (`3-carboxy-4-(2-oxido-2-oxoethyl)benzoate`,
  `4-[(oxidosulfonyl)methyl]benzoate`); it is now `3-carboxy-4-(carboxylatomethyl)benzoate` and
  `4-(sulfonatomethyl)benzoate` (P-65.6.2.3.1). The information was correct in the outer plan and lost when
  the substituent was named by a fresh, recursive call; the fix re-derives it from the fragment itself.
  A first version broke a thiolate-plus-carboxylate case (`D-121u`) and was caught by the known-defects suite
  before commit. Of 292 charged structures in the census sample, one other name changed (an aminophosphonate
  zwitterion, now with `carboxylato`), and it reads back.
- **The fused-ring-cation signal from round 11 was triaged and not admitted:** 8 of its 36 hits (and 6 more
  cationic ring systems outside the proxy) fail to name, visibly and never as a wrong molecule, but they are
  spread over about ten different ring systems; the largest is 4 of 2000, under the 10-structure floor.
- **New tooling:** `tools/naming_stage_artifact.py --frozen-impact <sealed stage>` tells, without revealing a
  row, whether a change moved any frozen-population name. See
  `src/openchem/vendor/KNOWN_LIMITATIONS.md`, "Open after naming round 12".

### Naming round 8 (branch `naming-round-8`)

- **Wrong molecules fixed, each found by a test that could not have passed before:** the trianion of a tricarboxylic
  acid (citrate) was named with one carboxylate as a neutral prefix, two charges for three sites; the biguanidium
  cation was named as a dication; every protonated or alkylated aminopyridine, dialkyl triazolium and
  benzotriazolium was another molecule; a lysine or histidine zwitterion beside a salt was named for the wrong
  ionisation state; an isothiourea's demoted prefix `(aminosulfanylmethylidene)amino` was read by OPSIN as another
  molecule (the one wrong structure `heldout_v4` had held). All are correct now, and a name that reads back as a
  different TAUTOMER (PubChem's own metformin drawing, proguanil) is shown with a note instead of being withheld.
- **Names that were right and not the book's** now match it: `2-hydroxypropane-1,2,3-tricarboxylic acid`, `1H-imidazol-3-ium`
  (and protonated benzimidazole, which was a refusal), condensed guanidines and ureas including `diimidotricarbonimidic
  diamide` and the skeletal-replacement names for n >= 5, `N-acetylbenzamide` for the imide parent, the pseudoketones
  (`1-(piperidin-1-yl)propan-1-one`, `bis(phenyldiazenyl)methanone`), acid hydrazides ranked below acids, ring cations
  above every junior group, `4-sulfonatobenzoate` and `2-oxidobenzoate` for mixed-class polyanions.
- **Found by naming ordinary compounds, and in no benchmark row:** acrylamide was `prop-2-eneamide` and allylamine
  `prop-2-ene-1-amine` (now `prop-2-enamide`, `prop-2-en-1-amine`); an oxime ether was `(methyloxyimino)` (now
  `methoxyimino`); the Weinreb amide was `methyl acetylmethylazinite` (now `N-methoxy-N-methylacetamide`), and
  `N-methoxymethanamine`, `N-ethoxyaniline` are named as the book prints them; biacetyl was `3-oxobutan-2-one` (now
  `butane-2,3-dione`); dimethyl carbonate was `dimethoxyoxomethane`; amyl nitrate was `1-(nitrooxy)pentane` (now `pentyl
  nitrate`); phosphonium and sulfonium cations are named on the cation, not on an amide or alcohol beside them; a ring-nitrogen
  amide on a ring is `4-(piperidine-1-carbonyl)benzoic acid`; carbonyldiimidazole no longer crashes the engine and is
  `bis(1H-imidazol-1-yl)methanone`; an embedded engine error is never shown as a name.
- **Measured:** the new 60-row addendum panel goes from 8 wrong molecules, 2 oracle errors and 2 ownership holes to none of
  them (exact 20 to 44); the round-7 panel's exact rows 79 to 91; against the engine the round began with, 37 of 543
  structures changed, none structurally regressed, 13 went from unreadable to reading back. The fresh `heldout_v5` (40 rows,
  scored once, aggregates only) has ZERO wrong structures; the tuning populations moved only where the round meant them to.
- **Instruments added:** `tools/naming_ref_compare.py` (two engines, one manifest of expected changes), `tools/naming_probe.py`
  (the ordinary-compound battery, with the plans that failed to execute), `tools/naming_app_check.py` (the driven check),
  a pinned-name snapshot of 200 shapes no corpus contains, the KNOWN_DEVIATION registry, and the naming-consumer manifest.
- **Not done, recorded with their targets** in `src/openchem/vendor/KNOWN_LIMITATIONS.md` ("Open after naming round 8"):
  peptide acyl prefixes, a charged acid group inside a substituent, carbazate esters, chloroformates and polynitrates,
  the P-15.3 multiplicative constructions, the silicon rows, fusion, and a thiolate beside an acid anion.

### Naming round 7 (branch `naming-round-7`)

- **Anions that carry another group are named as anions.** A carboxylate or sulfonate beside a
  hydroxy, amino or sulfanyl group, a second acid or a nitro group used to come out with `oxido`
  prefixes on the wrong parent: salicylate as `2-oxidooxomethylphenol` (a different molecule),
  lactate as `1-oxido-1-oxopropan-2-ol`. They are now `2-hydroxybenzoate`, `2-hydroxypropanoate`,
  `3-carboxypropanoate` (the mono-anion of a diacid, as the book prints it) and so on, and
  choline salicylate's engine name is no longer withheld. Aspartate and glutamate drawn as they
  are at pH 7 (two carboxylates, one ammonium) are named too.
- **Retained names the Blue Book prints for anions:** `methoxide`, `ethoxide`, `propoxide`,
  `butoxide`, `tert-butoxide`, `phenoxide` and `glycinate` (and their salts); an amide anion is
  `acetylazanide`, not `acetylamide`; a salt with two identical organic anions is
  `calcium diacetate` / `calcium bis(2,3,4,5,6-pentahydroxyhexanoate)`, not `calcium acetate acetate`.
- **A wrong molecule fixed:** the glutamate mono-anion zwitterion was named as the dianion.
- **Measured on a new 108-row panel of charged species built by class** (charged group x
  neighbouring group x context), against the Blue Book: wrong molecules 13 to 0, non-preferred
  names 42 to 9, exact 45 to 90. No name changed in the 307 tuning rows at any stage.
- **Ownership is a checked property.** `perception/charge_ownership.py` reports, for every charged
  atom, which route claims it and which the engine took; a site no route owns is a test failure
  unless its class is declared unsupported with a reason (deprotonated phosphorus acids are).
- **Not done, recorded:** chiral amino-acid anions (`alaninate`; need a stereo policy), the
  `hydrogen phenylphosphonate` construction, `imidazolium` (and protonated benzimidazole, which is a
  NAMING ERROR), and the betaine prefix form. Found AFTER the final evaluation and not fixed: the trianion of a
  tricarboxylic acid (citrate) is named as if one carboxylate were a neutral `carboxy` group, a wrong charge that the
  app's round-trip gate withholds; and the biguanidium cation is named as a dication. See `KNOWN_LIMITATIONS.md`.
- **The held-out boundary is executable.** One registry (`benchmarks/naming/populations.toml`)
  decides which populations any tool may read; a frozen one is refused before its file is opened. The
  fresh set for this round (`heldout_v4`) was drawn and hashed before any diagnosis and was scored
  once, at the end: 19/40 verbatim, 20/40 equivalent and ONE wrong structure, which was not read (it is
  the first row to read in round 8, when v4 becomes a tuning population).

### Functional groups v3 (branch `functional-groups-v3`)

- **Fifteen more features, each defined from a source before it was matched.**
  Thiocarboxylic acids, thiocarbamates (thiono, thiolo and dithio; rhodanine's
  ring is one), thioaldehydes, thioimidates, S-alkylisothioureas, cyanates,
  thiocyanates, cyanamides, acylals, sulfenic acids and sulfenamides, sulfinic
  acids, esters and amides, and acylium ions: 107 in all. Each cites a Gold
  Book headword and page, or the Blue Book rule where the Gold Book is silent.
  Fragment Counts and Functional Groups pick them up from the one detection
  (epalrestat's rhodanine ring and tolnaftate now read "thiocarbamate").
- **A candidate the plan named was refused: N,S-acetals** (penicillin's
  thiazolidine carbon). No source names the class, so a definition would have
  been this vocabulary's own. It, sulfenic esters, thiuram disulfides and
  sulfinohydrazides are recorded in `EXCLUDED_CLASSES` with the reason, and a
  test requires the reason.
- **A project saved by the previous build opens, keeps its Fragment Counts
  (shown as "previous method: vocabulary v2"), and recomputes under the new
  method.** The saved v2 result is never relabelled as v3. A project that
  holds both an older and a newer earlier method now shows the newer one, not
  both.

### Naming round 6 (branch `naming-cyano`)

- **Cyanamides and cyanic / thiocyanic acid esters are named as the Blue Book
  names them.** `NC#N` is `cyanamide` (was `aminomethanenitrile`),
  `CCN(CC)C#N` is `diethylcyanamide`, `CC(C)SC#N` is `propan-2-yl thiocyanate`,
  and `3-(thiocyanato)propanoic acid` replaces `3-(cyanosulfanyl)propanoic
  acid`. The molecules were right before; the names were not the preferred
  ones. Nothing in the three tuning populations changed.

### Naming round 5 (branch `naming-round-5`)

- The vendored IUPAC namer gains general fusion nomenclature (P-25.3),
  multiplicative names, an atom-ownership invariant on the semantic tree,
  a gate over the 1,824 names harvested from OPSIN's parse dictionary,
  principal-group seniority fixes (urea below amides, chain amidines,
  silanols, hydroxamic acids), hydro-locant numbering, and five
  serialization rules. Two WRONG MOLECULES were found and fixed, and three
  registry entries that named the wrong molecule were removed.
- A derived name OPSIN cannot parse is now shown, marked unverified,
  instead of being withheld (`chem/naming_providers.py`).
- Held-out corpus v3 (40 fresh molecules, frozen before the work): 0 wrong
  molecules, 13 matching PubChem's string exactly.


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
- **IUPAC locants now number the rings inside substituents too**, as each
  substituent's own name cites them: naproxen's naphthalene is numbered as
  "6-methoxynaphthalen-2-yl" says. Before, only a ring-table guess was
  available, and for naproxen it was the mirror image (the methoxy carbon
  labelled 2). Over the naming corpus coverage rose from 38.5% to 47.5% of
  heavy atoms. The Atom Inspector's locant cell says where each number came
  from, since a substituent's 2 and the parent's 2 are different atoms, and
  fused rings numbered from the table now show their 3a/7a positions.

### Changed

- **A salt's properties are its parent compound's.** Every calculator now
  declares which components of a drawing it describes. Properties of the
  compound (logP, polar surface area, pKa, logD, the drug-likeness rules,
  QED, the CNS and BBB scores, ADMET) are computed on the parent: ChEMBL's
  rule, which strips listed counter-ions and solvents and re-neutralises what
  is left. The molecular weight, formula, exact mass and net charge still
  describe the whole drawing, as ChEMBL's own FULL_MWT and FULL_MOLFORMULA
  do. So metformin hydrochloride has metformin's logP and passes the rule of
  five, and metformin pamoate no longer "fails Lipinski" on its larger
  counter-ion. When a salt has no single parent -- sodium acetate, where
  every component is a listed salt, or choline salicylate, where none is --
  those properties say so instead of giving a number for the ions together.
  Each result records which components it was computed over.
- **A refusal says which one, everywhere.** Calculators that decline a
  structure record a stable code with the reason (no pi system, element
  outside the method's parameter set, an input you have to supply, a sidecar
  that is not set up), and the method's own limits no longer paint like
  faults. Batch cells carry the same code as Properties.

- **Functional Groups and Fragment Counts are one detection, from one
  vocabulary.** Both used to answer "what groups does this have" with their own
  definitions, and disagreed: Fragment Counts, 24 of RDKit's counters, called an
  imine, an oxime, an azo or nitro group, an azide and a pyridine N a "Tertiary
  Amine" (caffeine had four), counted urea's NH2 as primary amines, a lactone as
  an ester AND an ether, and an acetate as a carboxylic acid. Now 92 features --
  each defined from the IUPAC Gold Book (or the Blue Book where it has none), each
  with a page -- are detected once per structure and projected: Functional Groups
  draws them, Fragment Counts counts them, the Atom Inspector lists them per
  atom. Where one feature is the better description of another's atoms the view
  says so (an acetal's oxygens are not also two ethers; a lactam is counted once
  and shown beside its amide). Charged forms are labelled as drawn: a carboxylate
  is a "carboxylate", a protonated amine an "ammonium". Amides are no longer
  called "secondary" or "tertiary" by their N-substituents, which the Gold Book
  says those words must not mean.
- **Fragment Counts labels changed** (from "Amide (1)", "Tertiary Amine (2)",
  "Benzene Ring (1)" to the vocabulary's own: "amide (1)", "tertiary amine (1)",
  "benzene ring (1)"). A project saved before this keeps its old Fragment Counts
  result, shown as "Fragment Counts (legacy: RDKit fr_* counters)", and never
  mixed with or overwritten by the new one; the always-on set is recomputed on
  opening.

- **Naming round 4: many names move to the Blue Book's preferred forms.**
  Every change was checked against the page it cites. Among them: substituted
  hydrazides, amidines and guanidines are named on their own parent
  (`N'-methylbenzohydrazide`, `N-methylguanidine`); silanols, boronic acids and
  phosphine oxides take the book's forms (`trimethylsilanol`,
  `phenylboronic acid`, `triphenyl-lambda5-phosphanone`); ring ketones cite
  their hydrogens as the book does (caffeine is
  `1,3,7-trimethyl-3,7-dihydro-1H-purine-2,6-dione`); `(acetyloxy)` rather
  than `acetoxy`; substituent order and locant order follow P-14.4/P-14.3.5.
  Several names that denoted a DIFFERENT molecule were found and fixed on the
  way (two dihydrofurans, a biguanide, a dihydrazide). The full account is in
  `src/openchem/vendor/CHANGELOG.md`.

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

- **Graph-distance results on a salt were RDKit's "unreachable" sentinel.**
  Eccentricity read 100000000 for every atom of sodium acetate and the Wiener
  index 400000009. Distances are now taken within each component.
- **pH-dependent charges, the major microspecies and logD failed on every
  salt** with "the protonated form has 4 heavy atoms where the drawing has
  5": protonation dropped the counter-ion and a check then refused the
  result. They now run on the parent compound.
- **Glycine drawn as its zwitterion had no ionizable centre**, so its pH
  curves and isoelectric point were refused. A carboxylate or ammonium now
  counts as the same centre as the acid or amine it came from.
- **Polarizability and atomic polarizability failed outright on sodium,
  potassium and other elements Jensen's table does not cover**; they now
  refuse as outside the method and name the elements it does cover.

- **A ring system's name carried the molecule's configuration** --
  "(5R)-hexadecahydro-1H-cyclopenta[a]phenanthrene", "trans-decalin" -- in
  Functional Groups, Ring Systems and now Fragment Counts. A ring system is a
  skeleton, and a skeleton has no configuration (Blue Book P-91.3), so the
  names are stereo-free now.

- **A sodium salt got no results at all.** Any structure containing an element
  outside the McGowan volume's twelve (sodium, potassium, lithium, calcium,
  magnesium, any metal, selenium, arsenic) lost every always-on descriptor,
  alert and per-atom result, because that one descriptor raised and took the
  rest with it. Now the McGowan volume alone says it does not apply, naming the
  element, and everything else is computed; a descriptor failure also no longer
  discards the alerts and per-atom data, which never depended on it.

- **The Atom Inspector printed a functional group as a number.** "Functional
  Groups: 1" on every atom of a group, and "Ring Systems: 1" likewise, because a
  categorical value was printed as its colour id. It now says what the atom is
  part of -- "acetal; ether (non-primary)" on an acetal oxygen.
- **Lactams, imides, cyclic ureas and ring carbonyls were claimed by no group**
  (caffeine, phenobarbital, pyrrolidinone, penicillin's beta-lactam), and
  phenobarbital showed no functional group at all. They are lactams, imides and
  ureas now.

- **A retained name is shown beside the preferred IUPAC name.** Where a
  compound is widely known by a name IUPAC keeps only for general use --
  caffeine, camphor, ibuprofen, chloroform -- the IUPAC Name result now
  gives the preferred name first and that name second, labelled as not the
  preferred one. Without it those names would have disappeared from the app
  entirely, since PubChem answers with the systematic string too. A name
  that IS both, like `toluene`, is shown once.

- **`isoxazole` and `benzofuran` are named as IUPAC prefers.** They become
  `1,2-oxazole` and `1-benzofuran`, which is also what sulfamethoxazole's
  name now uses. Both were inconsistent with their own neighbours in the
  same table -- plain oxazole was already `1,3-oxazole`, and
  `1-benzothiophene` sits beside benzofuran with its locant -- and the `1-`
  is what distinguishes 1-benzofuran from 2-benzofuran.
- **Trivial names are no longer shown as the IUPAC name when they are not
  one.** `butyraldehyde` becomes `butanal`, `triethylamine` becomes
  `N,N-diethylethanamine`, and camphor, caffeine and ibuprofen now get their
  systematic names. The table these came from asserted that all 292 of its
  names were preferred IUPAC names while citing a rule for 31 of them -- 161
  were harvested from a name PARSER's dictionary, which only establishes
  that a name can be read. Each entry now records whether it is preferred
  and why, with the quotation, in `benchmarks/naming/adjudication.toml`.

  Only the names the benchmark actually depends on were audited, and the
  remaining 274 entries behave exactly as before: denying them on no
  evidence would be the same mistake in the other direction.
  `tools/retained_name_audit.py` shows what is still unaudited.

  Two went the other way on reading the source. `toluene` IS a preferred
  IUPAC name and keeps it; and `1,4-xylene` turns out to be preferred over
  the engine's `1,4-dimethylbenzene`, which is still to fix.
- **Nested substituent names use the right kind of bracket.** Atenolol was
  `2-{4-{2-hydroxy-...}phenyl}acetamide`, with a brace directly inside a
  brace; IUPAC's nesting order cycles through parentheses, square brackets
  and braces and then starts again, so the outer one should be a
  parenthesis. Six names were affected. The same fix stops a spiro or
  bicyclo descriptor -- `[4.5]`, `[2.2.1]` -- from being counted as a level
  it was never part of.
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
- **A name the checker cannot read is shown, marked unverified, instead of
  withheld.** A derived name is parsed back with OPSIN; when OPSIN could not
  parse it at all, that counted as a wrong name and it was hidden. The first
  real case was a Blue Book PIN -- "N1,N2-bis(cyanomethyl)oxamide" -- which
  OPSIN cannot read. A checker failure now reads "Not verified: the checking
  parser (OPSIN) could not read this name back"; a name that parses to a
  different structure is still withheld. The IUPAC Name report also now
  shows a derived name's note at all: it built each line from the name
  alone, so that note -- and the stereochemistry notes before it -- never
  reached the screen.

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
