# Computed arbiter: result

Status: RESULT of `PLAN.md` (fixed 2026-10-29), run 2026-10-30 to 2026-10-31. Every number here is **`computed`** (PREREGISTRATION.md 3.1, D8). Nothing below verifies a measurement, becomes a corpus row, changes a `value_kind`, a rule or a section-11 number, or satisfies R1. The plan was not edited after this result was seen.

Protocol as planned: RDKit ETKDGv3 conformers, r2SCAN-3c optimisation and frequencies (ORCA 6.1.1), DLPNO-CCSD(T)/def2-TZVPP TightPNO single points on the conformers within 6 kJ/mol, RRHO at 298.15 K, isodesmic schemes A and B (PLAN.md). One deviation from the plan's text: the run was restarted once (the first attempt wrote its temporary files to a hard disk and was too slow), so every single point reported here comes from the second run, on identical inputs. The def2-QZVPP sensitivity check was **not run**.

Raw files are outside the repository; the reaction enthalpies and formation enthalpies are in `results/schemes_tz.json` (validation set) and `results/schemes_tz_targets.json` (with the targets).

## Validation, read first

| species | calculated dfH (kJ/mol) | reference | error |
|---|---|---|---|
| ethanol | -233.42 | -234.88 | +1.46 |
| ethylene glycol | -388.01 | -389.25 | +1.24 |
| nitroethane | -103.57 | -102.73 | -0.84 |
| ethyl nitrate | -154.75 | -155.00 | +0.25 |
| 2-methyl-2-nitropropane | -175.08 | -177.10 | +2.02 |

RMS 1.31 kJ/mol; the largest error is 2.02, far under the 10 kJ/mol failure line, so the protocol is not failed and the targets are interpreted. `u_val` takes the plan's floor, **3.00 kJ/mol**.

## Targets

Value = mean of schemes A and B; `spread` = half their difference; `u_ref` = the larger of the two schemes'; `U = sqrt(spread^2 + u_ref^2 + u_val^2)`.

| target | scheme A | scheme B | mean | spread | u_ref | U | 2U |
|---|---|---|---|---|---|---|---|
| pentaerythritol | -782.48 | -788.30 | **-785.39** | 2.91 | 0.96 | 4.29 | 8.58 |
| NIBTN | -331.22 | -329.19 | **-330.20** | 1.01 | 4.46 | 5.47 | 10.94 |
| PETN (comparator) | -414.30 | -415.29 | -414.79 | 0.49 | 12.01 | 12.39 | 24.79 |

All in kJ/mol, gas phase, 298.15 K. The mean is the plan's "calculated value"; the plan does not say how to combine A and B, and the mean was taken here, not chosen after seeing the numbers.

## Pentaerythritol: the calculation separates the sublimation rows

Each row converted to a gas value with the -920.6 solid, and compared with -785.39 at 2U = 8.58:

| row | gas value | difference | verdict |
|---|---|---|---|
| sublimation 131.4 | -789.2 | -3.81 | compatible |
| Font and Muntasell 1995, 134 | -786.6 | -1.21 | compatible |
| sublimation 143.9 | -776.7 | +8.69 | not compatible, by 0.11 kJ/mol |
| sublimation 161.0 | -759.6 | +25.79 | not compatible |
| sublimation 163.0 | -757.6 | +27.79 | not compatible |

Some rows are compatible and some are not, so the plan's "cannot arbitrate" condition does not apply: the calculation leans to the two low sublimation values and away from the two high ones. The 143.9 row misses by 0.11 kJ/mol, which is inside what the choice of `u_val` floor or of mean-versus-one-scheme could move, so it should be read as borderline, not as a rejection. The implied sublimation enthalpy is 135.2 kJ/mol from the -920.6 solid and 129.8 from the -915.2 solid.

This says which gas-phase value the other numbers agree with. It does not make the solid enthalpy or any sublimation row `measured`, and R1 stays unmet.

## NIBTN: neither measurement is compatible

Implied condensed enthalpy = -330.20 - 95 = **-425.2 kJ/mol**, tolerance `sqrt((2U)^2 + 15^2)` = 18.57:

| measurement | difference from implied | verdict |
|---|---|---|
| -226.8 | +198.40 | not compatible |
| -402.9 | +22.30 | not compatible, by 3.7 kJ/mol |

By the rule fixed in the plan, neither is compatible, so the calculation **cannot arbitrate**. No choice is made. As plain facts and not a finding: the implied value is 198 kJ/mol from the first measurement and 22 from the second, and the second sits just outside the tolerance, which rests on the assumed vaporization enthalpy of 95 +/- 15.

## PETN: the comparator disagrees, and that weakens the NIBTN number

The plan reports PETN against its derived comparator and keeps it out of the RMS, with no pass line. The calculated -414.79 is 26.69 kJ/mol below the derived -388.1 (+/- 8) and 19.29 below Muravyev 2021's W1-F12 value of -395.5. This is by far the largest deviation in the study, and PETN is the nearest relative of NIBTN (nitrate esters on a neopentane core). The five validation species are all small, and ethyl nitrate, the only nitrate ester among them, is reproduced to 0.25. So the validation does not show the protocol failing for nitrate esters, but PETN's gap means it has not been shown to hold for a four-nitrate molecule either. Possible causes (the comparator's own range, interactions among the four nitrate groups that a scheme built from single nitrates does not carry, the frequency treatment of a flexible molecule) were not tested here. This is the reason to read the NIBTN result as weaker than its stated U suggests; U does not include it.

## Not done

The def2-QZVPP check on the lowest conformers; anything for the solid state; hindered-rotor or anharmonic corrections.
