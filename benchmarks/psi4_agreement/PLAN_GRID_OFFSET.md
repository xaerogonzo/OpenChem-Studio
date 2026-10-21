# Does the Psi4-ORCA DFT offset move with the integration grid? (preregistered)

Written 2026-10-20, **before any job of it is run**, and committed with its runner (`run_grid_offset.py`) and its tests (`tests/test_psi4_grid_offset.py`) before the first one. The rule below is the code of `judge_cells` in the runner; where this text and that code disagree, that is a defect fixed before any run, never after.
This is a measurement that follows version 3 of the agreement check (`PLAN_V3.md`, PARTIAL), not a fourth run of it: it uses the same inputs the application writes and the same job runner, on a small fixed set of cells.

## The question

Version 3 found Hartree-Fock identical between the two programs (48 of 48 cells within 0.010 mEh) and DFT energies **steadily +0.05 to +0.65 mEh higher in Psi4** (medians +0.20 to +0.42 mEh; M062X largest; growing with molecule size). Exact integrals, the thread count and a finer Psi4 grid *within* Psi4 were each shown not to move energies by more than 0.063 mEh on the floor set, which does not say what the two programs' *default* grids do relative to each other. The grids are the natural suspect because they are the one ingredient the two programs choose independently and Hartree-Fock lacks.
**Question: if each program's integration grid is made finer, does the Psi4 minus ORCA offset shrink?** A "yes" says the offset is a grid-discretisation difference, not a different functional. A "no" says the offset is something else (the functional's definition, a convergence criterion, a basis-function detail), and the cause stays open.

## What is run, fixed now

* **Cells (26):** six molecules, then four DFT combinations each (M062X and B3LYP at def2-SVP and def2-TZVP; 24 DFT cells), plus two Hartree-Fock negative controls (water and benzene, HF def2-SVP). **The molecules** are fixed by this rule applied to version 3's records (`artifacts_v3/`, seen before this plan was written; the ranking is below): the five with the largest mean M062X difference (Psi4 minus ORCA) over the three bases, and water, the smallest, as the small-molecule control. Ranking (mean M062X d, mEh): dimethyl ether +0.611, fluorobenzene +0.565, benzene +0.556, dimethyl sulfoxide +0.531, propanal +0.494 (the five), then pyridine +0.477, ... water +0.039. Geometries, inputs, charges and multiplicities are the agreement check's (RDKit ETKDG seed 7 plus MMFF, the providers' own `build_input`).
* **Four runs per cell:** each program at its own default grid and at a finer one. Psi4: the engine's default (75 radial, 302 spherical points) and `dft_radial_points 99`, `dft_spherical_points 590` with `e_convergence 1e-10` (the agreement runner's `grid` variant). ORCA: its default (`DefGrid2`) and `TightSCF` with `DefGrid3` (the runner's `tight` variant). The convergence tightening in the finer variants is the only non-grid difference; the Hartree-Fock controls measure it (below). The engine writes `scf_type pk` throughout.
* **Per cell, in mEh:** d_default = Psi4 default - ORCA default (version 3's difference, re-measured here at this experiment's commit); d_fine = Psi4 fine - ORCA fine; the two cross terms (Psi4 fine - ORCA default; Psi4 default - ORCA fine), and each program's own shift (fine minus default). d_fine = d_default + (Psi4 shift) - (ORCA shift).

## The tolerances, fixed from version 3's artifacts and not tuned here

* T_DFT = **0.126 mEh**, version 3's DFT tolerance (twice its 0.0629 mEh floor); a single cell carries two programs' errors and is allowed **2 x T_DFT = 0.252 mEh**.
* The Hartree-Fock controls may move by at most **0.01 mEh** in either program (version 3's HF floor was 0.00001 mEh): a Hartree-Fock energy has no grid, so a larger move would mean the finer variants changed something besides the grid and the experiment would not be measuring what it names.
* The offset must reproduce: the median d_default over the 24 DFT cells must be at least **0.1 mEh**.

## The reading rule, fixed now (the first line that holds decides)

1. **NOT EVALUABLE:** fewer than 22 of the 24 DFT cells have all four runs, or a Hartree-Fock control lacks one. (A cell missing a run is dropped; a job that does not finish in 30 minutes or does not parse is missing, never a pass.)
2. **NOT VALID:** a Hartree-Fock control moved by more than 0.01 mEh in either program, or the median d_default is below 0.1 mEh.
3. **GRID EXPLAINS:** the median d_fine is within T_DFT of zero, at least **80%** of the DFT cells have |d_fine| within 0.252 mEh, **and** |median d_fine| is at most **half** of |median d_default|.
4. **NOT THE GRID:** |median d_fine| is at least **75%** of |median d_default| (the offset is essentially unmoved).
5. **PARTIAL** otherwise.

## What each verdict does (decided now)

* **GRID EXPLAINS:** `docs/PSI4_ENGINE_DESIGN.md` and the CHANGELOG record that the offset is a grid difference, with which program's grid moved (the medians of each program's shift), and the engine's DFT numbers are described as agreeing with ORCA's at converged grids. Nothing is changed in the engine (a user's Psi4 grid is their setting; whether the engine should write a finer default is a separate decision for Alex, with its cost measured first).
* **NOT THE GRID, PARTIAL:** recorded as such; the cause stays open, and the next candidates (the functional definition, each program's M06-2X and B3LYP details, convergence) are listed, not tested.
* **NOT VALID, NOT EVALUABLE:** nothing is claimed; the cause is fixed and the experiment re-run under a new plan.
* A result is never explained away by hand, and the plan is not changed after a result.

## Reported, and in no rule

* The median shift of each program's grid (which program's grid is responsible, if the verdict is GRID EXPLAINS or PARTIAL), the two cross terms, and the table of every cell. How the offset scales with the molecule and the functional.

## What it cannot say

* **Six molecules, two functionals, two bases**: a result about these cells. It does not cover PBE0, the other bases, larger molecules or open shells.
* **One finer grid per program**: "the grid explains it" means a grid at least this fine removes it, not that this is the converged grid. Psi4's 99/590 and ORCA's `DefGrid3` are not the same grid and not a common reference; the experiment asks whether the offset *moves*, not whether the finer grids agree with a third program.
* **It follows an outcome that was seen**: version 3's offsets, per cell, were read before this plan; the hypothesis (the grid) was chosen with those in view, so the experiment can refute it but a confirmation is specific to these cells.
* It says nothing about which program is right.

## Run order and records

From `benchmarks/psi4_agreement`: `run_grid_offset.py run --engine orca`, `run --engine psi4`, `report`, `--workers 3 --cores 4`, one engine at a time, `src/` clean, one commit (the report refuses mixed commits or a dirty `src/`). Records: `artifacts_grid/gridoff/<engine>.jsonl`, `report.txt`, `verdict.json`.

## Outcome

Not yet run.
