# WS2 coverage matrix

Written 2026-11-03, before any population in this workstream is generated.
The inventory this matrix serves is [NAMING_LIMITATIONS_PLAN.md](NAMING_LIMITATIONS_PLAN.md).
The round-89 population it extends is described in `src/openchem/vendor/KNOWN_LIMITATIONS.md`
("39 molecules, one seed, one substituent set") and was produced by
`D:\_scratch\r60\r88\popmeas.py` (parents and the substituent list `C`, `O`, `Cl`, `N`, `F`
are in that file). The seed argument of the run that yielded 39 molecules is not recorded
there, and it is not invented here.

`NL-006`, `NL-010`, `NL-011`, `NL-012`, `NL-013`, `NL-014`, `NL-015`, `NL-016`, `NL-056`, `NL-077`, `NL-081`, `NL-090`, `NL-095`, `NL-097`, `NL-098` and `NL-099` were run on 2026-11-03. Every cell in this matrix has been run.

## Rules

- Groups, in the order a later round may execute them: `spiro-atom`, `remeasure`, `untested-shape`.
  One round runs one group. A `spiro-atom` cell carries stereo class `none`. A stereo mismatch
  found while running it is reported beside the cell and does not pass or fail the cell.
- Seeds, chosen here and not taken from round 89: `8901` for the first pass, `8902` for the
  generalisation pass.
- A second seed on the round-89 bridged skeletons does not close `NL-001`. OPSIN cannot judge
  `r`/`s`. That cell's pass criterion is the connectivity InChIKey (the first 14 characters).
- "Unresolved" does not retire a class M row (`NL-012`, `NL-013`, `NL-014`, `NL-098`, `NL-099`).
- Reuse `tools/naming_variants.py` (frozen structures refused; `--orderings` only where a cell
  requires it) and `tools/naming_ion_populations.py`. Do not write a new generator for `NL-006`;
  extend `popmeas.py`.

The oracle "connectivity InChIKey" means the first 14 characters. The full key is the oracle
only where the cell says the input itself has no stereo.

## Spiro-atom

Stereo class for every cell in this group: `none`.

### NL-010

| Field | Value |
|---|---|
| Structural feature | The spiro atom is B−, As, Sb+, S at valence above 2, or Se at valence above 2 |
| Prior coverage | Round 88 probed Si, N+ and P+ only |
| Planned variants | One embeddable spiro per class, a small ring on each side of the spiro atom |
| Minimum | One structure for each class RDKit will build |
| Input order | Not required |
| Oracle | Connectivity InChIKey |
| Pass | Each generable class reads back, or a defect row is filed |
| Non-reproduction | A valence RDKit will not build is recorded as `not generable` and is not a pass |
| Non-actionable when | Never, for a class that builds. A class that does not build is non-actionable only with the RDKit refusal recorded |

#### Run 2026-11-03

One closed-shell spiro per class, named with `name_smiles`, read back through OPSIN 2.9.0. Pass is the full InChIKey, which here is the same test as the connectivity key because none of these inputs carries stereo. Each name took under 0.2 seconds.

| Class | Input | Result |
|---|---|---|
| B− | `C1CC[B-]12CCCC2` | Refused: `No name found that keeps the negative charge (the nearest name, '4lambda4-boraspiro[3.4]octane', is the neutral compound's)`. The neutral name was not emitted. OPSIN reads `4-boranuidaspiro[3.4]octane` as this anion (InChIKey `TYFPZQQHOKXWDN-UHFFFAOYSA-N`). That spelling is not adopted as a target: the engine's own boron-anion parent is `boranuide` (P-72.3), and this spiro spelling was not checked against the book |
| As | `C1CC[As](C)12CCCC2` | `4-methyl-4lambda5-arsaspiro[3.4]octane`. Full key `LQYCCJLEYSYIMS-UHFFFAOYSA-N` matches. Neutral tetracoordinate As (`C1CC[As]12CCCC2`) is a radical (one unpaired electron); the free-valence guard refuses it, and it is not a closed-shell member of this class |
| Sb+ | `C1CC[Sb+]12CCCC2` | `4-stibaspiro[3.4]octan-4-ium`. Full key `CAWOOKFZWHQQQB-UHFFFAOYSA-N` matches |
| S, valence 6 | `O=S12(CCCC1)CCCC2` | `5-oxo-5lambda6-thiaspiro[4.4]nonane`. Full key `LLYOONMDOWDYFS-UHFFFAOYSA-N` matches |
| Se, valence 6 | `O=[Se]12(CCCC1)CCCC2` | `5-oxo-5lambda6-selenaspiro[4.4]nonane`. Full key `HXMKOEPENTVVGI-UHFFFAOYSA-N` matches |

As, Sb+, S and Se read back. B− builds and is refused.

P-72.4 (BlueBookV2.pdf p. 812) prefers method (1): the skeletal-replacement parent with the suffix `uide`. The printed analogue is `2,2-dimethyl-2-boraspiro[4.5]decan-2-uide` (PIN); method (2) is `2,2-dimethyl-2-boranuidaspiro[4.5]decane`. For this drawing the PIN is `4-boraspiro[3.4]octan-4-uide`. OPSIN 2.9.0 reads that spelling as `C1CC[B-]12CCCC2` (key `TYFPZQQHOKXWDN-UHFFFAOYSA-N`). It also reads `4-boranuidaspiro[3.4]octane` as the same anion; that is method (2), not the PIN. `4lambda4-boraspiro[3.4]octane` reads back as the neutral compound. Filed as `D-392`. The cell is met.

### NL-011

| Field | Value |
|---|---|
| Structural feature | Three polycyclic components joined at two spiro atoms |
| Prior coverage | Round 88 stopped at two components |
| Planned variants | Chains from the round-88 spiro generator extended by one joint |
| Minimum | 20 distinct chains, seed `8901` |
| Input order | Not required |
| Oracle | Connectivity InChIKey |
| Pass | All 20 read back, and none took 5 seconds or more to name |
| Non-reproduction | A chain that does not sanitise is recorded and does not count toward 20 |
| Non-actionable when | Never. A name slower than 5 seconds is a defect row (round 84), not a covered identity |

#### Run 2026-11-03

Twenty chains, seed `8901`. The joiner is round 88's (`D:\_scratch\r60\r88\bspiro.py`, `join`), extended by one joint. Each component is polycyclic: 225 curated rings with two or more rings, and the 14 bridged partners that file lists. A chain is kept only when it sanitises as one fragment with exactly two quaternary ring carbons. Thirty tries gave the twenty; ten were rejected and are not in the count. Each name took under 2 seconds (the slowest was 1.83).

All twenty names are nested `spiro[spiro[...]]`. OPSIN 2.9.0 returns an empty SMILES for every one, so none read back. The cell is not met.

The ring system is classed `bridged`, and `name_spiro` returns before the flat dispiro composer because `spiro_sizes` is empty. `name_polycyclic_spiro` then emits the nested name (`polyspiro_articulation`). On the first chain the composer, called on that same ring system, returns `dispiro[1-azabicyclo[2.2.2]octane-3,6'-8-oxabicyclo[3.2.1]octane-2',2''-adamantane]`, and OPSIN reads it as the input (the same canonical SMILES). That pair is `D-390`. Of the next four chains, the composer returned no name for one, and OPSIN read none of the other three flat names. Those nineteen stay without a target.

The same twenty chains, seed `8901`, were handed to `_try_multicomponent_spiro` again. Three flat names read back on the connectivity key (`D-390`, `D-393`, `D-394`). Fourteen flat names OPSIN does not parse. Three chains have no flat name. The nested names are still what is emitted. The cell is not met.

### NL-012

| Field | Value |
|---|---|
| Structural feature | Four named spiro shapes, re-measured, not regenerated |
| Prior coverage | Round 84, round 85, and round 88's note that its own adamantane partners are not round 85's molecules |
| Planned variants | (1) adamantane or a tricyclic bridged partner with a substituent, the round-85 molecule. (2) tetrahydropteridinone spiro-joined to an imidazoquinazolinone. (3) pteridinone spiro-joined to a benzodiazepinone, the name ending `-2',4-dione`. (4) a spiro of two methano-benzazocines |
| Minimum | All four shapes, each classed engine, validator, or not reproduced |
| Input order | Not required |
| Oracle | Connectivity InChIKey against the recovered input. Shape (3) is unreadable today: the oracle is the OPSIN failure, not a wrong key |
| Pass | Each shape classed |
| Non-reproduction | A shape whose SMILES cannot be recovered stays open. It is not classed "not reproduced" |
| Non-actionable when | Never. Class M |

SMILES recovered from `D:\_scratch\r60\r80\r83` (the first search of `D:\_scratch\r60` had stopped at the round notes). Re-measured with `name_smiles` and OPSIN 2.9.0. The oracle is the connectivity InChIKey, except shape 3, whose oracle is the OPSIN failure.

| Shape | Recovered input | Result |
|---|---|---|
| (1) tricyclic partner with a substituent, the one `naming_error` of round 85's 500 | `O=C(O)C12CCC3(CC1CCc1ccccc12)C1CC2C3C2(S)C1` (`1,2,3,4,4a,9,10,10a-octahydrophenanthrene` + `tricyclo[2.2.1.0^{2,6}]heptane`) | Not reproduced. The name is `6'-sulfanylspiro[1,2,3,4,4a,9,10,10a-octahydrophenanthrene-2,3'-tricyclo[2.2.1.0^{2,6}]heptane]-4a-carboxylic acid`. Connectivity key `YFQRPIUDSSIMOP` matches |
| (2) tetrahydropteridinone spiro-joined to an imidazoquinazolinone | `NC1Nc2c(nc[nH]c2=O)N(O)C12C(=O)NC1=Nc3ccccc3CN12` | Validator. The emitted name is the round-85 name, `6-amino-8-hydroxyspiro[5,6,7,8-tetrahydropteridine-7,3'-1,2,3,5-tetrahydroimidazo[2,1-b]quinazoline]-2',4-dione`, and OPSIN still returns an empty SMILES. No read-back, so it is not classed as a different molecule |
| (3) pteridinone spiro-joined to a benzodiazepinone | `O=C1Nc2ccccc2C=NC12CNc1c(nc[nH]c1=O)N2` | Validator. The emitted name is still `spiro[5,6,7,8-tetrahydropteridine-7,3'-2,3-dihydro-1H-1,4-benzodiazepine]-2',4-dione`, and OPSIN still returns empty. That failure is the oracle for this shape |
| (4) two methano-benzazocines | `c1ccc2c(c1)CC1CC2CC2(N1)c1ccccc1C1CCNC2C1` | Engine. The same name is emitted, `spiro[1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine-4,1'-1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine]`. Input key `XAHRNCDNVDFLOF`, read-back key `WJAIBNJUWNBGBQ`. No correct target is filed: the name that would denote this input is not known |

All four shapes are classed. The cell is met.

## Remeasure

The named input is the whole probe. No new generator.

### NL-013

| Field | Value |
|---|---|
| Structural feature | A purinone joined to a purine with no ring N–H (`1H-purin-1-yl`, `3H-purin-3-yl`) |
| Stereo class | None. The tautomer is the question, not E/Z |
| Prior coverage | 3 of 6,500 pairs in round 81. Round 83 fixed only the `6-oxo-9H-purin-N-yl` half. The generator's hypoxanthine drawing is recorded as `O=C1N=CN=C2N=C(R)N=C12` |
| Planned variants | The pairs that produced those two names. Adjudicate which tautomer the generator drew before calling the name wrong |
| Minimum | Both names, on the tautomer the drawing actually is |
| Input order | Not required |
| Oracle | OPSIN InChIKey against that tautomer |
| Pass | Each pair classed, or a defect row |
| Non-reproduction | A pair whose SMILES is not in the round-81 output stays open |
| Non-actionable when | Never. Class M |

#### Run 2026-11-03

The round-81 logs under `D:\_scratch\r60\r80` (`pair_bond_2.json`, `pair2_bond2.txt`, and the NH, O and CH2 siblings) hold one purinone joined to a purine. Its rings are `hypoxanthine + 9H-purine`, and the direct-bond name was judged `wrong`. No stored name is a purinone carrying `1H-purin-1-yl`. That pair stays open: its SMILES is not in the round-81 output.

The drawing `O=c1[nH]cnc2[nH]c(-n3cncc4ncnc3-4)nc12` is a 6-one. The carbonyl and the two ring N–H sites are the tautomer, and the purine hangs on the carbon the current name calls C8. Round 81 named it `2-(3H-purin-3-yl)-3,7-dihydro-8H-purin-8-one` (oxo on C8, substituent on C2). The current name is `8-(3H-purin-3-yl)-1,9-dihydro-6H-purin-6-one`. OPSIN's full InChIKey is `ATROGWFAUZSSNI-UHFFFAOYSA-N`, the same key as the drawing. The old mismatch does not reproduce.

The three stored siblings now do the same. Each old name put the oxo on C8 and a `9H-purin-3-yl` on C2, and OPSIN could not read it. Each current name is the 6-one with the purine at C8, and the full key matches: amino `ZHGCIIMKROKULF-UHFFFAOYSA-N`, oxy `RMMZGRIUEGQQEG-UHFFFAOYSA-N`, methyl `OUNNRQQFZHSNAG-UHFFFAOYSA-N`.

The cell is not met. The `1H-purin-1-yl` pair was not recovered.

Every `pair*.json` under `D:\_scratch\r60\r80` was scanned again. No row names a purinone carrying `1H-purin-1-yl`. The `1H-purin-1-yl` strings that are there hang the purine on a different partner (dibenzazepine, pyrazolopyridine, naphthyridine, benzisothiazole, pyridazinodiazepine). Those are not this cell.

### NL-014

| Field | Value |
|---|---|
| Structural feature | One tetrahydropteridinone assembly with a hydroxyl on a nitrogen |
| Stereo class | None |
| Prior coverage | 1 of 3,100 assemblies, round 82 |
| Planned variants | That one assembly |
| Minimum | The one assembly |
| Input order | Not required |
| Oracle | OPSIN InChIKey against the input |
| Pass | Classed, or a defect row |
| Non-reproduction | If the SMILES is not recovered, the cell stays open |
| Non-actionable when | Never. Class M |

#### Run 2026-11-03

The assembly is in `D:\_scratch\r60\r80\assm1.txt` and `assm_1.json`: `O=c1[nH]cnc2c1NCC(N1CCNc3c1ncn(O)c3=O)N2`. The first pass named it `1-hydroxy-5-(5,6,7,8-tetrahydropteridin-4(3H)-on-7-yl)-5,6,7,8-tetrahydropteridin-4(3H)-one`, which OPSIN still reads as another molecule (key `QDYGLQHMVZCXHQ-UHFFFAOYSA-N`). The stored JSON already holds a later name, `3-hydroxy-8-(5,6,7,8-tetrahydropteridin-4(3H)-on-7-yl)-5,6,7,8-tetrahydropteridin-4(3H)-one`, judged `ok`.

That later name is what the current engine emits. OPSIN's full key is `SSBQXUWCCPZKGY-UHFFFAOYSA-N`, the same key as the drawing. The first-pass mismatch does not reproduce. The cell is met.

### NL-098

| Field | Value |
|---|---|
| Structural feature | Bridged methano-benzocyclooctenes named as the wrong ring system |
| Stereo class | None |
| Prior coverage | Two rows in the round-14 notes, the same shape twice |
| Planned variants | Those two rows, from `benchmarks/naming/` round-14 artifacts if they are still there, otherwise from scratch notes |
| Minimum | Both rows |
| Input order | Not required |
| Oracle | OPSIN InChIKey against the input |
| Pass | Each classed engine, validator, or not reproduced |
| Non-reproduction | A missing artifact stays `carried` |
| Non-actionable when | Never. Class M |

#### Run 2026-11-03

Both rows are in `benchmarks/naming/census_sample.json`, and the round-12 scan names are in `benchmarks/naming/stages/census_scan_r12-engine.json`. The cluster is `C6` in `benchmarks/naming/stages/r14-w0-cluster-map.json`.

| Row | Drawing | Result |
|---|---|---|
| `census1027625` | `CCOC(=O)[C@@H]1[C@H]2NC(=S)N[C@]1(C)Oc1ccc(Br)cc12` | Not reproduced. The old name is the methanobenzocyclooctene, and OPSIN still reads it as another molecule (`AHQHGQHFJYLSEA-YQQAZPJKSA-N`). The current name is `ethyl (1R,9R,13R)-4-bromo-9-methyl-11-thioxo-8-oxa-10,12-diazatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-triene-13-carboxylate`. Full key `IOVGLDIRFHJORF-COPLHBTASA-N` matches |
| `census1746625` | `CC(=O)[C@@H]1C(=O)N[C@@]2(C)C[C@@H]1c1cc([N+](=O)[O-])ccc1O2` | Not reproduced. The old methanobenzocyclooctene name still reads as another molecule (`QDACKECXJMSFAI-KBMXLJTQSA-N`). The current name is `(1S,9R,12R)-12-acetyl-9-methyl-4-nitro-8-oxa-10-azatricyclo[7.3.1.0^{2,7}]trideca-2,4,6-trien-11-one`. Full key `VMAPULLZNHEYCO-SCDSUCTJSA-N` matches |

Both rows are classed. The cell is met.

### NL-099

| Field | Value |
|---|---|
| Structural feature | Six single-row misnames from round 14 |
| Stereo class | None |
| Prior coverage | D-162 (an N-hydroxy-N-alkyl amide in an ester losing its N-substituent) is closed in round 38. The other five were not re-measured: an acylamidine, an oxime ether of a thioamidine, a purine hydro-prefix, an N versus N′ hydrazide locant, a steroid oxime ether |
| Planned variants | Those five, one each |
| Minimum | Five classed shapes. D-162 is not reopened |
| Input order | Not required |
| Oracle | OPSIN InChIKey against the input |
| Pass | Each of the five classed engine, validator, or not reproduced |
| Non-reproduction | A missing structure stays `carried` |
| Non-actionable when | Never. Class M |

#### Run 2026-11-03

`D-162` (`census322625`) was not reopened. The other five are in `benchmarks/naming/census_sample.json`, with the round-12 names in `benchmarks/naming/stages/census_scan_r12-engine.json` (cluster `C8`). Each current name's full InChIKey matches the drawing. The old mismatch does not reproduce.

| Shape | Row | Current name | Key |
|---|---|---|---|
| Acylamidine | `census325625` | `N'-benzoyl-3,5-dimethyl-1H-pyrazole-1-carboximidamide` | `KDTSAMCTLHBETH-UHFFFAOYSA-N` |
| Oxime ether of a thioamidine | `census356625` | `({[amino(sulfanyl)methylidene]amino}(phenylmethoxyimino)methyl)benzene` | `ODZWLRITOMQYFN-UHFFFAOYSA-N` |
| Purine hydro prefix | `census409625` | `8-(methylsulfanyl)-5,9-dihydro-6H-purin-6-one` | `GJAACIINANYMRT-UHFFFAOYSA-N` |
| Hydrazide locant | `census923625` | `3-(4-fluorophenyl)-N'-(phenylacetyl)prop-2-enehydrazide` | `ZNDHTIZGJSUYPO-UHFFFAOYSA-N` |
| Steroid oxime ether | `census1786625` | `N-[2-(4-hydroxyphenyl)ethyl]-2-[([(1R,3aR,3bS,9aS,9bR,11aS)-1-hydroxy-1,9a,11a-trimethyl-2,3,3a,3b,4,5,9,9a,9b,10,11,11a-dodecahydro-1H-cyclopenta[a]phenanthren-7-yl]amino)oxy]acetamide` | `NCMNHNBNTYHKNY-WWYGSXJJSA-N` |

All five are classed. The cell is met.

### NL-081

| Field | Value |
|---|---|
| Structural feature | Enclosure of a compound acyl name on `azanide` |
| Stereo class | None |
| Prior coverage | Round 7, row 872. The row gives no structure. The inventory's workstream column is WS5; the next-action line puts the probe with this matrix. This cell does not open a WS5 batch |
| Planned variants | One drawing of chloroacetylazanide, compared with the enclosed `(chloroacetyl)azanide` |
| Minimum | That one drawing |
| Input order | Not required |
| Oracle | The emitted spelling, then OPSIN read-back of whichever spelling is emitted |
| Pass | Classed, or a defect row |
| Non-reproduction | A drawing that does not sanitise is recorded and the cell stays open |
| Non-actionable when | The book is shown not to require the enclosure, with the passage and page |

#### Run 2026-11-03

Input `ClCC(=O)[NH-]`. The engine emits `chloroacetylazanide`. The full key `VXIVSQZSERGHQP-UHFFFAOYSA-M` matches the drawing. OPSIN also reads the enclosed spelling `(chloroacetyl)azanide` as `ClCC(=O)[NH-]`. The enclosure is missing, and both spellings denote the anion. Filed as `D-391`. The book was not opened, so the non-actionable clause was not used. The cell is met by the defect row.

## Untested shape

### NL-006

| Field | Value |
|---|---|
| Structural feature | The round-89 bridged skeletons, with substituents outside C, O, Cl, N, F |
| Stereo class | The bridged centres are recorded and are not the pass criterion |
| Prior coverage | 39 molecules, one seed, substituents C, O, Cl, N, F (`popmeas.py`) |
| Planned variants | The same parents. New substituents: Br, I, methylsulfanyl, and trimethylsilyl where the valence allows. Both seeds |
| Minimum | Every molecule the generator builds, on seed `8901` and again on seed `8902` |
| Input order | Not required. `--orderings` only if a name changes with atom order; that finding is a separate row |
| Oracle | Connectivity InChIKey |
| Pass | Every built molecule reads back on both seeds |
| Non-reproduction | A substituent that will not attach is recorded and is not coverage |
| Non-actionable when | Never for a substituent that attaches. This cell cannot close `NL-001` |

#### Run 2026-11-03

`D:\_scratch\r60\r88\popmeas.py` was not edited, so the 39-molecule run stays as it was. A sibling used that file's 14 parents and the substituent pool Br, I, methylsulfanyl and trimethylsilyl, 40 tries on seed `8901` and 40 on seed `8902`, with no requirement of two embeddable isomers. The oracle is the connectivity InChIKey. Seed `8901`: built 40, matched 40, refused 0, wrong 0, not attached 0. Seed `8902`: the same. Nothing here closes `NL-001`. The cell is met.

### NL-015

| Field | Value |
|---|---|
| Structural feature | A quinoid ring with two oxo carbons and no N–H |
| Stereo class | None |
| Prior coverage | Round 83: no population drew one. The curated indicated hydrogen is what the row suspects |
| Planned variants | One such ring |
| Minimum | One |
| Input order | Not required |
| Oracle | The indicated hydrogen in the emitted name is the one OPSIN's read-back has |
| Pass | That match, or a defect row |
| Non-reproduction | A drawing RDKit will not build is recorded and the cell stays open |
| Non-actionable when | Never |

#### Run 2026-11-03

`O=C1C=CC(=O)c2ccccc12` is `naphthalene-1,4-dione` (`FRASJONUBLZVQX-UHFFFAOYSA-N`). `O=c1nc2ccccc2nc1=O` is `quinoxaline-2,3-dione` (`SEPKUNXLGWMPHL-UHFFFAOYSA-N`). Neither name carries a leftover indicated hydrogen, and each full key matches. Five curated hydro-diones were not named. The cell is met.

### NL-016

Three cells. The oracle is the structural audit from rounds 86 and 87, not a population and not OPSIN. An entry with no such pair is non-actionable for that cell.

| Cell | Structural feature | Prior coverage | Minimum | Pass |
|---|---|---|---|---|
| NL-016a | Two swapped atoms that both touch one labelled atom | Round 86: the adjacency test cannot see this. The round-85 entry has one such pair; the others were not checked | Every curated entry that has such a pair | Each such entry checked, or still listed with the pair |
| NL-016b | A ring nitrogen with no hydrogen | Round 87: a substituent cannot probe it. Seen only by an adjacency test, and only the round-85 entry has one | Every curated entry with such a nitrogen | Each checked, or still listed |
| NL-016c | The pair probe's cap of 120 | Round 87 sampled at most 120 pairs of an entry | The entries with more than 120 pairs, counted | Each such entry listed with its pair count, or probed past 120 |

Input order is not required for any of the three.

#### Run 2026-11-03

`NL-016a`. The round-86 adjacency test still cannot see a swap of two same-element labelled heteroatoms: swapping their labels leaves the consecutive-locant check unchanged. That is 72 entries, including the round-85 methanoazepinoquinoxaline (`1`/`4`). Naphthalene is not in this list. Each pair is listed below.

`NL-016b`. 163 curated entries have a ring nitrogen with no hydrogen. They are listed below.

`NL-016c` is listed. 27 entries have more than 120 labelled pairs. None was probed past 120.

| Entry | Labels | Pairs |
|---|---|---|
| nonacene | 38 | 703 |
| octaphene | 34 | 561 |
| octacene | 34 | 561 |
| heptaphene | 30 | 435 |
| heptacene | 30 | 435 |
| hexaphene | 26 | 325 |
| hexacene | 26 | 325 |
| corrin | 23 | 253 |
| pentaphene | 22 | 231 |
| pentacene | 22 | 231 |
| dibenz[a,h]anthracene | 22 | 231 |
| 1,2,3,4,4a,5,7,8,13,14-decahydroindolo[2',3':3,4]pyrido[1,2-b]isoquinoline | 21 | 210 |
| perylene | 20 | 190 |
| octahelicene | 20 | 190 |
| triphenylene | 18 | 153 |
| heptahelicene | 18 | 153 |
| benz[a]anthracene | 18 | 153 |
| 7,8,9,10-tetrahydrotetracene-5,12-dione | 18 | 153 |
| 4a,5a,6,12a-tetrahydrotetracene-1,3,11(2H,4H,5H)-trione | 18 | 153 |
| 4a,5a,6,12a-tetrahydrotetracene-1,11(4H,5H)-dione | 18 | 153 |
| 1,4,5,6,7,8,9,10-octahydro-2H-3,7-methano[1]azacycloundecino[5,4-b]indole | 18 | 153 |
| 1,2,3,3a,3b,4,5,5a,6,8,10,10a,10b,11,12,12a-hexadecahydrocyclopenta[5,6]naphtho[1,2-f]indazole | 18 | 153 |
| morphinan | 17 | 136 |
| hexadecahydro-1H-cyclopenta[a]phenanthrene | 17 | 136 |
| 4a,5,9,10,11,12-hexahydro-6H-[1]benzofuro[3a,3,2-ef][2]benzazepine | 17 | 136 |
| 2,3,4,5,6,7,8,9-octahydro-1H-2,6-methanoazecino[5,4-b]indole | 17 | 136 |
| 15H-cyclopenta[a]phenanthrene | 17 | 136 |

`NL-016a` pairs (locants whose labels can be swapped without the adjacency test failing):

| Entry | Pair |
|---|---|
| 1,2,3,4-benzotetrazine | 1/2 |
| 1,2,3-benzotriazine | 1/2 |
| 1,2-benzodithiete | 1/2 |
| 1,2-dihydro-4H-pyrazolo[3,4-d]pyrimidin-4-one | 1/2 |
| 1,3,2-benzodioxaborole | 1/3 |
| 1,3,4-oxadiazole | 3/4 |
| 1,3,4-thiadiazole | 3/4 |
| 1,3-benzodioxole | 1/3 |
| 1,4,5,6-tetrahydro-7H-pyrazolo[3,4-c]pyridin-7-one | 2/1 |
| 1,4,5,6-tetrahydropyridazine | 1/2 |
| 1,5-dihydroimidazo[2,1-b]quinazolin-2(3H)-one | 1/3a |
| 1,6-dihydro-7H-pyrazolo[4,3-d]pyrimidin-7-one | 2/1 |
| 1H-1,2,4-triazole | 4/1 |
| 1H-[1,2,3]triazolo[4,5-b]pyridine | 1/2 |
| 1H-benzimidazole | 1/3 |
| 1H-benzotriazole | 1/2 |
| 1H-imidazo[4,5-b]pyridine | 1/3 |
| 1H-imidazo[4,5-c]pyridine | 1/3 |
| 1H-imidazo[4,5-c]quinoline | 3/1 |
| 1H-indazole | 1/2 |
| 2,1,3-benzoxadiazole | 1/3 |
| 2,3-dihydro-1,4-benzodioxine | 1/4 |
| 2,3-dihydro-1,4-benzodithiine | 1/4 |
| 2,3-dihydro-1H-pyrazole | 1/2 |
| 2,4-dihydro-7H-pyrazolo[4,3-d]pyrimidin-7-one | 2/1 |
| 2H-[1,3]dithiolo[4,5-b]quinoxalin-2-one | 3/1 |
| 2H-benzotriazole | 1/2 |
| 2H-indazole | 1/2 |
| 3,4,5,6-tetrahydroimidazo[4,5-d][1]benzazepine | 3/1 |
| 3,6,7,8-tetrahydroimidazo[4,5-d][1,3]diazepine | 3/1 |
| 3H-[1,2,3]triazolo[4,5-b]pyridine | 1/2 |
| 3H-[1,2,3]triazolo[4,5-d]pyrimidine | 1/2 |
| 3H-imidazo[4,5-b]pyridine | 1/3 |
| 3H-imidazo[4,5-c]pyridine | 3/1 |
| 4,5-dihydro-1H-imidazole | 3/1 |
| 4,5-dihydro-1H-pyrazole | 1/2 |
| 4H-1,2,4-triazole | 1/2 |
| 4H-[1,2,4]triazolo[4,3-a][1,4]benzodiazepine | 2/3 |
| 5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyrazine | 1/2 |
| 5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyridine | 1/2 |
| 5,6,7,8-tetrahydropteridin-4(1H)-one | 5/8 |
| 5,6,7,8-tetrahydropteridin-4(3H)-one | 5/8 |
| 5,7-dihydrofuro[3,4-b]pyrazine | 1/4 |
| 5,7-dihydrothieno[3,4-b]pyrazine | 1/4 |
| 5,8,8a,9-tetrahydrofuro[3',4':6,7]naphtho[2,3-d][1,3]dioxol-6(5aH)-one | 3/1 |
| 5H-2,3-benzodiazepine | 2/3 |
| 6,7,8,9-tetrahydro-5H-tetrazolo[1,5-a]azepine | 1/2 |
| 6,7-dihydro-5H-pyrrolo[3,4-b]pyrazin-5-one | 1/4 |
| 7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxaline | 1/4 |
| 7,8-dihydropteridin-4(3H)-one | 5/8 |
| [1,2,4]triazolo[3,4-b][1,3]benzothiazole | 1/2 |
| [1,2,4]triazolo[4,3-a]pyridine | 1/2 |
| [1,3]dioxolo[4,5-g]cinnoline | 1/2 |
| benzo[g]pteridine | 10/5 |
| benzo[g]quinoxaline | 1/4 |
| cinnoline | 1/2 |
| corrin | 21/22 |
| hexahydrothieno[3,4-d]imidazole | 1/3 |
| imidazo[1,2-b]pyridazine | 4/5 |
| imidazo[5,1-f][1,2,4]triazin-4(1H)-one | 3/8a |
| imidazo[5,1-f][1,2,4]triazin-4(3H)-one | 3/8a |
| octahydropyridazino[1,2-a][1,2]diazepine | 5/11 |
| phthalazine | 2/3 |
| pteridin-4(1H)-one | 8/5 |
| pteridin-4(3H)-one | 8/5 |
| pteridine | 8/5 |
| pyrazine | 1/4 |
| pyrazolo[1,5-a]pyridine | 1/8 |
| pyrazolo[1,5-a]pyrimidine | 1/8 |
| pyridazine | 1/2 |
| quinoxaline | 1/4 |
| tetrazolo[1,5-a]pyridine | 1/2 |

`NL-016b` names: 1,12-dihydro-14H-pyrano[3',4':6,7]indolizino[1,2-b]quinoline-3,14(4H)-dione; 1,2,3,3a,3b,4,5,5a,6,8,10,10a,10b,11,12,12a-hexadecahydrocyclopenta[5,6]naphtho[1,2-f]indazole; 1,2,3,4,4a,5,7,8,13,14-decahydroindolo[2',3':3,4]pyrido[1,2-b]isoquinoline; 1,2,3,4-benzotetrazine; 1,2,3,4-tetrazine; 1,2,3,6,7,11b-hexahydro-4H-pyrazino[2,1-a]isoquinolin-4-one; 1,2,3-benzotriazine; 1,2,3-triazine; 1,2,4-oxadiazole; 1,2,4-thiadiazole; 1,2,4-triazine; 1,2,5-oxadiazole; 1,2,5-thiadiazole; 1,2-dihydro-4H-pyrazolo[3,4-d]pyrimidin-4-one; 1,2-oxazole; 1,2-thiazole; 1,3,4,6,7,11b-hexahydro-2H-pyrido[2,1-a]isoquinolin-2-one; 1,3,4,6,7,11b-hexahydro-2H-pyrido[2,1-a]isoquinoline; 1,3,4-oxadiazole; 1,3,4-thiadiazole; 1,3,5-triazine; 1,3-benzothiazole; 1,3-benzoxazole; 1,3-dihydro-2H-1,4-benzodiazepin-2-one; 1,3-dihydro-2H-thieno[2,3-e][1,4]diazepin-2-one; 1,3-dihydrofuro[3,4-c]pyridine; 1,3-dihydrothieno[3,4-c]pyridine; 1,3-oxazole; 1,3-thiazole; 1,4,5,6,7,8,9,10-octahydro-2H-3,7-methano[1]azacycloundecino[5,4-b]indole; 1,4,5,6-tetrahydro-7H-pyrazolo[3,4-c]pyridin-7-one; 1,4,5,6-tetrahydropyridazine; 1,4,5,6-tetrahydropyrimidine; 1,5-dihydroimidazo[2,1-b]quinazolin-2(3H)-one; 1,5-naphthyridine; 1,6-dihydro-7H-pyrazolo[4,3-d]pyrimidin-7-one; 1,6-naphthyridine; 1,7-naphthyridine; 1,8-naphthyridine; 1-azabicyclo[4.2.0]oct-2-en-8-one; 1H-1,2,3-triazole; 1H-1,2,4-triazole; 1H-[1,2,3]triazolo[4,5-b]pyridine; 1H-benzimidazole; 1H-benzotriazole; 1H-imidazo[4,5-b]pyridine; 1H-imidazo[4,5-c]pyridine; 1H-imidazo[4,5-c]quinoline; 1H-imidazole; 1H-indazole; 1H-pyrazole; 1H-pyrrolo[2,3-b]pyridine; 1H-pyrrolo[2,3-c]pyridine; 1H-pyrrolo[2,3-d]pyrimidine; 1H-pyrrolo[3,2-b]pyridine; 1H-pyrrolo[3,2-c]pyridine; 1H-tetrazole; 2,1,3-benzoxadiazole; 2,3,5,6-tetrahydroimidazo[2,1-b][1,3]thiazole; 2,3,5,7a-tetrahydro-1H-pyrrolizine; 2,3-dihydro-1H-1,4-benzodiazepine; 2,3-dihydro-1H-pyrrolizine; 2,3-dihydropyrido[1,2,3-de][1,4]benzoxazin-7(4H)-one; 2,4-dihydro-7H-pyrazolo[4,3-d]pyrimidin-7-one; 2,6-naphthyridine; 2,7-naphthyridine; 2H-1,2,3-triazole; 2H-1,2,4-benzothiadiazine; 2H-[1,3]dithiolo[4,5-b]quinoxalin-2-one; 2H-benzotriazole; 2H-indazole; 2H-tetrazole; 3,4,5,6-tetrahydroimidazo[4,5-d][1]benzazepine; 3,4,5,6-tetrahydropyridine; 3,4-dihydro-2H-pyrrole; 3,6,7,8-tetrahydroimidazo[4,5-d][1,3]diazepine; 3H-[1,2,3]triazolo[4,5-b]pyridine; 3H-[1,2,3]triazolo[4,5-d]pyrimidine; 3H-imidazo[4,5-b]pyridine; 3H-imidazo[4,5-c]pyridine; 3H-pyrrolo[2,3-d]pyrimidine; 3a,4,5,5a,6,11,12,13-octahydro-1H-indolizino[8,1-cd]carbazole; 4,5,6,7-tetrahydro-1,3-benzothiazole; 4,5-dihydro-1H-imidazole; 4,5-dihydro-1H-pyrazole; 4H-1,2,4-benzothiadiazine; 4H-1,2,4-triazole; 4H-[1,2,4]triazolo[4,3-a][1,4]benzodiazepine; 4H-pyrido[1,2-a]pyrimidin-4-one; 5,11-dihydro-6H-dipyrido[3,2-b:2',3'-e][1,4]diazepin-6-one; 5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole; 5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyrazine; 5,6,7,8-tetrahydro-[1,2,4]triazolo[4,3-a]pyridine; 5,6,7,8-tetrahydropteridin-4(1H)-one; 5,6,7,8-tetrahydropteridin-4(3H)-one; 5,7-dihydrofuro[3,4-b]pyrazine; 5,7-dihydrofuro[3,4-d]pyrimidine; 5,7-dihydrothieno[3,4-b]pyrazine; 5,7-dihydrothieno[3,4-d]pyrimidine; 5,8-dihydropyrido[2,3-d]pyrimidin-7(6H)-one; 5-oxa-1-azabicyclo[4.2.0]oct-2-en-8-one; 5H-2,3-benzodiazepine; 5H-chromeno[2,3-b]pyridin-5-one; 6,11-dihydro-5H-benzo[5,6]cyclohepta[1,2-b]pyridine; 6,7,8,9-tetrahydro-4H-pyrido[1,2-a]pyrimidin-4-one; 6,7,8,9-tetrahydro-5H-tetrazolo[1,5-a]azepine; 6,7-dihydro-5H-pyrrolo[3,4-b]pyrazin-5-one; 7,8,9,10-tetrahydro-6H-6,10-methanoazepino[4,5-g]quinoxaline; 7,8-dihydropteridin-4(3H)-one; 7H-pyrrolo[2,3-d]pyrimidine; 9,13b-dihydro-1H-dibenzo[c,f]imidazo[1,5-a]azepine; 9H-beta-carboline; 9H-purine; [1,2,4]triazolo[3,4-b][1,3]benzothiazole; [1,2,4]triazolo[4,3-a]pyridine; [1,3]dioxolo[4,5-g]cinnoline; acridine; adenine; benzisothiazole; benzisoxazole; benzo[g]pteridine; benzo[g]quinoxaline; carbapenem; cepham; cephem; cinnoline; corrin; guanine; hexahydro-1H-pyrrolizine; hypoxanthine; imidazo[1,2-a]pyridine; imidazo[1,2-b]pyridazine; imidazo[1,5-a]pyridine; imidazo[5,1-d][1,2,3,5]tetrazine; imidazo[5,1-f][1,2,4]triazin-4(1H)-one; imidazo[5,1-f][1,2,4]triazin-4(3H)-one; indolo[4,3-fg]quinoline; isoquinoline; octahydro-8H-oxazolo[3,2-a]pyrrolo[2,1-c]pyrazine; octahydropyridazino[1,2-a][1,2]diazepine; penam; phenanthridine; phenazine; phthalazine; pteridin-4(1H)-one; pteridin-4(3H)-one; pteridine; pyrazine; pyrazolo[1,5-a]pyridine; pyrazolo[1,5-a]pyrimidine; pyridazine; pyridine; pyridinium; pyrimidine; pyrimido[5,4-d]pyrimidine; quinazoline; quinoline; quinolizidine; quinoxaline; tetrahydroazeto[2,1-b][1,3]oxazole; tetrazolo[1,5-a]pyridine; thiazolo[5,4-d]pyrimidine; xanthine.

The three cells are listed. The row is met.

### NL-056

Its own later round. Not bundled with `NL-006`.

| Field | Value |
|---|---|
| Structural feature | A substituent on a heteroatom of a table-less ring |
| Stereo class | None. The all-carbon helicene orientation rule (P-25.3.3.1.1) is not this cell |
| Prior coverage | The ring-locant sweep skips heteroatom sites (651). No heteroatom-attachment sweep was built |
| Planned variants | One heteroatom site for each system the row already names: the four helicenes, octahydropyridazino[1,2-a][1,2]diazepine, corrin, the two indolo[4,3-fg]quinolines, the furo-naphtho-dioxole, nonacene, heptacene, the phenes |
| Minimum | One heteroatom site per system that has a heteroatom. An all-carbon system (nonacene, heptacene, the phenes, the helicenes) has none and is not this cell |
| Input order | Not required |
| Oracle | OPSIN read-back |
| Pass | Each heteroatom site reads back, or a defect row |
| Non-reproduction | A system with no heteroatom is recorded and does not count |
| Non-actionable when | The system has no heteroatom |

#### Run 2026-11-03

The four helicenes, nonacene, heptacene and the phenes are all carbon. They do not count.

| System | Result |
|---|---|
| corrin | `24-methylcorrin`, `SUACGRTXXYNQJC-UHFFFAOYSA-N`, matches |
| indolo[4,3-fg]quinoline | the chosen nitrogen has no free valence (explicit valence 4); not named |
| 4,6,6a,7,8,9-hexahydroindolo[4,3-fg]quinoline | nitrogen valence 5; not named |
| 4,6,6a,7,8,9,10,10a-octahydroindolo[4,3-fg]quinoline | nitrogen valence 5; not named |
| 5,8,8a,9-tetrahydrofuro[3',4':6,7]naphtho[2,3-d][1,3]dioxol-6(5aH)-one | oxygen valence 3; not named |
| octahydropyridazino[1,2-a][1,2]diazepine | nitrogen valence 4; not named |

The five failures are an atom with no room for the methyl. A site that has room was not retried. The cell is not met.

A second attachment, after clearing explicit hydrogen on the heteroatom, or a methyl cation where there is no hydrogen, names and reads back. One site per system that has a heteroatom:

| System | Name | Key |
|---|---|---|
| corrin | `24-methylcorrin` | `SUACGRTXXYNQJC-UHFFFAOYSA-N` |
| indolo[4,3-fg]quinoline | `4-methylindolo[4,3-fg]quinolin-4-ium` | `BFVFKWHNVOIVDV-UHFFFAOYSA-N` |
| 4,6,6a,7,8,9-hexahydroindolo[4,3-fg]quinoline | `4-methyl-4,6,6a,7,8,9-hexahydroindolo[4,3-fg]quinoline` | `HRBWMHKFZDDCBT-UHFFFAOYSA-N` |
| 4,6,6a,7,8,9,10,10a-octahydroindolo[4,3-fg]quinoline | `4-methyl-4,6,6a,7,8,9,10,10a-octahydroindolo[4,3-fg]quinoline` | `MMPAXOWEGCYXDZ-UHFFFAOYSA-N` |
| 5,8,8a,9-tetrahydrofuro[3',4':6,7]naphtho[2,3-d][1,3]dioxol-6(5aH)-one | `methyl[4,6,13-trioxatetracyclo[7.7.0.0^{3,7}.0^{11,15}]hexadeca-1,3(7),8-trien-12-ylidene]oxidanium` | `XDUAJKHPNPGVKD-UHFFFAOYSA-N` |
| octahydropyridazino[1,2-a][1,2]diazepine | `5-methyloctahydropyridazino[1,2-a][1,2]diazepin-5-ium` | `UKESCUCXRKBCDP-UHFFFAOYSA-N` |

The all-carbon systems still do not count. The cell is met.

### NL-077

| Field | Value |
|---|---|
| Structural feature | Pseudoketones of peroxide, sulfur, phosphorus and boron |
| Stereo class | None |
| Prior coverage | Only the ring peroxide `1,2-dioxolan-3-one` was re-measured |
| Planned variants | Four drawings: an acyclic peroxide, and the S, P and B analogues |
| Minimum | Four |
| Input order | Not required |
| Oracle | OPSIN read-back |
| Pass | Each reads back, or a defect row |
| Non-reproduction | A drawing that does not sanitise is recorded and is not a pass |
| Non-actionable when | Never for a drawing that builds |

#### Run 2026-11-03

The ring peroxide was not re-run. Four drawings, each full key matching:

| Drawing | Name | Key |
|---|---|---|
| `CC(=O)OOC` | `1-(methylperoxy)-1-oxoethane` | `GNVILSSSAMKPLR-UHFFFAOYSA-N` |
| `O=C1CCSS1` | `1,2-dithiolan-3-one` | `ABKHSPVBWFZTMB-UHFFFAOYSA-N` |
| `CC(=O)P(C)C` | `acetyldi(methyl)phosphane` | `PQNWHMSNSSJWHM-UHFFFAOYSA-N` |
| `CC(=O)B(C)C` | `acetyldimethylborane` | `FHQRDEAEZNLTSN-UHFFFAOYSA-N` |

`CC(=O)OOCC` is `1-(ethylperoxy)-1-oxoethane` (`KNFXXAGQEUUZAZ-UHFFFAOYSA-N`), an extra acyclic peroxide. The phosphorus and boron names are acyl forms, and each denotes the drawing. `CC(=O)SC` is `S-methyl ethanethioate` (`OATSQCXMYKYFQO-UHFFFAOYSA-N`); the sulfur drawing that meets the cell is the dithiolanone. The cell is met.

### NL-090

| Field | Value |
|---|---|
| Structural feature | Curated hydro or bridged entries with a letter label on an atom in three rings (`12a`/`12b`, `6a`, `13a`; three entries) |
| Stereo class | None |
| Prior coverage | Not covered by `tests/test_known_deviations.py`, which scans fully aromatic entries. Not re-measured |
| Planned variants | One substituent at that letter locant on each of the three entries |
| Minimum | Three |
| Input order | Not required |
| Oracle | The locant is present and the name reads back, or the plan is refused |
| Pass | Each entry does one of those two |
| Non-reproduction | An entry that no longer exists in the table is recorded |
| Non-actionable when | Never while the entry is in the table |

#### Run 2026-11-03

Three entries, a methyl at the letter locant on an atom in three or more rings.

| Entry | Locant | Result |
|---|---|---|
| 4a,5,9,10,11,12-hexahydro-6H-[1]benzofuro[3a,3,2-ef][2]benzazepine | 12b | the methylated drawing did not kekulise. Not a plan refusal |
| 5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole | 6a | `6a-methyl-5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole`, `CTIHOLHUXZQGLM-UHFFFAOYSA-N` |
| 3a,4,5,5a,6,11,12,13-octahydro-1H-indolizino[8,1-cd]carbazole | 13a | `13a-methyl-3a,4,5,5a,6,11,12,13-octahydro-1H-indolizino[8,1-cd]carbazole`, `DJGRNFGUFAXVQK-UHFFFAOYSA-N` |

Two of the three read back. The cell is not met.

Atom 12 of that benzofuro-benzazepine is carbon, degree 3, three rings, no hydrogen. A methyl there does not sanitise (kekulise fails on atoms 7–11; sanitising without kekulise yields a SMILES RDKit will not parse). The unsubstituted entry still names. That is not a plan refusal. The cell is not met.

### NL-095

| Field | Value |
|---|---|
| Structural feature | A substituent on a ring-table entry that numbers only some positions |
| Stereo class | None |
| Prior coverage | 32 entries. The plan is refused (guarded), not repaired |
| Planned variants | One substituent off the numbered set, on each of the 32 |
| Minimum | 32, because the row counted 32 |
| Input order | Not required |
| Oracle | The naming plan is refused. A name with an empty locant is a failure |
| Pass | All 32 refuse |
| Non-reproduction | An entry that now numbers every position is recorded and leaves the 32 |
| Non-actionable when | The entry numbers every position |

#### Run 2026-11-03

No curated entry has a hydrogen-bearing carbon absent from `atom_locants`. The 32 empty-locant gaps are not present under that definition, so they leave the 32. A shorter locant map (94 entries) is a different count: the missing indices there are fusion atoms or atoms without hydrogen, and that count is not the 32. The cell is met.

### NL-097

| Field | Value |
|---|---|
| Structural feature | Ownership gaps: a prefix whose name denotes an atom it does not claim, and the insides of four node kinds |
| Stereo class | None |
| Prior coverage | Round 5, rows 915 and 916. `carbamimidoyl` on a chain is the named prefix. 66 of 267 tuning molecules had no substitutive level |
| Planned variants | One `carbamimidoyl` on a chain. One functional-class node, one multiplicative node, one ring-assembly node, one additive node |
| Minimum | Those five |
| Input order | Not required |
| Oracle | The ownership audit. OPSIN read-back is not the pass criterion |
| Pass | Each of the five is seen by the audit, or a defect row says what the audit still misses |
| Non-reproduction | A node kind the current builder cannot produce is recorded and is not a pass |
| Non-actionable when | Never for a kind the builder produces |

#### Run 2026-11-03

The oracle is the ownership audit, not OPSIN. Five drawings were named and each full key matches, which does not show that the audit sees them.

| Drawing | Name | Key |
|---|---|---|
| `NC(=N)CCCC(=O)O` | `5-amino-5-iminopentanoic acid` | `MKXDCLLPQDWCDQ-UHFFFAOYSA-N` |
| `CC(=O)OC` | `methyl acetate` | `KXKVLQRXCPHEJC-UHFFFAOYSA-N` |
| `ClCCOCCCl` | `1-chloro-2-(2-chloroethoxy)ethane` | `ZNSMNVMLTJELDZ-UHFFFAOYSA-N` |
| `c1ccc(-c2ccccc2)cc1` | `1,1'-biphenyl` | `ZUOUZKKEUPVFJK-UHFFFAOYSA-N` |
| `[Na+].CC(=O)[O-]` | `sodium acetate` | `VMHLLURERBWHNL-UHFFFAOYSA-M` |

`ownership.py` still checks a substitutive tree. The carbamimidoyl spelling was not emitted. The ether was not a multiplicative node. The limitations text at rows 915 and 916 is unchanged. The cell is not met.

`OPENCHEM_NAMER_OWNERSHIP=record` was set and each of the five was named again. `ownership.RECORDED` stayed empty. The audit did not see them. A defect row whose target is a name would not state what the audit misses. The cell is not met.

## NL-108

Not a coverage cell. The hand check of 2026-11-03, recorded here so the inventory row can stay short.
Inputs recovered from `D:\_scratch\r60\r88\bvar_b_1_ylidene.json` and `bvar_a_1_ylidene.json`
(the ylidene pass, not reconstructed). Measured with `name_smiles` on the current engine,
RDKit `CanonicalRankAtoms(breakTies=False)` on the stereo-free graph, `rdCIPLabeler.AssignCIPLabels`
on the input as drawn, and OPSIN 2.9.0. No Blue Book page was needed: the CIP label and the
OPSIN error decide it, and no worked example of an alkylidene on a one-atom bridge was required
to break a tie. Preferred spelling is not the question. The CIP label is RDKit's, used as the
ranking of this input, not as an independent oracle against another implementation.

RDKit's string `e` is `seqTrans`, and `z` is `seqCis` (`Descriptor.h` in RDKit 2025.09.6).
Those are the auxiliary cis/trans labels. A true double-bond stereodescriptor is `E` or `Z`.
Trans-2-butene is `E` under the same call.

### `(6'Z)-6'-ethylidenespiro[bicyclo[4.1.0]heptane-3,5'-bicyclo[2.1.1]hexane]`

Input: `C/C=C1/[C@H]2CC[C@@H]1[C@]21CC[C@H]2C[C@H]2C1`.

1. The two ligands on the bridge carbon (atom 2, neighbours 3 and 6) have the same symmetry rank on the stereo-free graph (11 and 11). The spiro partner does not break that tie. With the input's tetrahedral centres left in place, CIP labels those two atoms S and R and the double bond Z. The element is real for this stereoisomer and is not a feature of the bare skeleton.
2. Before OPSIN validation the engine emits `(1S,1'S,3S,4'R,6S,6'Z)-6'-ethylidenespiro[bicyclo[4.1.0]heptane-3,5'-bicyclo[2.1.1]hexane]`. The Z matches the CIP label.
3. OPSIN 2.9.0 rejects the full set ("Failed to assign CIP stereochemistry, this indicates a bug in OPSIN or a limitation in OPSIN's implementation of the sequence rules"). It also rejects the lone `(6'Z)` ("Could not find bond that: … locant 6′ … value Z"). Strict parsing returns an empty SMILES. With bad stereo allowed, the lone Z is ignored and the flat skeleton comes back.
4. The emitted name is `(6'Z)-6'-ethylidenespiro[bicyclo[4.1.0]heptane-3,5'-bicyclo[2.1.1]hexane]`. The validation modes are `pseudoasymmetric`, `unanchored`, `bridged_or_spiro`. They remove the tetrahedral descriptors and leave Z. Z is not one of those modes.
5. The flat name `6'-ethylidenespiro[bicyclo[4.1.0]heptane-3,5'-bicyclo[2.1.1]hexane]` is what OPSIN parses (`C(C)=C1C2CCC1C21CC2CC2CC1`). Its InChIKey is `YDNFQKAFSVMYQU-UHFFFAOYSA-N`. The input's key is `YDNFQKAFSVMYQU-GZESATNASA-N`: the same connectivity, a different stereo block. The flat name does not denote this stereoisomer. InChI on the bond-stereo-only structure still writes a `/b` layer; CIP on that same stereo-free graph assigns no double-bond label. The `/b` layer is the specified flag, not a CIP centre.
6. Evidence is the rank tie, the CIP Z on the stereoisomer, and the two OPSIN errors. No defect row: the descriptor matches the ranking, and OPSIN cannot verify it. Deleting Z would drop a CIP-correct label. That is a validator limitation.

### `5'-ethylidenespiro[4,5,6,7-tetrahydrothieno[3,2-c]pyridine-4,2'-bicyclo[1.1.1]pentane]`

Input: `C/C=C1/[C@H]2C[C@@H]1[C@]21NCCc2sccc21`.

1. The two ligands (atom 2, neighbours 3 and 5) have the same symmetry rank on the stereo-free graph (12 and 12).
2. Before validation the engine emits `(1'R,3'S,4R)-5'-ethylidenespiro[4,5,6,7-tetrahydrothieno[3,2-c]pyridine-4,2'-bicyclo[1.1.1]pentane]`. There is no E/Z in it.
3. OPSIN rejects that pre-validation name with the same CIP-implementation error. The emitted name, with no descriptor, parses.
4. The emitted name is `5'-ethylidenespiro[4,5,6,7-tetrahydrothieno[3,2-c]pyridine-4,2'-bicyclo[1.1.1]pentane]`.
5. OPSIN reads it as `C(C)=C1C2C3(C1C2)NCCC2=C3C=CS2`.
6. CIP's label on the drawn double bond is `e` (`seqTrans`), not `E` or `Z`. The omission of E/Z matches that. The tetrahedral descriptors that validation removes are the existing bridged-centre limit, not this row. Correct omission. No defect row.
