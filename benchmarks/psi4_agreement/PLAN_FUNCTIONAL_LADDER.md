# Is the Psi4-ORCA DFT offset in every density functional, or in one functional's coding? (preregistered)

Written 2026-10-22, **before any job of it is run**, and committed with its runner (`run_functional_ladder.py`) and its tests (`tests/test_psi4_functional_ladder.py`) before the first one. The rule below is the code of `judge_ladder` in the runner; where this text and that code disagree, that is a defect fixed before any run, never after.
It follows the agreement check (`PLAN_V3.md`, PARTIAL) and the grid test (`PLAN_GRID_OFFSET.md`, PARTIAL), and is a measurement, not a fourth run of either. **It has not been run, and is not to be run until Alex says Psi4 and ORCA are free** (another session is using them).

## The question

Hartree-Fock agrees between the two programs to the microhartree. Every density functional tried carries a steady, positive Psi4 minus ORCA offset of a few tenths of a mEh (B3LYP median +0.26, PBE0 +0.22, M062X +0.3 to +0.5), growing with the size of the molecule. The grid test showed that a finer grid removes part of M062X's offset (ORCA's default grid is not converged for it) and **none of B3LYP's**: B3LYP's +0.26 mEh is in both programs at either grid, and a uniform +0.1 to +0.3 mEh remains in every DFT cell. That residual is unexplained.
**Question: is the residual something every density functional carries (a numerical treatment common to the DFT part of the calculation), or something the coding of one functional's ingredients carries?** The ladder takes the ingredients apart: HF has none of the DFT part (the control), PBE is a pure GGA with neither exchange of B88 nor LYP correlation nor exact exchange, BLYP is B88 exchange with LYP correlation and no exact exchange, B3LYP is a mixture of BLYP with 20% exact exchange and a local part, and PBE0 is PBE with 25% exact exchange.

## What is run, fixed now

* **Cells (30 per engine):** the six floor molecules of version 1 (water, ethanol, acetic acid, benzene, pyridine, dimethyl sulfoxide: fixed before any offset was seen, so the choice does not depend on the thing measured), each at five functionals, all at def2-SVP: **HF** (negative control), **PBE**, **BLYP**, **B3LYP**, **PBE0**. One run per cell and engine, each program at its own default grid, as shipped (the engine writes `scf_type pk`).
* **Inputs:** HF, B3LYP and PBE0 are the application's own inputs, **byte for byte what version 3 ran** (a test holds this). PBE and BLYP are not in the application's functional table: they are the shipped B3LYP input with **only the functional's name changed** (ORCA: `! B3LYP def2-SVP` to `! PBE def2-SVP` and `! BLYP def2-SVP`; Psi4: `energy('b3lyp5')` to `energy('pbe')` and `energy('blyp')`), by the runner's `functional:` variant. They are tried here and not offered by the application.
* **The difference** d = E(Psi4) - E(ORCA) in mEh per cell, and for each functional its **median over the six molecules**. Geometries are the agreement check's (RDKit ETKDG seed 7 plus MMFF, the same coordinates in both inputs).
* **Smoke check, not a record:** before the run, one job per engine for each of PBE and BLYP on water in a scratch folder checks that each keyword is accepted and an energy parses. **Its energies are not read.** If either engine refuses either keyword, nothing is run and a new plan names the substitute.

## The thresholds, fixed from earlier artifacts and not tuned here

* A functional **carries an offset** when its median d is at least **0.1 mEh** (version 3's own threshold, the 0.1 mEh below which an offset was not treated as reproduced) and is **free of one** when it is below **0.05 mEh** (half of that, so that a median in between is neither).
* The four medians are **the same size** when the largest is at most **2 times** the smallest.
* The Hartree-Fock control must agree within **0.01 mEh** (version 3's HF floor was 0.00001 mEh): a larger move means the pipeline is not measuring what it names.
* At most one molecule may lack a run on either engine per functional; the Hartree-Fock control may lack none.

## The reading rule, fixed now (the first line that holds decides)

1. **NOT EVALUABLE:** a Hartree-Fock control, or more than one molecule of any of the four functionals, lacks a run on either engine.
2. **NOT VALID:** the Hartree-Fock control moved by more than 0.01 mEh, or **B3LYP's median is below 0.1 mEh** (version 3's offset did not reproduce at these cells, so there is nothing to explain).
3. **COMMON TO DFT:** all four functionals' medians are at least 0.1 mEh and the largest is at most twice the smallest.
4. **FUNCTIONAL-SPECIFIC:** at least one functional's median is below 0.05 mEh (and, by rule 2, B3LYP's is not): the offset is in how a functional is coded, and the report names which carry it and which do not.
5. **MIXED** otherwise.

## What each verdict does (decided now)

No verdict changes the engine or `PSI4_METHODS`: the offset (about 0.2 kcal/mol at its largest) is documented in `docs/PSI4_ENGINE_DESIGN.md`, not corrected.
* **COMMON TO DFT:** recorded as not being any functional's coding. The next candidates are listed, not tested: a numerical treatment common to the DFT part (a density or basis-function screening threshold, the orientation of the angular grid, how each program integrates the density), and each would need its own plan.
* **FUNCTIONAL-SPECIFIC:** the functional names are recorded and the ingredient follows from which are free of it (reported, not in the rule): PBE and PBE0 free and BLYP and B3LYP carrying it points to B88 exchange or LYP correlation; BLYP free with B3LYP carrying it points to B3LYP's own mixture (its local part or its coefficients); PBE carrying it with BLYP free points to PBE's exchange or correlation.
* **MIXED:** recorded as such, with the table; a further plan decides what to add.
* **NOT VALID, NOT EVALUABLE:** nothing is claimed; the cause is fixed and the ladder re-run under a new plan.
* A result is never explained away by hand, and the plan is not changed after a result.

## Reported, and in no rule

* The median offset per electron for each functional (whether it scales with the size of the molecule, which version 3 suggested), and the table of every cell with the electron count of each molecule.

## What it cannot say

* **Six molecules, one basis, one grid per program as shipped**: a result about these cells. It does not cover other bases, open shells, charged species or the functionals not on the ladder (M062X, with its own grid sensitivity, is not).
* **Names, not definitions:** "PBE" and "BLYP" are taken to be the same functional in both programs because each program's keyword says so; this is what the experiment is not able to check. A difference found could be a coding difference in the functional or in how a program applies it.
* **It follows outcomes that were seen:** version 3's per-functional offsets and the grid test's split were read before this plan; the hypothesis was chosen with them in view. PBE and BLYP have never been run on either engine for this project, so those two columns are new data; B3LYP, PBE0 and HF at def2-SVP repeat cells version 3 already measured.
* It says nothing about which program is right.

## Run order and records

After the smoke check, from `benchmarks/psi4_agreement`: `run_functional_ladder.py run --engine orca`, `run --engine psi4`, `report`, `--workers 3 --cores 4`, one engine at a time (60 jobs; about half an hour), `src/` clean, one commit (the report refuses mixed commits or a dirty `src/`). Records: `artifacts_ladder/ladder/<engine>.jsonl`, `report.txt`, `verdict.json`.

## Outcome

Not yet run.
