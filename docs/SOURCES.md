<!-- GENERATED FROM docs/sources.toml -- do not edit -->
<!-- SOURCE SHA256: 30b439deb8cfb142154a493d9b9cc1de7006d90758768cbb79e5d7cf28683616 -->

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

## Index

| key | kind | status | verification |
| --- | --- | --- | --- |
| [`abraham_predicted_solvents`](#abraham_predicted_solvents) | reference_table | **not shipped** | citation + claim |
| [`adoptium_temurin`](#adoptium_temurin) | software | shipped | unverified |
| [`allred1961`](#allred1961) | reference_table | shipped | unverified |
| [`aqsoldb`](#aqsoldb) | dataset | shipped | unverified |
| [`autodock_vina`](#autodock_vina) | software | shipped | unverified |
| [`avdeef2007`](#avdeef2007) | literature | shipped | citation + claim |
| [`avdeef2020`](#avdeef2020) | literature | shipped | citation + claim |
| [`bolovinos1984`](#bolovinos1984) | literature | shipped | citation + claim |
| [`bradley2014`](#bradley2014) | dataset | shipped | citation + claim |
| [`bradley2015`](#bradley2015) | literature | shipped | citation + claim |
| [`bravetti2023`](#bravetti2023) | literature | shipped | citation |
| [`cod`](#cod) | dataset | shipped | citation |
| [`crc_handbook`](#crc_handbook) | reference_table | shipped | unverified |
| [`cwc_annex_on_chemicals`](#cwc_annex_on_chemicals) | legal | shipped | citation + claim |
| [`dea_listed_chemicals`](#dea_listed_chemicals) | legal | shipped | citation |
| [`delaney2004`](#delaney2004) | literature | shipped | citation + claim |
| [`dimorphite_dl`](#dimorphite_dl) | software | shipped | citation |
| [`drago1965`](#drago1965) | literature | shipped | citation + claim |
| [`drago1992`](#drago1992) | literature | shipped | unverified |
| [`gutmann_frontiers2022`](#gutmann_frontiers2022) | literature | **not shipped** | unverified |
| [`hlb`](#hlb) | reference_table | **not shipped** | unverified |
| [`ich_m9`](#ich_m9) | standard | shipped | unverified |
| [`iupac2013`](#iupac2013) | standard | shipped | citation |
| [`iupac_namer`](#iupac_namer) | software | shipped | citation |
| [`jenkins1999`](#jenkins1999) | literature | shipped | citation + claim |
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
| [`nmrshiftdb2`](#nmrshiftdb2) | dataset | shipped | unverified |
| [`ons_solubility`](#ons_solubility) | dataset | shipped | citation |
| [`openbabel`](#openbabel) | software | shipped | citation |
| [`opsin`](#opsin) | software | shipped | citation |
| [`orca`](#orca) | software | shipped | unverified |
| [`parr_pearson1983`](#parr_pearson1983) | literature | shipped | citation |
| [`pearson1988`](#pearson1988) | literature | shipped | citation + claim |
| [`pkasolver`](#pkasolver) | software | shipped | unverified |
| [`platts1999`](#platts1999) | literature | **not shipped** | citation + claim |
| [`pyside6`](#pyside6) | software | shipped | citation |
| [`rcsb_pdb`](#rcsb_pdb) | dataset | shipped | citation |
| [`rdkit`](#rdkit) | software | shipped | citation |
| [`sci_downloads_note`](#sci_downloads_note) | reference_table | reference only | citation |
| [`shannon1976`](#shannon1976) | literature | shipped | citation + claim |
| [`tdc_admet`](#tdc_admet) | dataset | reference only | unverified |
| [`threedmol`](#threedmol) | software | shipped | citation |
| [`tsei`](#tsei) | reference_table | **not shipped** | unverified |
| [`vogel_drago1996`](#vogel_drago1996) | literature | shipped | unverified |

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

> Vogel & Drago, J. Chem. Educ. 1996, 73, 701. Title not established -- see note.

| | |
| --- | --- |
| Identifier | J. Chem. Educ. 1996, 73, 701 |
| Status | shipped |
| Verification | unverified |
| Used by | `src/openchem/chem/data/lewis_parameters.json` |

THE PRIMARY SOURCE OF THE SHIPPED E/C VALUES, AND THIS PROJECT HAS NEVER
SEEN IT. `lewis_parameters.json` says the numbers came "via the Wikipedia
ECW model compilation of Vogel & Drago" -- so the chain is
Wikipedia -> this repo -> here, and no step of it touched the paper. That
is why it is `unverified`, why it is recorded separately from
[source:drago1965] rather than folded into it, and why the title is left
blank: one was briefly added here from memory and removed.

It is the weakest link in the Lewis chain and worth closing: the shipped
E/C table is only as good as a compilation nobody here has checked against
its source. The eight measured enthalpies it reproduces to 0.27 kcal/mol
(`test_the_shipped_table_reproduces_the_measured_enthalpies`) are what
currently stands in for that check.

### drago1992

<a id="drago1992"></a>

> R. S. Drago et al., Inorg. Chem. 1992, 32, 2473.

| | |
| --- | --- |
| Identifier | Inorg. Chem. 1992, 32, 2473 |
| Status | shipped |
| Verification | unverified |
| Used by | `src/openchem/chem/data/lewis_parameters.json` |

A supplementary source for the shipped compilation; see [source:vogel_drago1996].

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

> The Gutmann donor/acceptor-number assessment published in Frontiers in Chemistry, 2022. Authors not recorded -- see note.

| | |
| --- | --- |
| Identifier | [10.3389/fchem.2022.861379](https://doi.org/10.3389/fchem.2022.861379) |
| Status | **not shipped** |
| Verification | unverified |
| Used by | `CLAUDE.md` |

**Why it is not shipped.** The accessible source tabulates ionic liquids and deep eutectic solvents
rather than the classical molecular table, and reports its own
acceptor-number model failing outright ('no correlation could be found'),
concluding it supports 'qualitative and relative criteria but not an
absolute and quantitative model'.

TWO THINGS IN THIS ENTRY WERE INVENTED AND ARE NOW REMOVED. It claimed a
local copy at `kaya2022.pdf` and an author of "S. Kaya et al." Both came
from matching the DOI's year against a filename. `kaya2022.pdf` is a
different paper entirely -- "On the Prediction of Lattice Energy with the
Fukui Potential", J. Phys. Chem. A 2022, 126, 4507-4516 -- and searching
every PDF in the archive for the Frontiers DOI or for Gutmann donor numbers
returns NOTHING, so this source is not held locally at all.

What survives is what the repository recorded rather than what was guessed:
the DOI, the venue, and the quoted findings in CLAUDE.md ("no correlation
could be found"; it supports "qualitative and relative criteria but not an
absolute and quantitative model"). Those were read from a web fetch that
cannot be reproduced here, which is exactly why this is `unverified` rather
than trusted.

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

### aqsoldb

<a id="aqsoldb"></a>

> Sorkun, Khetan & Er, Scientific Data 2019. Title, volume and pages not established -- see note.

| | |
| --- | --- |
| Identifier | <https://github.com/mcsorkun/AqSolDB> |
| Status | shipped |
| Verification | unverified |
| Used by | `benchmarks/solubility/fetch.py`, `benchmarks/solubility/README.md` |

THE CITATION IS EXACTLY WHAT THE REPOSITORY CARRIES AND NO MORE.
`benchmarks/solubility/README.md` says "Sorkun, Khetan & Er, Scientific
Data 2019"; a title and a volume/page were briefly added here from memory
and have been removed, because that is the same invention that put a
different paper's title on [source:avdeef2020]. The GitHub URL is the
identifier because it is the thing this project actually fetches from.

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

> nmrshiftdb2, an open-access NMR database (SourceForge distribution).

| | |
| --- | --- |
| Identifier | <https://sourceforge.net/projects/nmrshiftdb2/> |
| Status | shipped |
| Verification | unverified |
| Used by | `src/openchem/services/nmr_database_setup.py`, `src/openchem/chem/nmr_database.py`, `src/openchem/chem/hose_codes.py` |

Downloaded on demand (~152 MB), indexed, then the download is discarded.
IT IS THE HOSE-CODE LOOKUP'S OWN INDEX, so it is circular as ground truth
and nothing is scored against it -- see [source:kwon2023], which exists for
that reason.

### tdc_admet

<a id="tdc_admet"></a>

> Therapeutics Data Commons (TDC) ADMET benchmark group.

| | |
| --- | --- |
| Identifier | <https://tdcommons.ai/> |
| Status | reference only |
| Verification | unverified |
| Used by | `benchmarks/admet/README.md`, `README.md` |

**Why it is reference only.** Named as the shipped ADMET sidecar's training set so its accuracy figures
can be read correctly -- they are the vendor's held-out numbers, not ours,
and the model trained on all of TDC. Nothing here is scored against it.

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

> ICH M9, the guideline defining BCS-based biowaivers. Full title not verified against the guideline itself.

| | |
| --- | --- |
| Identifier | ICH M9 |
| Status | shipped |
| Verification | unverified |
| Used by | `src/openchem/chem/solubility.py` |

Defines the pH 1.2-6.8 window and the dose/solubility criterion the BCS
screen applies. IT IS DEFINED ON AQUEOUS MEDIA, which is why the screen,
the pH curve and the Henderson-Hasselbalch adjustment are all water-only
and a non-aqueous solvent gets `NON_AQUEOUS_SOLVENT` rather than an
authoritative-looking number.

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

> A. L. Allred, J. Inorg. Nucl. Chem. 17 (1961) 215-221. Title not established -- see note.

| | |
| --- | --- |
| Identifier | J. Inorg. Nucl. Chem. 1961, 17, 215-221 |
| Status | shipped |
| Verification | unverified |
| Used by | `src/openchem/chem/data/electronegativity.json` |

THE TITLE IS NOT RECORDED, DELIBERATELY. `electronegativity.json` cites
this as "A. L. Allred, J. Inorg. Nucl. Chem. 17 (1961) 215-221" and nothing
more; a title was briefly added here from memory and removed.

Pauling's original values as revised by Allred -- the set reproduced in the
CRC Handbook ([source:crc_handbook]) and in IUPAC's tables. The NUMBERS are
a standard published table reproduced rather than derived; what this project
measured is the ALGORITHM consuming them, in `tests/test_oxidation_states.py`.

He, Ne and Ar have no accepted Pauling value and are ABSENT. An absent
element is a refusal, never a guess.

### crc_handbook

<a id="crc_handbook"></a>

> CRC Handbook of Chemistry and Physics.

| | |
| --- | --- |
| Identifier | CRC Handbook of Chemistry and Physics (edition not recorded) |
| Status | shipped |
| Verification | unverified |
| Used by | `src/openchem/chem/data/electronegativity.json`, `src/openchem/chem/lattice_energy.py` |

Two uses: it reproduces the Allred-revised Pauling electronegativities
([source:allred1961]), and its lattice-energy column is the TARGET the
volume-based correlation was validated against ([source:jenkins1999]).

THE EDITION IS NOT RECORDED ANYWHERE IN THIS REPO, which is a real gap for
a reference table -- values do move between editions. Recorded as the gap
it is rather than guessed at.

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
| Licence files | `LICENSE` |

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

AND `dist/` IS A BUNDLE, NOT A LIBRARY -- AN OPEN GAP, RECORDED RATHER THAN
CLOSED. It contains third-party code beyond Ketcher itself: EPAM's Miew
0.11.1 is proven by its surviving banner, three.js by its constants. The
build tree resolves 430 packages (340 MIT, 46 ISC, 15 Apache-2.0, 11
"Apache-2.0 AND MIT", 6 BSD-3-Clause, 5 BlueOak-1.0.0, 1 CC-BY-4.0, 2
undeclared), though only the runtime subset is actually bundled.

Their notices are NOT recoverable from the artifact: the build strips
comments even with minification off -- exactly two licence banners survive
in 35 MB -- so an accurate list would have to be produced at build time
from `package-lock.json`, which is not done. Registering Ketcher's own
Apache-2.0 licence is necessary and not sufficient, and the licence guard
proves declaration rather than compatibility.

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
| Verification | unverified |
| Licence | GPL-2.0-with-classpath-exception |
| Version source | `src/openchem/services/java_setup.py` |

Downloaded by the app so OPSIN ([source:opsin]) can run without a system Java.

### autodock_vina

<a id="autodock_vina"></a>

> AutoDock Vina, Center for Computational Structural Biology (Scripps).

| | |
| --- | --- |
| Identifier | <https://github.com/ccsb-scripps/AutoDock-Vina> |
| Status | shipped |
| Verification | unverified |
| Licence | Apache-2.0 |
| Version source | `src/openchem/services/tool_download_service.py` |

Optional and separately installed. THE SHIPPED PROVIDER PASSES `seed=None`,
so Vina runs with a random seed and two runs of the same receptor already
differ -- any A/B on a receptor change is measuring the search wandering
until the seed is pinned, and pinning alone is not enough without measuring
the same-receptor spread as a control.

### orca

<a id="orca"></a>

> ORCA quantum chemistry program, FACCTs / MPI fur Kohlenforschung.

| | |
| --- | --- |
| Identifier | <https://www.faccts.de/> |
| Status | shipped |
| Verification | unverified |
| Licence | proprietary, free for academic use -- installed by the user, never redistributed |
| Version source | `src/openchem/services/tool_download_service.py` |

Optional, user-installed, and never bundled. Two invocation traps measured
here: it ABORTS AT STARTUP if its own path uses forward slashes (it derives
its helper-binary directory from the path it was invoked with), and it must
not be installed under a path containing spaces. A working probe does not
clear the path -- a TD-DFT single point ran fine through a forward-slash
path minutes before `Opt` died on it.

### pkasolver

<a id="pkasolver"></a>

> pkasolver, a graph-neural-network pKa predictor.

| | |
| --- | --- |
| Identifier | <https://github.com/mayrf/pkasolver> |
| Status | shipped |
| Verification | unverified |
| Licence | MIT |
| Version source | `src/openchem/services/pkasolver_setup.py` |

Optional sidecar. It predicts PER-SITE values, which are closer to
microscopic than to macroscopic constants -- the distinction that decides
which ionization formula is right, and that a tolerance would have buried.

### dimorphite_dl

<a id="dimorphite_dl"></a>

> Dimorphite-DL, a rule-based protonation-state enumerator.

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

Used for protonation states, NOT for pKa values. It was measured as a pKa
fallback and rejected: it puts propranolol at 5.65 against a real 9.42, off
by 3.8. That whole design existed only because a probe passed `None` for an
interpreter path and so reported pkasolver as 'not installed' on a machine
where it plainly was.
