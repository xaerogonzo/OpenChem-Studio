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

## Outcome

Not yet run.
