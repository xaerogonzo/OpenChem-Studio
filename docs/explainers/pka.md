# Explainers: pKa and the sequential distribution

Hand-written, merged into `docs/CALCULATOR_REFERENCE.md`. Claims here are **shipped** (what this application's code does) or **published** via [source:pkasolver]. Nothing on this page is a new accuracy measurement.

## pka

### What it does
Reports each ionisable centre pkasolver predicts, with the ensemble spread and the drawing atom when that atom can be mapped. Opening the result shows those sites on the structure. It does not enumerate microspecies.

### How it works
Shipped: pkasolver runs out of process from its own environment. Each prediction is ordered by increasing pKa (then mapped atom, then original position) and stored as a compact site record on the result so a later window can label atoms after restart. Acid versus base is read from the model's own protonated-site charge, the same rule Ionisable Sites uses. The text lines are the values, the atom on the drawing, and the spread when it is non-zero.

### What the result means
A per-site pKa from a graph model trained on measured constants [source:pkasolver], plus a spread that is how far fifty ensemble members disagreed, not a calibrated confidence interval. An unmapped site is listed without pointing at an atom.

### When to use it, when not
Use it to see which centres the model found and roughly how acidic or basic they are. Do not treat a tight spread as a guarantee (electron-poor phenols can be confidently wrong). Numeric pKa needs the pkasolver environment under External tools.

### Search for
pKa, ionisable, spread

### Sources
- [source:pkasolver] -- the model that produces the values

## pka_microspecies

### What it does
Plots the percentage of each sequential protonation species against pH from the same per-site pKa values. The dedicated pKa window can show pictures of that ladder. It is not Dimorphite's Major Microspecies calculator.

### How it works
Shipped: predicted pKa values are treated as macroscopic sequential dissociation constants. Species 0 is fully protonated; species `j` has `j` dissociations, in pKa order. Fractions come from `chem/ph_curves.py` and are not recomputed in the window. Pictures are built from the stored protonated and deprotonated site-state tuples, or omitted entirely when any step cannot be applied. More than eight ionisable sites keep the chart and table and drop pictures. A species that never reaches 0.01 % on the sampled grid keeps its series and table column and hides only its picture.

### What the result means
An approximate macroscopic reading of per-site pKa. Interacting sites, especially sites with similar pKa values, can produce a more complex real distribution. The structures are that sequential ladder, not an independent microstate set. Major Microspecies remains a separate Dimorphite calculation.

### When to use it, when not
Use it to see how the sequential model splits population with pH, and to inspect the corresponding structures when they can be built honestly. Do not use it as a complete microspecies enumeration. It needs the same pkasolver environment as pKa.

### Search for
microspecies, protonation ladder, pH distribution, sequential pKa

### Sources
- [source:pkasolver] -- the per-site values the sequential model reads
