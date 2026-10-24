# Synthesis planner quality benchmark, protocol 3 (option 3c): routes the model cannot have memorised

**Status: DRAFT of 2026-10-24, not frozen.** It freezes when Alex approves the decisions in the last section. Nothing in the planner has been run on these routes: the references were read and checked first, the protocol is written second, the run is third. Protocols 1 and 2 (`PREREGISTRATION.md`, `PREREGISTRATION_2.md`, `RESULT.md`, `RESULT_2.md`) are the context, and this document uses their matching rule, ranking, settings and vocabulary unchanged unless it says otherwise.

## The question, and what it can and cannot say

Protocols 1 and 2 measured how often the planner reproduces the published route on 300 PaRoutes targets. The planner's public model was trained on US patents to September 2016, and PaRoutes' routes come from the same patents, so a good score there could be memory (the contamination caveat of `PREREGISTRATION.md`). Protocol 2 gave M2 at 10 = 0.417 (the first 10 routes a person is shown contain the reference).

**Protocol 3 asks: when the reference is a synthesis from a journal paper published after the training data, does the planner recover it as often as it recovers routes of the same depth in protocol 2?** If it does, protocol 2's figure is not mostly memory. If it recovers markedly fewer, the product should quote the lower figure.

It can say: how often the planner's first 10 routes contain the paper's own route for the paper's lead compound, by route depth, period and confidence tier, and how that compares with depth-matched protocol 2.

It cannot say: that the planner finds feasible routes (feasibility is not measured), that it finds routes to molecules of novel chemistry (the papers are mostly analogue-library chemistry of ordinary reaction types, which is the product's likeliest use but not a test of invention), or anything about papers that do not give a short, explicit route (see the exclusions). A paper's route is one valid route, never the only one: a miss may be a valid alternative.

## The sample

**Frame.** Journal articles with "synthes" in the title (a mechanical stand-in for "a paper about making compounds"), in 20 medicinal-chemistry journals and Org. Process Res. Dev. The journal list is the one fixed on 2026-10-24 (`artifacts_protocol3/frame.json`). Three strata, drawn at different times because the frame was widened when the first two gave too few usable routes (30 of about 40 wanted):

| stratum | years | drawn | how | seed | papers in hand |
|---|---|---|---|---|---|
| 1 | 2018-2022, J. Med. Chem. | 60 | Europe PMC list (446 papers), seeded draw | 2026102402 | 59, plus 3 substitutes |
| 2 | 2018-2022, the other 19 journals + OPRD | 60 | Crossref list (8,530 papers), seeded draw | 2026102403 | 53, plus 10 substitutes |
| 3 | 2017 and 2023-2025, all 21 journals | 70 | Crossref list (6,623 papers), seeded draw | 2026102404 | 56 (4 as preprints or accepted manuscripts), plus 9 spares |

Papers were fetched by Alex, who can obtain older papers more easily than 2025 ones, so the papers in hand are the drawn ones that were obtainable; a paper that could not be obtained was replaced by the next entry of the same seeded stream (the substitutes and spares), chosen only by the seed and never by what the paper contains. 14 drawn papers of stratum 3 and 7 of stratum 2 are still missing; they are not replaced further, and any that arrive before this protocol freezes are read by the same pipeline and added (none after).

190 papers were read in all. 51 give a usable route. Papers with no usable route are listed with their reason and are part of the record, because they say what the rule excluded.

**Not in the sample:** the eight targets of the pilot on 2025 papers (kept outside the repository, with the stem-to-paper tables), because the pilot was exploratory and its results were seen; and four extra papers Alex found that are in no draw.

## The references

**One route per paper, chosen by a fixed rule (the lead rule).** The compound is (1) the one the abstract or title names as best, most potent, optimised, lead or featured; (2) if none, the compound used for the paper's main follow-up experiment; (3) if neither, the paper is excluded (`no_lead_identifiable`). The rule never swaps to a compound because its route is shorter or clearer. This is strict on purpose: a fallback ("any compound with a short route") would select the easiest chemistry. 26 of the papers excluded in strata 1 and 2 (stratum 3 was not counted) list other compounds with short routes; they are not used and not read further (a possible later, separately declared exploratory set).

**The route** is the paper's own synthesis from commercial starting materials, written from the article and its SI only:
- A starting material is a leaf only if the paper buys it or uses it with no preparation; a molecule the paper makes with a procedure is an intermediate and its preparation is a step. "As previously reported" without a procedure, or a starting material isolated from a natural source by the authors, excludes the paper (`route_not_explicit`).
- Every reaction counts, deprotections included; a one-pot sequence the paper writes as one procedure counts once. More than 4 reactions excludes the paper (`lead_route_over_4_steps`). A chiral separation is not a reaction; if the lead is one enantiomer obtained by separation, the reference is the racemate.
- A reactant is any molecule that supplies a non-hydrogen atom to the product (so methyl iodide, an acyl chloride, formaldehyde count; bases, catalysts, solvents, hydrides do not); a molecule incorporated twice is listed twice. A salt is written as its free base (largest fragment compared).
- Peptides, proteins, oligonucleotides, polymers, conjugates, radiolabelled compounds, metal complexes and organometallics, reviews and papers without a synthesis are excluded (`not_small_molecule_organic`, `no_synthesis_in_paper`).

**How they were made.** Reader agents (twenty for strata 1 and 2, eleven for stratum 3; one JSON per paper; brief `artifacts_protocol3/agent_brief.md`), each reading about six papers' texts (the PDFs' text layers: names, procedures, scheme captions; not the drawn structures). A program (`validate_refs.py`) checked every route: each SMILES parses, the product's carbon is supplied by the listed reactants, every intermediate is used once, the target is the last product, and each printed compound name is converted to a structure by OPSIN and compared with the SMILES. A second, independent reader then re-read every route against its paper, deciding the lead blind first (`verify_brief.md`, verdicts in `artifacts_protocol3/verification/`). Routes the second reader rejected, or whose leaves it found unsupported, were excluded at that stage (six in strata 1 and 2, two in stratum 3); every edit made after reading is recorded in the file's notes and in `refs_status.json`. **The 51 references are fixed as they stand when this protocol freezes.**

**Tiers.** Tier A (32): the second reader confirmed everything. Tier B (19): the route stands but something is inferred (a reactant derived from the product name, "purchased" supported only by a general statement, a telescoped step counted as one). The primary analysis uses all 51; tier A alone is reported beside it.

| | papers | routes | not explicit | over 4 steps | not small organic | no lead | no synthesis |
|---|---|---|---|---|---|---|---|
| stratum 1 (59 + 3) | 62 | 13 | 10 | 23 | 12 | 4 | 0 |
| stratum 2 (53 + 10) | 63 | 17 | 21 | 12 | 2 | 9 | 2 |
| stratum 3 (56 + 9) | 65 | 21 | 24 | 10 | 6 | 3 | 1 |

(Totals: 190 papers, 51 routes. By route depth, the longest chain of reactions: 15 routes of depth 1, 10 of depth 2, 14 of depth 3, 12 of depth 4. By period: 2017: 8 routes of 23 papers; 2018-2022: 30 of 125; 2023-2025: 13 of 42.)

## The planner

AiZynthFinder 4.4.1 in its own environment (`planner_env_lock.txt`), the same public USPTO expansion model, no filter policy, 500 iterations, at most 10 transforms, every solved route returned (`all_routes`), 1,800 s time limit as a safety net, routes ranked as protocol 2 ranks them (`route_ranking.py`: PaRoutes route score by dense rank, then state score, then planner order). As in protocol 2 the run refuses to start if the packages, the model file sizes or the settings differ from protocol 2's recorded identity.

## The stock (the decision that matters most)

The pilot showed the stock decides the result more than anything else: with a purchasable-compounds stock the planner stops at a purchasable intermediate and returns a shorter valid route that the exact rule scores as a miss. The stock is therefore fixed in advance:

- **Primary: protocol 2's stock (the PaRoutes n1 list), plus every reference's own starting materials, minus every reference's intermediates and targets.** This mirrors protocol 2, whose stock was built from its references' leaves, and it never contains a molecule the reference makes. One stock file serves all targets. A molecule that is a leaf of one route and an intermediate of another is reported before the run and the affected routes are run alone with the right stock.
- **Secondary: only the references' own starting materials** (the strictest: the planner can end nowhere else).
- **Tertiary: ZINC, as the application ships**, with no reference material added. Reported with a count of references whose intermediates ZINC sells (a shortcut the exact rule cannot credit).

Run r1 on all three stocks; r2 and r3 on the primary stock only, to measure the noise floor (as protocol 2 repeated 20 targets).

## The matching rule and what is counted

**Exact (primary, unchanged from protocols 1 and 2):** a returned route matches when the set of its reaction identities (product, sorted precursors; canonical SMILES, stereo kept, no atom maps) equals the reference's. The target is recovered at 10 when one of the first 10 routes in the user-facing order matches (**M2 at 10**).

**Reported beside it and never decisive:**
- **Lenient match:** the same, with every precursor of 3 or fewer heavy atoms (methyl iodide, formaldehyde, carbon disulfide) removed from both sides, because a planner template may or may not list such a reagent as a reactant.
- **Same-materials route:** a returned route that is not an exact match but whose starting materials are all among the reference's starting materials (right materials, different chemistry).
- **Reaction-level recall:** for each reference reaction, in how many returned routes it appears (the pilot's best diagnostic for why a route was missed).
- M1 (the PaRoutes count, ties included), M3 (planner order), the pool (the reference anywhere among the returned routes), solved flag, routes returned.

## The reading (fixed now, applied to the primary stock, exact rule, M2 at 10)

1. **Headline for product wording: M2 at 10 over all 51 routes** with its Wilson 95% interval, quoted with the by-depth split. Any statement about the planner must quote this figure, not protocol 2's.
2. **The comparison that answers the question.** Protocol 2's M2 at 10 by reference depth, under the same exact rule, is 0.81 at depth 2 (80 targets), 0.39 at depth 3 (136), 0.04 at depth 4 (50) (`artifacts_protocol2`, tree depth of the reference). For the 36 routes of depth 2 or more, the expected number of recoveries at those rates is **14.0 (0.39)**. Let k be the observed number.
   - If the probability of k or fewer recoveries under those depth rates (an exact lower tail, each route a Bernoulli trial with its depth's rate) is **below 0.05**, the reading is **LOWER**: protocol 2 overstates what the planner does on routes it did not train on, and the product quotes protocol 3's depth-specific figures.
   - Otherwise the reading is **NO EVIDENCE OF A DROP**: this protocol could not distinguish the two, and says so with the interval; it is never worded as confirmation.
3. **Depth-1 routes (15)** have no protocol 2 counterpart (PaRoutes routes start at depth 2) and are reported separately, with their own recovery rate; they are not part of the comparison in 2.
4. **Reported by period** (2017, 2018-2022, 2023-2025), **by tier** (A only, A and B), **by stratum**, **by stock**, **by journal publisher group**; with 51 routes no subgroup comparison is a test, only a description.
5. **Noise floor:** the difference in M2 at 10 between r1, r2 and r3 on the primary stock, and whether the solved flag is identical; if two runs differ by more than 0.06 in M2 at 10 the figure is reported as a range.

No verdict gate (GO / PARTIAL / NO-GO) is set: the question here is a comparison, not a threshold, and what the product says follows from reading 1 and 2.

## Threats, stated in advance

- **Selection toward easy chemistry.** Only papers with an explicit route of 4 reactions or fewer qualify: 51 of 190. The planner's recovery of long, hard, unpublished-in-detail routes is not measured.
- **Access.** The papers are those Alex could obtain; this is unrelated to route content but not random.
- **Reader error.** A transcription can be wrong in a way both readers and the checker missed (a plausible but wrong reactant). The tier and the two-reader design reduce it; the per-route notes record every inference. Every edit and exclusion made after reading is recorded (`refs_status.json` and each file's notes).
- **Time proximity.** The 2017 stratum is a few months after the training data and may contain similar chemistry; the 2023-2025 stratum is the cleaner test and is reported separately.
- **Stereochemistry.** A few complex targets are written without stereochemistry (flat); for those the comparison is connectivity-level.
- **Conventions.** Whether a telescoped procedure counts as one step, and which small reagents count as reactants, change some routes; the lenient match and the notes record where.
- **Small n.** With 36 comparable routes the interval on a rate near 0.4 is about plus or minus 0.15; only a large drop can be seen.
- **Same planner, same model.** This says nothing about other models.

## Expected cost and records

About 51 targets times three stocks at about 1 to 5 minutes each, plus two repeats on the primary stock: roughly 5 hours and about the same memory as protocol 2 (2.9 GB). Records (every route returned, gzipped), the references, the status table, the checker and both briefs go in `artifacts_protocol3/` (the repository holds no DOIs in its documents or data; papers are identified by file stem, author, year and topic, and the stem-to-DOI table is kept in the maintainer's library). A `RESULT_3.md` and an update of the design note follow the run.

## What gets built after approval (not before)

`run_quality_3.py` (reads the references, builds the three stock files and refuses as protocol 2 does), the lenient match and the reaction-level recall as pure functions with tests on synthetic routes, `judge_3.py` (the readings above), and the committed `artifacts_protocol3/`. No change under `src/` in the PR that carries the run.

## Decisions for approval (recommended answer first)

1. **Primary stock:** protocol 2's n1 stock plus the references' starting materials minus their intermediates and targets (recommended); alternatives are starting materials only, or ZINC.
2. **The lead rule stays strict, with no fallback** (recommended); the 26 papers that list other short routes stay unread.
3. **Tier B routes are in the primary analysis,** with tier A alone reported beside it (recommended); alternative: tier A only.
4. **Telescoped steps count once when the paper writes one procedure** (recommended; the readings flagged as ambiguous are listed in the notes).
5. **The reading rule of item 2** (lower tail below 0.05 against protocol 2's depth rates; otherwise "no evidence of a drop") and no GO / PARTIAL gate.
6. **Late papers:** papers that arrive before this freezes are read and added; none after (recommended).
7. **The pilot's eight routes stay out** (recommended).
8. **When to run it,** given the queued ORCA runs (about 5 hours, CPU-heavy).
