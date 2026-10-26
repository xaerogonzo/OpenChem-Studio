# PETN and the nitrate-ester family: an evidence hunt for Phase B

An inventory, not a score. No corpus was built, no method was run, and no number of `PREREGISTRATION.md` was changed (that file is an unfrozen draft and is not edited here). Every item carries its source, page or table, the value as printed, its `value_kind` (preregistration 3.1), the temperature and form, and whether it is independent of what `INVENTORY.md` already holds. The rows are in `PETN_EVIDENCE.json` (one row per item, ids `A01`... below); the COD rows are in `cod_nitrate_extra.json`; the searches that found them are in section 9.

<!-- cod_nitrate_extra: total=73 outside_window=41 single=52 formulas=64 four_arm=32 -->

**What is committed and what is not.** The preregistration (section 7) keeps per-compound values from copyrighted tables out of the repository. Rows from books, handbooks and journal articles therefore carry their locator, kind and lineage here and `"value": null`; the values themselves are in the maintainer's notes folder (`petn-evidence/petn_evidence_rows_full.json`). Values are printed in this file and in the JSON only where the source is public data (the NIST Chemistry WebBook, the Crystallography Open Database), a US Government document, an open-access text, or this inventory's own arithmetic.

## 1. What would move the conditions

`PREREGISTRATION.md` 12.1 and `docs/ROADMAP.md` (recorded 2026-10-05):

* **R1** is met by one verified row (value kind `measured`, phase `gas`, a primary locator read on the page, a different identity block from PETN) of a compound matching `[CX4;H0]([CH2][!#1])([CH2][!#1])([CH2][!#1])[CH2][!#1]` with four identical arms, plus the owner's approval (D8).
* **R2** needs the ORCA route to pass the P2 gate scoped to nitramines on at least 30 paired verified holdout nitramines (about 150 verified entities, section 5) and the PETN class refused by a coded limit.
* Any family claim needs about 150 verified entities in the family (section 5). The nitrate-ester family is the one this file counts.

## 2. Findings in brief

| # | finding | where |
|---|---|---|
| 1 | PETN has **no experimental gas-phase enthalpy of formation**; its gas value is a solid value plus an effusion sublimation value, **-388.1 +/- 1.5 kJ/mol** (`derived_from_measured`), and the one JPCRD reference table says none is known. | A01, A04, A07, A08 |
| 2 | So PETN itself is a **well-pinned derived gas-phase point** (+/- 2 kJ/mol), not a gap. If the repository's combined route used Keshavarz's PETN sublimation value of 138.0 kJ/mol (the number `docs/research/literature.toml` records for the APC route; the ORCA route's leg must be checked), about **12 of the recorded 59.5 kJ/mol PETN miss is the sublimation leg**, whose measured value is 150.4 +/- 1.3. | section 3.4 |
| 3 | **Pentaerythritol** is the only compound found that matches the R1 pattern with oxygen arms and a measured condensed enthalpy (-920.5 +/- 2.8, Medard and Thomas 1954) and sublimation enthalpies. Its gas value is `derived_from_measured` only, and the sublimation rows span 96 to 163 kJ/mol across polymorphs (about +/- 16 kJ/mol on the gas value). Under R1 as written it **does not qualify** (kind, not `measured` gas). | B01-B04 |
| 4 | The **R1 pattern is matched by a hydrocarbon** (3,3-diethylpentane) as well as by PETN and pentaerythritol, so the owner's approval does all the selecting; the rule's text should name the arms or list the approved compounds. A test pins this. | B05 |
| 5 | No measured formation enthalpy exists for any other C(CH2X)4 compound with X a heteroatom (tetrabromide, tetrachloride, tetraacetate: NIST has none; Acree 2010 has none). The only other four-arm quaternary carbons found are the **tetranitramine** (density only; COD 7105119 and a pycnometer value) and the **phosphorus-containing pentaerythrityl-type entries** in COD. | B06, D05, COD |
| 6 | **Nitrate-ester family**: NIST holds measured (calorimetric) formation enthalpies for 12 nitrate esters (one gas-phase, nitroglycerin, derived from a liquid value and a measured vaporization enthalpy; one directly, methyl nitrate). Klapoetke's Encyclopedia reprints several of them digit for digit, so books do **not** verify them. | C01-C11 |
| 7 | COD holds **73 nitrate-ester entries** (32 in the census window, **41 outside it**: low-temperature and no-temperature structures the census could not see), 52 of them single-component, in **64 distinct formulas**. PETN has **3** entries (100 K; and two cells with no temperature in the header, PETN-I 1947 and PETN-II 1975). | section 6 |
| 8 | Several items are **label traps** worth a regression fixture: Lease 2023 Table 1 prints PETN's 1.845 g/cm3 with a blank temperature while COD says 100 K and its derivatives were at about 296 K; NIST's EGDN sublimation row is probably dithiooxamide's (Acree p. 44 prints one CAS number for both); TEGDN is a liquid that two books print as a "solid" enthalpy. | section 7 |
| 9 | Everything above is **an order of magnitude short of 150 verified entities** for the nitrate-ester family, in every property. | section 10 |

## 3. PETN itself

### 3.1 Crystal density, with temperature and form

| id | value as printed | kind | T and form | source and locator | independent? |
|---|---|---|---|---|---|
| A15 | **1.845** g/cm3 | measured (CIF) | 100(1) K, PETN-I, R = 0.0104 | COD 4111071, Zhurova et al., J. Am. Chem. Soc. 128 (2006) 14728 (author, journal, volume, page read from the public CIF) | yes; **the same observation is printed by Lease 2023 Table 1 (A18, T blank) and cited by Stark 2022 p. 66 (100 K)** |
| A16 | 1.781 (computed here from the CIF's cell and Z) | derived | PETN-I, temperature not in the CIF | COD 5900023, Booth and Llewellyn, J. Chem. Soc. 1947, 837 | yes (not in the inventory) |
| A17 | 1.7148 (computed here from the CIF's cell and Z) | derived | PETN-II, Pcnb, temperature not in the CIF | COD 5000154, Cady and Larson, Acta Cryst. B31 (1975) 1864 | yes; the Klapoetke table (A13) has a 136 C value for the orthorhombic form within 0.002 of this cell's, probably this cell |
| A13 | a three-row table of crystal density against temperature: PETN-I at 22 C (calculated and experimental) and PETN-II at 136 C (calculated); values withheld | unlabelled | PETN-I / PETN-II | Klapoetke Encyclopedia vol 3, PETN entry, density cell (OCR) | no, same book family; the temperature table is new to the inventory |
| A14 | four books and handbooks print one value each, 1.76 to 1.773 g/cm3, two of them stated at 20 C (values withheld) | unlabelled | form not stated | Meyer p. 251; Akhavan Table 2.14; CRC 97 PDF p. 574; Lange's Sec. 01 PDF p. 291 | no |

The same Klapoetke density cell lists nine further values for PETN, labelled pycnometer, nominal, TMD, pressed and compressed: bulk, pressed and crystal numbers share one cell, as preregistration 3.2 warns. Two PETN polymorphs exist (PETN-I tetragonal, stable to 130 C; PETN-II orthorhombic, 130 C to the melt, mp 142.9 and 143.1 C, Klapoetke vol 3). **For P1 the primary-cohort PETN density is one room-temperature crystal observation family (PETN-I, about 1.76-1.78 g/cm3 across the sources) and one 100 K observation; a second independent root at 273-303 K with a read primary page is not yet in hand.** The room-temperature primary is Cady and Larson 1975 or earlier (the Klapoetke table's reference [21]), not read.

### 3.2 Enthalpy of formation, solid

| id | value as printed | kind | source | lineage |
|---|---|---|---|---|
| A01 | **-538.5 +/- 0.8** kJ/mol, solid, 298.15 K, method Ccb | measured | NIST WebBook, Ornellas, Carpenter et al. 1966 | primary root (paywalled; the Crossref title of the likely paper is *Detonation Calorimeter and Results Obtained with PETN*, Rev. Sci. Instrum. 10.1063/1.1720361, while NIST's method code is Ccb: which method made the row is **unverified**) |
| A03 | -2569.8 +/- 2.5 kJ/mol (combustion), Burlot 1939 | measured | NIST WebBook | a second, older root; the original value was -2594.7 and was reanalysed by Cox and Pilcher 1970 |
| A09 | CRC 97 and Lange's print one value each, within 0.1 kJ/mol of A01 (values withheld) | unlabelled | PDF pp. 897 and 39 | the same upstream as A01 (compilations) |
| A10 | Klapoetke vol 3, one cell: six values spanning 77 kJ/mol after conversion to kJ/mol (values withheld) | unlabelled | PETN entry | two of them equal A01 to 0.1 kJ/mol; **the other numbers are not explained** |
| A11, A12 | Meyer and Akhavan, in kJ/kg, convert to within 0.4 and 6.4 kJ/mol of A01 (values withheld) | unlabelled | printed pp. 251 and 41 | already in `INVENTORY.md` section 5 (spread 8.4 kJ/mol) |

**Verification under preregistration 8.2:** the solid enthalpy is verified in the sense of "one observation carrying a primary-literature measurement with a locator read on the page" only after Ornellas 1966 is read (the owner's to fetch, section 8). Without it, A01 plus A09 and A11 are one lineage.

### 3.3 Sublimation and the derived gas-phase enthalpy

| id | value | kind | source and lineage |
|---|---|---|---|
| A04 | **150.4 +/- 1.3** kJ/mol at 298 K (data 328-405 K, effusion) | measured | NIST WebBook and Acree and Chickos 2010 Table 6 p. 151 (rendered page read); Cundall, Palmer et al. 1978 |
| A05 | 152 +/- 2 kJ/mol (method V) | measured | NIST; Edwards 1953 |
| A06 | Acree prints six rows (one flagged U by the compilers); the five usable span 150.4-156.9 kJ/mol (values withheld except A04) | measured | Acree Table 6 p. 151; five roots |
| A20 | Lange's Sec. 06 PDF p. 74 prints one value, within 1.5 kJ/mol of A04 (withheld) | unlabelled | a compilation of A06's last row |
| A07 | **-388.1 +/- 1.5** kJ/mol gas, 298 K (A01 + A04) | derived_from_measured | this inventory |
| A08 | Burcat 1999 uses the Cox and Pilcher gas value, within 1.1 kJ/mol of A07 (value withheld); its section 3.25 says no experimental value is known | unlabelled | Burcat, J. Phys. Chem. Ref. Data 28 (1999) 63, Table 52, printed p. 118 (rendered page read) |

PETN has therefore a derived gas-phase enthalpy known to about 2 kJ/mol, and **no measured gas-phase enthalpy**. R1 requires `measured`, so it cannot be met by PETN or by any compound whose gas value is solid-plus-sublimation.

### 3.4 What this does to the repository's recorded PETN miss

`benchmarks/thermophysical/orca_atom_equivalents.py` records the 6-fit PETN solid value -479.5 against a measured -539.0 (59.5 kJ/mol), and `docs/research/literature.toml` records, for the APC route, gas -344.0 with Keshavarz's sublimation 138.0. **If** the ORCA route's sublimation leg for PETN was also 138.0, its implied gas value is -341.5, against the derived -388.1: a **gas-phase miss of about 47 kJ/mol**, and 12.4 kJ/mol of the recorded miss is the sublimation leg (138.0 against a measured 150.4 +/- 1.3). The gas-phase miss is the quantity R1 would test. This is arithmetic on recorded numbers; which sublimation value the ORCA route used is not confirmed here.

## 4. R1: four-arm quaternary carbons

| id | compound | what exists | kind |
|---|---|---|---|
| B01 | pentaerythritol | ΔfH(solid) -920.5 +/- 2.8 kJ/mol, Ccb, Medard and Thomas 1954 (NIST) | measured |
| B02, B03 | pentaerythritol | sublimation: 163.0 kJ/mol (298 K, NIST, Barone 1990) and seven rows in Acree p. 177 spanning 96 to 163 kJ/mol over crystalline, plastic and tetragonal forms (values withheld except NIST's) | measured, polymorph-dependent |
| B04 | pentaerythritol | the CRC gas column (derived: solid plus one sublimation row) and a range of about -757 to -789 kJ/mol by B01 + the usable B03 rows (this inventory's arithmetic) | derived_from_measured |
| B05 | 3,3-diethylpentane | ΔfH(liquid) -275.4 (NIST, from ΔcH -6124.5 +/- 1.6, Johnson, Prosen et al. 1947) | derived_from_measured |
| B06 | tetrabromide, tetrachloride, tetraacetate | none found | - |
| B07 | pentaerythritol trinitrate | one condensed value in two units from two references that convert to within 0.2 kJ/mol (Klapoetke vol 3; values withheld) | unlabelled |

* **Pentaerythritol is the only candidate.** Its structure matches the R1 pattern with four identical hydroxyl arms. A gas value exists only as `derived_from_measured` (kind), with a polymorph spread of about +/- 16 kJ/mol on the sublimation leg. R1 as written needs `measured`, phase `gas`; it is **not met**, and it could be met only by an amendment that admits `derived_from_measured` for this compound or by a new measurement.
* The **R1 pattern is not selective.** `tests/test_energetics_props_petn_evidence.py` shows that 3,3-diethylpentane, with measured combustion data, matches it. The owner's D8 approval is the real selector; the rule's text should say "four identical heteroatom-bearing arms" or list the approved compounds.
* The nearest nitrate-bearing neighbours are PETriN (three nitrate arms and one hydroxyl; condensed enthalpy only; B07) and the **metriol trinitrate** that the repository already predicts well; no gas-phase value of either exists. For three-arm nitrate esters the only gas-phase value is nitroglycerin's, derived: **-279.1 +/- 2.7 kJ/mol** (liquid enthalpy -371.1 +/- 1.7, Miroshnichenko 1988, plus a measured vaporization 92.0 +/- 2.1), and methyl nitrate's, **-122 +/- 1 kJ/mol** (NIST, method Cm, Ray and Ogg 1959). NIST's gas value for ethyl nitrate is **-155 +/- 3** (Eqk, Gray et al. 1956); the Encyclopedia prints -122 +/- 1.3 for ethyl nitrate's gas phase, the digits of methyl nitrate's value (a probable mix-up, section 7 item 10).

## 5. The nitrate-ester family, measured thermochemistry

NIST WebBook rows (public data; ids C01-C10, values in the JSON): nitroglycerin (five liquid rows from -353.9 to -375, one gas), diethylene glycol dinitrate (liquid and solid), metriol trinitrate (solid), 1,2,4-butanetriol trinitrate (liquid), propylene glycol dinitrate (solid, -296.9 +/- 9.3), triethylene glycol dinitrate (two solid rows, -656.9 and -603.8: 53 kJ/mol apart), methyl, ethyl, propyl and isopropyl nitrate, ethylene glycol dinitrate (liquid), and PETN. That is **12 compounds**, plus erythritol tetranitrate and mannitol hexanitrate, which NIST does not hold and whose measured basis is Oxley 2012 and unnamed references in the Encyclopedia (C12, C13).

* **Lineage collapse (C11).** The Encyclopedia's printed enthalpies for TEGDN (-656.9 and -603.8), metriol trinitrate (-450.2), ethyl nitrate (-190.4 liquid), nitroglycerin (-371) are the NIST digits. They do not verify NIST, and two of them print "solid" for liquids.
* **A label to watch:** Klapoetke's property tables also print "exptl." beside values that come from a fit table (the ethriol trinitrate, ethylene glycol dinitrate, glycerol dinitrate, mannitol hexanitrate, metriol trinitrate and methyl nitrate entries each carry an "exptl." and one or two "calcd." numbers from one reference), so "exptl." is not a `measured` tag by itself.
* **Fit tables, not data.** Several nitrate-ester values in the entries are the training sets of the Keshavarz-type methods (preregistration 10.2) and are not independent of them.
* **Open items found:** a measured solid enthalpy for a non-four-arm tetranitrate, -371 kJ/mol by bomb calorimetry, and a 1.917 g/cm3 X-ray density (US 8,324,421 B2; the paper, Angew. Chem. 47 (2008) 8307, is not read; C14, D07). Xylitol pentanitrate: density 1.852 at 150 K measured, enthalpy calculated (Stark thesis, D04, C15). Four PETN derivatives of Benz 2023 (CC BY): densities at 293, 123, 110 and 123 K, enthalpies calculated (D06).

## 6. The COD

The census (`cod_census_structures.json`) classified the 55,674 organic entries with nitrogen, a diffraction density, 273-303 K and no pressure, and found 32 nitrate-ester entries. That window is the **crystal-density** cohort; it hides every low-temperature structure of a nitrate ester (the modern norm), any pressure study (none was found), and every entry with no density or temperature in the header, which includes **both PETN cells that are not at 100 K**.

`inventory_scripts/cod_nitrate_ester_pass.py` takes the 39,625 organic C/N/O (O at least 3) entries the census skipped, plus the C5 entries that could hold a pentaerythrityl core, streams the archive once (as a stream, never unpacked: 91 minutes here) and records the nitrate-ester group by the same bond-order-free pattern and a four-identical-arm test. A density the header lacks is computed from the CIF's own cell. `inventory_scripts/cod_nitrate_ester_report.py` writes the rows. The counts:

| | entries | single-component | distinct formulas (floor) |
|---|---|---|---|
| nitrate esters, inside the census window | 32 | | |
| nitrate esters, **outside** it | 41 | | |
| **nitrate esters, total** | **73** | **52** | **64** (45 single-component) |
| entries with four identical one-atom arms on a quaternary carbon | 32 | | |

Entries are not compounds (repeat determinations, polymorphs and one paper's series of derivatives all count); the formula figure is a floor. A group present is not an energetic material.

The 41 nitrate-ester entries outside the census window (all have no stated pressure; the T column is the CIF's, never inferred):

| COD | formula (header) | T (K) | density (g/cm3) | component class | year |
|---|---|---|---|---|---|
| 2214848 | C10 H14 N4 O8 | 100 | 1.488 | single | 2007 |
| 1569020 | C10 H15 I2 N6 O18 | 305 | 2.158 | multi | 2023 |
| 2209166 | C10 H15 N3 O13 | 306 | 1.537 | single | 2006 |
| 1569021 | C10 H16 Cl6 N2 O6 | 250 | 1.657 | single | 2023 |
| 8104881 | C10 H16 N6 O19 | 170 | 1.683 | single | 2021 |
| 7155051 | C14 H18 N2 O6 | 120 | 1.426 | single | 2016 |
| 7156211 | C14 H19 N O12 | 100 | 1.467 | single | 2018 |
| 4111921 | C140 H151 N17 O18 | 153 | 1.241 | unknown | 2005 |
| 7712385 | C16 H12 N6 O14 | 100 | 1.697 | single | 2023 |
| 7152648 | C16 H15 N O9 | 173 | 1.544 | single | 2012 |
| 7118284 | C2 H2 N4 O12 | 173 | 1.991 | single | 2016 |
| 4519170 | C21 H18 F7 N3 O5 | 193 | 1.56 | unknown | 2021 |
| 4126601 | C23 H15 Br N2 O8 | 110 | 1.795 | single | 2017 |
| 2221931 | C23 H33 N O8 | 223 | 1.288 | single | 2009 |
| 4029117 | C25 H29 N3 O9 | 113 | 1.366 | unknown | 2014 |
| 1569431 | C26 H27 N2 O9 | 100.15 | 1.359 | multi | 2023 |
| 7118766 | C28 H47 N3 O6 | 130 | 1.22 | unknown | 2016 |
| 7059603 | C3 H3 N5 O5 | 151.88 | 1.787 | single | 2020 |
| 7059604 | C3 H3 N7 O3 | 150.18 | 1.769 | single | 2020 |
| 7127940 | C3 H4 N2 O7 | 107 | 1.8 | single | 2021 |
| 7707740 | C3 H5 N5 O3 | 128 | 1.584 | single | 2021 |
| 7707749 | C3 H5 N5 O3 | 105 | 1.619 | single | 2021 |
| 1549035 | C3 H6 N3 O10 P | 173 | 1.844 | unknown | 2018 |
| 7156212 | C34 H27 N O12 | 100 | 1.247 | single | 2018 |
| 2234470 | C35 H56 N2 O8 | 100 | 1.224 | multi | 2012 |
| 7708469 | C4 H4 N10 O6 | 108 | 1.745 | single | 2021 |
| 4512178 | C4 H6 N4 O12 | 140 | 1.851 | unknown | 2014 |
| 1549036 | C4 H7 N3 O9 | 173 | 1.713 | unknown | 2018 |
| 7059605 | C4 H8 N6 O6 | 150.03 | 1.662 | multi | 2020 |
| 7712978 | C5 H3 N7 O6 | 100 | 1.796 | single | 2023 |
| 7244596 | C5 H6 N8 O7 | 150 | 1.758 | multi | 2022 |
| 1569019 | C5 H8 Br2 N2 O6 | 305 | 2.147 | single | 2023 |
| 4111071 | C5 H8 N4 O12 | 100 | 1.845 | unknown | 2006 |
| 7236311 | C6 H4 N8 O10 | 100 | 1.867 | single | 2016 |
| 7154638 | C6 H8 N2 O6 | 152 | 1.63 | unknown | 2015 |
| 7131129 | C6 H9 N O6 | 160 | 1.554 | single | 2023 |
| 7131130 | C6 H9 N O6 | 113.15 | 1.547 | single | 2023 |
| 7714833 | C6 H9 N7 O8 | 100 | 1.699 | single | 2024 |
| 2000623 | C3 H5 N3 O5 | not stated | 1.662 | unknown | 1992 |
| 5000154 | C5 H8 N4 O12 | not stated | 1.7148 (from cell) | unknown | 1975 |
| 5900023 | C5 H8 N4 O12 | not stated | 1.781 (from cell) | unknown | 1947 |

32 of the 41 are at 100-175 K; the temperatures run from 100 K to 306 K; two PETN cells have none.

* **PETN** has three entries (A15-A17), none among the 32 of the census window; **no nitroglycerin entry** exists (formula C3H5N3O9: no header hit; the 2-nitro-1,3-dinitrooxypropane structure, COD 2237516, 293 K, is a different compound); erythritol tetranitrate has one (4512178, 140 K, 1.851); the xylitol, mannitol, PETriN and pentaerythrityl-tetraazide formulas have no header entry at all.
* **Four-arm entries (32) are a lower bound.** The test needs the whole molecule in the connectivity Open Babel builds from the CIF, and a molecule that sits on a symmetry element is cut: it **missed PETN-I (4111071 and 5900023) and all five entries whose header formula is C5H12O4** (pentaerythritol: 2101361, 2100483, 2218468, 5900022, 1557299, with temperatures None, 15, 150, None and 298 K by header and densities that are not all pentaerythritol's, so they were not read further). It found PETN-II (5000154), the phosphorus-containing entries with four identical oxygen arms (formulas with P and O4, mostly 120 K), and one nitrate ester that is not PETN (8104881, formula C10H16N6O19, 170 K, 1.683, four identical oxygen arms on a quaternary carbon). **There is no tetrahalide, tetraacetate or tetraazide in the header index** (the formulas C5H8Br4, C5H8Cl4, C5H8I4, C5H8F4 and C5H8N12 have no header entry; C13H20O8 has one, 5900024, from 1947, with no density and no temperature), and the tetranitramine is in COD (7105119, 293 K, 1.758; census window, nitramine family), so R1's four-arm crystal-density question has two nitrate/nitramine members (PETN, the tetranitramine) and no more.
* No entry of the 73 has a stated pressure. A pressure series of PETN is not in COD.

## 7. Label traps found while reading (each a candidate regression fixture)

1. **Lease 2023 Table 1** (journal p. 7049) prints "rho_calc (g cm-3) [temp. (K)]" with the temperatures **blank**, and one row mixes PETN's 1.845 (100 K, Zhurova) with derivative densities that COD records at 250-305 K (seven of ten at 293-296 K). For PETN itself the 100 K value is about 0.07 g/cm3 above its room-temperature crystal densities (A13, A14), more than the 0.04 criterion of preregistration 11.1; reading the column as one temperature is wrong.
2. **NIST's ethylene glycol dinitrate page** lists a sublimation enthalpy of 103.8 kJ/mol (Nunez, Barral 1988); Acree 2010 p. 44 prints CAS 628-96-6 for both ethylene glycol dinitrate and dithiooxamide, and the 103.8 row sits under dithiooxamide. EGDN freezes near -22 C. Inferred, not confirmed.
3. **TEGDN, a liquid, has "solid" enthalpies** in NIST and, copied, in the Encyclopedia, 53 kJ/mol apart.
4. **CRC 97's second thermochemistry column is the gas value** (for PETN and for pentaerythritol) and is derived from the first plus a sublimation enthalpy; a reader who takes it for a measurement is wrong.
5. **Meyer's "energy of formation"** for PETN, printed next to its enthalpy, is a different quantity (about 5% smaller); the preregistration already forbids using the energy.
6. **Klapoetke's PETN heat-of-formation cell** holds values spanning 77 kJ/mol; no label separates them.
7. **NIST's PETN method code is Ccb** while the matching Crossref title says detonation calorimeter; which is true is unverified.
8. **PETN density in one Klapoetke cell**: crystal, pycnometer, pressed, loading and TMD values together.
9. **Formula is not identity in COD**: C3H7NO3 (37 header entries) and C4H9NO3 (31) are also the formulas of serine and threonine, not only of propyl and butyl nitrate; only the connectivity pass finds the ester group.
10. **Klapoetke's ethyl nitrate gas value** (-122 +/- 1.3 kJ/mol) has the digits of methyl nitrate's NIST value (-122 +/- 1, Ray and Ogg 1959), while NIST's own ethyl nitrate gas value is -155 +/- 3 (Eqk): a probable mix-up in the Encyclopedia, not confirmed on the primary papers.

## 8. Not held: for the owner to fetch

Direct links, with a distinct suggested filename each (the project convention). DOIs were resolved through Crossref on 2026-10-26 by title, author and year; each is a **match, not a read**.

| what it would settle | link | suggested filename |
|---|---|---|
| PETN solid enthalpy primary root (A01); whether the method was combustion or detonation calorimetry | https://doi.org/10.1063/1.1720361 | `ornellas1966_petn_detonation_calorimeter.pdf` |
| PETN structure at 100 K (A15), the density Lease and Stark reuse | https://doi.org/10.1021/ja0658620 | `zhurova2006_petn_aim_jacs.pdf` |
| PETN-II cell and its transformation (A17) | https://doi.org/10.1107/s0567740875006383 | `cady1975_petn_ii_actab.pdf` |
| ETN room-temperature and 140 K structures (D01) | https://doi.org/10.1021/cg501362b | `manner2014_etn_structure_cgd.pdf` |
| ETN properties and the 150 K density (D01) | https://doi.org/10.1002/prep.201400291 | `matyas2015_etn_physical_properties.pdf` |
| ETN and other tetranitrate esters, the measured basis of the Encyclopedia's ETN enthalpy (C12) | https://doi.org/10.1002/prep.201100059 | `oxley2012_tetranitrate_esters.pdf` |
| MHN and SHN polymorphs (D03) | https://doi.org/10.1002/prep.202000197 | `mclennan2021_hexanitrates_pep.pdf` |
| the tetranitrate of Chavez et al. (C14, D07) | https://doi.org/10.1002/anie.200803648 | `chavez2008_energetic_nitrate_ester.pdf` |
| azido derivatives of PETN including the four-arm tetraazide (B06 search) | https://doi.org/10.1002/prep.202000265 | `lenz2021_azido_petn_derivatives.pdf` |
| pentaerythritol at very low temperature (a structure of the R1 candidate) | https://doi.org/10.1107/s0108768106008329 | `zhurova2006_pentaerythritol_actab.pdf` |
| pentaerythritol sublimation by polyol (B02, B03) | https://doi.org/10.1039/ft9908600075 | `barone1990_polyhydric_alcohols_sublimation.pdf` |
| alkyl nitrate combustion enthalpies, the ethyl, propyl and isopropyl rows (C08, C09) | https://doi.org/10.1039/tf9575300779 | `fairbrother1957_alkyl_nitrates_heats_of_combustion.pdf` |
| solid-state enthalpies of 63 CHNO energetic compounds from thermogravimetric sublimation (E03; the publisher page was not retrievable) | https://doi.org/10.1039/D1CP02201F | `muravyev2021_pccp_thermogravimetry_enthalpies.pdf` |
| nitric ester decomposition and heat of combustion series (the "heat of combustion of XPN" the Flinders thesis cites) | https://doi.org/10.1007/s10973-017-6706-5 | `dong2018_nitric_esters_jtac.pdf` |

DOI not resolved: Cundall, Palmer et al. 1978 (the PETN effusion study behind A04); Medard and Thomas 1954 (pentaerythritol combustion, B01); Miroshnichenko et al. 1985 and 1988 (nitroglycerin); Baroody and Carpenter 1972; Tavernier 1956; Cox and Pilcher 1970 (the book). The NIST WebBook is the only place these are held.

**Open items downloaded and read** (kept outside the repository): Stark, Flinders University thesis 2022 (open repository, 2.7 MB); Manner et al., Chem. Sci. 2018 on PMC (open access, HTML); a short review of nitric esters on PMC (ACS Omega 2021, HTML); US 8,324,421 B2 (Google Patents HTML); Benz et al., Chem. Eur. J. 2023, LMU repository, CC BY 4.0 (14.4 MB PDF); Burcat, JPCRD 1999, from the NIST reprint server (1 MB PDF). The RSC pages were behind a bot challenge and were not fetched.

## 9. How it was searched

* **Held library** (`tools/library_index.py`, 1,120 files indexed, 14 scans with no text layer, `explosives-propellants-and-pyrotechnics.pdf` among them and unreadable): PETN and its synonyms (441 pages in 42 files), nitroglycerin (486 pages, 52 files), ethylene glycol dinitrate, mannitol hexanitrate, "nitrate ester" (219 pages), pentaerythritol (115 pages) and the four-arm halides. The Encyclopedia's volume 2 is a text PDF; **volumes 1 and 3 are image tables**, read here by OCR for the PETN, PETriN, tetranitramine, TEGDN, XPN, TAP-Ac and tripentaerythritol octanitrate entries; the OCR text was read, the images were not all viewed, so those values carry the inventory's OCR caveat. Pages that carry a value were checked on the rendered page for Acree (pp. 151, 177), Lease (p. 7049) and Burcat (p. 118).
* **Open web:** NIST WebBook thermochemistry, phase-change and gas-phase pages for 19 CAS numbers (one, erythritol tetranitrate, not in the WebBook); Crossref for DOIs; the COD site for four deposited entries' bibliographic fields; the open papers above. The fetch tool's page summariser declined some energetic-compound pages, so NIST pages were read as HTML tables directly.
* **COD:** section 6.

## 10. Verdict

**R1: not met, and not meetable as written; but it can be made testable cheaply.**

1. No `measured` gas-phase enthalpy exists for PETN or for any four-arm quaternary carbon. PETN's own gas value is `derived_from_measured`, -388.1 +/- 1.5 kJ/mol, and the JPCRD says none is known.
2. The one compound that matches the pattern with oxygen arms, **pentaerythritol**, has a measured solid enthalpy (+/- 2.8) and a polymorph-dependent sublimation (about +/- 16 kJ/mol on the gas value), so its gas value is `derived_from_measured` and about a quarter the size of the 47-60 kJ/mol PETN miss it would be asked to detect. That is enough to see a gap of that size, and not enough to say what causes it (the quaternary centre or the nitrate arms): pentaerythritol has neither.
3. The **R1 pattern matches a hydrocarbon**, so approval (D8) is the selector.

**R2 and any nitrate-ester family gate: unchanged, and unreachable.** The evidence found does not touch the nitramine stratum (not searched). For nitrate esters every count is far under 150 verified entities: about 14 compounds with measured condensed enthalpies (NIST 12 + ETN + MHN), about 40 entries in the Encyclopedia by heading (an upper bound: the filter keeps a few non-esters and misses PETN's own heading), 73 COD entries in 64 formulas across all temperatures and states, and several of the same series (Lease: 7, Benz: 13) counted as entries. Adding temperatures does not change that conclusion; the literature simply holds few nitrate esters.

**What the new evidence does change:** (a) PETN is not "a compound with no calibrant": it is a derived gas-phase point known to 2 kJ/mol, and the repository's recorded miss mixes a gas-phase error with a 12 kJ/mol sublimation-leg error if the ORCA route used 138.0 (to be checked); (b) the census window hid 14 further nitrate-ester entries and both non-100 K PETN cells, so the nitrate-ester COD stratum is larger than the census said but still small; (c) three label traps (section 7, items 1, 2 and 4) are new fixtures.

**The smallest further evidence that would change the R1 position**, in order of cost:

1. **An amendment, not data.** Admit `derived_from_measured` for R1 and name pentaerythritol as the candidate calibrant (or list the approved compounds), with its +/- 16 kJ/mol stated. This costs a decision (D8) and one ORCA run of a 17-atom molecule, which would say whether the route misses pentaerythritol by tens of kJ/mol (a quaternary-carbon problem) or not (a nitrate-arm problem).
2. **One read page:** Ornellas 1966 (A01) and the pentaerythritol rows behind B01/B03 (Medard and Thomas 1954; Barone 1990), to give the two anchors a read primary locator under 8.2.
3. **A measurement** of the gas-phase or sublimation enthalpy of pentaerythritol tetra-acetate or the tetrahalides, which would give a heteroatom-armed four-arm compound with a measured value; none was found, and none of the held or open sources reports one.

Not searched: the nitramine stratum (R2's own condition), polymorph-resolved PETN thermal expansion (it needs the CSD and is the D10 expansion coefficient), and the LMU dissertations (D14).
