# Arm C (six C-H bonds next to fluorine and chlorine): result

**PASS**, by the first run's unchanged limits as the frozen preregistration (`PREREGISTRATION.md` section 8) states them. Run 2026-10-28 on commit `a14c01a3` (the freeze commit), a clean tree in every record, one worker with four cores per job at below-normal priority. Records and report: `artifacts/halogen/` (`structures.json`, `structures.meta.json`, `runs.jsonl`, `report.txt`, `verdict.json`, `run.log`). The arm was run once and not re-judged.

| bond | computed | ATcT 1.228 | error |
|---|---|---|---|
| chloromethane C-H | 98.66 | 99.41 | -0.75 |
| dichloromethane C-H | 95.10 | 96.20 | -1.10 |
| chloroform C-H | 92.17 | 93.31 | -1.14 |
| fluoroform C-H | 104.81 | 106.67 | **-1.86** (largest) |
| formyl fluoride C-H | 100.74 | 101.38 | -0.64 |
| formyl chloride C-H | 90.83 | 90.95 | -0.13 |

kcal/mol. **n = 6, 0 missing. Mean absolute error 0.94, mean signed error -0.94, largest absolute error 1.86; standard error of the mean error 0.24.** Limits: mean absolute error at most 2.5, no error above 5.0, mean signed error within 1.5. None of the three is within the 0.5 kcal/mol band that section 8 says cannot be told apart from a limit.

## What happened in the run

* 13 structures (6 parents, 6 radicals, the hydrogen atom), 26 records, all 13 chains closed, **no job failed**. About 49 minutes of ORCA time in total, one job at a time (the sum of the recorded job times).
* **No radical kept an imaginary mode after the first run's two stages, so the numerical stage never fired.** The lowest vibrations printed are 147 cm-1 (the chloromethyl radical) and above. **Arm C therefore does not test rule R1 at all**; it tests the first run's protocol on bonds it had not seen. R1 is exercised by Arm D (the thiyl radicals).
* Every bond has one conformer (small molecules). Every radical value is analytic.

## What it supports, and what it does not

Per section 9: Arm C PASS means the calculator's stated scope **may add** C-H bonds next to F and Cl, as a separate change (the scope check, the sentence in the calculator's description and a driven run on real ORCA), with Arm C's error stated beside the first two arms'. **That change has not been made and is not part of this result.**

* It is a statement about **these six bonds** (halomethanes and two formyl halides, ATcT references with stated uncertainties of 0.12 to 0.23 kcal/mol). It says nothing about bromine (Arm C-Br, reported only), about C-H bonds in longer halogenated chains, or about vinylic or aromatic halides; the preregistration says the same in section 6.
* **All six errors are negative**: the calculation runs low here as it did before (the first run's mean was -1.53 on 22 bonds, the held-out arm's -1.25 on 27). Arm C's mean is -0.94, less negative than either, by 1.3 standard errors of this arm; with six bonds that is not a finding. The preregistration allows no correction and none is applied.
* The largest error is the fluorinated radical (trifluoromethyl, -1.86), the one place near 2: a hint, not a result, that the correlation of fluorine is where this protocol is weakest.
* Nothing was re-run, selected or excluded after seeing the numbers.
