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
- **Seed stability, two ways**, with no hardcoded verdict — a human reads
  it. Counts (mean/min/max/range/stdev) *and* set agreement, because
  counts alone hide the interesting failure: five seeds each returning 14
  conformers looks stable and is not, if they are 14 *different*
  conformers every time.

  `union` is what all seeds found pooled; `coverage` is the fraction of
  it a single run typically finds. **1.00 means every run finds the whole
  discovered set; 1/nseeds means every run finds its own private set.**
  Sameness across runs is decided by the same criterion the
  de-duplication uses, and that comes for free rather than needing a
  second matcher — pooling two runs and de-duplicating gives the union,
  so `|A ∩ B| = |A| + |B| − |A ∪ B|` is exact.

  Measured on the shipped criterion: everything rigid scores 1.00,
  pentane and ibuprofen 0.92, ethylene glycol 0.82, and ethylmorphine
  **0.75** — the weakest agreement in the corpus, and the reason its
  union (17) exceeds its single-run reference (12).

## `funnel.py` — where the candidates actually go

`score.py` answers "how many". `funnel.py` answers "where did the rest
go", for one molecule, which is the question a count cannot reach:

```bash
uv run --no-sync python benchmarks/conformers/funnel.py ethylmorphine
uv run --no-sync python benchmarks/conformers/funnel.py "CCCCO" --seeds 3
uv run --no-sync python benchmarks/conformers/funnel.py ethylmorphine --inspect "seed=0 embedding=17"
```

It prints every stage — requested, attempted, embedded, converged,
distinct before minimisation, distinct by RMSD alone, distinct under the
shipped criterion, returned after the cap — and then the pairs that were
**discarded**, with the origin of each so `--inspect` can write the pair
out as an SDF and you can look at the structures.

**It is observational and delegates every stage to production.** The
RMSD-only arm is production de-duplication with the energy window at
infinity (`NO_VETO`); the cap is `select_for_return`; the criterion is
`distinct_conformers`. There is no funnel-local notion of conformer
identity, ordering or truncation, and a disagreement with the running app
is a bug here rather than a finding about conformers.

**Per-seed is the authoritative view; the pooled aggregate is not.**
Production never pools seeds, so the union across seeds says how much of
the space one run misses and must never be read as a number of conformers
production keeps or loses.

### Three words that are not interchangeable

| term | meaning |
| --- | --- |
| **merged away** | discarded — production judged it the same conformer |
| **vetoed merge** | **retained** as a separate conformer; energy declined the merge |
| **truncated** | a valid distinct conformer omitted only by the keep limit |

A vetoed pair is not a loss. Reading the vetoed count as "conformers
thrown away" inverts the meaning of the number.

### What it found, and what it did not

Measured at 50 embeddings, seed 0, on the corpus — **before
`useSmallRingTorsions` shipped**, which these findings then motivated
(cyclohexane's PRE-opt row is 3 under the flag; the section below has the
gate):

```
molecule         embedded  distinct PRE-opt  converged  POST-opt  POST shipped
cyclohexane            50          1               50        1          2
(S)-ibuprofen          50         17               50       10         10
ethylmorphine          50          8               50        2         10
```

- **De-duplication is not where the candidates go.** On ibuprofen it
  removes nothing at all — 10 by RMSD alone, 10 under the shipped
  criterion. The 17 → 10 fall is minimisation converging distinct starts
  into shared minima, which is what minimisation is for.
- **The discarded pairs are degenerate, not distinct.** Of the merged
  pairs whose largest corrected torsion moved more than 90 degrees, the
  greatest energy difference is 0.0000 (butane), 0.0000 (pentane), 0.0009
  (ibuprofen) and 0.0680 (ethylmorphine) kcal/mol. Equal energy with a
  large torsion is the signature of a mirror-image pair, and butane's are
  exactly its g+/g− forms at ±65 degrees — merging which is what produces
  the textbook count of 2.
- **Sampling is the constraint at the rigid end.** Cyclohexane's 50
  embeddings are all one shape before minimisation; the twist-boat arrives
  only through the energy veto.

`n/a` in the torsion columns covers two situations and ethanol is the
common one: RDKit's torsion enumeration is **empty** for a skeleton as
small as C-C-O-H, so there is nothing to measure rather than a measurement
that failed. Either way it is never printed as 0.

## `useSmallRingTorsions`: the gate that shipped it

ETKDGv3's default torsion preferences barely sample small-ring pucker —
the funnel measured cyclohexane's 50 embeddings collapsing to ONE
pre-optimisation shape. The flag was gated **in isolation, at this
benchmark's own protocol** (50 embeddings/seed, identical seeds, nothing
else varied), so its effect could not be confounded with the application
default changes that shipped beside it. OFF vs ON, full corpus:

```
                     OFF                          ON
aziridine            1.0 [1-1]                    identical
2H-azirine           1.0 [1-1]                    identical
benzene              1.0 [1-1]                    identical
ethanol              2.0 [2-2]                    identical
butane               2.0 [2-2]                    identical
1,2-dichloroethane   3.0 [3-3]  (over)            identical, no further over
cyclohexane          2.0 [2-2]                    identical
pentane              4.6 [4-5]  (over)            identical, no further over
ethylene glycol      7.4 [7-8]                    identical
(S)-ibuprofen        9.2 [8-10]                   identical
ethylmorphine       12.8 [10-14]  union 17       15.0 [10-18]  union 25
```

- **Ten of eleven molecules byte-identical**; the eleventh improves —
  ethylmorphine's flexibility IS ring pucker, and the flag grew its
  5-seed union 17 → 25 while its coverage fell 0.75 → 0.60 (the
  discoverable space grew faster than per-run yield; more embeddings per
  run is what narrows that, and the app default rose separately).
- **Cyclohexane counts 2 either way, and the funnel says why that is
  safe**: pre-opt diversity rose 1 → 3, but chair and twist-boat still
  merge geometrically (RMSD 0.3747 < 0.5), so the energy veto stays
  load-bearing and extra twist-boat *sampling* never became extra
  twist-boat *counting*.
- **The 2H-azirine same-shape floor is unmoved** — checked deliberately,
  because the flag targets small rings and azirine's distorted-minimum
  artefact is what `_IDENTICAL_SHAPE_RMSD`'s lower bound was measured on.
  `test_the_same_shape_floor_stays_between_its_measured_bounds`
  recomputes both ends and passes under the flag.
- **Paired cost, same corpus, same seeds, one session**: 25.9 s OFF →
  30.2 s ON total (×1.17); worst single molecule cyclohexane 1.3 s →
  2.1 s (×1.6); ethylmorphine ~unchanged (14.1 s → 13.7 s).
- The environment block and the app's provenance now record the flag
  explicitly, True or False, read from the provider that ran — so no
  stored record is ambiguous about which sampling produced it.

## Which numbers are regression controls

The per-molecule counts, unions and coverages are **means and ranges over
five seeds**, not the expected result of any single run — ethylmorphine's
12.8 [10-14] is a distribution. Exact comparison is only meaningful for a
fixed seed at a pinned RDKit version and embedding count, which is what
`build_predictions.py` writes into the `environment` block. Treat a
difference in the last digit of a mean as sampling, and re-measure before
treating it as a change.

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
