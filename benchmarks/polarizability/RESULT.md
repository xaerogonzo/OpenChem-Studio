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
