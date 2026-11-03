# Data, model and benchmark notes

Charge models, NMR, solubility, docking ranking, radii, interaction rules, melting/boiling and energetic-materials benchmarks, derived scores, structure-file formats and the source-reading traps found along the way.

These sections were moved here on 2026-10-29 from the assistant's private memory, so they are readable, searchable and versioned with the code. The text is kept as it was written (headings demoted one level, memory links written as plain names); dates and PR numbers are those of the time. Treat a measurement as true of the commit it was made on, and check a file or function named here still exists before relying on it. Where the original text named a commercial product or its vendor, the generic wording the repository uses ("the reference editor", "the vendor") stands in its place, as `tests/test_no_competitor_names.py` requires.

## Contents

- [project-qeq-shipped-a8](#project-qeq-shipped-a8) — QEq SHIPPED (PR #103 merged, 6fc42a1) under A8; O9 study PR #104: paper bound procedure is optimal on all 173 converged corpus molecules, the one bound-active case is non-convex runaway, refusal stays
- [project-charge-round3-six-tracks](#project-charge-round3-six-tracks) — Round 3 of the charge work (2026-09-15): six tracks, what each concluded, and which PRs carry them
- [project-charge-units-logd-branch](#project-charge-units-logd-branch) — Branch charge-index-space-and-results-units (2026-09-13) — 7 commits fixing pH charge atom order, stale per-atom values, Results layout, MMFF94, live units, LogD curve; plus its open edges
- [reference-charge-models-and-eem-literature](#reference-charge-models-and-eem-literature) — charge-model history (QEq/EEM/QTPIE), their source papers' traps, the MMFF94 oracle, Open Babel sign inversion and requested energetics papers
- [reference-openbabel-charge-models](#reference-openbabel-charge-models) — Open Babel's QEq returns sign-inverted charges (upstream unfixed); its EEM is exact but eem.txt only partly matches Bultinck; BABEL_DATADIR works only when set from Python AFTER import
- [reference-mmff94-halgren-table-v](#reference-mmff94-halgren-table-v) — Halgren 1996 part II Table V is an exact MMFF94 charge+type oracle RDKit reproduces on 19/20 molecules; the 20th row's carboxylate C contradicts the table's own acetate row
- [reference-chen-thesis-qtpie-code](#reference-chen-thesis-qtpie-code) — Chen's 2009 QTPIE thesis carries its own Fortran source (Appendix A), which settled what prose could not; its Table 2.2 exponents do not recompute from §2.4, and H is printed two ways
- [project-nmr-ml-not-shipped](#project-nmr-ml-not-shipped) — A gradient-boosted NMR shift model was trained on nmrshiftdb2 (2026-08-03) and lost to the HOSE lookup; do not retry without a GNN
- [solubility-predictor](#solubility-predictor) — Solubility predictor — aqueous, 91 non-aqueous solvents by lookup, and the base bias that is reported rather than corrected
- [project-affinity-ranking-program](#project-affinity-ranking-program) — Docking ranking program — route 1 shipped; route 2 ranking MEASURED NULL on a ChEMBL corpus; route 3 spiked and refused at corpus scale on cost; smina spike started 2026-09-12
- [project-vdw-radii-program](#project-vdw-radii-program) — van der Waals radii decisions 2026-10-11/12 (all merged): Bondi's own radii for steric, surface, volume, projections, Geometry; RDKit's table is Batsanov's; H stays 1.20; docking keeps its own table; what is open
- [project-interaction-analysis-v2](#project-interaction-analysis-v2) — Interaction Analysis method interactions-v2 (2026-10-11) - five rules fixed, what stays a limit, what was stacked on, and the open docking-side twin
- [project-metal-bond-windows-followup](#project-metal-bond-windows-followup) — DONE and merged: metal-bond-as-clash fix (#294), per-metal bond windows (#299, interactions-v3), fluorine refinements (#301/#302); the sourced targets and what is still open
- [fluorine-donor-acceptor-prs](#fluorine-donor-acceptor-prs) — 2026-10-12 fluorine work, ALL MERGED (#301, #302) — F metal donor rule (C/B-bound F: Na/K/Ca only; fluoride ion: every metal), C-F/B-F not an H-bond acceptor, PDB survey; what is still open
- [project-mp-bp-benchmark](#project-mp-bp-benchmark) — Melting/boiling-point benchmark (preregistered): corpus #462, Marrero-Gani fragmenter #463, holdout scored ONCE 2026-10-25 in #464, no method passed; don't re-run the holdout
- [project-phase-b-decisions](#project-phase-b-decisions) — Phase B (energetic materials) owner decisions made 2026-10-26 in chat, before the preregistration is amended and frozen; COD is the label source for crystal density
- [project-petn-evidence-inventory](#project-petn-evidence-inventory) — PR #472, the PETN / nitrate-ester / nitramine evidence inventory: what it found, the owner decisions it wrote into the Phase B preregistration, and what is still open
- [reference-thermochemical-lineage-traps](#reference-thermochemical-lineage-traps) — Traps when tracing old thermochemical values (compilation dates, one root behind many books, OCR negatives, printed unit errors) and the routes that work
- [project-geometry-derived-scores](#project-geometry-derived-scores) — Derived scores over the ten shape descriptors (PR #364 MERGED 2026-10-17 as 73e10177, branch claude/geometry-derived-scores): what it does, the four-units finding, Alex's three answers, traps hit
- [project-more-3d-derived-scores](#project-more-3d-derived-scores) — Second round of geometry derived scores (2026-10-17, branch claude/more-3d-derived-scores, PR #367 MERGED 2026-10-18 as 38771fe1): Alex's decisions, the measurements behind them, and the CORRECTION about the ten shape descriptors
- [reference-a-derived-column-is-a-checksum](#reference-a-derived-column-is-a-checksum) — When a table prints an input AND a quantity derived from it (Rappé Table I: R and zeta), recompute the derived column while transcribing; it found hydrogen's hidden lambda=1/2 and an oxygen misprint before any solver ran
- [reference-shannon-radii-column-trap](#reference-shannon-radii-column-trap) — Shannon 1976's CR and IR columns are offset by 0.14 A with the sign flipping between cations and anions, so a spot-check cannot catch a transposition
- [reference-pdb-survey-recipe](#reference-pdb-survey-recipe) — How a direct PDB survey was done (RCSB search + mmCIF), the API quirks that cost time, and why a ligand's real-space correlation is the filter before trusting a close contact
- [project-cif-import-routes](#project-cif-import-routes) — Measured state of getting a CIF into the app, and why COD beats RCSB despite the RCSB fetcher already existing
- [reference-cod-cif-fixtures](#reference-cod-cif-fixtures) — Real COD depositions are committed as CIF test fixtures, and each one states a volume and density that validate the whole parse chain independently
- [openbabel-mmcif-divergences](#openbabel-mmcif-divergences) — Open Babel reads mmCIF and PDB differently in three ways; two are fixed, the protonation one is not and nobody knows which arm is right
- [reference-seed-can-lock-in-the-wrong-answer](#reference-seed-can-lock-in-the-wrong-answer) — Pinning a random seed makes a wrong answer permanent instead of occasional — measure WHICH result the seed gives before shipping it
- [project-multicomponent-largest-component](#project-multicomponent-largest-component) — Group 3 of the refusal audit (PR #460) - a salt with no single ChEMBL parent is computed on its largest component, labelled; what still refuses; the 2D-vs-3D trap
- [project-conformer-funnel-closed](#project-conformer-funnel-closed) — Conformer generation, asked three times: the filter was acquitted (2026-08-13), and the third round moved the diagnosis to the EMBEDDER and pinned the seed (2026-09-11)
- [project-d191-d192-lambda-and-nuclide](#project-d191-d192-lambda-and-nuclide) — D-191/D-192 (hypervalent lambda number, nuclide on a one-atom prefix): MERGED 2026-10-06 as #238 (edda176a), fork port merged as fork #23 (e9a2d5f), VENDORING row in #241; D-193..D-196 still open
- [project-vb-ties-stage](#project-vb-ties-stage) — The three von Baeyer ties left open by #218 (meso, cages, compound locants) closed 2026-10-06: app #226 (1cac2a06) + fork #20 (547e00d); what is still open and what to know before touching it
- [reference-app-withholds-bad-names](#reference-app-withholds-bad-names) — The app WITHHOLDS an engine name that embeds NAMING ERROR or reads back as another structure; only an OPSIN-unreadable name is shown (unverified) - so engine defects rarely reach the user as wrong names
- [reference-caller-atom-maps-break-dimorphite](#reference-caller-atom-maps-break-dimorphite) — A drawing's atom-map numbers reaching Dimorphite-DL change its answer (mapped imidazole: no state); strip before any library call, restore per atom after
- [reference-py2opsin-cwd-collision](#reference-py2opsin-cwd-collision) — py2opsin uses a fixed temp filename in the CWD, so two OPSIN callers in the same directory crash each other
- [project-sources-registry](#project-sources-registry) — OpenChem Studio has a guarded provenance registry at docs/sources.toml; how to add to it and what its guards can and cannot prove
- [reference-ionescu2013-si](#reference-ionescu2013-si) — Ionescu 2013's SI: the one EEM source whose population is exactly recoverable, plus the four traps in reading it
- [reference-wilmer2012-si-structures](#reference-wilmer2012-si-structures) — Wilmer 2012's EQeq supporting information: what the ACS package holds, and why its .mol files are not molfiles
- [project-nmr-validation-sources](#project-nmr-validation-sources) — NMR ground truth must be independent of nmrshiftdb2; quinine is scored and shows the hybrid's calibration gate refusing a real gain
- [reference-belova2014-table1-vs-si](#reference-belova2014-table1-vs-si) — Belova 2014 (acetylacetone) main-text Table 1 and its own SI disagree on which B3LYP basis gave which dE; use the SI energies, MP2/cc-pVTZ is consistent

## project-qeq-shipped-a8

*From the assistant's notes (`project_qeq_shipped_a8.md`, type: n/a).*  
*QEq SHIPPED (PR #103 merged, 6fc42a1) under A8; O9 study PR #104: paper bound procedure is optimal on all 173 converged corpus molecules, the one bound-active case is non-convex runaway, refusal stays*

**PR #103 MERGED to master as 6fc42a1 (2026-09-14).** Alex decided to ship QEq under a revised scope, refuse bound-active solutions, and offer only the experimental H set.

- A8 records it; the original O4/O5 gate stays failed (strict xfails kept).
- Method code `qeq_rg1991_lambda_half_h_experimental` in "Partial Charge (3D)".
  - EEM stays default (key `c8a6d189021bbd3d35d4621f5b102f37` pinned).
  - `REFUSE_BOUND_ACTIVE` uses `final_active_atoms` only; `ever_clamped` is separate.
  - Silicon results carry a source-discrepancy note.
- **Speed:** Stage 1 batched quadrature was 4-13x faster but missed the 5 s gate.
  - Stage 2 closed form (Kummer sign switch; fallback below min(a,b)R < 2): atorvastatin 0.40 s (was 130-200 s), charges unchanged to 6.5e-14 e.
  - A quarter of the quadrature panels still matches to 1e-11, so the panel rule is conservative. Recorded, not exploited.
- **New drive step `result_report`** asserts the refusal code; Properties shows only "Not applicable".

**PR #104 MERGED to master as 75af939: amendment A9.**
- On the 174-molecule corpus, 173 converge (methanediylium does not).
- The paper's never-release fixing is the exact constrained optimum on every converged molecule.
- The ONE bound-active molecule, propane-1,3-diide (two H at -1), is also the ONE non-convex QEq matrix. Its unique KKT point is shared by paper, QP and brute force, and it is unphysical.
- Conclusion: don't replace the procedure; keep the A8 refusal.
- Slips: an unquoted CSV split 14 names, and the note first said 8.

**Why:** Alex asked whether the QEq work was wasted. The honest answer was a narrower, recorded claim, plus a speed fix, since speed was the real blocker.

**How to apply:**
- Don't re-open whether QEq ships.
- O9 is closed on this corpus: keep never-release fixing and the refusal unless a larger, more ionic set finds a convex bound-active case.

Related: project_state_2026_09_14 (pruned 2026-10-06), `feedback-heldout-experiment-discipline`.

## project-charge-round3-six-tracks

*From the assistant's notes (`project_charge_round3_six_tracks.md`, type: n/a).*  
*Round 3 of the charge work (2026-09-15): six tracks, what each concluded, and which PRs carry them*

Alex asked for every deferred charge thread to be pushed "as far as we can" and chose all six tracks. The approved plan is at `C:\Users\pmpd\.claude\plans\let-s-continue-with-the-breezy-feather.md` (revision 5, after four ChatGPT review rounds).

State as of 2026-09-15, with every track run:

- **Track 2, charge models in the dipole and ESP** — **MERGED** (PR #110, master 9165d4f). One `evaluate_charges` producer, a `chem/atom_identity.py` projection service, and ARCHITECTURE's per-atom index defect settled. Dipole MAE: Gasteiger 0.79 D, EEM 1.79, QEq 1.69 — reported, never used to pick a default.
- **Track 5, Ionescu 2013 EEM** — PR #113. **REPRODUCED**: all 12 E models, 36/36 model x dataset rows, with the test proteins agreeing at the charge file's own printing precision (median |Δ| 2.3e-07). See `reference_ionescu2013_si`. GO-CANDIDATE for shipping under per-model keys.
- **Track 1, Mathieu SQE causes** — PR #114. The printed (115, 0.816) is **not** where our error is minimised; Powell finds 3.8% lower at C = 56.8 with λ almost unchanged (0.8147 vs 0.816). **So the difference is in the C term, not λ.** Three candidates ruled out: the numerical arm, the Ohno–Klopman kernel, and the parameter set (the paper's model C misses too). S is INCONCLUSIVE because the Hessian there is indefinite — the instrument declines rather than guessing.
- **Track 4, Nistor SQE** — PR #111. The geometry is not "missing a hydrogen": the coordinate column is displaced one row. 6 of 41 recover; **no method reproduces** (PARTIAL). Kernel gate passed at 5e-13 eV.
- **Track 6, periodic EQeq** — PR #112. **BLOCKED**: the ionisation table, the 12 MOF structures and their charges are ACS accompanying files, none held. Three repo records claimed otherwise and were corrected.
- **Track 3, charges at a pH** — the state is carried onto the conformer (heavy atoms and retained H keep coordinates to the bit; only added H are placed). Two findings worth keeping: RDKit's canonical ranking calls a **prochiral CH₂'s two hydrogens equivalent**, so hydrogen choice is decided by prochirality instead; and the Properties panel keys results by `dataset.property_id`, not calculator id, so two calculators sharing an id silently overwrite each other — found by driving the app with every unit test green.

Two habits that paid off again here: pre-registering before the numbers exist (amendments A3 for Nistor and the envelope amendment for Ionescu were both made openly, before any result they judge), and mutating every guard — the Ionescu calcium mutation survived until a test with a calcium atom in it was added.

Related: project_qeq_hydrogen_and_model_triage (pruned 2026-10-06), `feedback_heldout_experiment_discipline`, `feedback_break_a_guard_before_believing_it`.

## project-charge-units-logd-branch

*From the assistant's notes (`project_charge_units_logd_branch.md`, type: n/a).*  
*Branch charge-index-space-and-results-units (2026-09-13) — 7 commits fixing pH charge atom order, stale per-atom values, Results layout, MMFF94, live units, LogD curve; plus its open edges*

Branch `charge-index-space-and-results-units` off master 8f31d95. MERGED as PR #96 (merge commit aa1357b) on 2026-09-13 after CI green (4 checks); branch deleted, docs swept in 3de9759. See project_state_2026_09_13 (pruned 2026-10-06). Commits in order: atom-order fix (5af3731), Atom Inspector freshness (159c254), modal reveal starving subscribers (d651f68), MMFF94 method (a711c87), Results note folding/layout (acbaa8e), Solubility units as renderings (29db633), LogD curve merge + cursor pin (2695cfa). Full suite passed on 159c254 and (after one flaky segfault, rerun) on acbaa8e.

**Why:** Alex reported a charge discrepancy between Calculator Inspector and Atom Inspector, a squeezed Results panel, and asked for live unit switching and a LogD/LogD-vs-pH merge. Plan was reviewed twice via ChatGPT (`feedback-chatgpt-review-loop`).

**Open edges, deliberately left (how to apply: don't re-report these as new bugs):**
- ORCA-service spectra carry no input fingerprint, so the Atom Inspector still shows them unchecked after an edit.
- pkasolver (basic pKa 3.20, neutral at 7.4) and Dimorphite (protonated) disagree on O1OCN1 — recorded in SCIENTIFIC_LIMITATIONS as unresolved, not fixed.
- Results docked top at 190 px still needs ~208 px, so a small outer scroll remains.
- Charge method is a parameter on `gasteiger_charge_at_ph`: an MMFF94 run REPLACES the Gasteiger result (app convention), it does not sit beside it.
- Open Babel EEM/QEq deferred in ROADMAP. MMFF94 oracle: `reference-mmff94-halgren-table-v`.

## reference-charge-models-and-eem-literature

*From the assistant's notes (`reference_charge_models_and_eem_literature.md`, type: n/a).*  
*charge-model history (QEq/EEM/QTPIE), their source papers' traps, the MMFF94 oracle, Open Babel sign inversion and requested energetics papers*

Moved verbatim out of MEMORY.md on 2026-10-06 to keep the always-loaded index small.

- [Charge/units/LogD branch](project_charge_units_logd_branch.md) — MERGED PR #96: pH charge atom order, stale inspector values, MMFF94, live units, LogD curve; four open edges deliberately left
- [MMFF94 oracle: Halgren II Table V](reference_mmff94_halgren_table_v.md) — RDKit matches 19/20 molecules exactly incl. types; the zwitterion C contradicts the acetate row (its footnote is on another column)
- [Open Babel charge models](reference_openbabel_charge_models.md) — QEq returns sign-inverted charges (upstream unfixed, W5 stopped); EEM exact but eem.txt only partly Bultinck; set BABEL_DATADIR from Python AFTER import
- [Charge model history](project_qeq_shipped_a8.md) — QEq shipped closed-form (#103); A10-A12 hydrogen triage (Mathieu SQE HOLD, EEM shipped on TS); charge round 3's six tracks pushed, only Ionescu 2013 reproduces exactly (`reference_ionescu2013_si`)
- [Ionescu 2013 SI](reference_ionescu2013_si.md) — the one exactly-recoverable EEM population, four reading traps including two different CSV layouts
- [Wilmer 2012 SI structures](reference_wilmer2012_si_structures.md) — 12 MOFs x 4 charge sets with cells; its .mol files are RASPA listings, not molfiles
- [Chen thesis QTPIE code](reference_chen_thesis_qtpie_code.md) — the thesis carries its own Fortran; it settled the overlap row, Table 2.2 does not recompute (H printed two ways)
- [Check licence before transcribing](reference_check_licence_before_transcribing.md) — arXiv default licence grants no redistribution; Chen's Fortran was not transcribed, its printed test numbers still usable
- [Energetics literature & requests](reference_energetics_literature_and_requests.md) — papers held in Sci Downloads, prep.70064 REQUESTED from authors 2026-09-24, corrections (Davis = crystal density @200 K, not TMD)
- [Belova 2014 Table 1 vs SI](reference_belova2014_table1_vs_si.md) — the paper's Table 1 and its SI disagree on which B3LYP basis gave which dE; use SI energies, MP2/cc-pVTZ is consistent

## reference-openbabel-charge-models

*From the assistant's notes (`reference_openbabel_charge_models.md`, type: n/a).*  
*Open Babel's QEq returns sign-inverted charges (upstream unfixed); its EEM is exact but eem.txt only partly matches Bultinck; BABEL_DATADIR works only when set from Python AFTER import*

Measured 2026-09-14 (openbabel-wheel 3.1.1.23, Windows). The scripts and tables are in `benchmarks/charges/` on branch `eem-qeq-through-open-babel` (PR C, W5a). The W5 stop rule fired for QEq.

- **Data directory:** set `os.environ["BABEL_DATADIR"]` to `<pkg>/bin/data` from Python *after* `import openbabel`. The DLL reads the variable when it opens a file, from Python's environment. A value set in the shell is overwritten by the wheel's `__init__`. Run it in a child process so the main process's Open Babel (symmetry expansion, format conversion) is untouched. See `openbabel-mmcif-divergences` and the LESSONS entry "OPEN BABEL HAS NO DATA FILES ON WINDOWS".
- **QEq crashes the interpreter whenever `qeq.txt` cannot be opened.** `GetParameters` tests `size()-1` on an empty vector. EEM fails cleanly with all charges 0. "No parameters found for: C 1" means the file never opened, not a parsing bug.
- **QEq sign bug:** `qeq.cpp` puts `+chi` on the right-hand side where stationarity needs `-chi`.
  - Neutral molecules come out as the exact negative of the correct solve.
  - Charged molecules are just wrong: up to 8 e off.
  - Upstream master is identical.
  - Even sign-corrected, magnitudes are 2–7× Rappé–Goddard's Table IV. The cause was not isolated.
- **EEM:** the implementation equals Bultinck eq 1 to 1e-15 e, and so do all six eem2015 sets. But `eem.txt`, labelled Bultinck:
  - matches part II Table 2 for H, N and F only; C and O differ;
  - gives twelve elements carbon's pair;
  - computes any unlisted element as hydrogen through its `* *` row.
  - Part I (JPCA 2002, 106, 7887) is now held (`bultinck2002.pdf`), and eem.txt's C eta* 8.97 and O pair appear in none of its tables either. The eem2015 sets' source is still unknown.

**How to apply:** do not ship QEq from Open Babel. Do not label EEM "Bultinck" without part I. An EEM wrapper must refuse unparametrized elements. SUPERSEDED 2026-09-14: both were implemented in-house on branch rappe-goddard-qeq; EEM shipped, QEq stopped at its gate. See project_state_2026_09_14 (pruned 2026-10-06).

## reference-mmff94-halgren-table-v

*From the assistant's notes (`reference_mmff94_halgren_table_v.md`, type: n/a).*  
*Halgren 1996 part II Table V is an exact MMFF94 charge+type oracle RDKit reproduces on 19/20 molecules; the 20th row's carboxylate C contradicts the table's own acetate row*

Halgren, J. Comput. Chem. 1996, 17, 520 (MMFF part II), **Table V, pp. 533-534** (PDF pages 14-15 of `halgren1996_II.pdf` in Sci Downloads — Alex renamed the five parts `_I`..`_V`; all download as `halgren1996`). It lists MMFF94 atom types and charges for 20 molecules/ions.

Measured 2026-09-13: RDKit `MMFFGetMoleculeProperties(AddHs(mol)).GetMMFFPartialCharge` reproduces every charge AND every atom type for 19 of 20 (methanol…aniline, imidazole, water, acetate, methylammonium, imidazolium). Two in-source defects, not RDKit's:
- zwitterion `-O2C(CH2)6NH3+` prints carboxylate C **0.900**; the acetate row prints **0.906** for the same types in the same bonding (eq. 7 makes them identical), and RDKit gives 0.906. **Footnote (o) is on the ABRAHAM column (-0.545), NOT the MMFF value** — I first recorded the MMFF 0.900 as "inferred per footnote (o)", which was a misread caught by rendering the row at 400 dpi. It is an unflagged internal contradiction.
- imidazole ring H printed as type "15"; RDKit gives type 5, charge 0.150 agrees.

The "Gast." column is SYBYL 5.5 Gasteiger and differs from RDKit's (methanol O -0.398 vs -0.400, acid C +0.256 vs +0.300) — not an oracle for our Gasteiger. The QEq column is Cerius 3.2 on MP2 geometries — not an oracle for Open Babel QEq.

Tosco/Stiefl/Landrum 2014 (`tosco2014.pdf`) is the RDKit-port validation paper; cite it as implementation reference. Read with pymupdf per `reference-reading-pdfs-in-this-project`; see `feedback-a-source-can-contradict-itself` and `feedback-the-fields-nobody-can-check` — superscripts are exactly such a field.

## reference-chen-thesis-qtpie-code

*From the assistant's notes (`reference_chen_thesis_qtpie_code.md`, type: n/a).*  
*Chen's 2009 QTPIE thesis carries its own Fortran source (Appendix A), which settled what prose could not; its Table 2.2 exponents do not recompute from §2.4, and H is printed two ways*

`chen2009thesis.pdf` (Sci Downloads, arXiv:1004.0186) has **Appendix A: the full Fortran 90
QTPIE source** (pdf pp ~180–215). Search the extracted text for `sGTOOvInt`, `DosGTOIntegrals`,
`GaussianExponent` before reasoning from the prose.

- The code applies the SAME Gaussian exponent to the overlap S and to the Coulomb J; LAMMPS
  `fix qtpie/reaxff` uses exactly that overlap formula (TRIAGE 3.10, 2026-09-16).
- H's exponent: Table 2.2 prints 0.5434, the appendix 0.534337523756312; the other 15 agree.
  LAMMPS's example gfile copies the table. Unresolved.
- Table 2.2 cannot be recomputed from §2.4: any reading makes alpha/zeta^2 constant per n, and
  the table's is not (Li 0.957 vs O 0.236). Don't re-attempt readings; that is fishing.
- Text extraction loses the Greek in eqs 2.14/2.15 — render the page to PNG (pymupdf) and read it.

Related: `reference-reading-pdfs-in-this-project`, `feedback-a-source-can-contradict-itself`

## project-nmr-ml-not-shipped

*From the assistant's notes (`project_nmr_ml_not_shipped.md`, type: n/a).*  
*A gradient-boosted NMR shift model was trained on nmrshiftdb2 (2026-08-03) and lost to the HOSE lookup; do not retry without a GNN*

Measured 2026-08-03 on branch `feature/admet-and-nmr-ml`: a
HistGradientBoostingRegressor trained on nmrshiftdb2 does NOT beat the
HOSE lookup in `chem/nmr_database.py`. Held-out carbon MAE: lookup 2.91,
model 3.32, best hybrid 2.91 (a tie). Full evidence in
`benchmarks/nmr/README.md`.

**Why:** with training leakage left in, the model's optimum is to *copy*
the lookup (2.89, reached in 49 of 400 iterations). Every RDKit atom
descriptor scores <=0.01 ppm on permutation importance. Boosted trees over
per-atom descriptors add nothing to a HOSE code, and more capacity does
not help.

**How to apply:** do not re-run this experiment. The only route that could
work is a message-passing GNN (torch, ~490 MB) — a dependency decision for
Alex, not an incremental step. A cheaper unexplored lead is recorded
below.

**The fix found alongside it DID ship** (commit 62285a0, index format 2):
34.3% of nmrshiftdb2 records carry explicit hydrogens, `hose_code` walks
them, so that third spoke a code vocabulary the rest could not match — and
`Chem.AddHs` queries were silently wrong (toluene methyl 8.89 ppm vs
literature 21.4). Both sides now normalise through
`nmr_database.heavy_atom_view`. Held-out carbon 2.91 -> 2.85 ppm, paired
delta −0.092 [−0.122, −0.064]; ~5x the ML model's only real effect, for no
new dependency.

**Any existing built index is format 1 and stale.** `stale_format()`
detects it and the External Tools status line offers a rebuild; a format-1
index still answers correctly, just reaches less. Alex's own index at
`D:/Random Programs/OpenChemStudio_Data/nmrshiftdb.sqlite` was NOT
rebuilt — that is his call.

Related: `reference-py2opsin-cwd-collision`, `feedback-verify-real-backends`

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [NMR: ML dropped](project_nmr_ml_not_shipped.md) — boosted-tree model lost to the HOSE lookup; nmrshiftdb2 circular as ground truth; quinine unfinished (`project_nmr_validation_sources`)

## solubility-predictor

*From the assistant's notes (`project_solubility_predictor.md`, type: n/a).*  
*Solubility predictor — aqueous, 91 non-aqueous solvents by lookup, and the base bias that is reported rather than corrected*

`src/openchem/chem/solubility.py` + `chem/abraham.py`, two calculators in a
Solubility panel section. **PR #28 merged to master (`f9a4627`); PR #29 open
on `solubility-base-bias`.**

Aqueous: ESOL baseline in three units, the vendor's Low/Moderate/High from the
INTRINSIC value, value at a chosen pH, pH curve, and a **bounded** ICH M9
screen (verdict comes from S ≥ S₀ and uncapped HH, so no arbitrary constant
decides a regulatory-shaped answer).

Non-aqueous: **91 solvents by lookup on BOTH sides** of Abraham's solvation
equation (`tools/build_abraham_tables.py`). Acetic acid is refused on two
measurements — it fails the shipped uncertainty bound, and the predicted
table is the `c=0` log-P form with no intercept.

**THE BASE BIAS IS REPORTED, NOT CORRECTED — and this is the part to read
before touching it.** ESOL under-predicts bases (−0.59 SC-1 n=27, −0.42
SC-2 n=17). `benchmarks/solubility/base_bias.py` ran a pre-registered
leave-one-corpus-out held-out test: 4 of 5 criteria pass, base RMSE
improves both ways, the adjustment removes the bias in-sample (−0.619 →
−0.108) — but both bootstrap CIs span zero. Outcome `SURFACE_ONLY`,
`insufficient_evidence`.

**"Insufficient evidence" is NOT "no bias".** The constraint is held-out
druglike BASES: ~30+ intrinsic-solubility bases outside SC-1/SC-2/Delaney
would settle it. Avdeef's full Wiki-pS0 would do it and is book-only, so
unobtainable. Rerun is one command; criteria are versioned.

**Adding corpora did not help, and the reason generalises:** power is set
by the TEST side. A1/A2 (from avdeef2020.pdf) are too small to be held out,
so they only joined the fit pool and the SC-1 CI moved −0.0009 → −0.0338.
A1 is 74% inside ESOL's own training set and yields zero bases.

**Superseded figures:** anything citing 67 scored or a −0.52 base bias
predates the polymorph fix — three SC-1 compounds were being scored twice.
PR #28's body still quotes the old ones and is immutable history.

Related: `feedback_ask_leakage_of_every_model`,
`feedback_benchmark_the_claim_you_can_support`,
`feedback_a_deferrals_reasons_rot_independently`,
`feedback_measure_in_the_running_app`,
`reference_probe_sidecars_with_configured_paths`

## project-affinity-ranking-program

*From the assistant's notes (`project_affinity_ranking_program.md`, type: n/a).*  
*Docking ranking program — route 1 shipped; route 2 ranking MEASURED NULL on a ChEMBL corpus; route 3 spiked and refused at corpus scale on cost; smina spike started 2026-09-12*

**UPDATE 2026-09-12 -- the "blocked on data" section below is SUPERSEDED.**
A within-assay ChEMBL corpus became the oracle (#72, widened #76): route 2's
ranking power is a measured NULL (Vinardo median delta-rho +0.000; ROADMAP
states 77 series on 12 targets, 4998 Vina searches -- DOCKING_RANKING_BENCHMARK
still quotes the pre-widening 56).
Route 3 was spiked (#68/#69: FreeSolv reproduces once GAFF1 is pinned; 251
ns/day OpenCL) and is refused at corpus scale on cost -- one series is a "long
weekend" needing its own pre-registration. DSX is unobtainable; smina is
obtainable on conda-forge win-64. **smina spike DONE 2026-09-12, PR #94 MERGED as
`ce269cf`; branch recorded in docs/BRANCH_CLEANUP.md (`96b35ae`) and
deleted, Alex chose STOP AT FINDINGS** -- not added to the app, `git
diff src/` empty. Do not re-propose shipping smina or a corpus arm without a
new reason. Its three live findings (silent "vinardo" swap on engine
injection; shipped Vinardo != paper's implementation; dkoes is -pK) are in
`docs/ROADMAP.md` "Ranking affinities". Read that for the live state.

Agreed 2026-08-31: plan **multiseed, X-Score, and "maybe OpenMM too"** in
cost order, with a month of Claude Max behind it. The routes and their
evidence live in `docs/ROADMAP.md` under "Ranking affinities"; read that
rather than re-deriving.

#### State as of 2026-09-04

- **Route 1 (replicate ranges): SHIPPED**, PR #65, merged `363ca54`.
- **Route 2 (rescoring): SHIPPED**, PR #66 (`rescoring-axis`) + PR #67
  (`rescoring-benchmark`, stacked on #66). Both open at time of writing.
- **Route 3 (OpenMM/FEP): not started.** It was gated on route 1, which is
  done, so it is unblocked.

#### Route 2 shipped VINARDO, not X-Score, and X-Score is now displaced

X-Score was the roadmap's named candidate and is out on two measured
grounds: [source:quiroga2016] §1 says Vina's function is "inspired by the
X-score function", so it is Vina's own **ancestor** and a weak independent
second opinion; and its public release is v1.2, ANSI C++ "tested on UNIX and
LINUX", behind a licence agreement + registration + server login.

**DSX ([source:neudert2011]) replaces it** — knowledge-based, reports ranking
power directly, and its abstract says freely downloadable from agklebe.de
(a 2011 statement, so availability is a spike). **smina ([source:koes2013])
comes first**, being both an engine and a rescorer and therefore the arm that
tests whether `PoseRescorer` is a real abstraction; it is Linux-first with no
official Windows binary, so that too is a spike.

All four candidate papers are registered and verified from their own first
pages: `koes2013`, `neudert2011`, `mcnutt2021`, `ballester2010`. GNINA's
published gain is recorded as **docking** power (Top1 58→73%), not ranking,
so nobody later cites it as a ranking fix.

#### RANKING POWER IS BLOCKED ON DATA, and re-checking is probably futile

Measured 2026-09-03, six routes to a set with measured affinities, all
closed: the PDBbind hosts (no connection or 403, including the plain-`wget`
CASF-2016 tarball URL published evaluations still use), PDBbind+ (a JS app
behind an account), Binding MOAD (**domain now serves a commercial antibody
catalogue** — the database is gone), Zenodo/figshare (only others'
preprocessed derivatives), and RCSB's own `rcsb_binding_affinity` — which
exists but is sparse and assay-heterogeneous: 0 records for 1HSG/3EML/2RH1
and **104 for 4EY7 spanning Kd 8 nM to IC50 7120 nM for one ligand**.

Do not re-derive this list; it is in `benchmarks/docking/rescore_power.py`'s
docstring. **What would reopen it**: a PDBbind+ account, or a curated
BindingDB/ChEMBL affinity set for library targets — the latter being its own
branch with its own curation and leakage analysis, and producing numbers not
comparable to any published table.

Consequence: the Vinardo-vs-Vina training-overlap question is
`TRAINING_PROVENANCE_UNRESOLVED`, not clean. quiroga2016 §3.1 names the
selection set (122 of 195 PDBbind Core 2013) and Vina was trained on PDBbind
2007; neither code list is obtainable either.

#### What WAS measured, and it is a null

`benchmarks/docking/rescore_power.py` measures **docking power** instead,
which has free ground truth because every catalogued receptor is deposited
with its ligand. Across 8 receptors Vinardo rescoring changes nothing
detectable: 6/8 within 3 Å either way, mean 1.45 vs 1.46 Å. The **ceiling is
8/8**, so both misses are scoring failures rather than search failures.
Reordering: Spearman mean +0.71, range +0.07 to +1.00.

`git diff src/` is empty on that PR, deliberately — see
`feedback_benchmark_the_claim_you_can_support` and the base-bias precedent.

#### The honest ceiling has not moved

CASF-2016 puts even top-ranked functions near 0.6 correlation, so routes 2
and 3 help a SERIES while route 1's "these overlap, do not rank them" is
likely to remain the right answer for three fentanyl analogues one CH2 apart.

Related: `project_repo_and_tracking`, `reference_alex_has_paywalled_papers`,
`feedback_ask_leakage_of_every_model`

## project-vdw-radii-program

*From the assistant's notes (`project_vdw_radii_program.md`, type: n/a).*  
*van der Waals radii decisions 2026-10-11/12 (all merged): Bondi's own radii for steric, surface, volume, projections, Geometry; RDKit's table is Batsanov's; H stays 1.20; docking keeps its own table; what is open*

Full record: `docs/VDW_RADII_ASSESSMENT.md` (every number measured; oracle table, Harding/Zhao/Gavezzotti/Alvarez rows, fluorine and metal sections). Decisions, all merged (#288, #290, #292, #299):

- RDKit's `GetRvdw` table equals Batsanov 2001 Table 9 (65/65 elements), NOT Bondi's; the app had labelled it Bondi's. One table now: `chem/vdw_radii.py` = Bondi 1964 Tables I/XIV plus Mantina 2009 for the sixteen elements he gave none for (`bondi_radius`, `radius_source`, `RADII_LABEL`).
- Steric = steric-v2, surface = surface-v3, Geometry = geometry-v3 (old results kept and labelled; old Geometry text "Bondi van der Waals radii." replaced at load by a reader's note, numbers untouched). Own volume routine `sasa.enclosed_volume` (within 0.25% of a 0.03 A grid; RDKit's DCLV takes no radii), `sasa.grid_volume` as the independent check.
- Hydrogen stays 1.20 for areas and volumes (1.10 errs 7.7% on Zhao's 46-molecule oracle; Bondi 1.84%, RDKit 2.12%, difference only in halides). Docking keeps its own contact table (H 1.10). The periodic-table dialog prints "van der Waals 1.7 A (Bondi 1964)".
- Open: metal radii untouched (Fe 1.56 untraced; Alvarez 2013 gives Fe 2.44, Zn 2.39, Mg 2.51, Ca 2.62, Na 2.50, K 2.73 but they are contact-peak edges, not cutoffs); Chernyshov 2020 says sums of tabulated radii undershoot the energy minimum by 0.3-0.4 A and radii are not meaningful for d/f elements.

**Why it matters later:** anything quoting "Bondi" must say whose table; a radii change is a method-version bump with the old result kept. See `project_metal_bond_windows_followup`, `reference_shannon_radii_column_trap`.

## project-interaction-analysis-v2

*From the assistant's notes (`project_interaction_analysis_v2.md`, type: n/a).*  
*Interaction Analysis method interactions-v2 (2026-10-11) - five rules fixed, what stays a limit, what was stacked on, and the open docking-side twin*

`interaction_analysis` moved to method `interactions-v2` on 2026-10-11 (legacy label `legacy-contact-rules-v1`): charge clusters that sum to zero are not ion sites (nitrate keeps its O-), a hydrogen bond needs a hydrogen on one atom, rings need >=3 bonds between nearest atoms to stack, divalent sulfur is a metal donor (valence <= 2, not sulfone/sulfoxide), hydrophobic contact floor = sum of vdW radii (3.4 for C-C). Tests: `tests/test_interaction_analysis_rules.py` (each case measures its own precondition from coordinates; 13 mutations all caught).

**Why it was stacked:** the explainer doc `docs/explainers/interaction_dynamics.md` lived only on `claude/explainers-interaction-md-align` (a long unmerged stack: radii research etc.), so the work branch was fast-forwarded onto it. When that merges (squash), rebase this on master.

**Still limits (documented, deliberately not fixed):** salt written as separate fragments is embedded on top of itself; tBu contacts 3.56-4.49 A are beyond the floor; no H-bond angle.

**The task text was wrong about one thing:** the "cis-1,3-di-tert-butylcyclohexane, nine contacts" figure. The meso (S,R) cis isomer gives 6-7 contacts per conformer; nine appears only for the trans (S,S) isomer. The 3.56-4.49 range reproduced for both. Check CIP before naming cis/trans.

**The docking twin is FIXED** (#293 merged: a nitro group is not an ion in `pose_analysis` either), and the separate-fragment metal clash (#295).

**UPDATE 2026-10-12 — method is now `interactions-v5`** (v3 = per-metal bond windows #299; v4 = fluorine metal-donor restriction #301; v5 = C-F and B-F not an H-bond acceptor, Mg removed as a donor of a carbon-bound fluorine, a fluoride ion keeps every metal, #302). Each older result is kept and labelled in `SUPERSEDED_METHOD_VERSIONS`. Details and open edges: `project_fluorine_donor_acceptor_prs`, `project_metal_bond_windows_followup`.

How to apply: before touching contact rules, note `pose_analysis` constants are shared with docking, so intramolecular-only changes belong in `interaction_analysis`. See `reference_run_tests_with_python_m_pytest` and `reference_bash_tool_heredoc_quoting` (an apostrophe in a Bash heredoc broke a patch script again; use the Write tool).

## project-metal-bond-windows-followup

*From the assistant's notes (`project_metal_bond_windows_followup.md`, type: n/a).*  
*DONE and merged: metal-bond-as-clash fix (#294), per-metal bond windows (#299, interactions-v3), fluorine refinements (#301/#302); the sourced targets and what is still open*

History: #294 stopped `analyze_pose` reporting a coordinated metal as a clash with ONE 1.8-2.8 A window. Alex agreed to per-metal windows as a follow-up; that is **#299 (merged 2026-10-11)**: `pose_analysis.metal_bond_window(metal, donor)` from `METAL_DONOR_TARGETS` (Harding 2006 Table 4; nickel from Zheng 2017 Table 3; N/S for Mg, Ca, Na, K are Harding's marked estimates, 2001/2002), window = target + 0.5 A (+ 0.75 for Na, K), floor target - 0.5 but never under 1.8, Na/K secondary sphere (+0.95) exempt from the clash test; one predicate (`is_metal_bond`, `is_metal_contact`) shared by the docking clash test, the detector and `interaction_analysis`. `INTERACTION_METHOD` went v2 -> v3; a v2 result is kept and labelled. Fluorine was refined afterwards: see `project_fluorine_donor_acceptor_prs`.

**Still open / deliberate limits:** the metal vdW radii are untouched (Fe 1.56 is traced to no published set; Co, Mn, Cu, Ni take the 1.70 default, so a genuine 2.709 A Cu(II)...F contact reads as a clash by 0.06 A); a saved docking result keeps the clash and H-bond lists it was analysed with (the result-store method versions do not reach docking poses); a receptor's fluorine arrives without bonds and is read as a fluoride ion.

Related: `project_interaction_analysis_v2`, `project_vdw_radii_program`.

## fluorine-donor-acceptor-prs

*From the assistant's notes (`project_fluorine_donor_acceptor_prs.md`, type: n/a).*  
*2026-10-12 fluorine work, ALL MERGED (#301, #302) — F metal donor rule (C/B-bound F: Na/K/Ca only; fluoride ion: every metal), C-F/B-F not an H-bond acceptor, PDB survey; what is still open*

Both merged 2026-10-12: **#301** (`bd0967fd`, F donor to Na/K/Ca/Mg only, v4) and **#302** (`f34d7524`: C-F and B-F not an H-bond acceptor; Mg removed as a donor of a carbon-bound F; a fluoride ion keeps the oxygen window for every metal via `pose_analysis.metal_donor_symbol` -> "CF" key; Interaction Analysis `interactions-v5`; PDB survey scripts in `benchmarks/fluorine_pdb_survey/`).

Sources registered (all Crossref-verified): plenio1997, plenio2004, murrayrust1983, dunitz1997, dunitz2004 (shipped); bakewell2016, maverick2002, ferro2018, ielo2019, kulawiec1990, willrett2025 (reference_only). Brese & O'Keeffe 1991 read but not registered/used.

**Why Cu and Mg are out:** Mg...F(C) is 3.20-3.49 A everywhere measured (Bakewell SI CIF, computed by me; PDB 3.29+) against a window ending 2.76. Cu: the two PDB tyrosinase hits (6QXD, 6EI4) have poorly fitted ligands (RSCC 0.69-0.79 vs 0.99 for the Cu ions), authors describe a substrate-mimic placement at 1.9 A, while every measured Cu(II)...F(CF3) contact is 2.71-3.11 A (Maverick 2002, recomputed from its CIF). Alex wanted to be "110% sure"; the evidence was gathered rather than asserted.
**Open edges:** Cu radius is the 1.70 default (not in the table), so a genuine 2.709 A Cu(II)...F contact reads as a clash by 0.06 A; receptor F arrives bondless and is read as fluoride; saved docking results keep old H-bond lists; H-Bond Acceptors property follows RDKit (F counted). Harding 2006 SI is the metal-site list (not otherwise used).
**Gotchas:** a web search summary is not a read; Europe PMC pdf URLs return HTML to curl (ask Alex); Crossref caught my wrong Bakewell authors/pages; Alex's file named *_si.pdf was once the wrong paper's SI; mmCIF parsing for PDB surveys needs the tokens regex in the survey scripts. See `feedback_the_fields_nobody_can_check`.

**Follow-up 2026-10-12:** PR #304 (branch claude/lesson-fluorine-pdb-survey) adds the LESSONS.md entry "TWO CLOSE COPPER CONTACTS LOOKED LIKE A COUNTEREXAMPLE..." plus the removed `METAL_COORDINATION_CUTOFF` dropped from `tools/constant_docs.py` and the debt ratchet. `tools/constant_docs.py --record` reports 397 constants vs 406 in the fixture (about 9 stale entries) but regenerating rewrites the whole file, so that cleanup is separate.

## project-mp-bp-benchmark

*From the assistant's notes (`project_mp_bp_benchmark.md`, type: n/a).*  
*Melting/boiling-point benchmark (preregistered): corpus #462, Marrero-Gani fragmenter #463, holdout scored ONCE 2026-10-25 in #464, no method passed; don't re-run the holdout*

Preregistered melting-point / normal-boiling-point benchmark in `benchmarks/mp_bp/` (PREREGISTRATION.md frozen via #461; Amendment 1 = corpus conventions, Amendment 2 = scorer choices). Corpus from Lange 15th ed. Table 1.15 + CRC 97th ed., built by `mpbp_build.py` OUTSIDE Git (`D:/_scratch/mp_bp_corpus`; the folder beside the PDF library was not writable from a session). #462 corpus, #463 Marrero-Gani 182-group fragmenter, #464 scorer + result (holdout scored once, lock in `benchmarks/mp_bp/results/holdout_scored.lock`).

**Result:** no method passed. Candidate C (Joback's 41 groups refit on development) FAILS on point MAE alone (Tb 20.8 K vs 19.35; Tm 38.6 K vs 33.9). Joback and Marrero-Gani are NOT EVALUABLE (fit populations unlisted -> leakage unknown); Marrero-Gani Tm (36.4 K vs 37.35) would meet all numeric criteria, exploratory only. Joback Tf as a Tm proxy runs +38 K and is never gate-eligible.

**Why:** the handbooks contain printed errors (Lange prints -100.7 for a compound melting at +100.7, a shifted row, etc.), found by comparing the two books; the cross-source `agree` subset is the label-quality check.

**How to apply:** the holdout is spent for this design. A new claim needs a NEW preregistered evaluation (new candidate version, untouched data), never a re-run, a moved ceiling, or a relaxed threshold. Phase B (energetic materials) starts only after this verdict (done) and has its own preregistration. Related: `feedback-heldout-experiment-discipline`, `reference-langes-handbook`.

## project-phase-b-decisions

*From the assistant's notes (`project_phase_b_decisions.md`, type: n/a).*  
*Phase B (energetic materials) owner decisions made 2026-10-26 in chat, before the preregistration is amended and frozen; COD is the label source for crystal density*

Phase B preregistration draft is merged (#469); the COD counts are merged (#470). Alex answered the section 14 decisions in chat on 2026-10-26. **The COD population decisions (D1-D7, D9-D11) are still NOT written into the preregistration and it is NOT frozen.** D8 and the PETN conditions WERE amended in on 2026-10-27 by PR #472 — see `project-petn-evidence-inventory` for the exact wording (R1's measured-legs rule, R2 split into an unchanged gate plus a descriptive pilot, and a hybrid-observation rule added to 8.2).

**Answered (all = my recommendation unless noted):**
- D6/D9 population: **COD compounds carrying a nitrate ester, nitramine, C-nitro or azide group are the PRIMARY population for crystal density**; the books' known energetic materials (RDX, TNT, PETN...) are a side stratum. Claim is stated as "nitro/azide-type organic crystals", never "all energetic materials". A ring with 2+ N is NOT an explosophore.
- D1 first property: crystal density; enthalpy second (described only, ~112 values, COD has none), melting described, decomposition evidence only (D12 accepted).
- D2 gate form: BOTH replication (1.5x / 2.0x of the paper's error) AND an absolute usefulness bar.
- D3 numbers kept: 0.04 / 0.05 g/cm3; 20% / 10% improvement over baseline; 70% coverage.
- D4 min n: 60/20/20 split, minimum 60 paired held-out entities (COD gives thousands, so the floor only bites on the book stratum).
- D5 labels: quality filter (R <= 0.07, single component, 273-303 K), repeats -> median, repeats disagreeing > 0.03 g/cm3 unresolved; the "two independent determinations agree" subset is a side check.
- D7: famous compounds (RDX, HMX, TNT, PETN) kept OUT of the sealed test set (they go to development; still reported in the side stratum).
- D11: Candidate D = one simple density refit on development rows, 10 rows per fitted parameter, named as this project's own.
- D10 temperature: main test is 273-303 K only, NO conversion. Low-temperature (~100 K) structures: a preregistered correction sub-study builds the correction on development matched pairs and checks it on held-out pairs; low-T joins a SECONDARY analysis only if the correction's measured error is <= 0.015 g/cm3. Measured on 3,926 COD pairs (matched on formula+space group+Z): low-T density ~2.8% higher; one fixed ratio leaves ~0.027 g/cm3 median error (crude matching; floor expected ~0.01-0.015). Improve by matching on unit-cell volume, fitting expansion vs temperature gap, fitting on development pairs only.
- D9 CSD: Alex has no CSD access and does not expect to; proceed without. CSD-trained density formulas stay unevaluable; testable candidates: Tarver 1979, Keshavarz papers, a Kim-type method, Candidate D.
- D8 PETN / D13 compute budget / D14 LMU: accepted as drafted for now. **Alex is NOT convinced PETN is a lost cause** and wants a separate spawned task to dig for more PETN / nitrate-ester evidence (COD has only 32 nitrate-ester entries, 28 single-component, 24 distinct formulas, so the nitrate-ester family is where PETN's evidence is thin). He did find bromine papers via ChatGPT after long searching, so keep pushing sources.

**Why:** Phase A's lessons (leakage unknown, handbook printed errors) drove every one of these; the COD census showed density labels are plentiful.
**How to apply:** next step is an amendment PR to benchmarks/energetics_props/PREREGISTRATION.md recording the ones still outstanding (the COD population and the correction sub-study), then freeze, then build the corpus. The PETN hunt D8 asked for is done (`project-petn-evidence-inventory`): PETN is not a lost cause, but R1 still needs a settled pentaerythritol sublimation value. Never score before the freeze. Related: `project-mp-bp-benchmark`, `feedback-heldout-experiment-discipline`.

**State on 2026-10-27 (end of day), density arm:** COD builder merged (#479), correction-study code (#482), Amendment 2 (#483: 35 held-out entities, pairs widened to every organic N-containing crystal, explosophore pairs flagged never gating). **PR #487 (MERGED 2026-10-27 22:05Z): Amendment 3 / section 17** closes 15.9 (d) and (e): Tarver 1979 (188) and Keshavarz 2009 x2 (113, 59) transcribed from images and checked three ways (own arithmetic; printed correlation; 80 of 84 shared compounds agree with Keshavarz's copy of Tarver's column); full tables PRIVATE (`...private notes/energetics-phase-b/density-candidates/`), only keys/counts/hashes committed; 6 of 256 keys are in COD (5 held out, removed per model); Candidate D = 8 elements + 10 groups, WLS on volume, ridge on groups only, >= 180 dev rows. Findings: Tarver furan volume is half its group sum; Keshavarz arene CNG coefficient is -0.0751 not the printed -0.751; Keshavarz reports rms%, so no 1.5x replication criterion for D4. Remaining before the density freeze: owner approval of Amendments 2 and 3, and the enthalpy arm's D8/R2 amendment (another session).
**Literature record (2026-10-28):** PR #493 (docs only: LITERATURE_LOG section, literature.toml notes and three not_held leads from Keshavarz's reference list: the 2007 nitramine and nitroaromatic density papers and Nielsen 1973 NWC TP 5452). The five D4b structures that could not be resolved (aza-TACOT, azo-bis(furoxan), three benzobisfuroxan amines) need the papers that first report those compounds; listed in WANTED_LITERATURE.md. The transcriptions and their scripts are in `private notes/energetics-phase-b/density-candidates/`.
**Traps from this session:** the Agent tool is blocked by a hook that insists on tokensave (do the transcription yourself); a Bash heredoc with apostrophes sometimes dies with "unexpected EOF" (write the file with the Write tool, then run it); `python -I` ignores PYTHONIOENCODING (use `-X utf8`); Bash cannot mkdir under Documents but PowerShell can; a new test file needs `tools/suite_shards.py --pin-new` on the CURRENT master (the pins file changed under me when #485 merged, so move work to a fresh branch from origin/master and re-pin); tables in these 1979/2009 PDFs are rotated scans or drawn structures, so render at 200 dpi and rotate, and use the printed correlation as a formula check on every structure read from a drawing.

## project-petn-evidence-inventory

*From the assistant's notes (`project_petn_evidence_inventory.md`, type: n/a).*  
*PR #472, the PETN / nitrate-ester / nitramine evidence inventory: what it found, the owner decisions it wrote into the Phase B preregistration, and what is still open*

Spawned 2026-10-26 from the Phase B work (`project-phase-b-decisions`) to dig for PETN and nitrate-ester evidence. Branch `claude/fervent-rhodes-5823fa`, PR **#472**, **137 rows** in `benchmarks/energetics_props/PETN_EVIDENCE.md` / `.json`. It is an **inventory only**: no corpus, no scoring, nothing frozen. The spawning session said keep it unmerged; **Alex overrode that on 2026-10-27 and told me to merge it.**

**Owner decisions it wrote into `PREREGISTRATION.md` (2026-10-26/27):**

- **D8 / R1**: a gas-phase enthalpy built from a measured condensed value plus a measured sublimation enthalpy counts as `measured`, **if each leg is itself verified under 8.2**. A calculated gas leg never does. R1 is still NOT met: pentaerythritol is the only candidate and its sublimation is a 30 kJ/mol spread (131.4 Nitta, 143.9 Bradley and Cotson, 161.0 Barone) over different temperature ranges, so it is `disagree` and not approvable as a calibrant yet.
- **R2 is now two tiers.** R2-gate is unchanged (at least 30 paired verified holdout nitramines, so about 150 verified entities; stays `NOT EVALUABLE`, never relaxed). **R2-pilot** is new and descriptive only: one row per verified nitramine with H4's error and leave-one-out error, a bootstrap interval for that n, the minimum detectable effect, and a fixed sentence saying it is not a pass and supports no product decision. Run once after the freeze, under a lock.
- **8.2 hybrids**: a *calculated* gas enthalpy plus a *measured* sublimation enthalpy is an observation with its own lineage, stored `computed` and flagged `hybrid`. It may corroborate a measured value across method classes, but never verifies alone, and cannot mark a verified entity `disagree` (Muravyev's own stated inaccuracy is up to 25 kJ/mol, wider than the 10 kJ/mol tolerance). Every report counting one states that accuracy figure.

**What the hunt found:**

- **Nitroisobutylglycerol trinitrate is the live question.** Two combustion measurements 8 per cent apart: Medard and Thomas 1949 give Qc(v) 530.5 kcal/mol, which converts to **-226.8 kJ/mol** (exactly NIST's -226, so that value is correctly derived and not a transcription slip), while the Army Encyclopedia vol. 8 prints 1707 kcal/kg, which converts to **-402.9** and matches Rzhevskiy 2023's computed -402 to 1 kJ/mol. Marked `disagree`; PATR 1125 or a third measurement would settle it. See `reference-thermochemical-lineage-traps`.
- **Nitrourea** is now held in three places and they agree within 2 kJ/mol (NIST -280.8, Meyer -282.5, Army Encyclopedia -281.2) — all one root.
- **Muravyev 2021** gives a measured-sublimation plus W1-F12 solid enthalpy for ten nitramines and nitramides: seven within 10 kJ/mol of the nearest experimental value, three not (TEX 85, DATN 66, BC-HMX 22). Useful for the R2 pilot, nowhere near enough for the gate.
- Sources mined whole: Meyer 2016 (214 entries), Muravyev 2021 and its SI, Rzhevskiy 2023 and its SI, Cox and Pilcher in part, and the Army Encyclopedia's relevant entries.

**Still open (none of it blocks anything):** PATR 1125 (Aaronson 1941, "Study of Explosives Derived from Nitroparaffins") is not online anywhere; Medard and Thomas *Mem. Poudres* **31** (1949) 196 and the Chemical Abstracts entries CA 46, 11684 and 11685; Lobanov and Karmanova 1971; Tavernier and Lamouroux; the Fraunhofer ICT database request. A modern measured gas or sublimation value for a four-arm calibrant, and an independent NIBTN measurement, went to a separate session Alex started on 2026-10-27.

**2026-10-27, the calibrant/NIBTN search session — owner decisions, all in `prereg-amendment-drafts/R2_two_tier_amendment_DRAFT.md` (last sections). APPLIED 2026-10-28 as Amendment 4 (section 18) on branch `claude/prereg-amendment-4-stohmann-historical`, PR #497 MERGED 2026-10-29 as cf1b4c3e (commits also add evidence rows B08-B10 to PETN_EVIDENCE); the calorie uncertainty (0.2%) is stated beside a historical comparison and does NOT widen the 10 kJ/mol tolerance (Alex chose strict), and Stohmann's two earlier papers + the 1889 method paper were read and define no calorie:** Stohmann and Langbein 1892 (*J. prakt. Chem.* [2] 45, pp. 328-329, 338; archive.org `sim_journal-fuer-praktische-chemie-1834_1892_45`) is a second, independent root for pentaerythritol's SOLID enthalpy (combustion 661.4 kcal/mol, 5.4 kJ/mol from Medard-Thomas); it does not touch the sublimation leg, so R1 stays unmet. Decided: compare on the combustion enthalpy; Stohmann's combustion row is `measured`, its formation row `derived_from_measured` by the study's own fixed step (a one-line §3.1 wording change); `historical` = no Washburn correction or undefined calorie, by property not date (both pentaerythritol roots carry it); fixed auxiliary values frozen as CODATA, dfH(CO2,g) -393.51 and dfH(H2O,l) -285.830 kJ/mol, 1 kcal = 4.184 kJ. Domalski 1972/1993 reprint Medard-Thomas (one root); neither holds NIBTN. The NIBTN disagreement is untouched.

**Where the working notes live:** `D:/Xaero Stuff/Documents/OpenChem Studio private notes/energetics-phase-b/` — `literature-ledger.md` (which source answers which question; **start here**), `library-additions.md` (what every fetched file really contains, wrong fetches included), `prereg-amendment-drafts/`, `ocr-extracts/`, and `petn-evidence/doi_links.md` (the 41 DOIs taken out of the repo). All indexed in that folder's `INDEX.md`.

**2026-10-29, computed arbiter (branch `claude/phase-b-computed-arbiter`, local, not pushed):** plan + pure core + ORCA driver committed (`benchmarks/energetics_props/arbiter/`); isodesmic schemes, r2SCAN-3c geometries, DLPNO-CCSD(T)/def2-TZVPP; validation set read BEFORE targets (`report` without `--targets`); result is `computed`, never satisfies R1. Scratch in `D:/OpenChemStudio-scratch/arbiter`.

**2026-10-29, ChatGPT leads checked (branch `claude/phase-b-evidence-corrections`, worktree `.claude/worktrees/phase-b-evidence-corrections`, commit 7175c782, NOT pushed, no PR):** rows G65-G69. No third measured NIBTN enthalpy: Dong 2017's Table 3 copies 2205.2 (Zeman 1995 = Medard-Thomas via NIST), RU2316538C1 states -54 kcal/mol unsourced, AMCP 706-177's entry has no enthalpy. Pentaerythritol's four sublimation values (131.4, 143.9, 161.0, 163.0) are THREE measurements (Nitta 1951, Bradley-Cotson 1953, Barone 1990): Font and Muntasell 1994 re-report Nitta (their 131.3), Jones 1960 compiles. Unread: Font and Muntasell 1995 (B03's 134 and 96 rows). ChatGPT's DOIs all resolved, but treat its attributions as unverified until read. Lebedev et al. 1970 (Termokhimiya nitrosoedinenii) is the likeliest remaining newer NIBTN source. In a worktree-isolated session the shell refuses computed interpreter paths: `uv sync` in the new worktree, then `uv run --no-sync python -m pytest`.

## reference-thermochemical-lineage-traps

*From the assistant's notes (`reference_thermochemical_lineage_traps.md`, type: n/a).*  
*Traps when tracing old thermochemical values (compilation dates, one root behind many books, OCR negatives, printed unit errors) and the routes that work*

Learned across the PETN / nitrate-ester evidence hunt, 2026-10-26/27 (`project-petn-evidence-inventory`). The long-form write-up is in `docs/LESSONS.md` under **"THE SAME ENTHALPY IN FIVE BOOKS WAS ONE 1949 MEASUREMENT, AND THE NEWEST BOOK HELD THE OLDEST DATA"**.

- **A compilation's date is not its data's date.** Meyer, Koehler and Homburg 2016 names Medard's 1954 tables and the Fraunhofer ICT database as its sources for formation enthalpies. Koch 2019 and Oxley 2012 likewise compile, and Koch's attributions do not match the papers he cites. Four books agreeing to the last digit turned out to be one 1949 measurement.
- **A negative from an OCR'd scan is not an absence.** An earlier pass recorded the Army Encyclopedia as lacking two compounds; it holds both, in volumes 2, 8 and 10. Search several spellings and abbreviations, and check the index volume.
- **Two entries in one reference work can disagree** — by 176 kJ/mol here — with neither cross-referencing the other.
- **Recompute a printed unit against a neighbour you already know.** Volume 8 printed "1707 kcal/mole" beside "1595 kcal/mole for NG in the same bomb"; nitroglycerin's heat of combustion is about 1604 kcal/**kg**, so both are per kg, and the nitroglycerin figure landing within 0.6 per cent is what showed that bomb was sound.
- **Check the citation itself.** Two misprints found: the Medard and Thomas paper is *Mem. Poudres* 31 (1949) 196, not 29 (1949) 173-195; Medard's *Tables thermochimiques* is volume 28 of *Mem. de l'artillerie francaise* (confirmed from that journal's own index volume), not the volume 23 that one Meyer entry prints.
- **Chemical Abstracts numbers are a cheaper route than an obscure journal** — the Encyclopedia prints one beside each *Mem. Poudres* reference, e.g. CA 46, 11684.
- **archive.org holds more old journals than it looks.** The 1912 volume of *Z. ges. Schiess- und Sprengstoffwesen* is free and complete (identifier `zeitschrift-fur-das-gesamte-schiess-und-sprengstoffwesen-1912`, most years 1907-1923 present), and DTIC reports turn up under `DTIC_AD...` identifiers. Pre-1945 Picatinny reports such as PATR 1125 are below DTIC's digitised floor and are not online at all.
- **Old papers have no DOI and Crossref invents matches.** Always check the title Crossref returns before recording it.

Related: `feedback-prefers-newer-sources`, `feedback-use-book-facts`, `reference-reading-pdfs-in-this-project`, `reference-alex-has-paywalled-papers`.

## project-geometry-derived-scores

*From the assistant's notes (`project_geometry_derived_scores.md`, type: n/a).*  
*Derived scores over the ten shape descriptors (PR #364 MERGED 2026-10-17 as 73e10177, branch claude/geometry-derived-scores): what it does, the four-units finding, Alex's three answers, traps hit*

Built after the three ORCA-conformer PRs (`project-orca-conformer-in-its-slot`), as `docs/DERIVED_SCORES_DESIGN.md` section 11 (#356) decided: a score reads the conformer every calculation uses (`canonical_conformer`), and the first outputs are the ten shape descriptors only.

**What it is:** `ApprovedOutput.input` (`drawing` default, `geometry` for the ten); `score_value.read_output` reads only results of the entry's input; a geometry result is current only for the conformer used now (`classify_results` already compared per input), else "calculated for an earlier geometry of this molecule"; no conformer = "it needs a conformer"; the conformer is named in the evidence (a geometry run now stamps `geometry_provenance` on its descriptors, the batch stamps its table cells).

**THE FINDING NOBODY HAD MADE:** four of the ten (PMI1-3 and the inertial shape factor) declared NO unit but are amu*A^2 and 1/(amu*A^2) (measured: a hand-built inertia tensor reproduces PMI1-3 to 6 digits; doubling lengths x4 and x1/4). Alex chose (2026-10-17): declare the true units and approve all ten (not the six-only option). New unit symbol `amu`. A bare number in a formula takes the unit of what it is added to, so the unit check bites on moment + ratio, NOT on `pmi1 + 1`. Definitions measured by reproducing RDKit: asphericity = 0.5*sum((li-lj)^2)/(sum l)^2 of the MASS-weighted gyration tensor (my first guess from the inertia moments was wrong); PBF = mean |distance| to the best-fit plane, unweighted, H included; spherocity = 3*lmin/sum of the UNweighted coordinate covariance.

**Alex's other answers:** old saved projects: drop the unit-less copies on open and measure again (`DescriptorService.is_obsolete_result`, via `set_obsolete_check`); the assistant's `list_score_outputs` gets its own 16000-char budget (`SCORE_OUTPUTS_BUDGET`) because 51 rows passed the general 12000 and the last rows were silently dropped (a test caught it).

**Traps hit:** the generated `docs/CALCULATOR_REFERENCE.md` lists descriptor units (regenerate with `tools/build_calculator_reference.py`; the guard is test_calculator_reference); docs guard `test_every_file_a_doc_cites_still_exists` counts TRACKED files (`git add` a new drive script first); the existing table-vs-Results parity test already loops over every APPROVED output, so it covered the ten for free; a drive script's guess at text ("MMFF94 energy") was wrong, the stored label is `MMFF94/UFF`; the controls overwrite a drive's screenshots, so rerun the passing script last.

**Evidence at build:** 38 tests in tests/test_score_geometry.py + 3 in test_main_window_scores.py; 27 mutants all caught (one survivor on the first run: the assistant's turn never passed its conformer count); real-ORCA drive `benchmarks/visual/score_geometry.json` PASS (3.623 -> 3.691 A after the ORCA geometry -> 3.623 after Undo) with two failing controls; `tools/sweep_score_outputs.py --check`: 51 of 51 hold.

#### Index line, as it stood before 2026-10-18 (moved from MEMORY.md, which has a size limit)

- [Geometry derived scores](project_geometry_derived_scores.md) — ten shape descriptors readable by a score (conformer every calculation uses); four had NO unit though not dimensionless (amu*A^2), Alex chose declare-and-approve-all; old projects drop-and-remeasure; own 16000 reply budget for list_score_outputs

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [Geometry derived scores](project_geometry_derived_scores.md) — ten shape descriptors readable by a score; four had NO unit (amu*A^2), Alex chose declare-and-approve-all; own 16000 reply budget for list_score_outputs

## project-more-3d-derived-scores

*From the assistant's notes (`project_more_3d_derived_scores.md`, type: n/a).*  
*Second round of geometry derived scores (2026-10-17, branch claude/more-3d-derived-scores, PR #367 MERGED 2026-10-18 as 38771fe1): Alex's decisions, the measurements behind them, and the CORRECTION about the ten shape descriptors*

Follow-up to `project-geometry-derived-scores` after Alex said "More 3D numbers in scores" (2026-10-17). What the census sweep offered beyond the ten shape descriptors: 12 Geometry Analysis numbers, HOMA/Bird (ids name the ring type), 96 torsions (ids name atoms). Dipole and surface areas are NOT typed numbers (rounded text lines), so each would be its own PR that types them first.

**Alex's decisions (all asked in chat before any code):**
1. **Eight sizes from Geometry Analysis, PR A:** max and mean radius from the centroid plus the six projection numbers (min/max area, min/max enclosing-circle radius, size along each view). NOT min radius (0 for ammonium nitrate and sodium acetate, 0.019 A for BF3; moves most between conformers: butanol 0.54-1.06 A) and NOT the three force-field energies (no meaning between molecules: MMFF94 nitroguanidine -152 vs NDMA +4, same atom count; after a real ORCA HF STO-3G optimisation of butanol MMFF94 -1.85 -> -0.15, UFF 5.10 -> 6.61, Dreiding 8.07 -> 7.07, so the three scales disagree in direction; 3/29 rows have no MMFF94).
2. **A structure of more than one fragment: a score refuses the geometry number. Alex chose "every geometry number, the ten included" ON A WRONG PREMISE OF MINE:** I measured RDKit on the whole salt, but the app computes the ten always-on shape descriptors on the ChEMBL PARENT compound (`chem/components.py`, `_DESCRIPTOR_PARENT_SCOPE`; sodium acetate is refused by the producer "Mixture: no single parent"; the provider's rg of metformin HCl 2.272143 equals its metformin fragment's, whole salt 2.014). Refusing the ten would reject a parent's number, so the BUILT rule is the EIGHT's only (`ApprovedOutput.whole_structure`; Geometry Analysis scope is WHOLE_STRUCTURE). I reported the correction and Alex confirmed 'the eight only' (and the 20,000-character list budget) on 2026-10-17. The metformin "543-658 over ten embeddings" I quoted was metformin's own conformational flexibility, not a fragment offset.
3. **HOMA only, from an ORCA-optimised geometry only, its OWN PR after the sizes (PR B):** highest and lowest HOMA over a molecule's rings, refused on a force-field conformer ("needs a measured geometry"). Bird and torsions stay out. Why: naphthalene HOMA is 0.942 per ring on the MMFF94 conformer and 0.66 on an ORCA HF STO-3G one (the force field assigns aromatic bond lengths from the drawing); Bird gives cyclohexane 95.8-100 against benzene 100; the HOMA producer's own docstring says "per ring, never per molecule", and the torsion table's text says one conformer is not a scan.

**Rule that follows from decision 1 of the first round (not asked):** only a Geometry Analysis result measured on the stored conformer as it is counts (`input_geometry == measured_geometry`, and `radius_scale == 1` for the six projections): `conformer_policy=always` measured a different geometry (octanoic acid max radius 4.914 -> 6.178), `optimise_projection` relaxes a copy (4.500; the radii use it too), `radius_scale` rescales the projections only. Energy unit, decimals, conformer count and optimisation limit do not change the eight.

**Things I got wrong on the way (so I do not repeat them):** (a) the result store keeps ONE result per (result id, input, fingerprint, method), NOT per settings, so a later Geometry Analysis run with other settings REPLACES the default one: my "default run beside a scaled one" scenario never happens in the app (the real-window drive showed it), the cure is to run again with defaults; (b) the label rule `name_collision` refuses a label equal to, containing or contained by an output name, so new output names make labels like "Area" refused (a test used "Area"); (c) `entries` in the `score_results` drive expect counts ALL scores in the reader, not the one `which` picks; (d) a simplex search for the smallest enclosing circle stalled short of the minimum (benzoic acid), use SLSQP on the epigraph form; (e) `list_score_outputs` took 14,249 of 16,000 chars at 59 outputs (the guard stops at 85%), budget now 20,000.

**Evidence at build:** `tests/test_score_geometry_sizes.py` (209) + 2 window tests; 21 mutants all caught; `benchmarks/visual/score_geometry_sizes.json` VERDICT PASS 16/16 with a failing control (3 of 16); sweep `--check` 59 of 59 hold.

**State 2026-10-17:** PR #367 opened (auto-fix on, 6 checks pending when opened; local full suite green: four shards 17,007 passed, shard 2 crashed once on the known WebGL access violation and passed on rerun, naming files 4,197). Next in this thread: PR B (HOMA only, from an ORCA geometry only: needs a 'needs a measured geometry' refusal, highest and lowest HOMA over rings typed in the HOMA report); dipole moment and surface areas would each be a PR that first types their values.

**MERGED:** #367 squash-merged as `38771fe14b74` on 2026-10-18 after Alex's 'merge if green' (four shards and gating benchmarks passed; the non-blocking linux job failed as usual). PR B (HOMA only, from an ORCA geometry only) is next and needs his go to start.

**PR B (HOMA's two extremes), PR #368 MERGED 2026-10-18 as 7c311a91 (Alex's 'merge if green'; four shards and gating benchmarks passed, the non-blocking linux job failed as usual) (local full suite green: four shards 17,057 passed, naming 4,229; shard 1 failed once on the constant-docs guard, three constants needed their own `#:`, fixed and rerun):** `Highest HOMA of any ring` / `Lowest HOMA of any ring` typed facts at the end of the HOMA report (labels are part of the output ids; present only when every ring has a value), approved with `ApprovedOutput.needs_quantum_geometry`; the reader declines unless the conformer's method is quantum (`input_conformer_method` stamped by `geometry_provenance` and by the batch on calculator cells), evidence names the level (`input_level_of_theory`, from the run's recorded method_basis). Alex chose ANY ORCA LEVEL, NAMED (not a minimal-basis refusal). Measured with real ORCA: naphthalene per ring MMFF94 0.942, HF/STO-3G 0.660, HF/def2-SVP 0.768, B3LYP/def2-SVP 0.739; azulene [0.220, 0.136] -> [0.498, 0.254]; benzene 0.988 -> 0.968; pyridine 0.990 -> 0.981. Evidence: 46 tests + 1 window test, 19 mutants all caught, drive `benchmarks/visual/score_homa.json` PASS 12/12 (indole HF STO-3G: ceiling 0.9229, floor 0.5255) with a failing control (2 of 12); sweep 61 of 61. ORCA runs fast for small molecules (indole HF STO-3G opt about 1 minute); parallel jobs appending to one file overwrite each other on Windows, so read the job.xyz files instead.

**Both PRs of this thread are MERGED:** #367 (eight sizes, 38771fe1) and #368 (HOMA extremes, 7c311a91). Open directions, each needing Alex's go: dipole moment and surface areas (producers return rounded text, so each first types its values; questions would be the charge model for the dipole, the probe radius and microspecies option for the surface), ORCA reactivity (Phase 3), the synthesis helper (Phase 4), the live assistant run (API key), local branch cleanup.

**ROUND 3 (2026-10-18), dipole moment and surface areas, ONE PR on branch claude/typed-dipole-surface-scores (from origin/master 7c311a91). Alex's decisions, all four the recommended option, asked in chat after measuring through the registry:** (1) dipole: GASTEIGER ONLY (aspirin 0.89 / EEM 4.76 / QEq 3.60 D under one label "Dipole"; the app benchmark MAE 0.79 / 1.79 / 1.69 D; EEM declines DMSO and chloroform); an EEM or QEq result is refused naming its model. (2) a net-charged species is REFUSED (origin-dependent: acetate 4.00 D about the centre of mass, 7.66 about the atom centroid; benzoate 11.90 vs 15.09); the result already records `origin_independent`. (3) FIVE surface numbers: ASA (1.4 A probe), ASA_H, ASA_P, van der Waals area, van der Waals volume; NOT ASA+ / ASA- (ASA+ is the hydrogens' area in a hydrocarbon, hexane 284.54 of 302.41 exactly; 7% of caffeine's ASA is on atoms with |q|<0.02; ASA- moves 40% across butanol conformers, ASA 3%). (4) surface settings: 1.4 A probe and the structure as it is ONLY (ASA 7% lower at 1.2 A, 24% higher at 2.0 A, only the ASA label carries the probe; the microspecies moves ASA+ -12% aspirin, -29% acetic acid). Not asked, applied by precedent: dipole MAGNITUDE only (X/Y/Z rotate with the frame: acetone X -0.48 to -1.88 D, magnitude 2.60), a salt refused for both (`whole_structure`; metformin HCl dipole 0.56-2.58 D, ASA 329.7-339.5 over ten embeddings), the van der Waals area and volume do not depend on the probe so a result made with any probe is read for them. Dipole varies hugely by conformer (1,2-dichloroethane 0.00-2.00 D, ethylene glycol 0.00-2.41 D): a limit stated in the docs, not a decision. Type EXACTLY the approved facts (the bbb/topology precedent).

**Round 3 build notes (2026-10-18):** branch claude/typed-dipole-surface-scores, 6 approved outputs (67 total, 26 geometry), `ApprovedOutput.run_with` + `score_value._settings_reason`; 28 mutants all caught; drive `benchmarks/visual/score_dipole_surface.json` PASS 21/21, control (settings rule removed) 4 of 21 fail; tests 34 + 39 + 95 + 1 window. Things I got wrong on the way: (a) I assumed an EEM dipole would sit BESIDE the Gasteiger one because `Provenance.method` differs; the store slot is (result id, input, fingerprint, method_version) and the charge model is none of those, so EEM REPLACES it (a real-services test showed it; the same trap as Geometry Analysis's settings, third time: read `SessionResultStore.put` before designing "side by side"); (b) a test label "Doubled dipole" was refused by `name_collision` (labels may not contain "Dipole" now); (c) golden recordings of a GEOMETRY calculator must use frozen molblocks (`tests/conformer_panel.py`), not a seeded embedding, because MMFF is floating point and CI is Linux; (d) `list_score_outputs` is at 84.9% of its 20,000 budget with 67 outputs (guard 85%), so the NEXT approval needs a budget decision; (e) I cited "section 12" of the design record for what is section 11 (section 12 is the decisions list).

**PR #370 OPENED 2026-10-18** (branch claude/typed-dipole-surface-scores, head ab3ac2c7, auto-fix on; local full suite green: shards 4,548 / 4,845 (rerun after the known WebGL access violation) / 3,685 / 4,155, naming 4,229). Waiting for Alex's per-PR "merge if green"; do not merge without it.

**#370 MERGED 2026-10-18 as 518be6ba** (Alex's "merge if green"; four shards and gating benchmarks passed on head 35f12510, the non-blocking linux job failed as usual; a CHANGELOG-only conflict with naming round 67 (#369) was resolved by keeping both entries). All three rounds of this thread are now merged (#367, #368, #370). Open directions, each needing Alex's go: ORCA reactivity (Phase 3), the synthesis helper (Phase 4), the live assistant run (API key), local branch cleanup; the assistant's `list_score_outputs` is at 84.9% of its 20,000 budget, so the next approved output needs a budget decision.

#### Index line, as it stood before 2026-10-18 (moved from MEMORY.md, which has a size limit)

- [More 3D derived scores](project_more_3d_derived_scores.md) — round 2 (2026-10-17, #367 sizes MERGED as 38771fe1; #368 HOMA extremes MERGED as 7c311a91, ORCA-only, any level named) and round 3 (2026-10-18, dipole magnitude + five surface numbers, Gasteiger only / neutral only / 1.4 A probe only, #370 MERGED as 518be6ba; the store keeps one result per geometry so EEM REPLACES Gasteiger): eight Geometry Analysis sizes; a salt refuses the EIGHT only (the ten are computed on the ChEMBL parent; my first claim was wrong, Alex confirmed the correction); HOMA-only-from-ORCA is its own PR B; the store keeps one result per geometry

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [More 3D derived scores](project_more_3d_derived_scores.md) — rounds 2-3 MERGED (#367, #368, #370): eight Geometry Analysis sizes, HOMA extremes (ORCA-only), dipole magnitude + five surface numbers; the store keeps one result per geometry (EEM REPLACES Gasteiger)

## reference-a-derived-column-is-a-checksum

*From the assistant's notes (`reference_a_derived_column_is_a_checksum.md`, type: n/a).*  
*When a table prints an input AND a quantity derived from it (Rappé Table I: R and zeta), recompute the derived column while transcribing; it found hydrogen's hidden lambda=1/2 and an oxygen misprint before any solver ran*

Rappé & Goddard 1991 Table I prints radius R and orbital exponent ζ, related by eq 17. Recomputing ζ from R during transcription (2026-09-14) showed: every heavy atom uses λ=0.4913, hydrogen needs λ=½ (only implied in the text), and oxygen's printed ζ 0.9745 follows from neither (implies R=0.667, printed 0.669).

**How to apply:** for any hand-transcribed table with a derived column, recompute it before building on it. Set the tolerance from the rounding of EVERY printed input — my ±0.0001 ignored R's 3 decimals and nitrogen failed by 2.5e-5 (amendment A3). Same idea as the Gell-Mann–Nishijima check on the particle table.

Also learned there: a paper can describe its own procedure twice, differently (Table III footnote vs section IV text) — make both named readings, pick a primary in advance, never choose by fit. Related: `feedback-a-source-can-contradict-itself`, `feedback-heldout-experiment-discipline`.

## reference-shannon-radii-column-trap

*From the assistant's notes (`reference_shannon_radii_column_trap.md`, type: n/a).*  
*Shannon 1976's CR and IR columns are offset by 0.14 A with the sign flipping between cations and anions, so a spot-check cannot catch a transposition*

Shannon 1976 (Acta Cryst. A32, 751) Table 1 prints **CR then IR** — the
crystal radius and the *effective* ionic radius. Kapustinskii and most
other uses want **IR**, the second number.

**They differ by 0.14 A and the sign of that offset FLIPS with charge**:
cations have CR > IR, anions have CR < IR. So the columns cannot be told
apart by "which is bigger", and worse:

    Cs+   CR 1.81   IR 1.67
    Cl-   CR 1.67   IR 1.81

— the same two numbers, swapped. **A spot-check landing on either one
alone reads as correct with the columns transposed.** Assert both, which
`tests/test_lattice_energy.py::test_the_effective_radii_are_used_not_the_crystal_radii`
does on purpose.

Two more facts about using this paper:

- **The PDF's text layer is OCR and mangles the ion labels** (`AC?3`,
  `AG?I`) while extracting the NUMBERS correctly — the worst combination,
  because a naive parse silently attaches right values to wrong ions.
  Render the table pages as images and read them (`page.get_pixmap`,
  `matrix=fitz.Matrix(6,6)`, clipped to a column) as was done for DREIDING.
- **`mendeleev` ships an independent transcription of the same table** and
  agreed on all 15 values checked. That is the good use of it: a second
  transcription the primary source adjudicates, not a source to trust.
  Installed for the check, uninstalled after; the values live in
  `chem/data/ionic_radii.json` so the app carries its own data.

Kapustinskii is **defined on six-coordinate radii whatever the real
structure's coordination is** — that is a property of the fit, not an
approximation. An entry for any other CN in that JSON would be a bug
waiting to be used.

See `reference-alex-has-paywalled-papers` — Shannon 1976 and the
Born–Haber source (kaya2022.pdf) were both supplied on request within
minutes, after I had checked and found neither on disk.

## reference-pdb-survey-recipe

*From the assistant's notes (`reference_pdb_survey_recipe.md`, type: n/a).*  
*How a direct PDB survey was done (RCSB search + mmCIF), the API quirks that cost time, and why a ligand's real-space correlation is the filter before trusting a close contact*

Scripts: `benchmarks/fluorine_pdb_survey/` (stage1 select, stage2 measure, stage3 close contacts and control, summarise; output folder is a CLI argument, outside the repo, about 1 GB). 1,240 entries took ~15 minutes with 6 download threads.

- **RCSB Search API** (`https://search.rcsb.org/rcsbsearch/v2/query`, POST JSON): `rcsb_entry_info.nonpolymer_bound_components` is NOT searchable (HTTP 400 "search is not enabled"). Use the text service on `rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id` (`in` / `exact_match`) and `rcsb_entry_info.resolution_combined` (`less_or_equal`). Components containing an element: service `chemical`, `type: formula`, `match_subset: true`, `return_type: mol_definition` (3,527 fluorine components); `result_set` items are dicts with `identifier`. A group query ANDing an `in` list of 3.5k ids with a metal worked.
- **Structures:** `https://files.rcsb.org/download/<ID>.cif.gz`; parse the `_atom_site` loop with a quote-aware token regex (atom names like `"O5'"` are double-quoted); first model only, alt id `.` or `A`. mmCIF has no bonds: a ligand fluorine is "on carbon" if a carbon of its own residue is within 1.65 A.
- **Validation before believing a close contact:** the Data API (`https://data.rcsb.org/graphql`) gives `rcsb_nonpolymer_instance_validation_score { RSCC RSR completeness average_occupancy }`. The two copper hits had RSCC 0.69-0.79 (the PDB flags under 0.8); the genuine calcium case had 0.99. Also read the primary paper (`rcsb_primary_citation`): their authors described a substrate-mimic placement, not coordination.
- **Control group:** a "no peak" claim needs a control with a peak (terminal ligand C-O oxygens against protein N peaked at 2.8-2.9 A; C-F thinned out).
- Europe PMC `?pdf=render` and ptpmcrender URLs return HTML to curl; ask Alex for PDFs. A web-search summary is never a read. Crossref-verify every DOI (a ChemInform abstract record often outranks the paper). See `project_fluorine_donor_acceptor_prs`, `reference_reading_pdfs_in_this_project`.

## project-cif-import-routes

*From the assistant's notes (`project_cif_import_routes.md`, type: n/a).*  
*Measured state of getting a CIF into the app, and why COD beats RCSB despite the RCSB fetcher already existing*

Alex asked (2026-09-16) for an in-app importer pulling CIFs from COD/RCSB instead of
downloading by hand. **Decision: roadmap only for now**, recorded in `docs/ROADMAP.md`
beside the periodic-charge entry. Three things were measured first, and the third
inverts the obvious order of work:

- **The RCSB fetcher already exists and is not the blocker.**
  `services/receptor_library_service.py` fetches `files.rcsb.org/download/{id}.pdb` with
  a `.cif` fallback and caches to disk (49 structures cached on his machine).
- **`read_cif` REFUSES a real RCSB mmCIF** — tried, not assumed, on the cached 7B6W
  entry: *"no usable unit cell: `_cell_length_a`/b/c are missing"*. mmCIF uses dotted
  tags (`_cell.length_a`) and Cartesian coordinates (`_atom_site.Cartn_x`); the reader
  wants underscores and `_atom_site_fract_x`. Recoverable — the file carries
  `_atom_sites.fract_transf_matrix` — but it is two reader features, not a download button.
- **COD has no client at all, and its files are the dialect the reader already parses.**
  All six committed CIF fixtures are COD: underscore tags, fractional coordinates, symop loop.

**Alex rejected fetch-by-ID alone**: "having to know the COD number kind of defeats the
purpose of casual importing." So the first thing built here is **COD fetch AND search
together, or nothing**.

**RCSB-as-a-crystal is the weakest item** and should not be re-argued: RCSB structures
already enter the app through another door (Import Macromolecule / receptor library, as
`MacromoleculeModel`), so the item is only "read one as a periodic solid" — and the PDB is
overwhelmingly proteins, whose unit cells are past the charge budget and for which the
crystal features are not what anyone wants.

**Network approach is pre-approved** so it is not re-litigated: through `net.py`, cached
to disk like the receptor library, and no test on the network.

Also asked for, and split in the roadmap: **building a crystal in the app**. Not from a
drawing or SMILES — that is crystal structure prediction, which `project-charge-round3-six-tracks`-era
docs already refuse. But hand-entering a measured cell + space group + sites is data
entry, not prediction, and a prototype library (rock salt, fluorite, wurtzite, perovskite)
is the same with the packing supplied. Either needs provenance that travels: a typed
structure is not a measured one.

## reference-cod-cif-fixtures

*From the assistant's notes (`reference_cod_cif_fixtures.md`, type: n/a).*  
*Real COD depositions are committed as CIF test fixtures, and each one states a volume and density that validate the whole parse chain independently*

`tests/fixtures/cif/` holds two real Crystallography Open Database
depositions, **public domain** by COD's own statement ("All data on this
site have been placed in the public domain by the contributors"), so
committing them is fine:

    1504676   perfluorophenyl-capped polyyne, triclinic P-1, 30 sites
    7717378   a uranium complex, triclinic P-1, 120 sites

**The reason these are worth more than a hand-written CIF** is not the
syntax stress (multi-line `;` fields, quoted values with commas, extra
`_atom_site_` columns, tags containing slashes, negative fractional
coordinates) — it is that each file states its own `_cell_volume` and
`_exptl_crystal_density_diffrn`, **computed by the depositor's software
from the depositor's structure**. Reproducing those exercises parse →
expand → wrap → deduplicate → compose → volume → density in one assertion,
against a number this project did not produce.

Both matched to four significant figures on the first run.

**Look for a self-stated derived quantity in any file format worth
parsing.** It turns a fixture from "does it crash" into an end-to-end
oracle, and it costs nothing. The same trick would work for any format
that records a checksum, a total, or a computed property alongside its
raw data.

Alex supplies these on request within minutes — see
`reference-alex-has-paywalled-papers`. Ask for an actual FILE when the
parser is what needs testing; a paper validates arithmetic only, which is
a different thing and was the gap these closed.

Still untested: disorder groups and partial occupancy in a real file.
Both fixtures are fully ordered.

## openbabel-mmcif-divergences

*From the assistant's notes (`reference_openbabel_mmcif_divergences.md`, type: n/a).*  
*Open Babel reads mmCIF and PDB differently in three ways; two are fixed, the protonation one is not and nobody knows which arm is right*

Open Babel 3.1.0 does not produce the same molecule from a deposit's
mmCIF form as from its PDB form. Found and mostly fixed 2026-08-09 on
branch `claude/eloquent-mayer-8a1f1a`.

**Fixed:**
- `_atom_site.type_symbol` is matched CASE-SENSITIVELY, and the PDB
  archive writes two-letter elements uppercase (`CL`, `ZN`, `SE`). Every
  one came back atomic number 0 and was then *deleted* downstream. It is
  every two-letter symbol, not a list of eight.
  `pose_analysis.normalise_element_symbols` fixes it.
- No implicit hydrogen counts at all from mmCIF, so an mmCIF receptor
  reached Vina essentially unprotonated (4DKL: 41 H vs 3,754).
  `OBAtomAssignTypicalImplicitHydrogens` per atom fixes it, and is a
  verified no-op on PDB.

**NOT fixed, and the important part:** 10 of 48 catalogue receptors still
differ between formats in polar hydrogens and nitrogen typing (`HD`/`N`/
`NA`). No heavy atom differs any more. **Which arm is correct has not
been established** — on 4M48 the PDB read assigns 641 implicit H to
nitrogen and mmCIF 955, and for a ~900-residue protein the mmCIF figure
is the more plausible. So do not "fix" it toward the PDB answer without
settling that first.

Parity metric worth reusing: prepare each receptor's PDBQT from both
formats through the real `_convert_receptor_to_pdbqt` and compare the
AutoDock type histogram. It went 0 of 48 -> 38 of 48. There is no
committed script (it needs all 49 deposits in both formats); rebuild it
as a throwaway harness.

Bonding is distance-based in both formats — disulfides survive mmCIF
intact, 10/10 on 5KIR. An earlier claim here that "Open Babel ignores
mmCIF connectivity" was an inference and is WRONG.

Related: `verify-real-backends`, `receptor-library`.

## reference-seed-can-lock-in-the-wrong-answer

*From the assistant's notes (`reference_seed_can_lock_in_the_wrong_answer.md`, type: n/a).*  
*Pinning a random seed makes a wrong answer permanent instead of occasional — measure WHICH result the seed gives before shipping it*

Seeding an unseeded random call fixes reproducibility and can make the
outcome **worse**: the coin flip becomes a permanent commitment to whichever
side the seed lands on.

Measured 2026-09-11 in OpenChem Studio. `nmr_scaling.py` embedded each NMR
calibration compound with ONE unseeded conformer. Ten of eleven compounds
are rigid and land identically from any seed. **Cyclohexane does not**:
chair −3.5609 kcal/mol, twist-boat +2.3688, and unseeded it produced the
twist-boat about one run in three. The experimental shift it is fitted
against (26.9 ppm, ¹³C) is the chair's.

**The seed chosen for reproducibility, `0x5EED`, produces the twist-boat.**
Pinning it alone would have calibrated every NMR shift against the wrong
conformer permanently rather than occasionally.

**Why:** "make it deterministic" reads as a pure safety improvement and is
not one. Determinism preserves whatever the draw gave you.

**How to apply:** before pinning a seed, measure what the seeded call
actually returns against what it *should* return. Where the call picks one
of several outcomes, the fix is usually not a seed but a selection rule —
here, generate several and take the lowest in energy, which is what a
"reference geometry" means. Related:
`feedback-verify-real-backends`, `project-conformer-funnel-closed`,
`feedback-a-residual-explained-by-inference`.

#### Index line before it was shortened (2026-10-18, MEMORY.md has a size limit)

- [A seed can lock in the wrong answer](reference_seed_can_lock_in_the_wrong_answer.md) — pinning a draw made a wrong NMR calibration permanent; PYTHONHASHSEED hit `variants[0]`

## project-multicomponent-largest-component

*From the assistant's notes (`project_multicomponent_largest_component.md`, type: n/a).*  
*Group 3 of the refusal audit (PR #460) - a salt with no single ChEMBL parent is computed on its largest component, labelled; what still refuses; the 2D-vs-3D trap*

PR #460 (MERGED 2026-10-25, branch claude/multicomponent-choice): the 16 parent-scoped calculators and the always-on descriptors compute on the LARGEST component (heavy atoms) of a drawing whose ChEMBL parent leaves several, re-neutralised like ChEMBL's own parent, labelled (first limitation, `caveat`, `component_choice`, reader status line). Still refused: equal-size different species (NaCl) and ChEMBL's metal exclusion. Solubility/Joback/Hansen still refuse any second component. Naming the component in the window is NOT built.

**Why:** Alex's rule (2026-10-23): refuse only what cannot be computed; label the rest. See `feedback-calculator-stage-policy`.

**How to apply:** any "does this structure have coordinates?" check must ask `Is3D()`. The app's own molecule comes from a molblock and carries 2D drawing coordinates, so `GetNumConformers() > 0` is true for every drawing. Unit tests built from SMILES have none, so only the driven window (benchmarks/visual/salt_largest_component.json) showed it. Golden fixtures with custom compact JSON (bbb/topology lines) need a renderer verified byte-for-byte against the existing file before regenerating entries.

## project-conformer-funnel-closed

*From the assistant's notes (`project_conformer_funnel_closed.md`, type: n/a).*  
*Conformer generation, asked three times: the filter was acquitted (2026-08-13), and the third round moved the diagnosis to the EMBEDDER and pinned the seed (2026-09-11)*

Alex has questioned conformer generation three times. **The de-duplication
has been acquitted twice and is not the place to look.**

Round 1–2 (2026-08-13, PR #21): the funnel proved de-duplication discards
only degenerate pairs. Real losses were ETKDG sampling
(`useSmallRingTorsions` default-on) and a silent keep-10 cap.

Round 3 (2026-09-11): *"every time I run it now, I get wildly different
results ... sometimes six, sometimes nine, sometimes eight"*. Two answers:

- **The embedder, not the filter.** funnel.py on the reported cage showed
  only **3–4 distinct shapes PRE-optimisation per 100 embeddings** — an
  upper bound on anything downstream. The cap never bit.
- **One unseeded line.** `ConformerService` built `RDKitConformerProvider()`
  with no seed. Fixed: seeded, and the search embeds in batches until two in
  a row find nothing unmatched. The cage now gives 9 every run (was 6/9/8/7);
  ethylmorphine 26–27 (was 20–21). Costs ~40 s against ~8 s.

**Why:** the first move on a conformer complaint is still
`benchmarks/conformers/funnel.py <smiles>`, and the row to read first is
**distinct PRE-optimisation** — if that is small, no threshold or cap change
can help and the answer is sampling.

**How to apply:** never say "converged" about a stopping search; it is a
*plateau*, a statement about sampling. And the survivor count is not a
measure of yield — adding one lower-energy candidate can LOWER the distinct
count, because leader clustering is energy-ordered. Related:
`reference-seed-can-lock-in-the-wrong-answer`,
`feedback-calibration-set-shape`.

## project-d191-d192-lambda-and-nuclide

*From the assistant's notes (`project_d191_d192_lambda_and_nuclide.md`, type: n/a).*  
*D-191/D-192 (hypervalent lambda number, nuclide on a one-atom prefix): MERGED 2026-10-06 as #238 (edda176a), fork port merged as fork #23 (e9a2d5f), VENDORING row in #241; D-193..D-196 still open*

**STATUS 2026-10-07: DONE and merged** -- app #238 (squash `edda176a`), fork #23 (`e9a2d5f`), VENDORING row in #241. The "Still to do" fork port below is finished; D-193..D-196 are the only open parts. (The text below is the history of how it was built.)

Built 2026-10-06 in the worktree `.claude/worktrees/musing-snyder-88897b` (branch `claude/musing-snyder-88897b`, base `1030bc96`): was uncommitted and unpushed when this was first written. Found by naming the Blue Book's own P-45.2.3 examples 11 and 12 (p. 422): a `λ5-phosphanyl` substituent lost its number and an `(81Br)bromo` its label, each a wrong molecule. Details are in `src/openchem/vendor/CHANGELOG.md` (2026-10-06) and the lesson "A GROUP'S BONDING NUMBER AND A PREFIX'S NUCLIDE WERE IN NO TABLE..."; gates: census 3 of 2000 moved, ref-compare 1712 structures 2 moved 0 violations (new manifest `D191-D192-lambda-and-nuclide-prefixes.toml`), vendored 5632 passed, app session 3181 passed.

**Still to do:** the fork port (`xaerogonzo/open-iupac-namer`): `engine.py`, `assembly.py`, `isotope.py`, `data/functional_groups.json` merge with `tools/fork_port.py`; the rows of `test_namer_known_defects.py` are hand-patched (the tool does not carry them). Open and measured: D-193 (nuclide on a retained parent's atom or a multi-atom prefix: `[15NH2]c1ccccc1` is `aniline`, wrong molecule, app withholds), D-194 (P-45.2.3 / P-45.4.1 parent chosen by atom order), D-195, D-196.

**This is the chip spawned from `project-p45-2-3-citation-locants`** (its examples 11 and 12 were blocked by these two defects). Measured 2026-10-06 on a scratch copy of `claude/nice-franklin-ca57cd` (`c67d10b1`) with my diff applied (clean): examples 11 and 12 are the book's name in 40 of 40 random spellings (each was ~50/50 alone), the P-45.4.1 ether stays 24/16. **Six tests flip there; whoever merges second updates them:** D-191p and D-192p (they pin the canonical spelling's NON-PIN names, because the application names `Chem.MolToSmiles`), D-194a and D-194b (strict xfails, now passing: move to FIXED), and the two book-example rows in `tests/test_naming_providers.py`. D-194c (P-45.4.1) stays open either way. The OPSIN-spelling rows D-191q and D-192q already hold the PIN and stay.

How to apply: see `reference_naming_rounds_index` for the round history and `project_post_round14_program` for the program; the P-14.4 (j) work is `project_p14_4j_stereo_tiebreak`.

## project-vb-ties-stage

*From the assistant's notes (`project_vb_ties_stage.md`, type: n/a).*  
*The three von Baeyer ties left open by #218 (meso, cages, compound locants) closed 2026-10-06: app #226 (1cac2a06) + fork #20 (547e00d); what is still open and what to know before touching it*

**State (2026-10-06):** MERGED. App PR #226 (squash `1cac2a06`), fork PR #20 (merge `547e00d`), both remote branches and the scratch checkouts deleted. Follows `project_naming_rounds_24_25`.
The `VENDORING.md` row is merged too (#230, squash `f7bc3c1f`), so the next `fork_port.py --base` is `cbc5fc94`. Nothing pending from this stage.

**What it did:** P-14.4 (j) meso tie-break (general, in `engine._break_alphanumerical_tie`); P-31.1.4.2 fewest compound locants first (`preference.unsaturation_tier`, and `_recompute_ring_unsaturation_name` rewrites `N(M)` locants); cages numbered from EVERY tied decomposition (`vb_decompose.best_decompositions`), superscripts before heteroatoms (P-23.2.6.2, P-23.3), element order is P-23.3.2.2 (older changelog entries cite P-31.1.4.2.4 wrongly).

**Still open (documented in both CHANGELOGs):** dependent secondary bridges cannot be enumerated and the 28-atom tetracyclic is beyond the enumerator cap; a benzene ring inside a von Baeyer system is named from the input's Kekule form (`C1=CC2=CC=CC=C2C3CCCCC13` is 4 names over 24 spellings, identical on the base, so a Kekule-form tie no rule here reaches); the pinned-heteroatom path ranks ene above suffix.

**Why it is not obvious / how to apply:**
- PR #227 (`project_p14_4j_stereo_tiebreak`) overlapped this stage, but it had already merged master at #226, so there was no duplicate rule. I brought it up to date by MERGING master (one CHANGELOG keep-both conflict; a rebase would have needed a force-push on a pushed branch, which the repo forbids) and it was MERGED 2026-10-06 (`1e2a3034`) by Alex from another branch.
- The fork's `tests/test_carbocyclic_indicated_h.py::test_trindene_indicated_h_name` (2 params) already fails on fork main `9560399`; not from this stage, never diagnosed.
- Probe a "pinned" name with OPSIN across 24 spellings (`doRandom=True`) before believing a note about it: I recorded a wrong name for the benzo tricyclo case and only a re-probe caught it. Run each mutation and read its failure count rather than relying on a remembered "passes under mutation".
- A mutation that adds a criterion the enumerator can never trigger (dependent bridges) passes every test: that is how a dead criterion is found, remove it.

## reference-app-withholds-bad-names

*From the assistant's notes (`reference_app_withholds_bad_names.md`, type: n/a).*  
*The app WITHHOLDS an engine name that embeds NAMING ERROR or reads back as another structure; only an OPSIN-unreadable name is shown (unverified) - so engine defects rarely reach the user as wrong names*

`src/openchem/chem/naming_providers.py::derived_name_for_structure` gates every engine name: (1) any name containing `NAMING ERROR` raises `NamingError` ("...reported an error instead of a name..."); (2) a name whose OPSIN read-back is a DIFFERENT structure raises `NamingError` ("...did not parse back to this structure..."); a name OPSIN cannot READ (`PARSER_FAILED`) is shown with a "not verified" note; without OPSIN the name is shown unverified.

Consequences: engine-level census classes (naming_error, mismatch_*) are NOT what a user sees; a fix turns "no name" into a right name. Severity ranking of an engine defect should account for this. Round 12 got it wrong in its docs (fixed in round 13). Pinned by 3 tests in `tests/test_naming_providers.py` on real engine output (D-133 for the embedded error, D-151 for the read-back mismatch). The engine still emits the embedded string on purpose; the fork (no app layer) shows it. See `project_naming_round_13`.

## reference-caller-atom-maps-break-dimorphite

*From the assistant's notes (`reference_caller_atom_maps_break_dimorphite.md`, type: n/a).*  
*A drawing's atom-map numbers reaching Dimorphite-DL change its answer (mapped imidazole: no state); strip before any library call, restore per atom after*

Found 2026-09-14 (PR A, W3.0a).
- `dominant_microspecies` passed the caller's atom maps into the SMILES it gave Dimorphite. A mapped imidazole at pH 7.4 came back with **no state**, where the unmapped one gives the anion.
- `_rebuild_in_original_order` built fresh atoms, so every output map was 0.
- Fixed by handing libraries an unmapped copy (`without_atom_maps`) and restoring each original map after.
- The pkasolver runner tags atoms with its own map numbers, so caller maps must never reach it either.

A second finding came out of the same work. The correspondence tests (element plus adjacency, canonical SMILES) pass for ANY automorphism. `tests/test_heavy_atom_correspondence_oracle.py` edits atoms in place, so the answer is known without the scoring rule. It predicts refusals from the drawing's own symmetry classes, `CanonicalRankAtoms(breakTies=False)`.

**How to apply:** metadata a caller put on a molecule (maps, props) is input to a third-party library whether you meant it or not. Strip it on the way in, and assert it is exactly restored on the way out. Related: `verify-index-spaces-on-edited-state`, protonation-hash-seed (pruned 2026-10-06).

## reference-py2opsin-cwd-collision

*From the assistant's notes (`reference_py2opsin_cwd_collision.md`, type: n/a).*  
*py2opsin uses a fixed temp filename in the CWD, so two OPSIN callers in the same directory crash each other*

`py2opsin` writes and deletes a fixed-name scratch file, `py2opsin_temp_input.txt`,
in the **current working directory**. Two processes calling OPSIN from the same
directory delete each other's file and one dies with:

`FileNotFoundError: [WinError 2] ... 'py2opsin_temp_input.txt'`

Hit this running `benchmarks/naming/score.py` while the vendored pytest suite
(which round-trips names through OPSIN) was running in the background from the
same worktree. The traceback points into `py2opsin.py:172 os.remove`, which
looks like a py2opsin bug rather than a collision — easy to misdiagnose.

**Second shape, 2026-10-06 (and it does NOT always say WinError 2):** I started the
naming-consumer pytest session, the vendored suite and `naming_ref_compare.py` together
from one worktree. A test that passes alone failed in the consumer session with
`TypeError: can only concatenate str (not "CalledProcessError") to str` raised from
`py2opsin.py:169` -- py2opsin's own error handler crashing on a non-zero OPSIN exit
because the shared temp file had just been clobbered. That reads as an OPSIN or engine
failure on the new test. Check the exception type before believing it, and re-run the
failing test alone from a different cwd (`cd <scratch>/iso; PYTHONPATH=<worktree>
python -m pytest <absolute test paths> --rootdir=<worktree>`; `PYTHONPATH` is what lets
`tests.conftest` import). `naming_ref_compare.py` is cwd-independent (its git calls use
its own ROOT), so launch it from the throwaway directory too.

**Third shape, 2026-10-06:** `tools/naming_census_scan.py` is an OPSIN caller too. I launched
the vendored suite in a worktree while that worktree's census scan was running and the scan
died with the WinError 2 shape (the suite survived). Launch each from its own cwd:
`cd <scratchpad>/cwd_x && <worktree>/.venv/Scripts/python.exe <worktree>/tools/naming_census_scan.py`.

**How to apply:** run concurrent OPSIN consumers from different working
directories. Scoring a benchmark while the suite runs is the common case; a
throwaway `scratchpad/scorerun/` cwd is enough, since `score.py` takes absolute
paths. Java must also be on PATH or py2opsin degrades to warnings and skips
instead of failing — see `project-external-tools-paths`.

## project-sources-registry

*From the assistant's notes (`project_sources_registry.md`, type: n/a).*  
*OpenChem Studio has a guarded provenance registry at docs/sources.toml; how to add to it and what its guards can and cannot prove*

`docs/sources.toml` is the hand-edited registry of every source OpenChem Studio rests on. `tools/build_sources_doc.py` generates `docs/SOURCES.md` from it; `tests/test_sources_are_current.py` guards it. Built and verified 2026-08-16/17 across PRs #30-#33, shipped in **0.10.0**.

State at 0.10.0: **60 sources — 20 `citation_and_claim`, 37 `citation`, 3 `unverified`.** The three are `miller_polarizability`, `hlb`, `tsei`, whose recorded `reason` IS that no usable source exists. That is their terminal state; do not try to "fix" them.

**Count 2026-10-12: 232 sources** (it was 60 at 0.10.0; 197 and 216 on the way). New statuses in use: `shipped` needs a `used_by` pointing at code that cites it, `reference_only` needs a `reason`; both need `verification` and `verified_date`. Say in each note what was CHECKED and what was NOT; a number computed from a CIF or a table is labelled as computed by us. Crossref-verify identity before registering.

**Why:** the project's whole discipline is measuring claims against primary sources, and for two years those sources lived in four inconsistent shapes with nowhere to read them.

**How to apply:**

- Edit `docs/sources.toml`, never `docs/SOURCES.md` (generated). Then `uv run --no-sync python tools/build_sources_doc.py` and run `tests/test_sources_are_current.py` + `tests/test_docs_are_current.py`.
- `citation` = the reference is right. `citation_and_claim` = the NUMBER this project uses was checked against the source. `verified_date` is required for both and forbidden for `unverified` — the pair is enforced.
- Cite from prose as `[source:key]`, never a bare backtick. `_source_key` in a data file — **underscore-prefixed**, because two loaders read their file's top level as data and drop `_` keys; a plain `source_key` broke 43 tests.
- If a shipped data file is GENERATED, put its `_source_key` in the generator. Hand-added metadata in `lewis_parameters.json` was silently dropped by the next run of its builder.

**What the guards cannot prove:** that a citation points at the right paper, that a table number is right, that a source still supports the claim, or licence compatibility. Completeness rests on the reconstruction sweep, not on a test — see `feedback_the_fields_nobody_can_check`.

Related: `reference_alex_has_paywalled_papers`, `reference_reading_pdfs_in_this_project`.

## reference-ionescu2013-si

*From the assistant's notes (`reference_ionescu2013_si.md`, type: n/a).*  
*Ionescu 2013's SI: the one EEM source whose population is exactly recoverable, plus the four traps in reading it*

`D:\Xaero Stuff\Documents\Sci Downloads\ionescu2013_si\` (doi 10.1021/ci400448n) is the only EEM source held whose population is **exact**: 41 protein fragments as PDB MODELs plus insulin and ubiquitin, per-atom QM charges for 12 schemes, per-atom EEM charges for all 24 published models, and Table S1's parameters. Table S1 and S2 are frozen as fixtures under `tests/fixtures/charges/ionescu2013/`.

The model reproduces: **ubiquitin 998/998 atoms** and the **training set 39,061/39,061** within the registered tolerance (TRIAGE check 2.8).

Four things measured while reading it, each of which would have produced a wrong answer if assumed:

- **The two CSV layouts differ.** The training set is 12 stacked blocks (one per QM scheme, three value columns); the two test proteins are one wide table with 12 QM columns and all 24 model columns.
- **Three scheme blocks are short** (40, 40 and 38 of 41 fragments), so the source population is scheme-dependent, and aligning blocks by position pairs one molecule's charges with another's structure. Key on the NSC id.
- **The PDB files have no element column** (lines stop at 54 chars). The rule that reproduces the paper's Table 1 counts exactly: a HETATM whose *residue* is CA is calcium (" CA " in an ATOM record is an alpha carbon), otherwise the atom name's first letter after any leading digit.
- **Distances are in ångström and R_avg is the SQUARED Pearson coefficient.** Neither is stated unambiguously — the paper's prose says squared, its own eq 7 prints the unsquared form — so both were identified by reproduction, not assumed. The bohr reading fails outright (34/998).

Calcium *is* parameterised in Table S1 (`Ca` in E, `Ca0` in EX), which settled an open question in the plan. The EX models need bond-order perception from a PDB and are recorded BLOCKED on typing; the E models need only the element.

Related: `project_charge_round3_six_tracks`, `reference_reading_pdfs_in_this_project`, `reference_openbabel_charge_models`.

## reference-wilmer2012-si-structures

*From the assistant's notes (`reference_wilmer2012_si_structures.md`, type: n/a).*  
*Wilmer 2012's EQeq supporting information: what the ACS package holds, and why its .mol files are not molfiles*

`D:\Xaero Stuff\Documents\Sci Downloads\wilmer2012_si\` (doi 10.1021/jz3008485), fetched 2026-09-15:

- `jz3008485_si_001.pdf` — the 24-page SI (derivation, run inputs, the EQeq source listing's *pointer*).
- `jz3008485_si_002/CrystalStructuresWithCharges/` — **48 structure files**: 12 MOFs × 4 charge sets (EQeq, REPEAT, ChelpG, AMSQeq).
- `jz3008485_si_002/…AllIsothermsData….xlsx` — per-MOF CO₂ isotherms, one column per charge scheme plus experiment, excess mg/g.

**The `.mol` files are NOT MDL molfiles.** They are the RASPA-style listing EQeq emits, and reading them as molfiles gets nothing:

```
 Molecule_name: hypotheticalMOF
   Coord_Info: Listed Cartesian None
       424                                   <- atom count
    1  7.5791 5.3369 5.3369  Mof_Zn  1.211 0 0   <- index x y z label CHARGE
    ...
       90.0 90.0 90.0                        <- cell ANGLES, at the END of the file
       0.0  0.0  0.0                         <- origin
       25.8320 25.8320 25.8320               <- cell LENGTHS
```

So each file carries the unit cell *and* the per-atom charges — everything a periodic charge result's identity needs.

**Two checksums that identify the corpus** (measured 2026-09-15): all 12 atom counts match the paper's Table 1 exactly (624, 252, 424, 472, 162 ×4, 276, 72, 354, 330), and every EQeq set sums to zero.

**Still missing from the ACS package:** `ionizationData.dat` (the ionisation/electron-affinity table the method runs on) and `EQeq_v1_00.cpp`. SI page 1 lists them as accompanying files; S8 points at the source rather than printing it. A substitute table can be rebuilt from the two references S2 cites (Andersen & Haugen 1999; Moore 1970) — but it is an independent reconstruction and has to be labelled one, or a per-atom mismatch has two candidate causes at once.

This moved Track 6 from BLOCKED to FEASIBLE; see `benchmarks/charges/periodic/FEASIBILITY.md` section 8 and `project_charge_round3_six_tracks`.

Related: `reference_alex_has_paywalled_papers`, `reference_reading_pdfs_in_this_project`.

## project-nmr-validation-sources

*From the assistant's notes (`project_nmr_validation_sources.md`, type: n/a).*  
*NMR ground truth must be independent of nmrshiftdb2; quinine is scored and shows the hybrid's calibration gate refusing a real gain*

Established 2026-08-03 validating the lookup+ORCA hybrid
(`chem/nmr_hybrid.py`); quinine scored the same day (commit 69aa56b).

**Never score the HOSE lookup against nmrshiftdb2-derived data.** That
database IS the lookup's index, so agreement would be circular. Truth
must be independent, and in **CDCl3** to match everything else here.
Assigned literature tables now live in
`benchmarks/nmr/literature_shifts.py` (quinine from Moreland 1974
doi:10.1021/jo00930a020, caffeine).

**The open design question, measured not guessed.** The hybrid's
scale-agreement gate refused quinine at +3.00 ppm against a 2.62 limit,
and the merge it blocked would have taken MAE from 7.96 to 3.44 (12
`rough` carbons: 12.50 -> 4.09). The gate measures its offset on `good`
atoms, which are exactly the atoms the lookup then wins — so
conformational error around quinine's flexible carbinol hinge vetoed the
merge everywhere else. Across five molecules the gate has prevented no
measured harm and cost one real gain. Left unchanged pending Alex's
call; a discriminator exists (a true scale error has |mean| near the
RMS, quinine's was 3.00 vs 5.36) but rests on two data points.

**Two structure traps, both hit for real:**
- The obvious quinine SMILES was **9-epiquinine** — a different column of
  the same table, differing by only 1.5-3.5 ppm, so it would have read as
  a plausible bias rather than as nonsense. Confirm any stereoisomer
  against PubChem (quinine = CID 3034034,
  InChIKey LOUPRKONTZGTKE-WZBLMQSHSA-N) before scoring with it.
- A quinuclidine **bridgehead nitrogen must carry no stereo tag** —
  `EmbedMolecule` fails outright with one, even with `useRandomCoords`.

**How to apply:** validate any new atom-index mapping against the
lookup's own `good` atoms first — that caught the ring-fusion ambiguity
in Moreland's 9'/10' numbering (0.47 ppm right vs ~18 ppm wrong).

Related: `project-nmr-ml-not-shipped`, `feedback-verify-real-backends`

## reference-belova2014-table1-vs-si

*From the assistant's notes (`reference_belova2014_table1_vs_si.md`, type: n/a).*  
*Belova 2014 (acetylacetone) main-text Table 1 and its own SI disagree on which B3LYP basis gave which dE; use the SI energies, MP2/cc-pVTZ is consistent*

Belova et al., J. Org. Chem. 79 (2014), doi:10.1021/jo402814c; both `belova2014.pdf` and `belova2014_si.pdf` are in Sci Downloads.

The SI lists electronic energies (Hartree) per labelled calculation. Electronic dE (diketo minus enol, kcal/mol) from them: B3LYP/6-31G(d,p) 6.256, B3LYP/aug-cc-pVTZ 6.481, MP2/6-31G(d,p) 1.466, MP2/cc-pVTZ 4.849.
Main-text Table 1 prints 6.48 under 6-31G(d,p) and 6.24 under aug-cc-pVTZ, the reverse of the SI; only MP2/cc-pVTZ (4.85) agrees in both places.

**Why:** I first told Alex the SI held no energies (I had read 250 characters of its description), then found it did; reading the SI itself then exposed the Table 1 mismatch. Both were found only by recomputing from the primary numbers.
**How to apply:** for the tautomer validation row use the SI energies and prefer MP2/cc-pVTZ; never lift the B3LYP rows from Table 1. See `feedback_a_source_can_contradict_itself`.
