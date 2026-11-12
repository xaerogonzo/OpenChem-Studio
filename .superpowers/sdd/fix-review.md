### Spec Compliance

- Spec compliant for the explicit-hydrogen fix. One commit, `fed14181`, on base `55011326`, message `Count bonded hydrogens when ionizing a site.`
- This review did not re-run pytest. The implementer report states `tests/test_salt_ionization.py` was **8 passed** after the fix, and that file holds eight tests, including the two new ones and the implicit-H acetic deprotonation. The RED report matches the old failure (`invalid_site` on deprotonation; protonation left a single bonded hydrogen).

Checked against the requirement:

- `AddHs` acetic acid, hydroxyl oxygen (the oxygen with a bonded hydrogen): `apply_site_transform(..., "deprotonate")` returns charge −1 and `fragment_key` `CC(=O)[O-]`. The parent SMILES is unchanged. The hydrogen is deleted with `RemoveAtom`, then `Chem.RemoveHs` drops the remaining explicit hydrogens so the key is the implicit acetate key.
- The implicit-H path is unchanged in structure: no bonded hydrogen, `GetTotalNumHs()` must be at least 1, then `SetNumExplicitHs(total - 1)` and charge −1. `test_deprotonating_acetic_acid_updates_hydrogen_and_charge` still expects `CC(=O)[O-]`, and it is one of the eight.
- Protonation of that same explicit-H oxygen adds one hydrogen atom and charge +1. It does not call `SetNumExplicitHs(GetTotalNumHs() + 1)` on top of a bonded hydrogen. The new test expects charge +1 and `CC(=O)[OH2+]`.
- `_ACID_ELEMENTS` is still N, O, P, S and `_BASE_ELEMENTS` is still N, P. `includeNeighbors=True` only lets an atom that already qualifies count a real hydrogen. Neutral carbon is still not offered. `test_acetic_acid_at_minus_one_is_acetate` and `test_acetic_acid_at_plus_one_is_net_charge_only` remain in the eight, so a full heavy-atom pass is still locked out for implicit acetic acid.

### Strengths

- Deprotonation and protonation each follow the representation the atom already uses: delete or add a hydrogen atom when one is bonded, and use the explicit-H property only when none is.
- `Chem.RemoveHs` is what makes an `AddHs` product share the implicit acetate key. Isotopic hydrogens stay, which is RDKit's default and matches the identity rule for isotopes.
- The N/O/P/S gate is still explained above the element sets, including the existing charge exception (a proton on an anion, or off a cation). The design sentence records why a later slice must not walk every heavy atom.
- The input molecule is copied through `RWMol`. Both new tests keep the parent SMILES.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

1. **Net-charge listing of an `AddHs` acetic acid is untested**
   - File: `tests/test_salt_ionization.py` (new tests call `apply_site_transform` only); `src/openchem/chem/salt_ionization.py` `GetTotalNumHs(includeNeighbors=True)`
   - The transform test locks the refusal that mattered. Reverting `includeNeighbors` would again leave `select_by_net_charge` with nothing to offer on an `AddHs` parent, and no test would fail. Add `select_by_net_charge(Chem.AddHs(Chem.MolFromSmiles("CC(=O)O")), -1) == "CC(=O)[O-]"` when the file is next touched. Do not block.

2. **The new "N, O, P and S only" sentences omit the charge exception**
   - File: `src/openchem/chem/salt_ionization.py` docstring of `structures_at_net_charge`; `docs/SALT_COMPOSITION_DESIGN.md` ionization-selection line
   - The comment above `_ACID_ELEMENTS` is the accurate rule: heteroatom acids, N/P bases, plus any existing anion or cation. A charged carbon can still be listed. The new sentences are right for neutral acetic acid, which is why they are there. Do not block.

### Recommendations

- Open the PR with this commit on the branch. The explicit-hydrogen requirement is met, and the minor notes are follow-ups.
- Leave multi-site indexes as the `ionize_at_sites` docstring describes them: each later index is read from the molecule the previous transform returned.

### Assessment

**Task quality:** Approved

**Ready to open a PR?** Yes.

**Reasoning:** An `AddHs` acetic hydroxyl deprotonates to `CC(=O)[O-]`, the implicit-H acetic test is still in the passing file, protonation of that oxygen is `CC(=O)[OH2+]`, and the N/O/P/S enumeration filter is intact. The eight reported passes cover those assertions. No code was changed in this review.
