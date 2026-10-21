# Psi4 against ORCA, version 3 of the agreement check (preregistered)

Written 2026-10-20, **before any job of it is run**, and committed with its runner before the first one. `PLAN.md` and `PLAN_V2.md` are untouched and stay the record of the first two runs. **Every rule, molecule, geometry, combination, floor formula, tolerance formula, ceiling and reading rule of `PLAN.md` applies, as changed by `PLAN_V2.md` (the engine writes `scf_type pk`; the Psi4 floor variants are `grid` and `one_thread`; the `tight` floor adds `geom_maxiter 200`; density fitting is the attribution rerun only)**, and including the 2026-10-19 amendment. `judge.py` is unchanged.

## Why a third plan

Version 2 (commit `68c3f8f1`) ended NOT EVALUABLE because 1 of the 16 Psi4 optimizations was missing (6.2%, limit 5%): the engine's output parser refused a converged chloromethane optimization because Psi4 prints chlorine as `CL`. That bug is fixed in commit `1bc81f43` ("read CL", with a real-output fixture and a test that fails without the fix). The floors of version 2 were small and evaluable (HF 0.000 mEh, DFT 0.063 mEh).

## What was seen before this plan was written (disclosure)

Version 2's results were seen, including the signed medians of Psi4 minus ORCA (HF 0.000 mEh in all three bases; B3LYP +0.20 to +0.29, PBE0 +0.21 to +0.30, M062X +0.31 to +0.42 mEh) and the per-cell ranges against T_DFT 0.126 mEh. **A DFT PARTIAL or FAIL by scatter is therefore a likely outcome of this plan, and will be reported as one.** Nothing about the tolerances, the threshold, the molecules or the combinations was chosen with those numbers in view; they are version 1's and version 2's, unchanged.

## What changes (and only this)

1. **The engine has the parser fix** (`CL` read as chlorine). Nothing else in `src/` changes between version 2's commit and this one except that fix.
2. **The optimization floor is taken on five molecules: pyridine is excluded for both engines** (`OPT_FLOOR_EXCLUDED` in the runner). Its Psi4 `tight` optimization hit the 30-minute cap in version 1 (50 iterations) and in version 2 (with `geom_maxiter 200`); running it again would cost 30 minutes for a cell known to be missing. The exclusion is declared here, in advance, and applies to the floor only: pyridine remains in the single-point floor, the grid and the optimization arm, where a non-converging default-input optimization is a missing cell (never a pass). Version 2's optimization floor also rested on five molecules (11 measurements counting both engines), so this changes the floor numbers by nothing material.
3. **Records go to `artifacts_v3/`** and **all stages are re-run for both engines** (the report refuses records from more than one commit).

## Run order, verdicts, limits

As `PLAN_V2.md`: `floor --engine orca`, `floor --engine psi4`, `floor-report`, `grid --engine orca`, `grid --engine psi4`, `optimize --engine orca`, `optimize --engine psi4`, `attribute`, `report`, `--workers 3 --cores 4`, one stage at a time, clean `src/`, one commit. **PASS** is recorded in `docs/PSI4_ENGINE_DESIGN.md`; **PARTIAL** names the cells and removes nothing; **FAIL** removes the functional of any systematic-offset combination from `PSI4_METHODS` (the narrower action where the evidence names one); **NOT EVALUABLE** claims nothing. A result outside the tolerances is never explained away by hand. What it cannot say is `PLAN.md`'s list, plus: it says nothing about Psi4 with density fitting, and it is the third try at one question after two outcomes were seen, so it is not an independent test.

## Outcome

Not yet run.
