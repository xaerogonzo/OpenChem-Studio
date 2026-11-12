# Review package 000fddc9..abb7d6c1

## log
abb7d6c1 Compose two supplied ions as given, without inventing protons or a pKa.

## stat
 src/openchem/domain/salt_stoichiometry.py | 25 +++++++++++++++++++++++++
 tests/test_salt_evidence.py               | 11 +++++++++++
 tests/test_salt_stoichiometry.py          | 19 +++++++++++++++++++
 3 files changed, 55 insertions(+)

## diff
diff --git a/src/openchem/domain/salt_stoichiometry.py b/src/openchem/domain/salt_stoichiometry.py
index af400120..a2635bae 100644
--- a/src/openchem/domain/salt_stoichiometry.py
+++ b/src/openchem/domain/salt_stoichiometry.py
@@ -105,20 +105,45 @@ def compose_mode_a(
                 "do not match the product ions."
             ),
         )
     return ModeAComposition(
         cation_count=balanced.cation_count,
         anion_count=balanced.anion_count,
         charge_valid=True,
     )
 
 
+def compose_supplied_ions(
+    cation: ModeASpecies,
+    anion: ModeASpecies,
+) -> ModeAComposition | ModeARefusal:
+    if cation.kind != KIND_ION or anion.kind != KIND_ION:
+        return ModeARefusal(
+            code="missing_proton_source",
+            reason=(
+                "A molecular neutral plus a supplied ion does not provide "
+                "the protons for a transfer; supply both ions as given."
+            ),
+        )
+    balanced = balance_two(
+        ChargedSpecies(cation.identity, cation.charge),
+        ChargedSpecies(anion.identity, anion.charge),
+    )
+    if isinstance(balanced, BalanceRefusal):
+        return ModeARefusal(code=balanced.code, reason=balanced.reason)
+    return ModeAComposition(
+        cation_count=balanced.cation_count,
+        anion_count=balanced.anion_count,
+        charge_valid=True,
+    )
+
+
 @dataclass(frozen=True)
 class ChargedSpecies:
     """One ion, as the stoichiometry layer is allowed to see it."""
 
     identity: str
     charge: int
 
 
 @dataclass(frozen=True)
 class TwoIonBalance:
diff --git a/tests/test_salt_evidence.py b/tests/test_salt_evidence.py
index baaffd83..913d2849 100644
--- a/tests/test_salt_evidence.py
+++ b/tests/test_salt_evidence.py
@@ -13,20 +13,31 @@ from openchem.domain.salt_evidence import (
 
 
 def _acetic() -> PkaValue:
     return PkaValue(4.76, ORIGIN_MEASURED, "water", 298.15, None, None, "acetic_acid_h1")
 
 
 def _pyridinium() -> PkaValue:
     return PkaValue(5.23, ORIGIN_MEASURED, "water", 298.15, None, None, "pyridine_bh1")
 
 
+def test_supplied_ions_do_not_assess_pka() -> None:
+    result = assess_pka_compatible(
+        already_charged=True,
+        proposed_acid_step_id="x",
+        proposed_conjugate_acid_step_id="y",
+        acid=None,
+        conjugate_acid=None,
+    )
+    assert result.verdict == VERDICT_NOT_ASSESSED
+
+
 def test_already_charged_input_is_not_assessed() -> None:
     result = assess_pka_compatible(
         already_charged=True,
         proposed_acid_step_id="acetic_acid_h1",
         proposed_conjugate_acid_step_id="pyridine_bh1",
         acid=_acetic(),
         conjugate_acid=_pyridinium(),
     )
     assert result.verdict == VERDICT_NOT_ASSESSED
     assert result.delta is None
diff --git a/tests/test_salt_stoichiometry.py b/tests/test_salt_stoichiometry.py
index 49ece98e..f588eb6f 100644
--- a/tests/test_salt_stoichiometry.py
+++ b/tests/test_salt_stoichiometry.py
@@ -14,20 +14,21 @@ from openchem.domain.salt_stoichiometry import (
     BalanceRefusal,
     ChargedSpecies,
     IonizationRefusal,
     ModeAComposition,
     ModeARefusal,
     ModeASpecies,
     TwoIonBalance,
     balance_two,
     choose_ionization,
     compose_mode_a,
+    compose_supplied_ions,
     formula_unit_conserved,
 )
 
 
 def _species(identity: str, charge: int, kind: str, counts: dict[str, int]) -> ModeASpecies:
     return ModeASpecies(
         identity=identity,
         charge=charge,
         kind=kind,
         element_counts=tuple(sorted(counts.items())),
@@ -152,20 +153,38 @@ def test_broken_hydrogen_count_is_not_a_composition() -> None:
     result = compose_mode_a(
         _species("EtNH2", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
         _species("AcOH", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 4, "O": 2}),
         _species("wrong", 1, KIND_ION, {"C": 2, "H": 9, "N": 1}),
         _species("AcO-", -1, KIND_ION, {"C": 2, "H": 3, "O": 2}),
     )
     assert isinstance(result, ModeARefusal)
     assert result.code == "conservation_failed"
 
 
+def test_sodium_and_acetate_as_given_ions_balance_one_to_one() -> None:
+    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
+    acetate = ModeASpecies("CC(=O)[O-]", -1, KIND_ION, (("C", 2), ("H", 3), ("O", 2)))
+    result = compose_supplied_ions(sodium, acetate)
+    assert isinstance(result, ModeAComposition)
+    assert result.cation_count == 1
+    assert result.anion_count == 1
+    assert result.charge_valid is True
+
+
+def test_a_neutral_passed_to_supplied_ions_is_refused() -> None:
+    acetic = ModeASpecies("CC(=O)O", 0, KIND_MOLECULAR_NEUTRAL, (("C", 2), ("H", 4), ("O", 2)))
+    sodium = ModeASpecies("[Na+]", 1, KIND_ION, (("Na", 1),))
+    refused = compose_supplied_ions(sodium, acetic)
+    assert isinstance(refused, ModeARefusal)
+    assert refused.code == "missing_proton_source"
+
+
 def test_neutral_base_plus_sulfate_without_a_proton_source_is_refused() -> None:
     result = compose_mode_a(
         _species("B", 0, KIND_MOLECULAR_NEUTRAL, {"C": 2, "H": 7, "N": 1}),
         _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
         _species("BH+", 1, KIND_ION, {"C": 2, "H": 8, "N": 1}),
         _species("SO4", -2, KIND_ION, {"O": 4, "S": 1}),
     )
     assert isinstance(result, ModeARefusal)
     assert result.code == "missing_proton_source"
 
