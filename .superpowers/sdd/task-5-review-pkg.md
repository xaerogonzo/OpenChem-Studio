# Review package 5feb4351..638e5ed5

## log
638e5ed5 List ionization microspecies at a charge; never pick among several.

## stat
 src/openchem/chem/salt_ionization.py | 58 +++++++++++++++++++++++++++++++++++-
 tests/test_salt_ionization.py        | 33 +++++++++++++++++++-
 2 files changed, 89 insertions(+), 2 deletions(-)

## diff
diff --git a/src/openchem/chem/salt_ionization.py b/src/openchem/chem/salt_ionization.py
index 9a40140a..991aaec5 100644
--- a/src/openchem/chem/salt_ionization.py
+++ b/src/openchem/chem/salt_ionization.py
@@ -1,20 +1,24 @@
 """Fully specified ionization states for salt composition. No pKa sidecar."""
 
 from __future__ import annotations
 
 from collections.abc import Sequence
 from dataclasses import dataclass
 
 from rdkit import Chem
 
-from openchem.chem.salt_components import IdentityRefusal, fragment_key
+from openchem.chem.salt_components import (
+    IdentityRefusal,
+    fragment_formal_charge,
+    fragment_key,
+)
 from openchem.domain.salt_stoichiometry import IonizationRefusal, choose_ionization
 
 REACHED_BY = (
     "tooling: consumed by tests/test_salt_ionization.py; ionization is not "
     "on the window yet"
 )
 
 
 @dataclass(frozen=True)
 class SiteTransform:
@@ -54,10 +58,62 @@ def ionize_at_sites(
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
+
+
+# Neutral Câ€“H and neutral oxygen both sanitize in this RDKit pin (acetic acid
+# gives ``[CH2-]C(=O)O``, ``CC(O)=[OH+]`` and ``CC(=O)[OH2+]``). Those are not
+# v1 microspecies: a named atom can still be transformed, but net-charge
+# enumeration only offers heteroatom acids and N/P bases, plus a proton on an
+# existing anion or off an existing cation. No ranking and no tautomer pass.
+_ACID_ELEMENTS = frozenset({7, 8, 15, 16})  # N, O, P, S
+_BASE_ELEMENTS = frozenset({7, 15})  # N, P
+
+
+def _enumeration_directions(atom: Chem.Atom) -> tuple[str, ...]:
+    charge = atom.GetFormalCharge()
+    number = atom.GetAtomicNum()
+    directions: list[str] = []
+    if number in _BASE_ELEMENTS or charge < 0:
+        directions.append("protonate")
+    if atom.GetTotalNumHs() >= 1 and (number in _ACID_ELEMENTS or charge > 0):
+        directions.append("deprotonate")
+    return tuple(directions)
+
+
+def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
+    """Distinct fragment_key values from one protonate or deprotonate that match target_charge.
+
+    Order is atom index, then protonate before deprotonate. Identity refusals
+    are skipped. Keys are not ranked and are not tautomer-canonicalized:
+    ``choose_ionization`` decides whether one graph is unique.
+    """
+    keys: list[str] = []
+    seen: set[str] = set()
+    for atom in mol.GetAtoms():
+        if atom.GetAtomicNum() <= 1:
+            continue
+        for direction in _enumeration_directions(atom):
+            result = apply_site_transform(mol, SiteTransform(atom.GetIdx(), direction))
+            if isinstance(result, IdentityRefusal):
+                continue
+            if fragment_formal_charge(result) != target_charge:
+                continue
+            key = fragment_key(result)
+            if isinstance(key, IdentityRefusal) or key in seen:
+                continue
+            seen.add(key)
+            keys.append(key)
+    return tuple(keys)
+
+
+def select_by_net_charge(
+    mol: Chem.Mol, target_charge: int
+) -> str | IonizationRefusal | IdentityRefusal:
+    return choose_ionization(structures_at_net_charge(mol, target_charge))
diff --git a/tests/test_salt_ionization.py b/tests/test_salt_ionization.py
index 754d1a67..8cc93dc5 100644
--- a/tests/test_salt_ionization.py
+++ b/tests/test_salt_ionization.py
@@ -1,14 +1,20 @@
 from rdkit import Chem
 
 from openchem.chem.salt_components import fragment_formal_charge, fragment_key
-from openchem.chem.salt_ionization import SiteTransform, apply_site_transform
+from openchem.chem.salt_ionization import (
+    SiteTransform,
+    apply_site_transform,
+    select_by_net_charge,
+    structures_at_net_charge,
+)
+from openchem.domain.salt_stoichiometry import IonizationRefusal
 
 
 def _acetic() -> Chem.Mol:
     return Chem.MolFromSmiles("CC(=O)O")
 
 
 def test_deprotonating_acetic_acid_updates_hydrogen_and_charge() -> None:
     mol = _acetic()
     oxygen = next(
         atom.GetIdx()
@@ -27,10 +33,35 @@ def test_protonating_pyridine_updates_hydrogen_and_charge() -> None:
     nitrogen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "N")
     result = apply_site_transform(mol, SiteTransform(nitrogen, "protonate"))
     assert fragment_formal_charge(result) == 1
     assert "[nH+]" in fragment_key(result) or "c1cc[nH+]cc1" == fragment_key(result)
 
 
 def test_a_bad_atom_index_is_refused() -> None:
     mol = _acetic()
     refused = apply_site_transform(mol, SiteTransform(99, "deprotonate"))
     assert refused.code == "invalid_site"
+
+
+def test_acetic_acid_at_minus_one_is_acetate() -> None:
+    mol = Chem.MolFromSmiles("CC(=O)O")
+    chosen = select_by_net_charge(mol, -1)
+    assert chosen == fragment_key(Chem.MolFromSmiles("CC(=O)[O-]"))
+
+
+def test_acetic_acid_at_plus_one_is_net_charge_only() -> None:
+    mol = Chem.MolFromSmiles("CC(=O)O")
+    refused = select_by_net_charge(mol, 1)
+    assert isinstance(refused, IonizationRefusal)
+    assert refused.code == "net_charge_only"
+
+
+def test_two_inequivalent_sites_at_the_same_charge_are_not_picked() -> None:
+    # 4-hydroxybenzoic acid: carboxylate vs phenolate at -1 are different graphs.
+    # If RDKit collapses them to one SMILES, identity is graph, not formula â€”
+    # switch the pair to tyrosol (OCCc1ccc(O)cc1).
+    mol = Chem.MolFromSmiles("O=C(O)c1ccc(O)cc1")
+    keys = structures_at_net_charge(mol, -1)
+    assert len(set(keys)) >= 2
+    refused = select_by_net_charge(mol, -1)
+    assert isinstance(refused, IonizationRefusal)
+    assert refused.code == "ambiguous_microspecies"
