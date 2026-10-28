# Literature record for the restart-v3 preregistration (S-H and bromine references), 2026-10-27

This is the record of what was searched, fetched and read for `PREREGISTRATION.md` sections 6 and 7, so that another session can reuse it without redoing the work. **Status of each source is stated separately for what was read in the PDF and what came only from a search summary.** Values quoted here are the ones the sources print; every derived number is in `references.json` and recomputed by `tests/test_restart_v3_references.py`.

## Where the files are

* **PDFs:** `D:\Xaero Stuff\Documents\Sci Downloads\`, named `authorYEAR[_X].pdf`, and registered with a `local` field in `docs/sources.toml`: `nicovich1992`, `chiang2004`, `leplat2013`, `ervin2015` (+ `_SI`), `eyet2009`, `janousek1980`, `moran1988`, `borgesdossantos2002`, `lim2007`, `andress2026` (+ `_SI`), `espinosagarcia1999`, `seetula2000_abinitio_TS`, `seetula2003_CH2Br_CHBrCl`, `seetula2008_CHBr2_CH3CHBr`, and Luo's handbook (its long file name is in the `luo2007` entry).
* **Text extracts** (outside Git): `D:\_scratch\thiyl_probe_records\literature_text\<name>.txt`. Made with `uvx --with pymupdf python -I -c "import pymupdf; ..."`, one `=====PAGE n=====` marker per page. **The extraction drops minus signs and mangles superscripts and `+-`**, so never take a signed enthalpy from it without looking at the PDF. `luo.txt` is 2.4 MB; Table 3.5 (C-H bond energies of halogenated hydrocarbons) is at printed pages 62 to 67, Table 8.1 (S-H) at PDF pages 454 to 459, Table 8.3 (S-C) at printed pages 436 to 437.
* **Not obtainable:** the ATcT site returned 403 to the fetch tool; the SI of `eyet2009` (Appendix A of the article) and the publisher pages of several papers did too. Crossref lookups worked for four or five calls and then returned 429.

## What each source gave (read in the PDF unless said otherwise)

| key | what it gives | used for |
|---|---|---|
| `nicovich1992` | D(CH3S-H) 87.35 +- 0.58 kcal/mol at 298 K (85.96 +- 0.68 at 0 K), 2 sigma; dfH298(CH3S) 29.78 +- 0.44 | the first run's methanethiol S-H; the anchor Arm D shares |
| `ervin2015` | D298(C2H5S-H) 364.7 +- 2.2 kJ/mol (87.16 +- 0.53 kcal/mol, about the 95% level); Table 3 acidities of the thiols; anchors H2S, CH3SH (D0 359.7 +- 1.5 kJ/mol), pyrrole. The copy is the Just Accepted manuscript. | Arm D reference |
| `moran1988` | EA(CH3CH2S) 1.947 +- 0.013 eV (Table VIII); no propylthiyl | the electron affinity Ervin used |
| `janousek1980` | EA(C2H5S) 1.953 +- 0.006, n-C3H7S 2.00 +- 0.02, i-C3H7S 2.02 +- 0.02, t-C4H9S 2.07 +- 0.02 eV; its own S-H values (88.6, 88.7, 88.4 +- 2 kcal/mol) are older and superseded | propanethiol references |
| `eyet2009` | Table 1: acidities of CH3SH, C2H5SH, n-C3H7SH, (CH3)2CHSH, (CH3)3CSH and others to +-0.5 kcal/mol; ethanethiol acidH298 356.0 | cross-check of Ervin's acidities; agrees within error |
| `borgesdossantos2002` | DH(PhS-H) 349.4 +- 4.5 kJ/mol (gas phase from solution calorimetry); literature range 331 to 349 | thiophenol, excluded |
| `lim2007` | D0(S-H) of thiophenol 76.8 +- 0.3 kcal/mol (Table II), D0(S-D) 79.6 +- 0.3, at 0 K | thiophenol, excluded |
| `andress2026` | Table 2: calculated C-H bond energies of 30 halomethanes (FPD/Q5 and G3(MP2)) beside Luo's values and ATcT; no calculated uncertainty | bromine comparison |
| `espinosagarcia1999` | calculated DH298 CH3Br 101.7 +- 1.4, CH2ClBr 98.7 +- 1.9 kcal/mol | bromine comparison |
| `leplat2013` | R + HBr kinetics disputed; C2H5 formation enthalpy 117.3 +- 3.1 kJ/mol (third law) against 120.7 (Seetula); its second-law treatment fails an entropy check | why the bromine arm is reported only |
| `chiang2004` | CH2Br+ appearance energy 11.22 eV from CH2Br2; IE(CH2Br2) 10.25 eV; Table IV of radical formation enthalpies from an earlier reference | no new radical data |
| Luo Table 3.5 | independent determinations of the bromine C-H bonds (bromination, photobromination, electron ionization, reviews), with printed uncertainties where given | `references.json` |
| Luo Table 8.1 / 8.3 | recommended S-H only for H2S and CH3SH; benzenethiol 79.4 to 83.5 and S-C bonds | context |

## NIST Chemistry WebBook (fetched 2026-10-27, through a summarising fetch tool: re-check the page before quoting a number)

* Ethanethiol, `https://webbook.nist.gov/cgi/cbook.cgi?ID=C75081`: gas-phase dfH = -11.03 kcal/mol (calorimetry, McCullough et al. 1957, no uncertainty listed); recommended IE 9.31 +- 0.03 eV; gas acidity of C2H5SH, dH = 355.7 +- 2.1 (Janousek 1980) and 355.2 +- 2.2 (Bartmess 1979) kcal/mol, dG = 348.9 +- 2.0.
* Ethylthio radical, `ID=C14836227`: EA 1.9530 +- 0.0040 (Janousek 1980, laser photodetachment), 1.97 +- 0.13 (Bartmess 1979), 1.947 +- 0.013 eV (Moran and Ellison 1988); IE 9.6 +- 0.8 eV; **no formation enthalpy**.
* Propylthio radical, `ID=C4985584`: EA 2.000 +- 0.020 eV (Janousek 1980), 2.02 +- 0.13 (Bartmess 1979); IE 8.2 +- 0.8; the page does not say which propyl isomer. The 2-propylthio page (`ID=T999904642`) has no electron affinity. The paper `janousek1980` settles the isomers (n-propyl 2.00, isopropyl 2.02).

## An outside literature search, and what it was worth

A general-purpose AI search assistant was given the prompt below on 2026-10-27. **Every claim it made was checked against the PDFs; its summary is not a source.** Held: Ervin's 364.7 +- 2.2 and its source of the electron affinity; Borges dos Santos 349.4 +- 4.5; Lim's 76.8 +- 0.3 (a 0 K value, as it said); Andress Table 2; Espinosa-Garcia's two values. **Not held up:** it called Ervin's ethanethiol value independent of the references we held, but the paper's CH3SH anchor is the Nicovich kinetics value we already used; it gave no propanethiol bond (they come from Ervin's Table 3 plus Janousek's electron affinities, which it did not combine); it listed Seetula's radical values only from secondary citations. **It found nothing for** 2-thiophenethiol, benzyl mercaptan, CH3CH2Br alpha C-H, or CHBr3 beyond the sources already held, and it found no formation enthalpy for C2H5S or C6H5S.

Open leads that no source has been found for: a 2-thiophenethiol S-H D0 of 27 800 +- 100 cm-1 (a search summary only; the paper is not identified).

### The prompt (reusable)

```
I'm preregistering a held-out benchmark of X-H bond dissociation enthalpies (DH298, kcal/mol) for a computational chemistry tool. I need EXPERIMENTAL or very-high-level-theory reference values that are INDEPENDENT of what I already hold. A reference qualifies only if its stated uncertainty is <= 1.0 kcal/mol (1 sigma or clearly stated 2 sigma) and it is gas phase or convertible to gas phase 298 K. Please do not pad: "I found nothing" is a useful answer.

WHAT I NEED (priority order)
1. Thiol S-H bonds, DH298(RS-H): ethanethiol, 1- and 2-propanethiol, thiophenol, 2-thiophenethiol, benzyl mercaptan. Methanethiol is already covered.
2. Bromine C-H bonds: CH3Br, CH2Br2, CH2BrCl, CH3CH2Br (alpha C-H), CHBr3.
3. Any evaluated thermochemical-network or high-level composite (W1/W2/HEAT/focal-point) value for the radicals C2H5S, C6H5S, CH2Br, CHBr2, CBr3, CH3CHBr.

ROUTES THAT MAY WORK (please also find others)
- Negative-ion thermodynamic cycles: gas-phase acidity of the thiol plus electron affinity of the thiyl radical minus IE(H).
- Photofragment / velocity-map imaging of S-H fission, and photoionization thresholds of the radicals, with a D0 -> DH298 conversion.
- Radical + HBr / HI equilibrium kinetics from groups other than Seetula, and any third-law reanalysis of Seetula's values.
- Evaluations (IUPAC, NASA/JPL, Burcat, Luo 2007), theses, proceedings.

WHAT I ALREADY HAVE (do not return as new): ATcT 1.228 (no thiyl or bromo-carbon radicals); Nicovich et al. 1992; Luo's handbook; Seetula 2000, 2003, 2008; Chiang 2004; NIST WebBook ethanethiol entries.

OUTPUT RULES
- For every reference give authors, journal, year, volume, pages, DOI. Only give a DOI you actually found; never construct one.
- Quote the number, its uncertainty, the temperature, whether the uncertainty is 1 sigma or 2 sigma, and where in the paper it appears.
- State the method and whether it is independent of the values I listed.
- Separate what you READ from what you INFER; mark anything you could not open as "from a secondary citation".
- A calculated value is lower grade than a measurement: say which it is and the level of theory.
- End with a short list of what you searched and found nothing for.
```

## Traps found while doing this

* A search summary and the PDF disagreed on a date: the NTRS record of Nicovich 1992 says 1997 (its deposit date); the journal date is 1992.
* A fetch tool answers about a PDF only when the PDF has a text layer and then only by summary; save the PDF and read it with the extraction recipe above.
* A DOI constructed from memory is not a DOI. Every DOI in `docs/sources.toml` for this work was read from the PDF's own first page or resolved through Crossref.


## Literature behind the open decisions (searched 2026-10-28; search summaries only unless a row says READ)

What each open decision of `PREREGISTRATION.md` section 10 rests on, and what a search found. **None of this was read in a PDF**: the publisher pages returned 403 to the fetch tool (as in the first sweep), so a row is a search summary and is marked so. Journal citations are given without DOIs on purpose: `tests/test_sources_are_current.py` fails any DOI that is not registered in `docs/sources.toml`, and none of these is registered because none has been read.

| decision | what a search found | what it would change | state |
|---|---|---|---|
| **The CH3SH anchor of Arm D** (all three references share it: Ervin 2015 anchors the acidity network on D0(CH3S-H) = 359.7 +- 1.5 kJ/mol, which is Nicovich 1992's 85.96 kcal/mol) | A 2025 Chem. Sci. paper (Wu, Zhou, Luo, Yang, Li, Dong and co-workers, "Ultraviolet photodissociation of methanethiol (CH3SH): revealing an S(1D) atom elimination channel", Chem. Sci. 2025, 16, 17165 to 17175; time-sliced velocity-map imaging at 190 to 210 nm; identity checked against Crossref 2026-10-28) **cites D0(H3C S-H) = 30 250 +- 100 cm-1** from another source, which the search summary does not name. That is 361.9 +- 1.2 kJ/mol, **2.2 kJ/mol (0.5 kcal/mol) above the anchor Ervin used** and 1.13 times the combined uncertainty (1.9 kJ/mol): outside one, inside two. | If the newer value were the anchor, the acidity network's absolute scale could move by up to that much, so Arm D's three references could move by up to about 0.5 kcal/mol, in the direction of making the calculation's error more negative (it already runs low). The size of the shift is not known: it is the result of a least-squares network, not a single offset. | **READ 2026-10-28** (`wu2025_ch3sh_s1d_photodissociation.pdf`, with the other two below in Sci Downloads): the value is quoted twice as "D0(H3CS-H) = 30 250 +- 100 cm-1" from reference 33, **S. H. S. Wilson, M. N. R. Ashfold and R. N. Dixon, J. Chem. Phys. 101, 7538 (1994)**, an H-atom photofragment translational-spectroscopy study of CH3SH. **Ervin 2015 did not use it**: his text (read) names two routes for the bond, the Nicovich kinetics (359.7 +- 2.8) and a photofragment route through D0(CH3-S) (359.7 +- 1.7), combined to 359.7 +- 1.5, and cites Wilson, Howe and Ashfold only for the H2S bond. So 30 250 cm-1 is a THIRD measurement; the 1994 paper itself is not held and not read (wanted). The numbers and the sensitivity are in `references.json` (`methanethiol_anchor`) and `PREREGISTRATION.md` section 7. The 2-thiophenethiol value 27 800 +- 100 cm-1 is Ingle et al., Phys. Chem. Chem. Phys. 2016, 18, 11401 (Ashfold group), which suggests the same group's convention for D0 and its +-100 cm-1; READ only as an abstract. |
| **The propylthiyl electron affinities** (+-0.02 eV = 1.9 kJ/mol each, the largest single term in the propanethiol references, from Janousek 1980) | **No experimental measurement newer than 1980 was found.** A B3LYP study gives 1.939 eV (n-propyl) and 2.023 eV (isopropyl) with a stated average error of 0.047 eV; Janousek's values (2.00 and 2.02) agree for isopropyl and differ by 0.06 eV for n-propyl. No slow-electron velocity-map imaging of the propylthiolate anions was found. | A newer photoelectron value with +-0.005 eV would cut the propanethiol uncertainty (now 0.62 kcal/mol) to about 0.45. | Gap. The search was one query; the absence is not established. |
| **Bromoethane's alpha C-H** (the one bromine bond with no calculated value) | The one determination is Seetula and Eskola 2008 (held): 415.0 +- 2.7 kJ/mol, with the 1-bromoethyl formation enthalpy 133.4 +- 3.4 kJ/mol. No high-level calculation of 1-bromoethyl was found (Espinosa-Garcia 1999, held, covers bromomethane and bromochloromethane only; Andress 2026, held, halomethanes only). | A single coupled-cluster value for CH3CHBr would let the bond have a calculated comparison like the other three. | Gap. A chlorine analogue exists (Miyokawa and Tschuikow-Roux 1990: D(CH3CHCl-H) = 96.5 +- 1 kcal/mol), which says nothing about bromine. |
| **An independent S-H measurement for ethanethiol or the propanethiols** (lead now READ, see the rows below this table) | Ethanethiol's S-H fission at 243 nm was imaged (Svrckova, Pysanenko, Lengyel, Rubovic, Kocisek, Poterya, "Photodissociation dynamics of ethanethiol in clusters", Phys. Chem. Chem. Phys. 2015, 17, 25734 to 25741; identity checked against Crossref; the H-atom peak at 1.25 eV with resolved vibrational structure of the CH3CH2S fragment; it is about CLUSTERS, so the single-molecule D0 is a side result at best) but the summary states no D0. An older photodissociation-photoionization study saw S-H cleavage only for thiols of up to five carbons. | A threshold-based D0 for ethanethiol would be the first value independent of the acidity network. | The 2015 paper is a lead (a maximum recoil energy bounds D0 from above); NOT READ. |
| **The 12-atom cap** | Nothing to find: it is a cost limit (6N gradients), not a chemical claim. What is missing is DATA, not literature: section 5 measured radicals of at most 9 atoms, and the 15 radicals of 10 to 14 atoms were never given a numerical job. | Whether an over-cap radical should keep its analytic value with a label rests on how often the analytic M06-2X Hessian is wrong for radicals of that size, which no literature gives and only a calibration on larger radicals could. | Open. Cheapest way to settle it: run the calibration's numerical-versus-analytic comparison on the 15 radicals of 10 to 14 atoms (hours each; section 5 lists them). |


### The three papers that arrived on 2026-10-28 (all READ; Sci Downloads names `wu2025_ch3sh_s1d_photodissociation.pdf`, `svrckova2015_ethanethiol_clusters.pdf`, `ingle2016_2thiophenethiol_sh_fission.pdf`; text in `D:\_scratch\thiyl_probe_records\literature_text\`)

* **`wu2025`** (Wu, Zhou, Luo, Yang, Li, Dong, Hua, Shuai, Dai, Ashfold, Yuan, Yang; Chem. Sci. 2025, 16, 17165): time-sliced velocity-map imaging of the CH3 and S(1D) fragments of CH3SH at 190 to 210 nm. Used for ONE thing: its quotation of D0(H3CS-H) = 30 250 +- 100 cm-1 and the citation behind it (above). It measures nothing about the S-H bond itself.
* **`svrckova2015`** (Svrckova, Pysanenko, Lengyel, Rubovic, Kocisek, Poterya, Slavicek, Farnik; Phys. Chem. Chem. Phys. 2015, 17, 25734; the accepted manuscript): ethanethiol in clusters. **A dead lead for the benchmark**: it states no S-H bond energy (its only enthalpies are the vaporisation enthalpy of ethanethiol, 27.2 kJ/mol, and a comparison value). Kept because the search that found it was about exactly this.
* **`ingle2016`** (Ingle, Karsili, Dennis, Staniforth, Stavros, Ashfold; Phys. Chem. Chem. Phys. 2016, 18, 11401): S-H fission of 2-thiophenethiol, D0 = 27 800 +- 100 cm-1 from a weak H + R(X) signal. Not a reference for any bond in the benchmark. Worth knowing for how this group's thresholds behave: the same paper REASSIGNS an earlier 2-methyl-3-furanthiol value (31 320 +- 100 cm-1) from a bond energy to a threshold for forming the radical's excited state, because a weak higher-energy pedestal had been missed. **A photofragment-spectroscopy D0 is only as good as the identification of its fastest feature**, which is a reason to read Wilson, Ashfold and Dixon 1994 before leaning on 30 250 cm-1.
