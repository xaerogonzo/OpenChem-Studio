# Polarizability refit 2: small molecules (registered 2026-11-05, before the fit)

## Why

`RESULT.md` found the refitted table weak on very small molecules (water 28 % low). That was judged on three small Bosque and Sales solvents. A second, independent set was then read: the CRC Handbook's table of atomic and molecular polarizabilities (97th ed., section 10, "Atomic and Molecular Polarizabilities", T. M. Miller, PDF pages 1798 to 1809). On the entries of that table that are not marked calculated, are not in the Bosque set and could be given a structure, **the shipped table is 5.3 % low on average (7.6 % mean absolute), and 13.7 % low (15.7 %) for molecules of six atoms or fewer.** This was seen before this document was written; it is the reason for the refit, not a result of it. The fix is a different model and different training data, so it is registered here first.

## Data

- **Bosque and Sales 2002**, as in `PREREGISTRATION.md` (426 solvents, structures as resolved there).
- **CRC table** (page numbers above). A record is the molecule's name, formula, value in 10^-24 cm^3 (= cubic angstrom) and its note. Kept: no "calculated", "theor", "ab initio" or "semi" in the note; no deuterium; at most 40 atoms. The name is given to OPSIN; a structure is kept only if its formula equals the printed formula. A structure already in the Bosque set, or already taken from this table, is dropped. The table is a bulk copy of a published table and stays outside git; the parsing and resolving scripts are committed with the result.
- Both tables report values from several methods (molar refraction at the sodium D line, dielectric constant, beam deflection, Stark effect); no correction between them is attempted. The spread this causes is part of the error, and the result says so.

## Split (seed 20261105)

- **Development:** Bosque working set (340) plus a random 70 % of the CRC molecules.
- **Holdout, touched once, after the variant is chosen:** Bosque prediction set (86) plus the other 30 % of the CRC molecules.
- The Bosque prediction set was seen in the first refit. It is kept as a regression guard (the new table must not be worse on it by more than 0.5 points), and the CRC 30 % is the new evidence.

## Variants (all fitted by weighted least squares on the relative error, as before)

- **A** element-additive, no intercept (the shipped one, refitted on the new development set).
- **B** A plus one constant per molecule.
- **C** A with hydrogen split by its neighbour (on C, on O, on N, other).
- **D** C plus the constant.

## Choice and criteria

1. The variant is chosen by 10-fold cross-validated mean absolute percentage error on the development set. A variant with more parameters is chosen only if it beats the simpler one by at least 0.2 points; otherwise the simpler one.
2. An element is fitted only with at least 5 development molecules containing it (as before); P, Si, B and Se are fitted if the new data gives them that, and keep their old value and their warning otherwise.
3. The refit ships only if, on the holdout: the mean absolute error on the CRC 30 % is lower than the shipped table's, the Bosque prediction set is not worse by more than 0.5 points, and the signed error (bias) on molecules of six atoms or fewer is smaller in magnitude than the shipped table's. If not, the shipped table stays and the result is reported.
4. Reported either way: errors by size (up to 6 atoms, 7 to 12, over 12), the ten worst molecules, water, and the fitted values with standard errors.

## What it cannot do

A constant per molecule is not physics; it absorbs that small molecules are more polarizable per atom than an additive scheme from larger ones says. It will be described as that. Hybridisation, conjugation and charge are not in any variant, and fused aromatics stay a known weak spot.
