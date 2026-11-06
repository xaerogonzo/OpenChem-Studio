# Preregistration: does gnina CNNaffinity rank ChEMBL series better than Vina?

Written 2026-11-05, **Frozen 2026-11-05** by the commit that adds this file together
with `cnn_affinity_core.py` and `run_cnn_affinity_test.py` `list` / `gates`.
**No ranking ligand has been given a CNNaffinity under this test.** Nothing here
may change after the first catalog CNNaffinity. A change is a dated Amendment.
Nothing is added to `src/`.

This is not an Amendment of `PREREGISTRATION_GNINA.md` or
`PREREGISTRATION_GNINA_DOCK.md`. Those closed pose ranking. This test asks
whether **CNNaffinity** (pK-style, higher = stronger) ranks within-assay
ligands better than Vina’s score of the **same pose**.

Design record: `docs/superpowers/specs/2026-11-05-cnnaffinity-ranking-design.md`.

## The question

On the frozen 77 single-assay series
(`docs/DOCKING_RANKING_BENCHMARK.md`, ChEMBL_37, Vina 1.2.7, exhaustiveness 25,
six replicates), does CNNaffinity of the **representative Vina pose** correlate
with pChEMBL better than **that pose’s Vina score**?

CNNaffinity is a learned pK-style score (CrossDocked labels mix Kd/Ki/IC50).
pChEMBL is mixed by type. The corpus primary stratum is Ki. This test is
**within-assay ranking**, not a Ki or a Kd.

gnina as a dock, CNNscore pose ranking, `--cnn_scoring all`, MM-GBSA and RBFE
are **not arms**.

## How gnina is invoked

WSL2, `HOME=/home/main`, GPU device 0:

```
gnina -r receptor.pdb -l pose.sdf --score_only --cnn_scoring rescore --device 0
```

Binary: `D:/_scratch/gnina/gnina.cuda12.8.static` (v1.3.3, `6fe1ce2`,
2,056,131,000 bytes, sha256 `3340c1f4…72172`). Default ensemble, recorded by
name (not left as “default”):

- `dense_1_3`
- `dense_1_3_PT_KD_3`
- `crossdock_default2018_KD_4`

`--cnn` is not set. A different ensemble is a different test.

CNNaffinity is the only primary predictor. CNNscore and CNNvariance are stored
and do not enter Δρ.

## Representative pose

Not the arithmetic median of six scores. `AffinityRange.median` /
`rank_report.representative` is `sorted(values)[n // 2]`. For six Vina scores
that **is one of the six** — the less negative of the two middle values. Ties:
lowest `replicate` index among those with that `vina_best`.

`rank_power.py` stored `vina_best`, `replicate`, `seed`, not coordinates. The
pose is recovered by re-docking that ligand with that seed under the ranking
protocol. **Gate:** reproduced `vina_best` must match the stored hundredths.
Failure → NULL, not a guessed pose.

The frozen manifest per ligand names series, molecule, replicate, seed,
vina_best, pose 1, receptor, CNNaffinity, CNNscore, CNNvariance.

Vinardo Δρ median’d six Vina scores and six Vinardo scores independently (not
necessarily the same replicate). This test is stricter: both numbers come from
one pose.

## Paired complete-case

For each series, both ρ values use **exactly the same ligand ids**. A ligand
missing CNNaffinity, Vina, or pChEMBL is dropped from both. `MIN_SERIES` = 5
applies to that subset. The committed full-series Vina ρ may be printed as
description and is not the Δρ baseline.

## Populations (`cnn_affinity_core.py`)

Ranking twelve PDBs, 77 series. CrossDocked2020 PDB-id overlap is the same
index as the pose tests (sha256
`254d543af569d942c9f8cb395e45a1db620ad950d47af2c83240054185ed03b0`).

- **Deciding:** 35 series on **1ERE, 3HS4, 5I6X, 5TGZ, 6WGT** (five PDBs).
- **Reported apart:** 42 series on **2RH1, 2V5Z, 3EML, 3PBL, 4EY7, 5C1M, 5HK1**.

This is a receptor-PDB exclusion, not a claim of no leakage. Homologs and
ligand-level overlap can remain. Ligand-level overlap is disclosed, not a
hold-out.

`list` prints these counts and starts nothing. It also reports assay
composition from the corpus (`standard_type` / endpoint). No corpus change
after CNNaffinity is seen.

## Primary endpoint

    Δρ = median over deciding series of
         ρ(CNNaffinity, pChEMBL) − ρ(−Vina_on_the_same_ligands, pChEMBL)

CNNaffinity direction is **predeclared** higher-is-better and is not negated.
If extracted numbers look inverted, that is a technical failure → NULL. Do
not flip the sign to fit pChEMBL.

Series bootstrap: same as `rank_report.py` (2000 draws, seed 20260905,
resample series). Receptor-clustered bootstrap: resample the deciding PDB
ids, taking every series of a drawn receptor. Report median Δρ and **both**
intervals.

## Verdict (deciding series only)

- **PASS** if the series-bootstrap lower bound of Δρ **> 0**.
- **HARMFUL** if the series-bootstrap upper bound **< 0**.
- **NULL** if the interval contains 0, or technical failure (sign, pose
  correspondence), or more than 5 deciding series dropped because n < 5 after
  pairing.

PASS means improvement over Vina was demonstrated under this protocol. It
does not mean a Kd. **Integration eligibility** additionally requires the
clustered lower bound **> 0**. A series-PASS whose clustered interval
contains 0 is not a UI column. NULL means unvalidated, not disproven.
HARMFUL means do not pursue this configuration.

Nothing in `src/` in the freeze or result commit. A later PR, only if
integration-eligible, may add a **learned affinity-ranking score**, never Kd,
Ki, or binding affinity.

## Gates, all before any Δρ is read

`run_cnn_affinity_test.py gates` (no catalog CNNaffinity):

1. Version: `gnina v1.3.3` and `6fe1ce2`.
2. `--help` names the three ensemble models above.
3. `nvidia-smi -L` names the RTX 4060.
4. Binary size matches the pose-test asset.
5. `SCORE_ONLY` is true; sign is predeclared higher-is-better.

## What this freeze does not do

No catalog CNNaffinity. No rebuild of the ChEMBL selection. No External Tools
tab.

```bash
uv run --no-sync python benchmarks/docking/run_cnn_affinity_test.py list
uv run --no-sync python benchmarks/docking/run_cnn_affinity_test.py gates
```

`rescore` is the first catalog CNNaffinity and must not run before this freeze.

## Amendments

(none)
