# Solubility benchmark

Two steps, and neither needs anything beyond the project's own
environment — no PyTDC, no throwaway virtualenv, no Harvard Dataverse:

```bash
uv run --no-sync python benchmarks/solubility/fetch.py
uv run --no-sync python benchmarks/solubility/score.py
```

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
