## Summary

- ORCA, Psi4, and xtb store this run’s dipole magnitude in Debye as `{provider}.dipole_moment` immediately after SCF when the output prints one (Psi4 converts the last Multipole Moments magnitude from a.u.; xtb reads GFN1 `total (Debye)` and GFN2 `full` `tot (Debye)`, never `q only`). Zero is stored; a missing dipole still completes SCF.
- Compound ORCA jobs (`delta_scf`, `led`, `fukui`) never store a dipole, even when later tables print one. Ions keep the engine’s number with `origin_independent` false. This is not Gasteiger/EEM/QEq Dipole Moment.
- `MIXED_QUANTITIES` stays empty and there is no Quantum family dipole row.

## Cross-links

Continues Results–Properties–Quantum after #645. Store-only; mixed allowlist and family dipole remain later.

## Verified

On `D:\_scratch\OpenChem-Studio-98c2674e`, `uv run pytest tests/test_orca_engine.py tests/test_psi4_engine.py tests/test_xtb_engine.py tests/test_history_compare.py tests/test_orca_led.py tests/test_orca_fukui_v2.py tests/test_changelog_fragments.py` — 329 passed, 4 skipped.
