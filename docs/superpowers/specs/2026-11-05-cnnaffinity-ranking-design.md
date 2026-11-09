# CNNaffinity ranking power (design)

**Status:** freeze `PREREGISTRATION_CNN_AFFINITY.md` (`e52f01ae`). Catalog
`rescore` finished 2026-11-08 **HARMFUL** (`RESULT_CNN_AFFINITY.md`).

**Kept:** CNNaffinity on frozen Vina poses; within-assay Spearman; gnina
1.3.3 `score_only`; freeze → list → gates → rescore → report → separate
integration PR. MM-GBSA and RBFE stay out.

## Why this exists

Vina estimates a ligand–receptor interaction energy for docking. gnina
CNNscore estimates whether a pose looks like a correct pose. gnina
**CNNaffinity** predicts affinity from the 3D complex, in **pK units**,
higher = stronger. That third output is the candidate. It is trained with a
pose-dependent affinity loss, so scoring the **same Vina poses** is the
right control.

Local Vina ranking against pChEMBL is a null
(`docs/DOCKING_RANKING_BENCHMARK.md`: median ρ(−Vina, pChEMBL) **+0.046**,
Vinardo Δρ **+0.000**, 77 series, 833 ligands). Pose tests do not speak to
that.

CNNaffinity is a learned pK-style score. CrossDocked2020 pK labels do not
distinguish Kd, Ki, and IC50. ChEMBL pChEMBL is also mixed by type. This
test is **within-assay ranking**, not Ki prediction. The corpus primary
stratum is Ki (`chembl_corpus.PRIMARY_ENDPOINT`); `list` reports composition
and does not rebuild the selection.

## Question

On the frozen 77 single-assay series, does **CNNaffinity of the representative
Vina pose** rank ligands with pChEMBL better than **that pose’s Vina score**?

Primary endpoint, **paired complete-case**:

    For each series, keep ligands that have CNNaffinity, a representative
    Vina pose score, and pChEMBL. n is that subset. MIN_SERIES (5) applies
    to n, not to the original series size.

    Δρ = median over deciding series of
         ρ(CNNaffinity, pChEMBL) − ρ(−Vina_on_the_same_ligands, pChEMBL)

Vina stays negated (more negative is better). **CNNaffinity direction is
predeclared: higher is better. It is not negated.** A gate checks the parser
and that gnina still sorts / documents that convention. If the extracted
numbers look inverted, the run is a **technical failure → NULL**. Do not
flip the endpoint to fit pChEMBL.

The committed full-series Vina ρ may be printed as description. It is **not**
the baseline inside Δρ.

Report the median Δρ and both confidence intervals, not only the verdict.
A Δρ of 0.01 and of 0.15 are different product facts.

## Representative pose (measured in-repo, 2026-11-05)

This is **not** the arithmetic median of six scores.

`rank_report.representative` is `AffinityRange.median`:
`sorted(values)[n // 2]`. For six Vina scores that is **one of the six
values** — the **less negative of the two middle** values after sorting
(conservative for a Vina score; one rule for even and odd n). Documented in
`rank_report.py` and `_stats.py` because an averaging median was written
once, disagreed with the panel by 0.5 kcal/mol on a fixture, and was
removed.

Tie: among replicates whose `vina_best` equals that representative value,
take the **lowest `replicate` index** (stable sort of equal floats keeps
file order; runs are appended 0…5).

The ranking JSONL stores `vina_best`, `replicate`, `seed` — **not pose
coordinates** (`rank_power.py`). The pose is recovered by re-docking that
ligand with that seed under the ranking protocol (one receptor file per
series, same prep). **Gate:** reproduced `vina_best` must match the stored
value (same printed Vina hundredths). Failure to establish pose/score
correspondence → **NULL**, not a guessed pose.

The frozen scoring manifest per ligand names: series_id, molecule_chembl_id,
replicate, seed, vina_best (that pose), pose id (pose 1 of that run),
receptor pdb, CNNaffinity, CNNscore, CNNvariance.

**Vinardo Δρ was looser:** it took the shipped median of six Vina scores and,
separately, the shipped median of six Vinardo scores, which need not be the
same replicate. This test is stricter: both numbers come from one pose.

## Verdict (deciding series only)

| Verdict | Rule | Meaning |
|---|---|---|
| **PASS** | series-bootstrap lower bound of Δρ **> 0** | Improvement over Vina demonstrated under this protocol. Eligible for a **separate** integration proposal **only if** the clustered interval’s lower bound is also > 0. |
| **NULL** | series-bootstrap interval contains 0, or a technical failure (sign, pose correspondence, too many dropped series) | Improvement not demonstrated. No integration. The approach is unvalidated here, not disproven. |
| **HARMFUL** | series-bootstrap **upper** bound of Δρ **< 0** | This configuration ranks worse than Vina. Do not pursue it as a ranking improvement. |

Series bootstrap is the **legacy-comparable** verdict (`rank_report.py`:
resample 77 series). Receptor-clustered bootstrap (resample the **12 PDB
ids**, taking every series of a drawn receptor) is **mandatory robustness**,
prespecified, and reported beside it. It does not override PASS/NULL/HARMFUL.
It **does** gate UI: a series-PASS whose clustered interval contains 0 is not
integration-eligible.

Too many series dropped because n < 5 after pairing → NULL (threshold: more
than 5 of the deciding series).

## Oracle

Frozen 77 / 833 / 12 in `docs/DOCKING_RANKING_BENCHMARK.md`. Do not rebuild
`chembl_corpus.py` selection. Nested 56-series control is reported, not a
second verdict.

`list` prints, before rescore, for each series: `standard_type` / endpoint,
assay_type if stored, confidence_score if stored, `standard_relation`
(`=` only is already the corpus rule), units. No corpus change after
CNNaffinity is seen. Wording of the result: within-assay pChEMBL ranking;
if every deciding series is Ki, say that.

## How it is scored

gnina v1.3.3 `6fe1ce2`, sha256 of `gnina.cuda12.8.static` as in the pose
tests. `--score_only --cnn_scoring rescore --device 0`. WSL2 RTX 4060.

**Default 1.3 ensemble, recorded at freeze (do not leave as “default”):**

- `dense_1_3`
- `dense_1_3_PT_KD_3`
- `crossdock_default2018_KD_4`

Confirm from `--help` / version output at `gates`. A different ensemble is a
different test.

Collect CNNaffinity (primary), CNNscore, CNNvariance, Vina energy of that
pose. Only CNNaffinity enters Δρ.

Stages: `list` → `gates` → `rescore` → `report`. **Freeze before `rescore`.**

## Leakage

Same CrossDocked2020 PDB-id index as `gnina_core.TRAINING_OVERLAP` (sha256
`254d543af569d942c9f8cb395e45a1db620ad950d47af2c83240054185ed03b0`).

**Deciding:** series whose receptor PDB is not in that index.
**Reported apart:** series whose receptor is (3EML is in the twelve; `list`
names the rest **before** rescore).

This is a **receptor-PDB exclusion**, not a claim of no leakage. Homologs
and ligand-level overlap can remain. The test is practical ranking of this
pretrained model on these series, not simultaneous novelty of protein and
chemotype. Ligand-level overlap is disclosed, not a hold-out.

## Product rules

- Nothing in `src/` in the freeze or result commit.
- A later integration PR, and only after PASS **and** clustered LB > 0:
  labelled **learned affinity-ranking score**, never Kd, Ki, measured
  affinity, or binding affinity.
- Obtain path stays WSL + ELF + CUDA. Not External Tools by itself.
- `--cnn_scoring all`, gnina-as-dock, MM-GBSA, RBFE are other questions.

## Out of scope

Absolute ΔG, analogue CH2 resolution, virtual-screening enrichment, CASF
tables, training a new model, flipping CNNaffinity’s sign after seeing ρ.

## Worktree

`D:\_scratch\` only. Not `D:\Random Projects\OpenChem Studio` or the
contaminated `OpenChem-Studio-gnina-*` trees.
