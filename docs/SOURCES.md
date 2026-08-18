<!-- GENERATED FROM docs/sources.toml -- do not edit -->
<!-- SOURCE SHA256: 4eea1cd40270e6d4643c5af9b430629420343d4d4e3045b095dce5773d494461 -->

# Sources

Every primary source, dataset, legal text, standard and bundled library this
project rests on, with what uses it and how far it has been checked.

## What this registry is, and the three things it cannot do

It is a **provenance registry**, not a bibliography page. Each entry declares
its kind, whether it is shipped, how far it is verified, and what points at
it, so that `tests/test_sources_are_current.py` can ask real questions.

1. **It does not verify scientific claims.** The guards cannot catch a
   citation pointing at the wrong paper, a wrong table or page number, a
   changed URL, a superseded source, or a source that no longer supports the
   claim resting on it.
2. **It does not prove licence compatibility.** The licence guard proves a
   file is classified, a licence file exists, and the relationship is
   declared. It says nothing about whether that text is correct, current, or
   actually covers that artifact.
3. **Its initial completeness is not mechanically proven.** The guards
   establish consistency *after* the registry was populated. That every
   source was found rests on the reconstruction sweep that built it, not on
   anything a test can re-run.

## How to read the columns

**Verification** is three-valued on purpose. A citation can be right while
the number derived from it is wrong -- this project has shipped a fixture
labelled "verbatim from a real run" whose energies were typed from memory.

| value | means |
| --- | --- |
| `unverified` | nobody has checked this entry against the source itself |
| `citation` | the reference is right |
| `citation + claim` | the **number this project uses** was checked against the source |

**Used by** is descriptive, not the dependency oracle: a stale entry there is
tolerated by design. The operational fields -- `resource_path`,
`package_manifest`, `license_files`, `third_party_globs` -- are the
authoritative ones, and every one of them is checked.

**Local** names a file in the maintainer's own paper archive. It is recorded
so a later session can verify a citation without hunting, and it is **never
checked by any guard**, because that folder is not in the repository.

## Citing a source from prose

Write `[source:key]`, never a bare backtick -- these documents contain
thousands of backticked identifiers, so a guard reading every one as a source
key would need an enormous allowlist, or would teach the prose to look like
the test. The syntax is validated before it is resolved, so a malformed
reference fails rather than being silently skipped.

## Adding to it, or raising an entry's verification

Everything is edited in `docs/sources.toml`. **Never edit this file** -- it is
generated and will be overwritten.

| what you established | field to set |
| --- | --- |
| the reference is right | `verification = "citation"` + `verified_date` |
| the **number this project uses** is right | `verification = "citation_and_claim"` + `verified_date` |
| a DOI | `identifier_type = "doi"`, `identifier` |
| a title you actually read | fold it into `citation` |
| a licence read from the artifact | `license` |
| a resolved version | `version` + `package_manifest` |
| you now hold a copy | `local` (declared only, never checked) |

Then regenerate and check:

```
uv run --no-sync python tools/build_sources_doc.py
uv run --no-sync python -m pytest -q tests/test_sources_are_current.py tests/test_docs_are_current.py
```

A `verified_date` on an `unverified` row fails the schema guard, and so does
the reverse -- the pair is enforced, so a check cannot be half-recorded. And
if a shipped data file is GENERATED, put its `_source_key` in the generator:
hand-added metadata in `lewis_parameters.json` was silently dropped by the
next run of `tools/build_lewis_parameters.py`.

## Index

| key | kind | status | verification |
| --- | --- | --- | --- |
| [`abraham_predicted_solvents`](#abraham_predicted_solvents) | reference_table | **not shipped** | citation + claim |
| [`adoptium_temurin`](#adoptium_temurin) | software | shipped | citation |
| [`allred1961`](#allred1961) | reference_table | shipped | citation |
| [`aqsoldb`](#aqsoldb) | dataset | shipped | citation |
| [`autodock_vina`](#autodock_vina) | software | shipped | citation |
| [`avdeef2007`](#avdeef2007) | literature | shipped | citation + claim |
| [`avdeef2020`](#avdeef2020) | literature | shipped | citation + claim |
| [`bolovinos1984`](#bolovinos1984) | literature | shipped | citation + claim |
| [`bradley2014`](#bradley2014) | dataset | shipped | citation + claim |
| [`bradley2015`](#bradley2015) | literature | shipped | citation + claim |
| [`bravetti2023`](#bravetti2023) | literature | shipped | citation |
| [`cod`](#cod) | dataset | shipped | citation |
| [`crc_handbook`](#crc_handbook) | reference_table | shipped | citation + claim |
| [`cwc_annex_on_chemicals`](#cwc_annex_on_chemicals) | legal | shipped | citation + claim |
| [`dea_listed_chemicals`](#dea_listed_chemicals) | legal | shipped | citation |
| [`delaney2004`](#delaney2004) | literature | shipped | citation + claim |
| [`dimorphite_dl`](#dimorphite_dl) | software | shipped | citation |
| [`drago1965`](#drago1965) | literature | shipped | citation + claim |
| [`drago1990`](#drago1990) | literature | shipped | citation |
| [`drago1993`](#drago1993) | literature | shipped | citation |
| [`glasser1995`](#glasser1995) | literature | shipped | citation |
| [`gutmann_frontiers2022`](#gutmann_frontiers2022) | literature | **not shipped** | citation |
| [`hlb`](#hlb) | reference_table | **not shipped** | unverified |
| [`hopfinger2009`](#hopfinger2009) | dataset | shipped | citation |
| [`ich_m9`](#ich_m9) | standard | shipped | citation + claim |
| [`iupac2013`](#iupac2013) | standard | shipped | citation |
| [`iupac_namer`](#iupac_namer) | software | shipped | citation |
| [`jenkins1999`](#jenkins1999) | literature | shipped | citation + claim |
| [`kaya2022`](#kaya2022) | literature | shipped | citation + claim |
| [`kendall2008`](#kendall2008) | literature | shipped | citation |
| [`ketcher`](#ketcher) | software | shipped | citation |
| [`kwon2023`](#kwon2023) | dataset | shipped | citation + claim |
| [`llinas2008`](#llinas2008) | dataset | shipped | citation |
| [`llinas2019`](#llinas2019) | dataset | reference only | citation |
| [`llinas2020`](#llinas2020) | dataset | shipped | citation + claim |
| [`lorentzon1995`](#lorentzon1995) | literature | reference only | citation + claim |
| [`mayo1990`](#mayo1990) | literature | shipped | citation + claim |
| [`miller_polarizability`](#miller_polarizability) | reference_table | **not shipped** | unverified |
| [`molstar`](#molstar) | software | shipped | citation |
| [`moreland1974`](#moreland1974) | literature | shipped | citation |
| [`nmrshiftdb2`](#nmrshiftdb2) | dataset | shipped | citation |
| [`nubase2020`](#nubase2020) | dataset | shipped | citation + claim |
| [`ons_solubility`](#ons_solubility) | dataset | shipped | citation |
| [`openbabel`](#openbabel) | software | shipped | citation |
| [`opsin`](#opsin) | software | shipped | citation |
| [`orca`](#orca) | software | shipped | citation |
| [`parr_pearson1983`](#parr_pearson1983) | literature | shipped | citation |
| [`pearson1988`](#pearson1988) | literature | shipped | citation + claim |
| [`pkasolver`](#pkasolver) | software | shipped | citation |
| [`platts1999`](#platts1999) | literature | **not shipped** | citation + claim |
| [`pyside6`](#pyside6) | software | shipped | citation |
| [`ran2002`](#ran2002) | literature | reference only | citation |
| [`rcsb_pdb`](#rcsb_pdb) | dataset | shipped | citation |
| [`rdkit`](#rdkit) | software | shipped | citation |
| [`sci_downloads_note`](#sci_downloads_note) | reference_table | reference only | citation |
| [`shannon1976`](#shannon1976) | literature | shipped | citation + claim |
| [`tdc_admet`](#tdc_admet) | dataset | reference only | citation |
| [`threedmol`](#threedmol) | software | shipped | citation |
| [`trott_olson2010`](#trott_olson2010) | literature | shipped | citation + claim |
| [`tsei`](#tsei) | reference_table | **not shipped** | unverified |
| [`vogel_drago1996`](#vogel_drago1996) | literature | shipped | citation + claim |
| [`yalkowsky_banerjee1992`](#yalkowsky_banerjee1992) | dataset | shipped | citation |

## Primary literature

### mayo1990

<a id="mayo1990"></a>

> S. L. Mayo, B. D. Olafson & W. A. Goddard III, 'DREIDING: A Generic Force Field for Molecular Simulations', J. Phys. Chem. 1990, 94, 8897-8909.

| | |
| --- | --- |
| Identifier | J. Phys. Chem. 1990, 94, 8897-8909 |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `mayo1990.pdf` (not checked) |
| Used by | `src/openchem/chem/dreiding/parameters.py`, `src/openchem/chem/dreiding/energy.py`, `src/openchem/chem/dreiding/typer.py`, `docs/DREIDING_ASSESSMENT.md` |

Read from the PDF with pymupdf; all eight published torsion barriers are
reproduced, which is what `tests/test_dreiding_barriers.py` asserts. The
PDF's text layer corrupts the atom-type labels the parameters key on
(`C_3`, `C_R`), so those were read from the rendered page.

This project asserted for months that DREIDING was simply unavailable.
That was the absence of a finding rather than one -- see
[source:sci_downloads_note].

### shannon1976

<a id="shannon1976"></a>

> R. D. Shannon, 'Revised effective ionic radii and systematic studies of interatomic distances in halides and chalcogenides', Acta Cryst. 1976, A32, 751-767, Table 1.

| | |
| --- | --- |
| Identifier | Acta Cryst. 1976, A32, 751-767 |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `shannon1976.pdf` (not checked) |
| Used by | `src/openchem/chem/data/ionic_radii.json`, `src/openchem/chem/lattice_energy.py` |

The shipped column is `IR` (effective ionic radius), NOT the adjacent `CR`
(crystal radius). The two differ by 0.14 A and the SIGN of that offset
flips between cations and anions, so reading the wrong column is not a
constant error and a spot-check cannot catch the transposition. Every
entry is six-coordinate, which is a requirement of Kapustinskii's equation
rather than a simplification of the table.

The PDF's text layer is OCR and mangles the ion labels (`AC?3`, `AG?I`),
so values were read from a rendered image and cross-checked.

### drago1965

<a id="drago1965"></a>

> R. S. Drago & B. B. Wayland, 'A Double-Scale Equation for Correlating Enthalpies of Lewis Acid-Base Interactions', J. Am. Chem. Soc. 1965, 87, 3571.

| | |
| --- | --- |
| Identifier | [10.1021/ja01094a008](https://doi.org/10.1021/ja01094a008) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `Drago & Wayland EC 1965.pdf` (not checked) |
| Used by | `src/openchem/chem/lewis_adduct.py`, `src/openchem/chem/data/lewis_parameters.json`, `tools/build_lewis_parameters.py` |

The ORIGINAL MODEL, and NOT the source of the shipped numbers -- see
[source:vogel_drago1996]. Its parameters are on a different scale, and that
is now READ FROM THE PAPER rather than taken from this project's notes: it
says "E A = 1.00 and CA = 1.00. Iodine was selected because", where the
shipped table has iodine at E = 0.50, C = 2.0. That sentence is what
`test_lewis_parameters_match_the_declared_parameter_scale` ultimately rests
on. Title, authors and pages 3571-3577 all confirmed; note the PDF's first
page is the tail of the PRECEDING article, so a check that reads only page
one concludes the file is the wrong paper. Mixing the two silently is a real hazard, which
is why `lewis_parameters.json` declares `parameter_scale` and a guard
derives it from the iodine entry rather than trusting the label.

Its observed enthalpies ARE scale-free and are used as a second,
independent validation set (12 values across three acid series). The
F-strain measurements in it are the model's best test because they are one
it must FAIL: an E/C equation has no steric term, so it necessarily
over-predicts trimethylborane's adducts with the two bulkiest amines.

### vogel_drago1996

<a id="vogel_drago1996"></a>

> G. C. Vogel & R. S. Drago, 'The ECW Model', J. Chem. Educ. 1996, 73(8), 701-707, Table 1.

| | |
| --- | --- |
| Identifier | J. Chem. Educ. 1996, 73, 701 |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-17 |
| Local copy | `vogel1996.pdf` (not checked) |
| Used by | `src/openchem/chem/data/lewis_parameters.json`, `tools/build_lewis_parameters.py` |

CLOSED, AND IT FOUND A DEFECT. This was the weakest link in the project:
`lewis_parameters.json` said its numbers came "via the Wikipedia ECW model
compilation of Vogel & Drago", so the chain ran Wikipedia -> this repo ->
here with no step touching the paper.

The paper is now read. **Every shipped parameter was checked against Table
1, and 52 of 53 matched exactly.** The one that did not was methylamine's
C_B, shipped as 3.13 where the table prints 3.12 -- a transcription slip
inherited from the compilation, fixed in `tools/build_lewis_parameters.py`.
It does not move the validation, which stays at 0.272 kcal/mol over the
eight iodine adducts.

The scan has NO TEXT LAYER (7 pages, one image each), so this was read from
a 520-dpi render -- the same route `shannon1976` needed, and the reason a
text-extraction check would have reported the file as empty rather than as
unreadable.

Iodine reads E_A = 0.50, C_A = 2.00, which is what
`_parameter_scale = "modern_ecw"` asserts and what
`test_lewis_parameters_match_the_declared_parameter_scale` derives. That was
previously inferred from [source:drago1965] stating the OTHER scale; it is
now confirmed from the paper that states ours.

**The paper's own footnote 1 is the argument for that guard existing**: its
parameters "should not be mixed with those parameters found in the
literature prior to 1991". Equation 1 also confirms the sign this project
once had wrong -- `-dH = E_A E_B + C_A C_B + W`, with W ADDED.

### drago1993

<a id="drago1993"></a>

> R. S. Drago, A. P. Dadmun & G. C. Vogel, 'Addition of new donors to the E and C model', Inorg. Chem. 1993, 32, 2473-2479.

| | |
| --- | --- |
| Identifier | [10.1021/ic00063a045](https://doi.org/10.1021/ic00063a045) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `drago1993.pdf` (not checked) |
| Used by | `src/openchem/chem/data/lewis_parameters.json`, `tools/build_lewis_parameters.py` |

CONFIRMED FROM THE PAPER ITSELF, whose header reads "Inorg. Chem. 1993, 32,
2473-2479 ... Addition of New Donors to the E and C Model ... Russell S.
Drago, Department of Chemistry, University of Florida ... Andrew P. Dadmun
and Glenn C. Vogel, Department of Chemistry, Ithaca College".

THIS ENTRY WAS UNFINDABLE UNTIL IT WAS CHECKED, AND THE KEY USED TO SAY
1992. **Inorganic Chemistry volume 32 is 1993** -- volume 31 is 1992 -- so
"Inorg. Chem. 1992, 32, 2473" is internally impossible and resolves to
nothing in any index. Searching for it failed exactly as it had to.

The real reference came from the Literature Cited of [source:vogel_drago1996]
(entry 8) and was then confirmed against CrossRef, which also supplied the
title and corrected the author spelling from "Dadman" to **Dadmun**.

The title says what it contributes: it ADDS donors to the model, which is
why it is a supplementary source for the shipped table rather than the
source of it.

**A citation can be wrong in a way that makes it unresolvable rather than
merely imprecise**, and an internally inconsistent volume/year pair is the
cheapest kind to detect -- had anyone checked that volume 32 is 1993.

### drago1990

<a id="drago1990"></a>

> R. S. Drago, D. C. Ferris & N. Wong, 'A method for the analysis and prediction of gas-phase ion-molecule enthalpies', J. Am. Chem. Soc. 1990, 112, 8953-8961.

| | |
| --- | --- |
| Identifier | [10.1021/ja00180a047](https://doi.org/10.1021/ja00180a047) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `drago1990.pdf` (not checked) |
| Used by | `src/openchem/chem/data/lewis_parameters.json`, `tools/build_lewis_parameters.py` |

Confirmed from the paper's own header: "J. Am. Chem. Soc. 1990, 112,
8953-8961 ... A Method for the Analysis and Prediction of Gas-Phase
Ion-Molecule Enthalpies ... Russell S. Drago, Donald C. Ferris, and Ngai
Wong ... University of Florida".

**WHERE THE SHIPPED IODINE SCALE COMES FROM, named at last.** Reference 6b
of [source:vogel_drago1996] states that the E and C values were transformed
to eliminate negative numbers in this paper, and that "in the process E_A
and C_A values of I2 were changed from 1 and 1 to 0.5 and 2, respectively.
One must not mix parameters from earlier fits with the transformed
parameters used since 1990."

That sentence is the whole justification for `_parameter_scale` and for
`test_lewis_parameters_match_the_declared_parameter_scale`. Until it was
read, the scale distinction rested on [source:drago1965] stating the OTHER
convention -- which establishes that two scales exist but not which paper
created ours, nor that mixing them is explicitly forbidden by the authors.

Registered although nothing in the repository cites it by name: it is the
provenance of a number every Drago adduct calculation uses.

### parr_pearson1983

<a id="parr_pearson1983"></a>

> R. G. Parr & R. G. Pearson, 'Absolute Hardness: Companion Parameter to Absolute Electronegativity', J. Am. Chem. Soc. 1983, 105, 7512.

| | |
| --- | --- |
| Identifier | J. Am. Chem. Soc. 1983, 105, 7512 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Local copy | `Parr & Pearson absolute hardness 1983.pdf` (not checked) |
| Used by | `src/openchem/chem/conceptual_dft.py` |

### pearson1988

<a id="pearson1988"></a>

> R. G. Pearson, 'Absolute Electronegativity and Hardness: Application to Inorganic Chemistry', Inorg. Chem. 1988, 27, 734, Table II.

| | |
| --- | --- |
| Identifier | [10.1021/ic00277a030](https://doi.org/10.1021/ic00277a030) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `Pearson, hardness in inorganic chemistry 1988.pdf` (not checked) |
| Used by | `src/openchem/chem/conceptual_dft.py`, `tests/test_conceptual_dft.py` |

Table II ('Experimental Parameters for Molecules, eV') is READ FROM THE
PAPER and asserted in `tests/test_conceptual_dft.py`, so the accuracy
claims resting on it are checked rather than described. Its rows round to
+-0.1 -- H2S's (I-A)/2 gives 6.3 against a printed eta of 6.2 -- so a
transcription self-check needs a tolerance of 0.15, not 0.05.

### avdeef2007

<a id="avdeef2007"></a>

> A. Avdeef, 'Solubility of sparingly-soluble ionizable drugs', Adv. Drug Deliv. Rev. 2007, 59, 568-590.

| | |
| --- | --- |
| Identifier | [10.1016/j.addr.2007.05.008](https://doi.org/10.1016/j.addr.2007.05.008) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `avdeef2007.pdf` (not checked) |
| Used by | `src/openchem/chem/solubility.py`, `src/openchem/chem/logd.py`, `docs/SCIENTIFIC_LIMITATIONS.md` |

Two separate things come from this paper and both were checked against it.

Section 2.2's 'sdiff 3-4' approximation bounds the pH adjustment: in
0.15 M NaCl the counter-ion salt precipitates once solubility exceeds
intrinsic by about four orders for a weak acid and three for a weak base.
Asymmetric on purpose. The reading was verified against the paper's own
worked example -- amiodarone, intrinsic 7.9e-9 M and Ksp 1.2e-6 M^2 --
where 7.9e-9 x 10^3 x 0.15 = 1.19e-6 reproduces the printed Ksp. That is
what says the rule was understood rather than merely quoted.

Table 1 is the ionization arithmetic, and reading it corrected a bug this
codebase had carried for years: ionization sites MULTIPLY,
sum(log10(1 + term)), not log10(1 + sum of terms). Monoprotic answers are
identical under both, which is why it survived so long.

### avdeef2020

<a id="avdeef2020"></a>

> A. Avdeef, 'Prediction of aqueous intrinsic solubility of druglike molecules using Random Forest regression trained with Wiki-pS0 database', ADMET & DMPK 8(1) (2020) 29-77.

| | |
| --- | --- |
| Identifier | [10.5599/admet.766](https://doi.org/10.5599/admet.766) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `avdeef2020.pdf` (not checked) |
| Used by | `benchmarks/solubility/extract_avdeef_sets.py`, `benchmarks/solubility/base_bias.py` |

Five appendix tables, of which only A1 and A2 are independent data. A3 and
A4 ARE the Solubility Challenge 2 sets under other names
([source:llinas2020]) and A5 likewise -- so a bulk extractor over those
pages would double-count data the project already had and INFLATE the power
of the experiment it was meant to strengthen. A naive row count over pages
35-44 gives 172 compounds; the honest independent gain is 49.
`extract_avdeef_sets.py` refuses A3/A4/A5 by name and says why.

THIS ENTRY CARRIED THE WRONG TITLE UNTIL IT WAS CHECKED, and was marked
verified while it did -- the worst combination, and the reason the
verification pass audited entries that already claimed to be checked rather
than only the unverified ones. The title recorded here was
"Multi-lab intrinsic solubility measurement reproducibility in CheqSol and
shake-flask methods", which is a DIFFERENT Avdeef paper: ADMET & DMPK 2019,
7, 210-219, reference (5) of [source:llinas2020]. The volume, pages and DOI
were right throughout, because those came from the repository rather than
from memory. Its abstract's "6355 entries ... for 3014 different molecules"
matches what `benchmarks/solubility/README.md` says about Wiki-pS0.

### bradley2015

<a id="bradley2015"></a>

> J-C. Bradley, M. H. Abraham, W. E. Acree Jr & A. S. I. D. Lang, 'Predicting Abraham model solvent coefficients', Chemistry Central Journal / BMC Chemistry 2015;9:12, Table 1.

| | |
| --- | --- |
| Identifier | [10.1186/s13065-015-0085-4](https://doi.org/10.1186/s13065-015-0085-4) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Licence | CC BY 4.0 |
| Used by | `src/openchem/chem/data/abraham_solvents.json`, `src/openchem/chem/abraham.py`, `tools/build_abraham_tables.py` |

ONLY THE 91 MEASURED SOLVENTS SHIP. The paper also predicts coefficients
for the rest and says of those they should not be taken 'as gospel' -- see
[source:abraham_predicted_solvents], which is refused with that reason.

The paper considers 293 solvents in TOTAL (sustainable, classic and
measured), of which 91 are measured, so 202 are predicted-only and the
article tabulates 118 of them. '293 further solvents' appeared in four
documents here and was wrong in all four: it was written from memory of the
abstract rather than from the sentence.

### delaney2004

<a id="delaney2004"></a>

> J. S. Delaney, 'ESOL: Estimating Aqueous Solubility Directly from Molecular Structure', J. Chem. Inf. Comput. Sci. 2004, 44, 1000-1005.

| | |
| --- | --- |
| Identifier | [10.1021/ci034243x](https://doi.org/10.1021/ci034243x) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `delaney2004.pdf` (not checked) |
| Used by | `src/openchem/chem/solubility.py`, `benchmarks/solubility/score.py`, `benchmarks/solubility/fetch.py` |

VERIFIED AGAINST THE PDF, which also supplied the DOI this entry lacked
while it was reconstructed from how the repo refers to it. The paper's own
running header reads "J. Chem. Inf. Comput. Sci., Vol. 44, No. 3, 2004" and
it self-cites as 44, 1000-1005 with doi 10.1021/ci034243x.

THE LOAD-BEARING CLAIM HOLDS EXACTLY, counted over the full text: the words
ionization, ionisation, amine, salt and pKa occur **zero** times, and so
does "pH". That is why ESOL cannot tell a base from a neutral of the same
size and lipophilicity, and why the base bias measured against it is a
domain limit rather than a fixable defect.

Its fitting set is `dataset-G` inside AqSolDB ([source:aqsoldb]), which is
what makes the de-leaking in `benchmarks/solubility/` necessary.

### jenkins1999

<a id="jenkins1999"></a>

> H. D. B. Jenkins, H. K. Roobottom, J. Passmore & L. Glasser, 'Relationships among Ionic Lattice Energies, Molecular (Formula Unit) Volumes, and Thermochemical Radii', Inorg. Chem. 1999, 38, 3609.

| | |
| --- | --- |
| Identifier | Inorg. Chem. 1999, 38, 3609 |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `jenkins1999.pdf` (not checked) |
| Used by | `src/openchem/chem/lattice_energy.py` |

The volume-based correlation `U = 2I(alpha/V^(1/3) + beta)`, which needs
only the formula-unit volume and so answers for polyatomic ions that
Kapustinskii refuses by name. Validated over Tables 2 and 3 taking the CRC
Handbook column as the target ([source:crc_handbook]) and the
crystallographic volume as the input, so neither side is the paper's own
estimate: 26 salts, mean deviation 3.3%, worst 7.7%.

The MX2 and M2X coefficient sets CROSS near V^(1/3) = 0.34, so a test point
chosen there proves nothing -- pick from where the data lives.

### bolovinos1984

<a id="bolovinos1984"></a>

> A. Bolovinos, P. Tsekeris, J. Philis, E. Pantos & G. Andritsopoulos, 'Absolute vacuum ultraviolet absorption spectra of some gaseous azabenzenes', J. Mol. Spectrosc. 1984, 103, 240-256, Tables I and III.

| | |
| --- | --- |
| Identifier | [10.1016/0022-2852(84)90051-1](https://doi.org/10.1016/0022-2852(84)90051-1) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `bolovinos1984.pdf` (not checked) |
| Used by | `benchmarks/uvvis/reference.json`, `benchmarks/uvvis/README.md` |

Direct absolute measurements, used as the UV-Vis reference where they exist.

### lorentzon1995

<a id="lorentzon1995"></a>

> J. Lorentzon, P-A. Malmqvist, M. Fulscher & B. O. Roos, 'A CASPT2 study of the valence and lowest Rydberg electronic states of benzene and phenol', Theor. Chim. Acta 1995, 91, 91-108.

| | |
| --- | --- |
| Identifier | [10.1007/BF01113865](https://doi.org/10.1007/BF01113865) |
| Status | reference only |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `lorentzon1995.pdf` (not checked) |
| Used by | `benchmarks/uvvis/README.md` |

**Why it is reference only.** Consulted for a benzene oscillator strength and found NOT to contain the
value that had been attributed to it, so nothing from it is scored.

A NEAR MISS WORTH KEEPING. A value of 1.25 was about to be written into the
UV-Vis reference citing this paper; the string does not occur anywhere in
it. What it says is that experimental values are 'scattered in the range
0.6-1.05', that its own graphical integration gives 0.80, and that the 0.80
includes the A2u Rydberg band.

Refusing to write 1.25 in is the only reason this did not become a wrong
number with a citation attached -- which is worse than an unsourced one,
because it stops looking like a question. The benzene entry in
`benchmarks/uvvis/reference.json` is marked `unsourced` instead, and
`tests/test_docs_are_current.py` has a predicate that fails if that ever
silently changes.

### moreland1974

<a id="moreland1974"></a>

> C. G. Moreland, A. Philip & F. I. Carroll, '13C Nuclear Magnetic Resonance Spectra of Cinchona Alkaloids', J. Org. Chem. 1974, 39, 2413.

| | |
| --- | --- |
| Identifier | [10.1021/jo00930a020](https://doi.org/10.1021/jo00930a020) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Local copy | `moreland1974.pdf` (not checked) |
| Used by | `src/openchem/chem/nmr_hybrid.py`, `benchmarks/nmr/literature_shifts.py` |

The assigned CDCl3 quinine table, which is the stress case for the NMR hybrid predictor.

### kendall2008

<a id="kendall2008"></a>

> J. Kendall, R. McDonald, M. J. Ferguson & R. R. Tykwinski, Org. Lett. 2008, 10, 2163.

| | |
| --- | --- |
| Identifier | [10.1021/ol800583r](https://doi.org/10.1021/ol800583r) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `tests/test_crystal.py`, `tests/fixtures/cif/1504676.cif` |

The publication behind COD 1504676, one of the six CIF fixtures. See [source:cod].

### bravetti2023

<a id="bravetti2023"></a>

> F. Bravetti, L. Tapmeyer, K. Skorodumov, E. Alig, S. Habermehl, R. Huhn, S. Bordignon, A. Gallo, C. Nervi, M. R. Chierotti & M. U. Schmidt, 'Leucopterin, the white pigment in butterfly wings: structural analysis by PDF fit, FIDEL fit, Rietveld refinement, solid-state NMR and DFT-D', IUCrJ 2023, 10, 448-463.

| | |
| --- | --- |
| Identifier | [10.1107/S2052252523004281](https://doi.org/10.1107/S2052252523004281) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `tests/fixtures/cif/1569411.cif`, `tests/fixtures/cif/SOURCES.md` |

A REQUIRED ATTRIBUTION, not merely a courtesy. Unlike the other five CIF
fixtures, COD 1569411's header states that the original data were provided
by IUCr Journals and that the file 'may be used within the scientific
community so long as proper attribution is given to the journal article
from which the data were obtained'. That article is this one.

It is registered here deliberately: the DOI sweep excludes
`tests/fixtures/cif/*.cif`, because those DOIs belong to the depositors
rather than to us, and this is the one that carries an obligation anyway.

### kaya2022

<a id="kaya2022"></a>

> S. Kaya, A. Robles-Navarro, E. Mejia, T. Gomez & C. Cardenas, 'On the Prediction of Lattice Energy with the Fukui Potential: Some Supports on Hardness Maximization in Inorganic Solids', J. Phys. Chem. A 2022, 126, 4507-4516, Table 3.

| | |
| --- | --- |
| Identifier | [10.1021/acs.jpca.1c09898](https://doi.org/10.1021/acs.jpca.1c09898) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-17 |
| Local copy | `kaya2022.pdf` (not checked) |
| Used by | `tests/test_lattice_energy.py`, `docs/SCIENTIFIC_LIMITATIONS.md` |

Table 3's "Exp U" column is the target every Kapustinskii estimate in this
project is scored against. **Verified value by value: 35 of the 36 shipped
salts were located in the paper and all 35 match exactly.**

FOUND BY BEING WRONG ABOUT IT TWICE. `kaya2022.pdf` was first assumed to be
[source:gutmann_frontiers2022] because the filename matched that DOI's year;
on discovering it was not, it was written off as unrelated -- when it is in
fact cited by `tests/test_lattice_energy.py` and by
`docs/SCIENTIFIC_LIMITATIONS.md`. A file can be the wrong answer to one
question and the right answer to another.

**AND THE AUTHOR-YEAR SWEEP COULD NOT HAVE CAUGHT IT.** That check (in
CLAUDE.md, under the sources section) greps a fixed alternation of surnames,
and "Kaya" was not in it -- so it finds only sources whose authors somebody
already thought of. That is the real limit of the non-DOI half of the
coverage story, and the reason this entry exists is that the CRC Handbook's
provenance was being chased for an unrelated reason.

### ran2002

<a id="ran2002"></a>

> Y. Ran, Y. He, G. Yang, J. L. H. Johnson & S. H. Yalkowsky, 'Estimation of aqueous solubility of organic compounds by using the general solubility equation', Chemosphere 48 (2002) 487-509.

| | |
| --- | --- |
| Identifier | [10.1016/S0045-6535(02)00118-2](https://doi.org/10.1016/S0045-6535(02)00118-2) |
| Status | reference only |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `ran2002.pdf` (not checked) |
| Used by | `docs/VALIDATION.md`, `benchmarks/solubility/score.py` |

**Why it is reference only.** Nothing here implements the General Solubility Equation. It is registered
because `docs/VALIDATION.md` PUBLISHES a "GSE (published baseline)" row and
`benchmarks/solubility/score.py` reports against it, so a reader is owed a
way to find out what the GSE is. The numbers themselves come from
[source:llinas2020]'s own GSE column, not from this paper.

**THIS PAPER EVALUATES THE GSE, IT DOES NOT DEFINE IT**, and the
distinction is the paper's own: its abstract says "the general solubility
equation (GSE) proposed by Jain and Yalkowsky was used to estimate aqueous
solubility of ...". So citing it as the origin of the GSE would be one
attribution too far -- it is a large-scale test of the method by a group
including Yalkowsky.

The DOI is DERIVED from the PII printed in the paper (S0045-6535(02)00118-2)
via Elsevier's deterministic mapping, rather than read off the page; the
journal, volume, pages and year are read directly.

Note the GSE needs a MEASURED MELTING POINT, which this project does not
have and cannot supply -- which is why the baseline is reported rather than
reproduced.

### trott_olson2010

<a id="trott_olson2010"></a>

> O. Trott & A. J. Olson, 'AutoDock Vina: Improving the Speed and Accuracy of Docking with a New Scoring Function, Efficient Optimization, and Multithreading', J. Comput. Chem. 2010, 31(2), 455-461.

| | |
| --- | --- |
| Identifier | [10.1002/jcc.21334](https://doi.org/10.1002/jcc.21334) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-17 |
| Used by | `src/openchem/ui/panels/docking_panel.py`, `docs/USER_GUIDE.md` |

**THE SCORING-FUNCTION ERROR THE POSE TABLE'S TOOLTIP QUOTES.** Read from
the open-access copy at PMC3041641 (NIH-funded, so no paywall), Results
and Discussion, verbatim:

    "Vina achieves a comparatively low standard error of 2.85 kcal/mol"

It is the standard error of PREDICTED AGAINST EXPERIMENTAL free energies
of binding -- Figure 7 plots exactly that -- over the paper's own
190-complex set, using the predicted bound conformations. The same
paragraph gives 2.75 kcal/mol for the 116 complexes not in PDBbind.

**IT IS THE AUTHORS' FIGURE FOR THEIR SET AND THEIR PROTOCOL, not a
universal error bar**, which is why the tooltip attributes it rather than
stating it flatly. Vina's own accuracy on this project's redocking set is
a different measurement and is recorded in `chem/binding_site.py`.

**THIS ENTRY EXISTS BECAUSE THE NUMBER WAS NEARLY SHIPPED FROM MEMORY.**
It was written into a draft tooltip with no source, spotted, and removed
on the grounds that no `2.85` anywhere in this tree was a docking figure
(every one is NMR ppm or unrelated) and `[source:autodock_vina]` recorded
no error. Checking afterwards showed the remembered number was RIGHT --
which is the point rather than a reprieve: it was unverifiable at the time
and a tooltip is exactly where an unsourced figure acquires false
authority. Being correct by luck is not a method. See
[source:sci_downloads_note] for the same lesson from the other direction.

`[source:autodock_vina]` is the software; this is the paper that carries
the claim.

### glasser1995

<a id="glasser1995"></a>

> L. Glasser, 'Lattice Energies of Crystals with Multiple Ions: A Generalized Kapustinskii Equation', Inorg. Chem. 1995, 34, 4935-4936.

| | |
| --- | --- |
| Identifier | Inorg. Chem. 1995, 34, 4935-4936 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Local copy | `glasser1995.pdf` (not checked) |
| Used by | `src/openchem/chem/lattice_energy.py`, `CLAUDE.md` |

Where the identity `2I = sum(n_k z_k^2)` equals Kapustinskii's
`nu |z+ z-|` is noted, which is what makes the volume-based route
([source:jenkins1999]) strictly backward compatible with the existing
36-salt Kapustinskii validation. This project verified the identity itself
over 1:1, 1:2, 2:1 and 2:3 rather than taking it on the paper's word, so the
claim resting on this citation is ours; the citation is the attribution.

MISSED BY THE ORIGINAL SWEEP because it carries no DOI and is named only in
prose. See [source:hopfinger2009] and [source:yalkowsky_banerjee1992], found
the same way.

### platts1999

<a id="platts1999"></a>

> J. A. Platts, D. Butina, M. H. Abraham & A. Hersey, 'Estimation of molecular linear free energy relation descriptors using a group contribution approach', J. Chem. Inf. Comput. Sci. 1999, 39, 835-845.

| | |
| --- | --- |
| Identifier | [10.1021/ci980339t](https://doi.org/10.1021/ci980339t) |
| Status | **not shipped** |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `platts1999.pdf` (not checked) |
| Used by | `docs/SOLVENT_SOLUBILITY_ASSESSMENT.md`, `docs/VALIDATION.md` |

**Why it is not shipped.** It would work -- Table 2 gives all 81 fragment definitions, Table 4 their
coefficients, Table 5 a separate 51-fragment set for H-bond acidity -- and
it is roughly 480 coefficients and 132 hand-written SMARTS patterns, every
one a place for a silent error, carrying 0.7-1.0 log of its own error.
Fragments 59-67 are defined in a FIGURE rather than in text, so they cannot
be read from the PDF's text layer at all.

Looking the descriptors up instead ([source:bradley2014]) costs neither,
and that is what shipped.

Kept because THIS PROJECT'S REASONS FOR DEFERRING NON-AQUEOUS SOLUBILITY
WERE THREE, AND TWO WERE FALSE. 'E is derivable from Crippen molar
refractivity' -- measured and killed, hexane's Crippen-derived value is
0.805 against a defined E of 0.000. 'Ethanol is structurally unreachable
because it is miscible with water' -- false, Abraham's coefficients come
from solubility ratios, so neat ethanol is in the measured table. Only this
one was real. A deferral's reasons rot independently of its verdict.

### gutmann_frontiers2022

<a id="gutmann_frontiers2022"></a>

> B. Sanchez, P. R. Campodonico & R. Contreras, 'Gutmann's Donor and Acceptor Numbers for Ionic Liquids and Deep Eutectic Solvents', Frontiers in Chemistry 2022.

| | |
| --- | --- |
| Identifier | [10.3389/fchem.2022.861379](https://doi.org/10.3389/fchem.2022.861379) |
| Status | **not shipped** |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `gutmann_frontiers2022.pdf` (not checked) |
| Used by | `CLAUDE.md` |

**Why it is not shipped.** The accessible source tabulates ionic liquids and deep eutectic solvents
rather than the classical molecular table, and reports its own
acceptor-number model failing outright ('no correlation could be found'),
concluding it supports 'qualitative and relative criteria but not an
absolute and quantitative model'.

THE AUTHORS WERE INVENTED ONCE AND ARE NOW READ FROM THE PAPER, AND THE
GUESS WAS WRONG. This entry claimed "S. Kaya et al." and a local copy at
`kaya2022.pdf`, both from matching the DOI's year against a filename;
`kaya2022.pdf` is "On the Prediction of Lattice Energy with the Fukui
Potential", J. Phys. Chem. A 2022, 126, 4507-4516. The real authors are
Sanchez, Campodonico and Contreras, of Universidad de Chile.

The title settles the scope objection outright: these are Gutmann's numbers
**for ionic liquids and deep eutectic solvents**, which is precisely why the
paper does not supply the classical molecular table this project needed.

Partly available by another route anyway: the donor number is DEFINED as
-dH against SbCl5, which is already in the Drago table
([source:vogel_drago1996]).

## Datasets

### bradley2014

<a id="bradley2014"></a>

> J-C. Bradley, W. E. Acree Jr & A. S. I. D. Lang, 'Compounds with known Abraham descriptors', figshare 2014.

| | |
| --- | --- |
| Identifier | [10.6084/m9.figshare.1176994](https://doi.org/10.6084/m9.figshare.1176994) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Licence | CC BY 4.0 |
| Used by | `src/openchem/chem/data/abraham_solutes.json`, `src/openchem/chem/abraham.py`, `tools/build_abraham_tables.py` |

2193 solute descriptor sets after two quality gates, and the second is a
trap: a `donotuse` column with a written reason (6 rows), and **-123 as a
missing-value sentinel** (513 rows), which `float()` reads as a perfectly
ordinary number. A single leak puts a wildly negative descriptor into a
prediction that still looks like a prediction.

432 InChIKeys appear more than once and only 51 of those groups agree
exactly; merged by median with the per-descriptor spread kept and
propagated into a stated uncertainty. Acetanilide settles the design --
three rows give S = 3.61, 1.54, 1.37 and the FIRST is the outlier, so 'take
the first row' would have shipped it.

### llinas2008

<a id="llinas2008"></a>

> A. Llinas, R. C. Glen & J. M. Goodman, 'Solubility Challenge: Can You Predict Solubilities of 32 Molecules Using a Database of 100 Reliable Measurements?', J. Chem. Inf. Model. 2008.

| | |
| --- | --- |
| Identifier | J. Chem. Inf. Model. 2008, 48, 1289-1303 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `benchmarks/solubility/fetch.py`, `benchmarks/solubility/score.py` |

The data is reached through AqSolDB's `dataset-I` ([source:aqsoldb]) rather
than from the paper, so no claim of ours is checked against it -- but the
CITATION is now verified, from reference (2) of [source:llinas2020], where
the same authors cite their own earlier paper as "J. Chem. Inf. Model.
2008, 48, 1289-1303". 94 rows of intrinsic solubility by one
consistent method on druglike compounds; it post-dates ESOL's 2004 fit,
which is what makes it usable as a test set at all.

Scoring it exposed a defect in this project's own scorer: three compounds
appear under one InChIKey as two solid forms (chlorprothixene form I and
form II, -6.75 and -5.87), and both were being scored -- counting them
twice AND charging the polymorph gap, up to 0.88 log, to the model as
prediction error. Refusing them moved every published figure.

### llinas2020

<a id="llinas2020"></a>

> A. Llinas, I. Oprisiu & A. Avdeef, 'Findings of the Second Challenge to Predict Aqueous Solubility', J. Chem. Inf. Model. 2020, Table 1.

| | |
| --- | --- |
| Identifier | [10.1021/acs.jcim.0c00701](https://doi.org/10.1021/acs.jcim.0c00701) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Local copy | `llinas2020.pdf` (not checked) |
| Used by | `benchmarks/solubility/extract_sc2.py`, `docs/VALIDATION.md` |

EXTRACTING TABLE 1 FROM THE PDF NEEDED AN ACCEPTANCE TEST, AND THE PAPER
SUPPLIES ONE. The table closes with a Min/Max/Mean row. The first
extraction produced a perfectly plausible 129 rows by running past the end
of Table 1 into Table 2 -- the 'contentious' set, interlab SD 0.62 --
silently mixing two data qualities. Recomputing the summary row caught it;
the count alone would not have, because 129 looks as reasonable as 100. Two
further defects fell out of the same check: a row split across a page break
(bromazepam), and a melting point carrying a footnote marker (`193b`).

It supplies this endpoint's noise floor, with a distinction worth keeping:
the interlaboratory SD of ~0.17 log is stated by this paper directly, while
the CheqSol-against-shake-flask RMSE = 0.34 carries a citation marker in
its own text and belongs to its reference (5), Avdeef, ADMET & DMPK 2019,
7, 210-219. Quoting 0.34 as this paper's measurement would be one
attribution too far. It also gives a baseline: on the
same 73 compounds the General Solubility Equation scores RMSE 1.18 against
ESOL's 1.26, and the GSE needs a MEASURED melting point this app does not
have. So 'the endpoint is hard' rather than 'our model is poor'.

Its interlaboratory mean for aspirin (-1.67 over 16 sources) OVERTURNED a
claim this project had shipped, which rested on an ESOL-era value of -2.19.

### kwon2023

<a id="kwon2023"></a>

> Y. Kwon et al., 'DELTA50: A Highly Accurate Database of Experimental 1H and 13C NMR Chemical Shifts Applied to DFT Benchmarking', Molecules 2023, 28, 2449.

| | |
| --- | --- |
| Identifier | [10.3390/molecules28062449](https://doi.org/10.3390/molecules28062449) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Licence | CC BY 4.0 |
| Used by | `benchmarks/nmr/delta50.py` |

50 small molecules, assigned 13C in CDCl3, read from
`DELTA50_benchmark.xlsx` in the paper's supplementary archive: 600 MHz,
<=10 mM, TMS internal reference, ambiguities resolved by
gCOSY/gHSQC/gHMBC.

CHOSEN BECAUSE IT IS NOT CIRCULAR. nmrshiftdb2 ([source:nmrshiftdb2]) IS
the lookup's index, so scoring the lookup against it would measure
memorisation.

### nubase2020

<a id="nubase2020"></a>

> F. G. Kondev, M. Wang, W. J. Huang, S. Naimi & G. Audi, 'The NUBASE2020 evaluation of nuclear physics properties', Chinese Physics C 45, 030001 (2021).

| | |
| --- | --- |
| Identifier | [10.1088/1674-1137/abddae](https://doi.org/10.1088/1674-1137/abddae) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-18 |
| Local copy | `Kondev_2021_Chinese_Phys._C_45_030001.pdf` (not checked) |
| Used by | `tools/build_nuclide_table.py`, `src/openchem/chem/data/nuclides.json`, `src/openchem/chem/data/nubase_4.mas20.txt`, `src/openchem/chem/nuclides.py`, `src/openchem/chem/decay.py` |

Every ground-state nuclear property this application knows: half-life,
decay modes with branchings, natural abundance, spin and parity, mass
excess. 3,557 ground states, from the 5,843-row electronic table.

**THE LICENCE IS THREE SEPARATE CLAIMS, because a paper's licence does not
automatically licence a separately distributed data file.** They are
distinct works, and inferring one from the other is the provenance mistake
this project has spent whole commits undoing -- see the electronegativity
correction under [source:crc_handbook].

  1. THE ARTICLE IS CC BY 3.0, verbatim from page 030001-1: "Content from
     this work may be used under the terms of the Creative Commons
     Attribution 3.0 licence. Any further distribution of this work must
     maintain attribution to the author(s) and the title of the work,
     journal citation and DOI."
  2. THE ARTICLE CONTAINS THIS TABLE. Table I, "The NUBASE2020 table",
     runs about 160 of the paper's 181 pages, and U-238 was cross-checked
     against the electronic parse: `4.463 Gy`, `IS=99.2742 10; A=100;
     SF=5.44e-5 7; 2B-=2.2e-10 3`, identical. **That establishes the
     correspondence, not that all 5,843 rows are byte-identical** -- one
     row cannot, and the claim is written no wider than the check.
  3. THE ELECTRONIC FILE CARRIES A CITATION REQUEST, not a licence grant.
     The AMDC page says "any work that will use the file should make
     reference to this paper and not to the electronic files."

So the shipped table reproduces values published under CC BY 3.0 and is
attributed accordingly -- authors, title, journal citation and DOI -- which
is also exactly what AMDC asks for, so the two obligations are one action.
**This entry does not assert that the data file itself is CC BY.**

`verification = "citation_and_claim"`: the citation is confirmed from the
PDF in Sci Downloads, and the claim is the generator's acceptance block --
U-238 at 4.463 Gy and 99.2742%, Po-209 at 124 y, C-14 at 5,700 y, Tc-99 at
2.11e5 y, and exactly 253 stable nuclides.

THE SOURCE SNAPSHOT IS COMMITTED, NOT FETCHED. `nubase_4.mas20.txt` sits
beside the generated JSON and `--check` never touches the network: an
upstream that can change under CI would turn runs red with nothing in this
repository having moved, and a hash alone says which bytes were expected
without giving a future reader the bytes to regenerate from. The manifest
records the sha256 (which bytes) and the revision (which scientific
release) -- the second being what answers "why does this disagree with
NUBASE2024".

GROUND STATES ONLY, and enforced rather than described. NUBASE carries
isomers at T-half >= 100 ns; a molfile cannot express Tc-99m as distinct
from Tc-99, so those rows would be data nothing here could reach. The free
neutron is skipped with them -- NUBASE lists it as Z=0, and it is not an
element. Both exclusions are build-time invariants, because a documented
policy nothing enforces is how somebody helpfully adds them back.

### aqsoldb

<a id="aqsoldb"></a>

> M. C. Sorkun, A. Khetan & S. Er, 'AqSolDB, a curated reference set of aqueous solubility and 2D descriptors for a diverse set of compounds', Scientific Data 2019, 6:143.

| | |
| --- | --- |
| Identifier | [10.1038/s41597-019-0151-1](https://doi.org/10.1038/s41597-019-0151-1) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `aqsoldb.pdf` (not checked) |
| Used by | `benchmarks/solubility/fetch.py`, `benchmarks/solubility/README.md` |

Verified from the paper: Scientific Data (2019) 6:143,
doi 10.1038/s41597-019-0151-1, by Sorkun, Khetan and Er. The title and
volume had been added here from memory, removed as unverifiable, and are
now restored from the source. **The removal was still right**: at the time
nothing distinguished that guess from the one that put a different paper's
title on [source:avdeef2020], and only reading the source can tell those
apart afterwards.

The data itself is still fetched from `https://github.com/mcsorkun/AqSolDB`.

DOWNLOADED PARTLY IN ORDER TO SUBTRACT IT. AqSolDB is a merge of nine
sources, and TWO of them make it dangerous as an evaluation set:

  dataset-G  is Delaney's own ESOL fitting set ([source:delaney2004]),
             so scoring ESOL on AqSolDB scores a model on its own fit
  the merge  is the ADMET sidecar's training set, so scoring that model
             on it measures memorisation

The first was the one nobody suspected -- refusing to score the sidecar on
its own training data was in the plan; the fact that the OTHER model's
training data was hiding inside the same file was not. 14 of 94 rows share
an InChIKey with `dataset-G` and are dropped. An evaluation set assembled
from other people's datasets inherits ALL of their provenance.

`dataset-I` is the Solubility Challenge ([source:llinas2008]).

### ons_solubility

<a id="ons_solubility"></a>

> J-C. Bradley, R. Guha, B. Hooker, S. J. Koch, A. S. I. D. Lang, C. Neylon et al., 'Open Notebook Science Challenge Solubility Dataset', figshare.

| | |
| --- | --- |
| Identifier | [10.6084/m9.figshare.1514952](https://doi.org/10.6084/m9.figshare.1514952) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | CC BY 4.0 |
| Used by | `benchmarks/solubility/nonaqueous.py` |

The non-aqueous benchmark's data, and the only reason that benchmark can
defend itself at all: the set carries a CITATION column, so rows from
Abraham or Acree publications can be dropped -- 1998 of 9536, 21%.

That defence is PARTIAL and the leakage is structural. Abraham's solvent
coefficients ([source:bradley2015]) were fitted to measured solubilities,
so the endpoint being scored IS the endpoint they were fitted to. The
de-leaking is measured in both directions: `--keep-leaked` improves the
shift arm from 0.29 to 0.21 MAE, which is the coefficients looking 28%
better on data they were fitted to.

### nmrshiftdb2

<a id="nmrshiftdb2"></a>

> S. Kuhn & N. E. Schlorer, 'Facilitating quality control for spectra assignments of small organic molecules: nmrshiftdb2 - a free in-house NMR database with integrated LIMS for academic service laboratories', Magn. Reson. Chem. 2015, 53, 582-589.

| | |
| --- | --- |
| Identifier | [10.1002/mrc.4263](https://doi.org/10.1002/mrc.4263) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `kuhn2015.pdf` (not checked) |
| Used by | `src/openchem/services/nmr_database_setup.py`, `src/openchem/chem/nmr_database.py`, `src/openchem/chem/hose_codes.py` |

Downloaded on demand (~152 MB), indexed, then the download is discarded.
IT IS THE HOSE-CODE LOOKUP'S OWN INDEX, so it is circular as ground truth
and nothing is scored against it -- see [source:kwon2023], which exists for
that reason.

**THE PROJECT'S OWN SITE IS THE ONE PLACE THIS IS NOT AVAILABLE**, which is
why three attempts at it failed: the SourceForge page states only that "the
data is published under an open content license" without naming which and
gives no citation, the web front end at nmr.uni-koeln.de serves a Jetspeed
login form rather than an about page, and its help path 404s. The citation
lives in the literature instead.

Two further references for the same database, both now held locally and
read:

    Kuhn, Kolshorn, Steinbeck & Schlorer, "Twenty years of nmrshiftdb2: A
    case study of an open database for analytical chemistry", Magn. Reson.
    Chem., doi 10.1002/mrc.5418. **FOUR AUTHORS, not the two a search
    result gave** -- Kolshorn and Steinbeck were dropped by the summary and
    restored from the paper. A secondary source is not more reliable than
    the document for something as mechanical as an author list.

    Steinbeck, Krause & Kuhn, "NMRShiftDB - Constructing a Free Chemical
    Information System with Open-Source Components", J. Chem. Inf. Comput.
    Sci., doi 10.1021/ci0341363 (`steinbeck2003.pdf`) -- the original
    database this one succeeded, from the Max-Planck-Institute of Chemical
    Ecology, Jena

THE LICENCE IS STILL ONLY "OPEN CONTENT" and is not pinned to a named
licence by anything read so far.

### tdc_admet

<a id="tdc_admet"></a>

> Therapeutics Data Commons, 'Therapeutics Data Commons: Machine Learning Datasets and Tasks for Drug Discovery and Development', NeurIPS 2021. Author list not established -- see note.

| | |
| --- | --- |
| Identifier | <https://tdcommons.ai/> |
| Status | reference only |
| Verification | citation |
| Verified | 2026-08-17 |
| Used by | `benchmarks/admet/README.md`, `README.md` |

**Why it is reference only.** Named as the shipped ADMET sidecar's training set so its accuracy figures
can be read correctly -- they are the vendor's held-out numbers, not ours,
and the model trained on all of TDC. Nothing here is scored against it.

Title and venue read from tdcommons.ai, which names its primary publication
as "Therapeutics Data Commons: Machine Learning Datasets and Tasks for Drug
Discovery and Development", NeurIPS 2021, and a companion "Artificial
Intelligence Foundation for Therapeutic Science", Nature Chemical Biology
2022. **The author list is not on that page and is not recorded here** --
supplying one from memory is the mistake that put a different paper's title
on [source:avdeef2020].

The original plan's route to this data did not work and the failure was
misleading: TDC's Harvard Dataverse returned 403, and PyTDC then cached the
0-byte failure as a 'local copy', so every retry reported 'Found local
copy...' before failing -- which reads as a code bug rather than an outage.

### cod

<a id="cod"></a>

> Crystallography Open Database (COD).

| | |
| --- | --- |
| Identifier | <https://www.crystallography.net/cod/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | public domain, by COD's own statement, except where a deposition says otherwise |
| Used by | `tests/fixtures/cif/SOURCES.md`, `spikes/crystallography/halite.cif` |

Six real depositions are committed as CIF parser fixtures. They are worth
more than any fixture this project could author because each states its own
`_cell_volume` and `_exptl_crystal_density_diffrn`, computed by the
depositor's software -- so reproducing those two numbers exercises parsing,
symmetry expansion, wrapping, deduplication, composition and cell volume
AGAINST A VALUE THIS PROJECT DID NOT PRODUCE.

Five are public domain. 1569411 is NOT and requires attribution to
[source:bravetti2023].

### rcsb_pdb

<a id="rcsb_pdb"></a>

> RCSB Protein Data Bank.

| | |
| --- | --- |
| Identifier | <https://www.rcsb.org/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `src/openchem/services/receptor_library_service.py`, `src/openchem/chem/receptor_library.py`, `benchmarks/assembly/build.py` |

Source of the 49 curated docking receptors, downloaded on demand rather
than committed, and of the biological-assembly gate's reference structures.
RCSB's own pre-generated assemblies are the oracle the assembly builder is
scored against -- every buildable entry matches on every atom to the written
digit.

### llinas2019

<a id="llinas2019"></a>

> A. Llinas & A. Avdeef, 'Solubility Challenge Revisited after Ten Years, with Multilab Shake-Flask Data, Using Tight (SD ~0.17 log) and Loose (SD ~0.62 log) Test Sets', J. Chem. Inf. Model. 2019, 59, 3036.

| | |
| --- | --- |
| Identifier | [10.1021/acs.jcim.9b00345](https://doi.org/10.1021/acs.jcim.9b00345) |
| Status | reference only |
| Verification | citation |
| Verified | 2026-08-16 |
| Local copy | `llinas2019.pdf` (not checked) |
| Used by | `benchmarks/solubility/README.md`, `CLAUDE.md` |

**Why it is reference only.** This project takes its Solubility Challenge 2 data from Table 1 of
[source:llinas2020], not from here, so nothing is scored against this
paper. It is registered because it is where the TIGHT and LOOSE sets come
from -- their names, their membership and the SD ~0.17 / ~0.62 figures that
characterise them are this paper's, and the 2020 paper reports findings ON
them.

FOUND BY VERIFICATION, NOT BY THE ORIGINAL SWEEP. `llinas2019.pdf` sat in
the archive and was assumed to be the 2008 challenge; it is a third,
distinct paper. Without it the tight/loose vocabulary that
`benchmarks/solubility/` and CLAUDE.md both use has no source at all, and
the SD 0.17 figure looks like it originates in the 2020 paper.

Title, authors and DOI read from the PDF, and corroborated by reference (1)
of [source:llinas2020], which supplies the volume and page.

### hopfinger2009

<a id="hopfinger2009"></a>

> A. J. Hopfinger, E. X. Esposito, A. Llinas, R. C. Glen & J. M. Goodman, 'Findings of the challenge to predict aqueous solubility', J. Chem. Inf. Model. 2009, 49, 1-5.

| | |
| --- | --- |
| Identifier | J. Chem. Inf. Model. 2009, 49, 1-5 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `benchmarks/solubility/extract_avdeef_sets.py`, `benchmarks/solubility/README.md`, `docs/VALIDATION.md` |

The underlying source of external test set A2, which this project reaches
through Avdeef's appendix ([source:avdeef2020]) rather than from the paper.
23 rows survive de-leaking and yield 7 bases -- under the minimum of 10 to
serve as a held-out side, which is why it could only join the fit pool and
why more data did not rescue the base-bias experiment.

Citation confirmed from reference (3) of [source:llinas2020]. Independent of
Delaney's fit as far as the source states.

### yalkowsky_banerjee1992

<a id="yalkowsky_banerjee1992"></a>

> S. H. Yalkowsky & S. Banerjee, 'Aqueous Solubility: Methods of Estimation for Organic Compounds', Marcel Dekker Inc., New York, 1992.

| | |
| --- | --- |
| Identifier | 978-0-8247-8615-1 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `mackay1993.pdf` (not checked) |
| Used by | `benchmarks/solubility/extract_avdeef_sets.py`, `benchmarks/solubility/README.md`, `docs/VALIDATION.md` |

**`local` IS A REVIEW OF THE BOOK, NOT THE BOOK**, and the distinction is
kept deliberately. `mackay1993.pdf` is journal back matter from January
1993 carrying D. Mackay's (Institute for Environmental Studies, University
of Toronto) review, which states the publisher, year, price and **ISBN
0-8247-8615-7** -- independently confirming the bibliographic record found
via search. It is not the contents, which is why this stays `citation` and
not `citation_and_claim`.

**AND THE REVIEW EXPLAINS A FINDING IN THIS PROJECT'S OWN BENCHMARK.** It
notes that "regrettably there is no treatment of dissociating or ionizing
solutes such as phenols or amines". External test set A1 is drawn from this
book and yields **zero bases** -- a fact `benchmarks/solubility/` records as
an obstacle without explaining it. The book excludes ionizing solutes by
design, so A1 could not have contained bases. That is the reason, from the
source, for a number this project had only observed.

The underlying source of external test set A1, reached through Avdeef's
appendix ([source:avdeef2020]). A classic compilation of industrial and
agrochemical solubility -- which is the chemistry ESOL was fitted on, and
duly **74% of it is inside ESOL's own training set** (14 of 19 rows share an
InChIKey with Delaney's fit). It yields zero bases.

IT IS A BOOK, WHICH IS WHY NO DOI SEARCH COULD EVER HAVE FOUND IT.
ISBN-10 0-8247-8615-7. Nothing beyond the author-year string was recorded
anywhere in this repository, and the guess that it was a book rather than
an article turned out right -- which is not the same as having been
entitled to record it as one.

**PAGE COUNT DELIBERATELY OMITTED.** Two independent reviews give different
figures -- 272 pp and vi + 263 pp -- which is ordinary (front matter
counted or not) and not worth asserting either way.

The A1 finding that rests on this book -- "74% inside ESOL's own training
set" -- remains a claim about its CONTENTS that nothing here has checked,
which is why `verification` stops at `citation`.

## Legal texts

### cwc_annex_on_chemicals

<a id="cwc_annex_on_chemicals"></a>

> Convention on the Prohibition of the Development, Production, Stockpiling and Use of Chemical Weapons and on their Destruction (CWC), Annex on Chemicals, Schedules 1, 2 and 3.

| | |
| --- | --- |
| Identifier | CWC Annex on Chemicals (entered into force 1997-04-29) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Used by | `src/openchem/chem/data/regulatory/sources/cwc_schedule_1.json`, `src/openchem/chem/data/regulatory/sources/cwc_schedule_2.json`, `src/openchem/chem/data/regulatory/sources/cwc_schedule_3.json` |

These rulesets carry their own per-rule provenance and are NOT given a
`source_key` -- `legal.quote` holds the regulation's actual words and
`legal.cited_identifiers` its printed CAS numbers, governed by
`src/openchem/chem/data/regulatory/sources/README.md` and its build. A
second provenance mechanism beside a working one is how two accounts drift
apart.

The rule that matters there: an identity is resolved from the statute's
CAS, never from its name. Over the 27 named chemicals of Schedules 2 and 3,
a name resolver disagreed with the CAS twice, and both look perfectly
successful if you only ask whether the name resolved -- 'sulphur
monochloride' and 'dimethyl phosphite' both resolve to the wrong molecular
formula, in two different ways.

### dea_listed_chemicals

<a id="dea_listed_chemicals"></a>

> US Drug Enforcement Administration, List I and List II chemicals (21 CFR 1310.02).

| | |
| --- | --- |
| Identifier | 21 CFR 1310.02 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `src/openchem/chem/data/regulatory/sources/dea_listed_chemicals.json` |

The whole DEA list is UNDATED at both rule and ruleset level -- 47 of the
91 shipped rules. An undated rule is NOT date-filtered, and that wording is
load-bearing: treating an absent date as 'never applicable' would silently
empty a majority of the screen while looking exactly like a substance that
is not listed.

## Standards

### ich_m9

<a id="ich_m9"></a>

> ICH Harmonised Guideline, 'Biopharmaceutics Classification System-Based Biowaivers M9', final version adopted 20 November 2019 (Step 4).

| | |
| --- | --- |
| Identifier | ICH M9 (Step 4, 20 November 2019) |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-17 |
| Used by | `src/openchem/chem/solubility.py` |

Read from the guideline itself, which is freely published. Its solubility
criterion reads: "A drug substance is classified as highly soluble if the
highest single therapeutic dose is completely soluble in 250 ml or less of
aqueous media over the pH range of 1.2-6.8 at 37+-1 C."

All three numbers the code uses match that sentence exactly --
`BCS_PH_LOW = 1.2`, `BCS_PH_HIGH = 6.8`, `BCS_VOLUME_ML = 250.0` -- which
is what makes this `citation_and_claim` rather than `citation`.

**"AQUEOUS MEDIA" IS IN THE CRITERION ITSELF**, so the water-only scoping is
the guideline's, not an assumption of ours: the screen, the pH curve and the
Henderson-Hasselbalch adjustment are all aqueous, and a non-aqueous solvent
gets `NON_AQUEOUS_SOLVENT` rather than an authoritative-looking number.

### iupac2013

<a id="iupac2013"></a>

> IUPAC, Nomenclature of Organic Chemistry: Recommendations and Preferred Names 2013 (the Blue Book).

| | |
| --- | --- |
| Identifier | IUPAC Recommendations and Preferred Names 2013 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `src/openchem/chem/data/hypervalent_rules.json`, `src/openchem/vendor/iupac_namer` |

P-14.1 is the lambda-convention that `hypervalent_rules.json` follows: a
hypervalent centre gains ligands in pairs, so the halogens step 1, 3, 5, 7
and never reach an even count. The vendored naming engine implements the
2013 recommendations more broadly ([source:iupac_namer]).

## Reference tables

### allred1961

<a id="allred1961"></a>

> A. L. Allred, 'Electronegativity values from thermochemical data', J. Inorg. Nucl. Chem. 1961, Vol. 17, pp. 215-221.

| | |
| --- | --- |
| Identifier | J. Inorg. Nucl. Chem. 1961, 17, 215-221 |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Local copy | `allred1961.pdf` (not checked) |
| Used by | `src/openchem/chem/data/electronegativity.json` |

Verified from the paper's own header: "J. Inorg. Nucl. Chem., 1961, Vol.
17. pp. 215 to 221 ... ELECTRONEGATIVITY VALUES FROM THERMOCHEMICAL DATA,
A. L. ALLRED, Department of Chemistry, Northwestern University".

The title had been guessed here once and removed as unverifiable. The guess
happened to be right, which is not the same as having been right to record
it -- the identical guess on [source:avdeef2020] named a different paper.

Pauling's original values as revised by Allred -- the set reproduced in the
CRC Handbook ([source:crc_handbook]) and in IUPAC's tables. The NUMBERS are
a standard published table reproduced rather than derived; what this project
measured is the ALGORITHM consuming them, in `tests/test_oxidation_states.py`.

He, Ne and Ar have no accepted Pauling value and are ABSENT. An absent
element is a refusal, never a guess.

### crc_handbook

<a id="crc_handbook"></a>

> CRC Handbook of Chemistry and Physics, 97th edition.

| | |
| --- | --- |
| Identifier | CRC Handbook of Chemistry and Physics, 97th edition |
| Status | shipped |
| Verification | citation + claim |
| Verified | 2026-08-18 |
| Local copy | `CRC_Handbook_of_Chemistry_and_Physics_97.pdf` (not checked) |
| Used by | `src/openchem/chem/data/elements.json`, `src/openchem/chem/element_palettes.py`, `src/openchem/chem/data/electronegativity.json`, `src/openchem/chem/lattice_energy.py` |

"WHICH EDITION" TURNED OUT TO BE THE WRONG QUESTION. With the 97th edition
in hand the answer is that no number here came from any edition -- see
`reason` above -- so the entry is `reference_only` rather than a shipped
source.

**AND ONE CLAIM ABOUT IT IS MEASURABLY FALSE.**
`electronegativity.json` said the Allred set is "the set reproduced in the
CRC Handbook of Chemistry and Physics and in IUPAC's own tables". Compared
element by element against table 9-103 of the 97th edition: **72 of 85
match and 13 do not** -- As, Au, Bi, Hg, Lu, Np, Pb, Pt, Pu, Tc, Tl, U, W.
Some differ widely: Pb 2.33 against 1.8, W 2.36 against 1.7.

The cause is not an error on either side. CRC's table states outright that
it gives values "for the most common oxidation state", which is a different
quantity: Allred's own Table 4 is titled "Electronegativities of some
elements in different oxidation states" and lists Tl(I) 1.62 -- exactly the
shipped Tl -- and Pb(II) 1.87, where this project ships the Pb(IV) value.
Fe 1.83 and Tl 1.62 both appear in Allred's tables directly, so the
attribution to [source:allred1961] is sound and NO SHIPPED VALUE IS WRONG.
The word "reproduced" is what does not survive, and it has been corrected
in the data file.

The lattice-energy table in the 97th edition is at page 2097 and is by
"H. D. B. Jenkins and H. K. Roobottom" -- the same Jenkins as
[source:jenkins1999], which is why that paper's ref 40 points here.

**THE OXIDATION STATES WERE CHECKED AGAINST IT AND STILL DID NOT COME
FROM IT**, which is why this entry is still `reference_only` after a
review that expected to move it. `elements.json`'s
`common_oxidation_states` was compared against the periodic table on page
2639 (the poster is rotated 90 degrees in the PDF and its text layer
interleaves neighbouring cells, so this was read from a render at 10x,
not extracted).

The halogens were the reason for looking, and the expectation going in
was wrong. Reported internally as "bromine is missing +3 and +7, which
makes it inconsistent with chlorine in the same group". The CRC prints:

    F   -1
    Cl  +1 +5 +7 -1        <- no +3
    Br  +1 +5 -1           <- no +3, no +7
    I   +1 +5 +7 -1
    At  (none listed)

So **bromine matches the CRC exactly** and the group asymmetry is the
source's own. What differs is CHLORINE, where this project ships a +3 the
CRC does not -- and Cl(III) is real chemistry (ClF3, chlorites), so the
divergence is the CRC being conservative rather than this project being
wrong. The same holds for the noble gases: the CRC lists `0` for all six,
where this project lists Kr +2, Xe +2/+4/+6 and Rn +2, which are XeF6 and
its relatives.

**THE PHASE POINTS, BY CONTRAST, REALLY DO COME FROM THE BOOK.** 103 of
118 elements, from 4-116..4-118, extracted by binning words against the
table's own column positions -- the columns are right-aligned, so values
sit LEFT of their headers, and binning against the headers directly gave
2 rows out of 100 before the acceptance checks caught it. Three further
things it had to get right, each found the same way: the CRC spells them
"Aluminum" and "Cesium"; sulfur's rhombic row holds "95.2 trans monocl",
a TRANSITION rather than a melt, so the monoclinic row is the one with a
melting point; and allotropes are listed separately, so the reference
form is chosen explicitly (graphite, white P, gray Se, monoclinic S,
white Sn).

Sublimation is READ from the table's own "sp" marker -- arsenic and
carbon -- and never inferred from a missing boiling point, which would
put all fifteen superheavies in that class.

NO SHIPPED VALUE WAS CHANGED. The honest description of this column is
that it is a curated set, checked against the CRC, which is a MORE
CONSERVATIVE presentation of the same question -- not that it was taken
from it. A full element-by-element reconciliation of all 118 is not done;
the halogens and the noble gases are.

### abraham_predicted_solvents

<a id="abraham_predicted_solvents"></a>

> The predicted (non-measured) solvent coefficients of Bradley, Abraham, Acree & Lang 2015 -- 202 solvents, of which the article tabulates 118.

| | |
| --- | --- |
| Identifier | [10.1186/s13065-015-0085-4](https://doi.org/10.1186/s13065-015-0085-4) |
| Status | **not shipped** |
| Verification | citation + claim |
| Verified | 2026-08-16 |
| Used by | `src/openchem/chem/abraham.py`, `docs/VALIDATION.md` |

**Why it is not shipped.** The paper says of these they should not be taken 'as gospel', and two
measurements agree.

They FAIL THE UNCERTAINTY BOUND THE MODULE ALREADY APPLIES. Propagating the
paper's own Table 4 out-of-bag RMSE through the same sum(|error| x
descriptor) used for measured-descriptor disagreement gives, against a
ceiling of 1.0: aspirin 1.57, caffeine 2.04, ibuprofen 1.34, paracetamol
1.76. Caffeine is a factor of 110. Only benzene passes, and a solvent that
works for benzene and no drug is not an option. Two coefficients are poor
at the source -- OOB R^2 0.308 for `e` and 0.474 for `b`.

And IT IS THE WRONG PARAMETERISATION: the predicted table carries only the
c = 0 refit (equation 3, for log P), while the solubility equation is
equation 2 and needs the intercept. Ethanol's measured `c` is +0.222 and
the predicted table has no column for it.

The NAMES ship so a refusal can be specific; no coefficient ever does.

Acetic acid was asked for BY NAME, which is why this is a refusal with a
reason rather than an oversight. The good message was at first unreachable
for the one case it exists for -- it lived in `solvent_shift` while
`resolve_solvent` refuses an unknown solvent several layers earlier -- so
`predicted_only_reason()` is one function called from both.

### miller_polarizability

<a id="miller_polarizability"></a>

> Miller's atomic hybrid polarizability parameters.

| | |
| --- | --- |
| Identifier | no usable published parameter set -- see reason |
| Status | **not shipped** |
| Verification | unverified |
| Used by | `docs/VALIDATION.md` |

**Why it is not shipped.** THE PARAMETERS ARE UNPUBLISHED. A reconstruction missed benzene by +27% and
CCl4 by -50%, so there was nothing to validate against and nothing shipped.

### hlb

<a id="hlb"></a>

> The Hydrophilic-Lipophilic Balance (HLB) surfactant scale.

| | |
| --- | --- |
| Identifier | no usable published formula -- see reason |
| Status | **not shipped** |
| Verification | unverified |
| Used by | `docs/VALIDATION.md` |

**Why it is not shipped.** No formulas published, no worked example, and the reference implementation's
default is a proprietary consensus method. Nothing to check a result
against.

### tsei

<a id="tsei"></a>

> The TSEI (Topological Steric Effect Index).

| | |
| --- | --- |
| Identifier | several incompatible published definitions -- see reason |
| Status | **not shipped** |
| Verification | unverified |
| Used by | `docs/VALIDATION.md` |

**Why it is not shipped.** Several incompatible definitions in the literature and no reference value to
gate against. Omitted rather than guessed. The Szeged index, from the same
batch, DID ship -- because it has one definition and a checkable value.

### sci_downloads_note

<a id="sci_downloads_note"></a>

> Alex's local paper archive, `D:\Xaero Stuff\Documents\Sci Downloads\`.

| | |
| --- | --- |
| Identifier | local archive, not in the repository |
| Status | reference only |
| Verification | citation |
| Verified | 2026-08-16 |
| Used by | `CLAUDE.md`, `docs/DREIDING_ASSESSMENT.md` |

**Why it is reference only.** Not a source in itself. Registered so the `local` field on other entries
has something to point at, and because this project spent months asserting
that papers it already had on disk were unobtainable.

The `local` field is NEVER checked by any guard -- the folder is not in the
repository and CI cannot see it. That is an admitted gap, not an oversight:
a check that cannot run is worse than a stated limit.

Read these with `pymupdf` (`uv pip install --system pymupdf`, then `fitz`);
there is no PDF text extractor in the project venv and `pdftoppm` is not
installed, so `Read` on a PDF fails.

## Bundled and depended-on software

### ketcher

<a id="ketcher"></a>

> Ketcher, EPAM Systems -- the 2D structure editor bundled as `resources/ketcher/dist`.

| | |
| --- | --- |
| Identifier | <https://github.com/epam/ketcher> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | Apache-2.0 |
| Version | `3.17.0` |
| Package | `ketcher-react` |
| Version source | `tools/ketcher-host/package-lock.json` |
| Bundled at | `src/openchem/resources/ketcher` |
| Third-party files | `dist/**` |
| Licence files | `LICENSE`, `THIRD-PARTY-NOTICES.txt` |

IT SHIPPED WITH NO LICENCE FILE AT ALL until this registry was built, while
Mol*, 3Dmol and the vendored namer each carried one. It is redistributed in
every build.

The version is checked against the LOCKFILE, not `package.json`. The
declaration happens to be an exact pin here (`"3.17.0"`, no caret), but the
lockfile is what resolves with an integrity hash and so is what actually
proves the install.

THE CHECK PROVES THE LOCKFILE, NOT THE BUNDLE. The committed dist carries
no version string anywhere, so nothing can prove it was built FROM that
lockfile -- the same gap `tests/test_ketcher_bundle_is_current.py` already
lives with ("it catches a forgotten rebuild, not a broken one").

AND `dist/` IS A BUNDLE, NOT A LIBRARY -- NOW ATTRIBUTED. It contains
third-party code beyond Ketcher itself: EPAM's Miew 0.11.1 is proven by its
surviving banner, three.js by its constants.

Their notices are NOT recoverable from the artifact -- the build strips
comments even with minification off, so exactly two licence banners survive
in 35 MB. `THIRD-PARTY-NOTICES.txt` is therefore GENERATED by
`tools/build_ketcher_notices.py` from the lockfile plus the licence files in
`node_modules/`, and committed beside the dist for the same reason the dist
is: CI has no node, and a fresh clone must carry what it redistributes.

**318 of the 429 packages**, being every one the lockfile does not mark
`dev`. That is deliberately MORE than the bundle contains -- a build-time
tool can be a runtime dependency of a runtime package (the `@babel/*` set
arrives via `@emotion/babel-plugin`), and vite tree-shakes -- because
over-attribution is the safe direction and narrowing would mean deciding per
package whether any of its code survived a comment-stripped 35 MB artifact.
The file says so itself rather than implying a precision the method lacks.

Miew appears in it at **0.11.1, matching the banner in the dist exactly**,
which is what says the lockfile-derived list really describes the artifact.
Six packages ship no licence file and are listed with the identifier their
`package.json` declares; three of those are the Ketcher packages themselves,
covered by `LICENSE` beside it.

The licence guard still proves DECLARATION rather than compatibility.

The LICENCE TEXT is the canonical Apache-2.0 (byte-identical to the copy
two independent npm packages ship, sha256 d96eba1f...), with the copyright
line taken verbatim from ketcher-react's own README: "Copyright (c) 2021
EPAM Systems, Inc." The ketcher packages ship no LICENSE file themselves,
only a `license: Apache-2.0` field, so there was no upstream file to copy.

Note `ketcher-core` resolves to 3.17.1 while `ketcher-react` and
`ketcher-standalone` are 3.17.0 -- which is why `package_name` is declared
explicitly and never inferred from this entry's key.

### molstar

<a id="molstar"></a>

> Mol* (molstar), the macromolecular structure viewer bundled as `resources/molstar/`.

| | |
| --- | --- |
| Identifier | <https://molstar.org/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | MIT |
| Bundled at | `src/openchem/resources/molstar` |
| Third-party files | `molstar.js`, `molstar.css`, `favicon.ico` |
| Licence files | `LICENSE` |
| Ours, in the same place | `viewer.html` |

Licence verified: the bundled `LICENSE` opens "The MIT License".

NO VERSION IS RECORDED, DELIBERATELY, and the obvious probe returns a
plausible wrong answer: grepping `molstar.js` for a version yields
`18.3.1`, which is REACT's version inside the bundle, not Mol*'s. Shipping
that number would look authoritative and come from the wrong library.

`viewer.html` here is ours, adapted from the upstream package's
`build/viewer/embedded.html`.

### threedmol

<a id="threedmol"></a>

> 3Dmol.js, the WebGL molecular viewer bundled as `resources/viewer3d/3Dmol-min.js`.

| | |
| --- | --- |
| Identifier | <https://3dmol.csb.pitt.edu/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | BSD-3-Clause |
| Bundled at | `src/openchem/resources/viewer3d` |
| Third-party files | `3Dmol-min.js` |
| Licence files | `3Dmol-LICENSE.txt` |
| Ours, in the same place | `viewer.html` |

Licence verified from the bundled text, which is also where a SECOND
bundling case turns up: it opens "3Dmol.js incorporates code from GLmol,
Three.js, and jQuery and is licensed under a BSD-3-Clause license." So the
same caveat as [source:ketcher] applies here -- the licence covers 3Dmol's
own code and names three further projects inside it. Unlike Ketcher's, this
one at least SAYS so in the file we ship.

A MIXED DIRECTORY, which is why the licence guard is file-level rather than
directory-level. `3Dmol-min.js` and `3Dmol-LICENSE.txt` are theirs;
`viewer.html` is entirely ours -- it carries this project's own gallery
overlay, `createViewerGrid` handling and `drawnGridShapes` diagnostics.

No version is recoverable: the minified header carries only a licence
pointer.

### iupac_namer

<a id="iupac_namer"></a>

> open-iupac-namer, vendored under `src/openchem/vendor/iupac_namer/` -- the offline deterministic structure-to-name engine.

| | |
| --- | --- |
| Identifier | <https://github.com/leehiufung911/open-iupac-namer> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | MIT |
| Version | `c3eac17ffd110c7c5dd37aaad2955e06cf8c9303` |
| Version source | `src/openchem/vendor/VENDORING.md` |
| Bundled at | `src/openchem/vendor` |
| Third-party files | `iupac_namer/**`, `data/**`, `docs/**` |
| Licence files | `LICENSE.open-iupac-namer` |
| Ours, in the same place | `__init__.py`, `VENDORING.md`, `CHANGELOG.md`, `BENCHMARK_HISTORY.md`, `KNOWN_LIMITATIONS.md` |

THE IDENTIFIER POINTED AT THE WRONG REPOSITORY until it was checked --
this project's own URL rather than the upstream it was vendored from.
`VENDORING.md` names the real one and the exact commit, which is now the
`version`; upstream is abandoned (three commits, all 2026-05-24), so a
pinned commit is the only thing there is to cite. Licence verified from the
vendored file: "MIT License, Copyright (c) 2026 leehiufung911".

Implements [source:iupac2013]. Carries its own ~3,200-test suite under
`tests/vendor/`, excluded from the default run and expected at
`3209 passed` -- which needs JAVA_HOME set, not merely java on PATH.
Scored by the naming benchmark at 181/181.

### rdkit

<a id="rdkit"></a>

> RDKit: Open-source cheminformatics.

| | |
| --- | --- |
| Identifier | <https://www.rdkit.org/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | BSD-3-Clause |
| Version | `>=2024.3.1` |
| Package | `rdkit` |
| Version source | `pyproject.toml` |

LICENCE VERIFIED from the installed distribution's own metadata
(`importlib.metadata`: BSD-3-Clause). The VERSION is still a constraint,
not a resolved version. `pyproject.toml` declares `>=`, and
`uv.lock` records only the reference environment's resolution -- a user
installing from PyPI gets whatever satisfies the constraint. Recording the
constraint is the honest thing available.

Two library behaviours this project has had to measure rather than read:
`DoubleCubicLatticeVolume` defaults to a 1.4 A probe radius and so returns
a SOLVENT-ACCESSIBLE volume unless told otherwise (wrong by 700% on
helium), and `Conformer.Is3D()` follows the molblock HEADER rather than the
coordinates.

### openbabel

<a id="openbabel"></a>

> Open Babel: An open chemical toolbox.

| | |
| --- | --- |
| Identifier | <https://openbabel.org/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | GPL-2.0 |
| Version | `>=3.1.1.23` |
| Package | `openbabel-wheel` |
| Version source | `pyproject.toml` |

Optional (`--extra openbabel`), and THE REASON THIS PROJECT IS GPL.

Its mmCIF reader diverges from its PDB reader in three measured ways, two
fixed here and one open: it matches `_atom_site.type_symbol` CASE-SENSITIVELY
against its element table, so the uppercase `CL`/`ZN`/`SE` the PDB archive
writes come back as atomic number 0 and the atom is then DELETED rather
than mistyped; `_single_copy` picked a different ligand copy per format;
and it leaves every implicit hydrogen count at zero from mmCIF. The parity
sweep went 0 of 48 receptors to 38 of 48.

### pyside6

<a id="pyside6"></a>

> Qt for Python (PySide6).

| | |
| --- | --- |
| Identifier | <https://doc.qt.io/qtforpython/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0 |
| Version | `>=6.7` |
| Package | `pyside6` |
| Version source | `pyproject.toml` |

THE LICENCE IS A DISJUNCTION, NOT PLAIN LGPL, and this entry said "LGPL-3.0"
until the installed metadata was read: PySide6 declares
"LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0". Which arm applies is a choice
the distributor makes, so flattening it loses the fact that there is a
choice. The version is still a constraint -- see [source:rdkit].

### opsin

<a id="opsin"></a>

> OPSIN: Open Parser for Systematic IUPAC Nomenclature, reached through the `py2opsin` wrapper, which bundles OPSIN's jar.

| | |
| --- | --- |
| Identifier | <https://github.com/dan2097/opsin> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | MIT |
| Version | `>=1.2.0` |
| Package | `py2opsin` |
| Version source | `pyproject.toml` |

Name-to-structure, and the arbiter of the naming benchmark: 181 molecules
scored by OPSIN ROUND TRIP rather than string equality. It shells out to a
bare `java`, so the JRE is the real requirement ([source:adoptium_temurin])
and the import stays guarded regardless.

### adoptium_temurin

<a id="adoptium_temurin"></a>

> Eclipse Temurin JRE, fetched from the Adoptium API on demand.

| | |
| --- | --- |
| Identifier | <https://api.adoptium.net/> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Licence | GPL-2.0 with Classpath Exception (OpenJDK runtime); Apache-2.0 for Adoptium build scripts |
| Version source | `src/openchem/services/java_setup.py` |

Downloaded by the app so OPSIN ([source:opsin]) can run without a system
Java. Licensing read from adoptium.net: the OpenJDK code carries GPL v2
with Classpath Exception (and Assembly Exception), while Adoptium's own
build scripts and infrastructure are Apache-2.0. **It is the runtime that
ships**, so the Classpath Exception is the operative term.

### autodock_vina

<a id="autodock_vina"></a>

> J. Eberhardt, D. Santos-Martins, A. F. Tillack & S. Forli, 'AutoDock Vina 1.2.0: New Docking Methods, Expanded Force Field, and Python Bindings', J. Chem. Inf. Model. 2021; with O. Trott & A. J. Olson, J. Comput. Chem. 2010, 31(2), 455-461 for the original.

| | |
| --- | --- |
| Identifier | <https://github.com/ccsb-scripps/AutoDock-Vina> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Licence | Apache-2.0 |
| Version source | `src/openchem/services/tool_download_service.py` |

Licence and both citations read from the project's own repository, which
asks for the 1.2.0 paper (doi 10.1021/acs.jcim.1c00203) and the original
(doi 10.1002/jcc.21334) together.

Optional and separately installed. THE SHIPPED PROVIDER PASSES `seed=None`,
so Vina runs with a random seed and two runs of the same receptor already
differ -- any A/B on a receptor change is measuring the search wandering
until the seed is pinned, and pinning alone is not enough without measuring
the same-receptor spread as a control.

This entry stays `citation` rather than `citation_and_claim`: it records
the SOFTWARE, and no number here comes from it. The scoring-function error
the pose table quotes belongs to the original paper and is verified
separately at [source:trott_olson2010].

### orca

<a id="orca"></a>

> F. Neese, 'Software Update: The ORCA Program System - Version 6.0', WIREs Computational Molecular Science 2025.

| | |
| --- | --- |
| Identifier | [10.1002/wcms.70019](https://doi.org/10.1002/wcms.70019) |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Licence | proprietary, free for academic use -- installed by the user, never redistributed |
| Version source | `src/openchem/services/tool_download_service.py` |
| Local copy | `WIREs Comput Mol Sci - 2025 - Neese - Software Update The ORCA Program System Version 6 0.pdf` (not checked) |

Confirmed from the paper: "Wiley Interdisciplinary Reviews: Computational
Molecular Science, 2025; 15:e70019", SOFTWARE FOCUS, **OPEN ACCESS** -- so
the citation for the program is freely readable even though the program is
not freely licensed for commercial use.

**VERSION 6 IS THE RIGHT PAPER**, because CLAUDE.md records this project's
measurements on ORCA 6.1.1. The Version 5.0 paper is WIREs Comput. Mol.
Sci. 2022, 12, e1606, doi 10.1002/wcms.1606, if both are ever wanted.

Licence terms are from faccts.de directly: "ORCA is free for academic use,
while commercial licenses are available through FACCTs". THE SITE NAMES NO
PUBLICATION and points at the manual instead, so the citation came from the
publisher rather than from the vendor -- the same shape as
[source:nmrshiftdb2], where the project's own pages were the one place the
reference could not be found.

Optional, user-installed, and never bundled. Two invocation traps measured
here: it ABORTS AT STARTUP if its own path uses forward slashes (it derives
its helper-binary directory from the path it was invoked with), and it must
not be installed under a path containing spaces. A working probe does not
clear the path -- a TD-DFT single point ran fine through a forward-slash
path minutes before `Opt` died on it.

### pkasolver

<a id="pkasolver"></a>

> pkasolver -- 'Improving Small Molecule pKa Prediction Using Transfer Learning with Graph Neural Networks', bioRxiv 2022. Author list not established -- see note.

| | |
| --- | --- |
| Identifier | <https://github.com/mayrf/pkasolver> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-17 |
| Licence | MIT |
| Version source | `src/openchem/services/pkasolver_setup.py` |

Licence (MIT) and the preprint it asks to be cited (doi
10.1101/2022.01.20.476787) read from the repository. **The author list is
not on that page and is not recorded here.**

Worth knowing from the same page: the repository states that Schrodinger's
Epik licensing prevents distribution of the transfer-learning-trained model
variant the paper describes -- so the shipped model is not the paper's best
one.

Optional sidecar. It predicts PER-SITE values, which are closer to
microscopic than to macroscopic constants -- the distinction that decides
which ionization formula is right, and that a tolerance would have buried.

### dimorphite_dl

<a id="dimorphite_dl"></a>

> P. J. Ropp, J. C. Kaminsky, S. Yablonski & J. D. Durrant, 'Dimorphite-DL: An open-source program for enumerating the ionization states of drug-like small molecules', J. Cheminform. 2019, 11, 14.

| | |
| --- | --- |
| Identifier | <https://github.com/durrantlab/dimorphite_dl> |
| Status | shipped |
| Verification | citation |
| Verified | 2026-08-16 |
| Licence | Apache-2.0 |
| Version | `>=2.0.2` |
| Package | `dimorphite-dl` |
| Version source | `pyproject.toml` |

Citation and licence read from the project repository
(doi 10.1186/s13321-019-0336-9).

Used for protonation states, NOT for pKa values. It was measured as a pKa
fallback and rejected: it puts propranolol at 5.65 against a real 9.42, off
by 3.8. That whole design existed only because a probe passed `None` for an
interpreter path and so reported pkasolver as 'not installed' on a machine
where it plainly was.
