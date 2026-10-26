# Homolytic bond dissociation enthalpy from ORCA: design (2026-10-19)

Status: **thresholds approved by Alex 2026-10-19; preregistered in `benchmarks/bde/PREREGISTRATION.md` (frozen when its runner is committed); nothing is run.** The third reactivity calculator of Phase 3 (after Fukui and proton affinity), behind a preregistered gate; "measured, not shipped" is an accepted outcome. This note records what was decided with Alex, what the one reference source says, and the thresholds proposed for approval. The preregistration is written after the thresholds are approved, as it was for proton affinity.

## What is computed, and what is never claimed

* **The bond dissociation enthalpy at 298.15 K, DH298(R-H) = H(R.) + H(H.) - H(RH)**, each H a total enthalpy at 298.15 K and 1 atm, the same quantity as Blanksby and Ellison's `DH298`. Not D0, not De, not a Gibbs energy, and never an electronic-energy difference. [source:blanksby2003]
* **X-H bonds only** (Alex, 2026-10-19). C-C, C-Hal, C-O and C-N bonds are a later class with its own preregistration, so one failure cannot sink the other.
* **Closed-shell neutral parent, doublet radical, unrestricted Kohn-Sham.** Radicals of the benchmark's own bonds only; no biradicals, no charged species, no open-shell parents (so CH3, CH2, OH, NO, HONO are out).
* The hydrogen atom is computed, not tabulated: `H(H.) = E(H atom, same method and basis) + (5/2) RT` (translation only, `1.4812` kcal/mol, the same term `benchmarks/proton_affinity/pa_core.py` derives for the proton).

## The reference (Table 1 of Blanksby and Ellison 2003, read from the page image)

Experimental `DH298` with the stated uncertainty, in `benchmarks/bde/reference_values.json`: **33 bonds**. The **25 whose stated uncertainty is at most 1.0 kcal/mol decide** (methane through silane, the alkane C-H classes, ethene, ethyne, benzene, propene allylic, toluene benzylic, the alcohol O-H and C-H, the thiol S-H, H2S, NH3, H2O, the two peroxide O-H, formaldehyde, acetaldehyde formyl, HCN, SiH4); the **8 with an uncertainty above 1.0** (acetaldehyde's methyl C-H, phenol, the two hydroperoxides, the three acids, methanethiol's C-H) are **reported, never deciding**, because a reference this loose cannot tell a good calculation from a bad one. The stratum is set by the reference's own uncertainty, not by what the calculation gives. Formic acid's `>=96` is an inequality and is left out.

## Protocol, primary arm (same as proton affinity)

M062X/def2-TZVPD, `TightSCF TightOpt DefGrid3 Opt Freq`, ORCA 6.1.1, radicals as `* xyz 0 2` (UKS), the parent as 0/1. Each species: ETKDG seed 7 (30 conformers), MMFF94, dedupe by all-atom RMSD 0.5 Angstrom, the lowest three within 5 kcal/mol optimized; **a radical's starts are the parent's kept conformers with the hydrogen deleted**, so the radical is not embedded as a closed-shell guess. The lowest-H structure of each species, independently; no Boltzmann average. A frequency below -20 cm-1 is not accepted (one retry with an initial Hessian). The hydrogen atom: one UKS single point of the same method.
**Reported for every radical, deciding nothing:** the `<S**2>` (0.75 is a clean doublet), flagged above 0.80. (A per-atom spin-leakage flag was considered and dropped from the preregistration: it needs a population analysis this benchmark does not otherwise run.)
No symmetry-number issue: the quantity is an enthalpy.
The secondary arm (DLPNO-CCSD(T)/def2-QZVPPD single points on the same geometries with the DFT thermal corrections) is the same one as for proton affinity and is only run if the primary arm passes.

## What the literature says about accuracy (read so far, and what it does not cover)

* **The reference's own uncertainty** for the deciding bonds is 0.008 to 1.0 kcal/mol, the median about 0.4. No threshold below sits under it.
* **Zhao and Truhlar 2008 (the M06 suite), their Table 5, the ABDE4 database** (four alkyl bond energies, R-CH3 and R-OCH3 with R = methyl and isopropyl, **De, electronic, not an enthalpy**, 6-311+G(3df,2p) single points on B3LYP/6-31G(d) geometries; read from the page image): **M06-2X MSE +0.27, MUE 0.74 kcal/mol**; M05-2X -0.18 and 0.61; BMK -1.37 and 1.67; M06 -1.90 and 1.90; **B3LYP -8.62 and 8.62**, PBE -3.98. [source:zhao2008] These are C-C and C-O bonds, a harder class for a density functional than X-H, and a different quantity (De), so it is evidence about the functional, not a transferable error bar.
* **Trung, Mechler, Hoa and Vo 2022** (17 functionals, **experimental** reference, aromatic X-H bonds; 6-311+G(3df,2p) single points on B3LYP/6-31G(d) geometries): **M06-2X MUE 1.3 (C-H, 11 bonds, max 3.2), 1.2 (N-H, 9 bonds, max 2.9), 1.2 to 1.4 (O-H, 10 bonds, max 3.2 to 3.4), 1.1 (S-H, 9 bonds, max 5.4); averaged over the four classes MUE 1.2, MaxAE 3.7.** B3LYP is several kcal/mol worse. These are large aromatic molecules whose experiments are less certain than a small molecule's. [source:vo2022]
* **St. John et al. 2020** (the ALFABET database): against **368 experimental bond enthalpies** (iBond), gas-phase enthalpies at 298 K with unscaled ZPE and thermal corrections after a conformer search, **M06-2X/def2-TZVP has MAE about 2.1 kcal/mol, the same as DLPNO-CCSD(T)/cc-pVTZ** (their Fig. 1a, read from the text layer, not the image), beating B3LYP-D3 and wB97X-D; the authors say this approaches the experimental uncertainty. That set mixes X-H and X-Y bonds and large molecules, and its experimental scatter is bigger than ours. This is the closest published match to **our protocol** (the same functional and a triple-zeta basis, enthalpies at 298 K). [source:stjohn2020]
* **Mardirossian and Head-Gordon 2017** (MGCDB84, per-set MAD in their SI, against **CCSD(T)/CBS-type references**, not experiment): **M06-2X MAD 1.83 kcal/mol on BDE99nonMR** (99 bond dissociation energies of non-multireference species), 2.50 on HAT707nonMR (hydrogen-atom transfer); against 6.32 and 5.08 on the multireference sets BDE99MR and HAT707MR, where M06-2X is unreliable. B3LYP 3.19 and 3.08 on the non-multireference sets. [source:mardirossian2017] **This is why the deciding set is closed-shell parents with ordinary radicals** and why the preregistration will say that a multireference-looking species (here possibly HCN's radical, H2O2, HOO.) may behave worse.
* **Not found:** GMTKN55 (`goerigk2017_si.pdf`) carries no organic R-H set; its two bond sets (ALKBDE10, YBDE18) are different bonds.

## Thresholds (revised after reading these three; approved 2026-10-19; the same shape as proton affinity's rule)

On the **25 deciding bonds**, error = calculated - experimental in kcal/mol:

* **PASS:** MAE <= **2.5**, no error above **5.0**, |MSE| <= **1.5**.
* **PARTIAL:** not PASS and MAE <= **3.5**.
* **FAIL:** otherwise.
* **NOT EVALUABLE:** more than **three** of the 25 have no computed value.
* The 8 loose-reference bonds, and all 33 together, are reported in the same statistics and decide nothing.

**Why these changed from the first proposal (2.0 / 4.0 / 3.0).** The published M06-2X errors, now read, are 1.1 to 1.4 (aromatic X-H against experiment), 1.83 (BDE99nonMR against theory), **2.1 (the broad experimental set with our own protocol)** and 0.74 (ABDE4, De). A limit of 2.0 sits *below* the 2.1 that this exact protocol scored on a broad set, so a correct implementation behaving as published could fail it; 2.5 is about 1.2 times the worst published figure and twice the typical one, the same margin proton affinity's 2.5 had over its 1.2-1.75. The maximum of 5.0 is above Vo's worst class maximum for M06-2X (5.4 for S-H, 3.7 on average) only for the S-H class, which is not in this set (H2S and CH3SH are); 5.0 stops one wild bond hiding in a good mean without failing a method that behaves as published. The 1.5 limit on the mean signed error catches a systematic bias.

## What a verdict does

PASS: the calculator is built (a service-level sequence, experimental, needing approval at first), offered only for the X-H classes the benchmark covers and with its error stated. PARTIAL: the failing bonds are named and Alex decides. FAIL: nothing is built; the report is the deliverable. NOT EVALUABLE: nothing is claimed; the cause is fixed and the benchmark re-run under a new preregistration.

## Order of work

1. This note, and Alex's approval of the thresholds.
2. `PREREGISTRATION.md`, `bde_core.py` (the arithmetic) and `judge.py`, tested on synthetic data before any job.
3. The runner (the proton-affinity runner's structure, radical starts from the parent), tested on real output, committed, **not run** until Alex says so.
4. The overnight run, then the report.
5. Only then, on a PASS, the calculator in the application.

## Result: the primary arm was run on 2026-10-20/21 and is PARTIAL

Run on commit `6ec0fd29f72945b1f708d67dfe95050fb20656bc`, clean `src/`, one commit in every record, ORCA 6.1.1, `run --workers 3 --cores 4`, nothing else heavy on the machine (the proton-affinity run had finished first). **Wall time 10 h 35 min** (20:14:58 to the last record at 06:49:33; 38,075 s; the jobs' own time sums to 29.4 h, which over three workers is 9.8 h). 68 structures, 72 jobs (four re-runs with `Calc_Hess`), 65 structures accepted; the longest job was 2.2 h (limit 4 h). Records: `benchmarks/bde/artifacts/primary/runs.jsonl`; report and verdict beside them.

The judge's output (preregistered rule, unchanged), kcal/mol:

| | n | MAE | MSE | largest | missing | |
|---|---|---|---|---|---|---|
| 25 deciding bonds | 22 | 1.76 | -1.53 | 4.57 | 3 | **PARTIAL** |
| 8 loose-reference bonds (reported) | 8 | 1.24 | +0.07 | 2.32 | 0 | decides nothing |
| all 33 | 30 | 1.62 | -1.10 | 4.57 | 3 | decides nothing |

**Why PARTIAL, by the rule:** MAE 1.76 <= 2.5 and the largest error 4.57 <= 5.0 both pass, and three missing is within the allowed three (a fourth would have made it NOT EVALUABLE). **|MSE| = 1.53 exceeds the 1.5 limit**, so the arm is not PASS; MAE <= 3.5 makes it PARTIAL. The miss is by 0.03 kcal/mol and is a systematic bias, not scatter: of the 22 computed deciding bonds, 21 are below the experimental value (all but HCN's C-H, +2.53), i.e. the calculation underestimates the bond enthalpy by about 1.5 kcal/mol on average. The verdict stands as the judge gave it.

**Missing cells (all three in the deciding stratum), by the preregistered rule:**
* ethanol O-H: its radical kept a vibration at -105.8 cm-1 after the `Calc_Hess` re-run (-109.9 before);
* toluene benzylic C-H: the toluene *parent* kept -49.4 cm-1 after the re-run (-59.7 before), so the bond has no parent;
* methanethiol S-H: its radical (CH3S) converged to a stationary point with an imaginary mode of -1306 cm-1 (-1328 after the re-run), which is a saddle point, not a minimum.
Nothing was repaired or re-started from other geometries: that would be a protocol change. Acetic acid's radical failed the -20 cm-1 rule once (-71.6) and passed after the re-run.

**By class (reported, in no rule):** C-H n=15 (1 missing) MAE 1.32, MSE -0.89; O-H n=8 (1 missing) MAE 1.52, MSE -0.38; N-H (ammonia, n=1) -1.16; S-H (H2S, n=1, methanethiol missing) -1.39; Si-H (silane, n=1) -2.92; **peroxide O-H n=4 MAE 2.79, all four negative, methyl hydroperoxide -4.57 (the largest error of the run)**, which is the class Mardirossian's multireference warning pointed at. **Spin contamination: no radical's `<S**2>` is above 0.80** (largest 0.789, phenol, a loose-reference bond), so the errors are not explained by it. HCN's C-H (+2.53) is the only positive error in the deciding set.

**Not computed:** the effect of lowest-structure against Boltzmann averaging, and time per job by bond, were named in the preregistration as reported items but are not produced by `run_bde.py report`; they were not computed by hand afterwards (the per-job records are committed).
The peak load was not measured; 12 cores (3 workers x 4) and `%maxcore 3000` per core were configured, up to about 9 GB.

**What this does under the preregistration:** PARTIAL means the failing cells are named (above), **nothing is built**, and whether a calculation with a stated larger error is wanted is Alex's decision. The secondary DLPNO-CCSD(T) arm is run only if the primary arm passes; it did not, so it was neither written nor run.

## Exploratory rerun of the dropped structures (2026-10-21; not a benchmark record)

After the verdict, the three structures that cost the deciding set its missing bonds (ethanol's radical, toluene, methanethiol's radical) and water's H3O+ from the proton-affinity run were re-optimized from a geometry displaced along their most imaginary mode (`benchmarks/restart_diagnosis/`). **H3O+ is repaired in both directions** (a real minimum matching the preregistration's smoke-run value); **ethanol's radical and toluene are repaired in one direction each** (the surface is flat along the soft mode: the energies agree to 1e-5 Eh, but the ethanol radical's enthalpy moves by 0.7 kcal/mol between the saddle and the minimum); **methanethiol's CH3S radical is not**: displacement made the imaginary mode larger (-1744, -1553 cm-1) and the energy did not change, so the mode is not a real instability and a different treatment is needed (its near-degenerate electronic state is a suspicion, unchecked). The bond enthalpies this would give are 102.8 for ethanol O-H, 90.4 for toluene's benzylic C-H and 84.0 for methanethiol's S-H, **after the verdict was seen and from a protocol designed after it, so they move nothing**: the PARTIAL stands, and the protocol that would be tested properly is `benchmarks/restart_v2/PREREGISTRATION.md` (a draft).

## To run the primary-arm ORCA benchmark (as recorded 2026-10-19, before the result above)

The runner is written, tested on real CN-radical and H-atom output and committed (`benchmarks/bde/run_bde.py`, `tests/test_bde_runner.py`); (as written before the run; it has since been run, see above). It builds 68 structures (32 parents, 35 radical starts, the hydrogen atom); the run time is **unmeasured**. Run it after the proton-affinity run, never beside it (both want the cores):

```bash
uv run --no-sync python benchmarks/bde/run_bde.py structures
uv run --no-sync python benchmarks/bde/run_bde.py run --workers 3 --cores 4     # resumable
uv run --no-sync python benchmarks/bde/run_bde.py status
uv run --no-sync python benchmarks/bde/run_bde.py report                        # report.txt, verdict.json
```

Same rules as the proton-affinity run: no edit to `src/` between the first job and the report, one stage at a time, no threshold changed after the report is seen, the DLPNO arm only if the primary arm passes.

## The calculator (2026-10-23): what Alex decided and what it states

The first run was PARTIAL and the rule said building was Alex's decision; he decided the calculator is wanted ("I would like to fix anything if it can be fixed"), so after the displaced restart (`benchmarks/restart_v2/`: not adopted, thiyl radicals not rescued) and the held-out arm (**PASS**, 27 ATcT bonds, mean absolute error 1.25, mean signed -1.25, nothing missing) the calculator is built **with the first run's protocol unchanged**, in three stacked changes like proton affinity: the chemistry (`src/openchem/chem/bond_dissociation.py`, held to both benchmarks' records by `tests/test_bond_dissociation_calculation.py`), the service sequence, and the registered calculator with the panel button, help and a recorded driven run on real ORCA.

**What a result states, beside every number** (`BENCHMARK`, recomputed from the committed records by a test): 49 deciding bonds in all (the first run's 22 computed against Blanksby and Ellison, the 27 held-out against ATcT), mean absolute error **1.48 kcal/mol**, mean signed error **-1.38** (the calculation runs LOW, and only HCN's C-H is above its reference), largest 4.57; by class C-H 32 bonds MAE 1.28, N-H 7 bonds 1.02, ordinary O-H 4 bonds 1.68, and **O-H next to another oxygen or a nitrogen 4 bonds, mean absolute error 3.30, all low, up to 4.57** (hydrogen peroxide, methyl hydroperoxide, hydroxylamine, formaldoxime). **That last class was separated after the results were seen**, which the stated note says; it is a description of what the records show, not a preregistered stratum.
The bias is NOT subtracted: the preregistered bias test did not reproduce the first run's -1.53 on the held-out bonds (-1.25, interval -1.50 to -1.01), so a correction was not supported.

**What it refuses or may not give:** molecules with an element outside H, C, N, O, S (silane, the one Si bond, is out), charged or open-shell ones, more than nine heavy atoms (the largest measured), several components. **A bond whose radical keeps an imaginary mode after the one re-run has no value, named with its reason**: the benchmark lost methanethiol's S-H that way and the stress set's ethanethiyl radicals were not rescued by the displaced restart (0 of 2), so S-H bonds are offered with that warning and one measured bond (H2S, -1.39) is not an error bar.
**The headline is one number**, the weakest bond among those computed (the bonds chosen are listed, and a bond with no value is listed beside it with its reason); the per-bond values are in the result's table. A run computes at most six bonds: each costs up to three radical optimizations on top of the parent's, one after another.

### The driven run on real ORCA (2026-10-23)

`benchmarks/visual/bond_dissociation_run.json` was driven through the real window (the real button, the real bond-choice dialog ticked through its own widgets, ORCA 6.1.1) on commit `44158e14` of the stage-3 branch, clean `src/`, nothing else running ORCA: **VERDICT PASS, 6 of 6 assertions**, 14 minutes. Chloromethane was refused before the dialog opened; cancelling the dialog queued nothing; and the values read back from the STORED result reproduce the first benchmark run's records:

| bond | driven run | first run's record |
|---|---|---|
| methanol C-H (the weakest, the headline) | 397.76 kJ/mol | 397.76 |
| methanol O-H | 429.82 | 429.82 |
| hydrogen peroxide O-H | 355.62 | 355.62 |
| methanethiol S-H | no value: the radical still at -1326 cm-1 after the one re-run | no value (-1328 cm-1) |

**The first attempt at this run FAILED, and the cause was not found (see "Driven twice more and promoted", below, for what two further runs did and did not settle).** On the same code an hour earlier, the refusal and the cancel passed but all three runs failed at their first job: the hydrogen atom's output was handed to the sequence within a second of the job starting, without ORCA's closing line, so the run correctly stopped with "the hydrogen atom's single point failed". The same input runs to completion in ORCA directly, through the real service in a script (HCN, 539.0 kJ/mol) and through the window twice since. It happened while another session's test suite was finishing; nothing in the application's log says what ended the ORCA process. It is recorded here because a run that failed once for an unknown reason is a fact about the run, not something a later pass erases. If it recurs, the drive's wrapper that keeps each job's handed output (used for the passing run) is the way to see it.

## Driven twice more and promoted to LIMITED (2026-10-25)

The recorded driven run was made on the stage-3 branch, before the scope-warning change (#447) reached this calculator, and its first attempt had failed for a cause nobody found. The proton affinity's promotion repeated its drive on the commit it was promoted from, so this one did the same, twice in a row: `benchmarks/visual/bond_dissociation_run.json`, the real window and the real bond-choice dialog, ORCA 6.1.1, **master `c86f3e0a`, clean tree**, no other ORCA job running (I did not control for other sessions' non-ORCA work). Both runs: **VERDICT PASS, 6 of 6 assertions, no application error**, 20 min 42 s and 20 min 31 s.

| bond | run 1 | run 2 | the recorded run of 2026-10-23 |
|---|---|---|---|
| methanol C-H (the weakest, the headline) | 397.76 kJ/mol | 397.76 | 397.76 |
| methanol O-H | 429.8 | 429.8 | 429.82 |
| hydrogen peroxide O-H | 355.62 | 355.62 | 355.62 |
| methanethiol S-H | no value: the radical still at -1326 cm-1 after the one re-run | the same | the same |

The stored values agree to the last digit across the three runs, and the script's charged molecule (tetramethylammonium) is again refused before the dialog opens, and a cancelled dialog again queues nothing.

**What this does and does not settle about the first attempt.** The hydrogen atom's job ending within a second did not recur in these two runs. Two clean runs after one unexplained failure are not an explanation, and the earlier note stands: nothing in the application's log says what ended the ORCA process, and the drive's wrapper that keeps each job's handed output is the way to see it if it returns. It happened while another session's test suite was finishing, which is a reason to run a long BDE job with the machine otherwise quiet, not a finding.

**What the promotion is.** `orca.bond_dissociation_enthalpy` was EXPERIMENTAL and hidden for one stated reason: the benchmarks' verdicts were about the benchmarks' own runner, and this implementation had not been driven through the application. With that recorded it is **LIMITED and shown by default** (`docs/CALCULATOR_MATURITY.md`: a promotion is one change carrying the metadata, the evidence and the changelog entry). It is LIMITED and not STABLE for four stated reasons: the scope is narrow (neutral closed-shell molecules of at most nine heavy atoms of H, C, N, O and S, with a warning and an estimate beyond); the calculation runs about 1.4 kcal/mol low and an O-H next to O or N 3.3 low; an S-H gets no value because its thiyl radical keeps an imaginary vibration; and the held-out arm is one preregistered benchmark, not the independent, stratified result STABLE asks for. Its execution policy is unchanged: a model may not start it without a person's approval.
