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

Run on 2026-10-19 at the commit that holds this plan (`artifacts/631pG/` and `artifacts/def2tzvp/`, seven molecules each, every job completed at the first attempt, ORCA 6.1.1, four cores, 6 to 7 minutes at 6-31+G* and 9 to 11 at def2-TZVP;
`report.txt`, `summary.json`). **READING RULE: NOT SUPPORTED.**

The sigma-pi gap G (positive when the sigma state is lower) and the sigma shift S = G(6-31G*) - G(basis) (positive when the larger basis moves the sigma state UP relative to the pi state):

| molecule | G at 6-31G* | 6-31+G* | def2-TZVP | S at 6-31+G* | **S at def2-TZVP** | the printed range of |G| | distance of |G| from it, 6-31G* -> def2-TZVP |
|---|---|---|---|---|---|---|---|
| pyrimidine | +0.909 | +0.807 | +0.877 | +0.102 | **+0.032** | 0.48 to 0.80 | 0.109 -> 0.077 |
| pyrazine | +0.683 | +0.654 | +0.632 | +0.029 | **+0.051** | 0.55 to 0.80 | inside -> inside |
| pyridazine | +1.564 | +1.532 | +1.515 | +0.032 | **+0.049** | 1.30 to 1.52 | 0.044 -> 0.000 (inside) |
| imidazole | -1.174 | -1.196 | -1.179 | +0.022 | **+0.005** | 1.23 to 1.67 | 0.056 -> 0.051 |
| pyrazole | -1.157 | -1.246 | -1.239 | +0.089 | **+0.082** | 1.55 (contested) | 0.393 -> 0.311 |
| oxazole | -1.252 | -1.277 | -1.269 | +0.024 | **+0.017** | 1.36 (second-hand) | 0.108 -> 0.091 |
| pyridine | +0.123 | +0.116 | +0.120 | +0.007 | **+0.003** | (EOM-IP-CCSDT +0.15) | |

* **S(def2-TZVP) is at least +0.10 eV in none of the six and below +0.05 in four of them** (pyrimidine, pyridazine, imidazole, oxazole), which is the rule's NOT SUPPORTED. The four that were outside their range were each nearer it at def2-TZVP, and none farther; that was
  not enough on its own.
* **No lowest state changed kind** in any molecule at either basis (sigma lowest in the diazines and pyridine, pi lowest in the azoles).
* **Every S is positive**: the larger basis moves the sigma state up relative to the pi state, in the direction of the sources, but by 0.0 to 0.1 eV, a fraction of the +0.56 eV the ADC(3) table shows for the same change.
* **Pyridine's ladder is the same at the three bases**: sigma 0, pi 0.123 / 0.116 / 0.120, pi 0.803 / 0.799 / 0.806, sigma 2.973 / 2.945 / 2.906 against EOM-IP-CCSDT's 0.15, 0.85 and 3.17. The one number that moves is the in-plane sigma 5b2, away from the reference (0.20 to 0.26 low).
* **Pyrimidine at 6-31+G* has two pi states 0.08 eV apart** (0.807 and 0.887) where the other two bases have one (0.909 and 0.877). G is read from the lowest pi, as the plan says, so its +0.102 at 6-31+G*, **the only S of 0.10 or more anywhere in the probe**, is the lowest pi state of a ladder that has an extra state in it, and not a trend in the basis (def2-TZVP, the larger basis, gives +0.032). Why the extra state appears there was not examined.
* The four "nearer" are not equal improvements: pyridazine moves from 0.044 outside to inside its range, pyrimidine from 0.109 to 0.077, oxazole from 0.108 to 0.091, imidazole from 0.056 to 0.051 (0.005 eV, which is nothing).
* Pyrazole's distance falls from 0.393 to 0.311 eV, but its range is the contested one (gate 4's section 11.4), so nothing is read from it.

**What it says.** The "sigma too low" bias of gate 4 is **not mainly the small basis of B3LYP/6-31G***: going from 6-31G* to a triple-zeta basis with f polarization moves the sigma-pi gaps by 0.00 to 0.08 eV, always toward the sources, and
pyridine's whole ladder is stable to the basis. That is a fraction of the +0.56 eV the same change does to the sigma holes in the pyrimidine ADC(3) table (`shojaei2010` Table 1), so that sensitivity does not carry over to this delta-SCF calculation. Why it does not was not
tested; one candidate is that a delta-SCF relaxes the hole orbital variationally at any basis while the ADC(3) numbers recover that relaxation through the basis, but that is a candidate and not a finding. What is left of the bias, 0.04 to 0.11 eV, could be the functional's, the geometry's
(the 6-31G* optimum), the reference's (vertical against adiabatic, or the assignment) or the method's (delta-SCF against a correlated state), and this probe separates none of them.

**What it does not say.** The geometries are the 6-31G* optima (not re-optimized at the larger basis), one functional, seven molecules, and the ranges are gate 4's (one contested, one second-hand). It does not touch gate 4's outcome.

**Left open.** A second functional (a range-separated hybrid or a meta-GGA), or the same states at EOM-IP-CCSD on pyrimidine, would say whether the residual is B3LYP's.
