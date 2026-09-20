# Benchmark history — `iupac_namer`

Score per change against `benchmarks/naming`, scored by OPSIN round trip and
not by string match. The corpus was 124 molecules through the rows below and
is now 165; the revision each row was measured on is stated. Regenerate with:

```bash
uv run --no-sync python benchmarks/naming/score.py benchmarks/naming/predictions_check.json
```

The headline number is deliberately not the only column. It can sit still
while one molecule is fixed and another breaks, which is why `score.py` prints
a per-molecule delta and why the defect counts are tracked alongside it.

`gate_disagreement` appears from 2026-08-01: the scorer gained full InChIKey
as a second gate, and rows where the two gates disagree are surfaced for a
human rather than scored either way. It is not a regression — it split the
existing `wrong_structure` bucket into "genuinely wrong" and "same substance,
different depiction".

Rows below are all against the **124-row** corpus revision:

| date | change | correct | exact | equiv | gate-dis | wrong | Sev A open | vendored suite |
|---|---|---|---|---|---|---|---|---|
| 2026-08-01 | as vendored | 120/124 | 71 | 49 | — | 4 | not yet measured | 2940 P / 5 F / 16 S |
| 2026-08-01 | WS-1 instrumentation + InChIKey gate | 120/124 | 71 | 49 | 2 | 2 | 5 known | 2953 P / 5 F / 16 S |
| 2026-08-01 | WS-2/3 test expectations + ring polyacylium | 120/124 | 71 | 49 | 2 | 2 | 14 measured, 7 fixed | 2962 P / 0 F / 16 S |
| 2026-08-01 | WS-5 ylium/ide locant | 120/124 | 71 | 49 | 2 | 2 | 14 measured, 16 fixed | 2971 P / 0 F / 16 S |
| 2026-08-01 | WS-4 charge next to unsaturation | 120/124 | 71 | 49 | 2 | 2 | 7 open, 26 fixed | 3039 P / 0 F / 16 S |
| 2026-08-01 | WS-9 refusal guard | 120/124 | 71 | 49 | 2 | 1 + 1 no-pred | 7 open, 26 fixed | 3046 P / 0 F / 16 S |
| 2026-08-01 | WS-6 PIN consistency (Sev B) | 120/124 | 71 | 49 | 2 | 1 + 1 no-pred | 7 open, 26 fixed | 3047 P / 0 F / 16 S |

The last row is the only one where a molecule moved: diazomethane
`wrong_structure -> no_prediction`. The score is unchanged because both are
failures — but one of them was a confident wrong answer and the other is an
honest refusal, which is the trade the refusal guard exists to make.

## Why the score did not move — and then did

Every severity-A fix above repaired molecules the corpus did not contain. It
is a general-purpose naming benchmark — 124 molecules across aliphatics,
aromatics, heterocycles, drugs, stereochemistry, isotopes — and its one
`charged_zwitterion` category (8 rows) happened to include no carbocation, no
carbanion and no polyacylium. **The benchmark could not see the single largest
correctness problem the engine had.** Its role through that work was as a
veto, not a scoreboard: it proved that changes to a core renderer and a
perception classifier broke nothing mainstream.

The corpus was then extended with 41 charged species in four new categories
(`carbocation`, `carbanion`, `onium_ion`, `polycharged`), deliberately
including species that still fail. Running the **pre-work engine** against
that same extended corpus gives the comparison that was missing:

| corpus | | corrected | exact | equivalent | wrong structure |
|---|---|---|---|---|---|
| 165 rows | as vendored | 148/165 (90%) | 79 | 69 | 15 |
| 165 rows | after this work | **164/165 (99%)** | 80 | 84 | **0** |
| 181 rows | as vendored | 157/181 (87%) | 81 | 76 | 22 |
| 181 rows | after this work | **180/181 (99%)** | 82 | 98 | **0** |

Both engines were run against both corpus revisions, so each pair is a like
for like comparison. The 181-row revision is the current one.

**These four figures are as scored at the time, deliberately.** The scorer
has since gained a `tautomer` outcome class, under which this engine scores
**181/181** on the 181-row corpus — metformin round-trips to a different
tautomer of the same substance, which is a success. Restating only the row
that benefits would break the like-for-like comparison, and rescoring the
`as vendored` rows needs that engine re-run. The table stays as measured;
the current number is in the dated log below.

| category | as vendored | after |
|---|---|---|
| carbocation | 7/12 | **12/12** |
| carbanion | 4/8 | **8/8** |
| onium_ion | 8/9 | **9/9** |
| polycharged | 9/12 | **12/12** |

**No wrong structures remain, and nothing is refused or unparsable.** The two
failures are tautomers — same InChIKey, not errors. Every molecule in the
corpus gets a name, and every name denotes the molecule it was given.

All three defects the new categories exposed — phenyl anion (D-003),
guanidinium (D-004), azide (D-016) — were fixed within a day of being made
visible. That is the corpus doing its job: none of them was findable from the
124-row revision, and each was obvious once it appeared as a red row.

| date | change | correct | notes |
|---|---|---|---|
| 2026-08-01 | corpus extended to 165 | 158/165 | +41 charged species; baseline on the same corpus is 148/165 |
| 2026-08-01 | aromatic ring carbanion + guanidinium | 160/165 | carbanion 7/8 -> 8/8, onium_ion 8/9 -> 9/9; delta reported both rows as FIXED |
| 2026-08-01 | azide | 161/165 | polycharged 11/12 -> 12/12; all four charged categories now perfect |
| 2026-08-01 | pyrazolone in substituent position | **162/165** | novel_unregistered 3/4 -> 4/4; **wrong_structure count reaches 0** |
| 2026-08-01 | pyrazole stem (severity B) | 162/165 | unchanged by design -- both stems denote the same molecule; the fix is which one is preferred |
| 2026-08-01 | the last five open severity-A defects | **163/165** | diazomethane no_prediction -> equivalent; **zero wrong structures, zero refusals, zero unparsable** |
| 2026-08-01 | poly-N-substituted guanidinium (D-025) | 163/165 | unchanged: the corpus contains no substituted guanidinium. Verified by the defect table, not the score |
| 2026-08-01 | ring N-oxide substituents (D-024) | 163/165 | unchanged, and not in the corpus either. **Severity-A open list reaches empty** |
| 2026-08-01 | indicated hydrogen preserved (D-026) | **164/165** | 1,2,3-triazole gate_disagreement -> equivalent. The one remaining failure, metformin, is a genuine depiction difference |
| 2026-08-01 | corpus extended to 181 | **180/181** | +16 rows covering the last three fixes: n_oxide 6/6, guanidinium 5/5, tautomer 5/5 |
| 2026-08-04 | `tautomer` scored as the success it is | **181/181** | no engine change. Metformin round-trips to a different tautomer of the same substance; the scorer now says so instead of counting it wrong. Awarded only when canonical-tautomer AND InChIKey both agree |

The extension paid for itself immediately. Every defect fixed in the rows above
was surfaced by the new categories or by the one corpus row that happened to
carry a pyrazolone, and together they moved the headline number 158 -> 163 —
which the previous six changes, all real severity-A fixes, could not do at all
on the 124-row revision.

### Why the corpus was extended twice

Three consecutive fixes — D-024, D-025, D-026 — could not move the score,
because the corpus held no ring N-oxide substituent, no substituted
guanidinium, and no tautomer pair. Each had to be verified against the defect
table instead. A score that cannot move is a score that cannot regress either,
so the second extension exists to close that blind spot rather than to raise
the number.

It half worked, and the as-vendored comparison below says which half.
`guanidinium` goes 0/5 -> 5/5 and `n_oxide` 4/6 -> 6/6, so those rows do catch
their defects. `tautomer` reads 5/5 on both engines: the as-vendored one
emitted the bare name `1,2,3-triazole`, which OPSIN resolves to 1H, so it
round-tripped by accident. D-026 is caught by the pre-existing `heterocycle`
row instead. New rows do not automatically see the defect they were added
for — that has to be checked, not assumed.

### Consequence worth knowing

Predictions files recorded against the 124-row corpus — including the ML
baselines in `predictions_full.json` — **cannot be rescored** against the
extended corpus. `score.py` now refuses them rather than letting `zip()`
silently truncate and report a model's 88/124 as "88/181". Those files remain
valid against the corpus revision they were made for. This now applies to the
165-row revision as well.

## The 187-row revision (2026-09-17)

Six molecules added as `substituent_naming`, from a user report: three
fentanyls and three MPMI tryptamines. Every one of them ROUND-TRIPPED while
wrong, which is why the EXACT column is what moves here.

| date | change | correct | exact | equiv | stereo_wrong | vendored suite |
|---|---|---|---|---|---|---|
| 2026-09-17 | master 8be42b6, 187-row corpus | 184/187 | 82 | 101 | 3 | 3209 P / 0 F / 16 S |
| 2026-09-17 | D-027 substituent stereo inheritance | 187/187 | 82 | 104 | 0 | 3209 P / 0 F / 16 S |
| 2026-09-17 | D-028 alphanumerical order | 187/187 | 82 | 104 | 0 | — |
| 2026-09-17 | D-029 free-valence numbering | 187/187 | 87 | 99 | 0 | 3255 P / 0 F / 16 S |

On the OLD 181-row revision, for comparison with the rows above: 181/181
throughout, exact 82 -> 84 (the two nicotine rows, whose `-5-yl` locant D-029
fixed).

`stereo_wrong` is new in `score.py`. A name whose descriptor CONTRADICTS the
structure was scored `stereo_lost` -- "silently flattened" -- which is the
same conflation the app's own round-trip verifier had. It now asks that
verifier (`naming_providers._stereo_verdict`), so the benchmark and the
displayed name cannot disagree about what "wrong" means.

**D-028's whole point is invisible here**, and that is the lesson of this
revision rather than a gap in it: four corpus names changed to the correct
prefix order (chloroquine, atenolol, omeprazole's sulfoxide, the biaryl urea's
N/N') and the score did not move, because a mis-ordered name parses to the
right molecule. Those defects are pinned by exact-name rows in
`tests/test_namer_known_defects.py` and by the sort-key table in
`tests/vendor/iupac_namer/test_assembly.py`.

## 2026-09-17 -- naming round 3: 187/187, exact 87 -> 98; held-out 39/40 -> 40/40

| stage | regression exact | held-out | what moved |
|---|---|---|---|
| baseline | 87 | 39/40, one wrong_structure | -- |
| D-030 bridged free valence | 87 | 40/40 | the held-out adamantane; 5 malformed organoelement suffixes became well formed |
| D-031 fused free valence | 89 | 40/40 | both naproxen rows |
| D-032 plan budget | 92 | 40/40 | Si, P and I parents finally proposed |
| D-033 mononuclear locant | 93 | 40/40 | betaine; silyl prefixes |
| D-034 nesting order | 93 | 40/40 | 6 names re-bracketed; PubChem uses brackets throughout, so none can become exact |
| D-035 isotope hyphen | 93 | 40/40 | PubChem discards the isotope on both rows |
| D-036 retained names | 97 | 40/40 | +5 exact, and chloroform exact -> equivalent because PubChem's own string is the non-preferred one |
| D-037 ring names | 98 | 40/40 | benzofuran |

Stage records for every row are in `benchmarks/naming/stages/`. The held-out
PubChem-verbatim count stayed at 14/40 throughout, which is the honest
generalisation signal: every fix here was made on the regression corpus.

## 2026-09-18 -- naming round 4: 187/187 throughout; verbatim 98 -> 101; the fresh held-out set 9 -> 15

Three populations, and only the last one is a generalisation number
(`benchmarks/naming/README.md`). Round-trip correctness never moved from
187/187 and 40/40 on the two active sets; what moved is agreement with a
name, which the round trip cannot see.

| stage | regression verbatim | heldout_v1 verbatim | what moved |
|---|---|---|---|
| baseline (99b6281) | 98/187 | 14/40 | -- |
| stage 5a/5b comparator | 98 | 14 | decisions identical under 5a; 5b's two reorders enumerated |
| A3 N-H numbering, locant omission | 99 | 14 | benzenediazonium; cid4000 at its target |
| A4 retained parents | 100 | 14 | 1,4-xylene |
| A5 P-58.2 hydrogens | 101 | 14 | |
| A5b esters, aminium | 100 | 14 | methylammonium LOST verbatim to the book's `methanaminium` |
| A5c/A5d | 100 | 14 | chloroquine to its adjudicated name |
| A9a enclosing marks, alkoxy | 102 | 15 | |
| A9b locants, amido | 100 | 14 | four acetate-locant losses where PubChem keeps "2-" and the book drops it |
| A9c preferred prefixes | 100 | 15 | |
| A10, A8, A7 | 100 | 15 | no corpus row at their targets; the defect table carries them |
| A6 heteroatom parents | 101 | 16 | trimethylsilanol, phenylboronic acid, cid32000; cid55000's dihydrazide |
| A11, A12 | 101 | 16 | no names changed (0/187, 0/40) |

Every stage's record is in `benchmarks/naming/stages/r4-*.json`, including
the count of changed winning hypotheses, so a stage that changed decisions
without changing text is visible too.

### The final evaluation (`--final-evaluation`, stage r4-final)

| population | round trip | PubChem verbatim | engine = adjudicated PIN | PubChem = adjudicated PIN |
|---|---|---|---|---|
| regression (187) | 187/187 | 98 -> **101** | **28/30** | 15/30 |
| heldout_v1, used for tuning (40) | 40/40 | 14 -> **16** | **14/16** | 5/16 |
| heldout_v2, fresh (40) | 40/40 -> 40/40 | **9 -> 15** | not adjudicated | not adjudicated |

The v2 "before" is the baseline commit scored on the same frozen set after
the round (`r4-baseline-v2-final.json`), in aggregate: nothing in v2 was
looked at row by row, before or after. Its +6 is larger than either set the
round was tuned on, which is the evidence the fixes are rules rather than
rows.

The preferred-name columns are over rows with a SETTLED target in
`adjudication.toml`. PubChem agreeing with the adjudicated PIN on only half of
them is why the verbatim column is reported but not optimised: A5b and A9b
each LOST verbatim matches by moving to the book's form.

heldout_v2's round-5 candidates: no structural failure (0 wrong structures,
0 unparsable); 25 rows differ from PubChem and are unadjudicated, so they are
candidates for round 5's adjudication, not defects yet.

## Naming round 5 (from 2026-09-19)

### N0: the populations, fixed before any diagnosis

| population | role this round | file | baseline (`r5-baseline`, ba006cb) |
|---|---|---|---|
| regression | tuning, per-stage invariant | `corpus.json` | 187/187 round trip, verbatim 101/187 |
| heldout_v1 | used since round 4 | `heldout.json` | 40/40, verbatim 16/40 |
| heldout_v2 | **used from round 5** (N1 adjudicates its 25 differing rows) | `heldout2.json` | 40/40, verbatim 15/40 |
| heldout_v3 | **fresh, evaluation only** | locked; see the benchmark README | not scored until the final evaluation |

The baseline reproduces round 4's final record row for row (0 names changed
against `r4-final.json` in every population). heldout_v3 was drawn by the same
filter at stride +250, excluding all three earlier files: 40 rows, 39 with a
trusted PubChem target, 1 with stereochemistry, rejected 19 multi-component
and 4 out of the heavy-atom range. One fragment of one row leaked through an
OPSIN warning during the quiet draw; its meta file records exactly what, and
the builder now suppresses those warnings on quiet runs.

Every later report in this round prints four populations separately and never
pools them: regression x/187, v1-used y/40, v2-used z/40, v3-fresh w/40 (end
only).

### N1: adjudication and triage

heldout_v2's 25 differing rows, each read against the Blue Book (20 new
quoted rules in `adjudication.toml`):

| verdict | rows | what it means for the engine |
|---|---|---|
| PUBCHEM_NOT_PREFERRED | 15 | the engine's name is the book's form; PubChem's style differs (enclosing marks, dropped locants, `azanium`, `chromene`, `trans-`) |
| ENGINE_WRONG | 3 | the phosphoryl prefix; `propoxy` is substitutable and was not contracted; an ylidene prefix enclosed and given added hydrogen |
| BOTH_NOT_PREFERRED | 1 | `propane-2-sulfonyl`, which neither writes |
| UNDECIDED | 6 | four need general fusion to derive the PIN (P-52.2.4.1 rules out the von Baeyer names); `tabun` and a nucleotide sugar sit on unaudited vocabulary |

So of v2's 25 "misses", 15 are not engine defects at all, which is what a
PubChem-verbatim score cannot show. Nine round-4 leftovers that existed only
in the session record got rows too (8 with a quoted target, 1 undecided),
and CS2 and the pinacol boronate, which already had rows, got layers.

Every OPEN or UNDECIDED row (28) now names its layer and the stage expected
to take it; "deferred" is not a class. By layer: candidate absent 11 (N3 4,
N4 7), serialization 8 (N7 2, N8 6), candidate misranked 3 (N6),
candidate unsupported 2 (N5), source unresolved 4. The guard
(`test_every_open_row_says_which_layer_it_fails_in`) was mutation-checked.

Two KNOWN_LIMITATIONS entries were stale and are corrected: oxalyl
dichloride (fixed in round 4) and the four dead acyl keys (already removed).

### N2: atom ownership on the tree (`r5-N2-ownership`)

Measured in record mode before anything was enforced: 30 double-owned levels
in 22 of 267 molecules and 0 unowned atoms; every one of the 30 was a suffix
SMARTS counting its context neighbours, fixed by reading the pattern's
context atoms rather than by loosening the check. After: 0 violations in
strict mode, and the stage artifact shows 0/187, 0/40, 0/40 names changed and
0 winning hypotheses changed. Mutation-checked 6/6 (no stamp, the executor
skipping the check, context not subtracted, no element rule, no component
rule, enforce keeping the bad tree). Reach: 201 of the 267 molecules have at
least one audited level; the rest are named by a single leaf (63), a
pre-plan string dispatcher (2) or additively (1).

### N3: general fusion nomenclature (`r5-N3-fusion`)

Two populations, counted separately as the plan requires.

**Source fixtures, the book's own P-25 examples** (every "(PIN)" name on pdf
pp. 204-256 that OPSIN parses back to a structure; 125 ortho- or ortho- and
peri-fused systems). Before N3: 13 exact. After: 79 in the supported class
(one parent, first-order attached components, rings of 3 to 8), of which 78
are exact end to end and the 79th differs only because the book's table
prints quinolizine without the "4H" its PIN carries (p. 203). The other 46
are refused with a stated reason -- 16 need a second-order attached
component, 10 are multiparent, 8 have a 7- or 8-membered ring fused on three
or more sides (the drawing model agreed with OPSIN on 4 of those 8, so the
shape is refused, not guessed), 6 have interior heteroatoms, 5 need distorted
ring shapes, and 1 is a helicene. The whole-system numbering agrees with
OPSIN's on every in-class example that can be probed (101 of 101 by chloro
probes, plus 40 of 40 common drug scaffolds).

**Corpus-discovered** (tuning populations only, never v3): 4 fused systems
the ring table did not name -- cid5000, h2cid3500, h2cid23500, h2cid55500.
All 4 now carry fusion names that round-trip; h2cid23500 is identical to
PubChem's string. The plan's other named fixtures: the book's 2-benzazepine
is exact; budesonide (cid40000) is outside the class (its steroid would be a
second-order component) and keeps its von Baeyer name.

Stage artifact against N2: regression 0/187 names changed; v1 1/40 (cid5000);
v2 4/40 (the three fusion rows and h2cid20500, whose "9H-fluoren-9-imine" is
P-58.2.3.1.1's form -- the planner reached the ring once the constructor
supplied its hydrogens); 0 structurally regressed. A draft of the whole-
retained change took trans-decalin's stereo away (caught by this artifact,
fixed before commit). Mutation-checked 9/9.

The vendored suite then found what no corpus molecule reaches: the preference
key had no tier for indicated hydrogen, which P-14.4 (b) ranks before the
suffix (p. 74), so the ring table's per-numbering variants were chosen on a
substituent's locant -- "4-chloro-3H-perimidine" for 9-chloro-1H-perimidine
(p. 201: "the PIN is 1H-perimidine"). The tier was added; its first draft
scored a name with no block as the empty (best) set and turned h2cid20500
back into "fluoren-9-imine", so a missing block ranks last. With it: 0 names
changed in any tuning population, 9 perimidine expectations moved, the
book's "2H-pyran-6-carboxylic acid" held as a converse, mutation-checked 2/2.

### N4: candidate generation (`r5-N4-candidates`)

Three constructions, measured on the book first. Multiplicative names: 22 of
the book's P-15.3 / P-51.3 PINs exact, 9 of its substitutive converses held,
and every built name round-trips (`test_multiplicative_round_trip.py`).
Hydrazine as parent: the book's p. 755-758 and p. 668-671 names exact
("phenylhydrazine", "hydrazinecarboxamide", "N-phenylhydrazinecarboxamide",
"N,1-dimethylhydrazine-1-carboxamide", "2-(hexan-3-ylidene)-N,N-diphenyl-
hydrazine-1-carboxamide", "hydrazinecarboxylic acid", "hydrazinecarbothioamide",
"hydrazinecarbohydrazide", "2-(hydrazinecarbonyl)benzene-1-sulfonic acid").

Stage artifact against N3: regression 1/187 changed -- the pinacol boronate
now takes its heterocycle as parent (PubChem's string, P-44.2.1 (a); an open
row settled). A draft had also changed hexamethyldisiloxane, to
"oxybis[tri(methyl)silane]", until the constructor was taught that Si-O-Si is
a chain; it is unchanged. v1 1/40 (cid45000, the multiplicative bis-guanidine,
derived); v2 0/40; 0 structurally regressed. Vendored suite: 7 expectations
moved (methylhydrazine, phenylhydrazine, benzylhydrazine, three
semicarbazones to the book's hydrazine-1-carboxamide form, sulfamate), then
green. PubChem's
generator writes no multiplicative names, so this stage moves the
PubChem-exact count only where the adjudicated target moves with it.

Tried and reverted: admitting an acylated N' to the hydrazide pattern reached
"N'-benzoylbenzohydrazide (PIN)" and turned 4-(2-benzoylhydrazinyl)-4-
oxobutanoic acid into a butanedioyl name; it stays open (D-088a). Mutation-
checked 18/18.

### N5: retained parents and the OPSIN registry gate (`r5-N5-registry`)

The gate refuses a retained-name RECORD from OPSIN's parse dictionary unless
the registry types it with NORMATIVE_RULE evidence, and binds an audited
demotion to every table that spells the name. Over the registry's 295
entries: 174 untyped OPSIN copies and 27 audited demotions refused; 94 usable
(19 audited PINs, 75 unaudited with no OPSIN provenance). Of the 1,824-name
vocabulary file, the 206 names that could ever stand alone are all refused.

What the tuning populations depend on (`tools/retained_name_audit.py
--reachable`, v3 excluded): 12 registry entries win a name, all 12 audited
after this stage typed guanidine (PIN, p. 350) and tabun (absent from the
book); 33 more winners come from the curated ring and inorganic tables. Of
the 44 retained RING parents that win a plan at any level, 10 exist only in
OPSIN's ring vocabulary, and all 10 are names the book uses (purine,
9H-fluorene, phenanthrene, pyrrolidine, imidazolidine, pyrylium, ...).

Stage artifact against N4: regression 1/187 changed -- hexamethyldisiloxane
leaves PubChem's two-silane string for the disiloxane parent, verbatim 102 ->
101 on purpose (its locants wait for P-14.3.4.5, N8); v1 1/40 (cid55000,
oxalohydrazide); v2 2/40 (tabun gated; the nucleotide's "adenin-9-yl" now
"6-amino-9H-purin-9-yl"); 0 structurally regressed. Of the four, two are the
gate's (both v2) and two the new parents'. Mutation-checked 22/22. Vendored
suite: bare xanthine's expectation moved to the systematic name, and the
book's "N1,N2-bis(cyanomethyl)oxamide" -- which OPSIN cannot parse -- is a
declared, checked exemption; then 4200 passed.

### N6: principal-group seniority and assignment (`r5-N6-pcg`)

No tuning-population name changed (0/187, 0/40, 0/40): every N6 class is
outside the corpora, and each is pinned by a D-row with the book's page --
the five P-66.1.6.1.1.5 urea/amide examples, the P-66.4.1.3.2 amidine, the
p. 748 silanols, the p. 586-587 hydroxamic acids and the p. 535 enol, all
exact. The probe found one WRONG MOLECULE the corpora never reached:
"4-carbamimidoylbutanoic acid" for H2N-C(=NH)-CH2CH2-COOH, the prefix's
carbon counted twice; and "4-(carbamimidoylmethyl)benzoic acid" for an
N-substituted ring amidine, now the book's second form. The N2 ownership
guard missed the first because a prefix's CLAIMED atoms are not the atoms
its NAME denotes -- recorded as an audit-reach gap. Mutation-checked 19/19
(one mutation first written as a no-op, and one guard found only once
tests/test_feature_vocabulary.py joined the run). Vendored: one enol
expectation moved ("1,2,5,6-tetrahydropyridin-3-ol"), then green.

Re-probing every adjudication row assigned to N3-N6 closed the stage-bound
list: the quinolizinone, OPEN since N1, already gave 4H-quinolizin-4-one
(pinned as D-091w; which earlier stage fixed it was not bisected), and
h2cid10500, left for N3 to classify, is not in N3's corpus-discovered
population, so it moves to 'later' as a von Baeyer main-ring question.

### N7: numbering (`r5-N7-numbering`)

No tuning-population name changed (0/187, 0/40, 0/40). The layer was proved
before the comparator was touched: for "(5-chloropyridin-1(2H)-yl)acetic
acid" both orientations were generated and carried their numbering, and
their keys were identical down to the prefix tier, which chose 3-chloro-
1,6-dihydro. The one change -- the retained hydro route records its hydro
atoms, and their locants join P-14.4 (e)(i)'s tier -- fixed both plan cases
(D-092a-d, with converses) and each is invariant under atom permutation,
Kekule input and random SMILES traversal. Mutation-checked 4/5; the fifth
(the primary orientation losing its hydro atoms) is equivalent, since that
orientation is built as the lowest-hydro one and an empty tier ranks best.

The two adjudicated N7 rows moved to N8 without an engine change. cid56000's
thiazolidine had been right since r4-final (the row's engine name was a
stale snapshot). h2cid28500's added hydrogen was RE-ADJUDICATED: the book
keeps hydrogen at an ylidene position three times ('2-ethylidene-2H-indene
(PIN)', pdf p. 932, and a tricyclic on pdf p. 642) against the bicyclic
'3-sulfanylidene-2-benzothiophen-1-one' once, so '1(3H)' stands. Both keep
an enclosure defect for N8. PubChem-vs-preferred on v2 moves 2 -> 1/23 for
that reason alone.

### N8: serialization (`r5-N8-serialization`)

The stage the plan gates hardest: every candidate was classified before any
code moved, and only the five LEXICAL ones were built -- a case qualifies
only if the candidate, its interpretation and its ranking all stay put.
Measured: 5 names changed (regression 1/187, v1 1/40, v2 3/40) and **0
winning hypotheses changed** in any population, 0 structurally regressed.
Engine-vs-adjudicated rose in all three: 29 -> 30/31, 16 -> 17/18, 18 ->
20/23, which is the whole point of the stage -- the changes move names onto
their adjudicated targets without touching what the engine decided.

Built: the one-stem ylidene prefix unenclosed (P-16.5.1.3); the elision that
exposed at a prefix/parent junction; the first-cited simple prefix bare
(P-16.5.1.3.1); P-14.3.4.5 full-substitution locant omission, engine-wide;
P-63.2.2.2 alkoxy contraction on a substituted chain; and P-66.3's
"pentanehydrazide". Six candidates were classified OUT and recorded, tert-
butyl among them: it renames a prefix and moves the alphanumerical citation
order, so it cannot be tested as neutral.

Mutation-checked 14/16. The two misses are equivalent and say so in the
code: the indicated-hydrogen condition on the locant rule is belt-and-braces
(the all-carbon test is what saves the tetrazole, and a carbocyclic parent
carries indicated hydrogen in its NAME, so "octamethyl-1H-indene" is emitted
and correct), and the hydrazide stem gate is masked for the only stems that
reach it by the retained-PIN rewrite that follows it. Three guards were
ADDED after the first mutation run left them uncovered: a two-stem ylidene
(D-092u), a ring attachment whose stem ends in "butyl" (D-092y, the case
that bites, since "cyclohexyl" could not contract anyway), and the tetrazole
and hydrazine converses (D-092w, x).

Two corrections to this round's own record came out of the classification.
The N6 note that `di(methyl)` was a defect is WRONG -- P-16.5.1.3.1 prints
`ethyldi(methyl)phosphane (PIN)` -- and two round-4 rows (cid14000's double
wrapping, the disiloxane `silyloxy`) were stale, both already correct.

### N9: the final evaluation (`r5-N9-final`)

Four populations, each with its own denominator, never pooled. `heldout_v3`
was drawn and frozen in N0, before any round-5 diagnosis, and is scored HERE
AND ONCE, as aggregates only.

| population | rows | PubChem string | equivalent | wrong molecule |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1 (used) | 40 | 16 | 24 | 0 |
| heldout v2 (used) | 40 | 15 | 25 | 0 |
| **heldout v3 (fresh)** | **40** | **13** | **27** | **0** |

**The fresh corpus found no wrong molecule.** All 40 names parse back to the
structure they were built from, 13 of them matching PubChem's string exactly.
That is the round's one unbiased measurement, and it is the same shape as
round 3's first v1 run, which DID find one (D-030) -- so the instrument is
known to be capable of failing.

**Agreement with PubChem's strings did not move in round 5**: 101/187, 16/40
and 15/40 are what round 4 ended with. This is the honest headline and it is
not a surprise: the round's work was fusion names, the registry gate,
principal-group seniority and serialization, and PubChem does not print
preferred IUPAC names for those cases either. Where a name changed, it
usually moved from one `equivalent` string to another.

**Agreement with the ADJUDICATED preferred name is the metric that moved**,
and it moved in every population that has one:

| population | round 4 end | round 5 end |
|---|---|---|
| regression | 28/30 | 30/31 |
| heldout v1 | 14/16 | 17/18 |
| heldout v2 | not adjudicated | 20/23 |

PubChem against the same targets: 15/31, 5/18, 1/23. The v2 figure fell from
2 to 1 when N7 re-adjudicated h2cid28500 away from PubChem's form on the
book's own majority.

**The registry audit changed nothing in the corpora** -- 0 names in all three
tuning populations -- which is what the N5 report predicted when it measured
those 75 entries as unreached. It did find three entries that named the wrong
molecule; see LESSONS.
