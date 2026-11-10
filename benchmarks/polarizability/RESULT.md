# Refit of the additive atomic polarizability table: result (2026-11-05)

Procedure and criteria: `PREREGISTRATION.md` (committed before any fit). Code: `refit.py`. Numbers: `results/refit.json`, `results/secondary_kang1982.json`. Data: Bosque and Sales 2002, kept outside git.

## Deviation from the preregistration (found after the first run, stated here)

The first run (`results/refit_run1_unfixed.json`) dropped phosphorus from the design matrix without dropping the molecules that contain it, so four working-set rows were fitted without their P and the
prediction-set rows with P were predicted without it. Phosphorus is below the preregistered threshold (4 molecules in the working set, 5 needed) and so is **not fitted**; the code was changed to leave
the molecules that contain an unfitted element out of the fit and to predict them, when judging, with the current table's value for that element. This changes the rows used (335 and 85 instead of 339 and
86) and nothing else. The criteria did not move. The first run's numbers were within 0.1 percentage point of the corrected run's on every judged quantity.

## Result against the criteria

| criterion | result |
|---|---|
| 1. refit prediction-set MAPE no worse than the current table's | **pass: 2.15 % against 7.83 %** on 85 held-out solvents (median 1.5 % against 7.9 %, largest 9.9 % against 17.5 %; the current table was biased +7.1 %, the refit is unbiased) |
| 2. no negative value; H, C, N, O, F, Cl, Br, S within a factor 2 of the current one | **pass**, narrowly for hydrogen and fluorine: H 0.203 against 0.389 (ratio 0.52), F 0.263 against 0.464 (0.57); C 1.13, N 1.17, O 0.83, S 1.22, Br 1.03, Cl 1.00, I 1.01 |
| 3. stability under 200 random 80 % refits, every element with 10+ molecules under 10 % standard deviation over mean | **pass**: the largest is 2.6 % (sulfur and fluorine) |

**The table is replaced.** Including the molecules with phosphorus (current value kept for it), the 86-row prediction set gives 2.17 % against 7.94 %. No row had an error over 15 %, so no identity correction was made after the fit.

## The values (A^3, fitted on all 420 usable rows with no unfitted element; standard error in brackets)

H 0.2026 (0.0065), C 1.4965 (0.0111), N 1.1433 (0.0296), O 0.6364 (0.0153), F 0.2631 (0.0122), S 3.0171 (0.0581), Cl 2.2538 (0.0200), Br 3.4334 (0.0605), I 5.6014 (0.1147, **weakly determined: 8 molecules**).
Not fitted and kept at their old, unsourced values: P 2.63 (4 working-set molecules), Si 3.9628, B 1.6, Se 3.38 (no data). Context: Bosque and Sales' own published fit (with an intercept) gives 1.90 % on the
same rows; this fit has no intercept and 2.15 %.

## Secondary check, not gating: 88 compounds of Kang and Jhon 1982 (gas-phase and other, no halogens)

Refit 4.25 % mean absolute error (median 2.7 %), the old table 9.77 %; Bosque and Sales' coefficients 3.88 %. Saturated hydrocarbons from methane to dodecane (12): refit 2.5 %, the old table 13.3 % (always high). Aromatic hydrocarbons (9):
refit 4.4 %, old 7.3 %. Three N,N-substituted names failed to parse because the script lower-cased them, and so are not in the 88.

**Where the refit is worst** (all listed, none hidden): water **-28.2 %** (the old table +6.4 %), the fused aromatics dibenzanthracene -13.4 %, acridine -12.0 %, pyrene -11.5 %, anthracene -11.4 %, chrysene -11.2 %
(the old table was 13 to 16 % low on these too), methane -11.3 % (old +10.8 %), ethylene -10.7 % (old -1.2 %), hydrazine -10.5 %, methanol -9.7 %, hydrogen cyanide +9.7 %. The familiar molecules: benzene -1.3 %,
toluene -1.6 %, CCl4 exact, dichloromethane -1.1 %, **chloromethane -7.7 %** (the old table was +0.6 %, the molecule it had been matched to).

## What this means

- On solvents (the population the data come from) the refit is about 3.5 times closer than the old table, and unbiased.
- Very small molecules are the failure of a purely additive scheme fitted to liquids: the polarizability of water, methane and similar molecules is not a sum of transferable atom values. They are now off the
  other way (low) where the old table was off high. Anyone using this on small molecules should read the stated errors.
- The result is limited by its data: one compilation of room-temperature liquids, 8 iodine and 5 phosphorus molecules, none with silicon, boron or selenium.
- The identity of each molecule rests on OPSIN reading the printed name; 39 names were corrected by hand before the fit (`name_fixes.json`) and one row was excluded.


## Second refit, same day: small molecules (`PREREGISTRATION_2.md`, `refit2.py`, `results/refit2.json`)

**Why.** The first table was judged on solvents. The CRC Handbook's table of molecular polarizabilities (97th ed., PDF pages 1798 to 1809), read afterwards, showed it **16 % low on average for molecules of six atoms or fewer**. The fix, its data and its criteria were registered before any fitting.

**Data.** Bosque and Sales as before, plus the CRC table's entries not marked calculated that OPSIN could turn into a structure with the printed formula and that are not already in the Bosque set (305 molecules; 264 of them with elements this fit covers). The two compilations mix methods (molar refraction at the sodium D line, dielectric constant, beam deflection); no correction was attempted and the spread is part of the error.

**Variants (cross-validated, 10-fold, on development = Bosque working set + 70 % of the CRC molecules):** element-additive 4.65 %; plus one constant per molecule 4.18 %; hydrogen split by neighbour 4.61 %; both 4.11 %. Rule: take the simpler unless the gain is 0.2 points; **the constant (B) was chosen**.

**Holdout (Bosque prediction set + the other 30 % of CRC), touched once:**

| | shipped first table | chosen (B) |
|---|---|---|
| CRC holdout, mean absolute error (n = 83) | 8.38 % | 7.70 % |
| six atoms or fewer: mean absolute error / bias | 16.4 % / -16.1 % | 13.4 % / -9.0 % |
| seven to twelve atoms | 9.1 % / -7.6 % | 7.8 % / -4.6 % |
| over twelve atoms | 5.9 % / -3.9 % | 6.1 % / -4.1 % |
| Bosque prediction set (n = 86) | 2.13 % | 2.11 % |

All three registered criteria hold, so it ships. **What it does not fix:** the CRC error is still about 8 % on average and 13 % for the smallest molecules, a systematic low bias of about 5 % remains, and the worst offenders are ozone (-38 %), iodine chloride (-35 %), tetranitromethane (-32 %), a dinitrile (-25 %), sulfur hexafluoride (-23 %) and dinitrobenzene (-22 %); a purely additive scheme with one constant cannot see conjugation, multiple bonds or unusual bonding. The constant is not physics: it is the offset small molecules need, and it is shared out equally over the atoms in the per-atom output.

**First run, superseded.** The first run applied no minimum-molecule rule and fitted one-molecule metals; it is kept as `results/refit2_run1_unrestricted.json`. The rule (an element is fitted only with five development molecules, other molecules left out) was in the registration; the code now applies it. The variant chosen did not change.

**Values shipped** (all 689 usable molecules; standard errors in `polarizability_refit.json`): H 0.1813, C 1.4816, N 1.1378, O 0.5831, F 0.3084, S 2.8877, Cl 2.2158, Br 3.2543, I 5.4220, **P 3.6319 (8 molecules) and Si 4.1253 (6 molecules), both less certain**, constant 0.4160. Boron (two molecules) and selenium (one) are still unfitted and keep their old unsourced numbers. Water: 1.45 measured, about 1.36 here (about 6 % low), from 28 % low. Still absent: any metal inside a molecule.
