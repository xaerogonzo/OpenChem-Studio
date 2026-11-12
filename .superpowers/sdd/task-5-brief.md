### Task 5: Chem net-charge enumeration without auto-pick

**Files:**
- Modify: `src/openchem/chem/salt_ionization.py`
- Test: `tests/test_salt_ionization.py`

**Interfaces:**
- Consumes: `apply_site_transform`, `choose_ionization`
- Produces:

```python
def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
    """Distinct fragment_key values reachable by protonate/deprotonate of heavy atoms that match target_charge."""
```

v1 enumeration: for each heavy atom, try `protonate` once and `deprotonate` once (single-site). Collect identities whose `fragment_formal_charge` equals `target_charge`. Do not rank. Then `choose_ionization` on that tuple.

Also:

```python
def select_by_net_charge(mol: Chem.Mol, target_charge: int) -> str | IonizationRefusal | IdentityRefusal:
    return choose_ionization(structures_at_net_charge(mol, target_charge))
```

- [ ] **Step 1: Write the failing tests**

```python
from openchem.chem.salt_ionization import select_by_net_charge, structures_at_net_charge
from openchem.domain.salt_stoichiometry import IonizationRefusal


def test_acetic_acid_at_minus_one_is_acetate() -> None:
    mol = Chem.MolFromSmiles("CC(=O)O")
    chosen = select_by_net_charge(mol, -1)
    assert chosen == fragment_key(Chem.MolFromSmiles("CC(=O)[O-]"))


def test_acetic_acid_at_plus_one_is_net_charge_only() -> None:
    mol = Chem.MolFromSmiles("CC(=O)O")
    refused = select_by_net_charge(mol, 1)
    assert isinstance(refused, IonizationRefusal)
    assert refused.code == "net_charge_only"


def test_two_inequivalent_sites_at_the_same_charge_are_not_picked() -> None:
    # 4-aminophenol: O-H and aniline N are different graphs at -1 vs +1;
    # at charge 0 the parent is already unique. Use 3-aminophenol / 4-aminophenol
    # is not the pair. Use 4-hydroxybenzoic acid: carboxylate vs phenolate at -1.
    mol = Chem.MolFromSmiles("O=C(O)c1ccc(O)cc1")
    keys = structures_at_net_charge(mol, -1)
    assert len(set(keys)) >= 2
    refused = select_by_net_charge(mol, -1)
    assert isinstance(refused, IonizationRefusal)
    assert refused.code == "ambiguous_microspecies"
```

If 4-hydroxybenzoic acid yields only one SMILES in this RDKit pin (tautomer merge — **forbidden by design** if it happens), the test must fail: identity is graph, not formula. Do not call `CanonicalRankAtoms` tautomer canonicalization. If the two deprotonations collapse, pick another pair (e.g. `NCCCO` vs wait — use `OCCc1ccc(O)cc1` tyrosol: aliphatic alcohol vs phenol). Prefer `OCCc1ccc(O)cc1` if 4-hydroxybenzoic collapses.

- [ ] **Step 2: Run to verify FAIL** (`select_by_net_charge` missing).

- [ ] **Step 3: Implement** by looping heavy atoms, applying each direction, skipping `IdentityRefusal`, keeping keys whose charge matches. `structures_at_net_charge` returns a tuple of unique keys in atom-index then protonate-before-deprotonate order.

- [ ] **Step 4: Run `tests/test_salt_ionization.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_ionization.py tests/test_salt_ionization.py
git commit -m "List ionization microspecies at a charge; never pick among several."
```

---

