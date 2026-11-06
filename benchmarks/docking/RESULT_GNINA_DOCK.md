# Result: gnina default dock vs Vina

Run 2026-11-05 under `PREREGISTRATION_GNINA_DOCK.md` (Frozen 2026-11-05, freeze commit
`6301920e`). gnina v1.3.3 `6fe1ce2` default dock (no `--score_only`, `--cnn_scoring
rescore` as `--help` default), same crystal-ligand box as the survey, seed 20261029,
exhaustiveness 25, nine poses, WSL2 RTX 4060.

Vina pose-1 RMSDs are from this run's `vina_dock` (same provider path as PLEC).
Per-receptor numbers: `artifacts_gnina_dock/results.jsonl` (47 lines). Tallies:
`artifacts_gnina_dock/summary.json`. Molblocks, SDF, receptor PDBs, ligand starts and
`gnina.out` stay on disk and are not in Git.

**Verdict by the preregistered rule: NULL.** Zero deciding receptors unscored. Net +1
is short of PASS (`MIN_NET` 3) and of HARMFUL.

| Population | Docked | Vina top pose correct | After gnina dock | Gained | Lost |
|---|---|---|---|---|---|
| Deciding (not in CrossDocked2020 index) | 29 of 29 | 20 | 21 | 4 | 3 |
| Reported apart (in that index) | 18 of 18 | 15 | 14 | 1 | 2 |

One-sided sign test on the deciding arm, 4 gained of 7 changed: p = 0.5.

Gained: 6A93, 6KUX, 7M93, 8EF5. Lost: 1HSG, 6DG8, 6JP5. Overlap, reported apart:
gained 3EML, lost 3SN6 and 5KIR.

## What it means

- **Gnina's default dock does not move the top-pose count on this catalog enough to
  pass or to harm.** Twenty of 29 deciding receptors already had Vina's first pose
  within 2.0 A; after gnina search that is 21 of 29 — the same net as CNN rescore of
  Vina's poses (`RESULT_GNINA.md`), with a different 4/3 split.
- **Default gnina dock on this catalog is closed as a product path.** The freeze said
  a NULL leaves PR 508's pose-choice sentence in place. It does not speak to
  `--cnn_scoring all`, to DiffDock-class generators, or to analogue affinity ranking.
- Nothing is added to `src/`. The obtain path is still WSL + ELF + CUDA.
