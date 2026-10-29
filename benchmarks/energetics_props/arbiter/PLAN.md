# Computed gas-phase enthalpy as an arbiter: pentaerythritol and NIBTN

Status: PLAN, written 2026-10-29 before any job for the two questions was run. Owner request 2026-10-29. A plan, once a result is seen, is not edited: a change is a new plan that says what was seen first.

## What this is, and what it is not

Two questions in the Phase B energetics arm cannot be settled by the measurements held, and a calculation can say which side of each the evidence leans to.

1. **Pentaerythritol's sublimation leg.** The measured solid enthalpy (-920.6 kJ/mol, Medard and Thomas, now with Stohmann and Langbein as a second root at -915.2 by the study's step) plus four published sublimation values (131.4, 143.9, 161.0 and 163.0 kJ/mol over different temperature ranges and solid forms) gives a gas-phase enthalpy anywhere from about -789 to -758 kJ/mol. R1 needs that leg verified; it is not (PREREGISTRATION.md 12.1, 18.4).
2. **NIBTN's condensed enthalpy.** Two measurements differ by 176 kJ/mol (Medard and Thomas 1949 give about -227; the Army Encyclopedia vol. 8 gives about -403). The entity is `disagree` (PETN_EVIDENCE.md).

The output is a **calculated gas-phase formation enthalpy** with an uncertainty fixed below. It is `computed` (PREREGISTRATION.md 3.1). It does **not** verify either measurement, does not become a corpus row, and does **not** satisfy R1: a calculated gas leg never counts as `measured` (D8). What it can do is say which published rows are compatible with it, and that is all this plan claims.

## What was seen before this plan was written

All from the files in this repository: the sublimation rows and the pentaerythritol enthalpies (PETN_EVIDENCE.md B01-B10), the two NIBTN measurements and Rzhevskiy 2023's W1-F12 value with a Trouton estimate (-402) for NIBTN, PETN's derived gas value (-388.1) and Muravyev 2021's W1-F12 value for it (-395.5). **No calculation for pentaerythritol or NIBTN had been run by this study.** The NIBTN result is therefore not independent of Rzhevskiy 2023 in its conclusion if it agrees, only in its method.

## Method (fixed)

**Species.** Neutral closed-shell gas-phase molecules: pentaerythritol, NIBTN, PETN (validation comparator), and the reference and validation species of `arbiter_core.REFERENCES`.

**Reference values.** The Active Thermochemical Tables, version 1.228, from the table saved in the library, for methane, ethane, methanol, ethanol, neopentane, nitromethane, nitroethane and ethylene glycol. NIST WebBook entries for methyl nitrate (-122 +/- 1), ethyl nitrate (-155 +/- 3) and 2-methyl-2-nitropropane (-177.1 +/- 3.3). NIST's own methanol and ethanol entries are unweighted averages of nine values and are not used.

**Reactions.** Isodesmic: each conserves atoms, bond types and the counts of nitro, nitrate, hydroxyl and quaternary-carbon groups (`balance`, tested). Two independent schemes per target, built from different reference species, so their difference measures the design of the reaction.

| target | scheme A | scheme B |
|---|---|---|
| pentaerythritol | + 4 CH4 -> neopentane + 4 CH3OH | + 4 C2H6 -> neopentane + 4 C2H5OH |
| NIBTN | + 3 CH4 -> 2-methyl-2-nitropropane + 3 CH3ONO2 | + 3 CH4 + C2H6 -> neopentane + CH3NO2 + 3 CH3ONO2 |
| PETN (validation) | + 4 CH4 -> neopentane + 4 CH3ONO2 | + 4 C2H6 -> neopentane + 4 C2H5ONO2 |

**Conformers.** RDKit ETKDGv3, up to 300 embeddings, MMFF94s, pruned at 0.3 A heavy-atom RMSD and a 40 kJ/mol window, the 30 lowest kept. Each is optimised and its frequencies computed at r2SCAN-3c (ORCA 6.1.1); conformers within 12 kJ/mol of the lowest free energy are kept.

**Energies.** DLPNO-CCSD(T)/def2-TZVPP with TightPNO on the geometries above, for every conformer within 6 kJ/mol; the others take the r2SCAN-3c difference to the lowest. A def2-QZVPP single point on the lowest conformer of the targets and of each reference species is the basis-set sensitivity check, reported and not used in the primary number.

**Thermochemistry.** Rigid-rotor harmonic-oscillator at 298.15 K from the r2SCAN-3c frequencies, unscaled. The ensemble enthalpy is the population-weighted enthalpy, the populations coming from the free energies.

**Uncertainty.** `U = sqrt(spread^2 + u_ref^2 + u_val^2)` where `spread` is half the difference between schemes A and B, `u_ref` the larger of the two schemes' reference uncertainties, and `u_val` the RMS error of the validation set, **never below 3.0 kJ/mol** (five points cannot certify a better number). Claims are made at **2U**.

## Validation (run first, and read before the targets)

Predict, with the same protocol, species whose gas-phase value is known: ethanol, ethylene glycol (the nearest to pentaerythritol's hydrogen-bonded hydroxyl groups), nitroethane, ethyl nitrate and 2-methyl-2-nitropropane. Their errors give `u_val`. PETN is computed and reported against its derived comparator (-388.1 +/- 8, deliberately wide, since its sublimation term ranges from 146.6 to 156.9) but is **not** in the RMS: its comparator is not an independent measurement of the gas phase. **No target is read until the validation set is done.** If any validation error exceeds 10 kJ/mol the protocol is reported as failed for that chemistry and the targets are not interpreted.

## Decision rules (fixed now)

**Pentaerythritol.** Convert each sublimation row to a gas value with the Medard and Thomas solid (-920.6): 131.4 -> -789.2, 143.9 -> -776.7, 161.0 -> -759.6, 163.0 -> -757.6. A row is **compatible** if it lies within 2U of the calculated value. Report which rows are compatible and the implied sublimation enthalpy (calculated gas value minus each solid root). If every row or none is compatible, say that the calculation **cannot arbitrate**; do not choose.

**NIBTN.** Implied condensed enthalpy = calculated gas value minus a vaporization enthalpy of **95 +/- 15 kJ/mol** (an assumption: nitroglycerin's measured value is 92.0 +/- 2.1; the +/- 15 covers the extension to a different molecule). A measurement is compatible if it lies within `sqrt((2U)^2 + 15^2)` of that. Report which of -226.8 and -402.9 is compatible. If both or neither, **cannot arbitrate**.

**Neither result changes any rule, any row's `value_kind`, or any number in section 11.** Whatever is found goes into a result note beside this plan, labelled `computed`, and into a proposal for the owner if it bears on R1.

## Costs, and what is not done

Serial wall time is a few hours on this machine with three jobs at once. Not done here: coupled-cluster-quality geometries, anharmonic or hindered-rotor corrections (they largely cancel in an isodesmic reaction but are not assessed), crystal-lattice or phase-change energies, and any claim about the solid-state enthalpy.
