# Solubility benchmark

Two steps, and neither needs anything beyond the project's own
environment — no PyTDC, no throwaway virtualenv, no Harvard Dataverse:

```bash
uv run --no-sync python benchmarks/solubility/fetch.py
uv run --no-sync python benchmarks/solubility/extract_sc2.py <llinas2020.pdf>   # optional
uv run --no-sync python benchmarks/solubility/score.py
```

The middle step is optional and needs the paper, which is not in this
repository. It adds a second, independent evaluation set that brings a
noise floor and a published baseline — see below.

`data/` is fetched, not committed. Nothing here ships an invented corpus —
a solubility number typed from memory is exactly the mistake this project
has already paid for twice.

## Results, measured 2026-08-16

> **These figures superseded an earlier set, and the earlier set is still
> quoted in [PR #28](https://github.com/xaerogonzo/OpenChem-Studio/pull/28).**
> That body is immutable history and is deliberately not edited. Three
> polymorph pairs were being scored twice; refusing them moved every
> stratum — all n=67→61 / bias −0.20→−0.17, acid n=22→18 / +0.06→+0.26,
> base n=29→27 / −0.52→**−0.59**. Anything citing 67 scored or a −0.52
> base bias predates that fix. CHANGELOG carries the same table.


ESOL against the de-leaked Solubility Challenge, 61 scored of 80:

| stratum | n | MAE | RMSE | median | max | bias |
| --- | --- | --- | --- | --- | --- | --- |
| all | 61 | 0.74 | 0.98 | 0.52 | 2.65 | −0.17 |
| neutral | 16 | 0.80 | 1.05 | 0.51 | 2.47 | +0.02 |
| acid | 18 | 0.55 | 0.79 | 0.35 | 2.36 | +0.26 |
| base | 27 | 0.84 | 1.05 | 0.63 | 2.65 | **−0.59** |

RMSE 0.98 is in line with ESOL's own documented accuracy, on compounds it
was not fitted on.

**THE STRATIFICATION EARNED ITS KEEP ON THE FIRST RUN.** The aggregate
bias is −0.17 and reads as noise. Split by class, ESOL **under-predicts
bases by more than half a log unit** while acids sit at +0.26. A single MAE
would have hidden a systematic error across a third of a druglike set.

**SIX ROWS ARE REFUSED AS POLYMORPH PAIRS, and they used to be scored
twice.** Three compounds appear under one InChIKey as two solid forms —
chlorprothixene (−6.75 / −5.87, spread 0.88), sulindac (−3.68 / −4.50,
0.82) and phthalic acid (−1.49 / −1.61, 0.12). ESOL predicts one number per
*structure* and has no representation in which the forms differ, so scoring
both counted those compounds twice **and** charged the polymorph gap — up to
0.88 log, the size of the base bias itself — to the model as prediction
error. Found when `base_bias.py` halted on the contradiction. Refusing what
cannot be scored is the posture already taken for ampholytes, and it moved
the acid bias +0.06 → +0.26 and the base bias −0.52 → −0.59.

## Should the base bias be corrected? Pre-registered answer: no

`base_bias.py` puts an adjustment through a **leave-one-corpus-out
held-out** test whose criteria were fixed before it was first run.

    fit on SC-2+A1+A2 (n=24) -> test on SC-1 (n=20 after removing 7 shared)
    fit on SC-1+A1+A2 (n=34) -> test on SC-2 (n=10 after removing 7 shared)

    offsets           +0.511 and +0.615, agreement 0.105     PASS
    base RMSE         1.101 -> 0.918 and 0.822 -> 0.789      PASS (both improve)
    overall MAE       not worse in either direction           PASS
    improvement CI    [-0.034, +0.331] and [-0.248, +0.413]   FAIL

**Outcome `SURFACE_ONLY`, reading `insufficient_evidence`.** Four criteria
of five pass and the adjustment does substantially remove the bias
in-sample (base bias −0.619 → −0.108 and −0.351 → +0.265) — but the
bootstrap 95% CI on the held-out paired improvement **includes zero in
both directions**. That is not evidence there is no bias; it is
insufficient evidence for the pre-registered claim.

### Adding two more corpora did NOT increase power, and that is measured

The obvious response to a CI that missed by 0.0009 was more data. Two
further corpora were extracted from Avdeef 2020 — and they did not help,
for a structural reason worth stating:

| corpus | rows | after de-leaking | bases | can be a test side? |
| --- | --- | --- | --- | --- |
| A1 (Yalkowsky & Banerjee 1992) | 19 | **5** | **0** | no |
| A2 (Hopfinger et al. 2009) | 27 | 23 | 7 | no — under the minimum of 10 |

**Power here is set by the TEST side, not the fit side.** Both new corpora
are too small to be held out, so they can only join the fit pool — which
moves the fitted offset without narrowing any CI. The SC-1 arm's lower
bound actually went from −0.0009 to −0.0338, i.e. slightly *further* from
significance.

**A1 is 74% inside ESOL's own training set** — 14 of its 19 rows share an
InChIKey with Delaney's fit, and it contributes **zero** bases. Yalkowsky
& Banerjee 1992 is a classic compilation of industrial and agrochemical
solubility, which is exactly the chemistry ESOL was fitted on. Extracting
it anyway is what turned that suspicion into a number.

**And two of Avdeef's five appendix tables are the Solubility Challenge 2
sets under different names** — A3 is the tight set and A4 the loose set.
`extract_avdeef_sets.py` refuses them by name. Extracting them would have
double-counted SC-2 and inflated the apparent power of the very experiment
they were meant to strengthen.

So the honest position is that **the available independent data cannot
settle this question**, and the bias is reported to the user rather than
subtracted. `base_bias_result.json` records every criterion, both offsets,
the overlap matrix, per-corpus funnels, corpus fingerprints, the bootstrap
parameters and the acceptance-criteria version.

**SD and n are metadata, never weights.** The corpora carry per-compound
standard deviations and source counts; the fit is unweighted, one row per
compound, and does not use them.

### What would actually settle this

**The constraint is held-out druglike BASES, not compounds.** A1 and A2
failed to help because neither reaches the 10 bases needed to *be* a
held-out side — not because the effect is absent. Concretely, what would
close it:

- **~30+ measured intrinsic-solubility bases** that are not in SC-1, SC-2
  or Delaney's fit. That is the whole requirement; total corpus size is
  irrelevant if the bases are not there.
- **An `intrinsic` endpoint declared in the manifest.** A corpus of
  aqueous solubility over unspecified solid forms is `TEST_ONLY` however
  large — the reason AqSolDB's ~10k rows cannot be used.
- Avdeef's full **Wiki-pS0** database (3014 molecules, 6355 entries) would
  almost certainly do it. The paper says it is "planned to be released in
  book form", so it is not obtainable today; the 49 compounds published in
  its appendices are what exists.

Then `uv run --no-sync python benchmarks/solubility/base_bias.py` is the
whole rerun. The criteria are versioned (`acceptance_criteria_version`),
the corpora are declared in `CORPORA`, and the verdict decides on its own
whether production may change — so revisiting this costs one command and
no judgement calls.

**A rerun that flips to `SHIP` may not be taken at face value either.**
The offsets fitted here are +0.51 and +0.62 against a v2 pair of +0.59 and
+0.42; a constant that moves that much with the corpus is a constant to
re-examine, not to trust because it finally cleared a threshold.

**13 of 80 compounds — 16% — are ampholytes, and are refused.** That is a
large slice of druglike chemistry to decline, and it is printed beside the
accuracy so the two can never be read apart.

## Second set: Solubility Challenge 2, and what it adds

Table 1 of Llinàs, Oprisiu & Avdeef 2020 — 100 druglike compounds, and
after de-leaking Delaney's set (16) and refusing ampholytes (11), 73 are
scored:

| model | n | MAE | RMSE | bias |
| --- | --- | --- | --- | --- |
| ESOL | 73 | 0.90 | 1.26 | −0.05 |
| ESOL, acids | 22 | 0.86 | 1.10 | +0.40 |
| ESOL, bases | 17 | 0.70 | 0.87 | **−0.42** |
| **GSE (published baseline)** | 73 | 0.86 | 1.18 | +0.37 |

**THE BASE BIAS REPLICATES.** −0.42 here against −0.59 on the first set,
on entirely different compounds. One set makes a bias a curiosity; two
independent ones make it a property of the model. Delaney's paper mentions
ionization, amines and salts *zero* times, so ESOL cannot distinguish a
base from a neutral of the same size and lipophilicity.

**A NUMBER WITHOUT A BASELINE SAYS NOTHING.** The General Solubility
Equation scores RMSE 1.18 on the same compounds — and it needs a
*measured melting point*, which this app does not have. ESOL lands within
0.08 of it regardless. The honest reading is that the endpoint is hard,
not that our model is poor.

**AND THE SET CARRIES ITS OWN NOISE FLOOR:** interlab SD 0.17 log, with
CheqSol against high-quality shake-flask at RMSE 0.34. Nothing can score
below that, and a difference smaller than it is not a difference.

## THE ANTI-LEAK RULE CAUGHT BOTH MODELS

Obvious for one, and not for the other.

**AqSolDB (the trained model) is not scored at all.** It was trained on
the merged AqSolDB, which contains this evaluation set as one of its nine
constituent sources, so any figure would measure memorisation — the
circularity already recorded for nmrshiftdb2. `score.py` refuses and says
so in its output rather than quietly omitting the row: an omission reads
as an oversight, a refusal reads as a decision.

**ESOL needed de-leaking too, which the first design missed.** The merged
AqSolDB includes Delaney's own ESOL set (`dataset-G`, reference [7] in the
AqSolDB README), so scoring ESOL against AqSolDB would have been scoring
it against its own fit. `fetch.py` downloads that set purely to
**subtract** it: 14 of the 94 Challenge rows share an InChIKey with it and
are dropped, leaving 80.

## Why this source

`dataset-I` in the AqSolDB repository is the Solubility Challenge
(Llinàs, Glen & Goodman 2008): intrinsic solubility measured by one
consistent method on druglike compounds, and the recognised high-quality
reference for this endpoint. It post-dates ESOL's 2004 fit.

It validates the **baseline** layer only — the Challenge measures the
neutral form's intrinsic solubility, which is what the baseline model
predicts. The pH layer is covered by the shape checks (acid rises with
pH, base falls, neutral flat), phrased as claims about this
independent-site Henderson–Hasselbalch model rather than as universal
chemistry.

`solid_form` is not recorded by the source, so no free-form-only headline
is derived and `score.py` prints that as a finding. A future corpus that
does record it will populate the field, which the scorer already reads.

## Non-aqueous: what can and cannot be scored

```bash
uv run --no-sync --with openpyxl python benchmarks/solubility/nonaqueous.py
```

**THE LEAKAGE HERE IS STRUCTURAL AND CANNOT BE ENGINEERED AWAY.** Abraham's
solvent coefficients are, in the source paper's own words, *"obtained by
linear regression using experimentally determined partitions and
solubilities of solutes with known Abraham descriptors"*. The endpoint
being scored **is** the endpoint they were fitted to. Nothing here
validates the shift the way the sets above validate ESOL, and this
benchmark does not claim to.

What makes it worth running anyway is that the evaluation data carries a
**citation column**, so rows sourced from Abraham or Acree publications can
be identified and dropped — 1998 of 9536 usable rows, 21%.

Measured 2026-08-16, ONS Solubility Challenge dataset, 968 de-leaked
(solute, solvent) cases over 159 solutes and 70 solvents:

| arm | n | MAE | RMSE | median | bias | status |
| --- | --- | --- | --- | --- | --- | --- |
| composite — our prediction vs measured | 786 | 0.68 | 0.96 | 0.49 | −0.07 | **honest** |
| baseline — our ESOL vs measured aqueous | 786 | 0.61 | 0.85 | 0.41 | −0.03 | **honest** |
| shift only — predicted vs measured shift | 786 | 0.29 | 0.49 | 0.16 | −0.04 | *optimistic* |

*Status is carried per arm in the tool's own output — text and `--json` alike — from a
closed vocabulary. The shift arm is `OPTIMISTIC` and can never be emitted as
`VALIDATED`: its coefficients were fitted to the endpoint scored here.*

**THE COMPOSITE IS BARELY WORSE THAN THE BASELINE — 0.68 against 0.61 MAE
— AND THAT IS THE RESULT.** It confirms the claim the module makes: a
non-aqueous answer is an ESOL prediction moved by a measured shift, so its
error is dominated by ESOL and it is never more reliable than the aqueous
value behind it. That claim does **not** depend on the shift being
independently validated, which is why it can be made honestly.

**AND THE CONTROL SHOWS THE LEAKAGE DIRECTLY.** Re-run with
`--keep-leaked` and the shift arm improves from **0.29 to 0.21 MAE** — the
coefficients looking 28% better on data they were fitted to — while the
composite barely moves (0.68 → 0.69) because ESOL dominates it. A
de-leaking rule whose effect you cannot see is a de-leaking rule you have
not tested.

Three caveats that are stated rather than fixed: no temperature filter
(the set is largely ambient but does not say so per row); no `solid_form`,
so polymorphs and hydrates are mixed in; and dropping Abraham/Acree
citations is a **partial** defence, since their coefficients may rest on
measurements other people published.

182 of the 968 cases are refused outright by the shipped uncertainty
bound, and those refusals are counted rather than quietly excluded.

## This is evidence disclosure, not a release gate

Pre-registered before any number was seen, and unchanged by them:

- both models are reported; neither is selected as a winner;
- no model is called "validated" for beating Marvin, or for anything else
  this benchmark alone can show;
- the feature ships as an informational/comparative predictor.

A mediocre MAE is a fact to publish, not a reason to withhold the feature.

Sources: [AqSolDB](https://github.com/mcsorkun/AqSolDB) (Sorkun, Khetan &
Er, *Scientific Data* 2019), whose reference [8] is the Solubility
Challenge and reference [7] is Delaney's ESOL set.
