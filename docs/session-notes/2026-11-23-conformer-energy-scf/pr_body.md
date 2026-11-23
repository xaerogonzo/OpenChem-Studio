## Summary

- Quantum history compare can tabulate SCF energy in Hartree for two jobs that share submitted molecular identity, method, basis, charge, multiplicity, and solvent even when the geometries differ. The Δ is an electronic-energy difference, not a free-energy difference.
- Identity comes from each run's `input_molblock`, not the molecule UUID or current drawing. A rewrite, stereo flip, or isotope change of the same UUID is refused. Empty snapshots do not match.
- Enthalpy and Gibbs still need matching `input_fingerprint`. HOMO/LUMO and the empty mixed allowlist are unchanged.

## Cross-links

Follows family suffixes #642. Design §9 and §12.8 in `docs/RESULTS_PROPERTIES_QUANTUM_DESIGN.md`.

## Verified

On `D:\_scratch\OpenChem-Studio-690adb06` with `uv run --no-sync pytest tests/test_history_compare.py tests/test_changelog_fragments.py`: 101 passed.
