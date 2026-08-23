# Solubility in solvents other than water

**Status: SHIPPED for 92 solvents, by lookup on both sides.** This document
was twice a record of why the feature could not be built, and both of those
verdicts were wrong. They are kept below rather than deleted, because the
route that finally worked is the one the earlier versions had ruled out.

Requested as "solubility in other substances than water, such as acetic
acid, ethanol, a non polar solvent like hexane, similar to how NMR tables
can use different solvents". The analogy turned out to be the design, not
merely a helpful comparison — `RESIDUAL_SOLVENT_PEAKS` in
`src/openchem/chem/nmr_signals.py` is a solvent-keyed table of published
values, and `src/openchem/chem/abraham.py` is the same thing one layer up.

## What is built

    log Ss = log Sw + c + e·E + s·S + a·A + b·B + v·V

`src/openchem/chem/abraham.py` resolves both halves by lookup:

| half | source | size |
| --- | --- | --- |
| solvent coefficients `c e s a b v` | Bradley, Abraham & Acree, BMC Chemistry 2015, [10.1186/s13065-015-0085-4](https://doi.org/10.1186/s13065-015-0085-4), Table 1 | **91 measured** solvents |
| solute descriptors `E S A B V` | Bradley, Acree & Lang, figshare 2014, [10.6084/m9.figshare.1176994](https://doi.org/10.6084/m9.figshare.1176994) | **2193 compounds** |

Both are CC BY 4.0, both are fetched by `tools/build_abraham_tables.py`
rather than typed, and both shipped JSON files carry their attribution
string so provenance cannot be lost to a refactor.

Ethanol, hexane, methanol, 1-octanol, toluene, acetone, DMSO and 84 others
are answerable. **Acetic acid is not**, and that is deliberate — see below.

`mcgowan_volume()` is still shipped as its own descriptor row and is still
exact, but it is no longer load-bearing here: `V` comes from the same
measured table as the other four.

## The three reasons this was deferred, and what was wrong with each

**`E` is derivable from Crippen molar refractivity — FALSE, and measured.**
The relation `MR/10 − 2.83195·Vx + 0.52553` returns **0.805** for hexane,
whose `E` is **0.000 by definition** — hexane *is* the n-alkane reference
that `E` is an excess over, and molar refractivity does not carry that
reference. Water returns 0.413 against 0.000.
`test_the_textbook_excess_molar_refraction_relation_does_not_work_here`
pins it so the claim cannot drift back.

**Ethanol is unreachable because it is miscible with water — FALSE.** No
two-phase partition coefficient exists for a miscible pair, and the UFZ
LSER database omits ethanol for exactly that reason, which is what made
this look like a structural impossibility rather than a gap in one
database. Abraham's coefficients for these solvents are derived from
**solubility ratios**, not from a measured partition, so neat ethanol is
in the measured table and the equation is valid for it.

**`S`, `A` and `B` need the Platts fragment scheme — TRUE, and no longer
binding.** Platts, Butina, Abraham & Hersey 1999
([10.1021/ci980339t](https://doi.org/10.1021/ci980339t)) is in hand and
would work: Table 2 gives all 81 fragment definitions, Table 4 their
coefficients, Table 5 a separate 51-fragment set for H-bond acidity.
It is also roughly **480 coefficients and 132 hand-written SMARTS
patterns**, every one a place for a silent error, and fragments 59–67 are
defined in Figure 1 rather than in text so they cannot be read from the
PDF's text layer at all.

**Looking up an experimental descriptor costs none of that, and is more
accurate.** The prediction step carries 0.7–1.0 log of its own error;
a measured descriptor carries none. This is the same trade
`RESIDUAL_SOLVENT_PEAKS` already makes: published values, exact in a way
nothing predicted can be, for the subset somebody measured.

## What it costs instead: coverage, and two honest refusals

**A compound nobody has measured is refused by name.** 2193 compounds is a
lot of chemistry and is not all of it. There is no fallback to a predicted
descriptor, because a silent downgrade from measurement to estimate is the
failure this project keeps recording.

**Two literature sources that disagree are propagated, not averaged.** 432
InChIKeys appear more than once in the source and only 51 of those groups
agree exactly; the widest single-descriptor disagreement is 2.24.
Acetanilide is the case that settled the design — three rows give
`S` = 3.61, 1.54, 1.37 and `A` = 1.908, 0.417, 0.400, and the **first** is
the outlier, so "take the first row" would have shipped it. The build takes
the median and keeps the **per-descriptor** spread; `abraham.py` propagates
that into a stated uncertainty and refuses past 1.0 log unit.

Per-descriptor rather than one blanket number, because the first version
multiplied the single widest spread by the sum of all five coefficient
magnitudes — assuming every descriptor was wrong by the worst amount at
once — and refused aspirin, caffeine and ibuprofen, three of the first four
drugs tried. A bound that rejects the ordinary case is not a safety
feature.

Aspirin in toluene is the case that still refuses, and correctly: two
sources, and toluene's coefficients turn their disagreement into more than
a factor of ten.

## Two quality gates honoured in the source data

**A `donotuse` column with a written reason** — 6 rows carry one.

**`-123` as a missing-value sentinel** — which `float()` reads as a
perfectly ordinary number, and 513 rows carry at least one. A single leak
would put a wildly negative descriptor into a prediction that still looked
like a prediction.
`test_the_missing_value_sentinel_never_reached_the_shipped_table` walks
every shipped row.

## Why acetic acid was absent, and why it is not any more

It appeared only in the paper's **predicted** coefficient set. The authors
predict coefficients for 202 further solvents and say of those "not as
gospel"; only the measured ones ship. Offering acetic acid would have meant
shipping a number its own authors decline to stand behind — the same call
already made against Miller polarizability, HLB and TSEI.

**It ships now, from a different paper.** Stovall, Schmidt, Dai, Zhang,
Acree & Abraham, *J. Mol. Liq.* **212** (2015) 16–22
([source:stovall2015]), Eq. (6), measured it over 68 compounds:

    log P = 0.175 + 0.174 E − 0.454 S − 1.073 A − 2.789 B + 3.725 V
    N = 68, SD = 0.182, R² = 0.980

That answers both recorded objections. It has the intercept the `c = 0`
refit lacks, and propagating its printed standard errors the way the
refusal was decided gives aspirin 0.55, ibuprofen 0.47 and benzene 0.19
against the ceiling of 1.0 — where the predicted set gave 1.57, 1.34 and
0.51.

**THE STANDARD DID NOT MOVE; THE LITERATURE DID.** This is the fifth time
in this project that a deferral's *reason* rotted while its verdict looked
settled, and the other 117 predicted-only names are refused on exactly the
grounds acetic acid was.

**It does not make every drug answerable in acetic acid.** Caffeine is
still refused — in acetic acid and equally in ethanol, toluene and hexane
— because its own descriptors come from two literature sources that
disagree. That bound is about the solute and predates this entirely.

## The error budget

The lookup route removes the descriptor-prediction term entirely, so what
remains is the aqueous baseline plus the solvation equation's own fit:

    ESOL on the SC-2 tight set          RMSE 1.26 log
    interlaboratory noise floor         0.17 log

The non-aqueous answer is the aqueous prediction moved by a measured
shift, so **its error is dominated by ESOL**, not by the shift. That is
stated on every non-aqueous fact: *"The AQUEOUS baseline is still a
prediction, so its error carries through."*

## What is deliberately still water-only

pH, the ICH M9 BCS screen, and the solubility-versus-pH curve.
Henderson–Hasselbalch, the pKa values behind it and the regulatory window
are all defined on aqueous media. A non-aqueous solvent gets an intrinsic
solubility and no pH story at all, rather than a curve that would look
authoritative and mean nothing. A pH-labelled row carrying an ethanol
number would be an aqueous answer's clothes on a non-aqueous one.

## The alternative that was considered and not taken

**Hansen solubility parameters** (δD, δP, δH) are computable from group
contributions today, with published tables for common solvents. They give
a *relative* miscibility ranking via the Hansen distance Ra.

Not shipped, because it answers a different question. Ra is an affinity
score, not a solubility, and putting it beside a logS in mg/mL would invite
exactly the units-and-meaning confusion the solubility module spends its
docstring preventing. If it ships it should ship under its own name, as
solvent compatibility, and never as "solubility in ethanol".

## What would extend this

1. **Coverage of the solute table.** A validated Platts implementation
   would answer for compounds nobody has measured — but it must be
   presented as an estimate distinct from a lookup, never merged into the
   same number.
2. **Benchmark each solvent separately.** A model that works for ethanol is
   not thereby a model that works for hexane, and no non-aqueous benchmark
   corpus exists here yet. The accuracy claim above is inherited from the
   aqueous baseline and the sources' own reported fits, not measured on
   this application's output.
3. **The predicted-coefficient set**, if it is ever wanted, must be marked
   as such at every point it is displayed.
