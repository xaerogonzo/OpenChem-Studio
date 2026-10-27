# Numerical frequencies for the radicals an analytic Hessian cannot be trusted on (protocol v3), and a halogen arm: preregistration

**Status: DRAFT, written 2026-10-26. NOT FROZEN. Arms C and D have not been computed, and nothing in this file changes a verdict that was already given.** Section 10 lists what must happen before it is frozen. A calibration that was run on spent data is reported in section 5.

## 1. What this is, and what it is not

The bond-dissociation benchmarks (`benchmarks/bde/PREREGISTRATION.md`, PARTIAL; `benchmarks/restart_v2/PREREGISTRATION.md`, held-out arm PASS, stress arm DO NOT ADOPT) both lost the S-H bond of the thiyl radicals to an imaginary mode that no restart removed. **Their verdicts stand and nothing here re-judges them.** This asks a narrower question that the probe in `benchmarks/thiyl_probe/` opened: is the imaginary mode real, and if it is not, can the calculator get a value for those bonds without a new kind of risk?

It is **not** a way to improve a score: Arm C is a set of bonds nobody has computed, Arm D is reported and decides nothing, Arms A and B are made on bonds whose results are spent and are labelled so.

## 2. What was seen first (disclosure)

Everything in this section was observed BEFORE this file was written, in this order, and it is why the rule below looks as it does.

1. The first run lost methanethiol's S-H (radical lowest mode -1328 cm-1 after the one `Calc_Hess` re-run); the stress set lost both ethanethiyl radicals (-332, -370); the displaced restart made the methyl radical's mode worse (-1743, -1553) and left its energy where it was (`benchmarks/restart_diagnosis/`).
2. **The probe** (`benchmarks/thiyl_probe/README.md`, 2026-10-25) reran the benchmark's own frequency job at the recorded final geometry of the three thiyl radicals and changed one thing at a time. The analytic Hessian reproduces the imaginary mode; **a numerical Hessian does not have it** (CH3S's lowest mode is +601 cm-1) and agrees with the analytic one on every other mode to about 10 cm-1; B3LYP's analytic Hessian does not have it; the wavefunction is stable but its softest orbital-rotation direction (0.0005 to 0.0015 Eh) is 100 times softer than the next; four starting guesses reach energies that agree to 10 microhartree. **The mode is spurious and the analytic radical enthalpy is wrong by 0.85 to 1.03 kcal/mol for these radicals.**
3. **Three radicals that passed** were run the same way. Methoxy (CH3O, methanol's O-H) has a quiet analytic error: one mode 208 cm-1 from the numerical value and an enthalpy 0.27 kcal/mol different, with no imaginary mode to flag it (smallest stability eigenvalue 0.0049). HOO (0.036) and CH2SH (0.128) agree to 3 and 46 cm-1 and 0.01 and 0.03 kcal/mol.
4. **The calibration** (section 5) was then run on every radical the two benchmarks accepted. Its table is the only thing the trigger rule in section 3 (R2) is allowed to read, by the procedure written there.
5. **The references for Arm C** (`benchmarks/bde_heldout/extract_atct_halogen.py`) were chosen from the saved ATcT 1.228 table's names and formulas alone and their enthalpies read afterwards; the six DH298 values are in section 6. **No Arm C bond has been computed.**
6. **S-H cannot be a held-out arm** (section 7): the table holds no ordinary thiyl radical, and Luo's handbook (Table 8.1, PDF pages 454 to 459) has a recommended value for only hydrogen sulfide and methanethiol, both already in the first run.
7. **The integration grid was tested as a cause (2026-10-27, after the calibration) and is not the cause.** `probe.py` variants `freq_intacc6`, `freq_defgrid2` and `sp_stability_intacc6` on methylthiyl and one ethanethiyl conformer, at the benchmark's geometry. A FINER grid (`IntAcc 6.0`, Lebedev-590 at the final grid) leaves the imaginary mode (CH3S -1293 against -1332 cm-1; C2H5S -323 against -332) and the stability eigenvalues (0.00048 and 0.00155 Eh). A COARSER grid (`DefGrid2`) removes the imaginary SIGN but not the error: CH3S's six modes come out 742, 875, 1169, 1337, 1477, 1601 against the numerical 601, 741, 860, 1334, 1336, 1476, and ethanethiyl's 478 and 911 against 526 and 974. **So a loud error became a quiet one, which is the case R1 cannot see.** The cause inside ORCA's analytic Hessian is still not isolated; nothing here says which grid is "right". Records: `benchmarks/thiyl_probe/artifacts/*/summary.json`.
8. **The bromine literature was read (2026-10-27)**: Seetula 2003 (CH2Br, CHBrCl), Seetula and Eskola 2008 (CHBr2, CH3CHBr) and Seetula 2000 (ab initio, 19 radicals). Section 6 and decision D5 record what they offer. Nothing has been computed.

## 3. The v3 rule (everything here is fixed once frozen)

v3 is v2 (which is v1 plus the displaced restart) **plus one additional stage for a RADICAL (a doublet) at its accepted or final geometry**. Nothing changes for a closed-shell structure.

* **R1, the imaginary-mode trigger (fixed now).** A radical whose lowest analytic frequency is still below -20 cm-1 after v1's `Calc_Hess` re-run, and whose skeleton is intact, gets ONE numerical frequency job at **the geometry of that re-run**: `! M062X def2-TZVPD TightSCF DefGrid3 NumFreq` (same functional, basis and grid; `%pal nprocs 4`, `%maxcore 3000`; charge 0, multiplicity 2, unrestricted). v2's displaced restart is **not** applied to it first: the probe shows there is no saddle to leave.
  * **Accepted** when the numerical lowest frequency is >= -20 cm-1. Its enthalpy is that job's own `Total enthalpy` (298.15 K, 1 atm), at the same electronic energy.
  * **Not accepted** when it is below -20 cm-1: the mode is real, v2's displaced restart is then applied exactly as written in `benchmarks/restart_v2/PREREGISTRATION.md` section 3, and the species is a missing cell if that fails too.
* **R2, the stability trigger (decided mechanically after section 5, never by eye).** Every radical gets a stability analysis (`%scf StabPerform true end`, a single point at its final geometry, 15 seconds to 4 minutes) and the smallest eigenvalue `e` is recorded. If section 5's rule (below) found a threshold `T`, a radical with `e < T` gets the same numerical job as R1 whether or not an imaginary mode appeared, and its enthalpy is the numerical one. **If section 5 did not find a clean threshold, R2 is not part of v3, and a radical with `e` below the lowest eigenvalue seen in a radical that agreed with its numerical Hessian is reported with the warning "the analytic frequencies of this radical were not verified" and its value is kept.** The step is a trigger and an arbiter, never a way to drop a value.
* **The cost cap (a decision for Alex, section 9, D1).** A numerical Hessian is 6N gradients, which is hours for a radical of more than about 12 atoms. v3 as preregistered applies R1 and R2 to radicals of **at most 12 atoms**; a larger one is not given the numerical job and is reported "analytic frequencies not verified". The calibration measured radicals of at most 9 atoms only (section 5), so **v3 makes no claim about radicals of 10 to 12 atoms beyond what the 9-atom ones suggest.**
* **Units, records.** Each job writes the v2 record fields plus `stage` (`stability`, `numerical`), the smallest `stability_eigenvalue`, and `analytic_enthalpy` beside `enthalpy` for a radical the numerical job replaced, so the effect of the replacement is always readable. A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`, `benchmarks/restart_v3`, `benchmarks/thiyl_probe`, `benchmarks/bde`, `benchmarks/bde_heldout` or `benchmarks/restart_v2` (their `artifacts/` excluded).

## 4. Arms

* **Arm A, the calibration (done, section 5):** radicals the first run and the held-out arm accepted, at their recorded final geometries; analytic against numerical frequencies. Spent data; decides only the threshold `T`, by the procedure in section 5.
* **Arm B, the regression arm (descriptive, no verdict):** the first run's and the held-out arm's accepted radicals of at most 9 atoms, re-scored with their numerical enthalpy wherever v3 would have used one. It reports how much each bond's error moved and whether any verdict's number crossed its limit; **the old verdicts stand whatever it shows**, because these bonds are not held out. Computed from Arm A's jobs: no new ORCA run.
* **Arm C, the halogen arm (held out, deciding):** the six C-H bonds of section 6, never computed. Read by the held-out arm's own rule (section 8).
* **Arm D, the thiol S-H bonds (reported only, deciding nothing):** methanethiol's S-H (the first run's lost bond; spent) and ethanethiol's S-H (no recommended value, section 7), computed with v3, so the effect of R1 on a thiyl radical is on record.

## 5. Arm A: the calibration (run 2026-10-26 on the radicals both benchmarks accepted)

**What was run.** `benchmarks/thiyl_probe/calibrate.py` (stability analysis of all **65** accepted radicals of the first run and the held-out arm; analytic and numerical frequencies for the **41** its selection rule picked, which excludes the **15** radicals of 10 to 14 atoms: the secondary and tertiary alkyl, n-propyl and n-butyl, the propoxyls and tert-butoxyl, phenyl, benzyl, phenoxyl, benzoyloxyl and tert-butylperoxyl radicals). The full table is `benchmarks/thiyl_probe/calibration/calibration_table.json`, with `stability.json`, `numfreq.json`, `selected.json`, `radicals.json` and the ORCA inputs of the radicals named below. ORCA's own output files are kept outside Git (their banner trips the repository's product-name guard); the numbers read from them are in the JSON.

**One selected radical produced no measurement and is not in the table.** Methyl hydroperoxide's C-H radical (`heldout_methyl_hydroperoxide_C_H_Hydroperoxymethyl`) crashed in ORCA's coupled-perturbed SCF step (`orca_scfresp_mpi`, exit code 0xc0000409, "Failed to write HEADER of job.cpscfvec"), and was rerun once, with the same result. Its numerical job started and stalled after its first displaced SCF (no file written for 8 hours until it was killed). It is listed in `unmeasured.json` and counted below as unmeasured, not as non-material. So the table has **40** radicals, not 41.

**The table, read by the rule below (2026-10-27).** Of the 40 measured radicals, **4 are material and 36 are not.** The material four:

| radical | atoms | smallest stability eigenvalue `e` (Eh) | enthalpy shift (kcal/mol, numerical minus analytic) | largest mode difference (cm-1) | why material |
|---|---|---|---|---|---|
| methoxy (methanol O-H) | 5 | 0.00487 | +0.272 | 208.4 | both |
| ethoxyl (stress set) | 8 | 0.00611 | +0.175 | 101.6 | mode |
| acetyloxyl (acetic acid O-H) | 7 | 0.02587 | -0.638 | 113.1 | both |
| acetyl (acetaldehyde formyl C-H) | 6 | 0.08728 | -0.658 | 136.4 | both |

* The largest material `e` is **0.0873** (acetyl). The smallest non-material `e` is **-0.00149** (the SH radical of hydrogen sulfide), and **18 of the 36** non-material radicals have `e` at or below 0.0873. Four non-material radicals have a smaller `e` than any material one (the SH radical -0.00149, the OH radical of water 0.00018, azide 0.00130 and the cyanooxidanyl radical 0.00211).
* **The two groups overlap, so by step 3 of the rule `T` does not exist and R2 is not in v3.** The smallest stability eigenvalue does not predict which radicals carry an analytic error. The material four are not even among the lowest `e`: the largest error in the table (acetyl, -0.66 kcal/mol) belongs to a radical whose `e` is 0.087, higher than that of half the radicals with none.
* Under section 3's fallback sentence (a radical with `e` below the lowest `e` of a radical that AGREED with its numerical Hessian is flagged "not verified"), the lowest such `e` is -0.00149, which is the lowest in the table, so **the fallback flags nothing**: R2 contributes neither a trigger nor a warning, and the answer to "when are the analytic frequencies not trustworthy" rests on R1 alone.
* **The methanethiyl and ethanethiyl radicals are not rows of this table**, because the benchmarks that produced it refused them (the imaginary mode). Their `e` (0.0005 and 0.0015, `benchmarks/thiyl_probe/artifacts/`) are within the range of non-material rows (water, azide), so adding them as material rows would change nothing about the overlap.
* **What R1 alone misses**: the material four are radicals with no imaginary mode after the re-run, so R1 would not have given any of them a numerical job. That is 4 of 40 (10%) measured radicals with an analytic enthalpy off by 0.17 to 0.66 kcal/mol; the held-out arm's standard error was 0.25. This is the cost of keeping R1 and no R2, stated here so it is not discovered later.
* **A caveat on R1's acceptance threshold (-20 cm-1)**: for the acetyloxyl and acetyl radicals the *numerical* lowest frequency is itself below it (-95.2 and -29.7 cm-1, against +17.9 and +106.7 analytic). Both are floppy radicals, and a numerical Hessian on a soft torsion is not obviously the better answer. Under R1 as written such a result would be "not accepted" and sent to v2's displaced restart. This is a property of the rule as drafted, not something the calibration decided, and it is part of what Alex is asked in D2 (section 9).
* **Sample sizes**: 40 radicals (4 material, 36 not), of at most 9 atoms; none of 10 to 14 atoms was measured (15 radicals), so nothing here speaks to them.

**The rule that reads the table, fixed before the table was read.**
1. A radical is **material** when the absolute analytic-to-numerical enthalpy shift is at least **0.25 kcal/mol** (the standard error of the mean error of the held-out arm; a shift below it cannot be told from noise in a verdict) **or** its largest mode difference is at least **100 cm-1**.
2. If every material radical has a smaller `e` than every non-material one, `T` is the **geometric mean** of the largest material `e` and the smallest non-material `e`, rounded to one significant figure. R2 is in v3 with that `T`.
3. If the two groups overlap, **R2 is not in v3** (section 3).
4. The table, `T` or the statement that none exists, and how many radicals of each kind there were are written into this section before the freeze, with the sample sizes. **A threshold from fewer than three material radicals is stated as resting on that few.**

## 6. Arm C: the references

The six bonds, from `benchmarks/bde_heldout/candidates_halogen.json` (ATcT 1.228, kcal/mol, with the table's uncertainty): chloromethane C-H to chloromethyl **99.41 +- 0.21**; dichloromethane C-H to dichloromethyl **96.20 +- 0.23**; chloroform C-H to trichloromethyl **93.31 +- 0.22**; fluoroform C-H to trifluoromethyl **106.67 +- 0.14**; formyl fluoride C-H to fluoroformyl **101.38 +- 0.12**; formyl chloride C-H to chloroformyl **90.95 +- 0.20**. The rule that chose them is in `extract_atct_halogen.py`; `tests/test_bde_heldout_halogen.py` fails if a seventh bond appears, if one overlaps the first run or the first held-out arm, or if one is not a C-H bond of H, C, O, F and Cl.

**What the table does not hold, and so what Arm C cannot test:** no fluoromethyl, difluoromethyl, bromomethyl or tribromomethyl radical, and no chloroethyl, halovinyl or halophenyl radical; **bromine is therefore not tested at all**, and nothing here supports a claim about a C-H bond outside a halomethane or a formyl halide.


**Candidate bromine bonds, from the literature and NOT from ATcT (read 2026-10-27; NOT adopted, see D5).** The saved ATcT table holds 44 gas-phase species with carbon and bromine and no bromo radical of the kind needed, which is why the six bonds above have none. Three papers by one laboratory measured the C-H bond energy directly, from the forward and reverse kinetics of R + HBr = RH + Br in a photoionization mass-spectrometer reactor (second-law; the reverse-reaction kinetics were taken from earlier work):

| bond | C-H bond energy (kJ/mol) | in kcal/mol | source |
|---|---|---|---|
| bromomethane to bromomethyl | 427.2 +- 2.4 | 102.10 +- 0.57 | Seetula 2003 (`10.1039/b210787m`) |
| bromochloromethane to bromochloromethyl | 406.0 +- 2.4 | 97.04 +- 0.57 | Seetula 2003 |
| dibromomethane to dibromomethyl | 412.6 +- 2.7 | 98.61 +- 0.65 | Seetula and Eskola 2008 (`10.1016/j.chemphys.2008.04.008`) |
| bromoethane (alpha C-H) to 1-bromoethyl | 415.0 +- 2.7 | 99.19 +- 0.65 | Seetula and Eskola 2008 |

All four are inside the 1.0 kcal/mol rule for a deciding bond. What reading them showed, and what it does not show:
* **They are one laboratory's kinetic measurements, not an evaluated value.** ATcT combines many determinations; these four rest on one method and one apparatus. The bond energy is the measured reaction enthalpy plus the H-Br bond energy, so it does not depend on the parent molecule's formation enthalpy (the radical's formation enthalpy does).
* **The 2008 value for the dibromomethyl radical (199.1 +- 2.7 kJ/mol) agrees with the calculations of three theoretical studies** quoted in that paper (196.9 to 201.3) and with a recalculation of an earlier experiment (198.9), and it supersedes the same author's 2000 ab initio value (180 +- 5), which the 2000 paper itself warns is low-accuracy for radicals with several bromine atoms. A fourth theoretical study (191.7 +- 3.0) is lower.
* **Tribromomethyl has no usable value**: only the 2000 ab initio estimate (195 +- 5, plus 2.4 for the method), which fails the 1.0 kcal/mol rule on its own uncertainty, so it is excluded.
* **The calculator's scope does not include bromine**, and nothing here tests heavy-atom effects (spin-orbit coupling, scalar relativity) that M06-2X/def2-TZVPD ignores or treats approximately. A pass would show the unmodified protocol gives an acceptable error on four bromo C-H bonds against these references; it would not show the references are right.

## 7. Why there is no S-H arm

* ATcT 1.228 has no CH3S or CH3CH2S: the thiyl radicals it holds are SH (hydrogen sulfide's, the first run's) and the inorganic HSO and HOS from HSOH and H2SO.
* Luo's handbook (Table 8.1) names a recommended value only for H-SH (91.2) and CH3S-H (87.4 +- 0.5), both in the first run. Ethanethiol's values are 88.6 +- 2, 87.3 and 87.5 (the last two derived or correlated, with no uncertainty given); benzenethiol's range from 79.4 to 83.5 and none is recommended.
* So the S-H class after v3 rests on **two spent bonds and a reported-only third**, and the calculator's S-H value, when it is given, **carries the statement that this class has no held-out validation**. That is a limit of the references that exist, not of the method.

## 8. The reading rule for Arm C (unchanged from the held-out arm; `benchmarks/bde/judge.py` is not edited)

On the six deciding bonds: mean absolute error, mean signed error, largest absolute error, each with the standard error of the mean.
* **PASS:** MAE <= 2.5 kcal/mol, no error above 5.0, |MSE| <= 1.5. **PARTIAL:** not PASS and MAE <= 3.5. **FAIL:** otherwise. **NOT EVALUABLE:** more than one of the six has no computed value.
* **At n = 6 the standard error of the mean error is about 0.25 kcal/mol if the spread resembles the held-out arm's measured one (its standard error was 0.12 at n = 27, a standard deviation near 0.6), and about 0.5 if it is as wide as that arm's preregistration assumed; a result within 0.5 of a limit cannot tell the two sides apart and the report says so.** A PASS here is a statement about these six bonds.
* The bias test of v2 (section 7 there) is **not** applied: six bonds cannot reproduce or refute a mean of -1.5.

## 9. What each outcome does, and the decisions this needs from Alex

* **Arm C PASS or PARTIAL:** the calculator's stated scope may add C-H bonds next to F and Cl (a separate change: the scope check, the sentence and a driven run), with Arm C's error stated beside the first two arms'. **FAIL:** the scope is not extended; the calculator keeps computing such a molecule with the existing warning. **NOT EVALUABLE:** nothing is claimed.
* **R1/R2 and the calculator:** adopting the numerical step in `chem/bond_dissociation.py` is a separate change after this is frozen and run, with its own driven run on real ORCA; until then the calculator is unchanged and S-H still gets no value.

**Decisions:**
* **D1 (the cap, section 3):** at most 12 atoms for the numerical job, or no cap and an hours-long job for a large thiyl. Recommended: 12, with the warning above it.
* **D2 (R2, and what R1 should do about quiet errors):** section 5's rule found NO threshold, so R2 is out as written. That leaves R1 alone, which would have missed 4 of 40 measured radicals (an analytic enthalpy off by 0.17 to 0.66 kcal/mol, no imaginary mode). Options: (a) accept R1 alone and state the 10% as a known limit (recommended: it is what the rule gave, and the calculator's stated error already includes these radicals' analytic values); (b) run the numerical job for every radical of at most 9 atoms (a numerical job costs 2 to 2.7 times the analytic one, 25 minutes at 4 cores for an 8-atom radical, so this is heavy for a calculator and acceptable for a benchmark arm); (c) a trigger that is not the stability eigenvalue, which would be a new rule needing its own calibration on data other than these four. Separately: R1 accepts a numerical result only at -20 cm-1 or above, and two floppy radicals' numerical results fall below it (section 5), so decide whether a numerical result below -20 cm-1 on a soft mode sends the radical to the displaced restart (as drafted) or is reported as unverified.
* **D3 (Arm C's size):** six bonds is a small arm. Accept it as deciding with the larger standard error stated, or hold it as reported-only too. Recommended: deciding, because it is the only fresh data that can exist from these references.
* **D4 (S-H):** accept that S-H stays unvalidated and is labelled so. Recommended: yes; the alternative is a measurement nobody has published.
* **D5 (bromine, new 2026-10-27):** the four candidate bonds in section 6. Options: (a) leave bromine out, as drafted (the calculator stays without bromine in scope); (b) add them as a SEPARATE sub-arm, Arm C-Br, reported with the sources stated and deciding only the bromine claim, so a failure there cannot touch the fluorine and chlorine result; (c) add them to Arm C as deciding. Recommended: (b). They are the only fresh bromine references that exist, but they are not evaluated, so they should not share a verdict with the ATcT bonds. Needs your decision before the freeze, and the bond list is fixed by this section.

## 10. Before this is frozen

1. ~~Section 5 filled from the finished calibration, and `T` (or its absence) decided by the written rule.~~ **Done 2026-10-27: no `T`; R2 is out.**
2. Alex's answers to D1 to D4.
3. The runner: `run_restart.py` extended with the stability and numerical stages, `restart_core.py` with the trigger and the acceptance rule (pure, tested against the probe's real ORCA outputs), and an independent read against this text, as v2's was.
4. Not done and not planned here: phosphorus (no usable species in the table), silicon (three bonds, one an O-H, outside the calculator's elements), bromine (no radical), and any molecule of more than nine heavy atoms (the first held-out arm's largest parent has four heavy atoms, and the experimental references for larger molecules that Luo's handbook prints are scattered and mostly not recommended).
