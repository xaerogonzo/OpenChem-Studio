# Conformer de-duplication benchmark

The regression check on "how many distinct conformers does the app find".
It exists because that question had no arbiter: a morphine derivative
reported "Kept 2 distinct conformer(s) of 10 embedded", and 3 on an
earlier run, and there was nothing to say which — if either — was right.

```bash
uv run --no-sync python benchmarks/conformers/build_predictions.py --label shipped
uv run --no-sync python benchmarks/conformers/score.py benchmarks/conformers/predictions_shipped.json
```

Two scripts, like `benchmarks/naming/`: generation is minutes and scoring
is milliseconds, so predictions are produced once and scored many times.
`score.py` refuses a predictions file whose corpus length or molecule
order disagrees, rather than silently mis-scoring a stale one.

## Read the reference types before reading the numbers

Half the corpus is **textbook** counts — cyclohexane's chair and
twist-boat, butane's anti and gauche. Half is **computational lower
bounds**, meaning *at least this many distinct minima were found under
the sampling protocol in `corpus.json`*. Ethylmorphine's 12 is not "this
molecule has 12 conformers". Exceeding a lower bound is not a failure and
the scorer does not treat it as one.

## What it reports beyond the count

- **The threshold sweep, with and without the energy veto.** A constant
  that only looks good at its own value is how the shipped 0.5 Å
  threshold got calibrated on butane and generalised badly.
- **RMSD, TFD and largest dihedral change** for pairs close enough to be
  merge candidates. This is what separates two situations the counts
  cannot: a pair kept apart with a *large* torsion change is a real
  conformational difference both geometric metrics missed; one with a
  *small* one would be a force-field artefact.
- **Seed stability** as mean/min/max/range/stdev, with no hardcoded
  verdict. A human reads it. Note that counts alone can hide instability
  — five seeds returning 14–16 conformers whose *sets* overlap poorly is
  not stable, and comparing retained sets across seeds is left to a
  later change.

## Two traps already paid for

**Seed bases must be strided.** `RDKitConformerProvider` uses
`random_seed + attempt` so embeddings within a run differ, which means
consecutive bases overlap: base 0 draws seeds 0–49 and base 1 draws 1–50.
The naive `range(seeds)` version reported *identical* counts for seven of
eight molecules — perfect stability, and really the same run measured
five times.

**The corpus covers over-counting as well as under-counting.** 2H-azirine
is there because about 2% of its embeddings converge to a distorted
minimum 10.7 kcal/mol up, and an energy criterion without a same-shape
floor promotes that artefact to a second conformer — the original bug in
reverse. Its row shows the veto correctly declining to fire on a 10.73
kcal/mol difference because nothing geometric differs.
