## Summary

- Mode C enumerates candidate ionization states of one two-component pair: user structures first, then ladder species, then identity. Identical compositions are kept once.
- At most 50 compositions are returned, with generated / returned / omitted counts. A `BalanceRefusal` pair is skipped, not repaired. pKa is not used to rank.
- A species-ladder refusal is a note on the result, never a silent empty list. Still no panel.

## Cross-links

Follows #585 (slice 3 ionization, catalog, pKa evidence). Worktree is `D:\_scratch\OpenChem-Studio-salt-slice-4` on `cursor/salt-composition-slice-4`, from `origin/master` after that merge.

## Verified

- `tests/test_salt_stoichiometry.py` and `tests/test_salt_mode_c.py` plus architecture count/map — 38 passed (`PYTHONPATH` to this worktree `src`, main checkout venv).
- Shard pin `"tests/test_salt_mode_c.py": 6`.
