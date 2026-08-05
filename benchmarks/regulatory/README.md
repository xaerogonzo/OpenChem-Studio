# Regulatory benchmark — rules, not runs

```bash
python benchmarks/regulatory/score.py
```

## Result, CWC Schedule 1, 29 structures across 4 corpora

| rule | TP | FP | FN | TN | precision | recall |
|---|---|---|---|---|---|---|
| `cwc-1-a-1` alkylphosphonofluoridates | 3 | 0 | 0 | 26 | 1.00 | 1.00 |
| `cwc-1-a-2` phosphoramidocyanidates | 1 | 0 | 0 | 28 | 1.00 | 1.00 |
| `cwc-1-a-3` aminoethyl phosphonothiolates | 1 | 0 | 0 | 28 | 1.00 | 1.00 |
| `cwc-1-a-4` sulfur mustards | 3 | 0 | 0 | 26 | 1.00 | 1.00 |
| `cwc-1-a-5` lewisites | 1 | 0 | 0 | 28 | 1.00 | 1.00 |
| **`cwc-1-a-6` nitrogen mustards** | 2 | **2** | 0 | 25 | **0.50** | 1.00 |

## The 0.50 is the point of the whole benchmark

`cwc-1-a-6` matches **chlorambucil** and **melphalan**, both licensed
cytotoxic medicines. Neither is among the HN1/HN2/HN3 the treaty entry
enumerates, so both are genuine false positives of a pattern that keys on
the bis(2-chloroethyl)amine motif.

They are recorded in `edge_cases` as expecting **no match**, so the
benchmark scores them as the failures they are rather than blessing the
current behaviour. The rule ships anyway, marked `approximate`, carrying a
limitation that says this in as many words — the alternative is to say
nothing about nitrogen mustards at all, which is worse. What is not
acceptable is shipping it while pretending precision is 1.00.

The score is **reported, not enforced**. A gate failing the build here
would push someone to delete the honest edge case rather than fix the rule.

## Why four corpora

**`positives`** alone are worthless. A rule matching every organophosphate
scores perfect recall on sarin, soman and tabun.

**`negatives`** are ordinary chemicals — aspirin, glucose, malathion,
triethyl phosphate — that must match nothing.

**`edge_cases`** carry the weight, and the sharpest is **diisopropyl
fluorophosphate**: sarin's phosphoryl, fluorine and alkoxy, no P–C bond,
not Schedule 1. Also here: a P-butyl homologue (outside the entry's
"Methyl, Ethyl, n-Propyl or Isopropyl" restriction), a C12 homologue
(outside "equal to or less than C10"), and sarin's hydrolysis product
(no fluorine, so outside the entry despite being a famous marker).

**`historical`** is reserved for structures whose status *changed*, the
only way to test that effective-date resolution works. Empty until a
superseding ruleset ships, and documented as such rather than omitted.
