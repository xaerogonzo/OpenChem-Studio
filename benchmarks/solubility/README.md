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

ESOL against the de-leaked Solubility Challenge, 67 scored of 80:

| stratum | n | MAE | RMSE | median | max | bias |
| --- | --- | --- | --- | --- | --- | --- |
| all | 67 | 0.74 | 0.98 | 0.52 | 2.65 | −0.20 |
| neutral | 16 | 0.80 | 1.05 | 0.51 | 2.47 | +0.02 |
| acid | 22 | 0.61 | 0.85 | 0.37 | 2.36 | +0.06 |
| base | 29 | 0.81 | 1.03 | 0.63 | 2.65 | **−0.52** |

RMSE 0.98 is in line with ESOL's own documented accuracy, on compounds it
was not fitted on.

**THE STRATIFICATION EARNED ITS KEEP ON THE FIRST RUN.** The aggregate
bias is −0.20 and reads as noise. Split by class, ESOL **under-predicts
bases by half a log unit** while acids sit at +0.06. A single MAE would
have hidden a systematic error across a third of a druglike set.

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

**THE BASE BIAS REPLICATES.** −0.42 here against −0.52 on the first set,
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
