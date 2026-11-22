## Summary

- Results **Compare with…** lists other ordinary property executions and Quantum jobs together, with Property/Quantum labels and a stable picker mapping.
- A mixed pair is compared only through `match_mixed_history` against `MIXED_QUANTITIES`. That allowlist ships empty, so similar names (dipole, Hückel vs eV, Miller polarizability) are refused: no approved shared quantity is defined.
- Same-kind compare is unchanged, including Quantum NMR on the per-atom dialog. A later allowlist row is the contract a patched-entry test already exercises.

## Cross-links

Continues the Results history triangle after #637. Design note §9 and decision 8 in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`.

## Verified

On `D:\_scratch\OpenChem-Studio-b9203894` with `PYTHONPATH=src` and `D:\_scratch\OpenChem-Studio-d7b5ea33\.venv\Scripts\python.exe`: `tools/suite_shards.py --pin-new` pinned `tests/test_history_compare.py` to shard 5; `pytest tests/test_history_compare.py` 27 passed; `pytest tests/test_history_compare.py tests/test_property_execution.py tests/test_results_history.py tests/test_changelog_fragments.py tests/test_layering.py tests/test_docs_are_current.py` 308 passed; later `pytest tests/test_changelog_fragments.py tests/test_docs_are_current.py tests/test_layering.py tests/test_property_execution.py tests/test_results_history.py` 286 passed.
