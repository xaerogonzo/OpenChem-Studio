# NMR shift model — trained, measured, not shipped

A gradient-boosted regressor was trained on nmrshiftdb2 to correct the
HOSE-code lookup in `src/openchem/chem/nmr_database.py`, on the held-out
protocol that module already records. **It lost.** The lookup is kept and
nothing under `src/` imports scikit-learn.

This directory is the evidence, kept so the result is reproducible and so
a later attempt starts from it rather than repeating the three hours.

## The protocol

The one already recorded in `nmr_database.py`, unchanged, because a
different split produces numbers that cannot be compared with the table
there. Every twentieth **record** of `nmrshiftdb2withsignals.sd` is held
out; the index is rebuilt from the other nineteen twentieths; the held-out
molecules are then predicted against their own measured shifts.

Reproducing the baseline first was the check that the split was right:

| | recorded (index built 2026-07-31) | reproduced (downloaded 2026-08-03) |
|---|---|---|
| carbons | 24,046 | 24,330 |
| coverage | 99.9% | 99.8% |
| MAE / median | 2.98 / 1.32 | 2.91 / 1.28 |
| good | 1.17 (n=10,541) | 1.11 (n=10,835) |
| medium | 3.38 (n=11,437) | 3.36 (n=11,421) |
| rough | 9.93 (n=2,068) | 10.02 (n=2,024) |

The small differences are the database itself: today's download carries
605,374 assigned shifts in the training split against the 613,193 in the
whole file as indexed on 2026-07-31, i.e. nmrshiftdb2 has grown by roughly
4% since. Everything below compares model against lookup **on the same
download**, so that drift cancels.

## The result

MAE in ppm, held-out, same atoms for every row.

### ¹³C — 24,330 atoms

| predictor | good (10,835) | medium (11,421) | rough (2,024) | ALL (24,280) |
|---|---|---|---|---|
| HOSE lookup | **1.11** | **3.36** | 10.02 | **2.91** |
| model alone | 1.75 | 3.62 | **9.97** | 3.32 |
| hybrid: HOSE for good | 1.11 | 3.62 | 9.97 | 3.03 |
| hybrid: HOSE for good+medium | 1.11 | 3.36 | 9.97 | 2.91 |

### ¹H — 7,727 atoms

| predictor | good (2,953) | medium (3,105) | rough (1,647) | ALL (7,705) |
|---|---|---|---|---|
| HOSE lookup | **0.10** | **0.26** | 0.77 | 0.31 |
| model alone | 0.15 | 0.28 | **0.75** | 0.33 |
| hybrid: HOSE for good | 0.10 | 0.28 | 0.75 | 0.31 |
| hybrid: HOSE for good+medium | 0.10 | 0.26 | 0.75 | **0.30** |

The best hybrid **ties** the lookup on carbon and improves it by 0.01 ppm
on hydrogen.

### Is the `rough` band a real win?

Paired bootstrap over molecules — not over atoms, since atoms of one
molecule share a structure and an assignment (`significance.py`). Negative
delta means the model is better.

| | delta (ppm) | 95% CI | verdict |
|---|---|---|---|
| C good | +0.640 | [+0.60, +0.68] | HOSE better |
| C medium | +0.258 | [+0.22, +0.30] | HOSE better |
| C rough | −0.049 | [−0.13, +0.03] | not distinguishable |
| H good | +0.057 | [+0.05, +0.07] | HOSE better |
| H medium | +0.021 | [+0.01, +0.03] | HOSE better |
| H rough | −0.020 | [−0.03, −0.01] | model better |

The only band where the model measurably wins is ¹H `rough`, by **0.020
ppm** — statistically real on 1,647 atoms, and below the reproducibility
of a ¹H shift between solvents or labs. For that, shipping the model would
cost scikit-learn and scipy (~130 MB), a second 150 MB download, and half
an hour of training on the user's machine.

## Why it lost

Not for want of tuning. Four ablations, each a full retrain:

| variant | C model MAE | note |
|---|---|---|
| residual target (chosen) | 3.32 | fits `shift − lookup` |
| raw target | 4.11 | a tree reproducing a 0–220 ppm axis is a staircase |
| no hashed-HOSE columns | 3.87 | the hash *does* help — see below |
| leave-one-out disabled | **2.89** | stops at 49 iterations having learned to copy the lookup |
| 1500 iterations instead of 400 | 3.40 | capacity is not the limit |

**The leaky variant is the finding.** Given the uncorrected index mean —
which contains the atom's own measurement — the model's optimum is to
reproduce the lookup, and it reaches it in 49 iterations and scores 2.89
against the lookup's 2.91. Remove that shortcut and the model has to
actually predict, and does worse. Nothing in these features holds
information the lookup does not already have.

Permutation importance says the same thing: the RDKit atom descriptors —
hybridisation, ring size, Gasteiger charge, E-state, Crippen
contributions, neighbour histograms out to two bonds — are all at or below
**0.01 ppm**, against 0.21 for the sphere-1 lookup mean. (The lookup
columns are near-duplicates of each other, so permutation splits their
credit and understates them individually; the descriptors' near-zero is
the part that is trustworthy.)

Two guesses were wrong and the measurements stand instead:

- The hashed HOSE codes were expected to be noise. They are the largest
  single contributor (+0.293 ppm for `hose1_hash`): at sphere one the code
  is coarse enough that 250 buckets encode it nearly losslessly.
- Leakage was expected to make held-out numbers collapse. It makes them
  *better*, by making the model a no-op.

## A separate finding: explicit hydrogens split the index

**34.3% of nmrshiftdb2 records carry explicit hydrogens** and the rest do
not. `hose_code` walks every bond, so an explicit H becomes part of the
code — which means those records speak a different code vocabulary from
the other two thirds, and neither can match the other. A molecule the user
drew (no explicit H) can only ever match the 65.7%.

Stripping to heavy atoms before coding, both when building the index and
when querying it (`hydrogen_normalisation.py`), on the same held-out split:

| ¹³C | good | medium | rough | ALL | median |
|---|---|---|---|---|---|
| as shipped | 1.11 (10,835) | 3.36 (11,421) | 10.02 (2,024) | 2.91 | 1.28 |
| H-normalised | 1.12 (11,390) | 3.36 (10,933) | 10.00 (1,957) | **2.85** | **1.23** |

The per-band accuracy is unchanged; what moves is *which band an atom
lands in* — 555 more carbons rated `good`, 67 fewer `rough`. That is a
larger overall gain than the ML model achieved, from a one-line
normalisation and no new dependency.

**Not shipped in this branch either**, because it is a change to the index
format that obsoletes every built index and deserves its own tests. Two
caveats a follow-up must settle first:

- The ¹H side is not directly comparable above — normalising drops
  assignments whose atom index *is* a hydrogen (7,935 measurements, and
  1H records do index the heavy atom, so these need checking rather than
  discarding).
- Atom indices must be remapped, not trusted: `RemoveAllHs` renumbers, and
  the assignments reference the original numbering.

## Running it

Needs `uv sync --group bench` for scikit-learn, and about 45 minutes.

Each script writes into the work directory named at the top of
`split.py`, which needs `nmrshiftdb2withsignals.sd` in it to begin with.

```bash
python benchmarks/nmr/split.py
```

```bash
python benchmarks/nmr/build_split_index.py
```

```bash
python benchmarks/nmr/extract.py train.sd split_index.sqlite train.npz --leave-one-out
```

```bash
python benchmarks/nmr/extract.py heldout.sd split_index.sqlite heldout.npz
```

```bash
python benchmarks/nmr/holdout.py train.npz heldout.npz --importance --out models.pkl.gz
```

```bash
python benchmarks/nmr/significance.py
```

The separate hydrogen-normalisation measurement is two more steps, and
does not depend on any of the above beyond `split.py`:

```bash
python benchmarks/nmr/hydrogen_normalisation.py build && python benchmarks/nmr/hydrogen_normalisation.py score
```

Training itself is the cheap part: **59 s** for carbon and **28 s** for
hydrogen on 438,795 and 135,838 rows; the resulting model is 3.8 MB. Every
other minute is downloading, parsing and featurising.
