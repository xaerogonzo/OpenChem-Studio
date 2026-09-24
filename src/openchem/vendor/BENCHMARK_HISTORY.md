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

**The evaluation was run TWICE, and both runs are committed.** The audit's
demotion of "methanediol" exposed a locant defect under it (the systematic
route wrote "methane-1,1-diol"; P-14.3.4.6 omits locants on a mononuclear
parent), so the engine changed AFTER the first final run. Rather than reuse
a number measured on different code, the whole evaluation was repeated
(`r5-N9-final-recheck`) and compared: **0 names changed in all four
populations, heldout_v3 included**, so the fresh corpus's 13/27/0 is the same
on both. The fresh corpus has now been scored twice, which is stated here
rather than hidden: the second scoring was forced by a code change, it was
compared row for row against the first, and nothing about v3 informed the
change -- it came from the vendored suite.

## 2026-09-20 -- naming round 7: the charged-species panel, and the fresh set found one wrong structure

Round 7's target was a class NO corpus contained (a carboxylate or sulfonate beside
another group), so the round's principal measurement is a panel built by class,
`benchmarks/naming/charged_panel.toml`, not a corpus score. Both are reported here.

### The panel, before and after (108 rows, frozen before any fix)

| | baseline | round end |
|---|---|---|
| wrong molecule | 13 | 0 |
| non-preferred | 42 | 9 |
| exact preferred | 45 | 90 |
| ownership holes (a charged site no route owns) | 47 | 0 (2 rows are a declared UNSUPPORTED edge) |

No row got worse. `PREFERENCE_UNKNOWN` rows are reported apart from both. The nine
not-exact rows are the four chiral amino-acid anions and glutamate (a stereo policy
comes first), the two phosphorus acids (declared unsupported), the betaine prefix
form (source unresolved) and imidazolium (abandoned under the stop rule). An
EXACT_PREFERRED result on a DERIVED row means agreement with a rule-derived target,
not that the book printed the name; 22 of 44 derived neutral-acid PINs were located in
the book text, and one target (erratum 2, pdf p. 593) was corrected after the fix was
measured. Both are disclosed in the panel header.

### The final evaluation (`r7-final`, `--final-evaluation`)

Five populations, each with its own denominator, never pooled. `heldout_v4` was drawn
and frozen in R0, before any round-7 diagnosis, and is scored HERE AND ONCE, as
aggregates only.

| population | rows | PubChem string | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1 (tuning) | 40 | 16 | 24 | 0 |
| heldout v2 (tuning) | 40 | 15 | 25 | 0 |
| heldout v3 (tuning since round 7) | 40 | 13 | 27 | 0 |
| **heldout v4 (fresh)** | **40** | **19** | **20** | **1** |

**The fresh set found ONE wrong structure.** Round 5's fresh set found none; this one
is the same instrument doing what it is for. It has NOT been diagnosed: the row was
not read, because a row read during a round becomes a row fixed during it, and a set
is fresh once. It is recorded as open, unattributed (nothing here says whether it is
a charged species, and the panel's zero says nothing about it either way). `heldout_v4`
becomes a tuning population for round 8, where the row is the first thing to read.

**Nothing moved in the four tuning populations against the last stage** (0 names changed
in each, no structural regression), and the agreement with the adjudicated preferred
name is unchanged from round 5's end: regression 30/31, heldout v1 17/18, heldout v2
20/23. That is the expected shape: the round's changes are anion names, and the
tuning corpora hold almost none. The panel, not the corpora, is where the round's
improvement is measured, and the corpora's job here was to show nothing else moved.

**v4 has no adjudicated preferred-name figure**: its targets were deliberately not
read. Its 19/40 against PubChem's string is comparable to v1-v3's 13-16 only loosely,
since a different draw of PubChem records is a different draw of PubChem's naming
habits; nothing should be inferred from the difference.

### Suites at the round's end

Vendored suite 4,515 passed (0 skipped, JRE and JAVA_HOME both set); the default app
suite as CI's two shards 5,505 and 5,902 passed, every skip an environment one (offscreen
WebGL, no PDF library, no pkasolver, the network test).


## 2026-09-21 -- naming round 8: the fresh set found no wrong structure, and the fixes were mostly in no corpus

Round 8 took the four workstreams of its plan (polyacids, condensed guanidines and ureas, protonated azoles and cations,
the round-5 open list, plus the one wrong structure `heldout_v4` had held), then ran a limitations pass whose defects
were, for the most part, in NO corpus row. So, as in round 7, the principal measurements are panels and a whole-round
comparison, not a corpus score. All are reported here, each with its own denominator and never pooled.

### The whole round, against the engine it began with (`tools/naming_ref_compare.py --base fbebdb3`)

543 structures (the round-7 panel, the round-8 addendum panel, the salt panel and the five tuning populations):
**37 names changed, 0 structurally regressed, 13 went from a name that did not read back to one that does**, and 24 changed
without changing their round-trip verdict (a preferred spelling, `enamide` for `eneamide`, `methoxy` for `methyloxy`).
The 506 others are byte-identical. Every stage also ran the same comparison against its own predecessor with a manifest of
the changes it expected; an unlisted change was a failure.

### The panels, before and after

| panel | | baseline | round end |
|---|---|---|---|
| round 7 (108 rows) | exact preferred | 79 (its own end) | 91 |
| | non-preferred | 20 | 8 |
| | wrong molecule | 0 | 0 |
| **round 8 addendum (60 rows, frozen in R0)** | wrong molecule | 8 | **0** |
| | oracle error (a name OPSIN read as another molecule) | 2 | 0 |
| | engine error (a refusal) | 1 | 1 |
| | non-preferred | 21 | 4 |
| | exact preferred | 20 | 44 |
| | preference unknown | 8 | 11 |
| | ownership holes | 2 | 0 |

The addendum panel was built from the round's class space and the round-7 findings, NOT from `heldout_v4`'s wrong row, so it
stayed independent of the observed failure. The one remaining engine error is the negative control of the biguanide work: a
true DICATION has no name yet (a dication name for a MONOcation was the wrong molecule; the control shows the engine no longer
confuses them). The four remaining non-preferred rows and the target of each are in `KNOWN_LIMITATIONS.md`.

### The final evaluation (`r8-final`, `--final-evaluation`, `heldout_v5` scored once, aggregates only)

| population | rows | PubChem string | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1 (tuning) | 40 | 16 | 24 | 0 |
| heldout v2 (tuning) | 40 | 15 | 25 | 0 |
| heldout v3 (tuning) | 40 | 14 (was 13) | 26 | 0 |
| heldout v4 (tuning since R0) | 40 | 19 | 21 (was 20) | 0 (was 1) |
| **heldout v5 (fresh, drawn and hashed in R0)** | **40** | **11** | **29** | **0** |

**The fresh set found no wrong structure.** Round 7's did (one), round 5's did not. `heldout_v5` was drawn from a new offset
(125) before any diagnosis, excluded by CID, canonical SMILES and row identity from the corpus and every earlier held-out set,
and no row of it was read: its per-row records are in a sealed sidecar (`stages/sealed/r8-final.heldout_v5.records.json`,
referenced by hash, read by no tracked script; a convention with a guard, since repository visibility cannot enforce it). The
PubChem-verbatim figure (11/40) is lower than v4's (19/40) and nothing should be inferred from the difference: a different draw of
PubChem records is a different draw of its naming habits, and "equivalent" is a success class (it round-trips), so the wrong-structure
count is the figure that measures the engine. Anything found in v5 from here is round 9's, not this round's.

**The four tuning populations moved as expected and no further:** `heldout_v3` gained one verbatim match (amyl nitrate, `pentyl nitrate`),
and `heldout_v4` turned its one wrong structure (the isothiourea `h4cid4750`, its demoted prefix written `(aminosulfanylmethylidene)amino`,
which OPSIN reads as another molecule) into a correct one. The regression corpus, v1 and v2 did not move at all over the round (0 of their rows in the whole-round comparison above). The
agreement with the adjudicated preferred name is unchanged: regression 30/31, v1 17/18, v2 20/23.

### Why the corpora barely moved, and what measured the round

Six of the limitations pass's fixes (`prop-2-enamide`, the Weinreb amide, `butane-2,3-dione`, `dimethyl carbonate`, nitrate esters,
mixed-class polyanions) had no corpus row: 0 of the 543 structures moved for most of them. They were found by naming a battery of
ordinary compounds and reading the names (`tools/naming_probe.py`), and are protected by 337 D-rows (D-100 to D-129, each red before
its fix with converses that differ by reason, each mutation-checked with the equivalent mutants written into the code) and by a
200-shape pinned-name snapshot (`tests/fixtures/naming_cation_shapes.txt`) that also pins the neighbours of every class fixed and the
open non-preferred names. The release-candidate driven check runs 18 rows through the application's own provider and asserts the
exact name, the source tag, the round-trip verdict and the structure's charge and component count (`tools/naming_app_check.py`).

## 2026-09-22 -- naming round 9: a source-backed battery first, 9 of 13 admitted findings fixed

Round 9 ran an instruments stage BEFORE any fix (a Blue Book PDF harvest, an ordinary-compound battery, a frequency census), admitted
13 findings from it into a hash-frozen ledger (`admissions_r9.toml`), and fixed 9 of them; the other 4 are recorded, not fixed
(`KNOWN_LIMITATIONS.md`, "Open after naming round 9"). Every fix has its own D-row (D-130 to D-138) and its own stage-comparison
against its immediate predecessor, in addition to the whole-round measurements below.

### The whole round, against the engine it began with (`tools/naming_ref_compare.py --base 5d910751`)

1712 structures (the round-7 panel, the round-8 addendum panel, the multicomponent/salt panel, and every tuning population):
**7 names changed, 0 structurally regressed**, every one matching a manifest entry's stated reason, layer and expected name
(`violations: 0`, `benchmarks/naming/stages/r9-release-candidate-refcompare.json`). Two of the round's 9 fixed items (the
carbodiimide and the peptide-acyl-naming worked example) touch structures that live only in the B2 battery, a population this
comparison does not cover, so they do not appear as changed rows here despite being fixed and separately verified.

### The driven check (`tools/naming_app_check.py`, the application's own provider, not the bare engine)

26/26 rows pass: the 18 pre-existing rows unaffected, plus 8 of round 9's 9 fixed items (D-133 excluded -- its fix IS an honest
`NamingError`, a refusal this table's row shape cannot represent, not a name to assert).

### Gates

Naming-consumer set (`--exclude-vendor`): 2231 passed. Vendored suite (own pytest session): 5212 passed. App gate, both shards, in a
detached worktree: `RESULT: PASS` (every chunk exit 0). One infrastructure gap found and fixed along the way:
`tools/naming_ref_compare.py` had no per-row timeout at all and hung on the same coronene-class fused-ring structure that hung
`naming_stage_artifact.py` earlier this round; ported the same persistent-worker-with-restart pattern (verified: the known-hanging
row times out at ~121s and the worker restarts cleanly).

### The final evaluation (`r9-final-evaluation`, `--final-evaluation`, `heldout_v6` and `bluebook_frozen` scored once, aggregates only)

| population | rows | PubChem string (verbatim) | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1 (tuning) | 40 | 16 | 24 | 0 |
| heldout v2 (tuning) | 40 | 15 | 25 | 0 |
| heldout v3 (tuning) | 40 | 14 | 26 | 0 |
| heldout v4 (tuning) | 40 | 19 | 21 | 0 |
| heldout v5 (tuning since R0) | 40 | 11 | 29 | 0 |
| **heldout v6 (fresh, drawn before any round-9 diagnosis)** | **40** | **13** | **25** | **2** |
| bluebook tuning | 1129 | 507 | 532 | 16 (58 unparsable, 16 no-prediction) |
| **bluebook frozen (the Blue Book harvest's held-out half, never read before this run)** | **1126** | **505** | **540** | **22** (46 unparsable, 13 no-prediction) |

Both frozen rows are FIRST-EVER scores; per-row records are sealed (`records_sealed: true` in the artifact, aggregate counts only,
no name or SMILES persisted). **Anything the two wrong-structure and the two unparsable/no-prediction columns found is round 10's
starting material, not this round's**: chasing them down now would un-freeze the very control the freeze exists to be. `heldout v3`
and `v4`'s own tuning numbers are unchanged from round 8's end (0 wrong structures each), and `bluebook_tuning`'s two rows this
round's own fixes touched (the alkynyl dianion, the phosphide anion, the imine anion, the phosphine oxide, and the carbamimidoyl
locant fix) moved from `wrong_structure` to `equivalent` or `exact`, accounting for the population's own small improvement over its
pre-round-9 state.

### Suites at the round's end

Vendored suite 5,195 passed (JRE and JAVA_HOME both set); the default app suite 11,843 passed in 16 chunks of at most 25 files
each (the Windows access violation in `conftest.dispose` ended two chunks, which passed on a retry: see `docs/LESSONS.md`); the
D-table 1,057 passed with 14 expected failures (the open rows). One deliberate deviation from the book is now a registry with a
guard, `benchmarks/naming/known_deviations.toml` (pyrene 10b/10c, perylene 12c/12d, a phenalene-type hydro ring 9b).

## 2026-09-23 -- naming round 10: all 4 of round 9's deferred items closed, each deeper than diagnosed, plus a real regression caught by the vendored suite

Round 10 closed all 4 items round 9 deferred, then ran a discovery-only extension of round 9's B3 frequency census against
6 of the round 5-8 backlog's still-open shapes (`KNOWN_LIMITATIONS.md`, "Open after naming round 10"; two clear the
admission threshold, four are genuinely rare). Three of the four fixes traced deeper than round 9's own diagnosis before
landing; the fourth (item 1's phenothiazine fix) also caused a real regression the vendored suite caught, fixed before
this checkpoint.

### The whole round, against the engine it began with (`tools/naming_ref_compare.py --base 92782b0`)

1516 structures (every tuning population `naming_ref_compare.py`'s registry exposes): **1 name changed, 0 violations**,
matching the manifest's single expected row (`benchmarks/naming/stages/manifests/r10-release-candidate.toml`,
`bb-db0d904b9c97`, item 3's polycarbocation). Items 1 and 2 (phenothiazine, spiro-xanthene) touch zero rows in this
population -- their fixture molecules (methylene blue, fluorescein) are not themselves `bluebook_tuning` rows. Item 4
introduces zero further changes on top of item 3's, verified directly.

### A regression caught before the RC checkpoint closed, not after

The full vendored suite (run once for this checkpoint, its own pytest session) found one real failure:
`test_arsanthrene_atom_locants_assign_peri_to_locant_1`. Item 1's fix had widened a numbering-matching gate too far --
"every heteroatom gets the benefit of the doubt" also covered arsanthrene's As atoms, which (unlike phenothiazine's
plain-bonded N/S) carry a genuinely structural explicit double bond in their curated key. Confirmed as caused by item
1's commit via a controlled single-file swap against the pre-round-10 version; narrowed further (a heteroatom only gets
the relaxation when it carries no explicit double bond); re-verified against both the regression test and item 1's own
D-rows before re-running the full suite. A first attempt at the narrower fix had its own bug (a flipped carbon check)
caught before committing, by re-running the same test file rather than just the one failing test.

### The driven check (`tools/naming_app_check.py`, the application's own provider, not the bare engine)

30/30 rows pass: the 26 pre-existing rows unaffected, plus 4 new rows for round 10's fixes (item 3, charge-
polycarbocation, excluded -- same precedent as D-133 and round 9's carbodiimide item: its fix IS a raised refusal, a
row shape this table cannot represent).

### Gates

Naming-consumer app session (36 files): 2241 passed, 1 skipped, 15 xfailed, checked after every one of the round's 6
commits that touched `src/`. Vendored suite (own pytest session, after the arsanthrene fix): **5,204 passed, 0
failed**, 16 skipped (JAVA_HOME not literally exported as an env var in this run, only `java` on PATH -- a documented,
benign skip class, not a failure). App gate, both shards, in a detached worktree (`--no-vendor`, since the vendored
suite was already run separately): one chunk (s1c8) failed on its first pass with a `py2opsin` `FileInputStream` error
reading its own relative temp file -- the documented CWD/temp-file collision class (`reference_py2opsin_cwd_collision.md`),
not a code issue. Re-ran the failing test standalone (passed clean) and the whole shard through the gate a second time
(s1c8: 1295 passed, 0 failed, confirming the extra pass over the original 1294): `RESULT: PASS`.

### The final evaluation (`r10-final-evaluation`, `--final-evaluation`, `heldout_v6` scored once, aggregates only)

| population | rows | PubChem string (verbatim) | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1-v5 (tuning) | 40 each | 16/15/14/19/11 | 24/25/26/21/29 | 0 each |
| **heldout v6 (fresh, drawn round 9, scored for the first time this round)** | **40** | **13** | **25** | **2** |
| bluebook tuning | 1129 | 507 | 532 | 15 (58 unparsable, 17 no-prediction) |

`bluebook_frozen` came bundled with `--final-evaluation` (the tool has no way to score `heldout_v6` alone) and was
recomputed, but verified byte-identical to round 9's own sealed per-row content -- every name, every verdict, only
per-row timing differed. Rather than commit a redundant seal for an already-frozen, already-scored-once population,
the artifact points back at round 9's original sealed file (same content, same hash) and the newly-written duplicate
was discarded, not committed -- keeping "scored once, ever" literal, not just in spirit. `bluebook_tuning`'s own two
moved rows (`wrong_structure` 16->15, `no_prediction` 16->17) are exactly item 3's shift, wrong molecule to honest
refusal, and nothing else.

**heldout_v6's 2 wrong-structure rows are round 11's starting material, not this round's**: per the same discipline
round 9 established, chasing them down now would un-freeze the very control the freeze exists to be.

## 2026-09-23 -- naming round 11: two fixes, two backlog rows already resolved, one re-diagnosed deeper

Round 11 re-verified every candidate directly against the current engine before admitting or dropping it --
round 9's own lesson (three of its eight seed hypotheses were ruled out by live testing) held again: two of
five candidates this round looked at were already fixed by other rounds' general work, never reflected back
into `KNOWN_LIMITATIONS.md` until now. Full findings: `KNOWN_LIMITATIONS.md`, "Open after naming round 11".

### The whole round, against the engine it began with (`tools/naming_ref_compare.py --base 575b5037`)

1516 structures (every tuning population the tool's registry exposes): item 1 (ketone-parent enclosure)
touched **0 rows** (its shape is not itself present in the tuning populations -- a real, if unexciting,
regression-safety result, not a sign the fix didn't fire). Item 2 (carbamimidoyl N'/N,N split) touched **4
rows, 0 violations**, matching the manifest's declared set exactly
(`benchmarks/naming/stages/manifests/r11-release-candidate.toml`) -- each verified structurally identical
via OPSIN round-trip before being added to the manifest, never the reverse.

### The driven check (`tools/naming_app_check.py`, the application's own provider, not the bare engine)

32/32 rows pass: the 30 pre-existing rows unaffected, plus 2 new rows for this round's 2 fixes.

### Gates

Naming-consumer app session (37 files): 2253 passed, 1 skipped, 14 xfailed -- checked after both of the
round's `src/`-touching commits. Vendored suite (own pytest session): **5,207 passed, 0 failed**, 16 skipped
(the same documented, benign skip class every prior round recorded). App gate, both shards, in a detached
worktree (`--no-vendor`): **RESULT: PASS**, every chunk on its first attempt, no retries needed. (One
self-inflicted false start: the gate's `--out` flag was passed pointing at the SAME path the script
auto-derives for the worktree itself from `--sha`, so the script's own `rm -rf "$OUT"` step deleted the
freshly-checked-out worktree before any tests ran -- `git worktree prune` and a clean re-run without `--out`
recovered it; no committed work was at risk, since the deleted worktree held only a disposable checkout.)

### The final evaluation (`r11-final-evaluation`, `--final-evaluation`, `heldout_v6` + `bluebook_frozen`)

| population | rows | PubChem string (verbatim) | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1-v5 (tuning) | 40 each | 16/15/14/19/11 | 24/25/26/21/29 | 0 each |
| heldout v6 (frozen, round 9) | 40 | 13 | 25 | 2 (round 11's starting material, not this round's -- see round 10's own note) |
| bluebook tuning | 1129 | 507 | 532 | 15 (58 unparsable, 17 no-prediction) |
| **bluebook frozen** | **1126** | **505** | **540** | **22 (46 unparsable, 13 no-prediction)** |

**`bluebook_frozen` genuinely changed this round**, unlike round 10 where the re-score was byte-identical to
round 9's own seal and the duplicate was discarded. Diffed directly against round 9's original sealed
content (never assumed): exactly 2 rows differ, both item 2's own already-verified carbamimidoyl N'/N,N fix
reaching this frozen population, both scoring `equivalent` before and after (re-verified via OPSIN
independently, same standard as every other row this round touched). A genuine fix reaching the frozen
population and changing its printed string is the expected, correct outcome of shipping a real fix --
"scored once, ever" governs re-TUNING against the frozen set, not freezing its strings forever. The newly
sealed file is committed under this round's own name
(`sealed/r11-final-evaluation.bluebook_frozen.records.json`), not pointed back at round 9's.

## 2026-09-23 -- naming round 12: a charged acid inside a substituent (D-144), and a triaged census signal

A deliberately small round: one fully diagnosed item and one census signal that had never been triaged. Full findings:
`KNOWN_LIMITATIONS.md`, "Open after naming round 12".

### The whole round, against the engine it began with (`tools/naming_ref_compare.py --base fcb35a19`)

1712 structures (the r7, r8 and multicomponent panels and every tuning population the registry exposes): **0 changed, 0
violations**. That is not a sign the fix did not fire: no corpus row has the shape (a charged acid group inside a carved substituent),
which is why D-144 has its own FIXED rows and tests. The check that DID see the change was a different shape than the corpora: the
engine over every charged row of the frozen 2000-structure census sample (292), base against working tree, by a per-row runner that
records a refusal (`ValueError`) and an embedded `NAMING ERROR` rather than stopping at the first: **1 of 292 changed**, an
aminophosphonate zwitterion, `{(2R,4E)-6-[dioxido(oxo)phosphanyl]-1-oxido-1-oxohex-4-en-2-yl}azanium` ->
`{(1R,3E)-1-carboxylato-5-[dioxido(oxo)phosphanyl]pent-3-en-1-yl}azanium`, which reads back MATCH. It sits on a route other than the
carved one: the fix is a property of the fragment, which is what keeps it cache-safe.

### A first version regressed a documented converse, and the known-defects suite caught it

The first version added the synthesised FG to every SUBSTITUENT fragment whose acid group was charged. `D-121u`
(`[S-]c1ccccc1C(=O)[O-]`, pinned OPEN as `2-[oxido(oxo)methyl]benzene-1-thiolate`) then failed a plan ("atom 0 owned by prefix[0] and
prefix[1]") and fell back to a `NAMING ERROR` name: a fragment that IS the whole acid group, attached through its own carbon, is named by the
single-FG path and a second FG double-owned the atom. The fix skips a group containing the attachment atom. Before the guard: 1 failed,
1015 passed; after: 1114 passed, 14 xfailed (now 1126 passed with the round's own tests).

### The frozen impact, checked blind (`tools/naming_stage_artifact.py --frozen-impact r11-final-evaluation`)

A tool built this round because the ref-compare cannot reach frozen rows and rounds 10 and 11 decided by hand whether to rescore. It
prints only `unchanged` or `changed_count=N of M`. Result: **`heldout_v6` unchanged (40); `bluebook_frozen` changed_count=1 of 1126**.
The same run with the base engine's `engine.py` swapped in reported 0 for both, which attributes the one row to this round's change
without ever printing a label or a name.

### The driven check (`tools/naming_app_check.py`, the application's own provider)

36/36 rows pass: the 32 pre-existing rows unaffected, plus 4 new rows (D-144a, b, c and the classifier-route converse).

### Gates

Known-defects suite: 1126 passed, 14 xfailed; six of the twelve new cases fail with the engine change removed, and the other six (the
converses and the one-owner check) pass either way, as intended. Vendored suite (own pytest session, on the gated commit): **5,229
passed, 0 failed**. App gate, both shards, in a detached worktree at the gated commit (17 chunks, no retries): 16 chunks exit 0; the one
failure was `test_namer_probe_shapes.py::test_no_pinned_name_has_moved`, which pinned D-144a's structure as OPEN with the old name and was
updated in the next commit, together with its manifest row; that file, the manifest and the doc guards were re-run on the final tree (all
pass). The engine is byte-identical between the gated commit and the final tree (`git diff` of the engine directory: 0 lines).
(Two self-inflicted false starts, recorded so they are not repeated: `export PATH="C:/Users/.../bin:$PATH"` puts a `C` and a `/Users/...`
into a colon-separated PATH, so the gate refused to start with "no `java` on PATH" -- the `/c/Users/...` form is the one that works; and
`naming_plan_trace.py` on a molecule that never reaches plan search at top level raises `IndexError`, which is how the carved fragment was
first found to be named by a RECURSIVE call, by spying on `_name_bound` instead.)

### The final evaluation (`r12-final-evaluation`, `--final-evaluation`, `heldout_v6` + `bluebook_frozen`)

| population | rows | PubChem string (verbatim) | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1-v5 (tuning) | 40 each | 16/15/14/19/11 | 24/25/26/21/29 | 0 each |
| heldout v6 (frozen, round 9) | 40 | 13 | 25 | 2 (unchanged) |
| bluebook tuning | 1129 | 507 | 532 | 15 (58 unparsable, 17 no-prediction) |
| **bluebook frozen** | **1126** | **505** | **540** | **22 (46 unparsable, 13 no-prediction)** |

Every total is identical to round 11's. Diffed against round 11's sealed records in aggregate (a count, never a row): **`bluebook_frozen`:
1 name changed, 0 outcome classes changed; `heldout_v6`: 0 names changed**, which agrees with the blind check above. All tuning populations:
0 names changed, none structurally regressed. Scored once, after the gate passed on the final engine. The newly sealed files are committed
under this round's own name (`sealed/r12-final-evaluation.*.records.json`).

### The W2 measurement (the fused-aromatic-ring-cation census signal, round 11)

The 36 hits of `fused_aromatic_ring_cation` were named and read back (36 unique row identities, 36 unique canonical structures): 28
MATCH, 8 `PARSER_FAILED` with an embedded `[NAMING ERROR ...]` name. `naming_probe.py`'s own status counters reported 31 `clean` and 5
`fallback` for the same 36, because three of the eight emit the error as a NAME and no plan dies; the counter under-reports and the name
has to be read. Neutral parents were named for the layer (`imidazo[1,2-a]pyridine`, `imidazo[2,1-b][1,3]thiazole`, `quinolizidine`);
their cations fail with one plan executed and none valid. The failing fragments were named standalone and by ring system; the per-system
counts (4 / 2 / 1 / 1 / six singletons) are in `KNOWN_LIMITATIONS.md`, and the largest, 4/2000 = 0.2%, is under the 10-structure floor,
so nothing was admitted.

## 2026-09-24 -- naming round 13: a wrong ring locant on a heterocyclic substituent, and a demoted ketone that claimed its aryl carbon

The round began with a measurement instead of a backlog: `tools/naming_census_scan.py` (merged before the round) named all 2000 census rows and read
each back through OPSIN, and the round's `tools/naming_ring_locant_sweep.py` did the same for every curated ring. Full findings:
`KNOWN_LIMITATIONS.md`, "Open after naming round 13".

### The census, every row, before and after (`naming_census_scan.py`, 2000 rows)

| class | round-12 engine | after W1 | after W2 |
|---|---|---|---|
| exact | 1869 (93.45%) | 1896 (94.80%) | **1914 (95.70%)** |
| same connectivity | 34 | 35 | 35 |
| wrong structure, different formula | 35 | 13 | 13 |
| wrong structure, same formula | 13 | 7 | 5 |
| unparsable | 11 | 11 | 10 |
| embedded engine error | 37 | 37 | 22 |
| refused | 1 | 1 | 1 |

Candidate wrong structures 2.40% -> 0.90%; embedded errors and refusals 1.90% -> 1.15%. No row LEFT `exact` at either step. Each of the 27 W1 rows and
each of the 13 W2 rows was WITHHELD by the application before the fix (`stages/r13-baseline-reproductions.json`: 27 for the read-back mismatch, 13 for
the embedded error), so the round turned "no name" into a right name and shipped nothing wrong-and-visible. W2 moved 30 names in all: 14 embedded errors,
3 wrong structures (esters named on a ketone-parent `carboxy` prefix, the silent half) and 1 unparsable name became exact, 11 exact names became better exact names (`2-{...}-1-(4-chlorophenyl)ethan-1-one` ->
`2-(4-chlorophenyl)-2-oxoethyl 4-(...)benzoate`), and 1 row moved the wrong way (an embedded error to the pre-existing D-151 wrong structure).

### The ring-locant sweep (`naming_ring_locant_sweep.py`; 371 rings, 7,372 cases)

The ring population is committed and hashed BEFORE any result (`benchmarks/naming/ring_sweep_population.json`), and the tool refuses a stale one.

| table state | rings | tested | rings with wrong | wrong / cases | engine errors |
|---|---|---|---|---|---|
| table-less, before | 70 | 66 | 23 | 712 / 1578 | 15 |
| table-less, after | 69 | 65 | 15 | 682 / 1558 | 15 |
| partial | 6 | 6 | 4 | 13 / 113 | 6 |
| full, before -> after | 295 -> 296 | 292 -> 293 | 0 | 0 / 5,681 -> 5,701 | 0 |

Sweep cases that got worse after the fixes: 0; that got better: 26. The 682 remaining wrong cases are 638 on 11 all-carbon fused rings (bare `-yl`) and the
rest on about 7 partly hydrogenated fused rings; neither has a census row. The oracle is structural (read-back), so numbering preference is not adjudicated.
Time: baseline 939 s (build 1.2 s, naming 889 s, read-back 44 s); the rerun took 1,328 s (naming 1,261 s) because the app gate was running at the same time.
Skipped and never swept: 906 fusion atoms, 651 heteroatom sites, 78 atoms with no free hydrogen, 73 exocyclic atoms.

### The mechanisms, and the three hypotheses that were wrong

The plan named three suspects for the ring locant (an index-space mismatch, atom-map loss on canonical renumbering, the `min()` over symmetric matches).
A per-attachment trace refuted all three: the fragment's atom map was intact, and the numbering filter selected among 10 candidate numberings correctly
BY ITS OWN KEY. The key ranked a lower combined heteroatom set ahead of the senior heteroatom at locant 1 (D-145). A second mechanism was a hard-coded
locant returned verbatim (D-146, D-147) and a third was a data row keyed on the wrong ring (D-148); the ownership error (D-149, D-150) was a claim
computed one way in one pass and read another way in the next, with a silent half no read-back can see.

### Gates

- **ref-compare** (`--base d2b95a6`, master before the round): 1712 structures over r7, r8, mc and the tuning populations, 1 name changed, **0 violations**. The
  one row is an isouronium cation, recorded STRUCTURALLY_EQUIVALENT in `stages/manifests/r13-release-candidate.toml` (both names read back MATCH; the
  preferred name is not adjudicated). W1 touched no tuning row.
- **Known-defects suite:** 1170 passed, 15 xfailed (the 14 old plus D-151). Mutation checks: 14 of the 24 W1 cases and 9 of the 20 W2 cases fail with the
  engine and data changes removed; the rest are converses that pass either way.
- **Vendored suite** (own pytest session): **5,262 passed, 0 failed**. **App gate**, both shards, in a detached worktree at the W2 commit (`aea95a2c`, no
  `--out`): **RESULT: PASS**, every chunk on its first attempt. The engine and data are byte-identical from that commit to the final tree (0 diff lines); the
  later commits are tests, tools and documents, whose guards were re-run (170 passed).
- **Driven check** (`tools/naming_app_check.py`, the application's own provider): 50/50 rows, 14 of them new (10 repaired shapes and 4 boundaries that must not
  move), each verified by read-back.
- **Fork** (`xaerogonzo/open-iupac-namer`, run under the main repository's interpreter): 6,637 passed, 0 failed, 15 xfailed; engine and data numstat +48/-2 on
  both sides; no `openchem` reference in any `.py` file the round touched.

### The blind frozen impact, and the final evaluation (`r13-final-evaluation`, `heldout_v6` + `bluebook_frozen`)

`--frozen-impact r12-final-evaluation` reported `heldout_v6` 1 of 40 and `bluebook_frozen` 1 of 1126 changed. Run again with the W1-only engine it reported 0 and
0, so every frozen row that moved is W2's. The frozen set was then scored once, after the gate passed on the final engine.

| population | rows | PubChem string (verbatim) | equivalent | wrong structure |
|---|---|---|---|---|
| regression | 187 | 101 | 85 | 0 (1 tautomer) |
| heldout v1-v5 (tuning) | 40 each | 16/15/14/19/11 | 24/25/26/21/29 | 0 each |
| heldout v6 (frozen, round 9) | 40 | 13 | 25 | 2 (unchanged) |
| bluebook tuning | 1129 | 507 | 532 | 15 (58 unparsable, 17 no-prediction) |
| **bluebook frozen** | **1126** | **505** | **540** | **22 (46 unparsable, 13 no-prediction)** |

Every total is identical to round 12's. Diffed against round 12's sealed records in aggregate, never a row: **`bluebook_frozen` 1 name changed and 0 outcome
classes changed; `heldout_v6` 1 name changed and 0 outcome classes changed.** The frozen strings moved without moving any structural outcome, which is consistent with
a better name for a row that was already structurally right (it is not proof of that: no individual frozen row was read). The newly sealed files are committed under this round's own name.

### Process notes worth keeping

- The census scan's classes are what the ENGINE emits, not what a user sees. Round 12's documentation said the application shows an embedded engine error as an
  unverified name; it withholds it (and any name whose read-back is a different structure). Corrected in `KNOWN_LIMITATIONS.md` and pinned by three tests on
  real engine output.
- `naming_probe.py`'s `clean` status under-reports an embedded error (the error is emitted as a NAME, not as a dead plan), and it stops on the first refusal;
  the census scan reads the name and records a refusal instead.
- A first draft of the ring-cation count said 19 rows; only 14 of the 19 "no valid plan" rows are cations. Checked before it was written down.
- The W2 commit message calls the 3 rows that moved from wrong-structure to exact "wrong locants"; they were esters named on a ketone-parent `carboxy` prefix
  (the silent half of D-150). The documents and this table are right; the message is not, and is left as committed.
- W2 exposed, and did not create, a wrong-structure path for an ester whose acid carries a ring-nitrogen sulfonamide (D-151). The strict xfail row and a real-OPSIN
  test that uses it as its example will fire together when it is fixed.

## 2026-09-24 -- naming round 14: the measured residue, worked as clusters with one root mechanism each

The round began with a reconstruction, not a fix: the round-13 census scan had never been saved, so it was rebuilt and checked ROW BY ROW against the
saved r12 per-row baseline (`stages/census_scan_r13-engine.json`, `stages/r14-w0-provenance.json`): the same 2000 row labels, 47 rows changed class
(exactly the ones round 13 declared), 0 left `exact`, totals 1914/35/13/5/10/22/1. Definitions of `exact`, `same_connectivity` and the wrong-structure
classes, and the residue table, are in `KNOWN_LIMITATIONS.md`, "Open after naming round 14".

### The census, every row, at each committed step (`naming_census_scan.py`, 2000 rows, each `--compare`d to the step before)

| class | r13 engine | + C1/C2 sulfonyl | + C3 cations | + stereo, spiro, tables | + D-153 (final) |
|---|---|---|---|---|---|
| exact | 1914 (95.70%) | 1924 | 1932 | 1958 | **1959 (97.95%)** |
| same connectivity | 35 | 35 | 37 | 13 | 13 |
| wrong structure, different formula | 13 | 12 | 12 | 12 | 11 |
| wrong structure, same formula | 5 | 3 | 3 | 1 | 1 |
| unparsable | 10 | 7 | 7 | 7 | 7 |
| embedded engine error | 22 | 18 | 8 | 8 | 8 |
| refused | 1 | 1 | 1 | 1 | 1 |

One step regressed and was caught by the rule "no row leaves `exact`": the first C3 build gave three tricyclic purine-fused cations a fusion name OPSIN
cannot read where the von Baeyer fallback had read back exactly (3 rows left `exact`). The fix was to limit the neutral-copy path to bicyclic systems, the
scope in which it had been verified; the tricyclic cations stay on the fallback. Total: 45 rows to exact, 0 left, 5 exact tricyclic-cation rows changed name only
(a different resonance drawing gives a different von Baeyer name that reads back exactly).

### The ring-locant sweep, before and after (`naming_ring_locant_sweep.py`; 371 curated rings, 7,372 cases)

| | rings with a structurally wrong case | wrong cases | engine errors |
|---|---|---|---|
| before (r13 engine) | 19 (11 all-carbon fused, 4 other table-less, 4 partial) | 695 | 21 |
| after | 9 (4 helicenes, pyridazino-diazepine, corrin, 3 partial-table) | 274 | 21 |

The round-14 plan's "about 7 partly hydrogenated rings" was wrong; the re-run gave 8 rings that are not all-carbon fused. STRUCTURAL_FAILURE is the `wrong_structure`
outcome; structurally correct cases on table-less rings are NUMBERING_UNADJUDICATED and are not counted. Sweep runtime about 1,260 s.

### The mechanisms, with the evidence each was found by

- **Ring-nitrogen sulfonyl (D-151, D-152).** `tools/naming_probe.py --failures` showed `leaves heavy atoms [11..15] unclaimed`: the piperidine's carbons. The
  broadening (the plain acid was misnamed too, silently, because the read-back matched) came from naming the acid beside the ester.
- **Ring cations (D-154..D-157).** FOUR roots, not one, found by naming the cations ALONE: a `sys.settrace` of `try_retained_name` showed the retained lookup
  never matching, then `extract_ring_mol` showed the SAME ring key as the neutral molecule, which named fine, which located the refusal in the systematic
  fusion path (`fusion_general` raised on any charged atom); the bridgehead drawing and the acyl-prefix charge loss were separate, reproduced on their own.
- **Stereo (D-158, D-159).** A spy on `name` printed the LEAF type: `retained name: oxolan-2-yl` (no stereo) beside `parent=pyrrolidine` (stereo). The pyrrolidine
  name carried `(2R)`; the oxolane did not, though the two structures are analogues.
- **A wrong locant hidden by the sweep's own scope.** The quinolizidine nitrogen's locant `4a` (it is 5) was in a table whose every carbon locant was right;
  651 heteroatom sites are never swept. Found by a quaternary bridgehead cation, not by the instrument built to find wrong locants.

### Gates

- **ref-compare** (`--base a66644c3`, the round-13 merge): 1712 structures, 1 name changed, **0 violations** (`stages/manifests/r14-release-candidate.toml`:
  `c1c[cH+][cH+]1`, `cyclobutane` -> `cyclobutene`, not the printed bis(ylium)).
- **Known-defects suite:** 1256 passed, 15 xfailed (14 old + D-162). Each fix was broken once and its new tests failed. **Driven check:** 66/66 rows (16 new).
- **Frozen populations:** blind `--frozen-impact r13-final-evaluation`: **unchanged** for `heldout_v6` and `bluebook_frozen`, so the round-13 seal stands and no new final
  evaluation was scored.

### Process notes worth keeping

- The bridgehead-charge drawing (D-155) is one cation with its `[nH+]` drawing (the same InChIKey), but the vendored OPSIN gate compares canonical SMILES, so those
  two rows live in their own tests. The application's own provider says so with a tautomer note; the driven check records the verdict as TAUTOMER, not MATCH.
- The sweep's results are READ in three classes (STRUCTURAL_FAILURE, NUMBERING_UNADJUDICATED, CONTESTED); the tool itself still prints `wrong_structure` / `structurally_correct`, so the third class is a reading, not an output, and no ring needed it.
- The helicenes were not numbered: `fusion_orientation` declines them ("a helicene is oriented and numbered by its own rule"), and no other source for their numbering
  was at hand. A table that only OPSIN vouched for would have broken the provenance rule adopted this round.
