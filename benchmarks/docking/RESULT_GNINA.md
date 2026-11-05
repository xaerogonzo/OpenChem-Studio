# Result: gnina CNNscore on Vina's nine poses

Run 2026-11-05 under `PREREGISTRATION_GNINA.md` (Frozen 2026-11-04, freeze commit
`6d9de103`). Same Vina 1.2.7 poses as the prep-and-box survey `app` arm (seed 20261029,
exhaustiveness 25). gnina v1.3.3 `6fe1ce2` `--score_only --cnn_scoring rescore --device 0`
on WSL2 with the RTX 4060. Ranking number is **CNNscore**; CNNaffinity is stored beside it
and was not used to order poses.

Per-receptor RMSDs, Vina scores and CNN numbers: `artifacts_gnina/results.jsonl` (47 lines).
Tallies: `artifacts_gnina/summary.json`. Molblocks, SDF, receptor PDBs and `gnina.out` stay
on disk and are not in Git (~63 MB).

**Verdict by the preregistered rule: NULL.** CNN sanity passed (median of per-receptor max
CNNscore 0.87, floor 0.01). Zero deciding receptors unscored. Net +1 is short of PASS
(`MIN_NET` 3) and of HARMFUL.

| Population | Rescored | Vina top pose correct | After CNNscore | Gained | Lost |
|---|---|---|---|---|---|
| Deciding (not in CrossDocked2020 index) | 29 of 29 | 20 | 21 | 3 | 2 |
| Reported apart (in that index) | 18 of 18 | 15 | 15 | 1 | 1 |

One-sided sign test on the deciding arm, 3 gained of 5 changed: p = 0.5.

Gained: 6A93, 6KUX, 8EF5. Lost: 6CM4, 6DG8. Overlap, reported apart: gained 5HK2, lost 5KIR.

## What it means

- **CNNscore does not move the top-pose count on this catalog enough to pass or to harm.**
  Twenty of 29 deciding receptors already had Vina's first pose within 2.0 A; after rescoring
  that is 21 of 29.
- **CNN rescore of these Vina poses is closed as a product path.** The freeze said a NULL
  leaves PR 508's pose-choice sentence in place. It does not speak to gnina as a dock, to
  DiffDock-class generators, or to analogue affinity ranking.
- Nothing is added to `src/`. Slice 1's obtain path (WSL + ELF + CUDA, not a one-file PE)
  is unchanged.
