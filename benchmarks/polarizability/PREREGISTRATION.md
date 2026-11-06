# Refit of the additive atomic polarizability table (preregistered 2026-11-05, before any value was fitted)

**Why.** The table in `chem/electronic_properties.py` (`ADDITIVE_POLARIZABILITY`, 13 elements) has no recorded source (`docs/LITERATURE_LOG.md`, "The additive polarizability table's source"). Ten papers
were searched and none contains it. It was matched against a screenshot of another program, which is not a basis we will use. This replaces it with values fitted here, to published experimental
polarizabilities, with the whole procedure fixed in advance.

## 1. Data

- **Primary set:** Bosque and Sales, J. Chem. Inf. Comput. Sci. 42, 1154 (2002), Tables 1 and 2: **426 solvents** with an experimental polarizability in cubic angstroms (the paper derives it from
  refractive index and density). Table 1 (340 solvents) is the authors' working set and Table 2 (86) their prediction set; **that split is used as printed** and not re-drawn.
  The held PDF is `bosque2002.pdf`. The extracted corpus (names, values) is a bulk table and stays OUTSIDE git, in `Documents/OpenChem Studio literature/polarizability_corpus/`; this directory commits
  only the procedure, the name corrections and the counts.
- **Identity:** only the elemental composition matters to an additive model. Each printed name is resolved to a structure by OPSIN and its composition counted (explicit hydrogens). Thirty-nine
  printed names are misspellings, truncated by a line wrap or non-systematic, and were corrected by hand BEFORE any fit (`name_fixes.json`: printed and used name for each). One row is excluded: working-set
  no. 236, "hexamethylphosphoric acid", is not a compound, and the same table lists hexamethylphosphoramide separately with a different value. **425 rows remain (339 working, 86 prediction).**
  Elements and the number of molecules containing each: C 425, H 406, O 235, N 101, Cl 53, F 27, S 26, Br 15, I 8, P 5. **No silicon, boron or selenium compound is in the set.**
- Value on the corpus file (`bosque2002_resolved.json`, sha256): `7d546903556444ce9adfde9d6fd01a8bd7f4a5fcd2d85d9eb4b5266717281bb3`.

## 2. Model and fit

- alpha(molecule) = sum over atoms of a_element, **no intercept** (an intercept breaks additivity: it gives a molecule with no atoms a polarizability). Hydrogens are counted explicitly.
- Fitted by **weighted least squares with weights 1/exp^2**, i.e. minimising the sum of squared RELATIVE errors, because the quantity reported and judged is a percentage error. Unweighted fits are reported
  beside it, not instead of it.
- **Fit on the 339 working-set rows; judged on the 86 prediction-set rows.** The values that ship are then the same model refitted on all 425 rows; that refit has no held-out set of its own and its
  quality is the working-set fit's held-out number.
- An element is **refitted** if at least 5 molecules in the working set contain it. The standard error of each value is reported; an element with fewer than 10 molecules (here iodine and phosphorus)
  is shipped with the word **"weakly determined"**.
- **Elements with no data (Si, B, Se) are not refitted.** Their current values have no source. They are kept and every result that uses one carries a warning saying the value is unsourced and
  unvalidated; they are not removed.

## 3. What is judged

Reported on the 86 prediction-set rows: mean absolute percentage error (MAPE), median, 90th percentile, largest, bias (mean signed percentage), and the same for **(a) the current table** (the thing being
replaced), **(b) Bosque and Sales' published coefficients** (Table 4, with its intercept; context only), and **(c)** Miller's ahp method as the application implements it, on the same molecules (context
only, if the application can type them).

**Acceptance (all required to replace the current table):**
1. The refit's prediction-set MAPE is **no worse than the current table's.**
2. No element's refit value is negative, and every value for H, C, N, O, F, Cl, Br, S is within a factor of 2 of the current one (a larger move is investigated before it ships, as it may be an
   identity error or a collinearity).
3. The fit is stable: refitting on a random 80% of the working set 200 times (seed fixed at 20261105) moves each element's value by less than 10% (standard deviation over mean) for every element
   with 10 or more molecules.

If criterion 1 fails the table is NOT replaced and this result is recorded; the current table then stays with its warning.

## 4. Rules for what may change after seeing results

- No row is removed or corrected after the fit except for an identity error found by reading the NAME of a row whose relative error exceeds 15% (a wrong structure is a data error, not a model
  failure). Every such change is listed, and the fit is shown with and without it.
- The criteria above do not move. A different element threshold or weighting, if tried, is reported as a sensitivity result and does not decide.

## 5. Known limits stated before the result

- Solvents are liquids at room temperature, polarizability derived at the sodium D line; the application has so far estimated gas-phase molecules. The difference is small for these molecules but is
  not zero.
- The prediction set is a random half-split of the same compilation, so its error is **optimistic** about unrelated chemistry (salts, large drug-like molecules, charged species, conjugated dyes).
  A second set, Kang and Jhon 1982's 94 compounds, is read afterwards as a **non-gating** secondary check if it can be parsed.
- Iodine and phosphorus are determined by 8 and 5 molecules.
