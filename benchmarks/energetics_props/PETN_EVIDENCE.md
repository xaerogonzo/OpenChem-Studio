# PETN and the nitrate-ester family: an evidence hunt for Phase B

An inventory, not a score. No corpus was built, no method was run, and no number of `PREREGISTRATION.md` was changed (that file is an unfrozen draft and is not edited here). Every item carries its source, page or table, the value as printed, its `value_kind` (preregistration 3.1), the temperature and form, and whether it is independent of what `INVENTORY.md` already holds. The rows are in `PETN_EVIDENCE.json` (124 rows, ids `A01`... below); the COD rows are in `cod_nitrate_extra.json`; the searches are in section 9. Nine papers the owner supplied (and four SI files) were read after the first pass (section 3.5, rows `F01`-`F18` and the mined fit tables and further NIST rows `G01`-`G06`, the four remaining held books `G07`-`G10`, two papers added by the owner afterwards and a resolved reference `G11`-`G13`, the nitramine count for R2 `G14` its trace, identity resolution and Encyclopedia pass `G19`-`G21`, the eleven primaries read `G22`-`G27`, two more papers (the 1967 Korsunsky and a 2009 recommended set) with the recount `G28`-`G30`, and the substitutes for the Medard and Thomas papers `G31`-`G33` (Pedley 1986, Koch 2019, Stegeman 1945 `G34`, the Cox and Pilcher 1970 data pages `G35`-`G38`, the McEwan-Rigg and Bradley-Cleasby files `G39`-`G40`, the pentaerythritol sublimation paper `G41`, and the 2023 nitroisobutylglycerol paper with its Supporting Information `G42`, and the 2021 sublimation paper's nitramine block, rule, DSC, gas-phase and accuracy data `G43`-`G51`), the two effusion papers behind PETN's sublimation `G15`-`G16`, and the Medard and Thomas and Cox and Pilcher bibliography `G17`-`G18`).

<!-- cod_nitrate_extra: total=73 outside_window=41 single=52 formulas=64 four_arm=32 -->

**Values.** Single measured values, short runs of values from one cell, spreads and locators are quoted as facts, with the page. No table is reproduced and no running text is copied. This is looser than `PREREGISTRATION.md` section 7, which keeps per-compound values from copyrighted tables out of the repository; the owner relaxed it for this file on 2026-10-26 ("they're numbers"), and the preregistration needs a one-line amendment to say so (section 10).

## 1. What would move the conditions

`PREREGISTRATION.md` 12.1 and `docs/ROADMAP.md` (recorded 2026-10-05):

* **R1** is met by one verified row (value kind `measured`, phase `gas`, a primary locator read on the page, a different identity block from PETN) of a compound matching `[CX4;H0]([CH2][!#1])([CH2][!#1])([CH2][!#1])[CH2][!#1]` with four identical arms, plus the owner's approval (D8).
* **R2** needs the ORCA route to pass the P2 gate scoped to nitramines on at least 30 paired verified holdout nitramines (about 150 verified entities, section 5) and the PETN class refused by a coded limit.
* Any family claim needs about 150 verified entities in the family (section 5). The nitrate-ester family is the one this file counts.

## 2. Findings in brief

| # | finding | where |
|---|---|---|
| 1 | PETN has **no experimental gas-phase enthalpy of formation**. Its derived gas value is a measured solid value (-538.5 +/- 0.8, two bomb-calorimeter runs, Ornellas 1966) plus a measured sublimation enthalpy (150.4 +/- 1.3): **-388.1 +/- 1.5 kJ/mol**, `derived_from_measured`. A W1-F12 calculation gives -395.5 (Muravyev 2021), 7.4 kJ/mol lower; Suntsova 2017 calculates -413.6 +/- 4; Manaa 2016 calculates -410.0 (ccCA-PS3), -442.2 (G4) and -443.5 (G3) and derives an experimental -381.2 with the larger sublimation value. The derived experimental gas value is **-381 to -388** and the calculated ones span **-395.5 to -443.5**. | A01, A07, F01, F08, F14, F15, F17 |
| 2 | Five measured PETN sublimation enthalpies agree within 146.6-156.9 kJ/mol (Ostmark's 2012 review of seven vapour-pressure studies fits 150.8 from Lau and Dionne's data), so PETN is a **well-pinned derived gas-phase point**, not a gap. If the repository's route used the 138.0 kJ/mol Keshavarz value (the number `literature.toml` records for the APC route), about **12 of the recorded 59.5 kJ/mol PETN miss is the sublimation leg**; against the W1-F12 gas value the gas-phase miss is about 54. | F11, section 3.4 |
| 3 | **Pentaerythritol** is the only compound found that matches the R1 pattern with oxygen arms and measured data (solid -920.5 +/- 2.8; sublimation 96-163 kJ/mol across polymorphs). Its gas value is `derived_from_measured` only (about +/- 16 kJ/mol), so it **does not meet R1 as written**. | B01-B04 |
| 4 | The **R1 pattern is also matched by 3,3-diethylpentane**, so the owner's D8 approval does all the selecting; a test pins this. | B05 |
| 5 | **Three printed values are one number or a contradiction.** The Encyclopedia's PETN (-538.48), EGDN (-243.01) and ETN (-474.8) enthalpies and the Chavez patent's DNTN (-371) are the **literature inputs of one Cheetah table** in Oxley 2012 (Table 8; the text says they are literature values), not measurements. And that -371 is contradicted by 171 kJ/mol by Muravyev 2021 (-542 for the same compound; another literature value -580). | F04, F10, C12, C14 |
| 6 | ETN's two low-temperature structures disagree: **1.851 (140 K, Manner) against 1.827 (150 K, Matyas)**, 0.024 g/cm3 and 1.3 % in cell volume at 10 K apart, more than the 0.02 tolerance of preregistration 8.2. Volumetric expansion from 100 K to room temperature is about 2e-4 per K (PETN, ETN), so 0.04 g/cm3 is about 100 K. | F05-F07 |
| 7 | **Nitrate-ester family**: NIST holds measured formation enthalpies for **at least 26 nitrate esters** (12 found first, then 19 more by name through the Keshavarz 2006 table, which copies NIST); the Encyclopedia's 'exptl.' numbers are these NIST values digit for digit. Two new sublimation measurements of ETN disagree by 22 kJ/mol (117.7 and 139.5). | C01-C11, F03, F09 |
| 8 | COD holds **73 nitrate-ester entries** (32 in the census window, **41 outside it**), 52 single-component, in **64 distinct formulas**. PETN has 3 entries (100 K, and two cells with no temperature in the header; the paper for PETN-II gives 136 C). | section 6 |
| 9 | Label traps worth fixtures: Lease 2023 Table 1 has a blank temperature column mixing 100 K and about 296 K; NIST's EGDN sublimation row is probably dithiooxamide's; TEGDN is a liquid that two sources print as a solid; the ETN "X-ray density" 1.553 / 1.55 in Oxley and the Encyclopedia is 0.22 below any X-ray density read. | section 7 |
| 10 | Everything above is **an order of magnitude short of 150 verified entities** for the nitrate-ester family. | section 10 |

## 3. PETN itself

### 3.1 Crystal density, with temperature and form

| id | value | kind | T and form | source and locator | independent? |
|---|---|---|---|---|---|
| A15 | **1.845** g/cm3 | measured | 100.0(1) K, PETN-I, P-4 21 c, a = 9.2759(8), c = 6.6127(4) A, V = 568.97 A3, Z = 2, R(F) 0.0104 | Zhurova et al., J. Am. Chem. Soc. 128 (2006) 14728, Table 1, p. 14729 (**read**); COD 4111071; the SI CIF (ja0658620_si_001, **read**) carries the same cell, 1.845 and R | yes. **The same observation is printed by Lease 2023 Table 1 (A18, T blank) and cited by Manner 2014 and Stark 2022** |
| A13 | 1.778 (X-ray calculation, 22 C); 1.716 (X-ray calculation, 136 C, orthorhombic); 1.778 (exptl., 22 C) | unlabelled | PETN-I / PETN-II | Klapoetke Encyclopedia vol 3, PETN entry, density cell (OCR); ref [21] | the 136 C value is Cady and Larson's cell (A17) |
| A17 | **1.72** g/cm3 calculated; CIF cell gives 1.7148 | measured cell | PETN-II, Pcnb, a = 13.29, b = 13.49, c = 6.83 A, Z = 4, **136 C** | Cady and Larson, Acta Cryst. B31 (1975) 1864, abstract and p. 1864 (**read**); COD 5000154 | yes |
| A16 | 1.781 (computed here from the cell and Z) | derived | PETN-I, temperature not in the CIF | COD 5900023, Booth and Llewellyn, J. Chem. Soc. 1947, 837 | yes |
| A14 | 1.76 (Meyer p. 251); 1.76 at 20 C (Akhavan Table 2.14, p. 41); 1.773 at 20 C (CRC 97 PDF p. 574); 1.773 (Lange's Sec. 01, PDF p. 291, text layer reads '1.177320 4') | unlabelled | form not stated | as listed | no |
| F02 | 1.7599 +/- 0.0006 g/cm3 (helium pycnometer); 'literature X-ray density' 1.778 | measured | solid, room temperature | Oxley et al. 2012, Table 6, p. 34 (**read**) | yes; the pycnometer value is 1 % below the X-ray density |

The Klapoetke density cell also lists nine further values for PETN, labelled pycnometer, nominal, TMD (1.78), pressed (1.74) and compressed (1.60): bulk, pressed and crystal numbers share one cell, as preregistration 3.2 warns. Two polymorphs exist: PETN-I (tetragonal, stable to about 130 C; the I to II transition is about 410 K per Zhurova) and PETN-II (orthorhombic, up to the melt); **PETN II melts 0.2 C above PETN I** (142.9 C), and the heat of fusion of PETN I depends on crystal quality (32 to 38 cal/g), Cady and Larson. **For P1 the PETN density is one 100 K structure (1.845), one room-temperature family (1.76-1.78, PETN-I) and one 136 C PETN-II cell (1.72); the room-temperature X-ray primary is Trotter 1963 or Booth and Llewellyn 1947 (not read).**

### 3.2 Enthalpy of formation, solid

| id | value | kind | source | lineage |
|---|---|---|---|---|
| A01, F01 | **-538.5 +/- 0.8** kJ/mol (= -128.7 +/- 0.2 kcal/mol), solid, 298 K, from two bomb-calorimeter determinations of the combustion energy (618.7 and 618.1 kcal/mol at constant volume, standard-state corrected) | measured | Ornellas, Carpenter and Gunn, Rev. Sci. Instrum. 37 (1966) 907, printed pp. 910-911 (**read**); NIST WebBook row, method Ccb | the primary root. NIST's Ccb is right (combustion, not detonation calorimetry) |
| F01 | earlier combustion energies 620.5 (Burlot and Thomas 1939) and 620.0 (Schmidt 1934) kcal/mol at 290 K, not standard-state; NIST reanalyses Burlot at -2569.8 +/- 2.5 kJ/mol (original -2594.7) | measured | Ornellas p. 910; A03 | older roots; consistent after conversion by NIST's reanalysis |
| A09 | CRC 97: -538.6 (second column -387.0); Lange's Sec. 06 Table 6.1: 538.6 (sign lost in the text layer) | unlabelled | CRC PDF p. 897; Lange's PDF p. 39 | the same upstream as A01; CRC's second column is a derived gas value |
| A10 | Klapoetke vol 3, one cell: -538.48 kJ/mol [109,112]; -128.7 kcal/mol [20,91]; -128.8 kcal/mol (solid) [59]; -125.5 kcal/mol [77] (= -525.1 kJ/mol); -515.3 kJ/mol [72]; -110.34 kcal/mol at 25 C [20,21] (= -461.7 kJ/mol) | unlabelled | PETN entry (OCR) | the -538.5 cluster is A01; -538.48 is the **Cheetah input digit** of Oxley's Table 8 (F04); -461.7, -515.3 and -525.1 are other numbers, 77 kJ/mol across one cell |
| A11 | Meyer: enthalpy of formation -407.4 kcal/kg = -1704.7 kJ/kg (= -538.9 kJ/mol); 'energy of formation' -385.0 kcal/kg = -1610.7 kJ/kg | unlabelled | printed p. 251 | spread already in `INVENTORY.md` section 5 |
| A12 | Akhavan: enthalpy -1683 kJ/kg (= -532.1 kJ/mol); energy of formation -1509 kJ/kg | unlabelled | Table 2.14, printed p. 41 | same |
| F04 | -538.48 kJ/mol | unlabelled | Oxley 2012, Table 8, p. 37: 'literature values for the heats of formation [3,9]' fed to Cheetah | **not a measurement of Oxley's** |
| F08, F15 | -543 (calculated gas minus measured sublimation; mean uncertainty 10); literature list -538.5 +/- 0.8 (the one flagged experimental), -525, -556.8 +/- 2.0, -544; Suntsova: calculated -548.6 and a further literature -593.0 (Huynh et al., 'possibly too negative') | computed | Muravyev 2021, Table 1, p. 15528; Suntsova 2017, table, PDF p. 4 (**read**) | the literature spread of PETN's solid enthalpy is 31.8 kJ/mol in Muravyev's list, 67.5 with Huynh's value; one value is a combustion experiment |

**Verification under preregistration 8.2:** the primary page is now read, so A01 qualifies as a verified solid enthalpy (a primary-literature measurement with a locator read on the page); A09, A10 (two values), A11 and F04 are the same lineage, not four sources.

### 3.3 Sublimation and the derived gas-phase enthalpy

| id | value | kind | source |
|---|---|---|---|
| A04 | **150.4 +/- 1.3** kJ/mol at 298 K (328-405 K, effusion) | measured | NIST WebBook; Acree and Chickos 2010, Table 6, p. 151; Cundall, Palmer et al. 1978 |
| A05 | 152 +/- 2 (method V) | measured | NIST; Edwards 1953 |
| A06 | 156.9 +/- 0.8 (369 K, TE); 152.3 (DSC); 146 +/- 12; U 121.3 (flagged); 151.9 +/- 2.1 (370-411 K) | measured | Acree 2010, Table 6, printed p. 043101-151 (rendered page read) |
| F02 | 146.6 (isothermal TGA, extrapolated to 25 C); vapour pressure 5.21e-6 Pa at 25 C | measured | Oxley 2012, Table 6, p. 34 (**read**); cites 1.78e-5 Pa (Crimmins 1969) |
| F08, F13, F16 | 147.6 +/- 3.5 (modified low-pressure TG); literature in the SI: 150.8 [Ostmark review: a fit to Lau and Dionne's data of the seven studies it reviews], 150.4 +/- 1.3, 150.6 +/- 1.8, 149.2 (Oxley recalculated) | measured | Muravyev 2021 (**read**), SI p. 14; Ostmark 2012, section 4.6, printed p. 17 (**read**) |
| A20 | 151.9 (Lange's Sec. 06, PDF p. 74) | unlabelled | a compilation of A06's last row |
| A07 | **-388.1 +/- 1.5** kJ/mol, gas, 298 K (A01 + A04) | derived_from_measured | this inventory |
| A08 | -92.5 kcal/mol (= -387.0 kJ/mol), Cox and Pilcher; Burcat's text, section 3.25: 'No experimental value is known for this explosive material'; Burcat's own calculations -89.89, -98.2, -95.3 kcal/mol | unlabelled | Burcat 1999, Table 52, p. 118 (rendered page read) |
| F17 | experimental by Hess's law: -91.1 kcal/mol (= -381.2 kJ/mol) from -128.7 and a sublimation of 37.6 kcal/mol (157.3 kJ/mol); calculated -98.0 (ccCA-PS3), -106.0 (G3), -105.7 (G4) kcal/mol (= -410.0, -443.5, -442.2 kJ/mol); the authors: no consistent method reaches 1-2 kcal/mol for these molecules | computed | Manaa, Fried, Kuo 2015 (LLNL), Table I and PDF pp. 10-11 (**read**) |
| F08, F14, F15 | **-395.5** (W1-F12 atomization energy); another calculation -413.6 +/- 4 (Suntsova and Dorofeeva 2017, their sublimation model gives 135.0 against an experimental 146.6) | computed | Muravyev 2021, Table 1 and SI p. 22; Suntsova 2017, table, PDF p. 4 (**read**) |

PETN therefore has a derived gas-phase enthalpy known to about 2 kJ/mol (five sublimation measurements within 10), a W1-F12 value 7.4 kJ/mol below it, and **no measured gas-phase enthalpy**. R1 requires `measured`, so it cannot be met by PETN or by any compound whose gas value is solid-plus-sublimation.

### 3.4 What this does to the repository's recorded PETN miss

`benchmarks/thermophysical/orca_atom_equivalents.py` records the 6-fit PETN solid value -479.5 against a measured -539.0 (59.5 kJ/mol), and `docs/research/literature.toml` records, for the APC route, gas -344.0 with Keshavarz's sublimation 138.0. **If** the ORCA route's sublimation leg for PETN was also 138.0, its implied gas value is -341.5, against the derived -381.2 to -388.1 (a gas-phase miss of about 40-47), against the W1-F12 -395.5 (about 54) and the ccCA-PS3 -410.0 (about 68); 12.4 kJ/mol of the recorded miss is the sublimation leg (138.0 against a measured 150.4 +/- 1.3, or 147.6 +/- 3.5). The gas-phase miss is the quantity R1 would test. This is arithmetic on recorded numbers; which sublimation value the ORCA route used is not confirmed here.

### 3.5 What the supplied papers add (all read)

| paper | what it settled |
|---|---|
| Ornellas 1966 | A01 is a bomb-calorimeter combustion value (618.7 and 618.1 kcal/mol, two runs); the heat of detonation is 1490 +/- 6 cal/g, H2O(l) |
| Zhurova 2006 | PETN-I at 100.0(1) K: 1.845, cell and R factor; the I to II transition is about 410 K |
| Cady and Larson 1975 | PETN-II: Pcnb, Z = 4, 1.72 g/cm3 at **136 C**; PETN II melts 0.2 C above PETN I |
| Manner 2014 | ETN 1.851 at 140(1) K (Table 4); 1.773 at room temperature with its cell; CIF matches |
| Matyas 2015 | ETN 1.827 at 150 K, a different crystal: it disagrees with Manner by 0.024 (F05-F07) |
| Oxley 2012 | sublimation enthalpies and vapour pressures by TGA (PETN 146.6, ETN 117.7, DNTN 105.3); pycnometer densities; **its heats of formation are literature values fed to Cheetah** (F04) |
| Ostmark 2012 | PETN vapour pressure: seven studies agree except John's; fit gives 150.8 kJ/mol; no vapour pressure of solid nitroglycerin exists (melts 12.8 C) |
| Suntsova 2017 and SI | a calculated PETN gas value -413.6; a further literature solid enthalpy -593.0; the SI has no PETN or nitrate-ester row |
| Manaa 2015 | the experimental PETN gas value by Hess's law (-381.2 kJ/mol with a 157.3 sublimation) and G2, G3, G4 and ccCA-PS3 calculations spanning 33 kJ/mol |
| Cooper 1996, Agrawal 2010 | condensed enthalpies only (PETN -128.7 kcal/mol, -538 kJ/mol); no gas-phase value in either book |
| Muravyev 2021 and SI | a W1-F12 gas enthalpy and a modified-TG sublimation enthalpy for PETN, ETN and SMX (= DNTN); DSC melting data with purity (PETN 140.9 +/- 0.3 C, 48.1 +/- 1.1 kJ/mol; ETN 61.2 +/- 0.7, 36.9 +/- 3.3); the **-371 vs -542** contradiction for the Chavez compound |

## 4. R1: four-arm quaternary carbons

| id | compound | what exists | kind |
|---|---|---|---|
| B01 | pentaerythritol | dfH(solid) -920.5 +/- 2.8 kJ/mol, Ccb, Medard and Thomas 1954 (NIST); CRC 97 and Lange's print -920.6 | measured |
| B02, B03 | pentaerythritol | sublimation 163.0 (298 K, NIST, Barone 1990); Acree 2010 Table 6, printed p. 043101-177 (rendered page read): 134 +/- 7 (crystalline, 441-460 K); 96 +/- 9 (plastic, 465-477 K); 131.3 +/- 6.6 (403 K); 161 +/- 1.0 (418-455 K); 163.0 (298 K); 131.4 (tetragonal, 397-410 K); 143.9 +/- 0.8 (379-408 K) | measured, polymorph-dependent |
| B04 | pentaerythritol | gas -776.7 (CRC 97 p. 897, = -920.6 + 143.9); about -757 to -789 by B01 + the usable B03 rows | derived_from_measured |
| B05 | 3,3-diethylpentane | dfH(liquid) -275.4 (NIST, from dcH -6124.5 +/- 1.6, Johnson, Prosen et al. 1947) | derived_from_measured |
| B06 | tetrabromide, tetrachloride, tetraacetate | none found | - |
| G02 | dipentaerythritol hexanitrate; nitroisobutylglycerol trinitrate (O2NOCH2)3C-NO2; trimethylolpropane trinitrate | solid dfH -979.6 +/- 5.4; -226; -479.9 kJ/mol (Ccb, Medard and Thomas 1955, 1949, 1953; NIST): quaternary carbons with three nitrate arms; no gas-phase or sublimation value | measured |
| B07 | pentaerythritol trinitrate | -134 kcal/mol (25 C) [8] and -2,069 kJ/kg [7] (= -560.7 and -560.9 kJ/mol), Klapoetke vol 3 entry (OCR) | unlabelled |

* **Pentaerythritol is the only candidate.** Its structure matches the R1 pattern with four identical hydroxyl arms. A gas value exists only as `derived_from_measured`, with a polymorph spread of about +/- 16 kJ/mol on the sublimation leg. R1 as written needs `measured`, phase `gas`; it is **not met**, and could be met only by an amendment that admits `derived_from_measured` for this compound or by a new measurement.
* The **R1 pattern is not selective.** `tests/test_energetics_props_petn_evidence.py` shows that 3,3-diethylpentane, with measured combustion data, matches it. The owner's D8 approval is the real selector; the rule's text should say "four identical heteroatom-bearing arms" or list the approved compounds.
* The nearest nitrate-bearing neighbours are PETriN (three nitrate arms and one hydroxyl; condensed enthalpy only; B07), nitroisobutylglycerol trinitrate (three nitrate arms and a nitro group), dipentaerythritol hexanitrate, trimethylolpropane trinitrate (G02) and the **metriol trinitrate** that the repository already predicts well; no gas-phase value of any of them exists, so they test the condensed leg only. For three-arm nitrate esters the gas-phase values are nitroglycerin's, derived: **-279.1 +/- 2.7 kJ/mol** (liquid -371.1 +/- 1.7, Miroshnichenko 1988, plus a measured vaporization 92.0 +/- 2.1), and methyl nitrate's, **-122 +/- 1 kJ/mol** (NIST, method Cm, Ray and Ogg 1959). NIST's gas value for ethyl nitrate is **-155 +/- 3** (Eqk, Gray et al. 1956); the Encyclopedia prints -122 +/- 1.3 for ethyl nitrate's gas phase, the digits of methyl nitrate's value (a probable mix-up, section 7 item 10).

## 5. The nitrate-ester family, measured thermochemistry

NIST WebBook rows (public data; ids C01-C10, values in the JSON): nitroglycerin (five liquid rows from -353.9 to -375, one gas), diethylene glycol dinitrate (liquid and solid), metriol trinitrate (solid), 1,2,4-butanetriol trinitrate (liquid), propylene glycol dinitrate (solid, -296.9 +/- 9.3), triethylene glycol dinitrate (two solid rows, -656.9 and -603.8: 53 kJ/mol apart), methyl, ethyl, propyl and isopropyl nitrate, ethylene glycol dinitrate (liquid), and PETN. That is 12 compounds; the Keshavarz 2006 table of experimental enthalpies (all 'taken from NIST', G01) and further name look-ups (G02, G03) add dipentaerythritol hexanitrate, trimethylolpropane trinitrate, nitroisobutylglycerol trinitrate, the glycerol mono- and di-nitrates, 1,4-butanediol dinitrate, 2,4-pentanediol dinitrate, acetyl nitrate, mannitol hexanitrate and others: **at least 26 nitrate esters with a measured condensed enthalpy**, almost all solid or liquid, none with a measured gas value except nitroglycerin and methyl nitrate (G05).

* **Lineage collapse (C11, F04).** The Encyclopedia's printed enthalpies for TEGDN (-656.9 and -603.8), metriol trinitrate (-450.2), ethyl nitrate (-190.4 liquid) and nitroglycerin (-371) are the NIST digits; its PETN (-538.48), EGDN (-243.01) and ETN (-474.8) are the Cheetah-input digits of Oxley's Table 8. They do not verify their sources, and two of them print "solid" for liquids.
* **ETN's enthalpy has no measured basis in the sources read.** Oxley takes -474.80 from the literature (Fedoroff and Sheffield 1972); Muravyev's own value is -496 and the literature values he lists run -475 to -545, none flagged experimental. Mannitol hexanitrate (C13) has -706.7 +/- 4.2 (c), -169.42 +/- 0.68 kcal/mol and -708.8 kJ/mol (exptl.) in the Encyclopedia, on three references.
* **A label to watch:** the Encyclopedia prints "exptl." beside values that come from a fit table (the ethriol trinitrate, ethylene glycol dinitrate, glycerol dinitrate, mannitol hexanitrate, metriol trinitrate and methyl nitrate entries each carry an "exptl." and one or two "calcd." numbers from one reference), so "exptl." is not a `measured` tag by itself.
* **Open items found:** the Chavez/Oxley tetranitrate, whose -371 kJ/mol 'by bomb calorimetry' (US 8,324,421 B2) is contradicted by Muravyev 2021 (-542; literature -371 and -580; F10), and a 1.917 g/cm3 X-ray density for it (D07); xylitol pentanitrate, density 1.852 at 150 K measured, enthalpy calculated (Stark thesis, D04, C15); four PETN derivatives of Benz 2023 (CC BY), densities at 293, 123, 110 and 123 K, enthalpies calculated (D06).

### 5.1 The fit tables, mined

The Keshavarz, Nazari, Cawkwell and Byrd-Rice papers hold the nitrate-ester rows of the held literature's "fit tables" (INVENTORY section 6). Read page by page: **they repeat NIST** (G01, G06; Keshavarz 2006's footnote says so), include liquids as "densities" (G04), and add one genuinely useful set, **Cawkwell 2021's experimental gas-phase values** for nitroglycerin (-66.71 kcal/mol), methyl, ethyl and t-butyl nitrate and furazandimethanol dinitrate (G05), together with its finding that an atom-equivalent scheme struggles with the nitrate ester group in nitroglycerin (12.1 kcal/mol for the 7-parameter model in the text, 12.9 from its Table 1 values, and 25.5 for the 4-parameter model). That is the same shape of failure as the repository's PETN miss, now seen in a second method on a three-arm molecule. Byrd and Rice 2005's table lists nitrate esters (methyl, ethyl and propyl nitrate, nitroglycerin, PETN, metriol trinitrate, butanetriol trinitrate, trimethylolpropane trinitrate, furazandimethanol dinitrate) and the printed list carries phase flags, but the experimental values were not found in the main text.

### 5.2 Four more held books

Klapoetke's 4th edition (Tab. 9.16b, printed p. 270), Viswanath 2018 (Table 2.15), Akhavan (Table 2.7, nitroglycerin) and Boddu and Redner 2010 were read on the page. **None adds an independent number for PETN or its family.** Klapoetke's table reprints PETN (141.3 C, 1.760, -539 kJ/mol) and NG (14 C, 1.60, -370) beside a new tetranitrate ester that is not an R1 candidate (G08); Viswanath's Table 2.15 repeats Meyer's -407.4 kcal/kg and the X-ray density 1.778 for PETN (G09, same digits as A11 and A13); Akhavan's nitroglycerin table (G07) is a liquid and its -1633 kJ/kg is about -371 kJ/mol, NIST's liquid value; Boddu holds no PETN or nitrate-ester value at all (G10). The handoff's "Akhavan Table 5.11" is not in the file held (a 28-page chapter) and Viswanath's Table 5.11 is NTO vacuum stability.

### 5.3 The nitramine stratum (R2)

R2 needs the ORCA route to pass the P2 gate on at least 30 paired verified holdout nitramines, which the preregistration puts at about 150 verified entities (12.1, D8). What could be counted (G14, G19-G21):

* **The first count was wrong in two ways, and is corrected.** "At least 19 nitramines" included DINA and four N-alkyl-N-(2-nitratoethyl)nitramines (NENAs), which the repository's own family rule (`epb_families.family`, nitrate ester ranks first) puts in `nitrate_ester`. **By that rule 14 of the 19 names are nitramines.** And Keshavarz and Sadeghi's "ref [23]" is the NIST WebBook, so their table, like Keshavarz 2006 and Nazari 2016, adds no independent root (G19). (I had also concluded that NIST lacks the NENAs from a formula search that returned "not found"; that search is unreliable, it fails for HMX too, and a CAS look-up shows NIST holds them. Not a reliable test.)
* **Identities resolved** (G20): RDKit InChIKeys equal NIST's for all 15 compounds looked up by CAS. Of the 14 nitramines, 12 have a solid formation enthalpy in NIST and 2 are liquid only. **First pass: two verified by the preregistration's 8.2 rule from NIST's rows; after the primaries were read (below), five of the eight eligible.** RDX, HMX, 1,4-dinitropiperazine and dimethylnitramine are forced into development, which leaves **8 solid nitramines for any partition, about 2 in a 20 % holdout**.
* **Klapoetke's Encyclopedia** (vols 1 and 3 by OCR, vol 2 by text layer; G21) adds **17 further neutral nitramine entries** with a printed heat of formation (CL-20, TNAZ, BCHMX, keto-RDX, methylene dinitramine, ethyltetryl, TNGU, DNNC and others), four of them with an "exptl." label, most with several values several kJ/mol apart. That raises the ceiling to about 31 names; it does not raise the number that could be verified.
* **The sublimation leg is better covered than the formation enthalpies**: Cundall 1978 measured RDX (134.3 +/- 0.7 kJ/mol), HMX (161.0 +/- 0.3), tetryl (133.8 +/- 1.6) and nitroguanidine (142.7 +/- 2.0), and Edwards 1953 gives RDX 112.1 (G15, G16), 22 kJ/mol below Cundall's value for the same compound.

**After the eleven primaries were read (G22-G27): 5 of the 8 eligible solid nitramines rest on a primary page I read** (4-nitromorpholine, EDNA, nitroguanidine, bis(2,2-dinitropropyl)nitramine, bis(trinitroethyl)nitramine), tetryl is `disagree` (29.3 against 43.9 kJ/mol as the two papers print them), and nitrourea and methyldinitramine remain single, unread sources. **A NIST row is not what its paper prints**: its 'ALS' re-evaluation sits 3.6 to 15 kJ/mol above Krien's printed figures (G22) and neither of its tetryl rows is the figure in either paper (G25); Ornellas 1974 and Korsunskii 1989 cite the values NIST attributes to them (G26). Measured sublimation legs now exist for 4-nitromorpholine, both dinitroalkyl nitramines, 1,4-dinitropiperazine, RDX, HMX, tetryl and nitroguanidine (G16, G23, G24).

**Two further papers changed the count again (G28-G30).** Korsunsky 1967 is a nitrosamine paper that only cites dimethylnitramine's value (G28). **Miroshnichenko et al. 2009** (G29), the same group's recommended set with purity-checked samples, adds six solid nitramines measured by its authors (2,4-dinitro-2,4-diazapentane, 2,5-dinitro-2,5-diazahexane, 1,6-bis(methylnitramino)hexane, 1,3-dinitroimidazolidine, CL-20 and one unnamed bicyclic), gives RDX and HMX a modern root that agrees with Krien, and shows that **methyldinitramine is a liquid at 298 K**, so it leaves the solid pool. Counted that way (G30): about 37 names in all, **10 verified of about 13 eligible solid nitramines, plus one unresolved identity**, about 2 in a 20 % holdout. Delepine and Badoche's RDX is 70.3 as printed (NIST's 66.5 is Cox and Pilcher's reanalysis).

**Pedley, Naylor and Kirby (1986) was added to the library (G31)** and prints, on readable pages, the Medard and Thomas digits for pentaerythritol (-920.6 +/- 2.8, gas -776.7), EDNA (-103.0), DINA (-308.0), nitroguanidine (-92.4), trimethylolpropane trinitrate (-479.9) and dipentaerythritol hexanitrate (-979.6), with uncertainties. It is a re-evaluation of those papers (same lineage), so it **confirms the digits but adds no independent root**; it also shows CRC's gas-phase pentaerythritol value comes from it. Nitrourea and nitroisobutylglycerol trinitrate were not found in it. **Koch 2019 (G32)** compiles six solid nitroguanidine values (-75.3 to -100.0 kJ/mol) but its attributions disagree with the papers it cites (Krien prints -92.05, Koch gives -100.00), so it is a lead, not a source.

**Cox and Pilcher (1970) was added and read (G35-G37).** Its tables print the combustion and formation enthalpies on facing pages with a reference code per value, and the codes decode (its reference list, PDF pp. 612-624): pentaerythritol, DINA, EDNA, TMP trinitrate and the methyl-propanediol dinitrate rest on Medard and Thomas (1953, 1954, 1955), DINA's second value on Tavernier and Lamouroux (1955), PETN's sublimation on Edwards (1953), pentaerythritol's on Bradley and Cleasby (1953) and **nitroguanidine on a National Bureau of Standards combustion (Prosen and Gilmont, OSRD report 1590, 1943) that McEwan and Rigg quote, J. Am. Chem. Soc. 73, 4725 (1951), DOI 10.1021/ja01154a072, read in G39** (so it is not a Medard-Thomas value, and agrees with Krien's -92.05). **Dipentaerythritol hexanitrate is there too (G38, -979.5 kJ/mol, Medard and Thomas 1956, vol. 38 p. 45, not 1955 as NIST has it).** The pentaerythritol sublimation paper is Bradley and **Cotson** (not Cleasby), J. Chem. Soc. 1953, 1684, DOI 10.1039/jr9530001684, now read (G41): its 143.9 kJ/mol is the slope of an effusion fit over 106-135 C, the 131.4 of Nitta et al. is the same kind of value over 124-137 C, and Barone's 161.0 over 145-182 C: three second-law values rising with temperature, 30 kJ/mol apart, so pentaerythritol's gas-phase value stays uncertain by that much. No row for nitrourea or nitroisobutylglycerol trinitrate was found in the pages read; the N6 block holds dipentaerythritol hexanitrate. Rzhevskiy et al. 2023 (G42, DOI 10.3390/ijms24108541, text and SI read) gives a **computed** value for the latter (gas -308 by W1-F12 plus a 94 kJ/mol vaporization estimate, so -402 kJ/mol) that sits **176 kJ/mol away** from the -226 NIST prints from Medard and Thomas 1949: unresolved, neither verified.

Muravyev 2021's Table 1 (G43-G44) adds a second solid enthalpy by a different method (measured sublimation plus a W1-F12 gas value) for RDX, HMX, 1,4-dinitropiperazine, 2,4-dinitro-2,4-diazapentane, tetryl, nitroguanidine and CL-20, each within 10 kJ/mol of the nearest experimental literature value; TEX, BC-HMX and DATN do not agree (85, 22 and 66 kJ/mol), and the paper puts its own method's inaccuracy at up to 25 kJ/mol (G50), so this is a weak independent observation, not a replication. Whether it counts under 8.2 is an owner question, and at most it adds a few verified entities. On this evidence R2 is `NOT EVALUABLE`, as the preregistration already expects; the gap is a factor of about fifteen (10 verified, about 2 in a holdout, against about 150 and 30), and more literature of the kinds held would not close it. What would: new calorimetry on solid nitramines, or relaxing the count (a decision, D8), which this file does not propose.

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

1. **Lease 2023 Table 1** (journal p. 7049) prints "rho_calc (g cm-3) [temp. (K)]" with the temperatures **blank**, and one row mixes PETN's 1.845 (100 K, Zhurova) with derivative densities (1.723, 1.957, 2.158, 1.525) that COD records at 250-305 K (seven of ten at 293-296 K). For PETN itself the 100 K value is about 0.07 g/cm3 above its room-temperature crystal densities, more than the 0.04 criterion of preregistration 11.1.
2. **NIST's ethylene glycol dinitrate page** lists a sublimation enthalpy of 103.8 kJ/mol (Nunez, Barral 1988); Acree 2010 p. 44 prints CAS 628-96-6 for both ethylene glycol dinitrate and dithiooxamide, and the 103.8 row sits under dithiooxamide. EGDN freezes near -22 C. Inferred, not confirmed.
3. **TEGDN, a liquid, has "solid" enthalpies** in NIST and, copied, in the Encyclopedia, 53 kJ/mol apart.
4. **CRC 97's second thermochemistry column is the gas value** (PETN -387.0, pentaerythritol -776.7) and is derived from the first plus a sublimation enthalpy; a reader who takes it for a measurement is wrong.
5. **Meyer's "energy of formation"** for PETN (-385.0 kcal/kg), printed next to its enthalpy (-407.4), is a different quantity; the preregistration already forbids using the energy.
6. **Klapoetke's PETN heat-of-formation cell** holds values spanning 77 kJ/mol (-461.7 to -538.9 after conversion); no label separates them.
7. **Oxley 2012 Table 8 prints heats of formation beside measured properties** with no marker that they are inputs; the text says literature values. Four sources print the same digits (-538.48, -243.01, -474.8, -371).
8. **The Chavez DNTN enthalpy**: -371 (patent, "measured by combustion calorimetry"), -542 and -580 (Muravyev 2021's calculation and a literature value). One of the three is wrong by about 170 kJ/mol.
9. **ETN's "X-ray density" of 1.553 / 1.55** (Oxley's Table 6 and the Encyclopedia) is 0.22 g/cm3 below every ETN X-ray density read (1.773 at room temperature, 1.827 at 150 K, 1.851 at 140 K); and ETN's helium-pycnometer density (1.7219) is 3 % below the room-temperature X-ray value.
10. **The Encyclopedia's ethyl nitrate gas value** (-122 +/- 1.3 kJ/mol) has the digits of methyl nitrate's NIST value (-122 +/- 1, Ray and Ogg 1959), while NIST's own ethyl nitrate gas value is -155 +/- 3 (Eqk): a probable mix-up, not confirmed on the primary papers.
11. **PETN density in one Encyclopedia cell**: crystal, pycnometer, pressed, loading and TMD values together.
12. **Formula is not identity in COD**: C3H7NO3 (37 header entries) and C4H9NO3 (31) are also the formulas of serine and threonine, not only of propyl and butyl nitrate; only the connectivity pass finds the ester group.
13. **PETN's melting range in the Encyclopedia**: the entry lists melting points from 138.0 to 150 C in one cell (150 is a nanocalorimetric single-crystal value at 2,500 C/s); DSC melts are 140.9 +/- 0.3 (Muravyev SI), 142.9 (Cady and Larson, PETN I), 143 (Oxley).

## 8. Not held: for the owner to fetch

Direct links, with a distinct suggested filename each (the project convention). DOIs were resolved through Crossref on 2026-10-26 by title, author and year. The papers the owner supplied are read and are not listed. They sit in the library under these names: `ornellas1966_petn_detonation_calorimeter`, `zhurova2006_petn_aim_jacs` (+ `_SI`), `cady1975_petn_ii_actab`, `manner2014_etn_structure_cgd` (+ `_SI`), `matyas2015_etn_physical_properties`, `oxley2012_tetranitrate_esters`, `muravyev2021_pccp_thermogravimetry_enthalpies` (+ `_SI`), `ostmark2012_vapor_pressure_of_explosives_review`, `suntsova2017_sublimation_enthalpy_politzer` (+ `_SI`, fetched from the publisher's supplementary-file server).

| what it would settle | link | suggested filename |
|---|---|---|
| the Chavez tetranitrate's formation enthalpy, -371 or -542 (F10): **now held and read, row G12** (`chavez2008.pdf`); it prints -371 with no uncertainty, so the contradiction with Muravyev's computed -542 stays open | https://doi.org/10.1002/anie.200803648 | (held) |
| the further PETN solid enthalpy -593.0 attributed to Huynh, Hiskey, Hartline, Montoya, Gilardi, Angew. Chem. Int. Ed. 43 (2004) (title: Polyazido high-nitrogen compounds: hydrazo- and azo-1,3,5-triazine; DOI not resolved) | (library request) | `huynh2004_polyazido_triazines_angew.pdf` |
| MHN and SHN polymorphs (D03) | https://doi.org/10.1002/prep.202000197 | `mclennan2021_hexanitrates_pep.pdf` |
| azido derivatives of PETN including the four-arm tetraazide (B06 search) | https://doi.org/10.1002/prep.202000265 | `lenz2021_azido_petn_derivatives.pdf` |
| pentaerythritol at very low temperature (a structure of the R1 candidate) | https://doi.org/10.1107/s0108768106008329 | `zhurova2006_pentaerythritol_actab.pdf` |
| pentaerythritol sublimation by polyol (B02, B03): **now held and read, row G11** (`barone1990.pdf`): 161.0 (1.0) at 436 K measured, 163 at 298 K derived | https://doi.org/10.1039/ft9908600075 | (held) |
| alkyl nitrate combustion enthalpies, the ethyl, propyl and isopropyl rows (C08, C09) | https://doi.org/10.1039/tf9575300779 | `fairbrother1957_alkyl_nitrates_heats_of_combustion.pdf` |
| PETN vapour pressure and sublimation, the effusion study behind A04: **now held and read, row G16** (`cundall1978.pdf`; a journal article, J. Chem. Soc., Faraday Trans. 1, 74 (1978) 1339, DOI via Crossref, G13); it also gives RDX, HMX, tetryl and nitroguanidine | https://doi.org/10.1039/f19787401339 | (held) |
| PETN and RDX vapour pressure, the other effusion study (A05): **now held and read, row G15** (`edwards1953.pdf`); its printed PETN latent heat does not follow from its own equation | https://doi.org/10.1039/tf9534900152 | (held) |
| the pentaerythritol combustion behind B01 and the other Medard and Thomas rows (G02): Mem. Poudres 36 (1954) 97-127, a journal, no DOI; where it might be found is in row G17 | (library request; HathiTrust search-only, print at the University of Chicago) | `medard1954_chaleurs_combustion_24_explosives_mempoudres.pdf` |
| nitric ester decomposition and heat of combustion series (the "heat of combustion of XPN" the Flinders thesis cites) | https://doi.org/10.1007/s10973-017-6706-5 | `dong2018_nitric_esters_jtac.pdf` |

**Fetch list additions from Cox and Pilcher's reference codes (DOIs matched through Crossref 2026-10-26):** McEwan and Rigg 1951, 'The Heats of Combustion of Compounds Containing the Tetrazole Ring', https://doi.org/10.1021/ja01154a072 (the nitroguanidine primary behind the book's value); Bradley and Cotson 1953 (Part II), https://doi.org/10.1039/jr9530001684: **now held and read, row G41** (Part I, 1681, was a different paper); Tavernier and Lamouroux, *Mem. Poudres* 37 (1955) 197 (DINA's second value, no DOI).

### 8.1 Primaries to fetch for the nitramine stratum (G19, G20)

**All eleven DOI primaries below were added to the library and read on the page (rows G22-G27); the remaining unread ones are the journals and reports without a DOI, which follow the table.** The nitramines' formation enthalpies are NIST's rows; each cites one primary, and the preregistration's 8.2 needs a page read or two agreeing roots. DOIs below were matched through Crossref on 2026-10-26 by title, authors and year (the matching titles are the NIST citations' own, except where noted). In order of what each settles:

| what it would settle | link | suggested filename |
|---|---|---|
| 4-nitromorpholine, a single-source solid nitramine (-213 kJ/mol) | https://doi.org/10.1007/bf00957051 | `golovanova1988_nitromorpholine_thermochemistry.pdf` |
| four entities at once: EDNA (-101.0), tetryl (41.0), RDX (79.1), HMX (103.0), nitroguanidine (-86.6); settles the tetryl, RDX, HMX and nitroguanidine disagreements. Crossref's title is German ("Thermochemische Untersuchungen an Nitraminen") | https://doi.org/10.1016/0040-6031(73)85078-6 | `krien1973_nitramines_thermochimica_acta.pdf` |
| bis(2,2-dinitropropyl)nitramine (single source, -232) and the second root of bis(trinitroethyl)nitramine (-27); **NIST gives this paper the title 'Thermochemistry of N-Nitrosoamines', so check that it holds the nitramines before relying on it** | https://doi.org/10.1007/bf00850979 | `pepekin1973_nitrosoamines_thermochemistry.pdf` |
| bis(trinitroethyl)nitramine, the first root (-28.0) | https://doi.org/10.1007/bf00963402 | `kustova1981_nitro_compounds_enthalpies.pdf` |
| tetryl, the second root (30.7) | https://doi.org/10.1021/ja01364a018 | `rinkenbach1930_aromatic_nitro_heats.pdf` |
| EDNA and RDX heats of combustion that NIST lists without a formation enthalpy (EDNA -1552 kJ/mol): a third root for each | https://doi.org/10.1021/ie50560a040 | `young1956_organic_nitrogen_combustion.pdf` |
| 1,4-dinitropiperazine (forced into development, but an N-nitro alicyclic series with the ring of RDX) | https://doi.org/10.1007/bf00923193 | `pepekin1974_alicyclic_nitramines.pdf` |
| dimethylnitramine solid and 1-nitropiperidine liquid (both examined compounds; the piperidine paper's title is about the piperidyl radical) | https://doi.org/10.1007/bf00854305 | `matyushin1971_piperidyl_radical.pdf` |
| the liquid-stratum rows: dimethylnitramine -71.1 and diethylnitramine -106 | https://doi.org/10.1039/jr9580000958 | `cass1958_nitroalkanes_nitric_esters_combustion.pdf` |
| methyldinitramine liquid (1.7) | https://doi.org/10.1007/bf00953275 | `korsunskii1989_dinitroalkylamines_decomposition.pdf` |
| HMX 75.0 (examined compound) | https://doi.org/10.1016/s0010-2180(74)80025-8 | `ornellas1974_detonation_calorimeter_cno.pdf` |

**Not read yet, no DOI: where each might be found** (links are catalogue or archive pages found by search on 2026-10-26; several refused automated access, so none is verified to hold the page needed):

| paper | what it settles | where to look |
|---|---|---|
| Medard and Thomas, *Mem. Poudres* 29 (1949) 173-195; 37 (1955) 129-138 (also 35 (1953), 36 (1954), 38 (1955), rows G02, G17) | nitrourea -280.8, nitroguanidine -89.1, EDNA -102.8; pentaerythritol -920.5 | **checked by the owner:** the Gallica series page https://gallica.bnf.fr/ark:/12148/cb343783250/date lists only 1882-1899, so no 1949-1955 volume is online there. **HathiTrust holds v. 36-37 (1954-1955) as search-only**, https://babel.hathitrust.org/cgi/pt?id=mdp.39015023945432, which contains the 1954 paper (36: 97-127) and the 1955 EDNA paper (37: 129-138): search it for 'dinitramine', 'nitrourée' or 'pentaérythrite' to get page numbers; the other volumes (v. 29, 35, 38) need their own catalogue entries from https://catalog.hathitrust.org/Record/000047486. Print copy of v. 36 at the University of Chicago, https://catalog.lib.uchicago.edu/vufind/Record/7641278 |
| Miroshnichenko, Korchatova, Korsunskii, Fedorov, Orlov, Eremenko, Dubovitskii, *Dokl. Akad. Nauk SSSR* 295 (1987) 419-423 | methyldinitramine (a liquid at 298 K; its 0.4 kcal/mol = 1.7 kJ/mol is quoted in the 2009 paper, G29) | **now low priority**: the 2009 paper (https://doi.org/10.1007/s11172-009-0275-0, held and read) carries the value |
| Lobanov and Karmanova, *Izv. Vyssh. Uchebn. Zaved., Khim. Khim. Tekhnol.* 14 (1971) 865-867 | nitroguanidine -97.9 | the journal is now *ChemChemTech*, https://ctj.isuct.ru/ (does not load from either the owner's browser or mine); Crossref returned only a 2023 article of that journal, so the 1971 volume has no DOI |
| Delepine and Badoche, *C. R. Acad. Sci. Paris* 214 (1942) 777-780 | RDX 66.5 | the 1942 *Comptes rendus* may be scanned on Gallica (https://gallica.bnf.fr/) or the Biodiversity Heritage Library (https://www.biodiversitylibrary.org/); that is from memory, not verified, and no volume page was found |
| Handrick, report C-58247 for the Office of the Chief of Ordnance, contract DA-19-020-ORD-47, Arthur D. Little, Cambridge MA, 1956, pp. 467-573 (NIST's citation of 'Part IV') | RDX 61.5, HMX 74.9 | **found on archive.org** as DTIC AD0491366, 'Study of pure explosive compounds. Part IV. Calculation of heat of combustion of organic compounds from structural features...' (listed as 1952; the OCR is poor): https://archive.org/details/DTIC_AD0491366 ; **Stegeman's OSRD 5306 (1945), the 'Stegeman' behind NIST's comments and Koch's ref. 8, is at https://archive.org/details/DTIC_ADB279544** and was read (G34) |
| Korsunsky, Pepekin, Lebedev, Apin, *Izv. Akad. Nauk SSSR, Ser. Khim.* (1967) 525-528, English *Bull. Acad. Sci. USSR* 16 (1967) 509-511 | the paper NIST's dimethylnitramine row says to see (a nitrosamine paper) | **has a DOI after all: https://doi.org/10.1007/bf00905981, now held and read (G28); it is a nitrosamine paper and not a nitramine primary** |

The book NIST re-cites for several of them is Cox and Pilcher (G18).

DOI not resolved: Medard and Thomas 1949, 1953, 1954, 1955 (a journal, see the row above and G17); Miroshnichenko et al. 1985 and 1988 (nitroglycerin); Baroody and Carpenter 1972; Tavernier 1956; Cox and Pilcher 1970 (the book); Fedoroff and Sheffield 1972 (the Encyclopedia of Explosives, the root of Oxley's literature heats of formation). The NIST WebBook is the only place most of these are held.

**Open items downloaded and read** (kept outside the repository): Stark, Flinders University thesis 2022 (open repository, 2.7 MB); Manner et al., Chem. Sci. 2018 on PMC (open access, HTML); a short review of nitric esters on PMC (ACS Omega 2021, HTML); US 8,324,421 B2 (Google Patents HTML); Benz et al., Chem. Eur. J. 2023, LMU repository, CC BY 4.0 (14.4 MB PDF); Burcat, JPCRD 1999, from the NIST reprint server (1 MB PDF). The RSC pages were behind a bot challenge and were not fetched.

## 9. How it was searched

* **Held library** (`tools/library_index.py`, 1,120 files indexed, 14 scans with no text layer, `explosives-propellants-and-pyrotechnics.pdf` among them and unreadable): PETN and its synonyms (441 pages in 42 files), nitroglycerin (486 pages, 52 files), ethylene glycol dinitrate, mannitol hexanitrate, "nitrate ester" (219 pages), pentaerythritol (115 pages) and the four-arm halides. The Encyclopedia's volume 2 is a text PDF; **volumes 1 and 3 are image tables**, read here by OCR for the PETN, PETriN, tetranitramine, TEGDN, XPN, TAP-Ac and tripentaerythritol octanitrate entries; the OCR text was read, the images were not all viewed, so those values carry the inventory's OCR caveat. Pages that carry a value were checked on the rendered page for Acree (pp. 151, 177), Lease (p. 7049), Burcat (p. 118) and Muravyev (p. 15528). The nine papers the owner added after the first pass were read from their text layers, with Muravyev Table 1 checked on the rendered page.
* **Open web:** NIST WebBook thermochemistry, phase-change and gas-phase pages for 19 CAS numbers (one, erythritol tetranitrate, not in the WebBook); Crossref for DOIs; the COD site for four deposited entries' bibliographic fields; the open papers above. The fetch tool's page summariser declined some energetic-compound pages, so NIST pages were read as HTML tables directly.
* **COD:** section 6.

## 10. Verdict

**R1: not met, and not meetable as written; but it can be made testable cheaply.**

1. No `measured` gas-phase enthalpy exists for PETN or for any four-arm quaternary carbon. PETN's own gas value is `derived_from_measured`, -388.1 +/- 1.5 kJ/mol, with a W1-F12 value 7.4 below it; the JPCRD says none is known.
2. The one compound that matches the pattern with oxygen arms, **pentaerythritol**, has a measured solid enthalpy (+/- 2.8) and a polymorph-dependent sublimation (about +/- 16 kJ/mol on the gas value), so its gas value is `derived_from_measured` and about a third the size of the 47-54 kJ/mol PETN miss it would be asked to detect. That is enough to see a gap of that size, and not enough to say what causes it (the quaternary centre or the nitrate arms): pentaerythritol has neither.
3. The **R1 pattern matches a hydrocarbon**, so approval (D8) is the selector.

**R2 and any nitrate-ester family gate: unchanged, and unreachable.** The nitramine stratum was counted (section 5.3, G14, G19-G21): 14 nitramines in NIST (12 solid; after reading the primaries 5 of the 8 eligible are verified) and about 17 more names in the Encyclopedia, against about 150 verified entities needed. For nitrate esters every count is far under 150 verified entities: at least 26 compounds with a measured condensed enthalpy (NIST, through the Keshavarz table), three of them gas-phase, about 40 entries in the Encyclopedia by heading, 73 COD entries in 64 formulas across all temperatures and states, and several of the same series (Lease: 10, Benz: 13) counted as entries.

**What the new evidence changes:** (a) PETN is not "a compound with no calibrant": it is a derived gas-phase point known to 2 kJ/mol, confirmed against a W1-F12 value, and the repository's recorded miss mixes a gas-phase error of about 47-54 kJ/mol with a 12 kJ/mol sublimation-leg error if the ORCA route used 138.0 (to be checked); (b) four printed enthalpies that look like separate sources are one Cheetah input table, and one of them (-371) is contradicted by 171 kJ/mol; (c) ETN's two structures disagree beyond the 8.2 tolerance, so a verified crystal density for ETN does not exist yet; (d) the census window hid 41 further nitrate-ester entries and both non-100 K PETN cells; (e) the label traps in section 7 are new fixtures.

**The smallest further evidence that would change the R1 position**, in order of cost:

1. **An amendment, not data.** Admit `derived_from_measured` for R1 and name pentaerythritol as the candidate calibrant (or list the approved compounds), with its +/- 16 kJ/mol stated. This costs a decision (D8) and one ORCA run of a 17-atom molecule, which would say whether the route misses pentaerythritol by tens of kJ/mol (a quaternary-carbon problem) or not (a nitrate-arm problem).
2. **One more read page:** Barone 1990 is now read (G11); what remains is Medard and Thomas 1954 (the combustion behind B01; a journal, row G17) and Ostmark 2012, to give the R1 anchor a read primary locator under 8.2.
3. **A measurement** of the gas-phase or sublimation enthalpy of pentaerythritol tetra-acetate or the tetrahalides, which would give a heteroatom-armed four-arm compound with a measured value; none was found, and none of the held or open sources reports one.

**A one-line amendment the preregistration needs, for the owner:** section 7's "no per-compound values from a copyrighted table" becomes "single measured values, short runs of values and spreads are quoted as facts with their locators; no table or running text is reproduced". This file already follows the second wording.

Not searched: the nitramine stratum (R2's own condition), polymorph-resolved PETN thermal expansion (it needs the CSD and is the D10 expansion coefficient; F07 gives two derived pairs), and the LMU dissertations (D14).
