## Summary

- Fully specified ionization: a named site transform moves both hydrogen count and formal charge (including when hydrogens are real atoms). A net charge with no structure is refused; several graphs at one charge are listed, not picked.
- Two supplied ions compose as given (`compose_supplied_ions`) with no invented protons. `pka_compatible` is a named-step ΔpKa under comparable conditions and never feeds `balance_two`; already-charged input is not assessed.
- Small cited ion catalog (chloride through pyridinium, hydrogen sulfate kept apart from sulfate). No UI, no Mode C, not a crystal.

## Cross-links

Follows #583 (slice 2 Mode A). Worktree is `D:\_scratch\OpenChem-Studio-salt-slice-3` on `cursor/salt-composition-slice-3`, from `origin/master` after that merge.

## Verified

- `tests/test_salt_stoichiometry.py` and `tests/test_salt_evidence.py` — 32 passed after supplied-ion composition.
- `tests/test_salt_ionization.py` — 8 passed after the explicit-hydrogen deprotonation fix (`fed14181`).
- `tests/test_ionic_species.py` plus the sources `used_by` check — 5 passed; `docs/SOURCES.md` regenerated.
- Task 7 guard set (architecture count/map, changelog, 8-way pins, salt tests, layering, constant-docs, reachability) — 84 passed.
