# The larger-basis probe (after gate 4's outcome; exploratory, decides nothing)

Written 2026-10-19, **before any job of it was run**, and committed before the first one. Gate 4's outcome (PARTIAL, `../PREREGISTRATION.md` section 11) is final and this does not touch it: it is a measurement made afterwards, to answer one
question the literature pass raised.

## The question

Gate 4's gaps that fell outside their printed ranges all fell on the side where the **sigma state is too low relative to the pi states** (section 11.4: four uncontested gaps, 0.04 to 0.11 eV). The pyrimidine ADC(3) table (`shojaei2010` Table 1) shows that a
small basis does exactly that to correlated calculations: from 6-31G to cc-pVDZ++ the sigma holes (7b2, 11a1) move **+0.56 and +0.61 eV** and the pi holes (2b1, 1a2) **+0.11 and +0.18**. **Is the bias B3LYP/6-31G*'s small basis, and does a larger basis move
the sigma states up toward the printed ranges?**

## What is run

* **Molecules:** the six planar decided molecules of gate 4 with a sigma state in the comparison (pyrimidine, pyrazine, pyridazine, imidazole, pyrazole, oxazole) and pyridine (the calibration: its EOM-IP-CCSDT ladder is the best reference there is). Not selenophene (its pair is
  pi and pi: no sigma state to move).
* **Geometry:** **the same B3LYP/6-31G* optimized geometries as gate 4** (`../artifacts/geometries.json`, `../artifacts/calibration/geometries.json`), oriented with the plane as xy, NOT re-optimized: the probe changes the basis of the single-point energies and nothing else, so a difference between bases is a basis effect.
* **Bases:** `6-31G*` (gate 4's records, not rerun), **`6-31+G*`** (adds diffuse functions on the heavy atoms: the diffuse part of the change) and **`def2-TZVP`** (triple zeta with f polarization: the size part). Both with B3LYP, ORCA 6.1.1, `IntAcc 6.0`, four cores.
* **Procedure per molecule and basis:** gate 4's exhaustive search (the application's compound input with holes in the HOMO-1 to the HOMO-7, `run_gate.exhaustive_run`) and the same reading of every state's kind from the Loewdin spin populations. The application's own run is not repeated.
  A job that does not finish is repeated unchanged up to three times, as in the gates.

## What is compared, fixed now

For each molecule and basis, from the distinct states (jobs within 0.01 eV are one state):
* the **sigma-pi gap** G = E(lowest pi state) - E(lowest sigma state) in eV (positive when the sigma state is lower), and the **sigma shift** S(basis) = G(6-31G*) - G(basis): **positive when the larger basis moves the sigma state UP relative to the pi state**;
* whether the **lowest state's kind** is the same as at 6-31G* (the diazines' lowest state is sigma in every source; a basis that made it pi would be a result);
* the distance of the **printed range** of gate 4 (`../PREREGISTRATION.md` section 4) at each basis, for the four comparisons that were outside it at 6-31G* (pyrimidine, pyridazine, imidazole, oxazole) and for pyrazine and pyrazole;
* for pyridine, the ladder (sigma 7a1, pi 1a2, pi 2b1, sigma 5b2) against EOM-IP-CCSDT's +0.15, +0.85, +3.17 eV.

## The reading rule, fixed now

* **The basis hypothesis is SUPPORTED** if S at def2-TZVP is at least **+0.10 eV in at least five of the six molecules** (pyrimidine, pyrazine, pyridazine, imidazole, pyrazole, oxazole) **and** each of the four that were outside their range is nearer its range than at 6-31G* (none farther).
* **NOT SUPPORTED** if S is below +0.05 eV in at least three of the six, or if any of the four is farther from its range.
* **MIXED** otherwise. Said as such.
* A change of the lowest state's kind in any molecule is reported first, whatever the rest says.
* No tolerance, limit or range of gate 4 is changed by anything here, and the molecule set is not extended after seeing a result.

## What it cannot say

* It holds the geometry at the 6-31G* optimum, so it cannot say what a full optimization at the larger basis would give (the literature compares at experimental or optimized geometries of its own).
* B3LYP's own error (the functional, not the basis) is not separated: a larger basis may move the numbers and still leave a gap to the sources.
* The ranges themselves are the gate's (one of them, pyrazole's, contested in order, and oxazole's second-hand).
* Seven molecules, one functional.

## Records

`artifacts/<basis>/runs.jsonl` (one JSON line per attempt, with the commit, the dirty flag, the ORCA version and the input hash), `report.txt`, and the outcome written below, after the run and after nothing else.

## Outcome

(written after the run)
