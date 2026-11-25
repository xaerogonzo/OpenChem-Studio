# Proton affinity held-out size arm: preregistration

Written 2026-11-24, **before any job of this arm was run**. The protocol, the proton terms, the site rule, the frequencies, the symmetry override and the mean-error bands are those of `PREREGISTRATION.md` (frozen 2026-10-19, primary arm PASS 2026-10-20). This file only names a new panel and the one reading change that a panel of six requires. Where this text and `heldout.py` / `judge.py` disagree, the disagreement is fixed before the run, never after. **Status: frozen on commit of this file with `freeze_heldout.json`.** This file changes only by an `## Amendment` section that says what and why.

The original 28 bases stay the measured scope of the calculator. This arm asks whether that measured error still holds for **larger** bases of the same chemistry. A PASS here is what would let the ten-heavy-atom warning be lifted for the families this panel covers. A PARTIAL or FAIL leaves the warning in place. The calculator is not edited in the same commit as a result.

## The question

Does the primary protocol (M062X/def2-TZVPD optimization and frequencies, thermochemistry from them, `run_pa.py`) give PA and GB of **neutral bases of 11 to 20 heavy atoms** against the NIST evaluated Hunter and Lias values at the same accuracy the original 28 were judged by?

The secondary DLPNO arm is not part of this freeze. Amino acids, metals, radicals, charged structures and bases larger than 20 heavy atoms are not part of this freeze.

## The data (fixed before any calculation)

`heldout_values.json`: six neutral bases, Hunter and Lias 1998 as the NIST WebBook lists them [source:hunter1998], kJ/mol at 298 K, fetched 2026-11-24 **after the names were chosen**. Errors are computed minus reference, in kcal/mol (1 kcal = 4.184 kJ).

The six names were chosen by chemistry, not by their values:

| name | formula | heavy atoms | why this family |
|---|---|---|---|
| guanine | C5H5N5O | 11 | nucleobase, beyond pyrimidine and imidazole |
| camphor | C10H16O | 11 | aliphatic ketone, beyond acetone |
| benzoquinuclidine | C11H13N | 12 | rigid tertiary amine (NIST page title: 2H-1,4-ethanoquinoline, 3,4-dihydro-) |
| acridine | C13H9N | 14 | extended pyridine |
| anthracene | C14H10 | 14 | extended π base, beyond benzene |
| phenanthrene | C14H10 | 14 | isomeric π base |

None of these names is in `nist_values.json`. Each SMILES is the PubChem record for the CAS on the NIST page. Guanine is the 7H-keto tautomer that CAS 73-40-5 points at (`2-amino-1,7-dihydropurin-6-one`); camphor is the racemate connectivity of CAS 76-22-2, without stereo.

**The deciding stratum is still the bases whose reference PA is above propene's (751.6 kJ/mol).** The six WebBook proton affinities as fetched are all above that line, so **all six decide** and the low stratum of this arm is empty. That classification is a property of the stored numbers, not a reason the names were picked.

## The protocol (everything here is the original primary arm)

ORCA 6.1.1. Every job: `! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq`, `%pal nprocs 4 end`, `%maxcore 3000`, charge and multiplicity 0/1 for a base and +1/1 for its conjugate acid. Structures, sites, frequencies, thermochemistry, symmetry override and selection are `run_pa.py` as hashed in `freeze_heldout.json`. The wrapper `run_pa_heldout.py` only swaps the panel and the output directory (`artifacts_heldout/`). It must not be used to change a keyword, a keep-window or a site rule.

A job has a 4-hour limit. A structure with a vibrational frequency below −20 cm⁻¹ is re-run once with `Calc_Hess` and dropped if it still has one. A report is refused (NOT EVALUABLE) for records from more than one commit or made with a dirty `src/`.

## The reading rule

`judge.py`, primary arm, **except** that more than **one** missing deciding base is NOT EVALUABLE (`heldout.MISSING_ALLOWED = 1`). The original arm allowed two of twenty-one; two of six would be a third of the panel.

For each of PA and GB, on the deciding stratum:

* **PASS**: MAE ≤ 2.5 kcal/mol, no error above 5.0, |MSE| ≤ 1.5.
* **PARTIAL**: not PASS and MAE ≤ 4.0.
* **FAIL**: otherwise.
* **NOT EVALUABLE**: more than one of the six has no computed value for that quantity, or a provenance problem.

PA and GB are judged apart. The empty low stratum is reported and cannot decide.

## What each verdict does (decided now)

* **PASS (PA):** the calculator may keep computing bases of 11 to 20 heavy atoms of H, C, N, O, P and S, and the size warning may be lifted for that range in a **later** commit that states the error found. This freeze does not edit `chem/proton_affinity.py`.
* **PASS (GB):** the same, for GB, independently of PA.
* **PARTIAL:** the failing cells are named; the size warning stays; whether a calculation with a stated larger error is wanted is a later decision.
* **FAIL:** the size warning stays; the report is the deliverable.
* **NOT EVALUABLE:** nothing is claimed; the cause is fixed and the arm re-run under a new preregistration or an Amendment.

A result outside the thresholds is never explained away by hand.

## What it cannot say

* **Six bases:** nothing about amino acids, metals, other elements, charged structures, or bases larger than 20 heavy atoms.
* **One tautomer of guanine:** the 9H form is a different molecule.
* **The reference is still uncertain by about 8 kJ/mol** for most entries.
* **Harmonic-oscillator thermochemistry, lowest structure not a Boltzmann average, rule-based sites.**

## How to run (after this freeze is committed; not part of freezing)

From the repository root, clean `src/`, nothing else using the cores:

```bash
uv run --no-sync python benchmarks/proton_affinity/run_pa_heldout.py structures
uv run --no-sync python benchmarks/proton_affinity/run_pa_heldout.py run --workers 3 --cores 4
uv run --no-sync python benchmarks/proton_affinity/run_pa_heldout.py report
```

`--workers 3 --cores 4` is the original configuration. Guanine enumerates eleven protonation sites under the existing rule; the π bases enumerate several inequivalent carbons. The wall time is unmeasured. Resume by running `run` again. Do not start a job of this arm while another long ORCA batch is using the machine.
