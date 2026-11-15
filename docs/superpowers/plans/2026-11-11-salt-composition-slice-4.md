# Salt composition slice 4 Implementation Plan

> **For agentic workers:** Mode C of `docs/SALT_COMPOSITION_DESIGN.md`. UI is not this slice.

**Goal:** Enumerate candidate ionization states of one selected two-component pair, cap at 50 unique compositions, keep order and counts deterministic, and never use pKa to rank.

**Architecture:** Domain `enumerate_mode_c` does cartesian product + `balance_two` + dedupe + truncate. `chem/salt_mode_c.py` turns user mols and an optional species ladder into those candidates and propagates `LADDER_NOTE` or a ladder refusal as notes.

**Tech Stack:** Existing `balance_two`, RDKit only in chem/tests.

## Global Constraints

- `cursor/salt-composition-slice-4` from `origin/master` after #585.
- No UI, no `balance_many`, no NaOH path, no pKa in the solver.
- `MODE_C_LIMIT` is 50. `omitted = generated - returned`.
- Order: user states, then ladder index, then identity.
- Duplicate species+ratio kept once (first occurrence).
- New chem module named in ARCHITECTURE; count 167 → 168.
- Changelog fragment; `suite_shards.py --pin-new` without `--splits=3`.
