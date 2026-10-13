# The Lewis pairing gate: preregistration

**Frozen 2026-10-13, in the commit that adds this file, `src/openchem/app/lewis_gate.py`, the drive steps that use it and the two scripts. Before any ORCA
job of BH3 or BF3, and before the carbon monoxide floor below has been measured.** Everything in sections 1 to 8 is fixed. Section 9 is where the outcome is
written, below a rule, and nothing above the rule is edited afterwards. An amendment is allowed only before the number it concerns exists, and it is a new
commit that says what it changes and why (the held-out discipline this project already follows).

The design is `docs/RECIPES_DESIGN.md` section 10. This file is the decisions that section left to this commit: the rule for the tolerance, the exact
conditions of each verdict, and what may be repeated.

## 1. The claim, and what a pass does not say

> On ORCA 6.1.1 at B3LYP/def2-SVP, the Lewis pairing recipe, fed only by stored single-point and delta-SCF runs at the ORCA-optimized geometry of each molecule,
> gives the four documented numbers for BH3/CO and BF3/CO each within **T** eV, and the frontier-orbital line and the hardness line still disagree about which
> borane binds carbon monoxide better, as documented. No field combines the lines, and the role is the one the person set.

A pass says the recipe's wiring reproduces a number someone else already documented, on this machine, with the sourcing intact. It does **not** say the two lines
are chemically right (the disagreement is a known failure of the hardness line on this pair), that another method, solvent or pair reproduces, or that the
single point and the optimization's own orbital table agree (reported separately, section 4).

**What has been run before this commit, disclosed.** No ORCA job of BH3 or BF3 has been run by this machinery. The recipe's tests have been fed the documented
numbers as stored-run objects (`tests/test_lewis_pairing_eval.py`), which proves the wiring and says nothing about ORCA. The only ORCA evidence for these two pairs is
the earlier work behind `tests/test_lewis_adduct.py` (its comment: "Real ORCA 6.1.1 B3LYP/def2-SVP numbers: geometries optimized by ORCA, then delta-SCF hardness
from a compound job at that geometry, and the frontier energies from the optimization's own orbital table").

## 2. The documented values

Typed into `app/lewis_gate.py` (`DOCUMENTED`) and compared with `tests/test_lewis_adduct.py` by a test, so neither can move alone. All in eV.

| Molecule | HOMO | LUMO | Hardness (delta-SCF) |
|---|---|---|---|
| CO (the base in both pairs) | -10.17 | not used | 8.40 |
| BH3 (acid) | not used | -2.04 | 6.77 |
| BF3 (acid) | not used | 0.73 | 9.29 |

| Pair | Frontier gap E_LUMO(acid) - E_HOMO(base) | \|d eta\| = \|eta(acid) - eta(base)\| |
|---|---|---|
| BH3/CO | **8.13** | **1.63** |
| BF3/CO | **10.90** | **0.89** |

These four numbers are the ones compared. They follow from the six inputs above (a test asserts it), and carry two decimals, so a number derived from them is good
to about 0.01 eV. The disagreement: the gap orders BH3 below BF3 (BH3 binds CO), and the hardness difference orders BF3 below BH3 (the opposite).

## 3. Procedure

The application's own path throughout, driven by `OPENCHEM_DRIVE` (no mouse), on this machine's ORCA (`D:\ORCA\orca.exe`). **Method B3LYP def2-SVP, gas phase, charge 0,
multiplicity 1** (the panel's default for a closed-shell neutral). The keyword line the application writes is `! B3LYP def2-SVP Opt` for the optimization and `! B3LYP
def2-SVP` for the single point and for each of the three jobs of the delta-SCF compound input (`orca_engine.build_input`: neutral, cation at charge +1 and anion at -1, both
doublets, at the geometry as supplied).

For each molecule, in this order:

1. Add it from its SMILES (BH3 `B`, BF3 `FB(F)F`, CO `[C-]#[O+]`) and embed 3 conformers with the panel's default method.
2. One ORCA **Geometry Optimization**. The optimized conformer is then the canonical one since #312, and the script asserts `conformer_report` says `canonical_method: orca_opt` and
   `canonical_mapped: true` before any later job.
3. One **Single Point**, then one **Hardness / Softness (delta-SCF)**, each at that canonical geometry. A job is never started while another runs (`qc_wait`).

Then, for the gate, the pairing window evaluates **BH3 first and CO second, role = acid** (the documented orientation) and **BF3 first and CO second, role = acid**, at
B3LYP def2-SVP in the gas phase. Every stored run is read at the precision it recorded.

## 4. What is recorded (so nothing is chosen afterwards)

Into `benchmarks/lewis_gate/artifacts/floor.json` and `pair.json`, and quoted in section 9: for every run its id, calculation type, status, method, charge, multiplicity, the
ORCA version it recorded, its input fingerprint and every descriptor value; the six bound values of each pair and the four derived numbers at full precision; the report's own
printed two-decimal lines; every binding's state; the difference of each of the four numbers from its documented value, signed; and, **reported and not decided on**, the
HOMO and LUMO of each molecule from the optimization's own orbital table beside the single point's, with whether each difference exceeds T. A single-point/optimization difference beyond
T is a finding about the documented procedure and is reported as such; it is not a failure of the recipe (design section 10).

## 5. The noise floor, and the rule for T

**The floor F** is the largest of these differences, over the HOMO, the LUMO and the delta-SCF hardness, on carbon monoxide:

* the **same input twice**: the single point and the delta-SCF each run twice on one optimized geometry (a repeat that cannot be a cache hit: the quantum-chemistry service never
  reads its cache, only writes it; the two runs' input fingerprints must be equal or the floor is not recorded); and
* the **whole chain twice**: a second carbon monoxide molecule is embedded, optimized, single-pointed and delta-SCF'd independently, and compared with the first. The pair run
  re-optimizes each molecule, so this is the repeat the gate itself is exposed to. (The design names only the first; including the second can only raise F, never lower it,
  and is decided here, before either exists.)

**The rule, written before F was measured:**

```
T = max(0.01 eV, F rounded UP to the next 0.01 eV)
```

and **if that is more than 0.37 eV there is no tolerance, and the gate is NOT EVALUABLE**. The bounds are the design's: 0.01 eV because the documented numbers are good to about that;
0.37 eV because the smallest margin the claims rest on is the ordering of the hardness differences, 1.63 against 0.89 = 0.74 eV, and a tolerance of half that or more could let the two
orderings swap. T is never widened.

T is fixed **once, by hand, in a commit of its own**, by writing `benchmarks/lewis_gate/tolerance.json` (T, F and the floor artifact), **before the pair is run**. `lewis_gate_begin`, the first
step of the pair script, ends the run before one job if T is unset, or if it is not exactly what this rule gives the floor in the artifact.

"Within T" means `|measured - documented| <= T`, with a float slack of 1e-9 eV. The measured value is derived from the six bound values at full precision.

## 6. The verdicts

Decided by `app/lewis_gate.judge`, which is pure and tested with invented numbers (`tests/test_lewis_gate.py`). Every reason is collected; none hides another.

**PASS** requires **all** of:

1. each of the four numbers within T of its documented value;
2. the frontier gap of BH3/CO below that of BF3/CO;
3. the hardness difference of BF3/CO below that of BH3/CO (the disagreement reproduces: a recipe that "fixes" it has altered the chemistry);
4. no field that combines the lines: no fact label and no printed line name (the text before a line's first colon) containing `score`, `combined`, `overall`, `composite`, `total`, `rank` or
   `rating`, and all three lines (`Drago-Wayland enthalpy`, `Frontier orbital gap`, `HSAB hardness match`) present **by the name the report prints them under** (the Drago-Wayland line is a fact
   filed under the report's own name, so it is found by its printed name and not by its fact label; found by testing the reader on the real evaluator before any measurement existed);
5. the role recorded as set by the person (the report's `Role: as you set it.`).

**FAIL** is any of these not holding, when the gate could be evaluated. The documented values stay the documented values, the recipe's numbers are published beside them with the
signed differences, **the word "reproduces" is not used**, and T is not widened.

**NOT EVALUABLE** (nothing is claimed either way, and it takes precedence over FAIL) when any of: T is unset, or outside [0.01, 0.37]; any run recorded an ORCA version other than 6.1.1
(a different one is a recorded difference, not a pass); any run did not complete; any of the six numbers of a pair was not bound to a current run; the report prints a line its own evidence
does not give (a defect in the code, not a result about chemistry); or the gate was not given exactly the two documented pairs.

## 7. After each outcome

* **PASS:** `docs/RECIPES_DESIGN.md` section 10 and the user guide say the Lewis pairing recipe reproduced the documented numbers on real ORCA 6.1.1 at B3LYP/def2-SVP within T, name the
  commit, and the BH3/BF3/CO reservation is lifted for the recipe's tests and drive scripts.
* **FAIL:** the same places say it did not, with the numbers beside the documented ones. The recipe stays as it is: a failed gate changes what is claimed, not what ships (every number the
  window shows already comes from a named stored run). The cause is investigated as a separate piece of work, never by editing this file.
* **NOT EVALUABLE:** not a result. See section 8.

## 8. What may be repeated, and what may not

* **A run that did not finish** (ORCA crashed, the script lost a job) **may be repeated unchanged**, and every attempt is listed in section 9.
* **NOT EVALUABLE may be repeated after its cause is fixed**, with the same T and the same conditions: a code defect found this way is fixed in a commit that says so, and each attempt is listed.
* **PASS and FAIL are final.** A decided gate is not re-run to see whether the number moves, and nothing about T, the method, the molecules, the starting geometry or the conditions
  above is changed after a decided outcome.
* The same-input repeat of section 5 is a repeat of the *measurement*, not an attempt at the gate, and is done once.

## 9. Outcome

*(Empty at the freezing commit. The noise floor, the commit that fixes T, and the gate's outcome are appended below this rule, each with its commit, and nothing above it changes.)*

---


### 9.1 The noise floor, measured 2026-10-13 17:41 to 17:43 (UTC-4), commit that adds this section

`benchmarks/visual/lewis_gate_floor.json`, real ORCA 6.1.1, B3LYP def2-SVP, charge 0, multiplicity 1, `VERDICT PASS` (2 assertions, 0 app errors, 0 driver failures;
`artifacts/floor.drive_report.json`). Carbon monoxide only; no borane has been run. Every value is the stored run's, as recorded.

| Chain | Job | Run | Input fingerprint | HOMO (eV) | LUMO (eV) | Hardness, delta-SCF (eV) |
|---|---|---|---|---|---|---|
| a_first | sp | `b7e8f8fb` | `8a68e8fd8c59` | -10.1709 | -0.7212 |  |
| a_first | delta_scf | `9ef28175` | `8a68e8fd8c59` |  |  | 8.402038211633789 |
| a_second | sp | `59ec10a0` | `8a68e8fd8c59` | -10.1709 | -0.7212 |  |
| a_second | delta_scf | `58e09afe` | `8a68e8fd8c59` |  |  | 8.402038211633789 |
| b | sp | `53923d06` | `7cf038d0a9ba` | -10.1709 | -0.7212 |  |
| b | delta_scf | `b5e9fd55` | `7cf038d0a9ba` |  |  | 8.402038211633789 |

* **Same input twice** (`a_first` against `a_second`, one fingerprint): the largest difference of the HOMO, the LUMO and the hardness is **0.0 eV**.
* **The whole chain twice** (`a_first` against `b`, a second carbon monoxide embedded, optimized and run independently): the largest difference is **0.0 eV**.
* **F = 0.0 eV.** Six distinct ORCA jobs (distinct run ids; the service never reads its cache), identical to the four decimals ORCA prints orbital energies in and the full precision of the hardness,
  with an identical SCF energy (-113.17287091914 Eh) in all six: ORCA is deterministic on an identical geometry, and the two optimizations converged to the same one.
* **By the rule of section 5, T = max(0.01, 0.0 rounded up to 0.01) = 0.01 eV.** `tolerance.json` is written in this commit, with the floor artifact, and `lewis_gate_begin` checks it.

**Disclosure, seen before T was fixed and not used in choosing it** (T follows from the rule, and is 0.01 eV whatever these were): the floor run also gave carbon monoxide's own numbers, HOMO -10.1709 eV and
delta-SCF hardness 8.4020 eV, against the documented -10.17 and 8.40, so the base's half of both pairs reproduces on this machine. Nothing about a borane has been seen.
