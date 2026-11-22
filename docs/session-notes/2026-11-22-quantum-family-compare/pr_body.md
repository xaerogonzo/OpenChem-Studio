## Summary

- Two Quantum history jobs of the same calculation type can tabulate `QUANTUM_FAMILY_QUANTITIES` (SCF energy; ORCA HOMO/LUMO on `sp`). Matching uses `{provider}.{suffix}` and the descriptor’s provider, never display names or raw energy keys.
- Different programs are allowed when columns name them. SCF energy still requires the same molecule, method/basis, charge, multiplicity, solvent, and input fingerprint. NMR stays the per-atom dialog. Mixed ordinary-vs-Quantum stays an empty allowlist.

## Cross-links

Follows wizard Quantum staging #639. Design §9 and decision 8 in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`.

## Verified

On `D:\_scratch\OpenChem-Studio-9f362f21` with `PYTHONPATH=src`, `QT_QPA_PLATFORM=offscreen`, and `D:\_scratch\OpenChem-Studio-d7b5ea33\.venv\Scripts\python.exe`: `pytest tests/test_history_compare.py tests/test_property_execution.py tests/test_changelog_fragments.py tests/test_docs_are_current.py tests/test_layering.py` 330 passed.
