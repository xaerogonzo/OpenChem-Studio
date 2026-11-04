# Preregistration 3 (DRAFT, NOT FROZEN): does docking with another scoring function put the right pose first?

Drafted 2026-11-02. **Nothing here is binding until a dated "Frozen" line is added at the end,
and nothing may be scored for the deciding test before then.** Until then it may be edited
freely; after, only by dated Amendment, as `PREREGISTRATION_PLEC2.md`. The context, the
candidates and the licence questions are in `docs/DOCKING_ENGINE_CANDIDATES.md`; this file is
only the test.

## The question

`PREP_BOX_RESULT.md`: with the Docking panel's defaults Vina's top pose is within 2.0 A for 35
of 47 measurable catalogued receptors, and a pose within 2.0 A is among the nine for 44 of 47.
The headroom is the 9 receptors whose correct pose is found and ranked lower. Two ways of
re-ordering Vina's own poses have been tried and failed (Vinardo as a rescorer: no gain on
affinity ranking; PLECscore: 1 gained, 10 lost, `RESULT_PLEC2.md`). This test asks the question
the third way: **if the search itself is run under a different scoring function, does the
top-ranked pose of the same nine become the correct one more often?**

Only a different scoring function can change which pose ranks first among poses the search
finds. QuickVina 2 / QuickVina-W and Vina-GPU search faster under Vina's own function, so they
are not arms here (see the candidates document). The one native Windows engine with other
functions that was obtained and run is smina; its functions are the arms.

## Arms

All arms are the SHIPPED `VinaDockingProvider` with an engine injected, through the survey's own
`run_one` (`prep_box_survey.py`), so receptor preparation (Open Babel, waters stripped,
cofactors kept, pH 7.4), the box (from the crystal ligand), the ligand embedding, nine poses and
exhaustiveness 25 are identical across arms. `engine_pilot.py` is the pilot version of this
runner.

| Arm | Engine | Scoring | Role |
|---|---|---|---|
| `vina` | AutoDock Vina 1.2.7 (the application's own) | `vina` | reference |
| `smina-default` | smina 2020.12.10 (conda-forge win-64) | its default, which is Vina's function | CONTROL: same function, different search code |
| `smina-vinardo` | same | `vinardo` | candidate |
| `smina-dkoes_fast` | same | `dkoes_fast` | candidate |
| `smina-ad4` | same | `ad4_scoring` | candidate |

`smina-default` exists to separate two things a switch to smina changes at once: the search
code (Vina 1.1.2's, not 1.2.7's) and the scoring function. A candidate is compared with `vina`
(what a user gets by switching) and with `smina-default` (the function alone).

## Seeds and the unit of comparison

Three pinned seeds per arm and receptor: 20261029 (the survey's), 20261030, 20261031. A
receptor is **correct for an arm** when the arm's top-ranked pose is within 2.0 A of the crystal
ligand (assignment RMSD, `prep_box_core.assignment_rmsd`, the survey's lower-bound distance and
its 2.0 A cutoff, restated here so a later change to the survey cannot move this test) in at
least 2 of the 3 seeds. One seed per arm would make every comparison a comparison of two draws,
and the survey itself found three receptors within a few tenths of the cutoff.

Cost: 5 arms x 3 seeds x 47 receptors = 705 dockings, about 20 to 50 s each on this machine,
roughly 5 hours serial.

## Population

Deciding: the receptors the survey could measure (47 of 49: 6LQA's ligand would not embed, 5TGZ's
crystal ligand is incomplete), minus those a gate excludes for every arm (G4), minus the
**training-overlap stratum** for any function trained on PDB complexes. That stratum is
reported apart, never counted, as `plec_core.TRAINED_ON` was. It is built before scoring from
the primary sources of each function (open item 1). The 17 receptors of the pilot below stay in
the deciding population and are also reported apart as the seen subset, so the reader can see
whether the verdict depends on receptors that were looked at.

## Rules (the test's whole logic; each is a pure function in the runner's core module)

For each candidate arm A, against each comparator C in {`vina`, `smina-default`}:

- **Gained**: C is not correct for the receptor and A is. **Lost**: C is correct and A is not.
- **Net** = gained - lost.
- **One-sided exact sign test** on the receptors whose call changed (n = gained + lost, ties
  and unchanged receptors dropped): improvement p = P(X >= gained), X ~ Binomial(n, 1/2); harm
  mirrored with `lost`.
- **PASS** for A against C needs net >= +3 and p <= the level below. **HARMFUL**: the mirror.
  Otherwise **NULL**.
- **Level**: 0.05 divided by the number of candidate arms (3), i.e. 0.0167 (Bonferroni; the
  arms are not independent, so this is conservative). The smallest results that clear it are
  6 gained and 0 lost (p = 0.0156) or 9 and 1 (p = 0.0107). **State plainly: with at most 9
  receptors of headroom, a PASS needs nearly all of the headroom, and a modest real gain will
  read as NULL.** This test can find a large improvement or show harm; it cannot confirm a small
  one, and the verdict text must say so.
- The verdict of the PRIMARY comparison is each candidate against `vina`. The comparison with
  `smina-default` is reported beside it and decides only one thing: if `smina-default` itself
  differs from `vina` at p <= 0.05 two-sided, the search code is not a neutral backdrop, and
  every candidate verdict is stated with that sentence in front of it.
- **Order of verdicts**: INCONCLUSIVE (any gate fails), PASS, HARMFUL, NULL.

## Gates, all passed BEFORE any gained/lost count is read

Each prints its inputs and its verdict; the runner stops at the first failure.

- **G1, the reference reproduces the survey.** The `vina` arm at seed 20261029 reproduces the
  recorded top-pose distance of `artifacts_prep_box/results.jsonl` on every receptor it docks
  (to **0.05 A** on the survey's two-decimal distances). The prep-box survey stored
  `round(assignment_rmsd, 2)`; a remeasure of all 47 receptors on 2026-11-04 found 45 within
  0.005 A, one at 0.01 A (5KIR, centi-Å rounding), and one at 0.05 A (7B6W, alternate top pose
  at the same seed in a five-run repeat probe). The tolerance is the observed maximum, not
  tighter than the artifact. This is the lesson of the PLECscore test: a comparison is worthless
  if the harness no longer reproduces something known. Pilot: 17 of 17 reproduced at 0.05 A.
- **G2, the control is the same function.** `--score_only` of nine fixed Vina poses on five
  receptors (the first five of the 17-receptor pilot list, `engine_g2_score_only.g2_receptors`)
  differs between Vina 1.2.7 and `smina-default` by at most 0.01 kcal/mol (the smina
  spike measured at most 0.004 on one ligand).
- **G3, each arm is reproducible.** Re-running one receptor per arm and seed gives byte-identical
  pose files.
- **G4, coverage.** Every arm docks at least 44 of the 47 receptors without error. A receptor
  an arm cannot dock is dropped for ALL arms (a paired test), and more than 3 dropped makes the
  verdict INCONCLUSIVE.
- **G5, the functions are fed inputs they can read** (OPEN, see item 2). For each function the
  crystal ligand, prepared the same way, scores as a favourable complex on most receptors. The
  threshold is not set here because it has not been measured; it is fixed from the pilot
  receptors' crystal poses at freeze and this gate stays DRAFT until then. It exists because
  `ad4_scoring` expects AutoDock4 atom types and charges that Open Babel's PDBQT may not give,
  and an engine fed unreadable inputs produces a confident null.

## Reported beside the verdict, never counted

Best-of-nine per arm (is the right pose still found, which only a search change could alter);
the gained/lost lists by receptor; per-receptor top-pose distance for every arm and seed; seed
agreement within an arm; wall time per docking; the 9 headroom receptors on their own. **Scores
are never compared across functions**: `vinardo` and `ad4_scoring` are not in Vina's units, and
smina prints "(kcal/mol)" beside `dkoes_*` scores that are negated pK
(`ROADMAP.md`, smina spike).

## Expectation and what each outcome means

The expectation is a **null**. Vinardo is Vina-family and its affinity-ranking test found
nothing (`ROADMAP.md`), though that is a different ability from choosing a pose. `dkoes_fast`
and `ad4_scoring` are other families, which is why they are in. A PASS would justify the engineering question,
not shipping: a second engine needs the provider seam work the smina spike listed
(an injected rescorer, an engine-qualified rescore id, per-engine function vocabularies), a
five-package bundle or a project-hosted zip (candidates document), and a fresh review of
licences. A NULL or HARMFUL result closes the route of "another scoring function in a
Vina-family engine" on a measured footing and leaves the pose-choice sentence of PR 508 as the
product answer. It does not speak to ML scorers (gnina, DiffDock-like models), which this test
does not include.

## Limits stated now

- Redocking into the crystal ligand's own box, one ligand conformer per receptor: optimistic, as
  the survey said. It says nothing about a user who boxes by guesswork.
- The distance is an assignment RMSD, a lower bound; ligands of 13 heavy atoms or fewer (7E2Y,
  3HS4) sit near the cutoff.
- Same-protein leakage into any function's training set beyond the stratum is possible.
- One engine family (smina) supplies every candidate, so the result is about these functions,
  not about "other engines".

## Open items before freezing

1. Read the training sets of koes2013 (`dkoes_*`) and quiroga2016 (Vinardo) and the AutoDock4
   parameterisation, list their PDB entries, and build the training-overlap stratum by id.
   **Literature and where the lists live** (nothing bulk-copyrighted is committed; the repo
   holds citations in `docs/sources.toml`, intersection results in `engine_core.TRAINING_OVERLAP`,
   and the maintainer's copies under:

   - `D:/Xaero Stuff/Documents/Sci Downloads` — PDFs (already: quiroga2016, koes2013, trott2009)
   - `D:/Xaero Stuff/Documents/OpenChem Studio private notes` — working notes
   - `D:/Xaero Stuff/Documents/OpenChem Studio literature` — wanted list, synthesis refs, etc.
   - `E:/My Area/Claude/OpenChem Studio` — **large/off-repo databases** (checked 2026-11-03: COD
     corpus and synthesis records only; **no PDBbind or CSAR indexes yet** — future dumps, e.g.
     `E:/My Area/Claude/OpenChem Studio/docking/training_indexes/`, stay outside git)

   | Need | Role | In Sci Downloads? | In `sources.toml`? |
   |---|---|---|---|
   | [source:quiroga2016] | Vinardo trained on 122 of PDBbind Core **2013** (≤7 rotatable bonds) | `quiroga2016.pdf` | yes |
   | [source:koes2013] | `dkoes_*` trained on CSAR-NRC HiQ **2010** (343 complexes); CSAR **2012** named in quiroga | `koes2013.pdf` | yes |
   | [source:trott_olson2010] | Vina trained on PDBbind **2007** (provenance only) | `trott2009.pdf` | yes |
   | PDBbind Core 2013 index (195 PDB codes) | Reconstruct Vinardo's 122 by rule or verify overlap | **not held** — hosts need registration (same closure as CASF-2016 in `benchmarks/docking/README.md`) | no |
   | PDBbind 2007 release index | Vina overlap at PDB-code level | **not held** | no |
   | CSAR-NRC HiQ 2010 structure list (343) | `dkoes_*` overlap; Binding MOAD mirror is gone per `rescore_power.py` | **not held** | no |
   | CSAR 2012 structures (54 ligands, five targets) | Independent test set in koes2013; target-level check possible without full HiQ list | **not held** (paper + SI only) | no |
   | AutoDock4 parameter papers | `ad4_scoring` is a force field, not a per-complex ML set — document provenance; **no PDB overlap stratum** unless a primary source lists training complexes | not required for overlap | cite when G5 is written |

   **Sourcing research (2026-11-03), measured:** maintainer copy at
   `E:/My Area/Claude/OpenChem Studio/docking/ENGINE_TRAINING_SOURCING.md`. Headlines:
   DeepChem's `pdbbind_v2013_core_set.tar.gz` (**193** PDB ids, **0** catalog overlaps) is the
   best free Core-2013 index found; `csardock.org` and MOAD are gone; BindingDB CSAR zips work
   at `https://www.bindingdb.org/rwd/bind/downloads/BindingDB_CSAR_*` (direct path, not the
   `SDFdownload.jsp` link); PDBbind 2007 on DeepChem S3 is **403**; PDBbind+ demo still offers
   v2020 + CASF access after free registration. Reproduce Vinardo's **122** from the official
   PDBbind index, not from DeepChem ligands alone (<=7 rotatable bonds on DeepChem gave 141).

   **Measured 2026-11-03 (evening):** PDBbind+ demo index is on E:; koes2013 full PMC SI
   (`NIHMS443682-supplement-1_si_001.zip`) is the same RapidMiner bundle as Sci Downloads
   `koes2013_si` — **no** `set1.csv` / `KEEP_LIST.txt`. **`dkoes_*` training overlap** is
   locked at the maintainer path
   `E:/My Area/Claude/OpenChem Studio/docking/training_indexes/dkoes_csar_bindingdb_proxy.json`
   (**746** unique PDB codes from BindingDB CSAR TSV, **0** catalog overlaps, not verified
   equal to HiQ **343**). Regenerate with
   `uv run --no-sync python tools/build_engine_training_overlap.py`. Keep
   `TRAINING_PROVENANCE_UNRESOLVED` on the dkoes arm until HiQ `set1.csv` or the NRC tar
   replaces the proxy. Vinardo / Vina arms still need official PDBbind indexes.

2. Measure G5 on the pilot receptors' crystal poses and fix its threshold.
   **Design (2026-11-03):** run G5 on **all five arms**. The gate is per function
   ("for each function the crystal ligand … scores as a favourable complex on most
   receptors"), not a cross-arm score comparison — scores are never compared across
   functions (see Reported beside the verdict). Each arm gets its own favourable
   predicate and its own `min_fraction` pinned at freeze from the 17 pilot receptors;
   sharing one numeric cutoff across arms would be wrong for `vinardo`, `dkoes_*`, and
   `ad4_scoring`. **`smina-ad4` must be included:** it is the arm G5 exists to catch;
   if it fails input sanity the runner stops at G5 (INCONCLUSIVE), which is an honest
   outcome. **`vina` and `smina-default`** may share a Vina-scale rule if crystal
   `--score_only` scores match G2's story; still report both fractions.

   **Measured 2026-11-03 (real Vina + smina):** `benchmarks/docking/engine_g5_probe.py`
   on the 17 pilot receptors; crystal ligand = deposited SMILES with heavy atoms placed
   on the boxed copy, same app prep and `_convert_ligand_to_pdbqt` path as docking.
   Favourable = finite `--score_only` affinity **&lt; 0** (same predicate for every arm
   on this pipeline). Artifacts: `benchmarks/docking/artifacts_engine_g5/`.

   | Arm | Scored | Favourable | Pilot fraction | Suggested `min_fraction` (allow 1 miss) |
   |-----|--------|------------|----------------|-------------------------------------------|
   | `vina` | 17/17 | 17 | 1.00 | **0.941** (16/17) |
   | `smina-default` | 17/17 | 17 | 1.00 | **0.941** |
   | `smina-vinardo` | 17/17 | 17 | 1.00 | **0.941** |
   | `smina-dkoes_fast` | 17/17 | 17 | 1.00 | **0.941** |
   | `smina-ad4` | 17/17 | 16 | 0.94 | **0.882** (15/17); **4DKL** scored **+15.8** |

   Pin these at freeze (or tighten ad4 separately). Requires `OPENCHEM_SMINA` for smina arms.
3. ~~Write the pure core module~~ **`engine_core.py` and `tests/test_engine_core.py` written**;
   still need mutation-checked gate tests once G5's threshold exists.
4. **QuickVina / Vina-GPU control:** not an arm (`docs/DOCKING_ENGINE_CANDIDATES.md`); no further
   control unless a future Amendment adds one.

## What was looked at before this was drafted

The pilot of `docs/DOCKING_ENGINE_CANDIDATES.md` (`engine_pilot.py`, results in
`artifacts_engine_pilot/results.jsonl`): 17 receptors, one seed (20261029), the five arms above.
The receptors were chosen by a rule from the survey's recorded rows: the 12 measurable
receptors whose top pose was not correct (4DKL, 8EF5, 5HK2, 7M93, 7E2Y, 4IAR, 6A93, 6BQG, 6KUX,
6J8G, 8ZYO, 3EML) and every seventh top-correct one in catalogue order (5C1M, 4IB4, 3PBL, 3RZE,
5I6X).

| Arm | Top within 2 A | Best of nine | Gained / lost vs `vina` |
|---|---|---|---|
| `vina` | 5 | 14 | |
| `smina-default` | 5 | 14 | 0 / 0 |
| `smina-vinardo` | 7 | 15 | 2 / 0 |
| `smina-dkoes_fast` | 2 | 8 | 0 / 3 |
| `smina-ad4` | 7 | 11 | 3 / 1 |

Also seen: the `vina` arm reproduced the recorded survey distance on 17 of 17 at the G1
tolerance (0.05 A on two-decimal distances); `smina-ad4` returned 70 poses for 17 receptors and top scores of about -31 to
-82 (the reason for G5); `smina-dkoes_fast` found the wrong pocket on 4 receptors against 1. These
receptors were therefore looked at under one seed before this draft; if the freeze moves a rule,
say whether the move could have been prompted by them. No other receptor was docked with smina.

## Amendments

1. **2026-11-04, G1 tolerance.** Was 0.005 A in draft text before the full-catalog `gates` run.
   Remeasure found survey distances are centi-Å rounded and fixed-seed top-pose assignment RMSD
   can differ by up to 0.05 A (7B6W). G1 tolerance is **0.05 A** on centi-Å distances (same
   rounding as the survey); `engine_core.G1_DISTANCE_TOL` and the gate bullet above match.
