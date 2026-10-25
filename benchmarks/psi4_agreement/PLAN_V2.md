# Psi4 against ORCA, version 2 of the agreement check (preregistered)

Written 2026-10-20, **before any job of it is run**, and committed with its runner (`run_agreement.py`) before the first one. `PLAN.md` (version 1) is untouched and stays the record of the first run; **every rule, molecule, geometry, combination, floor formula, tolerance formula, ceiling and reading rule of `PLAN.md` applies here unchanged, including its 2026-10-19 amendment (the 0.5 mEh systematic-offset threshold)**. The rule is the code in `judge.py`, which is unchanged. Only what is listed under "What changes" differs.

## Why a second plan

Version 1 ran on 2026-10-19 (commit `7bc3d20c`) and ended **NOT EVALUABLE**: its Hartree-Fock floor, Psi4's default density fitting (`scf_type df`) against exact integrals (`pk`) at 6-31G(d), was 0.450 mEh (pyridine 0.450, dimethyl sulfoxide 0.387, benzene 0.384, acetic acid 0.365; every other floor change was 0.065 mEh or less), so T_HF = 0.90 mEh exceeded the 0.5 mEh ceiling. The ceiling did what it was written for: a floor that loud means the setting is not harmless. Density fitting changes the energy by an amount of the order of the differences being judged, ORCA's default is exact, and so it is a method choice and not a nuisance setting.
**Decided by Alex 2026-10-20 (option A): the Psi4 engine writes `scf_type pk`.** Commit `a6741657` makes that change (the input, the provenance, the tests) and precedes this plan.

## What was seen before this plan was written (disclosure)

The version 1 results were seen: signed median Psi4 minus ORCA of +0.09 to +0.49 mEh per combination (M062X def2-SVP +0.485, just under the 0.5 mEh threshold; 6-31G(d) and def2-TZVP M062X +0.455 and +0.380), the largest single difference 0.751 mEh, no sign of a 37 or 1.8 mEh error, and density fitting not explaining the offset (the version 1 `pk` reruns moved cells by tens of microhartree). **None of this was used to choose anything below**: the 0.5 mEh threshold, the tolerances' formulae, the molecules and the combinations are exactly version 1's. What version 1 did show is that a median near 0.5 mEh is possible, so a **FAIL by systematic offset on M062X is a live outcome of this plan**, and it will be reported as one.

## What changes (and only this)

1. **The engine under test writes `scf_type pk`** (`chem/psi4_engine.py`, commit `a6741657`). Psi4's inputs in the grid, the optimization arm and the floor's default are the engine's, so they are exact-integral inputs.
2. **The Psi4 floor variants are `grid` (a 99-radial, 590-spherical DFT grid and `e_convergence 1e-10`) and `one_thread` (`-n 1`)**; version 1's `pk` variant is gone because it is now the default. Density fitting leaves the floor: it is a method choice, and the question becomes whether the engine as shipped (exact integrals) agrees with ORCA to within its own harmless noise. The floor formulae are version 1's, on the same floor set. ORCA's floor (`tight`: TightSCF with DefGrid3, and TightOpt) is unchanged.
3. **The attribution arm** now reruns the cells outside tolerance with `scf_type df` and reports the signed d beside the exact-integral one (reported, in no rule), so a user who sets density fitting can see what it costs against ORCA.
4. **A non-converging Psi4 tight-optimization floor job** (version 1 lost the pyridine `gau_tight` one at Psi4's default 50 iterations): the floor's `tight` variant adds `geom_maxiter 200`. It is a text edit of the floor variant only; the engine's own optimization input, the grid and the optimization arm keep Psi4's defaults, so a default-input optimization that does not converge is a missing cell, never a pass (version 1's rule, and the 5% rule of reading rule 1).
5. **Records go to `artifacts_v2/`** (the runner's new default) and **all stages are re-run for both engines**, ORCA's included: the report refuses records from more than one commit, and the ORCA inputs have not changed but their records carry version 1's commit.

## Run order and records

From `benchmarks/psi4_agreement`, one stage at a time, `--workers 3 --cores 4`: `floor --engine orca`, `floor --engine psi4`, `floor-report`, `grid --engine orca`, `grid --engine psi4`, `optimize --engine orca`, `optimize --engine psi4`, `attribute`, `report`. `src/` is clean and the commit is one throughout (the report's own guard).

## What each verdict does

As `PLAN.md`: **PASS** is recorded in `docs/PSI4_ENGINE_DESIGN.md` with the tolerances and floors; **PARTIAL** names the cells and removes nothing; **FAIL** removes the functional of any systematic-offset combination from `PSI4_METHODS` (the narrower action where the evidence names one); **NOT EVALUABLE** claims nothing and needs a third plan. A result outside the tolerances is never explained away by hand.

## What it cannot say

Everything `PLAN.md` says it cannot, and in addition: it says nothing about Psi4 with density fitting (the engine does not write it), and it was designed after version 1's outcome was known (the disclosure above), so it is a second try at the same question, not an independent one.

## Outcome (run 2026-10-20, commit 68c3f8f1, `src/` clean throughout)

**Verdict: NOT EVALUABLE** (rule 1: more than 5% of the cells are missing). Records in `artifacts_v2/`; `judge.py` applied unchanged and nothing was altered after any result.

* **The floor is now evaluable.** HF floor 0.0000 mEh (T_HF = the 0.01 mEh minimum), DFT floor 0.0629 mEh (T_DFT 0.126 mEh), optimization energy floor 0.0087 mEh (T_Eopt 0.126 mEh), RMSD floor 0.00105 A (T_geom 0.0021 A). No tolerance is near the 0.5 mEh ceiling: removing density fitting from the engine fixed what version 1 failed on.
* **Why it is not evaluable:** 1 of the 16 Psi4 optimizations is missing (6.2% of the optimization arm's cells, above the 5% limit). The cause is **a bug in the engine's output parser, found by this run**: Psi4 prints chlorine as `CL` in "Final optimized geometry", and `psi4_engine._GEOMETRY_ROW` accepted only `Cl`, so the converged chloromethane optimization (exit 0, reproduced on its own) was refused with "final geometry has atoms ['C']". Any Psi4 optimization of a chlorine-containing molecule failed in the same way. Fixed afterwards in its own commit (below); the check was not re-run.
* **Other missing cell:** the Psi4 `tight` optimization floor job for pyridine hit the 1800 s cap even with `geom_maxiter 200` (as in version 1, where it did not converge in 50 iterations), so the optimization floor rests on 11 measurements. The grid is complete (240 of 240 per engine).
* **Descriptive only, in no rule** (signed median Psi4 minus ORCA, mEh): **HF agrees to 0.000 mEh on all three bases** (exact integrals against exact); B3LYP +0.20 to +0.29; PBE0 +0.21 to +0.30; M062X +0.31 to +0.42; B3LYP/G +0.227. Cell ranges reach -0.17 to +0.64 against T_DFT 0.126 mEh, so a judged DFT arm would very likely not have PASSed. **The DFT offset is steady, positive and 0.2 to 0.4 mEh in the median, below the 0.5 mEh systematic-offset threshold and so not a FAIL by that rule; it is a consistent small difference between the two programs' DFT implementations (grids, functional details) that the floors do not explain, and it remains unresolved.** The density-fitting attribution reruns moved cells by tens of microhartree only. No 37 mEh or 1.8 mEh signature.
* **What it does and does not change:** nothing is removed from `PSI4_METHODS`; no agreement and no failure is claimed for the DFT energies. HF agreement at the microhartree level is observed but, like everything here, not judged.
* **The next step is a third plan** (version 3): the same as this one, run on a commit with the parser fixed, so that the optimization arm is complete. It must also say in advance how the pyridine `tight` floor job is handled (a missing floor cell is a legitimate measurement shortfall, but it has now cost 30 minutes twice; options: a larger cap for that job, or define the optimization floor on the molecules that converge). Not started.
