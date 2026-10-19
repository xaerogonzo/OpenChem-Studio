# The second-functional probe (after gate 4's outcome; exploratory, decides nothing)

Written 2026-10-19, **before any job of it was run**, and committed before the first one. Gate 4's outcome (PARTIAL, `../PREREGISTRATION.md` section 11) is final and this does not touch it. It is the second of the two checks that section 11.6 left open for
the sigma-state bias, the first being the larger-basis probe (`../basis_probe/PLAN.md`, section 11.7: NOT SUPPORTED, the bias is not mainly the basis).

## The question

Gate 4's gaps that fell outside their printed ranges all fell on the side where the **sigma state is too low relative to the pi states** (section 11.4: four uncontested gaps, 0.04 to 0.11 eV), and a larger basis moved them by 0.00 to 0.08 eV only. **Is the remainder B3LYP's?**
That is: does a functional that differs from B3LYP in one respect a candidate explanation names, the fraction of exact exchange at long range and with it the self-interaction error (a candidate, not an established cause), put the sigma and pi holes where the sources do?

## What is run

* **Functional:** **wB97X-D3** (a range-separated hybrid: a small fraction of exact exchange at short range rising to 100% at long range, with D3 dispersion, a correction that depends on the geometry and not on the state, so it should not move a gap; the water check below showed ORCA's output naming WB97X-D3 for both exchange and correlation). It is chosen because it differs from B3LYP's fixed 20% exact exchange in exactly that respect, **not because the literature says it is better at this**: this plan makes no claim about which functional is the more accurate for these holes, and
  nothing in it depends on one. Exactly one functional is run; a different one would be a different plan.
* **Basis:** **6-31G\***, the basis of gate 4, so that B3LYP's column is gate 4's own records (and pyridine's the calibration's) and **nothing but the functional differs**. The larger-basis probe found the gaps nearly independent of the basis.
* **Molecules:** the six planar decided molecules of gate 4 with a sigma state in the comparison (pyrimidine, pyrazine, pyridazine, imidazole, pyrazole, oxazole) and pyridine (the calibration; its EOM-IP-CCSDT ladder is the best reference there is). Not selenophene (its pair is pi and pi).
* **Geometry:** gate 4's B3LYP/6-31G* optimized geometries (`../artifacts/geometries.json`, `../artifacts/calibration/geometries.json`), oriented with the plane as xy, **not re-optimized**: a difference from B3LYP is then a functional effect on the energies and nothing else.
* **Procedure per molecule:** the larger-basis probe's: gate 4's exhaustive search (the application's compound input with holes in the HOMO-1 to the HOMO-7, `run_gate.exhaustive_run`), the N+1 job removed (the probe needs the cation states only), and the same reading of every state's kind from the Loewdin spin populations.
  `../basis_probe/run_probe.py --method wB97X-D3 --basis "6-31G*" --tag wb97xd3 --out ../functional_probe/artifacts` (the runner gained `--method` and `--out`, with the defaults every earlier run used). A job that does not finish is repeated unchanged up to three times, as in the gates. The keyword was checked on water before this plan was committed
  (ORCA 6.1.1 reads `wB97X-D3 6-31G*`, a neutral and a hole-start cation in one compound input both finish); that check is not part of the records.

## What is compared, fixed now

For each molecule, from the distinct states (jobs within 0.01 eV are one state):
* the **sigma-pi gap** G = E(lowest pi state) - E(lowest sigma state) in eV (positive when the sigma state is lower), at B3LYP (gate 4's records) and at wB97X-D3, and the **shift** S = G(B3LYP) - G(wB97X-D3): **positive when the functional moves the sigma state UP relative to the pi state**, which is the direction of the sources;
* whether the **lowest state's kind** is the same as at B3LYP (a change is reported first, whatever the rest says);
* the distance of |G| from gate 4's **printed range** (`../PREREGISTRATION.md` section 4) at both functionals;
* for pyridine, the ladder (sigma 7a1, pi 1a2, pi 2b1, sigma 5b2) against EOM-IP-CCSDT's +0.15, +0.85, +3.17 eV (reported; not in the rule).

## The reading rule, fixed now (the first line that holds decides)

* **A record that did not complete** for any of the six: the rule is not applied for that molecule and the outcome says **NOT YET**, naming it.
* **SUPPORTED** (the remainder of the bias is B3LYP's) if **at least three of the four gaps that were outside their range at B3LYP** (pyrimidine, pyridazine, imidazole, oxazole) **are inside it at wB97X-D3**, **and pyrazine's stays inside its range**, **and no lowest state changes kind**.
* **NOT SUPPORTED** (the gaps are where B3LYP had them; the bias is not specific to B3LYP's exchange) if **|S| is below 0.05 eV in at least four of the six** (pyrimidine, pyrazine, pyridazine, imidazole, pyrazole, oxazole).
* **MOVED** otherwise: the functional changes the gaps by 0.05 eV or more in at least three of the six without bringing three of the four into their ranges. Said as such, with the count that moved toward the sources (S at least +0.05) and the count that moved away (S at most -0.05).
* **Two of the references are weak and count in full anyway:** pyrazole's is contested in its ORDER (section 11.4) and oxazole's is second-hand. Both are in the counts as the rule is written (oxazole among the four ranges, both among the six shifts), and the outcome says which of them decided it if either did.
* No tolerance, limit or range of gate 4 is changed by anything here, the molecule set is not extended after seeing a result, and **the application's functional (B3LYP) is not changed by this plan whatever it finds**: that would be a decision for Alex with its own preregistration.

## What it cannot say

* It holds the geometry at the B3LYP/6-31G* optimum, so it cannot say what a full optimization with the other functional would give.
* One other functional, one basis, seven molecules: a NOT SUPPORTED says that THIS functional leaves the gaps where B3LYP had them, not that no functional would move them; a SUPPORTED says that THIS one brings them to the printed ranges, not that it is the right one.
* A functional that is better at the gaps could be worse at everything else a Fukui calculation uses; nothing here tests that.
* The ranges themselves are the gate's (pyrazole's contested, oxazole's second-hand), and they are vertical energies read from photoelectron bands while the calculation is a delta-SCF at a fixed geometry.

## Records

`artifacts/wb97xd3/runs.jsonl` (one JSON line per attempt, with the commit, the dirty flag, the ORCA version and the input hash), `report.txt` and `summary.json` from `report_functional.py`, and the outcome written below, after the run and after nothing else.

## Outcome

Run on 2026-10-19 at the commit that holds this plan (`ba476185`, tree clean; `artifacts/wb97xd3/`, seven molecules, every job completed at the first attempt, ORCA 6.1.1, four cores, 4 to 6 minutes each; `report.txt`, `summary.json`). **READING RULE: MOVED.**

The sigma-pi gap G (positive when the sigma state is lower) and the shift S = G(B3LYP) - G(wB97X-D3) (positive when the functional moves the sigma state UP relative to the pi state, the direction of the sources):

| molecule | G, B3LYP | G, wB97X-D3 | **S** | printed range of \|G\| | distance of \|G\| from it, B3LYP -> wB97X-D3 |
|---|---|---|---|---|---|
| pyrimidine | +0.909 | +0.633 | **+0.276** | 0.48 to 0.80 | 0.109 -> 0 (inside) |
| pyrazine | +0.683 | +0.337 | **+0.346** | 0.55 to 0.80 | 0 (inside) -> **0.213 (below it)** |
| pyridazine | +1.564 | +1.451 | **+0.112** | 1.30 to 1.52 | 0.044 -> 0 (inside) |
| imidazole | -1.174 | -1.213 | **+0.039** | 1.23 to 1.67 | 0.056 -> 0.017 |
| pyrazole | -1.157 | -1.288 | **+0.131** | 1.55 (contested) | 0.393 -> 0.262 |
| oxazole | -1.252 | -1.302 | **+0.049** | 1.36 (second-hand) | 0.108 -> 0.058 |
| pyridine | +0.123 | +0.046 | **+0.077** | (EOM-IP-CCSDT +0.15) | |

* **Why MOVED.** Two of the four gaps that were outside their range are inside it now (pyrimidine and pyridazine), where the rule needed three, **and pyrazine's, inside at B3LYP, is now 0.213 eV below its range**, so SUPPORTED fails on both counts. |S| is below 0.05 eV in two of the six (imidazole 0.039 and oxazole 0.049), not four, so NOT SUPPORTED fails. S is at least +0.05 in four (pyrimidine, pyrazine, pyridazine, pyrazole) and at most -0.05 in none.
* **Every S is positive**: the functional moves the sigma state up relative to the pi state in all six, by 0.04 to 0.35 eV, **a spread that reaches well past the bias itself (0.04 to 0.11 eV) and is larger than the larger basis's shift for the same molecule in all six (1.6 to 9 times: pyrimidine 0.276 against 0.032, pyrazine 0.346 against 0.051, pyridazine 0.112 against 0.049, imidazole 0.039 against 0.005, pyrazole 0.131 against 0.082, oxazole 0.049 against 0.017)**.
* **No lowest state changed kind, and the ladder of kinds is the same in all seven molecules**: every molecule lists the same number of states, in the same order of sigma and pi, at both functionals (for example pyrazine: sigma, pi, sigma, pi, sigma, pi, sigma at both; pyridazine: sigma, pi, pi, sigma at both). The functional moves the energies and not the kinds or their order. By gate 4's own 0.25 eV distance tolerance, applied by hand (the judge was not run on this functional), the same one of the six would miss, pyrazole at 0.262 (pyrazine's 0.213 is inside it).
* **Neither functional is closer to the sources everywhere.** wB97X-D3 is nearer the printed range for five of the six (pyrimidine, pyridazine, imidazole, oxazole and pyrazole's contested one) and farther for pyrazine. In the pyridine calibration its sigma 5b2 state is nearer the EOM-IP-CCSDT value (3.242 against 3.17, 0.07 high; B3LYP's 2.973 is 0.20 low) while its two pi states are farther (1a2 at 0.046 against 0.15, and 2b1 at 0.777 against 0.85; B3LYP's are 0.123 and 0.803).

**What it says.** The sigma-pi gaps of these molecules **depend on the functional by 0.04 to 0.35 eV**, and the "sigma too low" bias of gate 4 is one point on that dependence and not a fixed error of the calculation: the other functional moves every gap toward the sources, by more than the bias in four molecules, which puts two of the four out-of-range gaps inside their ranges, leaves the other two
nearer, and takes pyrazine's gap, inside at B3LYP, out of its range. That spread is **larger than gate 4's 0.25 eV tolerance in two molecules (pyrimidine 0.28, pyrazine 0.35) and smaller than the 0.5 eV window of the note about competing states**, so the printed ranges do not choose between the two functionals (each is nearer for some molecules), and what is the same at both is the **kind and the order** of the states, which is what gate 4's claims were about.

**What it does not say.** That wB97X-D3 is the better functional for these holes (it is nearer for five of the six and farther for pyrazine, and in pyridine nearer for one of three states and farther for two), that B3LYP is, or what a correlated calculation gives. The geometries are B3LYP's, one other functional, one basis, seven molecules. The weak references (pyrazole's, oxazole's) count in full as the rule says, and **neither decided the outcome**: without them pyrazine is still
outside its range and imidazole outside its own (SUPPORTED still fails), and three shifts of 0.11 or more remain (NOT SUPPORTED still fails). The application's functional is unchanged.

**Left open.** The check that needs no functional: the same states at EOM-IP-CCSD on pyrimidine and pyrazine (the two molecules where the functionals differ most), which would say which of the two moved toward the right answer; and, separately, the geometry (the diazines re-optimized with each functional).
