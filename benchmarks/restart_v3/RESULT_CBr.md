# Arm C-Br (four bromine C-H bonds): result

**Reported only; no verdict, and nothing in it decides anything** (`PREREGISTRATION.md` section 8: the kinetics values are disputed and a coupled-cluster calculation sits below them; a claim is made only for a gross failure, an error of more than 5.0 kcal/mol against the kinetics value AND every calculated value). Run 2026-10-28 (after D-Ph, finished 15:34) on commit `015b48f8`, a clean tree in every record, one worker with four cores at below-normal priority. Records and report: `artifacts/bromine/` (`structures.json`, `structures.meta.json`, `runs.jsonl`, `report.txt`, `run.log`). The arm was run once.

| bond | computed | kinetics | error | other determinations | calculated (CC) |
|---|---|---|---|---|---|
| bromomethane C-H | 100.11 | 102.10 | -2.00 | 100.79 to 102.01 (-0.68 to -1.90) | 100.50, 100.57 (-0.40, -0.47) |
| dibromomethane C-H | 96.57 | 98.61 | -2.04 | 97.90 to 103.70 (-1.33 to -7.13) | 97.37, 97.16 (-0.80, -0.58) |
| bromochloromethane C-H | 95.85 | 97.04 | -1.19 | 93.93 (+1.92) | 96.51, 96.65 (-0.66, -0.80) |
| bromoethane alpha C-H | 97.57 | 99.19 | -1.62 | 94.19 to 97.20 (+3.37 to +0.36) | none |

kcal/mol, error = computed minus reference. **No claim on any of the four** (numbers only).

## What happened in the run

* 9 structures (4 parents, 4 radicals, the hydrogen atom), 18 records, all chains closed, **no job failed**. Job times 2 to 8 minutes (bromoethane radical longest, 479 s); the whole arm about 36 minutes at one worker.
* **No radical kept an imaginary mode**; lowest vibrations 155 to 247 cm-1 for the radicals, so the numerical stage never fired here either.
* Nothing was re-run, selected or excluded after seeing the numbers.

## What it shows, and what it does not

* **All four errors against the kinetics values are negative (-1.19 to -2.04)**, as in Arm C: the calculation runs low. Against the coupled-cluster values the errors are smaller (-0.4 to -0.8), which is the direction the preregistration expected if the kinetics values are somewhat high; it is a description of these numbers, not a ruling on which reference is right, and no reference was chosen or corrected.
* The dibromomethane determinations span 97.90 to 103.70, so its error range (-1.33 to -7.13) reflects the disagreement among references more than the method. Bromoethane has no calculated value; against its other determinations the computed value is above the lowest and just above the highest of them (+0.36).
* This says nothing about the calculator's scope: bromine is outside it, Arm C-Br adds no evidence for adding it, and the preregistration allows none to be drawn from a reported-only arm.
