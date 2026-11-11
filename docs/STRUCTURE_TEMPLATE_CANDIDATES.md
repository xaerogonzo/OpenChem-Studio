# Structure template candidates

Research inventory only. **Not loaded by the application.** Do not add this file or the sibling JSON to `_SHIPPED_FILES` in `src/openchem/chem/structure_templates.py`.

Companion: [`STRUCTURE_TEMPLATE_CANDIDATES.json`](STRUCTURE_TEMPLATE_CANDIDATES.json). One chemical identity per entry, many `category_ids`. Structures from PubChem PUG REST (record id + URL on every row). ChEBI ids from UniChem source 7 when present (162 of 193). Head of this worktree: `f503ba5b`.

A later, separately reviewed change would convert accepted identities into shipped JSON and, if wanted, multi-category support in `TemplateEntry`. 3D insert and fuse-on-click fragments are separate slices.

## V1 constraints (this checkout)

Shipped catalog: four files (`rings.json`, `amino_acids.json`, `nucleobases.json`, `sugars.json`), **34** entries (7 + 20 + 5 + 2). `TemplateEntry` has a **singular** `category_id`. Kind is `complete_molecule` only. Dummy atoms, query atoms, and S-groups are refused. `molblock_for()` builds a 2D molblock from SMILES, or regenerates 2D when a stored molblock has |z| > 0.05 Å — so a 3D conformer does not survive the current insert path.

Amino acids in V1 are the 20 proteinogenic set (glycine + 19 L), stored as **neutral** carboxylic acid + amine, not the zwitterion. This dump keeps that form. A later note for shipped docs: that set is not “20 L plus glycine.”

This JSON is richer than `TemplateEntry` on purpose (`category_ids`, `category_memberships`, `structure_form`, alkaloid class, validation, both PubChem and ChEBI provenance).

## Inclusion rules

A candidate is in the dump only if all of these hold:

- It is a **named complete molecule**, not a Markush, not a dummy-atom fragment, not a bulk natural-product dump.
- PubChem returned a CID and a SMILES for that identity.
- RDKit parsed and sanitized that SMILES. No atomic-number-0 dummy, no query atoms.
- The structure form is recorded (charge, protonation, stereo or anomer/ring form where it matters, salt vs free).
- Class membership that is **not** a graph property (alkaloids, vitamers, anomers) has a source, or is marked as a browsing decision.

Rejected during QA, not silently rewritten: PubChem CID 5460518 for “cobalamin” is oxidoboron (`BO+`); CID 439386 for “beta-D-mannopyranose” is a sulfate (`C6H12O9S`); CID 439163 / 439242 for xylose are the wrong formulas; CID 6036 is unspecified D-galactose, not the beta pyranose. Those rows cite the replacement CID.

Do not pad a category with analogues to hit a count. Broad categories aimed at about 5–20 recognizable parents; a closed set is enumerated when the names are the point (crowns, C3–C12 cycloalkanes, the proteinogenic acids, the five nucleobases, the four deoxynucleosides).

## Content kinds

| Kind | Meaning | This dump |
|---|---|---|
| **A** | Complete molecules on the V1 insert path | Every accepted entry |
| **B** | Attachment fragments (`*` is a wildcard, not an attach handle) | Category kept; populated with complete-molecule examples only; fuse-on-click deferred |
| **C** | Generic / query (homology, Markush) | Taxonomy only; no fake SMILES |
| **D** | Conformers / 3D | Taxonomy only; PubChem `ConformerCount3D` is stored as availability, not as a template |

## Taxonomy (26 supplied concepts)

| Id | Title | Kind | Treatment |
|---|---|---|---|
| `generic` | Generic | A | Common starters (benzene, pyridine, cyclohexane, water). Not assumed to duplicate the 2D editor’s built-in rings. |
| `rings` | Rings | A | Common ring parents as complete molecules. |
| `cyclopentyl_rings` | Cyclopentyl rings | A (B later) | Cyclopentane and close relatives as molecules. Attachment use deferred. |
| `phenyl_rings` | Phenyl rings | A (B later) | Benzene and phenyl-containing molecules. Attachment use deferred. |
| `amino_acids` | Amino acids | A | Neutral proteinogenic set plus selenocysteine and ornithine. |
| `aromatics` | Aromatics | A | Named aromatics and fused parents. |
| `bicyclics` | Bicyclics | A | Named bicyclic parents (decalins, norbornane, …). |
| `bridged_polycyclics` | Bridged polycyclics | A | Bridged and cage parents (adamantane, cubane, …). |
| `crown_ethers` | Crown ethers | A | 12-crown-4 through 21-crown-7 plus two benzo crowns and 1,10-diaza-18-crown-6. |
| `cycloalkanes` | Cycloalkanes | A | C3–C12 monocycles plus methylcyclohexane and both decalins. |
| `conformers` | Conformers | D | **Unresolved.** V1 `molblock_for` regenerates 2D. Empty. |
| `heterocycles` | Heterocycles | A | Named heterocyclic parents (largest browsing bucket). |
| `polycyclics` | Polycyclics | A | Fused aromatics and cages. |
| `homology_groups` | Homology groups | C | **Deferred.** Query/variable groups are not ordinary SMILES. Empty. |
| `alpha_d_sugars` | Alpha D sugars | A | Named α-D pyranoses/furanoses; ring form and anomer recorded. |
| `beta_d_sugars` | Beta D sugars | A | Named β-D pyranoses/furanoses; ring form and anomer recorded. |
| `deoxynucleosides` | Deoxynucleosides | A | dA, dG, dC, thymidine. |
| `flavonoids` | Flavonoids | A | Subclass parents plus named aglycones. Cyanidin is the flavylium cation. |
| `nucleobases` | Nucleobases | A | Free bases, not nucleosides. Caffeine is **also** here as a xanthine (browsing), classed as a **pseudoalkaloid** for alkaloid policy. |
| `nucleosides` | Nucleosides | A | A, G, C, U, I plus adenosine overlap with cofactors. |
| `organometallics` | Organometallics | A | Metallocenes and (benzene)tricarbonylchromium. SMILES are disconnected ligand + metal as PubChem stores them. 2D-editor display **unverified**. |
| `peptide_building_blocks` | Peptide building blocks | A | Complete Fmoc/Boc amino acids plus the free acids. **No sequencer.** |
| `protoalkaloids` | Protoalkaloids | A | Amino-acid-derived amines whose nitrogen is **not** in a heterocycle. |
| `true_alkaloids` | True alkaloids | A | Amino-acid-derived alkaloids with nitrogen in a heterocycle. |
| `vitamins` | Vitamins | A | Named **vitamers**, not family names. B12 is cyanocobalamin (CID 5311498), not a wrong small-molecule CID. |
| `my_templates` | My Templates | A | Existing **user** library. Not a shipped category. Empty here. |

## Extra categories (created only because they have entries)

| Id | Title | Why |
|---|---|---|
| `pseudoalkaloids` | Pseudoalkaloids | Required by alkaloid policy (caffeine, theobromine, theophylline). |
| `solvents_reagents` | Solvents and reagents | Common named solvents; not empty. |
| `functional_group_examples` | Functional-group examples | Small complete molecules (phenol, acetone, aniline, …). |
| `terpenoids_steroids` | Terpenoids and steroids | Camphor, cholesterol, carotene, two D vitamers. |
| `cofactors_metabolites` | Cofactors and metabolites | ATP, NAD+, adenosine. |
| `coordination_complexes` | Coordination complexes | Cisplatin (no M–C bond) and cyanocobalamin. Separate from organometallics. |

## Counts (accepted entries)

193 identities, all RDKit-accepted. Category memberships overlap, so the sum of `n` is larger than 193.

| Category | n | Status |
|---|---|---|
| generic | 12 | active |
| rings | 21 | active |
| cyclopentyl_rings | 5 | active |
| phenyl_rings | 12 | active |
| amino_acids | 24 | active |
| aromatics | 30 | active |
| bicyclics | 9 | active |
| bridged_polycyclics | 8 | active |
| crown_ethers | 7 | active |
| cycloalkanes | 12 | active |
| conformers | 0 | unresolved |
| heterocycles | 51 | active |
| polycyclics | 19 | active |
| homology_groups | 0 | deferred |
| alpha_d_sugars | 6 | active |
| beta_d_sugars | 7 | active |
| deoxynucleosides | 4 | active |
| flavonoids | 13 | active |
| nucleobases | 7 | active |
| nucleosides | 7 | active |
| organometallics | 5 | active |
| peptide_building_blocks | 26 | active |
| protoalkaloids | 4 | active |
| true_alkaloids | 7 | active |
| pseudoalkaloids | 3 | active |
| vitamins | 15 | active |
| my_templates | 0 | user_library |
| solvents_reagents | 14 | active |
| functional_group_examples | 8 | active |
| terpenoids_steroids | 7 | active |
| cofactors_metabolites | 3 | active |
| coordination_complexes | 2 | active |

## Alkaloids

Class is **biosynthetic origin**, not “nitrogen in a ring.” Source on every alkaloid row: Aniszewski, *Alkaloids: Chemistry, Biology, Ecology, and Applications*, 2nd ed., Elsevier, 2015: **true** = amino-acid nitrogen in a heterocycle; **proto** = amino-acid amine, nitrogen not in a heterocycle; **pseudo** = nitrogen introduced other than from an amino-acid skeleton.

| Id | Class | ChEBI | Notes |
|---|---|---|---|
| morphine | true | CHEBI:17303 | Tyrosine morphinan |
| codeine | true | CHEBI:16714 | |
| atropine | true | (UniChem miss) | Tropane ester |
| cocaine | true | CHEBI:27958 | Tropane |
| nicotine | true | CHEBI:17688 | Mixed ring origins; still true |
| quinine | true | CHEBI:15854 | |
| strychnine | true | CHEBI:28973 | Indole |
| mescaline | proto | CHEBI:28346 | Phenethylamine; N not in a ring |
| ephedrine | proto | CHEBI:15407 | |
| hordenine | proto | CHEBI:5764 | |
| colchicine | proto | CHEBI:27882 | Acetamide nitrogen, not heterocyclic |
| caffeine | pseudo | CHEBI:27732 | Xanthine from nucleotide metabolism |
| theobromine | pseudo | CHEBI:28946 | |
| theophylline | pseudo | CHEBI:28177 | |

Caffeine is **not** in `true_alkaloids`.

## Validation

Every accepted SMILES: RDKit `MolFromSmiles` + `SanitizeMol`; canonical isomeric SMILES; InChIKey (RDKit and PubChem); formula/charge compared to the PubChem record; dummy/query refused.

Recorded, not rejected:

- **cisplatin**: PubChem formula `Cl2H6N2Pt`, RDKit `H6Cl2N2Pt` (element order). Same composition.
- **Metals**: Fe, Ni, Co, Cr, Pt recorded on the organometallic/coordination rows. 2D-editor display is **unverified**. Sandwich compounds are stored as separate ligands + metal ion, as PubChem returns them.
- **cyanidin** and **thiamine**: formal charge +1, matching the source.
- **Amino acids**: PubChem SMILES on these CIDs are the **neutral** forms (`C(=O)O` + `N`), matching V1.

Classification confidence on each membership: `verified` (alkaloid class with literature), `supported` (named biochemical class), or `curation_decision` (OpenChem browsing overlap such as benzene in rings + aromatics + phenyl).

## Closed sets in this dump

- Crown ethers: 12-crown-4, 15-crown-5, 18-crown-6 (`C12H24O6`), 21-crown-7, dibenzo-18-crown-6, benzo-15-crown-5, 1,10-diaza-18-crown-6.
- Cycloalkanes: cyclopropane through cyclododecane (C10 and C12 included), methylcyclohexane, cis- and trans-decalin.
- Sugars: α/β-D-gluco, galacto, manno, xylo (pyranose); α/β-D-ribofuranose; β-D-fructofuranose; 2-deoxy-α/β-D-ribofuranose. Anomer in `structure_form`.
- Nucleobases: A, G, C, T, U, hypoxanthine (plus caffeine overlap).
- Nucleosides: adenosine, guanosine, cytidine, uridine, inosine.
- Deoxynucleosides: dA, dG, dC, thymidine.
- Vitamers: retinol, thiamine, riboflavin, nicotinic acid, nicotinamide, pantothenic acid, pyridoxine, biotin, folic acid, ascorbic acid, ergocalciferol, cholecalciferol, α-tocopherol, phylloquinone, cyanocobalamin.

## Open questions (not this task)

- Whether `TemplateEntry.category_id` becomes a list when shipping this inventory.
- How (or whether) PubChem 3D conformers are inserted without `molblock_for` flattening them.
- Fuse-on-click for cyclopentyl/phenyl vs keeping complete molecules only.
- Live 2D-editor display of sandwich compounds and cyanocobalamin.
- Atropine and cyanocobalamin ChEBI ids (UniChem source 7 did not return them here).
- Homology groups: needs a query encoding, not SMILES.

Temporary fetch helpers (`_research_fetch.py` and friends) stay untracked and are not a runtime dependency.
