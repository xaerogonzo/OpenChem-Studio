# The method screen behind `M062X def2-TZVP` (Phase R, step 0.4)

This directory is the **record** of how the method for the criteria-v2 validation run was chosen. It is
evidence for a decision, not a validation, and it is not meant to be re-run (the scripts hold paths from the
machine that ran them).

## What was done

1. `SELECTION_RULE.md` was written, and committed to the plan, **before any single-point number from a
   candidate existed**. Its SHA-256 is pinned in `src/openchem/chem/data/tautomer_validation_v2.json` and by
   `tests/test_tautomer_validation_v2.py` (line endings normalized).
2. `run_opt.py` optimized conformer pools of the four *development* systems (cytosine, acetylacetone,
   acetaldimine/vinylamine, 2-pyridone) with PBE0/def2-TZVP. 17 jobs, all converged; the acetylacetone pool
   came from an earlier run whose energies are inline in `analyze.py`.
3. `run_sp.py` ran single points of three candidates on those geometries: `M062X`, `wB97M-V` and
   `revDSD-PBEP86-D4/2021` (all def2-TZVP). `analyze.py` applies the rule. `screen_energies.json` holds every
   energy; `screen_results.txt` is `analyze.py`'s output; `opt_log.txt` and `sp_log.txt` are the run logs.

The held-out systems were **not** touched.

## Result (per-system maximum error, kcal/mol)

| functional | cytosine | acetylacetone | acetaldimine/vinylamine | 2-pyridone | rankings | worst |
|---|---|---|---|---|---|---|
| PBE0 (revision 3's preset) | rank fails | 2.06 | n/a | rank fails | no | 2.07 |
| **M062X** | 0.62 | 0.03 | 0.98 | 0.77 | all four | **0.98** |
| wB97M-V | 1.10 | 0.99 | 0.15 | 1.29 | all four | 1.29 |
| revDSD-PBEP86-D4 | rank fails | 2.05 | 0.85 | rank fails | no | 2.07 |

The rule picks M062X (0.98 against 1.29, a gap above the rule's 0.25 tie band).

## What this does not show

- It is **development-set evidence**: these systems were seen when v4 was designed.
- The single points sit on **PBE0 geometries**, a disclosed cost shortcut. The real model optimizes with
  M062X, which could move any number.
- Acetylacetone's reference is MP2/cc-pVTZ, so M062X's 0.03 is agreement with a weaker reference, partly luck.
- Cytosine's reference is one paper (Trygubenko 2002); the later CCSD(T)-F12 study (Barone 2023) was not used.
- The double hybrid failing two rankings is surprising and unexplained; the PBE0-geometry shortcut is one
  candidate explanation, not a tested one.
- Perry 2025 (`perry2025` in `docs/sources.toml`) is why wB97M-V and revDSD-PBEP86-D4 were screened beside
  M06-2X: it finds routine GGA and hybrid functionals poor on large drug-like tautomer systems. Goller 2022
  separately reports M06-2X reproducing the 2-pyridone CCSD(T) gap, which PBE0 misses.
