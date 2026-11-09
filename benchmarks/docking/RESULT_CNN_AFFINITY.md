# Result: CNNaffinity ranking power vs Vina

Run started 2026-11-06 and finished 2026-11-08 under
`PREREGISTRATION_CNN_AFFINITY.md` (Frozen 2026-11-05, freeze commit `e52f01ae`).
gnina v1.3.3 `6fe1ce2`, `--score_only --cnn_scoring rescore --device 0`, default
ensemble `dense_1_3`, `dense_1_3_PT_KD_3`, `crossdock_default2018_KD_4`, WSL2
RTX 4060. Poses recovered by re-docking the ranking protocol (Vina 1.2.7,
exhaustiveness 25) at the stored representative replicate and seed.

Per-ligand numbers: `artifacts_cnn_affinity/results.jsonl` (833 lines, 77
series). Tallies: `artifacts_cnn_affinity/summary.json`. Pose SDF, receptor
PDBs and `gnina.out` stay on disk and are not in Git.

The first 422 ligands scored on 2026-11-06; the process died mid
`5I6X_CHEMBL3871875`. Resume skipped those rows. Zero vina-hundredths
mismatches, zero missing CNNaffinity, zero deciding series dropped
(`n < 5` after pairing).

**Verdict by the preregistered rule: HARMFUL.** Series-bootstrap upper bound of
Δρ is below 0. Integration-eligible is false (verdict is not PASS).

| Population | Series with Δρ | Median Δρ | Interval |
|---|---|---|---|
| Deciding (1ERE, 3HS4, 5I6X, 5TGZ, 6WGT) | 35 of 35 | −0.130 | series [−0.330, −0.014] |
| Reported apart (CrossDocked2020 PDB-id overlap) | 42 of 42 | −0.091 | not the verdict |

Receptor-clustered interval on the five deciding PDBs: [−0.330, 0.179].
That interval is not a verdict override.

Δρ = ρ(CNNaffinity, pChEMBL) − ρ(−Vina on the same ligands, pChEMBL).
CNNaffinity was not negated.

## What it means

- **On this catalog, default-ensemble CNNaffinity ranked the frozen series
  worse than the same pose’s Vina score.** Median Δρ −0.130; the series
  interval does not contain 0.
- **This configuration is closed as a product path.** The freeze said HARMFUL
  means do not pursue it. It does not speak to a different ensemble,
  `--cnn_scoring all`, a crystal pose, or RBFE. It is not a Kd or a Ki.
- Nothing is added to `src/`. The obtain path is still WSL + ELF + CUDA.
  Pose-choice copy stays PR 508’s sentence.
