# The Within-Assay Docking Ranking Benchmark

**A dated record of one measurement, not a live claim.** Measured
2026-09-05/07 against ChEMBL_37 with AutoDock Vina 1.2.7 at exhaustiveness
25. The raw per-replicate JSONL under `benchmarks/docking/results/` is
gitignored, so **the per-series table below is the only committed form of an
18.8-hour run** and must not be regenerated from a later corpus without
saying so.

    4998 real Vina searches   833 ligands   77 single-assay series
    12 receptors              6 replicates each
    18.8 h of search time     mean 13.5 s, median 11.3 s, max 67.3 s

**WIDENED BY TARGET ON 2026-09-07, and the frozen 56 are a nested control
rather than history.** The first endpoint was 56 series on 8 receptors, five
of them aminergic GPCRs sharing an orthosteric site. Four structurally
distinct folds were added -- flavoenzyme, nuclear receptor, serine hydrolase
and ER chaperone -- costing 1170 searches and 4.2 h. Every one of the
original 56 survives unchanged: `benchmarks/docking/widening_diff.json`
records `REMOVED 0` and zero content drift, and a new JOIN row cannot reach
another row's candidates, so the superset holds by construction rather than
by promise.

## What it measures, and what it is not

Compounds measured in **one ChEMBL assay** — one endpoint, one laboratory —
ranked by the score this application generates for its own docked poses,
against their measured potency.

**NOT COMPARABLE TO CASF.** [source:su2019]'s ~0.6 and [source:nguyen2020]'s
0.498 +- 0.026 are pooled cross-target quantities on a different question.
These numbers do not belong in the same table, and the report prints that
line itself so nobody later writes "OpenChem achieves X CASF ranking power".

rho is **rho(-score, pChEMBL)**: the score is negated *before* the statistic,
so **higher means better agreement** in every column. Vinardo **rescores the
identical Vina-generated poses** — this is not Vinardo docking, which is a
different experiment.

## The headline: it is a null

| | 77 series (current) | 56 series (first endpoint) |
| --- | --- | --- |
| median rho(-vina, pChEMBL) | **+0.046**, 95% **[-0.027, +0.122]** | +0.082, 95% [-0.030, +0.245] |
| series with rho > 0 | 43/77, **p = 0.362** two-sided | 32/56, p = 0.350 |
| median rho(Vinardo) - rho(Vina) | **+0.000**, 95% [-0.053, +0.073] | +0.000, 95% [-0.104, +0.082] |
| series where Vinardo ranks higher | 38/77 | 27/56 |
| series beating every trivial baseline | **13/77** | 9/56 |
| series with rho above **twice** its own random floor | **1/77** | 1/56 |
| series with abs(rho) above its own random floor | 29/77 | 22/56 |
| range of rho across series | -0.93 to +0.79 | -0.60 to +0.79 |

**Widening did not change the answer; it slightly weakened it.** The interval
still spans zero and the sign test is still far from significance, on 37% more
series and 50% more receptors.

## THE QUESTION THE WIDENING ASKED, AND IT ANSWERED THE OPPOSITE WAY

The corpus was widened to separate **"docking cannot rank"** from **"docking
cannot rank in shallow aminergic GPCR pockets"**. The second is refuted, and
not in the direction expected:

| group | n | median rho | rho > 0 |
| --- | ---: | ---: | ---: |
| aminergic GPCR only | 32 | **+0.205** | 21/32 |
| everything NOT an aminergic GPCR | 45 | **-0.010** | 21/45 |

The aminergic GPCRs are where this method does *relatively best*. The four
added folds are flat.

**AND THE OBVIOUS CONFOUND DOES NOT EXPLAIN IT**, which is the only reason
the split is worth printing at all -- the added series are smaller by
construction, so a group difference could be an instrument difference:

    group              n   med ligands   med span   med floor
    aminergic GPCR    32            12       1.94      0.302
    everything else   45            12       1.95      0.302

Identical on all three. So it is not series size, potency span or random
floor.

**IT IS STILL POST HOC AND MUST NOT BE READ AS A RESULT OF THIS RUN.** The
pre-registered quantity was the aggregate; this split compares groups chosen
after the data was seen, over twelve targets where some will look extreme by
chance. It is a hypothesis for a future pre-registered test. Two of the new
targets are also thin -- ER alpha rests on **3** series and
acetylcholinesterase on **2** -- so their medians carry almost nothing, and
nothing here may be rendered as `0/4 new targets showed ranking`.

## Per target, and per structural class

Series are nested in targets, nested in class. This is a **class
diversification experiment, not twelve independent observations.**

| PDB | class | n | median rho | rho > 0 |
| --- | --- | ---: | ---: | ---: |
| 5C1M | aminergic GPCR (mu-opioid) | 7 | +0.270 | 6/7 |
| 6WGT | aminergic GPCR (5-HT2A) | 8 | -0.100 | 3/8 |
| 3PBL | aminergic GPCR (D3) | 8 | +0.280 | 6/8 |
| 2RH1 | aminergic GPCR (beta2) | 1 | +0.250 | 1/1 |
| 5TGZ | aminergic GPCR (CB1) | 8 | +0.210 | 5/8 |
| 3EML | other GPCR (adenosine A2A) | 8 | -0.035 | 2/8 |
| 5I6X | transporter (SERT) | 8 | -0.035 | 3/8 |
| 3HS4 | metalloenzyme (carbonic anhydrase II) | 8 | +0.205 | 5/8 |
| 2V5Z | **NEW** flavoenzyme (MAO-B) | 8 | +0.035 | 4/8 |
| 1ERE | **NEW** nuclear receptor (ER alpha) | 3 | -0.260 | 0/3 |
| 4EY7 | **NEW** serine hydrolase (AChE) | 2 | -0.045 | 1/2 |
| 5HK1 | **NEW** chaperone (sigma-1) | 8 | +0.035 | 6/8 |

    the FROZEN eight targets   56 series   median +0.075   31/56
    the NEW four               21 series   median +0.010   11/21

## TWO ENZYME CLASSES ARE ABSENT BECAUSE OF THE ENDPOINT

`PRIMARY_ENDPOINT` is Ki, and screening candidates **before** freezing them
found two obvious ones cannot form even one series of `MIN_SERIES` = 5:

    1HSG  HIV-1 protease   SIFTS gives P03367, the Gag-Pol polyprotein,
                           whose ChEMBL target carries Ki = 4   (IC50 = 77)
    5KIR  COX-2            Ki = 27                              (IC50 = 6116)

So the aspartic-protease and eicosanoid-enzyme classes are missing **because
of the endpoint stratum, not because they were not wanted**. The corpus
builder's own header already recorded the COX-2 case; the protease case is
sharper, because 1HSG is the textbook docking system and SIFTS maps it to the
polyprotein rather than the mature enzyme.

**They were NOT switched to IC50 to rescue them.** An IC50 series is
admissible and reported separately -- within one assay an IC50 ordering is
valid while a Ki and an IC50 are not one quantity -- but opening that stratum
now, for two targets, after seeing that Ki excludes them, would be choosing a
rule to admit a case.

**N5, N2 and N1 all land** — three of the five nulls `docs/ROADMAP.md`
pre-registered as shipping outcomes.

## The repeatability column is the entire result

| | |
| --- | --- |
| search repeatability, median | **+0.990** |
| series at or above +0.95 | **55 / 56** |
| ligand pairs reordered between independent replicate halves | **60 of 3462 — 1.7%** |

Replicates 1-3 and 4-6 are aggregated separately — a split fixed **before**
the run, never chosen after seeing results — and their two orderings compared.

**Without this column the headline is "docking did not correlate", which is
equally consistent with the search being too noisy to have tried.** With it,
the search orders these ligands almost identically across independent halves,
so the disagreement with measured potency is **not sampling noise**, and no
amount of extra exhaustiveness addresses it. It is the scoring function.

That is [source:su2019]'s ranking-power finding arriving as a local
measurement instead of a citation. The column only exists because route 1
shipped replicates first; a single-run benchmark cannot produce it.

**It is a SEARCH-REPEATABILITY diagnostic and NOT a noise ceiling.** It says
how stably this stochastic protocol orders the same ligands. It says nothing
about the maximum attainable correlation with experiment, which is also
bounded by assay noise, chemical space and model misspecification.

**A high value saturates easily**, which is why the swap count sits beside it:
+1.000 over 12 well-spread ligands means "noise did not reorder twelve spread
compounds", not "the search is noiseless".

## 64 of 77 series are ordered at least as well by a descriptor

Only **9 of 56** beat every trivial physicochemical baseline — heavy-atom
count, molecular weight, cLogP and TPSA, on the drop-for-drop identical ligand
set that produced the docking number. That is **N1 at 84%**, the outcome the
roadmap calls the most valuable, because it closes a route on evidence.

This project has already shipped an endpoint that turned out to be molecular
size at r = +0.98, which is why **every baseline is computed at corpus-build
time, free, before any Vina runs**. A benchmark whose sanity floor costs 14
hours is a benchmark nobody checks the floor of.

## Vinardo buys ordering diversity, not accuracy

The delta's median is exactly **+0.000** and 27 of 56 is what a coin gives
(**N2**). The two functions disagree strongly on individual series —
`3HS4_CHEMBL2045715` goes +0.33 to +0.70, `5I6X_CHEMBL5042437` -0.07 to
-0.75, `5C1M_CHEMBL747712` -0.21 to -0.69 — so the second column reorders,
and the reordering is not an improvement.

That is the measured form of the rescoring axis's own rule: **nothing
re-ranks on the second column.**

## The interim p-values crossed 0.05 and came back

    15 series (the first frozen selection)   11/15   p = 0.118
    28 series (widening in flight)           19/28   p = 0.087
    37 series (widening in flight)           25/37   p = 0.047   <-- crossed
    56 series (the PRE-COMMITTED ENDPOINT)   32/56   p = 0.350

Every row is the same statistic, computed correctly, on more data. **At 37
series this benchmark said "significant" about a dataset whose completed form
says nothing of the kind**, and it said so because the report was run three
times mid-flight to answer "how is it going".

Nothing in the arithmetic was wrong at any step. **The inspection schedule
was.** `rank_report.py` prints a PARTIAL banner whenever its complete-series
count is short of the frozen selection, because the script cannot know who is
running it or for the how-many-th time, and the interim value that happens to
sit across a conventional threshold is exactly the one that gets quoted.

## Widening, and why the two groups are not comparable

The first frozen selection was 15 series and returned **+0.245, 95%
[-0.030, +0.398]** — a hair from excluding zero, the shape most likely to be
written up as "suggestive". It was widened to 56 at 3.5x the compute.

**That is a legitimate move and a p-hacking move, and the only thing
separating them is what was committed before the data arrived.** The
manifest's `widening_note` records the pre-commitment — report the full set
whatever it says, with the first fifteen beside it — and the widened set is a
**strict superset**: the walk sorts by `(-n_ligands, series_id)`, so no
measured series was re-selected or dropped.

    first selection      median rho +0.245  (n = 15)  95% [-0.030, +0.398]
                         ligands/series 13, span 2.26, floor SD 0.289
    added by widening    median rho +0.006  (n = 41)  95% [-0.071, +0.200]
                         ligands/series 12, span 1.95, floor SD 0.302

**The two are NOT exchangeable.** The walk takes the largest series first, so
the added ones are smaller and lower-span by construction — noisier
instruments with a higher random floor. A lower median among them is partly an
artefact of that, not necessarily a weaker effect.

**And the added group's own median drifted as it filled**: +0.073 at 13 added,
+0.182 at 22, +0.006 at 41. A mid-run reading would have supported "widening
shows the effect is weaker", then "the two are converging", then the opposite
again. The split is printed anyway — with the caveat attached — because it is
the only way to see whether widening changed the answer or merely sharpened
it.

**It changed it.** +0.245 with an interval that almost excluded zero became
+0.082 with one that comfortably includes it. That is what widening after a
marginal result is for.

## What this does not say

**Not "docking cannot rank".** Two series reach rho = +0.79
(`5I6X_CHEMBL1645847`) and +0.75 (`5I6X_CHEMBL808864`), and 22 of 56 exceed
their own random floor in absolute value — 29 of 77 now, about what that
many draws from a null would give. The claim is **no ranking ability
detectable across within-assay congeneric series at this n**, on **twelve
targets spanning six structural classes**, with Vina at exhaustiveness 25,
rescored by Vinardo.

**The oracle's own reproducibility is unmeasurable here.** ChEMBL carries no
per-row uncertainty, so rho is bounded above by a quantity nobody can measure,
while the docking's own repeatability *is* measured and is essentially 1. That
asymmetry is in `docs/SCIENTIFIC_LIMITATIONS.md`.

**The leakage bound is CLOSED, and the null survives it.** Every compound in
the corpus has now been looked up; `NOT_LOOKED_UP` is empty, so the arms are a
real split rather than something `rank_report.py` refuses to present as one.

    ABSENT      624 compound-series entries   (613 distinct compounds)
    PRESENT      14                           ( 11 distinct compounds)
    UNRESOLVED    0

    ABSENT 810   PRESENT 23   UNRESOLVED 0
    median rho, ABSENT-only subsets   +0.046   (77 series)
    median rho, full set              +0.046

**The pre-committed number is the first of those two, and it was committed
before the lookup ran** (`benchmarks/docking/README.md`, commit `e91372a`).
Dropping every compound that could conceivably have been in PDBbind moves the
median by **−0.009**, in the direction of a slightly weaker correlation. So
the null is not an artefact of training-set contamination — which is the one
thing this arm can settle, and it settles it against the more convenient
answer.

**98% of the corpus is ABSENT**, which is what makes the split lopsided rather
than balanced: 11 distinct compounds are PRESENT, far too few to compute a
PRESENT-only median worth reading, and none is reported.

**Direction, stated because it is one-way.** ABSENT is a *sufficient*
exclusion from PDBbind under exact-InChIKey identity — a **minimal** bound,
not a leakage-free claim, since protonation, tautomer, salt, stereo and
component splits all break exact identity. PRESENT implies nothing: a compound
can be in the PDB bound to a protein PDBbind never included. Protein and
ligand *similarity* leakage are not addressed at all.

## The corpus, and the twelve targets

1586 single-assay series over eight catalogued receptors from 41,073
activities, of which 795 are size-decoupled. **56 were docked — 3.5%.**

Selection rule: size-decoupled, `5 <= n <= 14`, at most 8 per target, ties by
id. **Sorted by ligand count and never by potency span** — a wide span is
easier to rank, so selecting on it would flatter every number that follows,
where the count selects for statistical power. This is a **curated benchmark,
not a random sample**, and the manifest says so.

The minimum series size is **derived, not typed**: `SEPARATION_ALPHA` is
imported from `domain/affinity_range.py` and the exact two-sided permutation
null `2/n! <= alpha` solved — n=4 gives 0.083 and is refused, **n=5 gives
0.0167**. The same alpha route 1 uses, so the two conventions cannot drift.

| PDB | UniProt | ChEMBL target | organism | match | state | box ligand |
| --- | --- | --- | --- | :-: | --- | :-: |
| 5C1M | P42866 | CHEMBL2858 | *Mus musculus* | exact | active | VF1 |
| 6WGT | P28223 | CHEMBL224 | *Homo sapiens* | exact |  | 7LD |
| 3PBL | P35462 | CHEMBL234 | *Homo sapiens* | exact | inactive | ETQ |
| 2RH1 | P07550 | CHEMBL210 | *Homo sapiens* | exact | inactive | CAU |
| 5TGZ | P21554 | CHEMBL218 | *Homo sapiens* | exact | inactive | ZDG |
| 5I6X | P31645 | CHEMBL228 | *Homo sapiens* | exact |  | 8PR |
| 3HS4 | P00918 | CHEMBL205 | *Homo sapiens* | exact |  | AZM |
| 3EML | P29274 | CHEMBL251 | *Homo sapiens* | exact | inactive | ZMA |

### The join is pinned in source; SIFTS verifies rather than resolves

A UniProt accession is not a construct. Mutations, truncations, fusions,
thermostabilisation and functional state all break "same accession implies
same target", which is why every row carries `state` and a written reason.
SIFTS and ChEMBL then run as a **verifier that fails on disagreement**, not as
a resolver. All eight verify with zero disagreements.

**Four of the eight deposits carry a second accession for their
crystallisation fusion** — T4 lysozyme (P00720) in 3PBL, 2RH1 and 3EML,
cytochrome b562 in 6WGT, flavodoxin in 5TGZ — each with ChEMBL targets of its
own. So "take the accession with the most activities" can return a
chaperone's affinity data as the receptor's, silently.

Three cases otherwise fail by returning **silence, not an error**:

- **5C1M is mouse.** P42866 is mouse mu-opioid and so is CHEMBL2858, which
  carries 727 `=` Ki values — exact-organism is what the data supports rather
  than a principle imposed on it. No ortholog fallback is implemented, rather
  than written and left unreachable.
- **4M48 is *Drosophila*** and reaches no ChEMBL target at all.
- **COX-2 has 27 Ki values**, because that endpoint is measured as IC50. A
  Ki-only rule silently refuses an enzyme class.

### Receptor preparation differs from every other docking benchmark here

    {"strip_waters": True, "strip_cofactors": False,
     "strip_ligand_codes": (entry.ligand_code,)}

`redock.py`, `rescore_power.py` and `seed_spread.py` all pass
`strip_cofactors: True`. **That flag would delete 3HS4's catalytic zinc** —
the entire binding determinant for its sulfonamide series — because
`is_stripped_residue` ends `strip_cofactors and name not in
STANDARD_RECEPTOR_RESIDUES`. What has to go is the one ligand whose
coordinates defined the box, and nothing else.

Asserted before any run: the prepared PDBQT contains **no atom** of the box
ligand, and for the metalloenzymes **still contains the metal**. A blocked
pocket compresses every score toward a constant and still yields a plausible
correlation.

### One receptor preparation per series, and per-ligand derived seeds

`VinaDockingProvider.dock` re-prepares the receptor on every call, and
receptor preparation **is not reproducible** — three preparations of 5C1M gave
three different sha256s, 80 of 3794 lines differing on polar hydrogen
rotamers. Across a ranking series that would mean two ligands scored against
two different receptor files, a confound in exactly the dimension being
measured. The receptor is prepared once and its sha recorded in every record.

Seeds are derived per `(protocol_seed, molecule_chembl_id, replicate)` by
SHA-256. Two ligands sharing a replicate seed make the values arrive as
correlated pairs and void route 1's exact calculation; the runner asserts the
seed multiset within a series has no duplicate.

## The 77 series

`ρ Vina` and `ρ Vinardo` are ρ(−score, pChEMBL) — higher is better. `eff` is
the count of **distinct** potencies, so a ρ over 14 ligands tied at four
values is driven by four points. `floor` is the SD of ρ under a random
ranking, 1/sqrt(n−1). `swaps` is ligand pairs reordered between replicate
halves. `heavy`, `MW` and `cLogP` are three of the four trivial baselines —
TPSA is the fourth and is not shown, so **do not recompute "beats every
baseline" from this table**; `rank_report.py` owns that judgement and a second
implementation of it disagreed with the shipped one the first time it was
written. `set` says whether a series was in the first frozen fifteen (`1st`), added
by the per-target widening (`wide`), or added by the 2026-09-07 TARGET
widening (`new`).

| series | target | n | eff | span | ρ Vina | ρ Vinardo | repeat | swaps | floor | heavy | MW | cLogP | set |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :-: |
| `1ERE_CHEMBL3998977` | 1ERE Homo. 2017 | 7 | 7 | 0.73 | **-0.93** | -0.89 | +0.960 | 1/21 | +0.41 | +0.20 | +0.31 | +0.52 | new |
| `1ERE_CHEMBL5732098` | 1ERE Homo. 2017 | 11 | 11 | 1.82 | **-0.09** | +0.09 | +1.000 | 0/55 | +0.32 | -0.29 | -0.05 | -0.35 | new |
| `1ERE_CHEMBL897773` | 1ERE Homo. 2007 | 6 | 6 | 2.32 | **-0.26** | -0.03 | +1.000 | 0/15 | +0.45 | +0.12 | +0.32 | +0.67 | new |
| `2RH1_CHEMBL4187604` | 2RH1 Homo. 2018 | 12 | 11 | 2.26 | **+0.25** | +0.41 | +1.000 | 0/66 | +0.30 | +0.24 | +0.25 | +0.43 | 1st |
| `2V5Z_CHEMBL1252258` | 2V5Z Homo. 2010 | 11 | 11 | 3.40 | **-0.03** | +0.12 | +1.000 | 0/55 | +0.32 | -0.14 | +0.19 | +0.24 | new |
| `2V5Z_CHEMBL1816572` | 2V5Z Homo. 2011 | 9 | 8 | 2.55 | **+0.36** | +0.41 | +1.000 | 0/36 | +0.35 | +0.26 | +0.09 | -0.08 | new |
| `2V5Z_CHEMBL3996824` | 2V5Z Homo. 2017 | 5 | 5 | 1.32 | **-0.80** | -0.80 | +1.000 | 0/10 | +0.50 | +0.00 | +0.21 | +0.21 | new |
| `2V5Z_CHEMBL4183458` | 2V5Z Homo. 2018 | 5 | 5 | 2.24 | **+0.10** | +0.20 | +1.000 | 0/10 | +0.50 | +0.22 | +0.60 | -0.20 | new |
| `2V5Z_CHEMBL4354288` | 2V5Z Homo. 2019 | 10 | 9 | 0.97 | **+0.12** | +0.55 | +1.000 | 0/45 | +0.33 | +0.17 | +0.06 | +0.27 | new |
| `2V5Z_CHEMBL4385039` | 2V5Z Homo. 2019 | 13 | 13 | 3.46 | **-0.24** | -0.12 | +0.960 | 4/78 | +0.29 | +0.03 | +0.07 | -0.11 | new |
| `2V5Z_CHEMBL5730690` | 2V5Z Homo. 2017 | 8 | 2 | 1.04 | **+0.41** | +0.41 | +1.000 | 0/28 | +0.38 | +0.17 | +0.00 | +0.17 | new |
| `2V5Z_CHEMBL828820` | 2V5Z Homo. 2005 | 10 | 8 | 2.01 | **-0.24** | -0.07 | +0.960 | 2/45 | +0.33 | -0.25 | -0.30 | +0.37 | new |
| `3EML_CHEMBL1117497` | 3EML Homo. 2010 | 12 | 10 | 1.64 | **-0.02** | -0.15 | +0.990 | 1/66 | +0.30 | -0.10 | -0.05 | +0.09 | wide |
| `3EML_CHEMBL1120796` | 3EML Homo. 2010 | 12 | 12 | 1.71 | **+0.31** | +0.26 | +1.000 | 0/66 | +0.30 | +0.06 | -0.03 | +0.34 | wide |
| `3EML_CHEMBL2422901` | 3EML Homo. 2013 | 12 | 12 | 3.74 | **-0.01** | -0.09 | +1.000 | 0/66 | +0.30 | +0.04 | +0.05 | -0.07 | wide |
| `3EML_CHEMBL3878179` | 3EML Homo. 2017 | 13 | 12 | 3.03 | **-0.30** | -0.12 | +1.000 | 0/78 | +0.29 | -0.27 | -0.15 | -0.35 | 1st |
| `3EML_CHEMBL4123886` | 3EML Homo. 2018 | 12 | 12 | 2.15 | **-0.08** | -0.35 | +0.960 | 3/66 | +0.30 | +0.21 | +0.20 | -0.64 | wide |
| `3EML_CHEMBL4379761` | 3EML Homo. 2020 | 14 | 12 | 0.73 | **+0.05** | +0.20 | +1.000 | 1/91 | +0.28 | -0.08 | -0.10 | -0.16 | 1st |
| `3EML_CHEMBL639492` | 3EML Homo. 2004 | 12 | 11 | 3.70 | **-0.05** | -0.23 | +0.990 | 1/66 | +0.30 | +0.12 | -0.05 | -0.87 | wide |
| `3EML_CHEMBL918671` | 3EML Homo. 2004 | 13 | 11 | 1.04 | **-0.29** | -0.00 | +0.990 | 1/78 | +0.29 | +0.07 | +0.05 | +0.07 | wide |
| `3HS4_CHEMBL1246741` | 3HS4 Homo. 2010 | 14 | 12 | 0.54 | **-0.09** | -0.58 | +1.000 | 1/91 | +0.28 | -0.05 | -0.19 | -0.37 | 1st |
| `3HS4_CHEMBL1839822` | 3HS4 Homo. 2011 | 12 | 10 | 2.04 | **+0.36** | +0.05 | +0.980 | 2/66 | +0.30 | -0.19 | -0.06 | +0.29 | wide |
| `3HS4_CHEMBL2045715` | 3HS4 Homo. 2012 | 12 | 11 | 1.84 | **+0.33** | +0.70 | +0.990 | 2/66 | +0.30 | -0.29 | -0.20 | -0.31 | wide |
| `3HS4_CHEMBL3611445` | 3HS4 Homo. 2015 | 12 | 7 | 2.34 | **+0.41** | +0.30 | +0.990 | 1/66 | +0.30 | +0.20 | +0.16 | +0.47 | wide |
| `3HS4_CHEMBL3876600` | 3HS4 Homo. 2017 | 14 | 14 | 2.33 | **+0.40** | +0.54 | +0.990 | 2/91 | +0.28 | -0.10 | -0.48 | -0.37 | 1st |
| `3HS4_CHEMBL4119794` | 3HS4 Homo. 2017 | 13 | 13 | 1.03 | **+0.08** | +0.16 | +0.990 | 1/78 | +0.29 | +0.08 | +0.27 | -0.25 | wide |
| `3HS4_CHEMBL4136600` | 3HS4 Homo. 2017 | 13 | 13 | 3.70 | **-0.03** | +0.08 | +0.990 | 1/78 | +0.29 | -0.20 | -0.15 | +0.04 | wide |
| `3HS4_CHEMBL4615999` | 3HS4 Homo. 2020 | 13 | 11 | 1.95 | **-0.12** | -0.46 | +1.000 | 0/78 | +0.29 | -0.04 | -0.08 | -0.01 | wide |
| `3PBL_CHEMBL1225697` | 3PBL Homo. 2010 | 13 | 10 | 2.70 | **-0.03** | -0.13 | +0.980 | 2/78 | +0.29 | +0.23 | +0.17 | +0.42 | 1st |
| `3PBL_CHEMBL3239710` | 3PBL Homo. 2014 | 13 | 13 | 2.63 | **+0.42** | +0.51 | +1.000 | 0/78 | +0.29 | -0.21 | +0.05 | +0.38 | 1st |
| `3PBL_CHEMBL669161` | 3PBL Homo. 1999 | 10 | 10 | 2.59 | **+0.45** | +0.24 | +0.990 | 1/45 | +0.33 | +0.02 | +0.13 | +0.35 | wide |
| `3PBL_CHEMBL674832` | 3PBL Homo. 1999 | 11 | 11 | 1.92 | **+0.18** | +0.16 | +1.000 | 0/55 | +0.32 | +0.25 | +0.36 | -0.16 | wide |
| `3PBL_CHEMBL675054` | 3PBL Homo. 1999 | 11 | 11 | 1.60 | **+0.25** | +0.08 | +1.000 | 0/55 | +0.32 | +0.05 | +0.32 | +0.12 | wide |
| `3PBL_CHEMBL861437` | 3PBL Homo. 2006 | 12 | 12 | 2.99 | **+0.31** | +0.27 | +0.990 | 2/66 | +0.30 | -0.08 | +0.12 | +0.37 | wide |
| `3PBL_CHEMBL872893` | 3PBL Homo. 2002 | 13 | 13 | 4.16 | **+0.34** | +0.24 | +0.990 | 1/78 | +0.29 | +0.28 | +0.14 | +0.12 | wide |
| `3PBL_CHEMBL879553` | 3PBL Homo. 2000 | 10 | 9 | 3.39 | **-0.09** | -0.02 | +1.000 | 0/45 | +0.33 | -0.06 | -0.09 | -0.10 | wide |
| `4EY7_CHEMBL1227597` | 4EY7 Homo. 2010 | 7 | 7 | 0.51 | **-0.39** | -0.71 | +1.000 | 0/21 | +0.41 | -0.29 | -0.14 | +0.00 | new |
| `4EY7_CHEMBL3887379` | 4EY7 Homo. 2015 | 5 | 5 | 1.87 | **+0.30** | +0.30 | +1.000 | 0/10 | +0.50 | +0.15 | +0.15 | +0.67 | new |
| `5C1M_CHEMBL1274304` | 5C1M Mus. 2010 | 9 | 8 | 2.42 | **+0.27** | +0.38 | +0.980 | 1/36 | +0.35 | -0.21 | -0.25 | -0.53 | 1st |
| `5C1M_CHEMBL3385150` | 5C1M Mus. 2014 | 11 | 10 | 1.11 | **+0.38** | +0.24 | +1.000 | 0/55 | +0.32 | -0.14 | -0.10 | -0.63 | 1st |
| `5C1M_CHEMBL4035921` | 5C1M Mus. 2017 | 6 | 6 | 1.14 | **+0.09** | +0.37 | +1.000 | 0/15 | +0.45 | -0.23 | -0.37 | -0.14 | wide |
| `5C1M_CHEMBL747712` | 5C1M Mus. 1997 | 8 | 8 | 1.57 | **-0.21** | -0.69 | +1.000 | 0/28 | +0.38 | +0.01 | +0.00 | +0.31 | wide |
| `5C1M_CHEMBL757171` | 5C1M Mus. 1989 | 8 | 8 | 3.98 | **+0.43** | +0.57 | +0.980 | 1/28 | +0.38 | +0.20 | +0.12 | +0.21 | wide |
| `5C1M_CHEMBL758126` | 5C1M Mus. 1995 | 6 | 6 | 1.99 | **+0.20** | +0.09 | +0.990 | 0/15 | +0.45 | n/a | n/a | n/a | wide |
| `5C1M_CHEMBL759359` | 5C1M Mus. 1997 | 5 | 5 | 0.97 | **+0.60** | -0.20 | +1.000 | 0/10 | +0.50 | +0.10 | +0.10 | +0.10 | wide |
| `5HK1_CHEMBL4369944` | 5HK1 Homo. 2019 | 8 | 8 | 1.03 | **+0.40** | +0.26 | +1.000 | 0/28 | +0.38 | -0.16 | +0.00 | -0.21 | new |
| `5HK1_CHEMBL4622425` | 5HK1 Homo. 2020 | 8 | 8 | 1.71 | **-0.02** | -0.48 | +1.000 | 0/28 | +0.38 | +0.08 | +0.12 | -0.24 | new |
| `5HK1_CHEMBL6088796` | 5HK1 Homo. 2025 | 12 | 12 | 2.70 | **+0.05** | -0.26 | +0.990 | 1/66 | +0.30 | +0.09 | +0.17 | +0.32 | new |
| `5HK1_CHEMBL803932` | 5HK1 Homo. 1993 | 13 | 13 | 3.38 | **+0.02** | -0.02 | +1.000 | 0/78 | +0.29 | +0.19 | +0.08 | -0.09 | new |
| `5HK1_CHEMBL805786` | 5HK1 Homo. 1998 | 12 | 12 | 1.87 | **+0.43** | +0.24 | +0.990 | 1/66 | +0.30 | +0.03 | +0.01 | -0.00 | new |
| `5HK1_CHEMBL848647` | 5HK1 Homo. 1993 | 13 | 12 | 1.12 | **+0.01** | +0.04 | +0.910 | 7/78 | +0.29 | +0.27 | +0.21 | +0.18 | new |
| `5HK1_CHEMBL872703` | 5HK1 Homo. 1995 | 10 | 9 | 2.12 | **-0.55** | -0.54 | +0.990 | 1/45 | +0.33 | -0.23 | -0.64 | -0.30 | new |
| `5HK1_CHEMBL880938` | 5HK1 Homo. 1995 | 12 | 12 | 2.77 | **+0.07** | +0.06 | +1.000 | 0/66 | +0.30 | +0.29 | +0.55 | +0.23 | new |
| `5I6X_CHEMBL1041759` | 5I6X Homo. 2009 | 12 | 11 | 0.87 | **-0.23** | -0.07 | +0.990 | 1/66 | +0.30 | -0.00 | +0.19 | +0.18 | wide |
| `5I6X_CHEMBL1645847` | 5I6X Homo. 2011 | 7 | 7 | 1.54 | **+0.79** | -0.18 | +0.960 | 1/21 | +0.41 | -0.13 | +0.14 | +0.14 | wide |
| `5I6X_CHEMBL3871875` | 5I6X Homo. 2017 | 7 | 7 | 3.40 | **+0.11** | -0.11 | +1.000 | 0/21 | +0.41 | -0.26 | -0.14 | -0.57 | wide |
| `5I6X_CHEMBL5042437` | 5I6X Homo. 2022 | 7 | 7 | 1.35 | **-0.07** | -0.75 | +1.000 | 0/21 | +0.41 | +0.19 | +0.25 | -0.04 | wide |
| `5I6X_CHEMBL808864` | 5I6X Homo. 2003 | 13 | 12 | 1.40 | **+0.75** | +0.78 | +0.990 | 1/78 | +0.29 | +0.05 | -0.32 | -0.12 | 1st |
| `5I6X_CHEMBL839605` | 5I6X Homo. 2005 | 14 | 13 | 3.44 | **+0.00** | -0.48 | +0.980 | 3/91 | +0.28 | -0.24 | +0.04 | -0.41 | 1st |
| `5I6X_CHEMBL867297` | 5I6X Homo. 2006 | 8 | 8 | 2.94 | **-0.40** | -0.40 | +1.000 | 0/28 | +0.38 | +0.29 | +0.14 | +0.45 | wide |
| `5I6X_CHEMBL893351` | 5I6X Homo. 2007 | 13 | 13 | 4.08 | **-0.13** | -0.09 | +0.990 | 1/78 | +0.29 | -0.05 | +0.40 | -0.06 | wide |
| `5TGZ_CHEMBL1041035` | 5TGZ Homo. 2009 | 13 | 13 | 1.91 | **+0.21** | +0.31 | +1.000 | 0/78 | +0.29 | +0.04 | +0.21 | +0.28 | 1st |
| `5TGZ_CHEMBL1071213` | 5TGZ Homo. 2010 | 11 | 9 | 1.25 | **-0.14** | +0.18 | +0.980 | 2/55 | +0.32 | +0.14 | +0.15 | +0.24 | wide |
| `5TGZ_CHEMBL2025416` | 5TGZ Homo. 2012 | 13 | 13 | 2.07 | **+0.21** | -0.35 | +0.790 | 11/78 | +0.29 | +0.03 | +0.37 | -0.32 | wide |
| `5TGZ_CHEMBL2383562` | 5TGZ Homo. 2013 | 13 | 13 | 1.44 | **+0.31** | +0.01 | +0.980 | 3/78 | +0.29 | +0.25 | +0.32 | +0.36 | wide |
| `5TGZ_CHEMBL3873271` | 5TGZ Homo. 2016 | 12 | 10 | 1.07 | **+0.43** | +0.68 | +1.000 | 0/66 | +0.30 | -0.04 | +0.19 | +0.59 | wide |
| `5TGZ_CHEMBL4186781` | 5TGZ Homo. 2018 | 14 | 14 | 1.91 | **+0.49** | +0.27 | +1.000 | 0/91 | +0.28 | +0.18 | +0.15 | +0.51 | 1st |
| `5TGZ_CHEMBL941882` | 5TGZ Homo. 2007 | 13 | 12 | 4.49 | **-0.15** | +0.21 | +0.990 | 2/78 | +0.29 | -0.14 | -0.09 | +0.75 | wide |
| `5TGZ_CHEMBL963331` | 5TGZ Homo. 2009 | 13 | 13 | 2.44 | **-0.37** | -0.17 | +0.980 | 2/78 | +0.29 | +0.18 | -0.67 | +0.10 | wide |
| `6WGT_CHEMBL4366765` | 6WGT Homo. 2019 | 12 | 10 | 1.95 | **-0.04** | -0.26 | +0.990 | 1/66 | +0.30 | -0.12 | +0.25 | +0.14 | wide |
| `6WGT_CHEMBL4628379` | 6WGT Homo. 2020 | 11 | 11 | 1.09 | **+0.07** | +0.25 | +1.000 | 0/55 | +0.32 | -0.21 | -0.30 | -0.08 | wide |
| `6WGT_CHEMBL616895` | 6WGT Homo. 2001 | 14 | 13 | 3.88 | **+0.38** | +0.33 | +0.990 | 2/91 | +0.28 | +0.18 | +0.12 | +0.35 | 1st |
| `6WGT_CHEMBL617520` | 6WGT Homo. 2002 | 10 | 10 | 1.33 | **+0.01** | +0.08 | +1.000 | 0/45 | +0.33 | +0.29 | +0.71 | +0.70 | wide |
| `6WGT_CHEMBL617522` | 6WGT Homo. 2002 | 12 | 11 | 2.01 | **-0.22** | +0.05 | +0.990 | 1/66 | +0.30 | -0.06 | +0.23 | +0.35 | wide |
| `6WGT_CHEMBL854094` | 6WGT Homo. 2006 | 13 | 12 | 1.77 | **-0.18** | -0.13 | +1.000 | 0/78 | +0.29 | -0.26 | -0.22 | -0.29 | 1st |
| `6WGT_CHEMBL882471` | 6WGT Homo. 2005 | 12 | 12 | 1.90 | **-0.16** | -0.01 | +0.950 | 4/66 | +0.30 | -0.08 | -0.05 | +0.47 | wide |
| `6WGT_CHEMBL936730` | 6WGT Homo. 2008 | 10 | 10 | 1.60 | **-0.60** | -0.19 | +1.000 | 0/45 | +0.33 | -0.15 | +0.12 | -0.28 | wide |


## Reproducing it

`git diff src/` is empty for the branch that produced this — the benchmark
changes no application code.

```bash
uv run --no-sync python benchmarks/docking/chembl_corpus.py          # network, minutes
uv run --no-sync python benchmarks/docking/chembl_corpus.py --presence-only
uv run --no-sync python benchmarks/docking/rank_power.py             # 14.5 h, real Vina
uv run --no-sync python benchmarks/docking/rank_report.py            # seconds
```

Stage 1 appends one JSONL record per replicate, opened and flushed per record,
and is **resumable** — it skips triples already present. Stage 2 needs no
network and no Vina, reports only **complete** series, and refuses a corpus
whose `schema_version` or `chembl_release` differs from what the JSONL
recorded.

`rank_power.py` is cache-only by default. A measurement that depends on RCSB
being up is not a measurement; `--allow-fetch` is the opt-in.

## What it closes, and what it leaves open

**Route 2's acceptance criterion is measured** rather than unmeasurable. The
2026-09-03 survey that declared it unmeasurable was right about every route it
examined — PDBbind, CASF-2016's tarball, PDBbind+, Binding MOAD,
`rcsb_binding_affinity` — and wrong about the one it did not, ChEMBL's
`assay_chembl_id`. It is kept in `docs/ROADMAP.md` with its correction beside
it, because the way it was wrong is the durable part: it enumerated the closed
doors carefully and read that as a closed question.

**Route 3 (RBFE) has its oracle.** It was to be justified by docking's ranking
being inadequate; that is now measured as inadequate rather than assumed, and
**the same corpus is what a free-energy method would have to beat**. The
benchmark outlives the null it produced.

**The presence lookup is DONE** — it was the cheapest item on this list and
is the section above.

Open, in cost order, and the range is **four orders of magnitude**, so this
list is priced rather than merely ordered:

| | cost | what it buys |
| --- | --- | --- |
| **smina** ([source:koes2013]) | obtainable; then a pose-retaining re-dock | the only candidate that is BOTH engine and rescorer, so it is the arm that tests whether `PoseRescorer` is a real abstraction or a Vina-shaped hole. **It is NOT an independent second opinion** -- it is Vina-derived, and DSX, which was, is unobtainable (both spikes run 2026-09-07; see `docs/ROADMAP.md`) |
| **more targets** | curation, not compute | eight is family spread, not data volume, and seven of the eight are GPCRs or a single enzyme |
| **more series** | ~14.5 h per 56 | 1586 exist and 56 were docked; needs no new machinery and costs proportionally. All 1586 is ≈ **17 days** continuous |
| **RBFE, one series** | **2.3–5.5 GPU-days** | one ΔΔG ladder over one series, against a measured docking baseline |
| **RBFE, this corpus** | **121–291 GPU-days** | refused on cost — see `docs/ROADMAP.md` |

**smina is nearly free in the harness and nobody had noticed.**
`rank_power.py`'s `run_series` already takes `(provider, engine, rescorer)` as
parameters, so a second engine slots in at the constructor site, and
`_rescore_best` already goes through the shipped `PoseRescorer` interface with
a comment anticipating a rescorer from another family. The unknown is entirely
whether smina builds and runs on Windows, which is a spike and not a claim.

**More targets buys more than more series does.** Widening series adds
statistical power to a question already answered at p = 0.350; widening
targets is the only item here that addresses the stated narrowness of the
claim, since the corpus is six GPCRs, one carbonic anhydrase and one
transporter. `JOIN` in `chembl_corpus.py` is eight pinned rows each carrying a
written reason and a SIFTS/ChEMBL verifier, so adding one is curation plus
verification rather than compute.
