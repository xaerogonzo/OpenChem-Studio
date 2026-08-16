# Solubility benchmark

Two steps, the same shape as `benchmarks/admet/`:

```bash
uv venv tdcenv --python 3.11
uv pip install --python tdcenv/Scripts/python.exe "PyTDC==0.4.1" "setuptools<81"
tdcenv/Scripts/python.exe benchmarks/solubility/fetch.py
uv run --no-sync python benchmarks/solubility/score.py
```

`data/` is fetched, not committed. Nothing here ships an invented corpus —
a solubility number typed from memory is exactly the mistake this
project has already paid for twice.

## What it reports, and why each column exists

**Coverage beside accuracy.** The predictor refuses ampholytes, salts and
mixtures by design. Dropping those rows silently would make the model look
better the more it refused — accuracy over a denominator the model chose
for itself is not accuracy. Refusals are counted and named.

**Stratified by ionization class.** An aggregate over mostly-neutral
molecules hides whatever the acid/base handling does, and the pH machinery
is the entire point of the feature.

**Baseline and pH-adjusted scored separately.** They validate different
layers, so an error can be attributed to the baseline model, the pKa, or
the ionization equation rather than blamed on whichever is nearest.

**Shape checks, not only scalars.** A model can carry a respectable MAE
and an absurd curve. The directional checks are claims about *this*
independent-site Henderson–Hasselbalch model — acid rises with pH, base
falls, neutral flat — and are phrased as model-shape claims rather than
as universal chemistry.

## THE ANTI-LEAK RULE

**AqSolDB is not scored against AqSolDB.** It is the set the ADMET
sidecar's `Solubility_AqSolDB` head was trained on, so a figure there
measures memorisation, not skill — the same circularity already recorded
for nmrshiftdb2 in the NMR work. `score.py` refuses and says so in its
output rather than quietly omitting the row, because an omission reads as
an oversight while a refusal reads as a decision.

ESOL has no such relationship to the data: fixed coefficients published in
2004, so the set is a genuine held-out test for it.

## Solid form is missing, and that is itself a finding

Intrinsic solubility depends on the solid phase — free acid, free base,
hydrochloride, sodium salt, hydrate, polymorph — and AqSolDB records none
of it. So no entry can enter a free-form-only headline, and the scorer
prints that rather than presenting a mixed-solid-form aggregate as if the
question were settled. A future corpus that *does* record solid form
should populate the field; `score.py` already reads it.

## This is evidence disclosure, not a release gate

Pre-registered before any number was seen:

- both models are reported; neither is selected as a winner;
- no model is called "validated" for beating Marvin, or for anything else
  this benchmark alone can show;
- the feature ships as an informational/comparative predictor.

A mediocre MAE is a fact to publish, not a reason to withhold the feature.
