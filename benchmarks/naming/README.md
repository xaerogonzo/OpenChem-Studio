# Naming benchmark

A permanent, objective way to compare structure-to-name engines. When a new
model appears, run it against this corpus and compare the numbers instead of
arguing about impressions.

## Why it exists

STOUT's weights were withdrawn upstream in 2026, which forced a search for a
replacement. The first evaluation used 20 molecules and reported 80% for
`SMILES2IUPAC-canonical-base`. Rerun against 124 molecules chosen to probe
weaknesses rather than confirm strengths, the same model scores **71%** — and
the headline number turned out to hide the finding that actually mattered
(see *The decisive number* below). Twenty molecules is a smoke test, not a
characterisation.

## Files

| | |
|---|---|
| `corpus.json` | 187 molecules, 23 categories, ground truth from PubChem. The REGRESSION corpus: deliberately enriched with families the engine has got wrong. Committed. |
| `heldout.json` | 40 molecules selected WITHOUT consulting the engine -- a fixed PubChem CID stride and a filter settled in advance (`build_heldout.py`, frozen by hash in `heldout.meta.json`). The generalisation check the regression corpus cannot be. |
| `heldout2.json` | A second 40-row held-out set, drawn by the same filter (stride +500) before naming round 4 looked at anything, because round 4 spent `heldout.json` as fix targets. Locked through round 4 and scored once, at its final evaluation; marked USED in its meta file from round 5, which adjudicates its differing rows. |
| `heldout3.json` | The FRESH 40-row held-out set for naming round 5 (stride +250, all three earlier files excluded), drawn quietly before any round-5 diagnosis. LOCKED: `tools/naming_stage_artifact.py` loads it only under `--final-evaluation`, reports it in aggregate only, and `tests/test_naming_heldout_lock.py` fails if another script names it. Its failures become the next round's candidates, never fixes in the round that measured them. |
| `heldout4.json` | The fresh 40-row set of naming round 7 (a `tuning` population since round 8 began, per `populations.toml`); its one wrong structure was the first thing round 8 read. |
| `heldout5.json` | The FRESH 40-row set of naming round 8 (offset 125, drawn and hashed in R0 before any diagnosis, excluded from every earlier set by CID, canonical SMILES and row identity). LOCKED: it is scored once, by `tools/naming_stage_artifact.py --final-evaluation`, as aggregates only (11 verbatim, 29 equivalent, 0 wrong structures), and its per-row records are in `stages/sealed/`, referenced by hash and read by no tracked script. |
| `populations.toml` | The ONE registry of which population is `tuning` and which is `frozen`; every tool reads it, and a frozen population is refused before its file is opened. |
| `charged_panel.toml`, `charged_panel_r8.toml` | The charged-species panels built by class (108 rows in round 7, 60 in the round-8 addendum), each with its baseline and adjudication beside it (`charged_panel*_baseline.json`, `*_adjudication.toml`); `tools/charged_panel_report.py` reports both dimensions (structure and preference). |
| `known_deviations.toml` | The ONLY places the engine writes a name the Blue Book says not to, on purpose (the curated ring table's former-CAS interior locants: pyrene, perylene, a phenalene-type hydro ring), each with its normative target, reason and oracle statement. Reported as a KNOWN DEVIATION and never counted as a preferred match; guarded by `tests/test_known_deviations.py`. |
| `adjudication.toml` | Per-disagreement verdicts against the Blue Book, each with its rule, a quotation and the source hash. The TARGET set, since PubChem's string is a second engine's opinion. Guarded by `tests/test_naming_adjudication.py`. |
| `stages/*.json` | One record per naming change (`tools/naming_stage_artifact.py`): every row's name and round-trip class plus the toolchain versions, so "which names moved and why" is answerable later. |
| `build_corpus.py` | Regenerates `corpus.json`. `--append` adds only molecules not already present, so existing rows are never re-fetched. |
| `score.py` | Scores a predictions file and classifies every failure. |
| `predictions_full.json` | Raw output of the three models evaluated so far. Recorded against the original **124-row** corpus; see *Corpus revisions*. |

## Corpus revisions

The corpus started at 124 molecules and was extended twice in August 2026:
to 165 with four categories of charged species — `carbocation`, `carbanion`,
`onium_ion`, `polycharged` — and then to 181 with `n_oxide`, `guanidinium`
and `tautomer`.

The reason is worth recording, because it is an argument about what a
benchmark is for. A defect hunt in the deterministic engine found it was
**silently neutralizing** whole families of ions: the benzyl cation named as
`methylbenzene` (toluene), the phthaloyl dication as
`1,2-bis(oxomethyl)benzene` (phthalaldehyde). Twenty-six such cases were
fixed, and **not one of them was visible here**, because the sole
`charged_zwitterion` category contained no carbocation, no carbanion and no
polyacylium. The benchmark had been blind to the largest correctness problem
the engine had.

The new rows deliberately include species that still fail. A corpus containing
only what an engine already handles measures nothing.

The second extension was added for the opposite reason: three fixes in a row
landed in families the corpus could not see, so their score was unmoved and
nothing would have caught a later regression. Those categories start perfect —
they exist to stay that way, not to raise the number.

Ground truth for these rows is thinner on purpose. PubChem resolves a
structure it does not hold to the nearest one it does, which for ions is
routinely the neutral parent — it answers `methylbenzene` for the benzyl
cation and `propane` for the isopropyl cation. `build_corpus.py` therefore
keeps a PubChem name only when parsing it back yields the structure it was
fetched for; 24 of the 41 new rows have no trusted name and can score
`equivalent` but never `exact`. That costs nothing real: `exact` is a
tie-break, and the round trip is the actual gate.

**Predictions recorded against an older corpus cannot be rescored against a
newer one.** `score.py` refuses a length mismatch rather than letting `zip()`
truncate and report a model's 88/124 as "88/181".

```bash
python benchmarks/naming/score.py benchmarks/naming/predictions_full.json
```

`predictions.json` maps an engine label to a list of predicted names in
corpus order. Nothing about the scorer is model-specific — an engine only has
to produce that file.

## How it scores

**Not by string equality.** A molecule has many correct IUPAC names. The first
run of this benchmark marked `4-[amino(dioxo)-lambda6-sulfanyl]aniline` wrong
for sulfanilamide, which is a perfectly good name that simply is not the one
PubChem chose.

The primary metric is the **round trip**: parse the predicted name back with
OPSIN and compare structures. That is the only check that answers *does this
name denote this molecule*.

| outcome | meaning |
|---|---|
| `exact` | round-trips **and** matches PubChem verbatim |
| `equivalent` | round-trips; different valid wording — also a success |
| `tautomer` | same compound drawn as a different tautomer — also a success |
| `stereo_lost` | right skeleton, stereochemistry silently dropped |
| `wrong_structure` | parses, but to a different molecule |
| `unparsable` | OPSIN cannot read it |
| `no_prediction` | the engine returned nothing or crashed |

`stereo_lost` is separated out deliberately. An engine that quietly flattens a
chiral drug needs a different response — refuse, or warn — than one that
hallucinates a functional group, and a single "accuracy" figure hides which
you are dealing with.

## Results (2026-07-31)

Input requirements found the hard way, and mandatory for the knowledgator
models: a `<BASE>` style token must prefix the input, and the SMILES must be
**Kekulé**. The tokenizer vocabulary contains no lowercase aromatic atoms at
all — `c`, `n`, `p` are absent — so RDKit's default aromatic output becomes a
row of `<unk>` and the model invents a ring. Before this was found, every
aromatic compound came back as a phosphorus heterocycle and the model looked
worthless.

Scored against the original **124-row** corpus, which is the only revision all
four engines were run on:

| engine | correct | stereochemistry | dependencies | speed |
|---|---|---|---|---|
| **`open-iupac-namer`** (deterministic) | **120/124 (97%)** | **11/11** | rdkit only | 12 ms |
| `SMILES2IUPAC-canonical-base` (180 MB) | 88/124 (71%) | 0/11 — crashes with `IndexError` | torch + transformers, 1.1 GB | 190 ms |
| `SMILES2IUPAC-isomeric-small` (24 MB) | 75/124 (60%) | 5/11 correct, **3 silently flattened** | torch + transformers | 97 ms |
| `SMILES2IUPAC-canonical-small` (24 MB) | 71/124 (57%) | 0/11 | torch + transformers | 97 ms |

On the extended 181-row corpus the deterministic engine scores **181/181
(100%)** — 82 `exact`, 98 `equivalent`, 1 `tautomer` — against **148/165
(90%)** for the same engine as originally vendored on the revision that
existed then, the difference being the defects fixed since. **No wrong
structures remain**, and nothing is refused or unparsable.

The `tautomer` row is metformin, where engine and corpus depict the same
substance differently. It counted as the one failure until the `tautomer`
outcome class was added; it is a success, kept visibly distinct rather than
folded into `equivalent`. The ML models have not been rerun; re-running them
needs torch and the weights.

### The deterministic engine wins on every axis

[`leehiufung911/open-iupac-namer`](https://github.com/leehiufung911/open-iupac-namer)
(MIT, ~63k lines, from-scratch 2013 Blue Book implementation) beats the ML
option by 26 points while depending on nothing the app does not already have,
running 16x faster, and — the part no model managed — handling stereochemistry
perfectly. It also independently arrived at OPSIN round-tripping as its own
correctness check, which is what this benchmark scores on.

Adding full InChIKey as a second gate sorted its four failures. InChI
normalises mobile hydrogens, so a shared key means *the gate cannot tell them
apart* — which is weaker than it first looks, and is not by itself proof the
name is right:

```
1,2,3-triazole    -> 1H-1,2,3-triazole            same InChIKey  (tautomer)
metformin         -> 1,1-dimethylbiguanide        same InChIKey  (tautomer)
novel pyrazolone  -> N-{2-[1-(4-bromophenyl)-...  skeleton block DIFFERS
diazomethane      -> (azanylidyne)(methyl)azanium CH3N2+ vs CH2N2
```

The pyrazolone was previously assumed to be a tautomer too; it is not. Its
InChIKey skeleton block differs from the corpus entry, so it is a different
species — the emitted name omits the indicated hydrogen that pins the sp3 C4,
and OPSIN resolves it to the aromatic form. So **two** true structural errors
in 124, not one.

The triazole later turned out to be a third: matching keys meant only that
InChI could not see the difference, and the ring table had it labelled as the
wrong tautomer outright. Metformin is the genuine article — `biguanide` is a
retained name that carries no tautomer information for a name to lose.

All three have since been fixed. On the current corpus the engine reports
**no wrong structures at all** and refuses nothing, and it scores 4/4 on the
novel scaffolds where the ML model scored 1/6 across the whole gap.

Caveats worth stating: 1 GitHub star, self-described as experimental, and
partly built with a coding agent. Those are reasons to pin a commit and keep
the round-trip gate on, not reasons to ignore a result this far ahead.

### Forkability assessment (2026-08-01)

Measured, because "adopt or rebuild" turns on real numbers:

| | |
|---|---|
| engine | 63,129 lines — 28.6k top level, 18.9k perception, 15.4k ring naming |
| tests | 22,788 lines, 110 files, **2,907 passing / 12 failing** on upstream HEAD |
| data | 36,302 lines — Blue Book prefixes (397 KB), retained names, fusion components |
| docs | 2,994 lines of architecture documentation |
| licence | MIT, and the OPSIN-derived data tables are MIT upstream too — clean to vendor |

**It is abandoned.** Created 2026-05-24, last pushed 2026-05-24, 3 commits, one
author, zero forks, zero issues. It was published once and never touched again.

That single fact collapses the decision. There is no upstream to track, so
"depend on it" and "make it ours" are the same act — vendoring *is* the
in-house version. And rebuilding from scratch is not a real option: the 36k
lines of curated nomenclature tables alone represent months of work before a
single name is generated, and the engine encodes the Blue Book's decision
cascade that took this author however long it took.

The 12 failures are in narrow areas (xanthine retained-name fallback,
polycharged radical cations, skeletal chain replacement), not the core. One
test file (`test_fr_orientation_numbering.py`) references a `tests/audit`
package that was never committed.

Where `canonical-base` is strong: heterocycles 12/12, fused polycyclics 10/10,
bridged bicyclics 6/6, organosilicon 5/5, organoboron 5/5.

Where it fails, and these are not exotic:

```
chloroform            -> dichloromethane          (lost a chlorine)
carbon tetrachloride  -> trichloromethane         (lost a chlorine)
acetone               -> propanal                 (wrong functional group)
urea                  -> aminomethanone
deuterated water      -> oxosilane                (invented silicon)
```

Isotopic labelling: 0/4. Stereochemistry: 0/11.

### The decisive number

PubChem already names 118 of the original 124. Splitting the score by whether
PubChem had an answer changes the conclusion entirely:

```
87/118  where PubChem ALREADY has the exact name   (no value added)
  1/6   where PubChem has nothing                  (the only reason to run a model)
```

**The model is right about one time in six on precisely the structures it
exists to handle.** Its apparent competence comes almost entirely from
molecules where a lookup was already going to succeed.

### The round-trip gate holds

Every one of the 36 `canonical-base` failures was caught by the OPSIN round
trip. No wrong name was ever marked verified. So a predicted name can be shown
safely *provided* it is gated — the risk is not that a bad name slips through,
it is that 5 of 6 novel structures get no name at all.

## Alternatives surveyed (2026-07-31)

All checked live, not from documentation.

- **NCI CACTUS** (`cactus.nci.nih.gov/.../iupac_name`) — a lookup, not a
  generator. 0/6 on structures PubChem cannot name. It does return stereo
  descriptors (9/11), but so does PubChem, so it adds no coverage. Not worth
  a provider.
- **RDKit, Open Babel, CDK, Indigo** — none has structure-to-name. RDKit's
  `rdCIPLabeler` does assign R/S correctly, which is useful for *detecting*
  stereochemistry even though it cannot name it.
- **OPSIN** — name-to-structure only. It is the verification gate, not a namer.
- **`SMILES2IUPAC-isomeric-base`** — does not exist. HuggingFace returns 401
  for absent repos (confirmed against a control), so only the weak `small`
  variant is published.
- **STOUT** — weights withdrawn, bucket deleted, repository gone, no fork
  carries them.
- **PyPI rule-based namers** — none. `nomenclature` is Linux namespace
  tooling; `chemname` converts text to element symbols as a joke.
- No newer academic model with public weights was found.

## Adding an engine

1. Produce `predictions.json`: `{"engine label": {"predictions": [...]}}`,
   in corpus order.
2. `python score.py predictions.json`
3. Add a row to the results table above, and record any input requirements —
   the Kekulé discovery cost two wasted runs and would have caused a false
   rejection.

## Naming round 4 (2026-09-18)

**187/187 and 40/40 round trip throughout; PubChem verbatim 98 -> 101 on the
regression corpus, 14 -> 16 on the used held-out set, and 9 -> 15 on the
fresh one** (`heldout2.json`, scored once, in aggregate, at the end). On the
rows with a settled Blue Book target the engine now gives the preferred name
28/30 and 14/16 times; PubChem's string does 15/30 and 5/16. The per-stage
table is in `src/openchem/vendor/BENCHMARK_HISTORY.md`.

`tools/naming_stage_artifact.py` now prints that second agreement itself:
each population's engine and PubChem names against `adjudication.toml`'s
settled targets, over the rows that have one.

## Naming round 3 (2026-09-17)

**187/187 correct, 98 `exact`** on the regression corpus, from 87; **40/40**
on the held-out corpus, from 39/40. The round-trip gate never moved, which
is the point of recording the rest: it cannot see preference.

### Two corpora, because one cannot do both jobs

The regression corpus is enriched with what the engine gets wrong, which is
what makes it good at catching regressions and useless as evidence that a
fix generalises. The held-out corpus was selected by a rule stated before
any naming, by someone who had already seen the 60 disagreements -- so the
rule, not their judgement, picks the rows. **It found a wrong molecule on
its first run** (D-030, a substituted adamantane) that the regression
corpus scores 187/187 on both before and after the fix: the defect needs a
second ring substituent, and the curated corpus only ever carried
adamantane as a whole molecule.

### `exact` is measured against PubChem and PubChem is sometimes wrong

PubChem's displayed "IUPAC Name" is generated by another engine. So
`adjudication.toml` records, per disagreement, which string the Blue Book
prefers and quotes it. Examples where the reference is the non-preferred
one: `chloroform` (P-61.3.4: general nomenclature only -- and fixing the
engine LOST this row its exact match), `4-aminobenzenesulfonamide` (the
book cites the `-1-` locant whenever another substituent is present),
`methylsulfinylmethane` (P-63.6 confines alkylsulfinyl prefixes to general
nomenclature). And examples where the engine was wrong and PubChem right:
`1,4-xylene`, which P-22.1.3 names a PIN outright.

### Tools

    python tools/naming_stage_artifact.py --stage NAME --compare benchmarks/naming/stages/PREV.json
    python tools/retained_name_audit.py [--reachable]
    python benchmarks/naming/build_heldout.py        # already frozen; do not re-run to 'refresh'

The stage records need a bare `java` on PATH and refuse to write without
one, rather than recording a corpus-wide regression that is really a
missing JRE.
