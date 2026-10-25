# Preregistration: melting and normal boiling points of organic compounds

**Status: DRAFT. Not frozen.** It freezes when the owner confirms the open decisions in section 12 and this file is merged. Until then no corpus is built and no method is scored. After it is frozen, any change is a dated amendment that says what changed and why, and a number is never changed after a result that bears on it has been seen.

## 1. The question

How well do published group-contribution methods predict, for ordinary organic compounds, (a) the melting point and (b) the normal boiling point, against handbook reference values; where do they refuse; and is any of them good enough, on a held-out part of the data, to ship as a calculator?

A **FAIL**, a **NOT EVALUABLE** and a **PASS** are all complete outcomes of this work. The deliverable is a measured description of what the methods can and cannot do and what the references support, not a calculator.

Energetic materials are **not** in this round. Their properties (melting versus decomposition onset, crystal density, condensed-phase enthalpy of formation) need their own preregistration after this verdict exists (section 11).

## 2. Targets, and what each result may be called

Every line of every report carries: target property, the model output's definition, the reference event's definition, `target_matched`, and any proxy assumption.

| Target | Methods scored | `target_matched` | Gate-eligible |
|---|---|---|---|
| melting point (`melting_point`) | Marrero-Gani first-order Tm | yes | yes |
| melting point | **Joback Tf, as a PROXY** | **no** | **no** |
| normal boiling point (`normal_boiling_point`) | Joback Tb; Marrero-Gani first-order Tb | yes | yes |

* **Joback's Tf is a freezing-point output.** Its own paper says the estimate "is not accurate and should be considered as only very approximate". It is compared with measured melting points as a **diagnostic proxy only**: coverage, errors, bias, strata and failures are reported with `gate_eligible = False`. It cannot PASS, cannot promote anything, and no report, heading or help text may call it a validated melting-point predictor. A feature built on it as a proxy would need its own declared claim and its own gate.
* **Decomposition onset is its own property** (`decomposition_temperature`) and is never a boiling-point target. Whether a compound decomposes before it boils is a classification question and is out of scope.
* The two methods' parameters are the ones in `src/openchem/chem/joback.py` and `benchmarks/thermophysical/marrero2001_table.py`, **unmodified**. A change to a group table, a coverage rule or a decomposition after a diagnostic error has been seen makes a new method version, and a new version needs a new untouched evaluation.

## 3. The reference observation

### 3.1 Event, property and conditions are separate fields

`tools/validation_rows.py` carries them separately. The event vocabulary is `melting`, `boiling`, `sublimation`, `decomposition`, `melting_with_decomposition`, `not_observed`, `unknown`. `ADMISSION_POLICY` decides, for every (target, event) pair, whether a row may be scored; `unknown` is admitted to no score; matching units never make an unclassified row scoreable.

### 3.2 Melting point

* Only a clean `melting` event is a target. `melting_with_decomposition`, `decomposition`, an "estimated" value and a value the substance never reaches are not.
* A reported **range** is scored as an interval: error 0 inside it, the distance to the nearer bound outside it. It is never replaced by its midpoint, endpoints are not rounded, and a malformed or half-open range is excluded with a reason.
* Two values for one entity that the source attributes to different polymorphs, with no statement of which is stable, make the entity **unresolved** for this score.

### 3.3 Normal boiling point

* Only a clean `boiling` event at normal pressure is a target. A stated pressure counts as normal when it is within **+-1.5 kPa of 101.325 kPa** (about +-11 mmHg). An entry with no printed pressure counts as normal only when the table's own header states that its column is at normal pressure; otherwise it is excluded. This convention is read from the Lange and CRC table headers before extraction and recorded here as an amendment.
* A reduced-pressure value is **excluded, not converted**. A sublimation or decomposition temperature is not a boiling point.
* An entity with no clean normal-boiling event is recorded as a `NoEventRecord` (no numeric value, cannot be scored) with the event the source reported. It is neither a prediction failure nor a deletion; see section 6.

### 3.4 What is kept for every observation

Original value, unit and qualifiers as printed; the normalised value and the normalisation method; pressure as printed and normalised; the range if any; the physical form if stated; source file hash and edition; table, page and entry; whether the source is primary or secondary and its upstream citation where traced. The original is never discarded after conversion.

## 4. Entities, keys and the statistical unit

Four keys, kept apart:

1. **Entity id**: the benchmark's declared identity of the neutral parent compound. Stereo and tautomer variants are one entity for scoring, represented by one chosen structure.
2. **Physical-form / observation id**: polymorph, hydrate, salt or source-specific form where stated, plus the source locator.
3. **Leakage key**: the first InChIKey block (`identity_block`), deliberately conservative.
4. **Split grouping key**: the same first InChIKey block (`split_group_key`). Stereoisomers, isotopologues and charge variants of one skeleton always share a partition. This removes some near-duplicates from independent evaluation; it is not a claim that grouped records are the same entity or form.

**The statistical unit is one unique eligible entity with a numeric target for that property.** Source observations are all kept; no entity gets more than one vote in the primary gate.

* **Primary-label rule (fixed now).** For an entity with several admissible observations: take the primary-source value if one exists; otherwise take the observations from the most recent edition among those held; if the surviving values then differ by more than **1.0 K** (point values; ranges that do not overlap), the entity is **unresolved** and is not scored in the primary analysis.
* **Sensitivity analysis (fixed now).** The primary analysis is repeated using, for each entity with several admissible observations, each alternative in turn, and the spread of MAE across these repetitions is reported. Nothing is averaged.
* Two handbooks printing one value are two observations of one entity and are counted as such. Their agreement is evidence of transcription consistency, not of independent measurement.

## 5. Population and strata

"**Broad handbook corpus**" is the description of the population until the counts are known; no claim is made about all organic compounds, and the availability of a clean measurement is itself a selection (unstable, nonvolatile and decomposing compounds are under-represented).

* **Organic**: contains carbon and at least one C-H or C-C bond.
* **Primary set**: neutral, single-component, non-polymeric compounds. **Salts, hydrates and solvates, organometallics, mixtures and polymers** are separate reported strata and are outside the primary gate.
* Identity consistency (section 7) is a check, not proof.

**Families** (used for strata and for the baseline), assigned by the **first match in this fixed order**; a molecule with none of them and only C and H is `aromatic_hydrocarbon` (any aromatic atom) or `aliphatic_hydrocarbon`; anything else is `other`.

| # | family | SMARTS |
|---|---|---|
| 1 | nitrate_ester | `[OX2][N+](=O)[O-]` |
| 2 | nitramine | `[NX3][N+](=O)[O-]` |
| 3 | nitro | `[#6][N+](=O)[O-]` |
| 4 | halogenated | `[F,Cl,Br,I]` |
| 5 | carboxylic_acid | `[CX3](=O)[OX2H1]` |
| 6 | ester | `[CX3](=O)[OX2][#6]` |
| 7 | amide | `[CX3](=O)[NX3]` |
| 8 | ketone_aldehyde | `[$([CX3H1](=O)[#6]),$([#6][CX3](=O)[#6])]` |
| 9 | alcohol_phenol | `[OX2H][#6]` |
| 10 | amine | `[NX3;!$(NC=O);!$(N[N+](=O)[O-])][#6]` |
| 11 | nitrile | `[CX2]#N` |
| 12 | ether | `[OD2]([#6])[#6]` |
| 13 | sulfur | `[#16]` |

Families are defined from structure alone, before any score exists, and are not adjusted afterwards. Strata may overlap (a molecule is in the stratum of every pattern it matches, for reporting), but the baseline uses the first match only. **A stratum with fewer than 30 entities is reported with its n and supports no standalone claim.**

## 6. Counts and denominators

Reported separately, every time: entities considered; entities with an eligible numeric target for the property; entities each candidate predicted (and refused, by coded reason); paired candidate/baseline entities; the all-method common cohort; source observations; entities with more than one observation; unresolved entities; the `NoEventRecord` population by event.

**Coverage = (entities the method predicts within its declared scope) / (entities with an eligible numeric target).** The no-clean-event population is outside that denominator and is reported on its own line.

## 7. Building the corpus (a later PR; the rules are fixed here)

Every candidate row gets exactly one visible disposition: accepted for the melting-point set / accepted for the normal-boiling-point set / decomposition-or-sublimation evidence only / identity mismatch / identity ambiguous / pressure incomparable / event not comparable / parser ambiguity / source conflict. Counts are generated from the structured records, never typed.

1. Locate entries in the source table, keeping page and entry; parse value, unit, range and qualifiers. **Never infer** a pressure, a missing digit or an unclear name.
2. Resolve the printed name to a structure through the app's naming path; record unique, ambiguous or failed.
3. **Identity consistency check (not proof of identity).** The printed formula, parsed into element counts, must equal the resolved structure's; the printed molecular weight must agree within `max(0.5 x 10^-d, 2e-4 x MW)`, where `d` is the number of printed decimals. Constitutional isomers share both, so a name that resolves ambiguously goes to a review queue and is not accepted because the checksum passed.
4. Classify the event and the conditions; apply the admission functions.
5. Cross-check against the second handbook, tracking lineage. A conflict keeps both observations and uses the rules in section 4.
6. The parser has hand-checked positive examples and negative (plausible-but-wrong) examples; every manual override is explicit, attributed and regression-tested; the parser is **frozen before any selection or holdout score exists**.

**Two evidence layers.** The Lange and CRC tables are copyrighted and are not committed. The repository holds the schema, the parser's fixtures (a few hand-typed facts), the frozen split manifest and its checksum, the judge, and aggregate results. The full corpus is built beside the local PDF library (`OPENCHEM_PDF_LIBRARY`) and is not in Git. A run without the library reports `NOT_RUN` and is never a pass. A full evaluation records source-file hashes and editions, builder version, corpus, manifest and split hashes, judge version, all counts above, and states plainly that the reference values cannot be regenerated from the public repository.

## 8. The split and the sealed holdout

* **Three partitions**, by SHA-256 of the split grouping key: **60% development, 20% selection, 20% holdout** (`PARTITION_SHARES`). The manifest and its checksum are committed. The partition of a key does not depend on which other rows exist.
* A second report, **grouped by structural family (section 5) rather than by hash**, is labelled as a different claim (generalisation to an unseen family) and is never merged into the headline.
* **The holdout is sealed.** Parser and data defects are found and fixed on development rows and fixed fixtures. A holdout-informed change to the parser, the eligibility rules or a method is logged, and the holdout then no longer supports an untouched final claim for that part. The gate artifact states which partitions were examined, when and for what.
* Methods and the baseline are chosen using development and selection only. The holdout is scored **once**, after the candidate set, the scoring code and these thresholds are frozen.

## 9. Leakage, per (model, property)

`tools/validation_rows.py` carries leakage as a status: `known_population_no_overlap`, `known_population_overlap_removed`, `no_overlap_by_evidence`, `unknown`. `unknown` is not a form of clean: such a model may produce **exploratory statistics, labelled non-blind, and cannot PASS an independent-holdout claim** (`may_claim_independent_holdout`). A known overlap is removed from every partition for that model, counted and reported.

**Recorded for the two published methods (read for this document):**

| model, property | fit population as published | recoverable | status |
|---|---|---|---|
| Joback, Tb | 438 compounds (Table VI, p240, "regression testing"); members not listed in the paper, "a more detailed breakdown is given elsewhere" (Joback, 1984) | no | **unknown** |
| Joback, Tf | 388 compounds (same table) | no | **unknown** |
| Marrero-Gani, Tm | 1547 data points (Table 3, p192); regression data come from a data bank, not listed | no | **unknown** |
| Marrero-Gani, Tb | 1794 data points (Table 3, p192) | no | **unknown** |

**Consequence, stated now so that it is not discovered later:** with these four statuses `unknown`, **neither published method can PASS an independent-holdout gate on this corpus**, however well it scores. Their results are reported as exploratory and the verdict for each is `NOT EVALUABLE` for an independent claim. This is a finding about what is knowable, not a failure to try. Decision D4 (section 12) is about what, if anything, to add so that a promotable candidate can exist.

## 10. Scoring, thresholds and the verdict

**Primary metric**: mean absolute error (MAE, via `absolute_error`) over unique entities, in kelvin. Also reported: RMSE, median absolute error, signed bias (over- or under-prediction), coverage and refusal reasons per method, n per stratum.

**Two comparisons, neither substituting for the other.** (a) The **all-method common cohort**, for method-to-method comparison. (b) Each candidate against the **baseline on that candidate's own paired cohort**, with its coverage reported against the eligible denominator. A method must not improve its headline by refusing hard cases.

**Baseline** (fixed): the mean of the target over **development rows** in the molecule's family (section 5, first match), falling back to the mean over all development rows; no selection or holdout label is used.

**Published-error references**, each recorded like a citation (paper and place, metric name and definition, property, population, value, comparability):

| reference | value | metric as the paper names it | population it was computed on | like-for-like |
|---|---|---|---|---|
| Joback, Tb (Table VI, p240) | 12.9 K | "average absolute error" | its own 438 regression compounds | for the Tb gate, with the caveat that the benchmark population differs |
| Joback, Tf (same table) | 22.6 K | same | its own 388 | **not used for any gate** (proxy) |
| Marrero-Gani, Tm, first-order (Table 3, p192) | 24.90 K | "AAE", mean of |estimated - experimental| | its own 1547 regression points | for the Tm gate, same caveat |
| Marrero-Gani, Tb, first-order (Table 3, p192) | 7.90 K | "AAE" | its own 1794 points | for the Tb gate, same caveat |

**PASS requires all of the following, for a stated property and scope, on the holdout:**

1. leakage status for that (model, property) is not `unknown`;
2. point MAE <= **1.5 x** the reference above (Joback Tb 19.35 K; Marrero-Gani Tm 37.35 K, Tb 11.85 K) **and** the upper bound of its 95% interval <= **2.0 x** (25.8, 49.8, 15.8 K);
3. point improvement over the baseline >= **20%** **and** the lower bound of its 95% interval >= **10%**;
4. coverage >= **70%** of the eligible denominator;
5. **at least 300 paired unique eligible holdout entities** (candidate and baseline both predicted).

Intervals: **bootstrap over unique entities, 10,000 resamples, 95% percentile intervals**, for the holdout MAE and for the relative improvement over the baseline.

Why these numbers: 1.5 x leaves room for a benchmark population that differs from the method's fit set while still binding it to its own claim; 20% means beating "no model" by a margin visible above noise, and the interval condition stops a narrow clear of the point threshold counting as comfortable; 70% prevents winning by refusing; 300 entities makes the intervals narrow enough for the thresholds to mean something. They are engineering criteria, not established scientific standards, and they are fixed before scoring for that reason.

**Outcomes**: `PASS`, `FAIL`, `NOT EVALUABLE` (fewer than 300 paired entities; unresolved identity; leakage `unknown`), and the machine-readable full-evaluation status `NOT_RUN` (the corpus was not available). A relaxed threshold is never applied after the corpus is seen. `NOT EVALUABLE` is not `FAIL`.

**What a pass allows**: at most a narrowly scoped, EXPERIMENTAL, hidden calculator for that property and scope (`docs/CALCULATOR_MATURITY.md`). A melting-point pass promotes nothing about boiling points and the reverse; there is no STABLE claim from this gate; a proxy never promotes. A calculator also needs everything in that document (source entry, independent implementation check, units and reference conditions, coded refusals, help text, support reason, regression fixture, changelog).

**Example gate report** (the shape every full evaluation produces):

```json
{
  "evaluation_status": "PASS | FAIL | NOT_EVALUABLE | NOT_RUN",
  "target": "normal_boiling_point",
  "model": "joback", "model_output": "Tb", "target_matched": true, "gate_eligible": true,
  "leakage": {"status": "unknown", "evidence": "", "may_claim_independent_holdout": false},
  "counts": {
    "entities_considered": 0, "entities_with_eligible_target": 0, "entities_predicted": 0,
    "paired_with_baseline": 0, "all_method_common_cohort": 0, "source_observations": 0,
    "entities_with_multiple_observations": 0, "unresolved": 0, "no_event_records": {"decomposition": 0}
  },
  "coverage": 0.0,
  "metrics": {"mae": 0.0, "mae_ci95": [0.0, 0.0], "rmse": 0.0, "median_ae": 0.0, "bias": 0.0,
              "improvement_over_baseline": 0.0, "improvement_ci95": [0.0, 0.0]},
  "refusals": {"UNCOVERED_ATOM": 0},
  "strata": {"nitro": {"n": 0, "mae": 0.0, "claim_supported": false}},
  "sensitivity": {"mae_range_over_alternative_observations": [0.0, 0.0]},
  "partitions_examined": [{"partition": "development", "purpose": "parser and method choice"}],
  "provenance": {"source_file_hashes": {}, "corpus_builder": "", "corpus_hash": "", "split_manifest_hash": "",
                 "judge_version": "", "code_commit": "", "full_corpus_evaluated": false},
  "limitations": ["reference values cannot be regenerated from the public repository"]
}
```

## 11. Phase B (energetic materials): fixed boundaries, not yet a plan

Separate preregistration, not begun until this verdict exists. Boundaries already fixed: melting point and decomposition onset are separate properties; **crystal density is not loading density and is not theoretical maximum density**, so a passing crystal-density method yields a crystal-density estimate and nothing more, and **Kamlet-Jacobs detonation stays `NEEDS_INPUT`** unless a separate, owner-approved product decision defines a new, explicitly named input; enthalpy of formation is the condensed-phase quantity, and a gas-phase route needs its sublimation step and provenance; an oxygen balance printed in a source is a check that the formula was applied as intended, not an independent measurement; scope is validation of published methods on known compounds. The ROADMAP's PETN reversal conditions count as met only by frozen records and a rule the Phase B preregistration names.

## 12. Open decisions for the owner (this file freezes when these are answered)

* **D1. The gate numbers**: 1.5x and 2.0x of the published error, 20% and 10% improvement over baseline, 70% coverage, 300 paired entities, 60/20/20, +-1.5 kPa. Keep or change.
* **D2. The population rules** in section 5: what counts as organic; salts, hydrates, polymers and organometallics outside the primary gate.
* **D3. The primary-label rule**: primary source, else most recent edition, else unresolved if values differ by more than 1.0 K.
* **D4. Because every published method's fit population is `unknown` (section 9), no existing method can PASS here.** Options: (a) accept it: Phase A then delivers the measured description and an exploratory result, and no calculator; (b) **add a third candidate, "Joback's 41 groups with coefficients refit on the development partition only"**, whose fit population is the development partition and so is known by construction, evaluated on selection and holdout like any other; it would be this project's own method, not Joback's, and would be named so; (c) look for the fit populations (Joback's 1984 report, the data bank behind Marrero-Gani), which are unlikely to be obtainable. **Recommended: (a) plus (b).** Option (b) is NOT in the plan the owner approved and is not added without an answer.
* **D5. Whether Phase B starts only after this verdict** (default yes).
