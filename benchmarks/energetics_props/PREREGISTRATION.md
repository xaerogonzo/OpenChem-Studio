# Preregistration: energetic materials — crystal density, condensed-phase enthalpy of formation, melting point and decomposition (Phase B)

**Status: DRAFT (merged as a draft; the owner's decisions of 2026-10-26 are recorded in section 15; NOT frozen).** Nothing here has been scored: no corpus has been built, no method has been run, no label has been compared with a prediction. The numbers in sections 8, 9 and 11 are proposals with a stated rationale, to be confirmed or changed in section 14 and then frozen by a dated merge, exactly as `benchmarks/mp_bp/PREREGISTRATION.md` was. After the freeze a number changes only by a dated amendment that says what was seen first.

This document follows Phase A's discipline (`benchmarks/mp_bp/PREREGISTRATION.md`, `RESULT.md`, `CORPUS_REPORT.md`) and **does not touch Phase A**: `benchmarks/mp_bp/` is not edited, its spent holdout is not re-scored, and `tools/validation_rows.py` is not edited either, because Phase A's `freeze.json` records that file's hash (`FROZEN_FILES` in `mpbp_score.py`). Everything Phase B needs beyond that schema lives in new modules next to this file.

## 1. The question

For known energetic compounds, how well do published and project-built estimation methods predict (a) the **crystal density**, (b) the **condensed-phase enthalpy of formation**, (c) the **melting point**, against measured reference values; where do they refuse; and is any of them good enough, on a held-out part of the data, to ship as a narrowly scoped experimental calculator?

**Decomposition onset is a fourth property with an evidence layer and no gate** (section 3.5): no held paper offers a method for it, so it is described, not scored.

A **FAIL**, a **NOT EVALUABLE** and a **PASS** are all complete outcomes. With a corpus of a few hundred compounds the most likely complete outcome for several (method, property) pairs is NOT EVALUABLE, and this document says in advance what that means (section 11.4) so that it is not argued about afterwards.

Out of scope, fixed by Phase A section 11 and not reopened here: ranking compounds, inverse design, any detonation property. **Kamlet-Jacobs detonation stays `NEEDS_INPUT`** (`src/openchem/chem/energetics.py`, refusal `NO_LOADING_DENSITY`, kind `NEEDS_INPUT` in `domain/refusal_kinds.py`) unless a separate, owner-approved product decision defines a new, explicitly named input. No result of this benchmark is that decision.

## 2. Properties, targets, and what each result may be called

Every report line carries: target property, the model output's definition **and its own reference state**, the reference event's definition, `target_matched`, and any proxy assumption.

| # | target | the reference observation is | a method's output must be | gate-eligible methods |
|---|---|---|---|---|
| P1 | `crystal_density` (g/cm3) | a measured crystal density (single-crystal or powder diffraction) at a stated temperature, of a stated form | a crystal density of the neutral compound at a declared temperature | those whose output is a crystal density (section 10) |
| P2 | `enthalpy_formation_condensed` (kJ/mol, 298.15 K, solid) | a measured standard enthalpy of formation of the solid (liquid is a separate stratum), from calorimetry or derived from it with the source saying so | a condensed-phase value; a gas-phase value plus a sublimation step is a **route**, scored as one route with both parts named | direct condensed methods, and routes whose every step has provenance |
| P3 | `melting_point` (K) | a clean melting event (Phase A section 3.2), event kind recorded | a melting point | methods whose output is a melting point |
| P4 | `decomposition_temperature` (K) | a decomposition event with its kind and heating-rate class (section 3.5) | no method held | none: evidence only |

* **Crystal density is not loading density and is not theoretical maximum density.** A method that passes P1 yields a **crystal-density estimate and nothing more**. Its output may not be labelled "density", "loading density" or "TMD" in any report, help text or calculator, and may not be wired to the detonation calculator's `loading_density_g_cm3` input (section 12).
* A **proxy** (a method whose output is a different quantity from the target, as Joback's freezing point was for melting) is reported with `gate_eligible = false`, cannot PASS and cannot promote anything.
* **Temperature basis is part of the output.** A method that returns a density normalised to 200 K (Davis 2024 trained on CSD densities normalised to 200 K, per `docs/research/literature.toml`) is compared with a label at 295 K only as a **proxy for that comparison**, never gate-eligible, because no conversion is preregistered (section 3.2).
* The published methods' parameters are the ones transcribed in the repository or, where not yet transcribed, in the paper, **unmodified**. A change to a parameter table or a group-assignment rule after a diagnostic error has been seen makes a new method version, and a new version needs a new untouched evaluation.

## 3. The reference observation

### 3.1 Value kind is a field, and only some kinds are references

Phase A had one kind of reference (a handbook value). The energetic literature mixes kinds that look identical on the page. Every observation carries `value_kind`:

| `value_kind` | meaning | may be a reference label |
|---|---|---|
| `measured` | the source reports its own measurement, or cites one for this value | yes |
| `derived_from_measured` | computed from a measured quantity by an arithmetic step the source states, **or that this study states with fixed auxiliary values recorded in the row (Amendment 4, 18.2)** (kJ/kg to kJ/mol, combustion energy to formation enthalpy) | yes, lineage kept |
| `computed` | the source says the value is calculated: CBS-4M, G2/G3, DFT, EXPLO5, ACD/Labs, group additivity, "estimated", "theoretical", "predicted" | **no** (reported as a separate stratum, never a gate label) |
| `unlabelled` | the source prints a number and does not say which | **no** for a gate label until a second source or the primary paper settles it |

Why this is not optional: in the held sources the label is usually absent. Klapötke 2017 flags calculated values (CBS-4M, EXPLO5) but Meyer 2016, Agrawal 2010 and Akhavan 2011 print enthalpies of formation with no measured/calculated tag at all (`INVENTORY.md`); Lease 2023's Table 3 enthalpies are DFT values; a paper's "theoretical density" column can hold a measured number (Wang 2024, journal p. 133, says its BFTNAN entry of the theoretical-density column was obtained by measuring the size and weight of a cast column, i.e. it is neither a crystal density nor a theoretical maximum density). `unlabelled` is the default, and promotion to `measured` needs a stated reason on the record.

### 3.2 Crystal density

* Event: a diffraction (or pycnometric, labelled as such) measurement of a **crystal**. Admitted `density_kind`: `crystal_xray`, `crystal_other_measured`. Excluded and counted: `bulk`, `pressed`, `cast`, `loading`, `tmd`, `computed`, `unlabelled`. A cell reading "1.62 (bulk density ...)" is a bulk density even when it sits in a column headed density.
* **Temperature.** Every row carries the temperature of the measurement. The primary cohort is rows with a stated temperature in **273-303 K**. Rows at another temperature are kept, reported as their own stratum, and **not converted**: low-temperature structures are common in the modern literature, and a thermal-expansion difference over 100-200 K is of the same size as the tolerance this benchmark asks of a method. A single fixed volumetric expansion coefficient may be applied in a **sensitivity analysis only**; its value is read from a held source (Hofmann 2002 derives expansion coefficients from the CSD) and recorded as an amendment **before any score exists**. It is not guessed here.
* **Form.** Density is a property of a polymorph (Meyer 2016 prints HMX at 1.84 for the alpha form and 1.90 for the beta form, and FOX-7 at 1.89 and 1.80 for alpha and beta: differences of 0.06-0.09 g/cm3, larger than the criterion of section 11). The label is attached to the form the source names. An entity whose observations name different forms with no statement of which is the ambient-stable form is **unresolved for P1** (Phase A's polymorph rule, kept).
* A value the source prints twice and differently is a **source conflict**, not a choice: Kim 2008 prints picric acid's density as 1.655 in Table 1 (the TNT row's value above it) and 1.771 in Table 3 (`benchmarks/thermophysical/kim2008_crystal_densities.py`). Both are kept; the rules of section 8 decide.

### 3.3 Condensed-phase enthalpy of formation

* Reference state fixed: **solid, 298.15 K, kJ/mol**. A liquid (nitroglycerin) is a separate stratum. A **gas-phase** value is a different property (`enthalpy_formation_gas`); it is never a label for P2 and enters only as the first leg of a route, whose second leg is a sublimation enthalpy with its own provenance (a measured value from a primary report, or a named sublimation method with its own row in the candidate registry).
* **Units are normalised once, with the original kept.** kJ/kg, kcal/kg, kcal/mol and kJ/mol all occur. A value is converted using the molar mass of the *resolved structure*; where a source prints two units for one value and they disagree by more than 1% after conversion, the row is flagged `unit_conflict` and neither is used until the page is read (section 8). The held literature already contains such a case (Agrawal 2010, Table 1.5, CL-20 given in both kJ/kg and kJ/mol; `INVENTORY.md` section 4).
* Meyer 2016 prints both an "enthalpy of formation" and an "energy of formation" per kilogram. They are different quantities; a row records which was read, and the energy is never used as an enthalpy.
* A label from a **computational paper** is `computed` even when it is labelled "experimental" in a table of that paper unless the table cites the measurement.

### 3.4 Melting point

Phase A's rules (section 3.2) apply unchanged: only a clean `melting` event is a label; `melting_with_decomposition`, `decomposition`, estimated and unreached values are not; a range is scored as an interval and never replaced by its midpoint. Two additions:

* **The method of the event is recorded** (capillary, hot stage, DSC onset, DSC peak). A DSC *peak* temperature for a melt is a different number from an onset; different methods are compared only within the same method class in the agreement check of section 8.
* **A melting point at or above the same record's decomposition onset** is not a clean melting point; the record is `melting_with_decomposition` and goes to the evidence layer (this is the rule that keeps TATB-like "melting points" out of P3: Akhavan 2011 prints TATB's melting point as 448.5 C beside a decomposition above 350 C in the same entry).

### 3.5 Decomposition: evidence layer, no gate

`decomposition_temperature` already exists in `tools/validation_rows.py` as a target with a clean event `decomposition`. For energetics that single label hides at least four different quantities: extrapolated DSC onset, DSC peak (exotherm) temperature, ignition or explosion temperature in a timed test, and a thermogravimetric threshold, each depending on heating rate. Agrawal 2010 Table 3.6 prints melting point, ignition temperature and exotherm temperature as separate columns for exactly this reason, and Wang 2024 Table 1 gives TNT's "thermal decomposition peak temperature" at 20 C/min.

Rules, so the evidence is usable later and cannot be mixed now:

* `td_kind` in {`dsc_onset`, `dsc_peak`, `ignition_test`, `tga`, `unknown`} and `heating_rate_k_per_min` (or `unknown`) are required fields. **No conversion between kinds, ever.**
* Two Td values are compared (agreement check, section 8) only within the same `td_kind` and a heating rate within a factor of 2.
* No candidate method for P4 is held (`docs/research/literature.toml` lists none), so P4's status is **`NOT EVALUABLE (no candidate)`** and the deliverable is the described corpus: counts by kind, and the fraction of compounds whose melting precedes decomposition. A method offered later needs its own preregistered amendment before it sees a label.

### 3.6 What is kept for every observation

Original value, unit and qualifiers as printed; the normalised value and the normalisation; `value_kind` and the words that decided it; temperature as printed and normalised; the form and method where stated; source file hash and edition; table, page and entry; primary or secondary and the upstream citation where traced; and `lineage_root` (section 8.3). The original is never discarded after conversion.

## 4. Entities, keys and the statistical unit

Phase A's four keys are kept (entity id; observation id; leakage key = first InChIKey block; split key = the same block), plus one:

5. **Form key** (P1 only): the polymorph or hydrate/solvate label where stated.

**The statistical unit is one unique eligible entity (P2, P3) or one unique (entity, form) (P1) with a verified numeric label.** Every observation is kept; no entity gets more than one vote.

* **Primary-label rule.** For an entity with several admissible observations: the **verified** value of section 8 if one exists; otherwise the primary-source value; otherwise the most recent edition held; if the surviving values then differ by more than the agreement tolerance of section 8.2, the entity is **unresolved** for that property and is not scored in the primary analysis. (Phase A used 1.0 K for temperatures; the tolerances here are in section 8.2.)
* **Sensitivity analysis**: the primary analysis is repeated with each alternative admissible observation in turn; the spread of MAE is reported; nothing is averaged.
* Two books printing one value are two observations of one entity, **and are counted as one observation when they share a lineage root** (section 8.3).

## 5. Population and strata

"**Known energetic compounds with a measured reference value in the held literature**" is the description of the population until the counts are known. No claim is made about all energetic materials, and availability of a clean measurement is itself a selection (the best-characterised compounds are the commercial and military ones; very sensitive, unstable and newly made compounds are under-represented).

* **Organic** here means: contains carbon and no element outside {H, B, C, N, O, F, Si, P, S, Cl, Br, I}. **This is not Phase A's rule** (a carbon with at least one C-H or C-C bond): that rule would have dropped NTO, nitroguanidine, 5-aminotetrazole and 3,6-diaminotetrazine, whose carbons bond only to heteroatoms (held in `tests/test_energetics_props_families.py`). An energetic benchmark that inherited it would lose the nitrogen-rich compounds it is about.
* **Primary set**: neutral, single-component, non-polymeric organic compounds. **Salts (ammonium, hydrazinium, guanidinium and metal salts), hydrates and solvates, co-crystals, organometallics, carbon-free compounds (ammonium nitrate, azides of metals), mixtures, compositions and polymers** are separate reported strata outside the primary gate. Many modern energetic materials are salts; no candidate in section 10 other than Beaucamp 2003 (density) is scoped to them, and that is a finding about coverage, not a reason to widen the gate.
* **Families**, structure only, fixed before any score, by the **first match** in this order (`epb_families.py`, held by `tests/test_energetics_props_families.py`):

| # | family | rule |
|---|---|---|
| 1 | nitrate_ester | `[OX2][N+](=O)[O-]` |
| 2 | nitramine | N-nitro: `[#7;!$([N+](=O)[O-])][N+](=O)[O-]` |
| 3 | nitroaromatic | `[c][N+](=O)[O-]` (includes nitro on a heteroaromatic carbon) |
| 4 | nitroaliphatic | `[#6;!c][N+](=O)[O-]` |
| 5 | azide | `[N-]=[N+]=[N]` |
| 6 | peroxide | `[OX2][OX2]` |
| 7 | n_rich_heterocycle | a ring holding two or more nitrogens |
| 8 | halogenated | `[F,Cl,Br,I]` |
| 9 | other_organic | the rest |

Precedence is deliberate: tetryl and TNAZ carry both N-nitro and C-nitro groups and are nitramines. A **cage** flag (some atom belongs to three or more rings, RDKit's symmetrized smallest rings: cubane, adamantane; flat fused rings and simple bridged bicycles are not cages) is reported beside the family, never instead. Strata overlap only through the cage flag and the form/phase strata. **A stratum with fewer than 30 entities in the holdout supports no standalone claim.** With a 20% holdout that means a family claim needs about 150 verified entities in the family; the corpus will probably support such a claim for at most one or two families, and the report says so.

## 6. Counts and denominators

Reported separately, every time: entities considered; entities with an eligible numeric label (and, separately, a **verified** one, section 8); entities each candidate predicted and refused (coded reasons); paired candidate/baseline entities; the all-method common cohort; source observations; entities with more than one observation; unresolved entities; `NoEventRecord` population by event; and the **`computed`, `unlabelled`, bulk/pressed/cast and wrong-temperature populations**, which are the energetic literature's way of looking like data without being a reference.

**Coverage = (entities the method predicts within its declared scope) / (entities with an eligible verified label).**

## 7. Building the corpus (a later PR; the rules are fixed here)

Every candidate row gets exactly one visible disposition (Phase A's list, plus `value_kind_not_reference`, `temperature_out_of_window`, `form_unresolved`, `unit_conflict`, `row_implausible`). Counts are generated from the structured records, never typed.

1. Locate entries by **field label** in the source, keeping page and entry; parse value, unit, qualifier, temperature, form and method. **Never infer** a missing unit, a temperature, a phase or which of several numbers in a cell is the one meant. The cell grammar is closed; anything outside it is refused with a reason.
2. Resolve the printed name to a structure through the app's naming path; record unique, ambiguous or failed. Where a source prints a **formula** (Meyer, Klapötke), the formula and molar mass must equal the structure's (Phase A section 13.6 rule); the energetic literature uses abbreviations (RDX, FOX-7, TEX) that resolve through a reviewed alias table, every alias attributed.
3. Classify value kind, density kind, event and method; apply the admission functions.
4. Cross-check against every other held source, tracking lineage (section 8).
5. The parser has hand-checked positive examples and plausible-but-wrong negative examples; every manual override is explicit, attributed and regression-tested; the **parser is frozen before any selection or holdout score exists**.

**Text layers lie in source-specific ways, and each is a test case before it is a parser rule.** Minus signs are lost or spaced ("- 115"); exponents are flattened; a property block's heading can be the wrong substance after a page break; a scanned book has no text layer at all (`INVENTORY.md` section 4 lists the instances found while counting).

**Two evidence layers, as in Phase A.** The books are copyrighted and are not committed. The repository holds the schema, the family module and its test, the parser's fixtures (a few hand-typed facts), the frozen split manifest and checksum, the judge, aggregate results, and `INVENTORY.md` (counts and locators, no per-compound values from a copyrighted table). Tsang & Domalski 1974 is a US Government report and may be committed in full; the two open-access papers (Wang 2024 is CC BY-NC-ND, Lease 2023 is open access) are treated as copyrighted for this purpose until a licence check says otherwise. The corpus is built beside the local library (`OPENCHEM_PDF_LIBRARY`); a run without it reports `NOT_RUN`, never a pass.

## 8. Detecting label errors before scoring, not after

Phase A found its label errors only by comparing two books and reading rendered pages after the corpus existed, and the handbooks it used are mostly *independent compilations of the same upstream*. The held energetics sources are worse in three specific ways found while counting them (`INVENTORY.md`): values are copied between books (Akhavan 2011's enthalpies for HNS, TATB, HMX and nitroglycerin match Cooper 1996; Agrawal 2010's kJ/kg for ammonium nitrate, ammonium perchlorate and ADN match Meyer's *energy* of formation), the same compound's value differs by tens of kJ/mol between books (RDX 61.5 to 70.3, tetryl 19.5 to 34, TNT -26 to -67 kJ/mol across the sources compared), and a source can print a wrong sign, a wrong unit or the wrong heading. So detection is a stage with fixed rules, run **before any partition is scored** and frozen with the parser.

### 8.1 Within-row plausibility (no second source needed)

Each rule uses the row alone, is fixed now, and sends a failing row to `row_implausible` (kept, counted, not scored):

* **Density**: 0.8 < rho < 3.5 g/cm3; and a **packing coefficient** k = rho x N_A x Vvdw / M (Vvdw the molecular van der Waals volume of the resolved structure, Bondi radii; M its molar mass) outside [0.55, 0.90] is flagged. The bounds here are placeholders to be **set on development rows only** before the freeze (a range wide enough to keep every development row that survives the other rules, and no wider), recorded, and not adjusted after a selection or holdout row is seen. The check exists because a bulk density read as a crystal density gives a packing coefficient far below any crystal's.
* **Enthalpy of formation**: kJ/kg and kJ/mol printed together must agree within 1% after conversion with the resolved molar mass (the unit-conflict rule of 3.3); a solid and a gas value for one compound must differ by a positive sublimation enthalpy of plausible size (**40-250 kJ/mol**, set on development rows); a value of the right size and wrong sign is detected only by agreement (8.2).
* **Melting point**: not at or above the same record's decomposition onset (3.4); not above the same source's boiling point where both are printed (Phase A section 13.10).
* **Identity**: the printed formula and molar mass must equal the structure's. Meyer 2016 and Klapötke's Encyclopedia print both, so a wrong heading (a property block under the wrong substance after a page break, found in the held copy of Meyer) fails here instead of scoring against a different molecule.

### 8.2 Cross-source agreement, with tolerances fixed now

An entity-property is **verified** when it has at least two observations of different `lineage_root` that agree, or one observation carrying a primary-literature measurement with a locator that was read on the page. Agreement (within the same kind/method class):

| property | agree when | rationale |
|---|---|---|
| crystal density | within 0.02 g/cm3, same form, temperatures both in the 273-303 K window | thermal expansion over 30 K is ~0.01 g/cm3; smaller than the 0.04 criterion of section 11 |
| enthalpy of formation (condensed) | within 10 kJ/mol | the same book prints RDX twice 18 kJ/mol apart (66.6 in prose, 85.0 in Table 9.6: `benchmarks/thermophysical/validation_rows_energetics.py`); 10 kJ/mol is half the 21 kJ/mol criterion |
| melting point | within 2 K, same method class; ranges overlapping | DSC onset versus capillary differ by 1-3 K; Phase A used 1.0 K for handbooks |
| decomposition | not applicable to a gate (3.5) | |

**Hybrid observations (owner decision, 2026-10-26).** A condensed-phase enthalpy of formation built from a *calculated* gas-phase enthalpy and a *measured* sublimation or vaporisation enthalpy (Muravyev et al. 2021 is the held example) is an observation with its own `lineage_root` (the paper and its method), stored with `value_kind` `computed` and marked `hybrid`. Unlike every other pair in the table above it may corroborate a measured value **across method classes**, under these limits:

* a hybrid and one measured observation that agree within the 10 kJ/mol above verify the entity; a hybrid alone never does, and two hybrids that share a quantum-chemistry leg or an author group count as one root;
* a hybrid that disagrees with an entity already verified by two measured observations is recorded as a `hybrid_conflict` note, and **does not** mark the entity `disagree` (the method's own stated inaccuracy is up to 25 kJ/mol, larger than the 10 kJ/mol tolerance, so it cannot overrule a measurement);
* every report that counts a hybrid states the source's own accuracy statement, and lists the entities that rest on one.

**Historical observations (owner decision, 2026-10-27; Amendment 4, 18.3).** A condensed-phase combustion measurement with no standard-state (Washburn) correction, or with a calorie the source does not define, is admissible as an observation and carries the flag `historical`, whatever its date. A comparison that involves one is made on the **combustion enthalpy**, not on a formation enthalpy; its tolerance is the 10 kJ/mol above, **unchanged**. For an undefined calorie the row also states, beside the comparison, an uncertainty of 0.2% of the combustion enthalpy; it is information for the reader and does not widen the tolerance, and it is dropped if the source's calorie is later found to be defined. It may take an entity from one root to two; it never turns a `disagree` into verified; and every report that counts one lists the entities that rest on it.

A disagreement keeps both observations, marks the entity `disagree`, and sends the page to review (8.4); it is never resolved by averaging or by taking the "better" source.

### 8.3 Lineage

`lineage_root` is the furthest-back citation traced for a value (the book's own reference marker where it prints one: Klapötke's Encyclopedia and Viswanath 2018 do; Meyer 2016, Agrawal 2010 and Akhavan 2011 print none per value). Two observations that share a root, or that are **identical to the last printed digit in two books with no root traced and the same unit conversion**, count as one observation for the purpose of "two sources". Where a lineage cannot be traced, the pair is `agree_untraced` and does **not** verify the entity on its own. (Meyer 2016 and Klapötke's text print identical values for new compounds, e.g. the bis(nitramino)triazinone entry; that is transcription consistency, not replication.)

### 8.4 Review, and what review may do

A flagged row (implausible, disagree, unit_conflict, agree_untraced) is read on the rendered page. The reader records what the page prints, whether the text layer matched it, and the disposition; a correction to what the page prints is an explicit, attributed override with a regression fixture. Review **never** uses a prediction, a method's output or a partition: the reviewer sees the row and its sources and nothing else. Review runs on development, selection **and** holdout rows alike (a label error is a label error), but only on rows flagged by the rules above, and the rules are frozen first; a holdout row's disposition is fixed before any score exists and a holdout-informed *change to a rule* is logged and invalidates the untouched status of that part (section 9.4).

### 8.5 What the primary cohort is

**Recommended (D5): the primary gate cohort is the verified entities.** Single-source and `agree_untraced` entities are scored in a labelled secondary report. Phase A's holdout shows why: Joback's boiling-point MAE was 27.1 K on all entities and 21.8 K where both books agreed (RESULT.md), a 20% swing caused by label quality alone. The cost is cohort size (section 13), and the alternative (all entities, subsets as sensitivity) is the owner's call.

## 9. The split, the sealed holdout, and what has already been seen

### 9.1 Partitions

Three, by SHA-256 of the split key: **60% development, 20% selection, 20% holdout** (`validation_rows.PARTITION_SHARES`, partition independent of which rows exist). The manifest and its checksum are committed. A **second report, grouped by structural family rather than by hash**, is a different claim (generalisation to an unseen family) and is never merged into the headline.

### 9.2 Compounds already examined are forced out of the holdout

The repository already compared routes on RDX, HMX, TNT, PETN, metriol trinitrate, dinitropiperazine and nine calibration compounds (`benchmarks/thermophysical/compare_energetics.py`, `validation_rows_energetics.py`, `orca_atom_equivalents.py`), and recorded Kim 2008's 41 densities as `selection`. For P1 and P2 those compounds were **examined while choosing methods**. Rule: every identity block in those modules is **forced into `development` or `selection` regardless of its hash**, recorded in the manifest with the reason `previously_examined`. The remaining compounds keep their hash partition, so the rule does not depend on which rows exist.

### 9.3 Phase A's holdout is not a source of evidence here

P3 overlaps Phase A's handbook corpus (the primary stratum held 385 nitro, 8 nitrate-ester and 5 nitramine melting points, `CORPUS_REPORT.md`). Rule: an identity block that `benchmarks/mp_bp/split_manifest.json` assigns to `holdout` is **excluded from Phase B's P3 holdout for Marrero-Gani, Joback and Candidate C** (their behaviour on that molecule's handbook label was scored once already); it may be scored for methods Phase A did not run. The manifest is read for partition membership only, never for labels or predictions. Phase A's per-entity predictions are not read.

### 9.4 One look per property, and how a defect is handled

* `epb_score.py select` writes a `freeze.json` per property (penalties and coefficients of any refit candidate, hash of every file that decides a score, thresholds, seed); `holdout` refuses without `--confirm-holdout-once`, and refuses unless every hashed file is byte-identical to the freeze and the tracked tree is clean; it writes a lock **before** the first holdout label is read, and refuses a second run. These are the guards of `mpbp_score.py`, reused, with **one lock per property** because the properties become ready at different times.
* Parser, identity and label defects are found and fixed on development rows and fixed fixtures. A holdout-informed change to the parser, a rule, a threshold or a method is logged, and **that property's holdout no longer supports an untouched final claim**; the gate artifact states which partitions were examined, when and for what.
* **A defect in shared code found after one property's holdout has been read**: that property's verdict stands as scored; each later property is re-frozen on the fixed code with the diff recorded. A fix that changes any development label is shown, and the later property's verdict says so.

### 9.5 A prospective arm, for methods whose population cannot be listed

A method with leakage `unknown` can be given a **prospective cohort**: verified entities whose *first reported measurement of that property was published after the method's declared data cut* (the paper's CSD snapshot or submission date). That is evidence of non-overlap by date, status `no_overlap_by_evidence`, for that cohort only; it is scored once, separately from the holdout, and never merged. It is leakage by identity only: a near neighbour of a trained-on compound is not excluded. The held sources give very few such compounds (Lease 2023's PETN derivatives; Wang 2024's single new compound; the cut date of each CSD-trained model must still be read), so this arm will be descriptive. `INVENTORY.md` section 6 lists the small series.

## 10. Candidate methods and the leakage status each will have

Leakage is judged per (model, property) on chemical identity, as in Phase A. **`unknown` is not a form of clean**: such a model produces exploratory statistics, labelled non-blind, and cannot PASS (`may_claim_independent_holdout`). The table is the status **as of this draft**, from each paper's own text (read for this document; a population not listed in the paper is `unknown`), and what could change it.

Two energetics-specific leakage routes are checked beside identity, and either alone makes a model's result non-blind for the affected rows (flag `source_shared`, row-level):

* **Label-source overlap.** A model fitted to a compendium (the NIST WebBook, Pedley's tables) is not independent of a book that cites the same compendium for its label (Klapötke's Encyclopedia cites the NIST WebBook for some values).
* **Training on the crystals the labels come from.** The crystal-density labels are mostly diffraction structures deposited in the Cambridge Structural Database; every CSD-trained density model has plausibly seen them.

### 10.1 Crystal density (P1)

| id | method | published fit population | recoverable? | status | what changes it | in repo |
|---|---|---|---|---|---|---|
| D1 | Tarver 1979 group additivity | 188 explosives and related compounds, 173 compared (p1 abstract); tabulated in the paper | yes, from its tables | `known_population_overlap_removed` once the tables are transcribed | transcribe the table and resolve identities | no (Table 11 groups to transcribe) |
| D2 | Ammon 1998 / 2001 / 2008 volume additivity | >11,000, ~26,000, then ~41,000 (atom/group) and ~48,000 (atom_code) CSD structures; not listed | no | **`unknown`** | a CSD licence and the lists, or the prospective arm (Ammon 2008 cut: read before freeze) | no |
| D3 | Hofmann 2002 element volumes | 182,239 CSD structures after screening (p2); not listed | no | **`unknown`** | as D2 | no |
| D4 | Keshavarz 2009 (nitro/nitrate/nitramine; polynitroarenes) | fit tables in each paper; compounds drawn as images | after transcription | **`unknown`** until transcribed, then known | transcribe and resolve identities | no |
| D5 | Rice 2007 / Qiu 2007 / Kim 2008 / Rice 2013 (QM surface descriptors) | small sets in the papers; Kim 2008 reports 41 CSD structures (the table already in the repo) | yes | `known_population_overlap_removed`; **the 41 Kim rows are pre-examined (9.2)** | read each paper's train/test statement | no |
| D6 | Nguyen 2021 (ML) | 10,251 CSD compounds as of Dec 2018; refcode list in the SI | if the SI is obtained, by refcode only | **`unknown`** | SI plus a refcode-to-identity route (CSD), or prospective arm after Dec 2018 | no |
| D7 | Yang 2021 (GNN, CCDC) | a CCDC set, with an independent test set retained | unread for membership | **`unknown`** | read the membership statement | no |
| D8 | Jin 2023 (transformer, open access) | 12,072 CSD CHON compounds | unread whether released | **`unknown`** | check the data availability statement | no |
| D9 | Davis 2024 (ML) | ~21,000 CSD compounds, 70/20/10 split; SI "not held" (`literature.toml`) | no | **`unknown`**; output normalised to 200 K, so a proxy against 295 K labels | obtain the SI; resolve the temperature basis | no |
| D10 | **Candidate D (this project's refit)** | the development partition of this corpus | yes, by construction | `known_population_no_overlap` | n/a | no |

**Candidate D**: density = M / (sum of fitted volumes), volumes for the element counts and at most ten functional-group counts (nitro, nitramine N-nitro, nitrate ester, N-oxide, azide, furazan/azole ring, ... fixed list written before fitting), ridge penalty from the fixed grid {0.01, 0.1, 1, 10, 100} chosen by lowest MAE on **selection**, fitted on **development only**, intercept-free, a group absent from development unfitted and refusing. It is named as the project's own in every report. **It is offered only if the verified development partition has at least 10 rows per fitted parameter.**

**Consequence stated now**: D2, D3, D6-D9 cannot PASS an independent-holdout claim on this corpus as it stands, however well they score; their results are exploratory and their verdict `NOT EVALUABLE`. This is a finding about what is knowable. Only D1 (after transcription), D4, D5 and Candidate D can be evaluable.

### 10.2 Condensed-phase enthalpy of formation (P2)

| id | method | published fit population | status | in repo |
|---|---|---|---|---|
| H1 | Keshavarz 2006 (nitramines, nitrate esters, nitroaliphatics; 2009 nitroaromatics) | fit tables in the papers; reported rms 25.7 kJ/mol for 26 nitroaromatics (2009) and 42.3 for 59 complex molecules (2006) | **`unknown`** until transcribed | nitroaromatic 2009: `keshavarz_nitroaromatic2009.py`, **reproduced** against its own Table 1 |
| H2 | Keshavarz and Sadeghi 2009 (nitramine/nitrate/nitroaliphatic sister paper) | fit table in the paper | **cannot be scored as published: its own coefficients do not reproduce its own printed table** (`literature.toml`); `NOT EVALUABLE (not reproducible)` | `keshavarz_sadeghi2009.py` |
| H3 | Nazari 2016 / Jafari 2016 | 222 compounds (2016); 119 data points (Jafari) | **`unknown`** until transcribed | no |
| H4 | **ORCA atom-equivalent route** (this project) | 9 calibration compounds, listed (`CALIBRATION_SET`) | `known_population_overlap_removed` (the 9 and the pre-examined compounds leave) | `orca_atom_equivalents.py`; gas-phase output, needs a sublimation leg; **PETN topology refused by evidence** (ROADMAP) |
| H5 | Mathieu 2018 APC (gas phase) + Keshavarz 2010 sublimation (condensed route) | APC: 2,671 compiled entries, training list in the SI (not held); sublimation: 92-107 compounds in tables drawn as images | **`unknown` twice** (APC SI absent; sublimation tables untranscribed); `source_shared` with the NIST WebBook | `mathieu2018_apc.py`, `keshavarz2010_sublimation.py` (reproduced on one row) |
| H6 | Cawkwell 2021 atom equivalents (gas phase) + sublimation leg | training set of 103 molecules, listed in its Table 1 (the 45 Byrd and Rice molecules plus 58) | `known_population_overlap_removed` after transcription | no |
| H7 | Byrd and Rice 2005/2006 | training and test sets stated and tabulated | known after transcription (gas phase; sublimation leg needed) | no |

Candidate "H-refit" (a composition-and-group regression fitted on development) is **not offered**, because the verified condensed-phase development partition is expected to be well under the 150 rows its 15 parameters would need (section 13).

A **route** is gate-eligible only when every leg has a recorded population or an explicit `unknown`, and a route containing an `unknown` leg is `unknown`. The two legs' errors are also reported separately where the sublimation leg has measured values (Acree 2010: `INVENTORY.md` section 3).

### 10.3 Melting point (P3)

| id | method | published fit population | status |
|---|---|---|---|
| M1 | Marrero-Gani first order, Tm | 1,547 data points, not listed (Phase A) | **`unknown`** |
| M2 | Constantinou-Gani 1994 | not read for this document | **`unknown`** until read |
| M3 | Joback Tf | 388 compounds, not listed | **`unknown`**, and a freezing-point **proxy** (not gate-eligible) |

Phase A's Candidate C **FAILED** its gate on ordinary organics (RESULT.md) and is **not offered** here: refitting 41 parameters on the energetic development rows would be a new method on a corpus an order of magnitude smaller. With M1-M3 all `unknown`, **P3 is expected to end as an exploratory description**: how far each method is from measured energetic melting points, by family, and how often the event is not a clean melt. That is a useful result, and it is not a pass.

### 10.4 Decomposition (P4): no candidate (3.5).

## 11. Scoring, thresholds, minimum n, outcomes

**Primary metric**: mean absolute error over unique entities (g/cm3, kJ/mol, K). Also reported: RMSE, median absolute error, signed bias, coverage, refusal reasons, n per stratum. Two comparisons, neither substituting for the other: the **all-method common cohort**, and each candidate against the **baseline on its own paired cohort**, with its coverage against the eligible denominator, so that a method cannot improve its headline by refusing hard cases.

**Baselines** (fixed, development rows only, no selection or holdout label): P1, the mean density of the molecule's family (section 5) falling back to the mean of all; P2, an ordinary-least-squares regression of the enthalpy on C, H, N, O counts (a composition-only model, because a family mean is meaningless over a range of about 1,200 kJ/mol); P3, the family mean.

**Intervals**: bootstrap over unique entities, 10,000 resamples, 95% percentile intervals, for the holdout MAE and the relative improvement over the baseline. The seed is the freeze date as YYYYMMDD, written to `freeze.json`.

### 11.1 PASS requires all of the following, for a stated property and scope, on the holdout

1. leakage status for that (model, property, cohort) is not `unknown`;
2. **replication criterion**: point MAE <= **1.5 x** the method's own published error where the paper reports a comparable mean absolute error (Tarver 1979: 0.0191 g/cm3 on 173 compounds; Marrero-Gani Tm: 24.90 K), **and** the upper bound of the 95% interval <= **2.0 x** it. Where the paper reports only a percentage, an R2 or an rms, this criterion is **not applicable** and is stated as such for that method;
3. **usefulness criterion** (absolute, from the downstream need rather than from a paper): point MAE <= **0.04 g/cm3** and upper bound <= **0.05** (P1); point MAE <= **21 kJ/mol** and upper bound <= **28** (P2); point MAE <= **37.35 K** and upper bound <= **49.8 K** (P3: Phase A's Marrero-Gani ceiling, kept for comparability);
4. point improvement over the baseline >= **20%** and the lower bound of its 95% interval >= **10%**;
5. coverage >= **70%** of the eligible verified denominator;
6. **at least 60 paired unique eligible verified holdout entities** (section 11.2).

Rationale. Density: Kim 2008 state performance needs density "within an error of 0.03 g/cc" (quoted in `docs/research/SENSITIVITY.md`); the illustrative worked example there (RDX, Kamlet-Jacobs Table III) moves the detonation pressure by about 4.6-4.7% for a 0.04 g/cm3 step, because pressure goes as density squared; and 0.04 is about twice the 0.019 that Tarver 1979, an early group-additivity method, reports for itself. Enthalpy: Kim 2008 give 5 kcal/mol (21 kJ/mol) as the need, quoted in the same note; the published condensed-phase methods report rms errors of 25-45 kJ/mol, so **the usefulness criterion is expected to be failed by most published methods, and that is the intended reading** (a method that is as good as its paper but not good enough to use has FAILED the criterion that matters for shipping). Melting point: Phase A's ceiling, kept so that the two benchmarks can be compared. 20%/10%, 70% and the intervals are Phase A's. All of these are engineering criteria, not scientific standards, fixed before scoring for that reason. **If the owner prefers Phase A's relative-only form, D2 in section 14 says what changes.**

### 11.2 Minimum n, derived rather than copied

Phase A required 300 paired holdout entities. That is not reachable here (section 13) and is not needed for the thresholds above. For a point ceiling P and an upper-interval ceiling U = (4/3) P (the 1.5x/2.0x ratio), the 95% interval half-width at the ceiling is 1.96 s / sqrt(n), and the interval clears U when 1.96 s / sqrt(n) <= U - P = P/3. Taking the worst case s = P (the standard deviation of the absolute error as large as its mean, which is the exponential-error case), n >= (3 x 1.96)^2 = **34.6**. Allowing for non-normal bootstrap behaviour and a baseline comparison on the same entities, the preregistered minimum is **60 paired verified holdout entities**. With a 20% holdout, a property needs **at least 300 verified eligible entities in the primary population** before any verdict other than NOT EVALUABLE is possible. This is stated now so that a corpus of 120 is not made to look like a corpus of 300.

### 11.3 Outcomes

`PASS`, `FAIL`, `NOT EVALUABLE` (fewer than 60 paired verified holdout entities; leakage `unknown`; unresolved identity; no candidate; not reproducible as published), and the machine-readable full-evaluation status `NOT_RUN` (the corpus was not available). A threshold is never relaxed after the corpus is seen. `NOT EVALUABLE` is not `FAIL`.

### 11.4 If the corpus is smaller than needed

Below 60 paired holdout entities for a property the verdict is `NOT EVALUABLE`, the thresholds are **unchanged**, and the report carries (a) the counts, (b) descriptive error statistics on all partitions labelled non-blind, and (c) the number of verified entities that would have been needed. No shares are re-cut after the count is known, no threshold is loosened, and the holdout is not scored "to see". If the owner wants a different split for a small corpus, D4 in section 14 is where it is decided, **before** the corpus is built.

### 11.5 What a pass allows

At most a narrowly scoped, EXPERIMENTAL, hidden calculator for that property and scope (`docs/CALCULATOR_MATURITY.md`). A P1 pass allows a **crystal-density estimate** for the passing family, named so, with its temperature basis; a P2 pass allows a condensed-phase enthalpy estimate for the passing family with its legs named; nothing here promotes a STABLE claim, a proxy never promotes, and each property promotes nothing about the others. A calculator also needs everything in that document (source entry, independent implementation check, units and reference conditions, coded refusals, help text, support reason, regression fixture, changelog).

## 12. Boundaries carried from Phase A section 11 (not reopened)

* Melting point and decomposition onset are separate properties (3.4, 3.5).
* Crystal density is not loading density and not theoretical maximum density; a P1 pass yields a crystal-density estimate and nothing more; **Kamlet-Jacobs stays `NEEDS_INPUT`**. Nothing in a P1 pass is wired to `loading_density_g_cm3`. A loading-density input, a TMD input or a "crystal density used as a stand-in" is a separate product decision by the owner, defining a new, explicitly named input; it is not made by this benchmark, and no result here is evidence for it.
* Enthalpy of formation is the condensed-phase quantity; a gas-phase route carries its sublimation leg and provenance (3.3, 10.2).
* A source-printed oxygen balance is a formula-reproduction consistency check (`tests/test_oxygen_balance_extended.py`), never independent evidence for any property here.
* Scope is validation of published methods on known compounds.

### 12.1 The PETN decision: when its reversal conditions count as met

`docs/ROADMAP.md` (recorded 2026-10-05) states the decision that the ORCA atom-equivalent route is not an automatic detonation input, and what would reverse it: **(R1)** "a four-arm quaternary-carbon calibrant with a measured gas-phase enthalpy", or **(R2)** "a held-out set of nitramines large enough to ship the route scoped to that family alone with the PETN class refused by a coded limit". They count as met **only** by frozen records and these rules:

* **R1 is met** when the frozen corpus holds at least one verified row (value kind `measured`, phase `gas`, a primary-source locator read on the page, a different identity block from PETN) whose structure matches the four-arm rule `[CX4;H0]([CH2][!#1])([CH2][!#1])([CH2][!#1])[CH2][!#1]` bearing four identical arms, **and** the owner has approved that compound as a PETN-topology calibrant (D8). R1 met means the PETN miss is *testable as a calibration gap*; it does not ship anything. **Owner decision, 2026-10-26 (D8):** a gas-phase enthalpy built from a measured condensed-phase enthalpy and a measured sublimation or vaporisation enthalpy counts as `measured` for R1, provided each leg is itself verified under 8.2; a value with a *calculated* gas-phase leg (a hybrid, 8.2) never satisfies R1. Pentaerythritol, the one candidate so far, therefore needs its sublimation leg settled first: the held studies give 131.4, 143.9 and 161.0 kJ/mol over different temperature ranges, which is a disagreement under 8.2 until one rule or one measurement resolves it. **Amendment 4 (18.4):** the *solid* leg of pentaerythritol can now be verified from two roots; the sublimation leg is unchanged, so R1 is still not met.
* **R2 has two tiers, reported separately and never merged** (owner decision, 2026-10-26).
  * **R2-gate (unchanged).** It is met when H4 (the ORCA route), frozen on development rows only, passes the P2 gate **scoped to the `nitramine` family** with at least 30 paired verified holdout nitramines (the stratum rule of section 5), **and** the PETN class (a nitrate ester with a four-arm quaternary carbon) is refused by a coded limit implemented and tested before the freeze. The inventory (`PETN_EVIDENCE.md`) finds about a dozen eligible nitramines with a printed or verified value; the gate is not reachable unless the verified nitramine stratum reaches about 150 entities, and the ceilings of section 13 make that doubtful. If it does not, R2-gate is `NOT EVALUABLE`: the number 30 is not lowered and no holdout is shrunk to fit.
  * **R2-pilot (new, descriptive only).** Whatever the stratum size, the report gives, one row per verified nitramine: the frozen reference value with its `value_kind`, phase, lineage and locator; H4's prediction; the signed and absolute error; and the leave-one-out error where the compound contributes to a calibration. It states n, the mean absolute and mean signed error with a 95% interval computed for that n (a bootstrap with a fixed seed, and the t interval beside it), the smallest effect n could detect, which entities rest on a hybrid observation (8.2), and the sentence: *"This is a pilot on n verified nitramines. It has no pass or fail criterion, does not satisfy R2-gate, and supports no product decision by itself."*
  * **Limits of the pilot.** It is not a pass of the P2 gate; it is not pooled with the nitrate-ester family or with other families' holdout rows; a nitramine used in it keeps its development or holdout assignment from the freeze, so it reads the rows the gate would have read and adds no peeking; it is run once, after the freeze, under a lock with byte-identical frozen files, and no pilot number is looked at before then. Verified nitramines may still be added before the freeze: each needs 8.2 verification and a lineage entry, and the count is recomputed from the frozen records.
* Neither condition changes `Detonation`'s `NEEDS_INPUT` status by itself; both only allow a *separate* product decision to be taken on evidence.

## 13. What the held literature can support

`INVENTORY.md` (generated from `inventory.json`, tested) counts, per source, per property, the entries that print a numeric value, with page or table locators and the extraction error rate measured by hand checks. It counts **entries and table rows before any structure identification**, so every figure is an upper bound on usable distinct compounds: the usable number is what survives identity (section 7), value kind (3.1), temperature and form (3.2), and verification (8). `INVENTORY.md` section 7 states the resulting upper bounds per property and the sample sizes they allow against the 300-entity requirement of 11.2. This section is the summary of that, and is filled in from it:

**The ceilings (`INVENTORY.md` section 7; entries, not distinct compounds, summed over sources with every double count left in):**

| property | ceiling on entries | largest single source | against the 300 verified entities that 11.2 needs |
|---|---|---|---|
| P1 crystal density, qualified as a crystal measurement | 235 | 187 (Klapötke's Encyclopedia, scaled) | **already below 300** |
| P1 density, any (unqualified, bulk, "theoretical" included) | 672 | 385 | reachable only by counting values that are not crystal densities |
| P2 condensed enthalpy, labelled experimental | 112 | 99 | **already below 300** |
| P2 enthalpy, any label | 597 | 315 | reachable only by counting calculated and unlabelled values |
| P3 melting point, clean melting event | 541 | 212 | not excluded by the ceiling, but every candidate's leakage is `unknown` |
| P4 decomposition (evidence only) | 466 | 323 | not applicable |

What this does and does not say:

* **It does not say how many verified entities exist.** That needs identity resolution, and verification (two lineage roots that agree, section 8.2) cuts a ceiling hard: across the three or four books compared for eight well-known compounds the enthalpy spread runs from 0 to 88 kJ/mol (`INVENTORY.md` section 5), and the zero is a digit-for-digit copy, not a replication; and the Encyclopedia's densities and enthalpies mix crystal and bulk, measured and calculated, solid and gas in one entry. A realistic verified count is a fraction of the ceiling, and cannot be stated before the corpus build.
* **It does say that, from the held literature alone, P1 (qualified) and P2 (labelled experimental) cannot reach 300 verified entities at 60/20/20**, because their ceilings are below it. Under the rules as drafted the expected outcome for both is `NOT EVALUABLE` for every method, however well it scores: a measured description of the methods and of the labels, with exploratory error statistics, and no PASS. A holdout share of 30% (D4) lowers the requirement to 200 verified entities, which the P1 ceiling of 235 cannot realistically meet after verification either.
* **P3** is the only property whose ceiling does not rule out the minimum, and it is the one where every candidate's leakage is `unknown`; its expected outcome is also `NOT EVALUABLE`, for a different reason.
* The honest first deliverable of Phase B is therefore the **corpus and its label-quality report** (what fraction of the entries are measured, crystal, in the temperature window, verified), exactly as Phase A's second PR was; the first one that could end in a PASS needs data this library does not hold (D9: crystal labels from the CSD, or measured-enthalpy compendia). Nothing in the thresholds is changed to make a small corpus look sufficient.
* The Encyclopedia counts are on 329 of 413 entries (volume 3 only 70 of 129, volume 1 161 of 186); its volumes 1 and 3 are image tables read by OCR with a measured error rate of one wrong field in 24 checked and an OCR-specific rate not established. The figures above scale the uncovered entries at the covered rate, which is an assumption.
* **The LMU Munich dissertations (the Klapötke group) are not in the library** (`INVENTORY.md` section 8); they were not counted.

## 14. Decisions for the owner

Each has a recommendation; the draft numbers above are the recommendations.

**Answered by the owner in chat on 2026-10-26 (all as recommended except where section 15 says otherwise); D8 is recorded in 12.1 and the rest in section 15, which supersedes any text above that it contradicts.** The list is kept as the record of what was asked.

* **D1. Which property goes first.** *Recommendation: P1 crystal density, then P2, with P3 as a description and P4 as evidence only.* Density has the cleanest event (a diffraction measurement with a temperature and a form), the most candidates with a listable fit population (Tarver 1979, the Keshavarz papers, Kim 2008, and Candidate D), a prospective arm, and no compute cost. P2 needs a sublimation leg, a measured-or-computed decision on every row (3.1) and DFT time. P3 is expected to end NOT EVALUABLE because every candidate's leakage is `unknown`.
* **D2. The form of the gate.** *Recommendation: both a replication criterion (1.5x / 2.0x of the paper's own error, where the paper gives a comparable one) and a usefulness criterion (absolute).* Phase A used only the relative form. The relative form alone would let a method that is faithfully as bad as its paper pass; the absolute form alone ignores what the paper claimed. If the owner wants Phase A parity, drop criterion 3 of 11.1; nothing else in the document changes, and more methods become able to PASS.
* **D3. The numbers.** *Recommendation: as written in 11.1* (0.04 / 0.05 g/cm3; 21 / 28 kJ/mol; 37.35 / 49.8 K; 20% / 10% improvement; 70% coverage; 60 paired holdout entities). The first two absolute pairs are the ones most open to challenge: both are tied to a single sourced statement of need (Kim 2008) and an illustrative worked example, and 21 kJ/mol is below what most published condensed-phase methods report for themselves.
* **D4. Minimum n and the shares.** *Recommendation: 60 paired verified holdout entities, which needs about 300 verified eligible entities at 60/20/20 (11.2); keep the shares; below that the verdict is NOT EVALUABLE and nothing is loosened.* The alternative is to give the holdout a larger share (for example 50/20/30, which needs about 200 verified entities) at the cost of a smaller development set for Candidate D. If the counts of section 13 make 300 unreachable for the property the owner cares about, this must be decided **before the corpus is built**, not after.
* **D5. The primary cohort.** *Recommendation: verified entities only (8.5).* The alternative (all entities with a label, verification as a sensitivity subset) gives more entities and, by Phase A's own measurement, a worse MAE for reasons that are the labels' and not the method's.
* **D6. The population.** *Recommendation: as written in section 5* (neutral single-component organic compounds; salts, hydrates, co-crystals, organometallics, mixtures and polymers as strata outside the primary gate; "organic" redefined so that NTO, nitroguanidine and the aminotetrazoles stay in).
* **D7. Pre-examined compounds and Phase A's holdout.** *Recommendation: yes to both rules* (9.2: every compound the repository's earlier survey examined is forced out of the holdout; 9.3: Phase A holdout members are excluded from the P3 holdout for the methods Phase A scored). The cost is a holdout without RDX, HMX, TNT and PETN, which are the compounds a reader would look for first; the benefit is that nothing already looked at is called untouched.
* **D8. The PETN conditions.** *Recommendation: the R1 and R2 definitions of 12.1,* and the owner's approval of which compound (if any) counts as a four-arm calibrant. R2 is not reachable unless the verified nitramine stratum reaches about 150 entities; the draft says so rather than shrinking the number. **Decided by the owner, 2026-10-26:** a sublimation-corrected gas value counts as `measured` for R1 when each leg is verified (12.1); R2 is adopted as the two tiers of 12.1; a calculated-gas-plus-measured-sublimation value counts as a corroborating observation under the limits added to 8.2. Pentaerythritol is not yet approved as the calibrant: its sublimation leg is unresolved.
* **D9. Access to the Cambridge Structural Database and to the supporting information of Nguyen 2021 and Davis 2024.** *Question for the owner: is a CSD licence available?* Without it, D2, D3 and D6-D9 stay `unknown` and the prospective arm is the only route to a non-exploratory result for them. With it there are two different uses, and they conflict: CSD **labels** would make P1 large (thousands of structures with a temperature and an R factor) but would make every CSD-trained model leak by construction, leaving only Tarver, Keshavarz, Kim-type and Candidate D evaluable; CSD **membership lists** (not labels) would let the CSD-trained models be evaluated by identity on the held-source labels. *Recommendation: do not decide this before reading the counts; ask for the licence status.*
* **D10. The temperature window and the expansion coefficient.** *Recommendation: 273-303 K, no conversion in the primary analysis, and one fixed coefficient read from Hofmann 2002 in a sensitivity analysis only, recorded as an amendment before any score* (3.2).
* **D11. Candidate D.** *Recommendation: offer it for P1 if the verified development partition has at least 10 rows per fitted parameter; do not offer a refit for P2 or P3* (10.1, 10.2, 10.3). Offering it is the Phase A decision (D4 there) repeated for the one property where a refit is plausible at this corpus size.
* **D12. Decomposition (P4).** *Recommendation: evidence layer only, no gate* (3.5). If the owner wants a decomposition predictor evaluated, a candidate must be named and a preregistered amendment written before it sees a label.
* **D13. The ORCA route's compute budget.** *Recommendation: decide after the verified condensed-phase count is known (13), then run H4 on development and selection molecules only until the freeze.* The earlier survey needed a full DFT geometry optimisation per molecule; the budget is the owner's.
* **D14. The LMU dissertations.** They are not in the library (`INVENTORY.md` section 8). *Recommendation: do not fetch them now.* Their contents were never inventoried (the eighteen read earlier, per `docs/sources.toml`, were searched for an oxygen-balance convention only), and the Klapoetke group's work is dominated by salts and primary explosives, which are outside the primary gate; that is an expectation, not a count. Re-open if section 13 shows a property that one dissertation series could rescue.

## 15. Amendment 1 (2026-10-27): the owner's decisions of 2026-10-26, and what the COD census changed

Written after the COD census (#470) and the PETN evidence hunt (#472) merged. **What was seen first:** counts only (COD entries by header field and by the groups found in their connectivity; the PETN inventory); no label has been compared with a prediction and no method has been run. The decisions below are the owner's, taken in chat on 2026-10-26, each as recommended in section 14 unless this section says otherwise; D8 is already in 12.1 and is not repeated. **Where this section contradicts earlier text it supersedes it, and says which text.** The preregistration is still a draft: it is frozen when the corpus builder and its parser tests (15.9) merge, and no label is compared with a prediction before then.

### 15.1 The population of P1 changes (D6, D9)

* **The primary population of P1 (crystal density) is a COD population**: Crystallography Open Database entries that are organic (section 5's element rule), neutral and single-component, and carry at least one **nitrate ester, nitramine, C-nitro or azide group** (the bond-order-agnostic connectivity patterns of `inventory_scripts/cod_structure_pass.py`, first match in that order). A ring with two or more nitrogens is **not** an explosophore: imidazole, pyrimidine and piperazine are ordinary heterocycles, and compounds whose only qualifying feature is such a ring are outside the primary population (reported as a stratum, never pooled).
* **The claim is worded for that population**: *"the crystal density of organic crystals that carry a nitrate ester, nitramine, C-nitro or azide group"*. It is never "energetic materials" in general, in any report, help text or calculator. Nitroaromatic and nitroaliphatic are one group here (C-nitro) because separating them needs bond orders the pass does not use; section 5's two families are applied to the primary population only where a structure with bond orders is available (15.3).
* **The held-literature compounds are a side stratum, reported on their own** (RDX, HMX, TNT, PETN and the rest of the books' known energetic materials, with the verified-entity rules of 8.2 and 8.5). They are not pooled with the COD population, and a side-stratum claim needs the 30 holdout entities of section 5, which this stratum is not expected to reach.
* **Superseded text:** the opening sentence of section 5 ("known energetic compounds with a measured reference value in the held literature") now describes P2, P3 and the P1 side stratum; section 13's conclusion that P1 cannot reach 300 verified entities holds for the held literature only.
* **Why** (counts from `cod_census_headers.json` and `cod_census_structures.json`, ENTRIES not compounds): of 521,901 indexed COD entries, 55,674 are organic, nitrogen-containing, measured at 273-303 K with no stated pressure and a diffraction density; 3,973 single-component entries carry one of the four groups (3,005 distinct formulas at the least; 3,251 entries at R of 0.07 or better), against the held-literature ceiling of 235.

### 15.2 Where the COD labels come from, and what stays out of git

The label is the entry's `_exptl_crystal_density_diffrn`. COD is dedicated to the public domain (CC0) and asks that the original authors be acknowledged, which every report does. The archive used is `cod-cifs-mysql.txz`, the **February 2025 snapshot** (SHA-256 `569FAE5DC969ED688AA62950D481BE71FA6195C39A08B550085C14D169D8525C`, recorded in `cod_census_headers.json`), kept on the maintainer's disk and read as a stream (unpacking it measured 15 files/s; streaming 13,000 entries/s). Under the repository's rule for bulk extracted corpora (`CLAUDE.md`, "Books and papers: use the facts") the corpus of thousands of rows is built beside the archive and **not committed**; the repository holds the scripts, the split manifest and its checksum, aggregate counts, the judge and the tests. **The snapshot date is a data cut**: entries deposited after it are not in the corpus and can later form a prospective cohort (9.5).

### 15.3 Identity and the entity key for COD entries

A COD entry has no name, so name resolution (section 7, step 2) does not apply. **The entity key, for the split and for leakage, is the RDKit element-graph hash of the molecule's heavy-atom connectivity** (`rdMolHash.HashFunction.ElementGraph`): it ignores bond orders, charges and stereochemistry, so the three ways Open Babel and RDKit write TNT's nitro groups give one key (held by a test before any use), and tautomers and stereoisomers share a key. That is conservative in the same direction as Phase A's first-InChIKey-block key. An entry is accepted as a **single whole molecule** only when its moiety formula lists one uncharged component, or (with no moiety formula) a whole molecule with exactly the header formula exists in the cell (`single_by_geometry`, reported apart); an entry that is multi-component, ionic or unknown is a stratum or a refusal, never a primary row. Methods that need bond orders (Tarver's and Keshavarz's group types, the QM-descriptor methods) are given a structure perceived from the crystal coordinates by an RDKit route with total charge 0; **a structure that cannot be perceived is refused with a coded reason and counted**, and Open Babel's perceived bond orders are never used (they were measured unusable: only 6 of 40 probe entries could be sanitised).

### 15.4 Label quality (D5)

For the COD primary population, **8.5 is replaced**: the primary cohort is every entity with an **eligible** label, not only verified ones. A COD density is eligible when: the R factor (`_refine_ls_R_factor_gt`, else `_refine_ls_R_factor_all`) is stated and **at most 0.07**; a measurement temperature is stated within **273-303 K** (3.2); no non-ambient pressure is stated; and the entry is a single whole molecule (15.3). Rules for an entity with several eligible determinations: determinations with different space groups or different Z are different forms and are not combined (an entity with several forms and no stated stable one is unresolved for P1, as 3.2 says); within one form the label is the **median** density; if the determinations of one form spread by more than **0.03 g/cm3** (maximum minus minimum) the entity is **unresolved** and is not scored. **The agreeing subset** (entities with at least two eligible determinations within 0.03 g/cm3) is reported beside the headline as a labelled side check and is not the primary cohort. **Why not verified-only:** each COD density is its own diffraction measurement, so the copy-between-books failure that made verification necessary for the held literature does not arise; requiring two determinations would instead remove most compounds and skew the cohort toward the commonest. In 11.1, "verified" in criteria 5 and 6 reads "eligible (15.4)" for this population; for the side stratum it keeps its meaning.

### 15.5 The gate, the numbers, the size (D2, D3, D4): confirmed as written

11.1 stands unchanged for P1: the replication criterion (1.5x and 2.0x of a method's own published error where comparable) **and** the usefulness criterion (**0.04 and 0.05 g/cm3**), 20% and 10% over the baseline, 70% coverage, and **at least 60 paired holdout entities**. The shares stay **60/20/20**. For the COD primary population the holdout is expected to hold hundreds of entities, so 11.2's requirement of about 300 eligible entities is met there and 13's expectation of NOT EVALUABLE does not apply to it; it still applies to the side stratum, to P2 and to P3.

### 15.6 The famous compounds stay out of the sealed set (D7)

9.2 stands and extends to the COD population: every compound named in the modules of 9.2 (RDX, HMX, TNT, PETN, metriol trinitrate, dinitropiperazine, the nine calibration compounds and Kim 2008's 41) has its **entity key computed with the 15.3 function from its structure**, and any COD entity with that key is **forced into `development` or `selection`**, with the reason `previously_examined`, regardless of its hash. They stay in the side stratum's report.

### 15.7 Candidates (D9, D11)

* **No CSD access is available and none is expected**, so D2, D3 and D6-D9 of 10.1 stay `unknown` and cannot PASS; COD overlaps the CSD, so COD labels do not make them evaluable. The candidates that can be evaluated on this population are **Tarver 1979 (D1), Keshavarz 2009 (D4), Kim 2008-type (D5) and Candidate D**. D1 and D4 need their fit tables transcribed and their compounds resolved before their leakage status is known (10.1).
* **Candidate D is offered for P1**, fitted on the COD primary development partition only, under the rules of 10.1 (at least 10 rows per fitted parameter, ridge penalty from {0.01, 0.1, 1, 10, 100} chosen on selection, a group absent from development unfitted and refusing, named the project's own in every report). With a COD development partition of hundreds of entities the 10-rows rule is expected to be met; if it is not, Candidate D is not offered.

### 15.8 Temperature (D10): room temperature for the claim, a gated study for the rest

* **The primary population is measured at 273-303 K and nothing in it is converted** (3.2 stands). Low-temperature structures (about 100 K) are kept and reported as their own stratum, uncorrected.
* **A correction study is preregistered here, and the main claim does not depend on it.** *Pairs*: two eligible determinations of one entity key with the same space group and Z, one at 80-160 K and one at 273-303 K, whose unit-cell volume ratio V(RT)/V(low) lies in **[1.00, 1.08]** (a physical-plausibility cut that removes polymorph mismatches; the bound is fixed here from physical reasonableness and not from the data, and the unfiltered median ratio measured in the census exploration was 1.028). Pairs are split by entity key with the 60/20/20 hash. *Model forms, both fixed now*: a constant volumetric expansion coefficient, and one whose coefficient is linear in the low temperature; fitted on **development pairs only**, chosen on **selection pairs**, scored **once** on held-out pairs. *Admission bar*: a mean absolute error on the held-out pairs of at most **0.015 g/cm3** and an upper 95% bootstrap bound of at most **0.02**. The bar is the owner's (0.015) and the upper bound follows the 4/3 ratio of 11.2.
* **If it passes**, corrected low-temperature entities join a **secondary** analysis only, never the primary gate, with the correction's own error stated beside every corrected result and added in quadrature; a compound that already has a room-temperature determination is never corrected. **If it fails**, the low-temperature stratum stays uncorrected and the study's failure is reported.
* For orientation only (it decides nothing): a crude census exploration on 3,926 pairs matched on formula, space group and Z found low-temperature densities about 2.8% higher, and one fixed ratio left a median error of about 0.027 g/cm3 against 0.043 uncorrected; the match is crude, so a floor of about 0.01-0.015 is expected, not known. The study measures it properly.

### 15.9 Accepted as drafted (D12, D13, D14), and what must exist before the freeze

* **D12**: decomposition stays an evidence layer with no gate (3.5). **D13**: the ORCA route's compute budget is decided after the verified condensed-phase count is known. **D14**: the LMU dissertations are not fetched now. **D1**: P1 first, then P2, P3 described, P4 evidence only; each property has its own lock (9.4).
* **Not yet fixed, and each must merge before the freeze**: (a) the COD corpus builder with its parser tests (extraction by connectivity, the entity key, perception with refusal, the dispositions and their counts); (b) the cell-volume and space-group fields the first index pass did not capture, which the correction study needs; (c) the correction-study code and its tests; (d) the transcription of Tarver 1979 and Keshavarz 2009 and the resolution of their compounds; (e) Candidate D's fixed group list; (f) the split manifest and its checksum. No label is compared with a prediction before the freeze, and **nothing in this amendment changes a number of section 11**.

## 16. Amendment 2 (2026-10-27): the correction study's minimum, its pair population, and what is now built

Written after the COD corpus builder (#479) and the correction-study code (#482) merged. **What was seen first:** counts only, and one count drove a decision, so it is stated plainly. The builder's pair file, drawn from the explosophore population alone, held 49 pairs of 46 entities, of which 8 entities fell in the held-out part of the 60/20/20 split; the minimum below is 35, so the study as then drawn could only return NOT EVALUABLE. The owner decided to widen the pair population (16.2) on that count and on the physical argument given there. **No density of any pair has been compared with any prediction or with any other density, no fit has been run on a real pair, and no method has been scored.** The owner's decisions are of 2026-10-27, taken in chat. Where this section contradicts earlier text it says which text it supersedes. The preregistration is still a draft, frozen when the items of 15.9 that remain open (16.4) have merged.

### 16.1 The correction study's minimum number of held-out entities (supersedes 15.8's silence on it)

15.8 fixed the admission bar (held-out MAE at most 0.015 g/cm3, upper 95% bound at most 0.02) and gave the study no minimum number of held-out entities. **The minimum is 35 held-out entities.** It is the derivation of 11.2 taken at the study's own ceilings: with P = 0.015, U = (4/3) P and the standard deviation of the absolute error as large as its mean, n >= (3 x 1.96)^2 = 34.6, rounded up, **with no allowance added**. The 60 of 11.2 includes an allowance for a baseline comparison on the same entities; this study has no baseline (the uncorrected error, which is the low-temperature density used as the prediction, is reported beside every number but decides nothing). The unit is the **entity key**, not the pair: an entity with several forms counts once. **Fewer than 35 held-out entities is NOT EVALUABLE, never a relaxed bar.**

### 16.2 The pair population is every organic, nitrogen-containing crystal (supersedes the explosophore reading of 15.8)

15.8 defines a pair as two eligible determinations of one entity key, and 15.1 makes the eligible population the explosophore one. **For the correction study only, the population is widened** to every entry the corpus builder accepts as a candidate (organic, nitrogen-containing, a diffraction density, a stated temperature, no stated pressure) that is a single whole molecule (15.3) with an R factor of at most 0.07 (15.4), and that carries no qualifying group requirement. **Why:** the quantity being fitted is the thermal expansion of a molecular lattice between two temperatures, which has no reason to depend on whether the molecule carries one of the four groups; the explosophore pairs alone cannot reach 35 held-out entities; and the correction is a transfer from a larger organic population to the explosophore one, which is the use 15.8 describes. **What stays the same:** the pair rules of 15.8 (one entity key, the same space group and Z, one determination at 80-160 K and one at 273-303 K, a cell-volume ratio V(RT)/V(low) in [1.00, 1.08], the 60/20/20 hash by entity key with the previously examined compounds forced into development, 15.6). Within one form and one temperature window the determination used is the one with the lowest COD code (a deterministic rule, not a choice between densities).

**The explosophore subset is flagged and reported, never the gate.** Each pair carries a flag that is true when both of its determinations carry one of the four groups. The judge reports the held-out pairs and entities of that subset and their MAE (corrected and uncorrected) beside the verdict, as description only: no bar, no verdict and no effect on the outcome. **The claim is worded for the whole population:** *"the density change of organic, nitrogen-containing crystals between 80-160 K and 273-303 K"*. Applying it to corrected low-temperature entities of the explosophore population in the secondary analysis (15.8) is a stated extrapolation from that claim, and the subset's own error is printed beside it.

### 16.3 What the counts are, and the mechanics now fixed in code

From `cod_correction_pairs.json` and `cod_corpus_summary.json`, builder `epb-cod-corpus-1`: 392 determinations matched on key, space group, Z and both windows; 23 dropped because the volume ratio is outside [1.00, 1.08]; none for a missing cell volume; **369 pairs of 349 entities**. Split by the entity hash: development 208 pairs (193 entities), selection 76 (74), **held-out 85 pairs (82 entities)**. Of the 369, 49 pairs (46 entities) are explosophore pairs, with 8 held-out entities. The split manifest and its checksum (`c4352b53...e985b`) are unchanged by the widening, because the partition depends on the entity key alone.

`epb_density_correction.py` (judge version `epb-density-correction-1`) fixes the rest, and 15.8's wording is read as it is implemented: because the formula and Z are the same, the density ratio is the volume ratio, and both forms are fitted to it by ordinary least squares in closed form (constant: rho_low / rho_rt - 1 = alpha (T_rt - T_low); linear: the coefficient is a + b (T_low - 120 K)); the prediction is rho_rt = rho_low / (1 + that); fitted on development pairs only; the form with the lower selection MAE is chosen, a tie within 1e-9 g/cm3 going to the constant form; scored once on held-out pairs. The bootstrap resamples **entity keys** (a key's pairs move together) 10,000 times with seed 20261027, and **the bar is applied to the 97.5th percentile**, the stricter reading of "upper 95% bound". Outcomes are `NOT_RUN`, `NOT_EVALUABLE`, `FAIL`, `PASS`. The holdout run needs the explicit confirmation flag, byte-identical frozen files (the module, the corpus builder, the pairs file, the split manifest and `tools/validation_rows.py`), a clean tree, and refuses a second run.

### 16.4 Status of the items of 15.9

(a) the COD corpus builder and its parser tests, (b) the cell-volume and space-group fields, (c) the correction-study code and its tests, and (f) the split manifest and its checksum are **done** (#479, #482). **Still open, and each must merge before the freeze:** (d) the transcription of Tarver 1979 and Keshavarz 2009 and the resolution of their compounds; (e) Candidate D's fixed group list. **Nothing in this amendment changes a number of section 11.**

## 17. Amendment 3 (2026-10-27): the published density candidates are transcribed and resolved, and Candidate D's group list is fixed

Closes items (d) and (e) of 15.9. **What was seen:** the three papers' printed tables and drawings, and counts of how many of their compounds are in the COD corpus's split manifest. **No COD label was compared with any prediction**, and nothing in section 11 changes.

### 17.1 What was transcribed, where it lives, and how it was checked (item d)

Tarver 1979 (`tarver1979`): Tables I, III and V, **188 compounds** (25 + 80 + 83, the paper's own count) with their groups, and the group-volume Tables I (footnote), II and IV (**26 and 47 configurations**, again the paper's counts). Keshavarz and Pouretedal 2009 (`keshavarz2009_nitro`): Table 1 (72 compounds, the data of its correlation) and Table 2 (41, the comparison set). Keshavarz 2009 (`keshavarz2009_arene`): Tables 1-3 (21 + 9 + 16 = 46, the data of its correlation) and Table 4 (13, a reliability check). **The full transcriptions (about 360 rows, with names, structures, measured and printed values) are kept in the maintainer's private notes**, not in git, under the owner's instruction of 2026-10-26 (a bulk table); `density_candidates_manifest.json` records their SHA-256 and carries entity keys and counts only. The committed method parameters (the group volumes and the two correlations) are in `epb_density_candidates.py`, pinned by a hash.

Three independent checks, all passing except where listed: (1) **each Tarver row against its own arithmetic**: the molar volume is the sum of its groups, the density is mol wt over volume, the error follows from the two densities (the group-volume tables were thereby checked cell by cell, since every designation is used); (2) **each Keshavarz row against its printed correlation**: the printed 'new method' density is the correlation plus some ED/EI (or CPG/CNG) term the paper's rules allow, which fixes C, H, N, O and the molecular weight of each structure read from a drawing; (3) **between papers**: of the 84 compounds Keshavarz's tables share with Tarver's, 80 agree with Keshavarz's own copy of Tarver's column to the printed digit, and the other four are explained (a different measured HMX, a copy of the new-method value into one cell, a differently recomputed TMETN, and a two-value row). The printed inconsistencies this found (13 in Tarver, some of them readings of the print; in Keshavarz's two papers a printed sign convention, a caption count, a coefficient, a rule-versus-table point, two rows the correlation does not reproduce and the five unresolved structures) are findings, listed by id in the manifest; the transcription keeps what is printed. Two matter for use: **Tarver's volume for furan is half its group sum** (35.78 against 71.56) and **Keshavarz's Eq. (5) prints the CNG coefficient as -0.751 while every row of its own tables is reproduced only with -0.0751**; the committed constant is -0.0751 and the printed one is kept beside it.

### 17.2 Leakage status (10.1 D1 and D4, now known)

**D1 (Tarver), D4a (Keshavarz, nitro) and D4b (Keshavarz, arenes) are `known_population_overlap_removed`.** The rule: a COD entity whose entity key (15.3) is in a model's list is removed from that model's evaluation and counted, in whichever partition it fell, and **both the data tables and the comparison tables of a paper are treated as seen** (a paper's choice of ED/EI and CPG/CNG values was tuned across all of them). Of **256 distinct keys** the three papers print (174 Tarver, 113 Keshavarz nitro, 53 Keshavarz arenes, with overlaps), **6 are in the COD corpus's manifest: 1 in development and 5 in the held-out part** (m-dinitrobenzene and 2,3,4-trinitrotoluene in Tarver's; trimethylolpropane trinitrate in Keshavarz's nitro; m-dinitrobenzene and the 2,6-diamino-3,5-dinitropyrazine key, which its N-oxide shares, in Keshavarz's arenes); 21 of the 256 are in the set 15.6 forces into development. **Residual risk, stated:** five printed compounds of D4b (an aza analogue of TACOT, an azo-bis(furoxan) and three benzobisfuroxan amines) could not be resolved to a connectivity and are not in the key list; D4b's report must carry that sentence. Two cubane rows (tetra- and pentanitro) are drawn with positions that cannot be read at the print's size, so every positional isomer's key is in the list.

The published-error comparison of 11.4 is a mean absolute error. **Tarver's is comparable** (0.0191 g/cm3 over 173 compounds; the transcription has a printed error on 172 rows, and the paper says 173). **Keshavarz reports a root-mean-square deviation in percent, not a mean absolute error**, so the replication criterion of 11.4 is not applied to D4 (the rule says it applies where the paper reports a comparable error); D4's result is judged by the 0.02 g/cm3 and bootstrap bar and the baseline comparison alone, and its published rms values are quoted beside it.

### 17.3 Candidate D's group list is fixed (item e)

Written before any fitting. Density = M / V, **V = sum over elements and groups of fitted volumes times counts**, intercept-free; elements **C, H, N, O, F, Cl, Br, S** (a molecule with any other element is refused); **ten groups**, each a SMARTS or a ring rule applied to the resolved structure: `c_nitro` ([#6][N+](=O)[O-]), `n_nitro` ([#7][N+](=O)[O-]), `nitrate_ester` ([#6]O[N+](=O)[O-]), `azide` (N=[N+]=[N-]), `n_oxide` (a charged N bearing O-, nitro and azide excluded), `furazan` (a five-membered ring O1 N C C N, so furoxans too), `amino_ortho_nitro` (an N-H amine on an aromatic carbon next to an aromatic carbon bearing a nitro group; counted per amine-nitro pair), `hydroxyl` ([OX2H][#6]), `polyazole` (a five-membered ring with at least three nitrogen atoms) and `aromatic_ring` (a ring whose atoms are all aromatic). The group list is the 10.1 list (nitro, N-nitro, nitrate ester, N-oxide, azide, furazan, azole ring) plus three features chosen by chemistry, not by any label seen here: an amine beside a nitro group, a hydroxyl and the aromatic ring. **Fit:** weighted least squares on V = M / rho with weights 1 / V (a relative error in volume), a ridge penalty on the **group coefficients only** (the element volumes are not shrunk toward zero) from the grid {0.01, 0.1, 1, 10, 100} chosen by the lowest density MAE on **selection**, fitted on **development only**. **A group with no development row is unfitted, and a molecule that contains it is refused, as is one with a non-positive predicted volume.** It is offered only if the verified development partition has at least 10 rows per parameter, **18 parameters, so at least 180 rows** (the development partition holds 1,687 resolved entities, a count only). It is named the project's own in every report. The specification, the group counter, the fit and the prediction are in `epb_density_candidates.py` and tested on synthetic data (`tests/test_energetics_props_density_candidates.py`); no real row has been fitted.

### 17.4 Status of the items of 15.9

(a)-(f) of 15.9 are all **done**. What the density property still waits on before its freeze is the owner's approval of Amendments 2 and 3 and, outside this document's arm, the enthalpy arm's own amendment (D8 and R2, another session's). **Nothing in this amendment changes a number of section 11.**

## 18. Amendment 4 (2026-10-28): a second root for pentaerythritol's solid enthalpy, the `historical` flag, and a study-stated step for combustion enthalpies

An amendment to the enthalpy arm (3.3, 8.2, 12.1 and D8). **What was seen first:** the printed pages of one 1892 paper (18.1), two compilations of selected values and the standard-state values of two held sources (18.2); a search for a calibrant for R1 and for a second measurement of one nitrate ester. **No corpus was built, no method was run, no label was compared with a prediction, and no row of a corpus was written**; nothing in section 11 changes. The owner's decisions are of 2026-10-27, taken in chat. Where this section contradicts earlier text it says which text it supersedes. The preregistration is still a draft.

### 18.1 What was found: a second, independent root for the solid

Pentaerythritol's condensed-phase enthalpy rested on one measurement, Médard and Thomas, *Mem. poudres* 36 (1954) 97-127, which none of the held libraries has, so it could only be read through compilations. **Stohmann and Langbein, *J. prakt. Chem.* [2] 45 (1892) 305-356, measured it independently** (a different laboratory, 62 years earlier, a sample from Prof. Tollens), on pp. 328-329 (the four runs and the result) and p. 338 (the summary table), **read on the page images** of the free scan (archive.org identifier `sim_journal-fuer-praktische-chemie-1834_1892_45`): per mole 659.2, 661.9, 660.6 and 661.6 Cal; mean **660.8 Cal/mol at constant volume and 661.4 at constant pressure**; the paper's own formation heat is 222.6 Cal/mol (see 18.2 for why it is not used).

**Lineage.** The NIST WebBook, the CRC Handbook (97th ed.), Lange's, Domalski 1972 (*J. Phys. Chem. Ref. Data* 1, 221: Table 6.6, printed p. 231, -220.0 kcal/mol, with Stohmann and Langbein named as the alternative that was not preferred) and Domalski and Hearing 1993 (*J. Phys. Chem. Ref. Data* 22, 805: Table 15, printed p. 919, solid -920.60, reference code 54MED/THO) all print the Médard-Thomas 1954 value: **one `lineage_root`, however many books** (8.3). The 1993 paper's gas value, -776.70, is -920.60 + 143.9 exactly, the same solid plus a sublimation term, and adds no root. Stohmann and Langbein is a different root.

| comparison (1 kcal = 4.184 kJ) | Stohmann and Langbein 1892 | Médard and Thomas 1954 (as printed by NIST and Domalski) | difference |
|---|---|---|---|
| combustion enthalpy, constant pressure | 661.4 kcal/mol = -2767.3 kJ/mol | 660.1 kcal/mol = -2761.9 kJ/mol (NIST: -2762 +/- 2.8) | **5.4 kJ/mol** (0.2%) |
| formation enthalpy by the fixed step of 18.2 | -915.2 kJ/mol | -920.7 kJ/mol | **5.5 kJ/mol** |
| formation enthalpy as Stohmann and Langbein printed it, 222.6 kcal/mol | -931.4 kJ/mol | -920.7 kJ/mol | 10.7 kJ/mol; **not used** (18.2) |

**Caveats that travel with the row.** There is no standard-state (Washburn) correction, and purity is given only as "schön krystallisirtes Präparat"; the paper does not define the calorie, and neither do the two earlier papers it refers to for its procedure (Abhandlungen XXII and XXV, *J. prakt. Chem.* [2] 42, 361 and 44, 336, read on 2026-10-28, nor the method paper they cite for the apparatus, [2] 39, 503): all use "kleine Calorie" with no temperature and no value in joules, and describe a water calorimeter with the water at about 13 to 19 degC, which points to a calorie near the 15 degC one (4.1855 J, 0.04% above 4.184 J, about 1 kJ/mol here) but is an inference, not a statement; 0.1% of the combustion enthalpy is 2.8 kJ/mol, so the difference above is of the size of the allowance for the calorie alone; Domalski 1972 (p. 230, in its pyrocatechol entry) says that this paper's measurements used an oxygen bomb calorimeter; four runs, spread 659.2 to 661.9 Cal/mol. It is a measurement of the **solid** only and says nothing about sublimation.

### 18.2 A step this study states (supersedes the wording of 3.1's `derived_from_measured` row)

3.1 admitted a derived value only through "an arithmetic step the source states". Stohmann and Langbein state theirs, but it is on auxiliary values that are not standard (their two printed formation heats imply CO2 = 94.0 and H2O(l) = 69.0 kcal/mol, an inference from their erythritol and pentaerythritol rows, not a statement of theirs), so taking it literally would mark the pair `disagree` by an artefact. **Decided (owner, 2026-10-27, option B):** the combustion enthalpy of such a row is `measured`; its formation enthalpy is `derived_from_measured` by **this study's own fixed step**, applied identically to every root of an entity (Médard and Thomas included):

dfH(solid, 298.15 K) = 5 dfH(CO2, g) + 6 dfH(H2O, l) - dcH(solid, constant pressure)

with **dfH(CO2, g) = -393.51 kJ/mol and dfH(H2O, l) = -285.830 kJ/mol** (CODATA key values, Cox, Wagman and Medvedev 1984, as the NIST WebBook prints them: -393.51 +/- 0.13 and -285.830 +/- 0.040) and the thermochemical calorie, 1 kcal = 4.184 kJ. The CRC Handbook 97th ed. prints -393.5 (carbon dioxide, p. 5-9) and -285.8 (water, liquid, p. 5-41) and is the held cross-check; it is not used in the step. A constant-volume combustion value is first brought to constant pressure by the source's own correction where it prints one. **Limits:** the step is used only to turn a condensed-phase combustion enthalpy into a formation enthalpy, never for a gas-phase value, and the Kamlet-Jacobs constants of `energetics.py` (water as a gas) are not these values. A row filed this way carries the flag `step_by_study`, keeps the source's own printed number in an `as_printed` field, and carries the 0.69 kJ/mol that the two auxiliary uncertainties contribute (sqrt((5 x 0.13)^2 + (6 x 0.040)^2)); that term is common to every root and cancels in a comparison between roots. **The auxiliary values are frozen with the corpus: changing them after a score exists is a new corpus version.** Changing them now moves every formation enthalpy of pentaerythritol by 0.2 kJ/mol at most (the CRC's rounded values give -3682.3 where these give -3682.53 for the auxiliary term) and the difference between its two roots by nothing.

### 18.3 The `historical` flag

A flag beside `value_kind` (like `hybrid`, 8.2), not a fifth kind. **Defined by property, not by date:** a condensed-phase combustion measurement with no standard-state (Washburn) correction, or with a calorie the source does not define. By that rule Stohmann and Langbein is flagged, and so is Médard and Thomas as NIST reduces it ("no Washburn corrections"), so both roots of pentaerythritol carry it and a reader is not left thinking only the old one is uncorrected. A rule by date would have flagged only the 1892 paper. The rule for an observation carrying it is the paragraph added to 8.2: admissible as an observation; compared on the **combustion enthalpy**; the 10 kJ/mol tolerance, **unchanged** (owner decision, 2026-10-28: the calorie uncertainty does not loosen the test); for an undefined calorie the row states beside the comparison an uncertainty of 0.2% of the combustion enthalpy (about 5.5 kJ/mol here), so a reader sees that a difference of that size cannot separate a real disagreement from the calorie, and the statement is dropped if a source is found that defines the calorie (the two earlier papers were read and do not; the 0.2% stays as the stated bound because the inference of 18.1 is not a statement); it may take an entity from one root to two, and **never turns a `disagree` into verified**. A row filed this way is a primary measurement read on the page, so under 8.2 it is itself sufficient to verify the entity, and the second root is a cross-check and a measure of spread, not a precondition.

### 18.4 What this does to R1, and what it does not

R1 (12.1, D8) needs a gas-phase value whose two legs are each verified under 8.2. **The solid leg of pentaerythritol can now be verified from two roots 5.5 kJ/mol apart. The sublimation leg is unchanged**: 131.4, 143.9 and 161.0 kJ/mol over different temperature ranges, about +/- 16 kJ/mol around the middle, a disagreement under 8.2. The gas value therefore stays a `derived_from_measured` number dominated by its sublimation term, **R1 is not met, and pentaerythritol is still not approvable as a precise calibrant**. This amendment says nothing about the nitrate ester whose two combustion measurements differ by 176 kJ/mol in formation enthalpy; that entity stays `disagree` (`PETN_EVIDENCE.md`).

### 18.5 Status

The pages read and the arithmetic above are the evidence; they are recorded as rows B08 to B10 of `PETN_EVIDENCE.md` and its JSON, and **no row of any corpus is written by this amendment**. Nothing here changes a number of section 11, the sealed holdout, or any other section's rule beyond the wording of 3.1's row, the one paragraph added to 8.2 and the one sentence added to 12.1.
