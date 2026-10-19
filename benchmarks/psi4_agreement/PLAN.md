# Psi4 against ORCA: the agreement check (stage 2 of `docs/PSI4_ENGINE_DESIGN.md`), preregistered

Written 2026-10-19, **before any job of it is run**, and committed with its judge (`judge.py`, tested by `tests/test_psi4_agreement_judge.py`) before the first one. The rule below is the code in `judge.py`; where this text and that code disagree, the disagreement is a defect in one of them
and is fixed before any run, never after.

## The question

The Psi4 engine (`chem/psi4_engine.py`) translates a functional's NAME through a table (`PSI4_METHODS`) and passes the basis through with `puream true`. The spot check made while building it (water, five combinations, 0.1 to 0.16 mEh) is not a check: one molecule, no floor, no geometry.
**Does the engine, as built, give the energy and the optimized geometry ORCA gives for the same molecule, functional and basis, to within what each engine's own harmless settings already move them by?**
A "yes" says the table and the basis handling are right for the molecules and combinations tested. It does not say Psi4 and ORCA are equally good, only that a result labelled "B3LYP def2-SVP" means the same calculation in both.

## What is compared, fixed now

* **Molecules (16, fixed):** water `O`, methane `C`, chloromethane `CCl`, ethanol `CCO`, dimethyl ether `COC`, acetic acid `CC(=O)O`, methyl formate `COC=O`, acetone `CC(C)=O`, propanal `CCC=O`, benzene `c1ccccc1`, pyridine `c1ccncc1`, fluorobenzene `Fc1ccccc1`, thiophene `c1ccsc1`,
  dimethyl sulfoxide `CS(C)=O`, acetate `CC(=O)[O-]` (charge -1) and the hydroxyl radical `[OH]` (multiplicity 2). Elements H, C, N, O, F, S, Cl; a closed shell, an anion and a radical. **Three isomer pairs** for relative energies: ethanol / dimethyl ether, acetone / propanal, acetic acid / methyl formate.
* **Geometries:** RDKit ETKDG (seed 7) plus MMFF, **identical coordinates written into both engines' inputs**, never optimized first for the single points.
* **Single-point grid (15 combinations per molecule, 240 per engine):** the functionals HF, B3LYP, PBE0 and M062X (four of the five entries of `PSI4_METHODS`) at def2-SVP, 6-31G(d) and def2-TZVP (12), plus B3LYP at pcSseg-1 and pcSseg-2 (2), plus the Gaussian-style `B3LYP/G` at def2-SVP (1). **The inputs are the ones the application writes**: ORCA through `OrcaQuantumEngineProvider.build_input` and Psi4 through
  `Psi4QuantumEngineProvider.build_input`, each run with its own `command_args`, so what is tested is the engine as shipped.
* **Optimization arm:** B3LYP def2-SVP `Opt` on all 16 from the same start, by each engine's own provider; the final energy and the geometry compared.
* **The difference** is d = E(Psi4) - E(ORCA) in mEh (1 mEh = 0.627509 kcal/mol), the total energy as each provider reports it. Relative energies: for each isomer pair, d_rel = (E_a - E_b)(Psi4) - (E_a - E_b)(ORCA) in kcal/mol. Geometry: the RMSD over all atoms after a rigid-body (Kabsch) alignment, in Angstrom.
* **Missing cells:** a job that does not finish (30 minutes each at most) or an output that does not parse is a missing cell, never a pass.

## The floor, measured first and fixed before the grid is judged

A tolerance fixed by guess would be a tolerance fitted to nothing. The floor is how much each engine's total energy moves when a setting that **does not change the method** is changed, on a fixed floor set: water, ethanol, acetic acid, benzene, pyridine and DMSO, each at B3LYP def2-SVP, PBE0 def2-TZVP and HF 6-31G(d).
* **ORCA:** the default input against `TightSCF` with `DefGrid3` (a finer integration grid and a tighter SCF).
* **Psi4:** the engine's input (`scf_type df`, default grid, e_convergence 1e-8) against `scf_type pk`, against `dft_radial_points 99` with `dft_spherical_points 590` and `e_convergence 1e-10`, and against one thread (`-n 1`) in place of four. Density fitting is in the floor because it is the engine's own default and a Psi4 user's setting to change.
* The floor of a class is the **largest** absolute change seen in it: **HF** (cells with no grid and no functional) and **DFT** (the others), taking the larger of the two engines'. **For the optimization:** each engine's default `Opt` against its tight one (`TightOpt` for ORCA; `g_convergence gau_tight` for Psi4), on the same floor molecules at B3LYP def2-SVP, for the final energy and the RMSD.

## The tolerances, fixed by this arithmetic (no number below is chosen after seeing a result)

* **T_HF = max(2 x floor_HF, 0.01 mEh)** and **T_DFT = max(2 x floor_DFT, 0.01 mEh)**: twice the floor, and never below 0.01 mEh, ten times ORCA's default energy convergence (1e-6 Eh).
* **T_rel (kcal/mol) = 2 x T_class x 0.627509**, with the class of the combination (an isomer difference carries two errors).
* **T_Eopt = max(T_DFT, 2 x the optimization energy floor)** and **T_geom = max(2 x the RMSD floor, 0.001 A)**.
* **Ceiling: a T above 0.5 mEh (0.31 kcal/mol) makes the whole check NOT EVALUABLE**: a floor that loud cannot tell two engines from two settings, and the 37 mEh the VWN trap produced would still be seen, but the check would no longer be the check this plan describes.

## The reading rule, fixed now (the first line that holds decides)

1. **NOT EVALUABLE** if a floor gives a tolerance above the ceiling, or more than 5% of the grid's cells are missing (in either arm), and the report says which.
2. **Single points**, per class (HF and DFT), over the combinations of that class. A combination has a **systematic offset** if the MEDIAN of d over the molecules has absolute value **above 0.5 mEh** (a definitional difference, the signature of the VWN trap; fixed, see the amendment below). A cell's **scatter** is its d minus the median d of its own combination.
   * **FAIL** if any combination has a systematic offset, or any cell's scatter exceeds 5 x T.
   * else **PASS** if at least 95% of the class's cells have |scatter| within T.
   * else **PARTIAL**.
   The single-point verdict is the worst of the two classes.
3. **Relative energies:** **FAIL** if any |d_rel| exceeds 5 x T_rel; else **PASS** if at least 95% of the (pair, combination) cells are within T_rel; else **PARTIAL**.
4. **Optimization:** a molecule is within if its final energies differ by at most T_Eopt and its RMSD is at most T_geom. **FAIL** if any energy difference exceeds 5 x T_Eopt or any RMSD exceeds 5 x T_geom (a different structure); else **PASS** if all 16 are within; else **PARTIAL**.
5. **The overall verdict is the worst of the three** (PASS, then PARTIAL, then FAIL).

## Amendment of 2026-10-19, before any real job was run (decided by Alex)

The runner was smoke-tested on two molecules (water and the hydroxyl radical, 32 single points per engine, in a scratch folder, **not a record**). **That smoke run was seen when this amendment was decided, and the amendment is a response to it.** It showed ORCA and Psi4 differing by a steady +0.11 to +0.17 mEh for
B3LYP, PBE0 and M062X on both molecules, and by 0.05 mEh for HF at def2-SVP (density fitting, which the floor combinations underestimated: 0.014 mEh at 6-31G(d)), against a DFT tolerance from the within-engine floor of about 0.07 mEh. The plan as first frozen would have called those engines a FAIL for a difference that is two programs' implementations of one functional, not a mapping error.
**The change:** the systematic-offset test (rule 2) uses a fixed threshold of **0.5 mEh** on the median d of a combination, and the per-cell test uses each cell's scatter around its combination's median against T. The two real definitional errors found in this project were 1.8 mEh (cartesian against spherical d functions) and 37 mEh (VWN1RPA against VWN5), well above 0.5 mEh. **What this costs:** a definitional difference between 0.07 and 0.5 mEh is no longer
detected (it is reported in the signed medians). The relative-energy and optimization rules, the floors, the tolerances and the ceiling are unchanged. This amendment is the last change before the run; any later one needs a new plan.

## What each verdict does (decided now)

* **PASS:** `docs/PSI4_ENGINE_DESIGN.md` records that the table and the basis handling agree with ORCA on these molecules and combinations, with the tolerances and the floors. Nothing else changes.
* **PARTIAL:** the failing cells are named and the report says by how much; nothing is removed.
* **FAIL:** the functional of any systematic-offset combination is **removed from `PSI4_METHODS`**, and a basis with a systematic offset is refused by the engine, **until the cause is found and re-run**; the narrower action is taken where the evidence names one (a single molecule is not a reason to remove a functional). The engine's docstring and the user guide say which.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed (a floor that loud usually names a setting worth pinning) and the check is re-run under a new plan.
* A result outside the tolerances is **never** explained away by hand: an attribution arm (below) says what it can, and the verdict stands.

## Reported, and in no rule

* For every cell outside T: the same Psi4 run with `scf_type pk`, so that density fitting can be named or excluded as the cause.
* The signed median d per combination (the sign of a definitional difference, and the differences the amendment no longer judges), the largest |d| per molecule, and each engine's seconds per job.
* The numbers of the spot check made while building the engine (water, 0.1 to 0.16 mEh) against this grid's water cells.

## What it cannot say

* **Sixteen molecules and fifteen combinations**: a combination, element or geometry outside them is untested (no heavier element than Cl, no charged species beyond one anion, no open shell beyond one radical, no metals).
* **The same method label, not the same accuracy**: it says the two engines compute the same thing, not that either is right.
* **Energies and one optimizer pair**: nothing about gradients, frequencies, dipoles or any property, none of which the engine runs.
* **The tolerances are the engines' own noise floors**: a real difference smaller than them (a 0.1 mEh functional detail, for instance) is not resolved.

## Records

**A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`** (the guard the Fukui gates have). `artifacts/<stage>/<engine>.jsonl` (one line per job: molecule, combination, the input's sha256, the energy, the engine's version, the commit and whether `src/` was dirty, the seconds), `floor.json`, `report.txt`, `verdict.json`, and the outcome written below, after the run and after nothing else.
