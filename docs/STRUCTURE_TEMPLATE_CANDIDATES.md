# Structure template candidates

Research inventory only. **Not loaded by the application.** Do not add this file or the sibling JSON to `_SHIPPED_FILES` in `src/openchem/chem/structure_templates.py`.

Companion: [`STRUCTURE_TEMPLATE_CANDIDATES.json`](STRUCTURE_TEMPLATE_CANDIDATES.json). Schema version 2. One chemical identity per entry, many `category_ids`.

This revision is an **identity-correction pass**. RDKit parse/sanitize is recorded separately from identity verification. A valid graph is not evidence that the record is the intended compound.

## QA summary

| Measure | Count |
|---|---|
| Candidate records | 195 |
| PubChem records retrieved | 195 |
| RDKit parse/sanitize passed | 195 |
| Identity verified | 193 |
| Identity mismatch | 0 |
| Identity unresolved | 2 |
| Accepted candidates (identity + RDKit) | 193 |
| Editor-ready (accepted, not coordination-special) | 186 |
| Stereochemistry reviewed | 41 |
| Stereochemistry not applicable | 123 |
| Stereochemistry not reviewed | 31 |
| Editor display tested | 0 |
| Coordination/metal special handling | 7 |
| PubChem CID replaced vs previous draft | 30 |
| ChEBI independently verified (OLS name) | 151 |

Do not read `rdkit_structure_accepted` as overall acceptance. `validation.candidate_accepted` requires `identity.status == verified` as well.

### CID replacements this pass

| Id | Intended name | Previous CID | New CID | PubChem title |
|---|---|---|---|---|
| `pyrrole` | Pyrrole | 802 | 8027 | Pyrrole |
| `benzothiophene` | Benzo[b]thiophene | 9224 | 7221 | Benzo(B)Thiophene |
| `cyclopropane` | Cyclopropane | 6354 | 6351 | Cyclopropane |
| `cyclopentadiene` | Cyclopentadiene | 6491 | 7612 | Cyclopentadiene |
| `cyclooctane` | Cyclooctane | 11717 | 9266 | Cyclooctane |
| `cyclodecane` | Cyclodecane | 13611 | 9267 | Cyclodecane |
| `cis_decalin` | cis-Decalin | 9244 | 7044 | Decalin |
| `trans_decalin` | trans-Decalin | 9243 | 7044 | Decalin |
| `norbornene` | Norbornene | 82466 | 638051 | Norbornene |
| `bicyclo_2_2_2_octane` | Bicyclo[2.2.2]octane | 13609 | 9235 | Bicyclo(2.2.2)octane |
| `bicyclo_1_1_1_pentane` | Bicyclo[1.1.1]pentane | 139601 | 136153 | Bicyclo(1.1.1)pentane |
| `barrelene` | Barrelene | 136091 | 136326 | Barrelene |
| `camphor` | (1R,4R)-Camphor | 2537 | 159055 | D-Camphor |
| `perylene` | Perylene | 9115 | 9142 | Perylene |
| `coronene` | Coronene | 9112 | 9115 | Coronene |
| `15_crown_5` | 15-Crown-5 | 27224 | 36336 | 15-Crown-5 |
| `21_crown_7` | 21-Crown-7 | 27225 | 93160 | 1,4,7,10,13,16,19-Heptaoxacycloheneicosane |
| `dibenzo_18_crown_6` | Dibenzo-18-crown-6 | 24847 | 26541 | Dibenzo-18-crown-6 |
| `benzo_15_crown_5` | Benzo-15-crown-5 | 24846 | 84197 | 1,4,7,10,13-Benzopentaoxacyclopentadecin, 2,3,5,6,8,9,11,12-octahydro- |
| `1_10_diaza_18_crown_6` | 1,10-Diaza-18-crown-6 | 27351 | 72805 | Diaza-18-crown-6 |
| `l_selenocysteine` | L-Selenocysteine | 6326983 | 25076 | L-Selenocysteine |
| `fmoc_glycine` | Fmoc-Glycine | 94144 | 93124 | Fmoc-Gly-OH |
| `fmoc_l_alanine` | Fmoc-L-alanine | 100113 | 6364642 | N-((9H-Fluoren-9-ylmethoxy)carbonyl)-L-alanine |
| `boc_glycine` | Boc-Glycine | 84944 | 78288 | N-(tert-butoxycarbonyl)glycine |
| `boc_l_alanine` | Boc-L-alanine | 6950269 | 85082 | Tert-butoxycarbonylalanine |
| `guanine` | Guanine | 764 | 135398634 | Guanine |
| `hypoxanthine` | Hypoxanthine | 790 | 135398638 | Hypoxanthine |
| `isoflavone` | Isoflavone | 70377 | 72304 | Isoflavone |
| `naringenin` | Naringenin | 932 | 439246 | Naringenin |
| `cyanocobalamin` | Cyanocobalamin | 5311498 | 166596686 | Cyanocobalamin |

### Not identity-verified

| Id | Status | Rationale |
|---|---|---|
| `cis_decalin` | unresolved | PubChem name queries for cis- and trans-decalin both resolve to unspecified CID 7044 (Decalin), formula C10H18, with no stereochemistry in the SMILES. Not identity-verified as the named stereoisomer. |
| `trans_decalin` | unresolved | PubChem name queries for cis- and trans-decalin both resolve to unspecified CID 7044 (Decalin), formula C10H18, with no stereochemistry in the SMILES. Not identity-verified as the named stereoisomer. |

## V1 constraints

Shipped catalog remains four files and **34** entries. `TemplateEntry` still has a singular `category_id`. Dummy/query/S-group refused. `molblock_for()` flattens 3D. Amino acids in V1 and in this dump are **neutral** carboxylic acid + amine, not zwitterions.

This JSON remains richer than `TemplateEntry`.

## Inclusion and identity rules

- Intended OpenChem `name` is preserved. Never rename the entry to match a wrong PubChem title.
- PubChem is queried by intended name (and aliases), not by a guessed CID.
- Identity verification needs a name-resolved record, a title/synonym overlap, and an expected-formula match when a formula is specified.
- ChEBI is resolved from the intended name via OLS, not from UniChem of the selected CID.
- `as_source` on tautomer/protonation/salt is provenance, not a completed review (`status: not_reviewed` unless independently decided).

## Content kinds

| Kind | Meaning |
|---|---|
| **A** | Complete molecules |
| **B** | Attachment fragments (deferred; `*` is a wildcard) |
| **C** | Query / homology (not ordinary SMILES) |
| **D** | Conformers / 3D (availability only) |

## Taxonomy

| Id | Title | Kind | Status | n | Description |
|---|---|---|---|---|---|
| `generic` | Generic | A | active | 12 | Common starter molecules useful on an empty canvas. |
| `rings` | Rings | A | active | 21 | Common ring systems as complete molecules. |
| `cyclopentyl_rings` | Cyclopentyl rings | A | active | 4 | Cyclopentane and cyclopentene complete molecules, not five-membered heterocycles. |
| `phenyl_rings` | Phenyl rings | A | active | 13 | Benzene and phenyl-containing complete molecules. Attachment-fragment use is deferred. |
| `amino_acids` | Amino acids | A | active | 22 | Free proteinogenic amino acids plus selenocysteine and ornithine (neutral carboxylic acid + amine). Protected derivatives are not in this category. |
| `aromatics` | Aromatics | A | active | 31 | Representative aromatic molecules and scaffolds. |
| `bicyclics` | Bicyclics | A | active | 9 | Recognizable bicyclic parent structures. |
| `bridged_polycyclics` | Bridged polycyclics | A | active | 8 | Bridged and cage-like polycycles. |
| `crown_ethers` | Crown ethers | A | active | 7 | Common crown ethers and selected derivatives. |
| `cycloalkanes` | Cycloalkanes | A | active | 14 | Saturated monocycles C3–C12 inclusive, plus methylcyclohexane. cis/trans-Decalin are listed separately and are not identity-verified as stereoisomers. |
| `conformers` | Conformers | D | unresolved | 0 | Conformational templates need 3D coordinates; V1 molblock_for regenerates 2D. |
| `heterocycles` | Heterocycles | A | active | 51 | Representative heterocyclic complete molecules. |
| `polycyclics` | Polycyclics | A | active | 20 | Fused and cage polycycles. |
| `homology_groups` | Homology groups | C | deferred | 0 | Query/variable-group concept. Not ordinary SMILES. Not populated. |
| `alpha_d_sugars` | Alpha D sugars | A | active | 6 | Named alpha-D sugars with ring form and anomer recorded. |
| `beta_d_sugars` | Beta D sugars | A | active | 7 | Named beta-D sugars with ring form and anomer recorded. |
| `deoxynucleosides` | Deoxynucleosides | A | active | 4 | Named 2'-deoxyribonucleosides. |
| `flavonoids` | Flavonoids | A | active | 13 | Named flavonoid aglycones and subclass parents. |
| `nucleobases` | Nucleobases | A | active | 6 | Free nucleobases (A, G, C, T, U, hypoxanthine). Not methylxanthine alkaloids. |
| `nucleosides` | Nucleosides | A | active | 5 | Named ribonucleosides only (not deoxynucleosides or nucleotides). |
| `organometallics` | Organometallics | A | active | 5 | Selected compounds with metal-carbon bonds. Not editor-ready until coordination display is tested. |
| `peptide_building_blocks` | Peptide building blocks | A | active | 26 | Free amino acids and complete N-protected amino acids (Fmoc/Boc). No sequence builder. |
| `protoalkaloids` | Protoalkaloids | A | active | 2 | Amino-acid-derived amines whose nitrogen is not in a heterocycle, where the assignment is not disputed. |
| `true_alkaloids` | True alkaloids | A | active | 7 | Amino-acid-derived alkaloids with nitrogen in a heterocycle. |
| `pseudoalkaloids` | Pseudoalkaloids | A | active | 3 | Nitrogenous metabolites whose nitrogen is not introduced as part of an amino-acid skeleton (Aniszewski 2015). Compound-level assignments may be unresolved. |
| `vitamins` | Vitamins | A | active | 15 | Named vitamers, not family names. |
| `my_templates` | My Templates | A | user_library | 0 | Existing user store. Not a shipped category. |
| `solvents_reagents` | Solvents and reagents | A | active | 14 | Common laboratory solvents and simple reagents. |
| `functional_group_examples` | Functional-group examples | A | active | 8 | Small complete molecules illustrating common functional groups. |
| `terpenoids_steroids` | Terpenoids and steroids | A | active | 7 | A few recognizable terpenes and steroids. |
| `cofactors_metabolites` | Cofactors and metabolites | A | active | 3 | A few named cofactors, including nucleotides such as ATP. |
| `coordination_complexes` | Coordination complexes | A | active | 2 | Metal complexes without requiring a metal-carbon bond. Not editor-ready until coordination display is tested. |

Category `entry_ids` are derived from `category_ids` on identity-verified **or** still-listed candidates (mismatches remain in the file until replaced). Counts below are **identity-verified** memberships.

| Category | Identity-verified n |
|---|---|
| `generic` | 12 |
| `rings` | 21 |
| `cyclopentyl_rings` | 4 |
| `phenyl_rings` | 13 |
| `amino_acids` | 22 |
| `aromatics` | 31 |
| `bicyclics` | 7 |
| `bridged_polycyclics` | 8 |
| `crown_ethers` | 7 |
| `cycloalkanes` | 12 |
| `conformers` | 0 |
| `heterocycles` | 51 |
| `polycyclics` | 20 |
| `homology_groups` | 0 |
| `alpha_d_sugars` | 6 |
| `beta_d_sugars` | 7 |
| `deoxynucleosides` | 4 |
| `flavonoids` | 13 |
| `nucleobases` | 6 |
| `nucleosides` | 5 |
| `organometallics` | 5 |
| `peptide_building_blocks` | 26 |
| `protoalkaloids` | 2 |
| `true_alkaloids` | 7 |
| `pseudoalkaloids` | 3 |
| `vitamins` | 15 |
| `my_templates` | 0 |
| `solvents_reagents` | 14 |
| `functional_group_examples` | 8 |
| `terpenoids_steroids` | 7 |
| `cofactors_metabolites` | 3 |
| `coordination_complexes` | 2 |

### Category corrections in this pass

- Protected Fmoc/Boc alanines removed from `amino_acids`; they stay in `peptide_building_blocks` once identity-verified.
- `peptide_building_blocks` includes free amino acids and protected derivatives.
- Thymidine is only in `deoxynucleosides`. ATP is only in `cofactors_metabolites` (a nucleotide, not a nucleoside).
- Caffeine is not a nucleobase; it remains a pseudoalkaloid / heterocycle.
- Tetrahydrofuran is not in `cyclopentyl_rings`.
- Cyclononane and cycloundecane added so C3–C12 monocycles are complete. cis/trans-Decalin are unresolved stereoisomers (PubChem parent only).

## Alkaloids

Class is biosynthetic origin (Aniszewski 2015), not nitrogen-in-a-ring. Book citation, no DOI in this dump. Ephedrine and colchicine are **unresolved** at compound level (see their `classification_source`). Caffeine remains pseudo.

| Id | Class | Class status | ChEBI | Identity |
|---|---|---|---|---|
| `morphine` | true | verified | CHEBI:17303 | verified |
| `codeine` | true | verified | CHEBI:16714 | verified |
| `atropine` | true | verified | CHEBI:16684 | verified |
| `cocaine` | true | verified | CHEBI:27958 | verified |
| `nicotine` | true | verified | CHEBI:18723 | verified |
| `quinine` | true | verified | CHEBI:15854 | verified |
| `strychnine` | true | verified | CHEBI:28973 | verified |
| `mescaline` | proto | verified | CHEBI:28346 | verified |
| `ephedrine` | — | unresolved | — | verified |
| `hordenine` | proto | verified | CHEBI:5764 | verified |
| `colchicine` | — | unresolved | CHEBI:23359 | verified |
| `caffeine` | pseudo | verified | CHEBI:27732 | verified |
| `theobromine` | pseudo | verified | CHEBI:28946 | verified |
| `theophylline` | pseudo | verified | CHEBI:28177 | verified |

## Organometallics and coordination

Kept in the research inventory. `editor_ready` is false while PubChem SMILES are disconnected ligand/metal components. Cisplatin `N.N.Cl[Pt]Cl` does not encode Pt–N bonds or cis geometry. Cyanocobalamin similarly splits Co/CN from the corrin. These are not insertable V1 templates.

## Open questions (not this task)

- Shipping any of this into `_SHIPPED_FILES`.
- Multi-`category_id` in `TemplateEntry`.
- 3D insert; attachment fragments; homology encoding.
- Stereo-specific PubChem records for cis- and trans-decalin.
- Compound-level alkaloid class for ephedrine and colchicine.

