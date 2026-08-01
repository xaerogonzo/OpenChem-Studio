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
| `corpus.json` | 165 molecules, 19 categories, ground truth from PubChem. Committed. |
| `build_corpus.py` | Regenerates `corpus.json`. `--append` adds only molecules not already present, so existing rows are never re-fetched. |
| `score.py` | Scores a predictions file and classifies every failure. |
| `predictions_full.json` | Raw output of the three models evaluated so far. Recorded against the original **124-row** corpus; see *Corpus revisions*. |

## Corpus revisions

The corpus started at 124 molecules and was extended to 165 in August 2026
with four categories of charged species — `carbocation`, `carbanion`,
`onium_ion`, `polycharged`.

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
truncate and report a model's 88/124 as "88/165".

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

On the extended 165-row corpus the deterministic engine scores **158/165
(96%)**, against **148/165 (90%)** for the same engine as originally vendored
— the difference being the charged-species defects fixed since. The ML models
have not been rerun; re-running them needs torch and the weights.

### The deterministic engine wins on every axis

[`leehiufung911/open-iupac-namer`](https://github.com/leehiufung911/open-iupac-namer)
(MIT, ~63k lines, from-scratch 2013 Blue Book implementation) beats the ML
option by 26 points while depending on nothing the app does not already have,
running 16x faster, and — the part no model managed — handling stereochemistry
perfectly. It also independently arrived at OPSIN round-tripping as its own
correctness check, which is what this benchmark scores on.

Two of its four failures are not wrong molecules. Adding full InChIKey as a
second gate settled which — InChI normalises mobile hydrogens, so a pair that
shares a key is the same substance depicted two ways:

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
in 124, not one. Diazomethane has since been fixed to refuse rather than
answer wrongly.

It scores 3/4 on the novel scaffolds where the ML model scored 1/6 across the
whole gap.

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
