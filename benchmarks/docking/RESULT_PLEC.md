# Result: PLECscore re-ranking of Vina's poses

Run 2026-10-30 under `PREREGISTRATION_PLEC.md` (including its Amendment 1), ODDT 0.7, PLECscore
`linear` P5 L1 (PDBbind v2016). Poses and prepared receptors are kept outside the repository.

**Verdict by the preregistered rule: INCONCLUSIVE.** The input-sanity rule failed (median over the
deciding receptors of the highest predicted pKd was below 4.0), which the rule orders before any
count is read.

| Population | Rescored | Vina top pose correct | After PLECscore | Gained | Lost |
|---|---|---|---|---|---|
| Deciding (not in the training set) | 39 of 39 | 28 | 11 | 1 | 18 |
| Reported apart (in the training set) | 8 of 8 | 7 | 0 | 0 | 7 |

6LQA's ligand did not embed, so it has no poses and is in neither row. This run's Vina-order
top-1 call agrees with the survey's recorded class for every receptor (no mismatches).

## What this does and does not say

- The counts point one way (one sign test, mirror direction: 18 lost against 1 gained), but the
  rule forbids reading them as HARMFUL when the model's own outputs are implausible for this
  input. A HARMFUL reading was not claimed.
- It does not show that PLECscore cannot order poses. It shows that fed this way (poses through a
  charge-free PDBQT with Vina's protonation, a receptor rebuilt from a PDBQT, valence checks
  relaxed) it orders them worse than Vina does.
- Seven of the eight training-set receptors also lost their top pose, so memorised complexes did
  not help.
- A fair retest would need properly charged and protonated inputs. That is a new preregistered
  test, not a rerun of this one.

## Consequence

PLECscore is not a candidate for the Docking panel as it stands. The product-side answer remains
the pose-choice sentence (PR 508). Option 3 (another native Windows docking executable) is still
deferred.
