### Task 4: Chem site transform (structure, not charge)

**Files:**
- Create: `src/openchem/chem/salt_ionization.py`
- Test: `tests/test_salt_ionization.py`

**Interfaces:**
- Consumes: `fragment_key`, `fragment_formal_charge` from `salt_components`; `choose_ionization` from domain
- Produces:

```python
@dataclass(frozen=True)
class SiteTransform:
    atom_index: int
    direction: str  # "protonate" | "deprotonate"


def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
    ...


def ionize_at_sites(mol: Chem.Mol, transforms: Sequence[SiteTransform]) -> str | IdentityRefusal | IonizationRefusal:
    """Apply the named sites, then choose_ionization on the single result identity."""
```

`protonate`: `SetNumExplicitHs(n+1)` and `SetFormalCharge(z+1)` on that atom, then sanitize.
`deprotonate`: Hs must be ≥1 (explicit or implicit via `GetTotalNumHs`); then explicit Hs become `total-1`, charge `z-1`.

- [ ] **Step 1: Write the failing tests**

```python
from rdkit import Chem

from openchem.chem.salt_components import fragment_formal_charge, fragment_key
from openchem.chem.salt_ionization import SiteTransform, apply_site_transform


def _acetic() -> Chem.Mol:
    return Chem.MolFromSmiles("CC(=O)O")


def test_deprotonating_acetic_acid_updates_hydrogen_and_charge() -> None:
    mol = _acetic()
    oxygen = next(
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1
    )
    result = apply_site_transform(mol, SiteTransform(oxygen, "deprotonate"))
    assert fragment_formal_charge(result) == -1
    assert fragment_key(result) == "CC(=O)[O-]"
    # parent unchanged
    assert fragment_formal_charge(mol) == 0


def test_protonating_pyridine_updates_hydrogen_and_charge() -> None:
    mol = Chem.MolFromSmiles("c1ccncc1")
    nitrogen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "N")
    result = apply_site_transform(mol, SiteTransform(nitrogen, "protonate"))
    assert fragment_formal_charge(result) == 1
    assert "[nH+]" in fragment_key(result) or "c1cc[nH+]cc1" == fragment_key(result)


def test_a_bad_atom_index_is_refused() -> None:
    mol = _acetic()
    refused = apply_site_transform(mol, SiteTransform(99, "deprotonate"))
    assert refused.code == "invalid_site"
```

If pyridine's canonical SMILES in this RDKit pin is not `c1cc[nH+]cc1`, assert equality to `fragment_key` of `Chem.MolFromSmiles("c1cc[nH+]cc1")` instead of a literal.

- [ ] **Step 2: Run to verify FAIL** (`ModuleNotFoundError` for `salt_ionization`).

- [ ] **Step 3: Write minimal implementation**

Copy the molecule. Do not mutate the input. `REACHED_BY` pointing at `tests/test_salt_ionization.py`. Direction must be exactly `protonate` or `deprotonate`; anything else `invalid_site`.

```python
"""Fully specified ionization states for salt composition. No pKa sidecar."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.salt_components import IdentityRefusal, fragment_key
from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization

REACHED_BY = (
    "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
    "on the window yet"
)


@dataclass(frozen=True)
class SiteTransform:
    atom_index: int
    direction: str


def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
    if transform.direction not in {"protonate", "deprotonate"}:
        return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
    if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
        return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
    copy = Chem.Mol(mol)
    atom = copy.GetAtomWithIdx(transform.atom_index)
    if transform.direction == "protonate":
        atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
        atom.SetNoImplicit(True)
    else:
        total = atom.GetTotalNumHs()
        if total < 1:
            return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
        atom.SetNumExplicitHs(total - 1)
        atom.SetFormalCharge(atom.GetFormalCharge() - 1)
        atom.SetNoImplicit(True)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
    return copy


def ionize_at_sites(
    mol: Chem.Mol, transforms: Sequence[SiteTransform]
) -> str | IdentityRefusal | IonizationRefusal:
    current: Chem.Mol | IdentityRefusal = mol
    for transform in transforms:
        if isinstance(current, IdentityRefusal):
            return current
        current = apply_site_transform(current, transform)
    if isinstance(current, IdentityRefusal):
        return current
    key = fragment_key(current)
    if isinstance(key, IdentityRefusal):
        return key
    return choose_ionization([key])
```

Do not import `pka_providers` or `pka_species_ladder`.

- [ ] **Step 4: Run `tests/test_salt_ionization.py -v`**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/openchem/chem/salt_ionization.py tests/test_salt_ionization.py
git commit -m "Ionize a named atom by moving both its hydrogens and its formal charge."
```

---

