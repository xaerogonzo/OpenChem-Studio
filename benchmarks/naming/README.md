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
| `corpus.json` | 124 molecules, 15 categories, ground truth from PubChem. Committed. |
| `build_corpus.py` | Regenerates `corpus.json`. Only needed when adding molecules. |
| `score.py` | Scores a predictions file and classifies every failure. |
| `predictions_full.json` | Raw output of the three models evaluated so far. |

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

| engine | correct | stereochemistry |
|---|---|---|
| `SMILES2IUPAC-canonical-base` (180 MB) | **88/124 (71%)** | 0/11 — crashes with `IndexError` |
| `SMILES2IUPAC-isomeric-small` (24 MB) | 75/124 (60%) | 5/11 correct, **3 silently flattened** |
| `SMILES2IUPAC-canonical-small` (24 MB) | 71/124 (57%) | 0/11 |

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

PubChem already names 118 of these 124. Splitting the score by whether PubChem
had an answer changes the conclusion entirely:

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
