# Arm D-Ph (thiophenol S-H): result

**Reported only; no verdict, and nothing in it decides anything** (`PREREGISTRATION.md` decision D6, section 8). Run 2026-10-28 (started 13:20, finished 14:57) on commit `015b48f8`, a clean tree in every record, one worker with four cores at below-normal priority, after the freeze. Records and report: `artifacts/thiophenol/` (`structures.json`, `structures.meta.json`, `runs.jsonl`, `report.txt`, `run.log`). The arm was run once.

| determination | kcal/mol | computed minus it |
|---|---|---|
| Lim 2007 (0 K value plus the computed step) | 77.83 | +1.94 |
| Luo Table 8.1, low end of the range | 79.40 | +0.37 |
| Devine 2008, UPPER LIMIT (0 K value plus the step) | 81.17 | -1.40 (below the limit, as it should be) |
| Borges dos Santos 2002 / Luo, high end | 83.50 | -3.73 |

**Computed S-H bond dissociation enthalpy at 298 K: 79.77 kcal/mol.** It lies inside the span of the determinations (77.83 to 83.50) and below Devine's upper limit, so by the preregistered span rule (a claim only when more than 5.0 kcal/mol outside the whole span) **no claim is made**: numbers only. No determination is a reference, and this is not a pass or a fail of anything.

## What happened in the run

* 3 structures (parent, radical, hydrogen atom), 6 records, all chains closed, **no job failed**. Lowest vibrations: parent 80 cm-1, radical 164 cm-1.
* **The numerical stage did not fire.** The radical (12 atoms) kept no imaginary mode after the first run's two stages, so this arm did not exercise rule R1 either. Only Arm D can.
* **Cost, measured at one worker and four cores at below-normal priority:** the 13-atom parent 3,245 s (54 min), the 12-atom radical 2,588 s (43 min): 97 minutes for the arm. This is the first measurement of how long a 12 to 13 atom sulfur species takes in this protocol, for planning Arm D.

## What it does not say

It is one molecule against determinations that span about 5.7 kcal/mol; the span is wider than the method's stated error, so the arm cannot tell the method's bias from the disagreement of the references. The sign of the error against the three lower determinations is mixed (+1.94, +0.37) and against the higher ones negative, so there is no sign of the systematic low bias of the other arms that this one number could show or hide.
