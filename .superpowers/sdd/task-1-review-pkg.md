# Review package 24775f03..5c7616e6

## log
5c7616e6 Refuse a salt ionization that is only a net charge or several microspecies.

## stat
 src/openchem/domain/salt_stoichiometry.py | 23 +++++++++++++++++++++++
 tests/test_salt_stoichiometry.py          | 17 +++++++++++++++++
 2 files changed, 40 insertions(+)

## diff
diff --git a/src/openchem/domain/salt_stoichiometry.py b/src/openchem/domain/salt_stoichiometry.py
index 52631e6c..af400120 100644
--- a/src/openchem/domain/salt_stoichiometry.py
+++ b/src/openchem/domain/salt_stoichiometry.py
@@ -125,20 +125,26 @@ class TwoIonBalance:
     cation_count: int
     anion_count: int
 
 
 @dataclass(frozen=True)
 class BalanceRefusal:
     code: str
     reason: str
 
 
+@dataclass(frozen=True)
+class IonizationRefusal:
+    code: str
+    reason: str
+
+
 def balance_two(
     cation: ChargedSpecies, anion: ChargedSpecies
 ) -> TwoIonBalance | BalanceRefusal:
     if cation.charge <= 0 or anion.charge >= 0:
         return BalanceRefusal(
             code="not_opposite_signs",
             reason=(
                 "A binary salt needs one positive charge and one negative "
                 f"charge; got {cation.charge:+d} and {anion.charge:+d}."
             ),
@@ -157,10 +163,27 @@ def formula_unit_conserved(
     def _total(parts: Sequence[tuple[Mapping[str, int], int]]) -> dict[str, int]:
         out: dict[str, int] = {}
         for counts, n in parts:
             if n <= 0:
                 return {"__invalid__": 1}
             for element, count in counts.items():
                 out[element] = out.get(element, 0) + n * count
         return out
 
     return _total(left) == _total(right)
+
+
+#: Pick among fully specified ionic structures. An empty list is a net-charge
+#: request with no structure; several distinct graphs at one charge are not ranked.
+def choose_ionization(candidates: Sequence[str]) -> str | IonizationRefusal:
+    unique = list(dict.fromkeys(candidates))
+    if not unique:
+        return IonizationRefusal(
+            code="net_charge_only",
+            reason="A net charge is not an ionization state; name a structure.",
+        )
+    if len(unique) > 1:
+        return IonizationRefusal(
+            code="ambiguous_microspecies",
+            reason="Several structures share this charge; v1 does not pick one.",
+        )
+    return unique[0]
diff --git a/tests/test_salt_stoichiometry.py b/tests/test_salt_stoichiometry.py
index b30ab78d..49ece98e 100644
--- a/tests/test_salt_stoichiometry.py
+++ b/tests/test_salt_stoichiometry.py
@@ -6,25 +6,27 @@ Contract: docs/SALT_COMPOSITION_DESIGN.md. The solver never sees a molecule.
 from pathlib import Path
 
 import pytest
 
 from openchem.domain.salt_stoichiometry import (
     KIND_ION,
     KIND_METAL_HYDROXIDE,
     KIND_MOLECULAR_NEUTRAL,
     BalanceRefusal,
     ChargedSpecies,
+    IonizationRefusal,
     ModeAComposition,
     ModeARefusal,
     ModeASpecies,
     TwoIonBalance,
     balance_two,
+    choose_ionization,
     compose_mode_a,
     formula_unit_conserved,
 )
 
 
 def _species(identity: str, charge: int, kind: str, counts: dict[str, int]) -> ModeASpecies:
     return ModeASpecies(
         identity=identity,
         charge=charge,
         kind=kind,
@@ -161,16 +163,31 @@ def test_neutral_base_plus_sulfate_without_a_proton_source_is_refused() -> None:
     result = compose_mode_a(
         _species("B", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
         _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
         _species("BH+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
         _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
     )
     assert isinstance(result, ModeARefusal)
     assert result.code == "missing_proton_source"
 
 
+def test_one_structure_at_the_requested_state_is_accepted() -> None:
+    assert choose_ionization(["CC(=O)[O-]"]) == "CC(=O)[O-]"
+
+
+def test_a_net_charge_with_no_structure_is_refused() -> None:
+    refused = choose_ionization([])
+    assert refused.code == "net_charge_only"
+
+
+def test_two_structures_at_the_same_charge_are_not_auto_picked() -> None:
+    refused = choose_ionization(["CC(=O)[O-]", "[O-]C=O"])
+    assert refused.code == "ambiguous_microspecies"
+    assert isinstance(refused, IonizationRefusal)
+
+
 def test_the_domain_module_does_not_import_lattice_energy() -> None:
     text = Path("src/openchem/domain/salt_stoichiometry.py").read_text(
         encoding="utf-8"
     )
     assert "lattice_energy" not in text
     assert "rdkit" not in text.lower()
