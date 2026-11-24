## Summary

- `{provider}.dipole_moment` origin independence is overwritten from the submitted job charge in `_with_run_settings`, not from the drawing's formal charge.
- Neutral origin-independent QC dipoles in Debye are a Quantum family row across conformer geometries when identity and method match. ORCA entropy term and xtb zero-point energy are engine-specific `opt_freq` family rows with matching model and geometry.
- Mixed ordinary-versus-Quantum stays an empty allowlist. Family provenance requirements are generic key/value identity checks, including `is True` for booleans.

## Cross-links

Follows stored QC dipole #646. Stack the Gasteiger-versus-QC mixed dipole PR on this branch after it is green; merge this first.

## Verified

On `D:\_scratch\OpenChem-Studio-qc-dipole-family` with `uv run python -m pytest`: `tests/test_history_compare.py tests/test_quantum_chemistry_service.py::test_dipole_origin_independent_follows_submitted_charge_not_the_drawing tests/test_changelog_fragments.py tests/test_docs_are_current.py` — 352 passed.
