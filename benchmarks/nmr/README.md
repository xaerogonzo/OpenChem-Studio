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

## What did work, and shipped: explicit hydrogens split the index

**34.3% of nmrshiftdb2 records carry explicit hydrogens** and the rest do
not. `hose_code` walks every bond, so an explicit H becomes part of the
code — which means those records spoke a different code vocabulary from
the other two thirds, and neither could match the other. A molecule drawn
in the application has no explicit hydrogens at all, so it could only ever
match the 65.7%.

It was a live bug on the query side too: toluene's methyl carbon looked up
from `Chem.AddHs(...)` returned **8.89 ppm** against a literature 21.4,
and **21.52** from the same molecule without explicit hydrogens. Same
index, same molecule, two answers, no error either way.

Both sides now normalise through `nmr_database.heavy_atom_view`
(index format 2). Paired over the same held-out atoms, same download,
scored through the shipping `lookup` (`score_lookup.py`,
`compare_indexes.py`):

| ¹³C (24,330 atoms) | good | medium | rough | ALL | median |
|---|---|---|---|---|---|
| format 1 | 1.11 (10,835) | 3.36 (11,421) | 10.02 (2,024) | 2.91 | 1.28 |
| format 2 | 1.12 (11,390) | 3.36 (10,933) | 10.00 (1,957) | **2.85** | **1.23** |

| ¹H (7,727 atoms) | good | medium | rough | ALL | median |
|---|---|---|---|---|---|
| format 1 | 0.10 (2,953) | 0.26 (3,105) | 0.77 (1,647) | 0.31 | 0.13 |
| format 2 | 0.10 (3,052) | 0.26 (3,098) | 0.77 (1,555) | **0.30** | 0.13 |

Paired bootstrap over molecules: carbon **−0.092 ppm, 95% CI [−0.122,
−0.064]**; hydrogen **−0.025, [−0.031, −0.019]**. Both clear of zero.

Per-band accuracy barely moves; what moves is *which band an atom lands
in* — 555 more carbons rated `good`, 67 fewer `rough`. **That is roughly
five times the ML model's only statistically real effect (−0.020 ppm on
¹H `rough` alone), across every atom instead of one band, for a
normalisation instead of 130 MB of dependencies.**

Two things the fix had to get right, both silent when wrong:

- **A hydrogen's own index maps to its parent heavy atom, not to
  nothing.** nmrshiftdb2 files a proton's shift against its heavy atom
  (6,987 of the held-out ¹H assignments do), but 444 point straight at an
  explicit hydrogen. An early version of this experiment *dropped* those —
  7,935 measurements across the training split — which is why its ¹H
  numbers were not comparable. Remapping keeps the measurement count
  identical at 605,374 before and after.
- **Atom indices must be remapped, not trusted.** `RemoveAllHs` renumbers,
  and the assignments reference the original numbering. `predict_spectrum`
  also has to report results back in the *caller's* numbering, or every
  label in the correlation plot lands on the wrong atom.

An index built before this is detected (`stale_format`) and the user is
offered a rebuild rather than refused a prediction — a format-1 index
still answers correctly for the environments it can reach.

## Running it — the shift-model training

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

Scoring the lookup alone needs no ML and no extraction — just a split and
an index. This is the one to run after any change to the codes or the
build:

```bash
python benchmarks/nmr/score_lookup.py split_index.sqlite
```

```bash
python benchmarks/nmr/compare_indexes.py before.sqlite after.sqlite
```

Training itself is the cheap part: **59 s** for carbon and **28 s** for
hydrogen on 438,795 and 135,838 rows; the resulting model is 3.8 MB. Every
other minute is downloading, parsing and featurising.

---

# Phase 33 — which selection rule should the hybrid use?

`chem/nmr_hybrid.py` merges the HOSE lookup with a scaled ORCA calculation
per atom. Phase 32 shipped it with a **scale-agreement gate** that refused
the whole merge when the calculation sat too far from trusted database
values, and five molecules were not enough to say whether that gate helped.
This is the comparison that settled it.

## Ground truth

**DELTA50** (*Molecules* **2023**, 28, 2449, CC BY 4.0) — 50 compounds,
143 assigned ¹³C shifts, CDCl₃, 600 MHz, ambiguities resolved by
gCOSY/gHSQC/gHMBC. Deliberately **not** nmrshiftdb2, which *is* the
lookup's index and against which any comparison would be circular.

Three compounds are excluded (`DMF`, `DMAc`, `2-Methyl-2-butene`): all
have carbons the molecular graph makes equivalent but experiment
resolves — restricted amide rotation, and E/Z methyls across a double
bond — so nothing here could assign them better than a coin flip. Atom
mapping comes from matching our computed shieldings to DELTA50's own,
never from the lookup, so the truth stays independent of both methods
under test. A compound whose correspondence cannot be established is
dropped, not guessed at.

Coverage was probed *before* spending ORCA time, since a set the lookup
already nails cannot discriminate: **68.9% good, 24.9% medium, 6.2%
rough**, with 23 of 47 molecules carrying at least one poorly-covered
carbon.

## Result — B3LYP/def2-SVP, 46 compounds, 207 atoms

Paired bootstrap over **molecules** (atoms of one molecule share a
structure and an assignment). Negative = better than what shipped.

| strategy | MAE | sel. acc | worst regret | vs gate | verdict |
|---|---|---|---|---|---|
| `hard_gate` (shipped) | 1.46 | 77.8% | 10.94 | — | refused 13/46 |
| **`warn_only`** | **1.33** | **80.2%** | **6.39** | −0.131 [−0.308, −0.017] | **better** |
| `global_error` | 1.33 | 80.2% | 6.39 | −0.131 [−0.308, −0.017] | better |
| `shrunk_error` | 1.33 | 77.3% | 6.39 | −0.130 [−0.308, −0.016] | better |
| `per_molecule_error` | 1.34 | 74.9% | 6.39 | −0.115 [−0.288, +0.025] | not distinguishable |
| `disagreement_defers` | 1.65 | 72.0% | 14.21 | +0.197 [−0.178, +0.665] | not distinguishable |
| `lookup_only` | 2.33 | 72.0% | 30.95 | +0.874 [+0.258, +1.648] | worse |
| `orca_only` | 2.68 | 28.0% | 7.85 | +1.223 [+0.856, +1.616] | worse |

Confirmed on 14 held-out molecules the strategies never influenced, and
repeated at **wB97X-D3/def2-SVP**, where the gate fires only 3 times in 42
and removing it is *not distinguishable* rather than better — never worse.

**Selection accuracy** and **regret** are the metrics that judge the rule
rather than the predictors: for every atom we know both predictions *and*
the truth, so we know whether the rule chose the closer source. A rule can
lower MAE purely because the calculation is good while still choosing
badly.

## What shipped, and why it is the boring option

`warn_only`: keep computing the calibration check, report it, **stop
refusing**. Refusing was not a threshold that wanted loosening — selection
already declines a bad calculation atom by atom, so a spectrum-wide veto
can only remove atoms the selection would have got right.

## Rejected, with numbers, so they are not re-invented

- **`per_molecule_error`** — estimate the calculation's accuracy from the
  atoms the lookup rates `good`, rather than trusting the install-wide
  calibration residual. This was the phase's main hypothesis. Not
  distinguishable, and *worse* at choosing (74.9% vs 80.2%): seven atoms
  is too small a sample to pay for itself.
- **`shrunk_error`** — the same, shrunk toward the global figure.
  Identical to the simple rule.
- **`disagreement_defers`** — when the two methods disagree beyond what
  their errors explain, back the one with the better track record. Written
  after looking at a single atom it fixed, in a 28-atom sample, where it
  cut worst regret 8.80 → 1.17. On DELTA50 it is the **worst** hybrid at
  both levels, and significantly worse than refusing at wB97X-D3. A clean
  example of overfitting caught by a held-out split.

## Two side findings

**The band constants are corpus-specific.** `HELD_OUT_BAND_MAE` was
measured on held-out nmrshiftdb2 as 1.12/3.36/10.00; on DELTA50 the
observed errors are **0.67/4.06/13.51**. The ordering survives and every
selection still lands the same way at realistic calculation accuracy, but
these are not constants of nature.

**The calibration residual is a poor accuracy proxy.** wB97X-D3/def2-SVP
has a *worse* residual than B3LYP/def2-SVP (2.976 vs 2.339 ppm) while
making *better* predictions (2.02 vs 2.68 ppm MAE). It is fitted on seven
small reference molecules and does not transfer to drug-like ones.

## Quinine conformers — hypothesis refuted

Quinine's calculation was poor enough to trip the old gate, and the
proposed explanation was that one MMFF conformer is a bad model of a
floppy molecule. Nine conformers, Boltzmann-averaged:

    MAE over all 20 carbons   single 4.30  ->  Boltzmann 4.27 ppm
    the three "hinge" carbons single 6.77  ->  Boltzmann 7.13 ppm

No. And the per-atom view is what shows it — the carbons the hypothesis
named got slightly *worse*. The DFT populations are also lopsided (one
conformer at 98.7%), so this is closer to "a different single conformer"
than a real average. One atom did improve enormously (C-5′, 12.52 → 1.66
ppm) and it was exactly the worst-regret atom, so conformer choice can fix
an individual bad atom without moving the spectrum.

## Running it — the DELTA50 comparison

Quantum chemistry happens once; every design question after it is
arithmetic over the same shieldings, which are committed.

```bash
uv run --no-sync python benchmarks/nmr/run_shieldings.py "B3LYP def2-SVP" --literature --delta50
uv run --no-sync python benchmarks/nmr/run_delta50.py "B3LYP def2-SVP"
```

The second needs no ORCA install. Reports, per-atom decision matrices and
SVG plots land in `benchmarks/nmr/reports/`.
