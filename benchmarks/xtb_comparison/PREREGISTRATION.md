# xtb against ORCA (and Psi4): what is the tight-binding engine good for? Preregistration

**Status: DRAFT, 2026-10-27, NOT FROZEN. Nothing in it has been run, and no job of any arm exists.** Section 12 lists the decisions that are Alex's to make before this is frozen; until they are made and recorded in section 13, the numbers below are proposals with reasons, not a rule. When frozen, the runner (`run_comparison.py`) and the judge (`judge.py`, tested by `tests/test_xtb_comparison_judge.py`) are committed with it before the first job, the judge being the rule in section 8 as code. Where this text and that code disagree, the disagreement is a defect in one of them and is fixed before any run, never after.

## 1. The question, and what it is not

`chem/xtb_engine.py` runs xtb (GFN2-xTB, GFN1-xTB) as a third engine beside ORCA and Psi4. Its numbers have never been compared with either. This is **not** the Psi4 agreement check (`benchmarks/psi4_agreement/PLAN.md`): there the question was whether two programs compute the SAME calculation under one label, and a milli-hartree was the unit. A tight-binding method is a different, much cheaper calculation that is expected to differ from DFT by kcal/mol, so "agreement" is the wrong word. The question is a **usefulness** one, three claims a person might otherwise assume:

* **C1, geometry:** is an xtb-optimized structure close enough to the DFT-optimized one to be used in its place?
* **C2, relative energies:** are xtb's energy differences between isomers and between conformers close enough to DFT's to rank them?
* **C3, pre-optimizer:** does starting ORCA's optimization from an xtb structure rather than from the force-field structure save ORCA work, and still reach the same minimum?

Each is a claim the application could end up making in its words (a tooltip, a note on a result, a default). The benchmark decides what it may say, in section 9. It does not say which method is right: a DFT reference is itself an approximation, and section 5 says which one and why.

## 2. What is fixed before any job (the only inputs)

* **Programs:** ORCA, Psi4 and xtb as installed on the machine that runs it, versions recorded per job. xtb is the Windows 6.7.1pre build (sha256 `043e578da4a7e114a4d584972959a875e3ffb9f2767a86723b95aa6719d28d9c`, which is also what `tests/fixtures/xtb/` was made with). A different xtb build is a different benchmark.
* **Inputs are the ones the application writes**: ORCA through `OrcaQuantumEngineProvider.build_input`, Psi4 through `Psi4QuantumEngineProvider.build_input`, xtb through `XtbQuantumEngineProvider.build_input`, each run with its own `command_args`, so what is tested is the engine as shipped.
* **Start geometries:** RDKit ETKDG, seed 7, then MMFF, from SMILES; **identical coordinates go into every engine**. The MMFF structure is the start of every optimization arm.
* **Charge and spin:** the molecule's own, a radical unrestricted. xtb is run at GFN2-xTB; GFN1-xTB is run on the neutral closed-shell set as a descriptive aside (section 7).

## 3. The molecules (frozen by this list)

* **Set S (small, 16): the Psi4 agreement set**, so that the engines are compared on molecules already characterized there: water `O`, methane `C`, chloromethane `CCl`, ethanol `CCO`, dimethyl ether `COC`, acetic acid `CC(=O)O`, methyl formate `COC=O`, acetone `CC(C)=O`, propanal `CCC=O`, benzene `c1ccccc1`, pyridine `c1ccncc1`, fluorobenzene `Fc1ccccc1`, thiophene `c1ccsc1`, dimethyl sulfoxide `CS(C)=O`, acetate `CC(=O)[O-]` (charge -1), hydroxyl radical `[OH]` (multiplicity 2). **Judged: the 14 neutral closed-shell molecules.** The anion and the radical are **reported, not judged** (one each cannot support a rule; they are where a tight-binding method is least trusted, so they are shown). Isomer pairs for C2: ethanol / dimethyl ether, acetone / propanal, acetic acid / methyl formate.
* **Set M (medium, 6): molecules a user draws**, within what an ORCA B3LYP/def2-SVP optimization finishes in about an hour: aspirin `CC(=O)Oc1ccccc1C(=O)O`, paracetamol `CC(=O)Nc1ccc(O)cc1`, nicotinamide `NC(=O)c1cccnc1`, caffeine `Cn1cnc2c1c(=O)n(C)c(=O)n2C`, 2-phenylethanol `OCCc1ccccc1`, ethyl acetate `CCOC(C)=O`. All judged (closed-shell neutrals).
* **Set F (flexible, 5), for conformer energies:** 1,2-ethanediol `OCCO`, glycine `NCC(=O)O`, 1,2-dimethoxyethane `COCCOC`, ethyl acetate `CCOC(C)=O`, N-methylacetamide `CC(=O)NC`. **Conformers by rule:** 50 ETKDG embeddings (seed 7), MMFF-optimized, pruned at 0.5 A heavy-atom RMSD, the lowest 6 by MMFF energy kept (fewer if fewer survive). Each is an independent start.
* A molecule on which an engine does not finish (30 minutes per job at most, as in the Psi4 plan) or whose output does not parse is a **missing cell**, never a pass and never dropped silently.

## 4. The arms

* **Arm G (geometry; C1):** from each MMFF start of sets S and M, optimize with **xtb (GFN2, `--opt tight`)** and with **ORCA B3LYP def2-SVP `Opt`** (the application's default preset, its own `opt` calculation). On sets S, the same with **Psi4 B3LYP def2-SVP**. Compared: the all-atom and the heavy-atom RMSD of the xtb structure against the ORCA one after a rigid-body (Kabsch) alignment, and the mean absolute deviation over the bond lengths of the molecule's own bonds (A).
* **Arm R (relative energies; C2):** two decompositions, so a geometry error and an energy error are not confused.
  * *End to end:* the energy difference as each pipeline gives it, GFN2-xTB energy at the xtb structure against the reference energy at the ORCA structure.
  * *Fixed geometry:* GFN2-xTB energy and reference energy both at the ORCA structure.
  Sets: the three isomer pairs of set S, and, on set F, every pair of conformers whose xtb and ORCA optimizations land on the same minimum (heavy-atom RMSD of the two structures at most 0.3 A, a threshold fixed here). **The fraction of conformers that do NOT land on the same minimum is itself a result** and is reported with its list.
* **Arm P (pre-optimizer; C3):** on sets S and M, ORCA B3LYP def2-SVP `Opt` started from (i) the MMFF structure and (ii) the xtb-optimized structure of arm G. Recorded: ORCA's optimization cycles (read from its output), its final energy, and the wall seconds, with the xtb seconds added to arm (ii)'s total. Nothing is tuned between the two starts.
* **Cross-check (reference robustness):** Psi4 B3LYP def2-SVP optimizations on set S. The ORCA-to-Psi4 difference in structure and in the isomer-pair energies is the **reference's own spread**; it is reported beside every xtb number.

## 5. The references, and what they cannot say

* **Primary reference for structures:** ORCA B3LYP def2-SVP `Opt`. It is the application's own default preset, so a result says "xtb against what this application's DFT gives". It has no dispersion correction, and GFN2 has one built in: a conformer-energy difference between the two partly measures dispersion, not xtb's quality.
* **Reference for energies (C2): ORCA B3LYP-D3BJ def2-TZVP single points** at the ORCA B3LYP def2-SVP structures. It is a better, dispersion-corrected reference than the preset and is cheap (single points). **The verdict of C2 is read against this reference** (decision D2); the same differences against the plain preset B3LYP def2-SVP energies are reported beside it.
* **Neither is a measurement.** A DFT reference has errors of its own, of the size the comparison is about. A tier in section 9 therefore reads "xtb agrees with this DFT reference to within X", never "xtb is accurate to X". The benchmark does not use experimental or coupled-cluster references; that would be a different one.

## 6. The floors, measured first and fixed before the arms are judged

A tolerance fixed by guess is a tolerance fitted to nothing. Two floors, on a floor set of water, ethanol, acetic acid, benzene, pyridine and DMSO:
* **Optimizer floor (ORCA):** the application's default `Opt` against `TightOpt`: the largest change in final energy (mEh) and in structure (RMSD, A). It is what two optimizations of the SAME level are allowed to differ by.
* **Optimizer floor (xtb):** `--opt tight` against `--opt vtight`, and one thread against four, run twice each for determinism: the largest change in energy and in RMSD.
* **Same-minimum tolerance for arm P:** `T_E = max(2 x the ORCA optimizer floor in energy, 0.01 mEh)`. Two final energies within `T_E` are the same minimum.
* **Ceiling:** an optimizer-floor RMSD above 0.02 A, or a `T_E` above 0.5 mEh, makes arm P NOT EVALUABLE for the same reason the Psi4 plan's ceiling existed: a floor that loud cannot tell two minima from one.

## 7. Reported, and in no rule

* GFN1-xTB against GFN2-xTB on the neutral closed-shell molecules of sets S and M (structure and isomer energies), so the choice of default is seen.
* The anion and the radical of set S, each against ORCA and Psi4, signed.
* Seconds per job for every engine and the speed ratio, with the machine's core count.
* The signed errors, not only the absolute ones (a bias is information), and for each molecule the largest single deviation.
* xtb's own `# imaginary freq.` count is NOT collected (no frequency arm: see section 10).

## 8. The reading rule (the first line that holds decides, per claim)

**C1 (geometry), over the judged molecules of sets S and M (14 + 6 = 20):**
1. **NOT EVALUABLE** if more than 10% of the cells are missing, or the ORCA optimizer-floor RMSD exceeds the ceiling.
2. **FAIL** if any judged molecule's heavy-atom RMSD exceeds **0.30 A**, or the median exceeds **0.10 A**.
3. else **PASS** if the median heavy-atom RMSD is at most **0.05 A**, the maximum at most **0.15 A**, and the median bond-length deviation at most **0.015 A**.
4. else **PARTIAL**.

**C2 (relative energies), over the isomer pairs and the same-minimum conformer pairs, against the dispersion-corrected reference, end to end:**
1. **NOT EVALUABLE** if fewer than 12 conformer pairs survive the same-minimum rule across set F, or more than 10% of cells are missing.
2. A **tier** by the mean absolute error (MAE) in kcal/mol over all pairs: **A** at most 1.0; **B** at most 3.0; **C** above 3.0.
3. **Ranking:** over the pairs whose reference difference exceeds 1.0 kcal/mol, the fraction ordered the same way by xtb must be at least **0.90** for the tier to stand; otherwise the tier drops one level (A to B, B to C).
4. The fixed-geometry decomposition is reported with the tier and never changes it.

**C3 (pre-optimizer), over the 20 judged molecules, paired:**
1. **NOT EVALUABLE** if the same-minimum floor breaks its ceiling, or more than 10% of the pairs are missing.
2. **FAIL** if fewer than **90%** of the pairs reach the same minimum (final energies within `T_E`): starting from xtb must not change where ORCA ends.
3. else **PASS** if the median ratio (ORCA cycles from the xtb start) / (ORCA cycles from the MMFF start) is at most **0.80**, the one-sided Wilcoxon signed-rank test on the cycle counts has p below **0.05**, and the total wall time including xtb is lower from the xtb start in at least **half** the molecules.
4. else **PARTIAL**: reached the same minimum but did not demonstrably save work (the benefit claim is withdrawn, not the safety).

Each claim has its own verdict. Nothing is pooled and there is no overall pass.

## 9. What each verdict does (decided now)

* **C1 PASS:** the user guide and the xtb tab's note may say that the xtb structure agrees with the application's ORCA B3LYP/def2-SVP structure to within the measured numbers, on these molecules. **PARTIAL / FAIL:** the xtb geometry is offered as a quick, rough structure only, and the note says so with the measured median.
* **C2 tier A / B / C:** the note on an xtb energy difference reads, respectively, "agrees with DFT to within about 1 kcal/mol on these molecules", "a screening estimate, a few kcal/mol from DFT", or "not for ranking isomers or conformers". The tier is worded from the measured MAE, not from the letter.
* **C3 PASS:** the Optimize-with-ORCA dialog may offer "start from an xtb structure" as an option (never silently, never the default without a further decision). **PARTIAL:** nothing is offered. **FAIL:** nothing is offered and the cause is written up.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed and the arm is re-run under a new plan.
* A result outside a threshold is **never** explained away by hand. An attribution can be added (for example the conformers that did not map) and the verdict stands.

## 10. What it cannot say

* **Twenty-five molecules, three element classes beyond H, C, N, O (F, S, Cl):** nothing about metals, heavier elements, large molecules, charged species beyond one anion, or open shells beyond one radical.
* **Gas phase, ground state, energies and structures only.** There is no frequency, thermochemistry, dipole, solvation or property arm. xtb's frequencies are used by the application, so a frequency comparison is a separate, later benchmark.
* **Agreement with a DFT reference, not accuracy.** Section 5.
* **One xtb build and one optimizer pair.** A newer xtb, GFN-FF, or another ORCA optimizer setting is a different question.
* **The thresholds are decisions, not literature values.** They were not taken from any paper and no claim is made that they are standard; section 12 asks Alex to confirm or change them before the freeze.

## 11. Records

`artifacts/<arm>/<engine>.jsonl` (one line per job: molecule, start-geometry sha256, input sha256, energy, cycles, structure, seconds, engine version, commit, whether `src/` was dirty), `floor.json`, `report.txt`, `verdict.json`, and the outcome written below this line after the run and after nothing else. **A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`**, the guard the Psi4 and Fukui checks have.

## 12. Decisions for the owner (open; the draft is not frozen until each has an answer in section 13)

* **D1, the references.** Structures against ORCA B3LYP def2-SVP (the application's default preset). Alternative: a better-converged DFT reference (TZVP optimizations), at several times the cost, which would cost this benchmark days, not hours. Proposed: the preset, because the claim is about what a user of this application gets.
* **D2, the energy reference.** B3LYP-D3BJ def2-TZVP single points on the ORCA structures, against which the C2 tier is read, because the preset has no dispersion and GFN2 does. Alternative: judge against the plain preset as well, which would tend to mark xtb down for a difference that is dispersion.
* **D3, the thresholds** of section 8 (C1: 0.05 / 0.15 / 0.30 A median-and-maximum bounds and 0.015 A for bonds; C2: tiers at 1 and 3 kcal/mol and 0.90 ranking; C3: 0.80 cycle ratio, p 0.05, 90% same minimum). Each is a proposal with no source behind it; they are chosen so that a PASS means a difference a person would not see (C1), a tier a person can act on (C2) and a real saving (C3). Change any before the freeze, never after the first job.
* **D4, the molecule sets.** Set M and set F are proposals; the Psi4 set S is inherited. Add or remove any before the freeze.
* **D5, ORCA time.** Arm P and arm G run about 60 ORCA optimizations at an hour at most each, plus 30-odd single points. Say if that is acceptable on the machine, or whether set M should be shorter.
* **D6, the Psi4 role.** Only a reference-robustness cross-check on set S. Say if Psi4 should also be run on set M.

## 13. Record of the freeze

Not yet frozen. When it is: the date, the decisions D1 to D6 as answered, the commit of the runner and the judge, the xtb build hash, and the ORCA and Psi4 versions go here.
