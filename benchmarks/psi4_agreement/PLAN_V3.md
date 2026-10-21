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

## Outcome (run 2026-10-20 evening, commit 58e31894, `src/` clean throughout)

**Verdict: PARTIAL.** Every record is present (floor 46 + 64, grid 240 + 240, optimization 16 + 16 jobs; none missing) and from one commit. `judge.py` was applied unchanged; nothing was altered after any result. Records: `artifacts_v3/`. Floors: HF 0.0000 mEh, DFT 0.0629 mEh, optimization energy 0.0087 mEh, RMSD 0.00105 A (10 optimization measurements); tolerances T_HF 0.010 mEh, T_DFT 0.126 mEh, T_Eopt 0.126 mEh, T_geom 0.0021 A.

| arm | verdict | detail |
|---|---|---|
| HF single points (48 cells) | **PASS** | all 48 within T of their median; every median 0.000 mEh |
| DFT single points (192 cells) | **PARTIAL** | 73.4% within T; no systematic offset (all medians below 0.5 mEh); nothing beyond 5 T |
| relative energies (45 cells) | **PARTIAL** | 91.1% within T_rel; none beyond 5 T_rel |
| optimizations (16) | **PARTIAL** | 13 outside; none beyond 5 T in energy or geometry |

* **The cells outside T (51 of 192 DFT cells), by combination:** M062X def2-SVP 10 of 16, M062X 6-31G(d) 11, M062X def2-TZVP 10 (31 of 51); PBE0 def2-SVP 5, 6-31G(d) 2, def2-TZVP 3; B3LYP def2-SVP 2, 6-31G(d) 1, def2-TZVP 2, pcSseg-1 2, pcSseg-2 1, B3LYP/G def2-SVP 2. By molecule: hydroxyl radical 11, fluorobenzene 8, dimethyl ether 5, water 4, methane 4, benzene 4, chloromethane 3, ethanol 3, dimethyl sulfoxide 3, propanal 2, thiophene 2, pyridine 1, acetate 1. The hydroxyl radical's cells are outside T because its offset (+0.07 to +0.15 mEh) is smaller than its combinations' medians (+0.2 to +0.4), i.e. the offset grows with the size of the molecule.
* **Optimizations:** the final energies differ by Psi4 minus ORCA +0.07 to +0.31 mEh (all positive; T_Eopt 0.126; 3 of 16 within); the geometries agree to an RMSD of 0.0000 to 0.0034 A (all but acetone 0.0030 and propanal 0.0034 are within T_geom 0.0021; the largest is a third of 5 T_geom). So the structures agree and the energies carry the same steady offset as the single points.
* **Reading:** Hartree-Fock agrees with ORCA to the microhartree; DFT energies carry a **steady, positive, size-dependent offset of +0.05 to +0.65 mEh** (median +0.20 to +0.42), largest for M062X and smallest for B3LYP, below the 0.5 mEh systematic threshold the plan fixed and above the floor-derived tolerance. It is not density fitting (now excluded: the engine is exact, and the df attribution reruns moved cells by tens of microhartree), not the grid or threads (the floors), and not the VWN or cartesian-d errors (37 and 1.8 mEh). **It is unexplained**; the natural suspects (the two programs' default DFT integration grids, and functional details such as Psi4's and ORCA's M06-2X implementations) were not tested here.
* **What it does:** per the verdicts above, a PARTIAL names the cells (above) and **removes nothing** from `PSI4_METHODS`. The engine's claim after this: a result labelled "HF" in Psi4 is the same calculation as ORCA's to 0.01 mEh; a DFT result is the same method to a few tenths of a mEh (a fraction of a kcal/mol in absolute energy, and cancelling in part in relative energies, 91% of which were within tolerance and none beyond 5 T), with a systematic sign, and **the two engines' DFT numbers must not be mixed under one label** (as the provenance already enforces).
* **Next, if wanted (not started):** a measurement, not a fourth rerun: run Psi4 at a finer DFT grid (and ORCA at DefGrid3) on the five largest offsets (M062X benzene, fluorobenzene, dimethyl ether, DMSO, ethanol) and ask whether the offset moves with the grid. That needs its own preregistration if it is to be quoted.
