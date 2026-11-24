## Summary

- Mixed ordinary-versus-Quantum compare is the Gasteiger Dipole Moment magnitude (`dipole.magnitude`) versus this-run `{provider}.dipole_moment` in Debye, including across molecules.
- Provenance gates are generic: ordinary `charge_model == "gasteiger"` and `origin_independent is True`; QC `origin_independent is True` and submitted `charge == 0`. EEM/QEq are filtered before candidate count so they cannot block a Gasteiger output.
- The Δ is arithmetic, not a same-geometry charge-model error: ordinary uses that execution's geometry; `sp` uses the submitted QC geometry; `opt`/`opt_freq` uses the optimized geometry.

## Cross-links

Stacked on family compare #650. Merge #650 first, then this. Hückel, Miller, Method combo, Fill, and dipole arrows stay parked.

## Verified

On `D:\_scratch\OpenChem-Studio-gasteiger-qc-mixed-dipole` with `uv run python -m pytest`: `tests/test_history_compare.py tests/test_dipole_typed.py tests/test_score_dipole_surface.py tests/test_changelog_fragments.py tests/test_docs_are_current.py` — 504 passed. Repeated with `OPENCHEM_DATA_ROOT` set to an empty temp directory: 504 passed.
