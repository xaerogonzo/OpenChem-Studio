# Validation

Every number this application reports has a measurement behind it. This page
collects them in one place, each with the method and the sample size that
produced it, and links out to the benchmark that owns it — so there is one
source of truth per number, not a copy here that quietly goes stale.

If you only read one thing: the results that mattered most were the ones
that said *no*. Four features were built far enough to be measured and then
dropped. Those are in the last section.

---

## Naming — 181/181

**Method.** 181 molecules across 22 categories, ground truth from PubChem.
Scored by **structural round-trip**, not string equality: the predicted name
is parsed back with OPSIN and the resulting structure compared to the input.
A name that is correct but phrased differently passes; a name that is
plausible and wrong does not.

Re-run for this release against the 181-molecule corpus:

| outcome | n |
|---|---|
| `exact` — the expected name, character for character | 82 |
| `equivalent` — a different but correct name, confirmed by round-trip | 98 |
| `tautomer` — round-trips to a different tautomer of the same compound | 1 |
| **correct** | **181/181 (100%)** |
| stereochemistry | **11/11, 0 silently flattened** |

For comparison, the same engine as originally vendored scored 148/165 (90%)
on the revision that existed then.

The `tautomer` class is metformin, and it is deliberately kept visible
rather than folded into `equivalent`. It is awarded only when a canonical
tautomer match **and** an InChIKey match both agree — a deliberately strict
pair, verified not to collapse on the charge defects the gate exists for
(guanidine vs guanidinium and benzyl cation vs toluene both still fail, as
they must).

**Against the ML alternatives**, scored on the earlier 124-molecule revision
— the only one all four engines were run on:

| engine | correct | stereochemistry | dependencies | speed |
|---|---|---|---|---|
| **deterministic (shipped)** | **120/124 (97%)** | **11/11** | rdkit only | 12 ms |
| `SMILES2IUPAC-canonical-base` | 88/124 (71%) | 0/11 — crashes | torch + transformers, 1.1 GB | 190 ms |
| `SMILES2IUPAC-isomeric-small` | 75/124 (60%) | 5/11, **3 silently flattened** | torch + transformers | 97 ms |
| `SMILES2IUPAC-canonical-small` | 71/124 (57%) | 0/11 | torch + transformers | 97 ms |

Silent stereochemistry flattening is separated out deliberately: an engine
that drops a stereocentre without saying so is more dangerous than one that
fails loudly.

→ [`benchmarks/naming/`](../benchmarks/naming/)

---

## NMR shift prediction

### The HOSE-code lookup — per-band error, measured

**Method.** The index was rebuilt with every twentieth molecule excluded,
then those molecules predicted. This is a genuine novel-compound test: the
environments being matched came from other molecules entirely.

| band | n | MAE | median |
|---|---|---|---|
| `good` | 11,390 | **1.12 ppm** | 0.50 |
| `medium` | 10,933 | **3.36 ppm** | 2.31 |
| `rough` | 1,957 | **10.00 ppm** | 7.17 |
| all | **24,280** | 2.85 ppm | 1.23 |

These per-band figures are not decoration — they are what the hybrid selects
on. An atom is assigned to a band by how well its environment is
represented, and the band's measured error is that prediction's expected
error.

**Corpus-specific, and known to be.** Re-measured on DELTA50 the bands do not
transfer exactly. The constants carry the corpus they were measured on.

### The hybrid — judged on its decisions, not just its output

**Method.** DELTA50 (*Molecules* 2023, 28, 2449, CC-BY) — 46 compounds, 207
assigned ¹³C shifts, B3LYP/def2-SVP. Paired bootstrap resampled over
**molecules**, not atoms, because atoms of one molecule share a structure
and an assignment.

| strategy | MAE | selection accuracy | worst regret | vs shipped gate |
|---|---|---|---|---|
| `hard_gate` (was shipped) | 1.46 | 77.8% | 10.94 | — (refused 13/46) |
| **`warn_only`** (now shipped) | **1.33** | **80.2%** | **6.39** | −0.131 [−0.308, −0.017] |
| `per_molecule_error` | 1.34 | 74.9% | 6.39 | not distinguishable |
| `lookup_only` | 2.33 | 72.0% | 30.95 | worse |
| `orca_only` | 2.68 | 28.0% | 7.85 | worse |

**Selection accuracy and regret judge the rule rather than the predictors.**
For every atom both predictions *and* the truth are known, so it is knowable
whether the rule picked the closer source. A rule can lower MAE purely
because the calculation happened to be good while still choosing badly —
regret catches that and MAE does not.

Confirmed on 14 held-out molecules the strategies never influenced, and
repeated at wB97X-D3/def2-SVP, where the gate fires only 3 times in 42 and
removing it is *not distinguishable* rather than better — never worse.

→ [`benchmarks/nmr/`](../benchmarks/nmr/)

---

## Conformer generation — no molecule below reference

**Method.** `benchmarks/conformers/` scores "how many distinct conformers
does the app find" against an 11-molecule corpus of two deliberately
different kinds of reference: **textbook counts** (cyclohexane's chair and
twist-boat, butane's anti and gauche) that must be matched, and
**computational lower bounds** (ethylmorphine's 12) that must be met or
exceeded — exceeding a lower bound is not an error, and the scorer knows
the difference. Five seeds × 50 embeddings, seeded and strided so the
arms are genuinely independent.

Re-run for this release: **no molecule below reference.** Every textbook
case at its reference; ethylmorphine at 15.0 [10–18] against a lower
bound of 12.

**The count is not the whole validation.** The same benchmark ships a
*funnel* (`funnel.py`) that reports where candidates are lost — embedding,
minimisation, merge, cap — and a per-pair table of what was actually
discarded, because a count cannot tell under-sampling from over-merging.
Its verdict for this release: the de-duplication discards only degenerate
pairs (the largest energy difference among discarded pairs whose torsions
genuinely moved is 0.0009 kcal/mol on ibuprofen, 0.0000 on butane and
pentane — mirror-image conformers, whose merge is what *produces* the
textbook counts), and the losses live in sampling and in the keep cap,
both now visible in the app.

**A validated instrument correction rides along.** The benchmark's torsion
diagnostic was symmetry-blind — it reported a 180° torsion change between
two *identical* ibuprofen structures, and 33 of 40 discarded pairs flagged
>90° where the corrected reading is 14 — so every torsion figure above is
from the corrected metric, which reads dihedrals under the same atom
correspondence the merge decision used. `ETKDGv3`'s small-ring torsion
sampling was then enabled after an isolated full-corpus gate: ten of
eleven molecules byte-identical, ethylmorphine's five-seed union 17 → 25,
paired cost ×1.17. The gate table is in the benchmark README.

## Docking — redocking the crystallographic ligand

**Method.** Each curated receptor's own bound ligand is extracted, re-docked
into the box derived from it, and the **centroid displacement** measured.
Centroid rather than symmetry-corrected RMSD deliberately: RMSD needs an
atom correspondence this does not have, and the question being asked is
"did it find the right pocket", which a centroid answers.

**The seed is not pinned.** The app runs Vina as shipped, which means a
random seed, so two runs of the same receptor already differ. The table
below is therefore three whole runs — one before a change to which
copy of a multi-copy ligand gets boxed, two after — rather than one
column of single measurements. **The run-to-run scatter is about
0.03 Å**, and that is the scale any difference here has to be read
against.

| PDB | ligand | before | after | after | target |
|---|---|---|---|---|---|
| 1HSG | MK1 | 0.17 Å | **0.17 Å** | **0.16 Å** | indinavir / HIV-1 protease |
| 2RH1 | CAU | 0.39 Å | **0.33 Å** | **0.33 Å** | carazolol / β2-adrenergic |
| 1ERE | EST | 0.50 Å | **0.46 Å** | **0.48 Å** | estradiol / estrogen receptor α |
| 8ZYO | XB7 | 0.56 Å | **0.55 Å** | **0.52 Å** | astemizole / hERG |
| 4DKL | BF0 | 0.83 Å | **0.70 Å** | **0.71 Å** | β-FNA / μ-opioid |
| 4EY7 | E20 | 0.69 Å | **0.37 Å** | **0.39 Å** | donepezil / acetylcholinesterase |
| 3EML | ZMA | 2.59 Å | 2.54 Å | 2.48 Å | ZM241385 / adenosine A2A |

All seven land in the same pocket in every arm. 4EY7 is the one real
movement — 0.69 → 0.37 Å is twenty times the noise, and it is one of the
entries whose box moved to a more buried copy of its ligand.

The 3EML row is reported rather than hidden: a ligand can move several Å
within the same pocket and still score well, and the number is more useful
visible than tidied away. **An earlier revision of this table recorded
3.90 Å for it. That does not reproduce** — the before arm above, on
unchanged code, gives 2.59 Å. Treat the old figure as one draw from a
wide distribution rather than as something that was repaired.

**What this does not measure:** whether Vina's affinities correspond to real
binding free energies. They do not, and no redocking experiment can show
that.

→ [`benchmarks/docking/`](../benchmarks/docking/)

### The same deposit in two file formats

A receptor can be loaded as PDB or as mmCIF, and until recently those were
not the same receptor. Measured by preparing every one of the 48 curated
targets from **both** formats through the real docking preparation and
comparing the AutoDock atom-type histogram — which is what Vina scores
against:

| | receptors with an identical prepared receptor |
|---|---|
| before | **0 of 48** |
| after | **38 of 48** |

Before, aromatic carbon was typed on every PDB receptor and on *no* mmCIF
one, and the two forms of 6JP5 differed by 3,966 atoms. Three separate
causes: Open Babel reads mmCIF element symbols case-sensitively while the
archive writes them uppercase (so every two-letter element — Zn, Cl, Fe,
Se — was silently dropped); which copy of a repeated ligand got boxed
depended on chain labels that differ between the formats; and Open Babel
assigns no implicit hydrogens at all from mmCIF.

**The 10 that still differ do so only in polar hydrogens and nitrogen
typing.** No heavy atom differs anywhere in the catalogue. That residue is
a genuine Open Babel perception difference, it is *not* fixed, and **which
of the two is correct has not been established** — so a receptor loaded as
mmCIF and the same one loaded as PDB can still be protonated slightly
differently. If a result matters, note which format you loaded.

---

## Solubility — a bias that only stratification showed, replicated on a second set

**Superseded figures:** anything citing 67 scored or a −0.52 base bias
predates the polymorph fix (three compounds were scored twice); PR #28's
body still quotes those and is immutable history. See CHANGELOG.

**Method.** ESOL against the Solubility Challenge (Llinàs, Glen & Goodman
2008) and, independently, the Solubility Challenge 2 tight set (Llinàs,
Oprisiu & Avdeef 2020, Table 1). Both de-leaked by InChIKey; ampholytes
refused rather than scored.

| set | stratum | n | MAE | RMSE | bias |
| --- | --- | --- | --- | --- | --- |
| SC-1 | all | 61 | 0.74 | 0.98 | −0.17 |
| SC-1 | acid | 18 | 0.55 | 0.79 | +0.26 |
| SC-1 | base | 27 | 0.84 | 1.05 | **−0.59** |
| SC-2 | all | 73 | 0.90 | 1.26 | −0.05 |
| SC-2 | base | 17 | 0.70 | 0.87 | **−0.42** |
| SC-2 | GSE (published baseline) | 73 | 0.86 | 1.18 | +0.37 |

**The stratification earned its keep on the first run.** The aggregate bias
is −0.17 and reads as noise. Split by class, ESOL **under-predicts bases by
more than half a log unit** while acids sit at +0.26 — a systematic error
across a third of a druglike set, invisible in a single MAE.

**And it is NOT corrected, by a pre-registered decision.** A cross-corpus
held-out test (`benchmarks/solubility/base_bias.py`) fits the offset on one
corpus's bases and tests on the other's. The offsets agree (+0.586 / +0.422)
and base RMSE improves in both directions — but the bootstrap 95% CI on the
held-out improvement **includes zero both ways**, one of them by 0.0009.
Outcome `SURFACE_ONLY`: the bias is reported to the user rather than
subtracted. Removing the 7 bases the corpora share is what makes "held out"
true and what leaves the test underpowered at n=10 and n=20.

**Two further corpora were extracted to fix that, and did not.** A1
(Yalkowsky & Banerjee 1992) is **74% inside ESOL's own training set** and
contributes zero bases; A2 (Hopfinger 2009) yields 7, under the minimum to
be held out. Power here is set by the **test** side, so both can only join
the fit pool — the SC-1 arm's CI lower bound moved from −0.0009 to −0.0338,
slightly *further* from significance. Two of Avdeef's five appendix tables
turned out to be the SC-2 sets under other names, and are refused by name
rather than double-counted. The available independent data cannot settle
this question, which is itself the finding.

**And it replicated on 73 entirely different compounds** (−0.42 against
−0.59). One set makes a bias a curiosity; two make it a property of the
model. Delaney's paper mentions ionization, amines and salts *zero* times,
so this is a domain limit, not a fixable defect.

**A number without a baseline says nothing.** The General Solubility
Equation scores RMSE 1.18 on the same compounds — and needs a *measured
melting point*, which this application does not have. ESOL lands within
0.08 of it regardless, so the honest reading is that the endpoint is hard,
not that the model is poor. The set carries its own floor too: interlab SD
0.17 log, CheqSol against shake-flask at RMSE 0.34. Nothing can score below
that, and a difference smaller than it is not a difference.

**16% of a druglike set is refused** — 13 of 80 are ampholytes. That is a
large slice to decline, and it is printed beside the accuracy, because a
model that refuses its hard cases looks better the more it refuses.

**A claim in this project's own notes was overturned by the better
measurement.** The solubility module said ESOL beat Marvin on Marvin's own
documentation molecule, resting on an ESOL-era experimental value of −2.19
for aspirin. SC-2's interlaboratory mean over 16 sources is **−1.67**, and
against that Marvin (0.14 off) and AqSolDB (0.05) both beat ESOL (0.42).

**Non-aqueous — scored, and the shift is NOT validated by it.** Abraham's
coefficients are "obtained by linear regression using experimentally
determined partitions and solubilities" — the endpoint being scored. That
leakage is structural and cannot be engineered away, so only two of three
arms are claims. On 968 de-leaked cases (159 solutes, 70 solvents, ONS
Solubility Challenge dataset):

| arm | n | MAE | RMSE | status |
| --- | --- | --- | --- | --- |
| composite — our prediction vs measured | 786 | 0.68 | 0.96 | **honest** |
| baseline — our ESOL vs measured aqueous | 786 | 0.61 | 0.85 | **honest** |
| shift only | 786 | 0.29 | 0.49 | *optimistic* |

*Status is carried per arm in the tool's own output — text and `--json` alike — from a
closed vocabulary. The shift arm is `OPTIMISTIC` and can never be emitted as
`VALIDATED`: its coefficients were fitted to the endpoint scored here.*

**The composite is barely worse than the baseline**, which is the result:
the non-aqueous answer is an ESOL prediction moved by a measured shift, so
ESOL dominates its error. That claim does not require the shift to be
independently validated. **The control shows the leakage directly** — with
leaked rows kept the shift arm improves 0.29 → 0.21 MAE, flattering itself
28% on data it was fitted to, while the composite barely moves.

→ [`benchmarks/solubility/README.md`](../benchmarks/solubility/README.md)

---

## ADMET — and the confound that had to be found first

The ADMET panels were checked for whether their apparent discrimination
means anything. For hERG, it largely did not: the model's separation
**correlated with molecular size at r = +0.98**, which is worse than no
finding, because it looks like a result.

A size-matched panel of 19 compounds was built specifically to break that.
Even there, r(prediction, size) = +0.82 and r(prediction, logP) = +0.75.

This is why the rule-based **hERG risk-factor checklist ships alongside the
model and is labelled "not a prediction"** — it is honest about being a list
of structural correlates, which is what the evidence supports.

→ [`benchmarks/docking/README.md`](../benchmarks/docking/README.md)

---

## IR spectra — 27.6 cm⁻¹ after scaling

**Method.** 16 modes over water, CO₂ and methane, from real ORCA 6.1.1
`opt_freq` runs at B3LYP/def2-SVP, scored against NIST CCCBDB experimental
fundamentals.

| | |
|---|---|
| MAE unscaled | 64.7 cm⁻¹ |
| fitted scaling factor | **0.9666** |
| MAE scaled | **27.6 cm⁻¹** |

The scaling factor is the external corroboration: published B3LYP factors sit
in the 0.961–0.975 band, and a parser written against raw output text landing
inside it is evidence independent of any test here. It is **recorded, not
applied** — ORCA states its own factor and double-applying would be silent.

**Intensities are scored by symmetry, not against a table**, because group
theory supplies an exact expected answer where a table supplies an
approximate one. Every symmetry-forbidden band came back at **0.00**: CO₂'s
symmetric stretch, methane's ν₁ and ν₂, and 20 of benzene's 30 modes.

Acetone and benzene are run and parsed but **not scored on frequency** —
their assignments are not one-to-one with a sorted list, so pairing by index
would manufacture the comparison rather than measure it.

→ [`benchmarks/ir/`](../benchmarks/ir/)

---

## Electrostatic potential — where the two methods disagree

**Method.** Agreement would prove nothing: two methods that both put negative
potential near oxygen correlate whatever their shape. So the ab initio ESP is
scored against the point-charge one on the same conformer and grid, and the
result is the **disagreement**.

| | |
|---|---|
| surface correlation, 6 molecules | r = +0.80 to +0.99 |
| bromobenzene sigma-hole cap (0–30°) | **+10.35** kcal/(mol·e) |
| same molecule, point charges | **−5.69** |

The ab initio potential **changes sign around one atom**. A point-charge
model puts one charge there, so its potential cannot change sign with angle
and reports bromine as uniformly negative.

Three halobenzenes were run in place of the one asked for, specifically so
this could come out wrong: the hole deepens F −4.03 < Cl +13.85 < Br +21.46,
and **fluorobenzene has no sigma hole at all**, which is the textbook
exception.

→ [`benchmarks/esp/`](../benchmarks/esp/)

---

## Regulatory rules — scored per rule, and one is not perfect

**Method.** 148 structures across four corpora — positives, negatives, edge
cases and historical — with every rule reporting TP/FP/TN/FN rather than
"matched". A rule with perfect recall and terrible precision passes any
positives-only suite and is worse than useless in a screen.

**Every shipped rule has at least one positive case.** Sixteen of the
twenty-two did not when Schedule 3 landed, and a rule with no positive
scores a perfect 1.00 while testing nothing — the same vacuous pass this
section exists to refuse. A guard fails if a future rule ships without one.

90 of the 91 rules — all three CWC schedules and the US DEA listed
chemicals — score precision 1.00 and recall 1.00. The one that does not:

| rule | precision | recall |
|---|---|---|
| `cwc-1-a-6` nitrogen mustards | **0.50** | 1.00 |

It matches **chlorambucil** and **melphalan**, licensed cytotoxic medicines
and neither among the HN1/HN2/HN3 the entry enumerates. Both are recorded as
expecting no match, so the benchmark scores them as the false positives they
are. The rule ships marked `approximate` with a limitation saying so —
staying silent about nitrogen mustards would be worse, and reporting
precision 1.00 would be worse still.

The edge cases carry the weight. **Diisopropyl fluorophosphate** has sarin's
phosphoryl, fluorine and alkoxy, no P–C bond, and is not Schedule 1; a rule
that could not tell them apart would score perfectly on the positives alone.

Schedules 2 and 3 added a second kind of edge case: **chemicals the treaty
exempts by name**. Every generic family pattern hits its own exemption, so
without them fonofos, N,N-dimethylaminoethanol and N,N-diethylaminoethanol
— all in ordinary commerce — would each be a false positive. Each exemption
is a skeleton plus an exact carbon count, so it covers the chemical and its
salts without excusing a larger molecule that merely contains the fragment.

And a third: **licensed medicines near a rule's boundary.** Pyridostigmine
and neostigmine each fail one half of Schedule 1's entry A.16 — one
quaternises the ring nitrogen with no exocyclic ammonium, the other has the
ammonium but carries its carbamate on a benzene — so a pattern testing
either feature alone would flag a medicine. **Choline** matched Schedule 2's
entry B.11 until the pattern was tightened: those entries reach "and
corresponding *protonated* salts", and reading that as any four-coordinate
cationic nitrogen also reaches quaternary ammoniums, which are *alkylated*
salts.

→ [`benchmarks/regulatory/`](../benchmarks/regulatory/)

---

## Structural annotation — coverage, measured before building on it

**Method.** `annotate()` run over the 181-molecule naming corpus, counting
what fraction of heavy atoms each annotation reaches.

| annotation | coverage | every molecule? |
|---|---|---|
| ring systems | 45.3% | yes |
| functional groups | 19.7% | yes |
| IUPAC locants | **34.8%** | **no — 76 of 181 get none** |

The asymmetry is why the features were built in that order. 95 of 181
molecules name to a retained string carrying no atom indices at all, so
locants are absent rather than approximate for them, and the UI states
coverage instead of rendering a blank.

Stereocentre detection agrees with RDKit **exactly** — 13 of 13 tetrahedral
centres — so the engine's detector is used in preference to a second one
rather than cross-checked against it.

---

## Thermophysical properties — the paper's own tables

**Joback's Tables IV and V, reproduced.** Table IV's group summation is
checked field by field, and Table V's boiling point, freezing point, critical
temperature, critical pressure and critical volume each come from the paper's
own worked example — including the two cases that separate a correct
implementation from a plausible one: T_c computed from the **experimental**
boiling point rather than the estimated one, and P_c from the **total atom
count** rather than the group count.

**The 41 groups keep the symbols the paper printed**, and a dash in the table
is null rather than zero. A group with no contribution to a property must
make that property unavailable, not add nothing to it.

## Hansen solubility parameters — the regression, and its low range

r² = **0.935** for δd over 344 data points, **0.925** for δp over 350, and
**0.960** for δhb over 375, read off the paper's Figs. 1–3.

**Eqs. 27 and 28 are the acceptance test.** Below 3 MPa^0.5 the paper applies
a separate regression, and without it n-hexane's δp is **−2.009** — a
negative solubility parameter. It is a fixture precisely because the failure
produces a plausible-looking number rather than an error.

## Energetic properties — two oracles from opposite ends

**Oxygen balance: Klapötke Table 4.1, nine compounds, all nine reproduce** to
within **0.08 percentage points**, which is rounding in the book's
one-decimal printing. They span +20% to −74% — both signs — and ammonium
nitrate is a carbon-free edge case that a formula indexed on carbon could get
wrong.

**Detonation: Kamlet & Jacobs Table III, eight compounds.** The table prints
ρ₀, N, M and Q *and* the P and D their Eqs. (8) and (9) give from them, so it
validates the equations without requiring any thermochemistry. Worst
deviation **0.08 kbar** in pressure and **0.012 mm/µs** in velocity, both
rounding in the printed figures.

**K = 15.58, where the textbook prints 15.88.** The paper states 15.58 four
times — abstract, Eq. (8), the slope of Fig. 1, and Table III — and 15.88
appears in it zero times. Both constants produce entirely plausible pressures,
so no check on an output separates them: HMX comes out **384.7 kbar** against
the printed 384.7 with the paper's value and **392.1** with the textbook's.
Only the source can settle it, and a mutation arm is named for it because it
is the one a future reader is most likely to "fix" from the textbook.

## Geometric aromaticity — one oracle each, from two different papers

**HOMA: Krygowski's own benzene values, all three of them**, from one
sentence on p73 — with R_opt and α re-derived from the paper's Eqs. 6 and 7
rather than transcribed:

    geometry               bond length    printed HOMA
    electron diffraction      1.399 Å        0.969
    microwave                 1.397 Å        0.979
    X-ray                     1.392 Å        0.996

A three-point oracle from one source is worth more than three scattered ones:
the same parameters and the same formula have to hit all three, and the
spread across geometries is itself the point the limitation text makes.

**Bird: Katritzky 1990, five compounds, both ring sizes, five bond types**,
every one inside 0.2 of a one-decimal printed value:

    pyridine     I₆   85.73   against   85.7
    thiophene    I₅   65.48   against   65.5
    pyrrole      I₅   69.26   against   69.3
    furan        I₅   43.44   against   43.4
    pyrazole     I₅   74.60   against   74.6

**The oracle is deliberately not Bird's own paper.** Bird 1985 prints indices
and **no bond lengths** — pages 4–6 contain none — so not one of its
published values is reproducible from it. Katritzky tabulates experimental
geometries *and* the Bird indices computed from them, for the same compounds.

**So the claim is scoped: this reproduces Katritzky's experimentally-derived
indices from Katritzky's tabulated geometries**, not Bird's printed values.
The two papers disagree where they chose different geometries — Bird gives
pyrrole 59 against Katritzky's 69.3 — which is why the distinction is not
pedantry. Table 6 also carries MNDO, AM1 and MINDO/3 columns computed from
optimised geometries, and a fixture keyed on one of those would look like a
passing test, so the shipped oracle records every column and a guard asserts
they are far enough apart to tell.

## Measured, and deliberately not shipped

The most load-bearing results here.

**A trained NMR shift model.** Boosted trees over HOSE codes plus RDKit atom
features, aimed squarely at the 10.00 ppm `rough` band. Held-out MAE moved
2.98 → 2.91 with a confidence interval spanning zero: **not
distinguishable**. It did not ship. What *did* come out of that work was a
real improvement found along the way — splitting the index on explicit
hydrogens — which shipped instead.

**Miller polarizability — SHIPPED, and the reason it was not is the
clearest case of a rotted reason in this file.** It read "the parameters
are unpublished", which was a claim about ChemAxon's documentation rather
than about the literature: Miller 1990's Table I prints all twenty rows
([source:miller1990]). Both recorded failures have causes now. The +27% on
benzene is the `CBR` row, whose symbol reads as "carbon in a benzene ring"
and means the opposite — [source:miller1979] says the π system in benzene
"is directed only along two bonds", so benzene is `CTR` and `CBR` is for
π-*branched* carbons; the wrong row gives +36%. The −50% on CCl₄ is the
shape of using the wrong form: `α = (4/N)(Σ τ)²` squares a sum. With both
right, benzene lands at +0.6% and CCl₄ at +0.2%.

**AND THE `CBR` RULE HAD TO BE READ TWICE.** [source:miller1990] p 8535
states it as a hydrogen count — "CBR in trigonal carbon atoms **not bonded
to hydrogen atoms**" — and its own Table II three pages later contradicts
that on every case where the two differ: toluene's ipso carbon has no
hydrogen and is `CTR`, styrene's ipso carbon has no hydrogen and is `CBR`,
acetone's carbonyl carbon has no hydrogen and is `CTR`. The tables win, the
rule is conjugation, and the hydrogen rule was implemented here for one
commit on the strength of that sentence — it puts benzene at 13.99 against
10.39. **Nine of the paper's printed assignments are now pinned as
fixtures**, chosen because they separate the two candidate rules; only
nitrobenzene disagrees, and that row is also one of the worst in Table II
at −6.8%.

**HLB — SHIPPED as Griffin HLB, and only that.** The recorded reason was
"No formulas published, no worked example, and the reference
implementation's default is a proprietary consensus method. Nothing to
check a result against." Three of those four clauses fell to one paper:
[source:schott1989] prints Griffin's Eq. [1], its closed form Eq. [2] with
worked constants, and Davies' group numbers. The fourth stands and is not
chased — ChemAxon's default is proprietary, so agreeing with Marvin is
unreachable.

That paper also supplies the *reason the name is ambiguous*, which shaped
what shipped: the Davies scale "differs substantially from the Griffin
scale in the entire range of practical applications". So "HLB" names two
incompatible quantities, and only Griffin ships, under that name, with an
applicability predicate taken from the source's own opening sentence.

**Cao–Liu TSEI — SHIPPED and REACHABLE, and the second pass corrected
the first.** `topology_analysis` refused a "steric index" because the name
covers several incompatible quantities, there was no identity to check
against, and no reference value was found. [source:cao2004] answers the
last two; the first still stands, so it ships as *Cao–Liu TSEI* and never
as a bare "steric index".

What the first pass shipped was **eq 7**, `Σ 1/L³`, which the paper derives
one line after "For any alkyl, it only contains carbon and hydrogen atoms.
When its hydrogen atoms are ignored, eq 4 also can be simplified to eq 6".
On an all-carbon path that is the general form exactly, so Table 1's twenty
values reproduced perfectly and nothing was wrong — off it, a first-tier
chlorine came out 1.000 against the **1.4190** the paper derives in full.
The general form (eq 8a) uses each atom's covalent radius over the
**summed bond lengths** to the reaction centre.

**18 of the 19 reachable printed values now reproduce**, across Tables 2, 4
and 6 — the halogens, the ethers, the branched alkyls. Two further things
the second reading found:

- The second-tier figures "0.1250, 0.2500, and 0.3750" are a **straw man
  the paper rejects**. It concludes three carbons on one carbon contribute
  6.5 times one, and every TSEI it publishes after that uses it: t-Bu is
  1.8125 in Table 2 and 1.8395 in Table 6, never 1.3750.
- **Table 6's i-Pr = 1.3752 does not reproduce** and is recorded rather
  than chased. The paper's own text, Table 2 and every i-Pr-bearing row of
  Table 4 say 1.2500 with hydrogens ignored, which plus its seven
  hydrogens is 1.2801. 1.3752 is within 0.0002 of 1.3750, t-Bu's
  plain-additivity value in the table above it.

**THE RADII HAVE TWO INDEPENDENT ROUTES, AND THEY AGREE TO THE LAST
DIGIT.** The paper's radius source is Lange's Handbook 15th ed. Table 4.7,
p 4.35 ([source:langes15]) — its own ref 18 — and it was not held when
this shipped. Typing a remembered Pauling table would have been the
"fields nobody can check" failure this project has already paid for, so
every radius was instead **recovered by inverting a TSEI value the paper
prints**: for a lone first-tier atom, eq 8a collapses to
`8 ρ³/(1+ρ)³` with `ρ = R_X/R_C`.

    F   0.7449  ->  0.63997     Cl  1.4190  ->  0.99001
    Br  1.6957  ->  1.14002     I   2.0265  ->  1.33000
    H   from Me = 1.0362  ->  0.30001
    O   from MeO = 0.9505 ->  0.66000

**The book gives 64, 99, 114, 133, 30 and 66 pm — and carbon at 77.2
rather than a rounded 77**, which is the extra digit the paper itself
writes and what identifies this as the right table rather than a
neighbouring one. Seven for seven, from a transcription and a
back-calculation that share no step. The inversion is kept as a LIVE
cross-check rather than as history, so a mistyped radius for any of those
seven fails against a printed TSEI.

The book carries 28 elements, so nitrogen, sulfur and phosphorus are
covered now — they have no printed TSEI to invert from, so the projection
declined every amine, thiol and phosphine until the handbook arrived.
**The equation is geometric and the validation is not**: `R³/l³` has no
per-element fitting, so a radius is the only input any element needs, but
Cao & Liu validated against alkyl, halogen and ether substituents, so a
silver or mercury radius buys arithmetic rather than evidence.

**Gutmann donor and acceptor numbers — SHIPPED from the classical tables.**
The earlier assessment rejected [source:gutmann_frontiers2022] correctly —
ionic liquids, and its own acceptor model failing — but that was a
statement about one paper, not about the scales. [source:gutmann1976]
carries both: 53 donicities and 32 acceptor numbers, transcribed from a
300 dpi render because the OCR of a 1976 scan is actively wrong.

**Abraham coefficients for 202 further solvents.** The source paper
measures 91 and *predicts* the rest, saying of those they should not be
taken "as gospel". Only measured ones ship.

**Acetic acid is no longer among them, and its removal is the worked
example of how these entries go stale.** It was asked for by name and
refused here on two grounds: the predicted coefficients failed this
module's own uncertainty bound (1.34–2.04 log on ordinary drugs), and the
predicted table is the `c = 0` refit and so has no intercept. A *measured*
set was later read from [source:stovall2015] — Eq. (6), N = 68,
SD = 0.182 — which answers both, so it ships. The 117 names still listed
predicted-only are refused on exactly the original grounds.

**The Platts fragment scheme for Abraham solute descriptors.** It would
work, and it is ~480 coefficients and ~132 hand-written SMARTS patterns —
with fragments 59–67 defined in a *figure* rather than in text, so they
cannot be read from the PDF's text layer at all — carrying 0.7–1.0 log of
its own error. Looking the descriptors up instead costs neither, and that
is what shipped. Recorded here because two of the three reasons this
project had written down for deferring non-aqueous solubility turned out to
be **false on measurement**, and only the Platts one was real.

**The TSEI steric index — SUPERSEDED; see the Cao–Liu entry above.**
This paragraph is kept because it is the entry that rotted: "no reference
value to gate against" was true when written and false by 2004. The Szeged
index, from the same batch, *did* ship — because it
could be validated against a theorem.

**Missing-residue repair.** Spiked with PDBFixer, measured, and rejected:
the rebuilt geometry is not trustworthy near a binding site, which is
precisely where docking would use it.

**TD-DFT / UV-Vis.** Scoped, measured, refused — twice over, and there is a
benchmark for it now with pre-registered criteria and a control arm that
reproduces this project's own earlier figures to four decimals.

The first retry disproved the first diagnosis: benzene's strongly-allowed
¹E₁ᵤ band was said to be missing because def2-SVP lacks diffuse functions,
and re-run with `nroots 15` it is there at 7.918 eV. Eight roots were simply
too few. Adding diffuse functions to **B3LYP** improves every position and
destroys the intensity, which is the wrong trade for a spectrum whose
question is which band is strongest.

The second retry tried the functional that was supposed to fix it.
**ωB97X-D3 does not rescue UV-Vis and moves benzene the wrong way** — it
blue-shifts valence π→π\* further, to +0.73/+1.10 where B3LYP is
+0.59/+0.98. What it does fix is the intensity collapse, which turns out to
be a *B3LYP* failure rather than a basis-set one: with the same diffuse
basis ωB97X-D3 keeps *f* = 0.993 per component. (ωB97X-D3, not ωB97X-D -- different dispersion treatment, and the ORCA keyword is `wB97X-D3`.) The two error modes still
cannot be minimised together, so the refusal stands on a measurement rather
than a prediction.

**One comparison here was wrong and is corrected.** This section read "f =
0.96 against an experimental ≈0.9 — essentially correct". ¹E₁ᵤ is doubly
degenerate and ORCA reports each component separately, while an experimental
oscillator strength integrates one band; 0.96 is a *component* and 0.9 is the
*band*, so the two were never comparable. Summed, the computation gives
1.92–2.00 against a measured **0.90** (Bolovinos et al., *J. Mol.
Spectrosc.* **103** (1984) 240–256) — **2.13–2.23× too strong**. The ≈0.9
itself was right all along and simply had no citation; a web summary
attributing 1.25 to the CASPT2 study turned out to be a figure that paper
does not contain.

→ [`benchmarks/uvvis/`](../benchmarks/uvvis/)

**The quinine conformer hypothesis** — that a single MMFF conformer was
responsible for the hybrid's refusal — was tested with Boltzmann averaging
and **refuted**: MAE moved 4.30 → 4.27 ppm. Recorded so it is not
re-proposed.

---

## Reproducing any of this

Each benchmark directory has its own README with the exact commands. Nothing
here depends on data that is not either in the repository or downloadable by
the scripts.
