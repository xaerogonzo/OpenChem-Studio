## Summary

- Quantum history compare tabulates HOMO and LUMO from `opt` and `opt_freq` as well as `sp`, still without requiring the same method or fingerprint.
- Frequency jobs also tabulate enthalpy and Gibbs free energy in Hartree when the electronic model and structure match (`requires_matching_model`). Entropy and ZPE are not family rows.
- Extraction and NMR routing are unchanged. Mixed ordinary-vs-Quantum stays an empty allowlist.

## Cross-links

Follows family compare #640 and wizard Quantum start #641. Design §9 in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`.

## Verified

On `D:\_scratch\OpenChem-Studio-13d22dd2` with `uv run pytest`: `tests/test_history_compare.py tests/test_changelog_fragments.py tests/test_docs_are_current.py tests/test_layering.py tests/test_help.py` 390 passed. Descriptor-level compare tests only; engines were not re-parsed.
