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

## To run the primary-arm ORCA benchmark (as recorded 2026-10-19, before the result above)

The runner is written, tested on real CN-radical and H-atom output and committed (`benchmarks/bde/run_bde.py`, `tests/test_bde_runner.py`); (as written before the run; it has since been run, see above). It builds 68 structures (32 parents, 35 radical starts, the hydrogen atom); the run time is **unmeasured**. Run it after the proton-affinity run, never beside it (both want the cores):

```bash
uv run --no-sync python benchmarks/bde/run_bde.py structures
uv run --no-sync python benchmarks/bde/run_bde.py run --workers 3 --cores 4     # resumable
uv run --no-sync python benchmarks/bde/run_bde.py status
uv run --no-sync python benchmarks/bde/run_bde.py report                        # report.txt, verdict.json
```

Same rules as the proton-affinity run: no edit to `src/` between the first job and the report, one stage at a time, no threshold changed after the report is seen, the DLPNO arm only if the primary arm passes.
