### Fixed: C60 and other cages froze the application when IUPAC locants were on
- The vendored naming engine's von Baeyer decomposition searched combinatorially on a fullerene (no return in 40 s) on the UI thread. It now has step budgets (counts, not clocks) and returns "no derived numbering" in about 2 s. Covered by `tests/test_vb_decompose_budget.py`.
