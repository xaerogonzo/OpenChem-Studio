# Review package 55011326..fed14181

## log
fed14181 Count bonded hydrogens when ionizing a site.

## stat
 .../202611111916-salt-composition-slice-3-3717.md  |  3 ++
 docs/SALT_COMPOSITION_DESIGN.md                    |  3 +-
 src/openchem/chem/salt_ionization.py               | 52 +++++++++++++++++++---
 tests/test_salt_ionization.py                      | 28 ++++++++++++
 4 files changed, 79 insertions(+), 7 deletions(-)

## diff
diff --git a/changelog.d/202611111916-salt-composition-slice-3-3717.md b/changelog.d/202611111916-salt-composition-slice-3-3717.md
index 8942265a..257e8c55 100644
--- a/changelog.d/202611111916-salt-composition-slice-3-3717.md
+++ b/changelog.d/202611111916-salt-composition-slice-3-3717.md
@@ -1,6 +1,9 @@
 ### Salt composition, slice 3 (library, no UI)
 
 - Fully specified ionization (site transforms; net charge alone refused;
   several microspecies at one charge listed, not picked), two supplied ions
   as given, a small cited ion catalog, and `pka_compatible` as named-step
   evidence that never feeds `balance_two`. Still no panel and not a crystal.
+- Site ionization counts a bonded hydrogen atom. `GetTotalNumHs()` does not,
+  so an `AddHs` acetic acid refused deprotonation and a protonation could
+  stack an explicit-H property on the real hydrogen.
diff --git a/docs/SALT_COMPOSITION_DESIGN.md b/docs/SALT_COMPOSITION_DESIGN.md
index 172d96ea..94aaa536 100644
--- a/docs/SALT_COMPOSITION_DESIGN.md
+++ b/docs/SALT_COMPOSITION_DESIGN.md
@@ -412,21 +412,22 @@ ratio is calculated (the ratio is a separate fact).
 balanced; `[Na+].[O-]` is not sulfate (identity â‰  formula guess).
 
 **Structure.** Same formula and charge, **different constitution** (must not
 collapse); stereo; isotopes; explicit hydrogen; atom maps stripped from
 identity; no tautomer/resonance merge; permanent charge (quaternary
 ammonium, no protonation required); unsanitizable structures refuse;
 implicit-H formulas still distinguish graphs.
 
 **Ionization selection.** Net charge only is refused or listed as candidates;
 two microspecies at the same charge are not auto-picked; site-specific
-selection is accepted.
+selection is accepted. Net-charge listing tries N, O, P and S sites only, so
+a carbon deprotonation of acetic acid is not treated as a competing microspecies.
 
 **Acid-base / Mode A.** Monoprotic; diprotic first vs second deprotonation
 (hydrogen sulfate vs sulfate); triprotic with partial deprotonation; one
 basic site; several basic sites (do not assume max protonation); polybasic
 second protonation assessed with the **matching** conjugate-acid pKa, not the
 first; `B + 2 HA â†’ BH2^2+ + 2 Aâˆ’` multiplicity-weighted conservation;
 user-selected **structure** with pKa unused; pKa missing or incomparable;
 **neutral base + supplied sulfate** without a proton source is refused, not
 auto-protonated; **NaOH + HA** is out of v1 (not two-neutral proton transfer).
 
diff --git a/src/openchem/chem/salt_ionization.py b/src/openchem/chem/salt_ionization.py
index 991aaec5..3dcf2328 100644
--- a/src/openchem/chem/salt_ionization.py
+++ b/src/openchem/chem/salt_ionization.py
@@ -19,48 +19,83 @@ REACHED_BY = (
     "on the window yet"
 )
 
 
 @dataclass(frozen=True)
 class SiteTransform:
     atom_index: int
     direction: str
 
 
+def _bonded_hydrogen_indexes(atom: Chem.Atom) -> list[int]:
+    """Hydrogen *atoms* bonded to ``atom``. ``GetTotalNumHs()`` does not count these."""
+    return [neighbor.GetIdx() for neighbor in atom.GetNeighbors() if neighbor.GetAtomicNum() == 1]
+
+
 def apply_site_transform(mol: Chem.Mol, transform: SiteTransform) -> Chem.Mol | IdentityRefusal:
     if transform.direction not in {"protonate", "deprotonate"}:
         return IdentityRefusal(code="invalid_site", reason="direction must be protonate or deprotonate.")
     if transform.atom_index < 0 or transform.atom_index >= mol.GetNumAtoms():
         return IdentityRefusal(code="invalid_site", reason="atom index is not in the parent.")
-    copy = Chem.Mol(mol)
-    atom = copy.GetAtomWithIdx(transform.atom_index)
+    editable = Chem.RWMol(mol)
+    atom = editable.GetAtomWithIdx(transform.atom_index)
+    bonded = _bonded_hydrogen_indexes(atom)
     if transform.direction == "protonate":
-        atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
-        atom.SetFormalCharge(atom.GetFormalCharge() + 1)
-        atom.SetNoImplicit(True)
+        # A bonded hydrogen is invisible to GetTotalNumHs(). Setting an
+        # explicit-H property on top of it would count that hydrogen twice.
+        if bonded:
+            hydrogen = Chem.Atom(1)
+            hydrogen_index = editable.AddAtom(hydrogen)
+            editable.AddBond(transform.atom_index, hydrogen_index, Chem.BondType.SINGLE)
+            atom.SetFormalCharge(atom.GetFormalCharge() + 1)
+            atom.SetNoImplicit(True)
+        else:
+            atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
+            atom.SetFormalCharge(atom.GetFormalCharge() + 1)
+            atom.SetNoImplicit(True)
+    elif bonded:
+        # Delete one real hydrogen. An index above it moves down.
+        hydrogen_index = max(bonded)
+        editable.RemoveAtom(hydrogen_index)
+        site_index = transform.atom_index - (1 if hydrogen_index < transform.atom_index else 0)
+        site = editable.GetAtomWithIdx(site_index)
+        site.SetFormalCharge(site.GetFormalCharge() - 1)
+        site.SetNoImplicit(True)
     else:
         total = atom.GetTotalNumHs()
         if total < 1:
             return IdentityRefusal(code="invalid_site", reason="that atom has no hydrogen to remove.")
         atom.SetNumExplicitHs(total - 1)
         atom.SetFormalCharge(atom.GetFormalCharge() - 1)
         atom.SetNoImplicit(True)
+    copy = editable.GetMol()
     try:
         Chem.SanitizeMol(copy)
+        # Spectator hydrogen atoms would keep an AddHs parent from sharing
+        # the implicit-H fragment key (acetate is CC(=O)[O-]).
+        copy = Chem.RemoveHs(copy)
     except (ValueError, RuntimeError):
         return IdentityRefusal(code="unsanitizable", reason="the ionized structure could not be sanitized.")
     return copy
 
 
 def ionize_at_sites(
     mol: Chem.Mol, transforms: Sequence[SiteTransform]
 ) -> str | IdentityRefusal | IonizationRefusal:
+    """Apply each transform to the molecule the previous one returned.
+
+    Atom indexes are positions on that updated molecule. Deprotonation deletes
+    a bonded hydrogen when one is present, and the result then drops remaining
+    explicit hydrogen atoms, so every later index has to be read from the
+    updated mol. An index taken from the parent is only still valid when no
+    earlier transform removed an atom below it.
+    """
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
@@ -75,31 +110,36 @@ def ionize_at_sites(
 _ACID_ELEMENTS = frozenset({7, 8, 15, 16})  # N, O, P, S
 _BASE_ELEMENTS = frozenset({7, 15})  # N, P
 
 
 def _enumeration_directions(atom: Chem.Atom) -> tuple[str, ...]:
     charge = atom.GetFormalCharge()
     number = atom.GetAtomicNum()
     directions: list[str] = []
     if number in _BASE_ELEMENTS or charge < 0:
         directions.append("protonate")
-    if atom.GetTotalNumHs() >= 1 and (number in _ACID_ELEMENTS or charge > 0):
+    # includeNeighbors counts a real hydrogen atom. GetTotalNumHs() alone
+    # reports 0 after AddHs, so an explicit-H acid would never be offered.
+    if atom.GetTotalNumHs(includeNeighbors=True) >= 1 and (number in _ACID_ELEMENTS or charge > 0):
         directions.append("deprotonate")
     return tuple(directions)
 
 
 def structures_at_net_charge(mol: Chem.Mol, target_charge: int) -> tuple[str, ...]:
     """Distinct fragment_key values from one protonate or deprotonate that match target_charge.
 
     Order is atom index, then protonate before deprotonate. Identity refusals
     are skipped. Keys are not ranked and are not tautomer-canonicalized:
     ``choose_ionization`` decides whether one graph is unique.
+
+    Listing tries N, O, P and S only, so a carbon deprotonation of acetic acid
+    is not a competing microspecies.
     """
     keys: list[str] = []
     seen: set[str] = set()
     for atom in mol.GetAtoms():
         if atom.GetAtomicNum() <= 1:
             continue
         for direction in _enumeration_directions(atom):
             result = apply_site_transform(mol, SiteTransform(atom.GetIdx(), direction))
             if isinstance(result, IdentityRefusal):
                 continue
diff --git a/tests/test_salt_ionization.py b/tests/test_salt_ionization.py
index 8cc93dc5..646e3134 100644
--- a/tests/test_salt_ionization.py
+++ b/tests/test_salt_ionization.py
@@ -7,20 +7,48 @@ from openchem.chem.salt_ionization import (
     select_by_net_charge,
     structures_at_net_charge,
 )
 from openchem.domain.salt_stoichiometry import IonizationRefusal
 
 
 def _acetic() -> Chem.Mol:
     return Chem.MolFromSmiles("CC(=O)O")
 
 
+def test_deprotonating_explicit_hydrogen_acetic_acid_removes_the_bonded_hydrogen() -> None:
+    parent = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
+    oxygen = next(
+        atom.GetIdx()
+        for atom in parent.GetAtoms()
+        if atom.GetSymbol() == "O" and any(neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors())
+    )
+    parent_smiles = Chem.MolToSmiles(parent)
+    result = apply_site_transform(parent, SiteTransform(oxygen, "deprotonate"))
+    assert fragment_formal_charge(result) == -1
+    assert fragment_key(result) == "CC(=O)[O-]"
+    assert Chem.MolToSmiles(parent) == parent_smiles
+
+
+def test_protonating_explicit_hydrogen_oxygen_does_not_stack_a_hydrogen_property() -> None:
+    parent = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
+    oxygen = next(
+        atom.GetIdx()
+        for atom in parent.GetAtoms()
+        if atom.GetSymbol() == "O" and any(neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors())
+    )
+    parent_smiles = Chem.MolToSmiles(parent)
+    result = apply_site_transform(parent, SiteTransform(oxygen, "protonate"))
+    assert fragment_formal_charge(result) == 1
+    assert fragment_key(result) == "CC(=O)[OH2+]"
+    assert Chem.MolToSmiles(parent) == parent_smiles
+
+
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
