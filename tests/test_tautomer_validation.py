"""The preregistered tautomer validation: the criteria file, and the pure comparison.

No ORCA here. What is tested is that the criteria are frozen, closed and
self-consistent, and that the gate decides what it says it decides. The numbers in
the comparison tests are synthetic on purpose: the measured artifact is a later
commit, and nothing in this file may depend on a computed energy.
"""

from __future__ import annotations

import copy
import json

import pytest
from rdkit import Chem

from openchem.chem.tautomer_distribution import (
    HARTREE_TO_KCAL_PER_MOL,
    MODEL_POLICY,
    CandidateResult,
    CandidateStatus,
    build_outcome,
    generate_tautomer_candidates,
    model_version,
)
from openchem.chem.tautomer_validation import (
    SPEC_PATH,
    ExecutionStatus,
    GateOutcome,
    Gates,
    MappingError,
    SystemRun,
    TautomerEnergy,
    ValidationSpecError,
    assert_no_computed,
    build_artifact,
    canonical_key,
    computed_kcal,
    evaluate_gate,
    evaluate_system,
    load_spec,
    map_reference_tautomers,
    parse_spec,
    ranking_checks,
    rebaseline,
    reference_tautomer_energies,
    unreferenced_tautomers,
)

#: The criteria are FROZEN: these are the hashes of the file as preregistered. A
#: change to a tolerance, a reference value, the declared model or the set of
#: systems must be deliberate, which is what makes this test fail until it is
#: updated alongside the criteria version.
FROZEN_CRITERIA_HASH = "b7a86fa494fd760340d86b5b8262a1099e07e39cdf1406bc2d0230b23975d08d"
FROZEN_BENCHMARK_SET_HASH = "8437eec10b19be8ff5334568e08057c996aff1148d72ed0b6ab526981e9c71b3"
FROZEN_REFERENCE_BUNDLE_HASH = "1b89e4f5d1f318cb78b65bff16fc3035b665abf14f3bf259daeaac3238aca8fa"

GATES = Gates(reference_tie_kcal=1.0, mae_tolerance_kcal=1.0, max_error_tolerance_kcal=2.0)


@pytest.fixture(scope="module")
def spec():
    return load_spec()


@pytest.fixture
def raw():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _mutated(raw, edit):
    out = copy.deepcopy(raw)
    edit(out)
    return out


# --- the file is frozen, closed and holds no result ---------------------------------


def test_the_criteria_hashes_are_the_preregistered_ones(spec):
    assert spec.criteria_hash == FROZEN_CRITERIA_HASH
    assert spec.benchmark_set_hash == FROZEN_BENCHMARK_SET_HASH
    assert spec.reference_bundle_hash == FROZEN_REFERENCE_BUNDLE_HASH


def test_the_preregistration_file_contains_no_computed_or_outcome_keys(raw):
    assert_no_computed(raw)


@pytest.mark.parametrize(
    "key", ["computed_energy", "measured_kcal", "gate_outcome", "validation_outcome", "result", "observed_mae"]
)
def test_a_result_smuggled_under_a_result_name_is_refused(raw, key):
    with pytest.raises(ValidationSpecError, match="computed or outcome"):
        assert_no_computed(_mutated(raw, lambda r: r["systems"][0].update({key: 1.0})))


@pytest.mark.parametrize("key", ["energy_kcal", "mae", "score", "value", "orca_hartree"])
def test_a_result_under_any_other_name_is_refused_by_the_closed_schema(raw, key):
    """The name list is not the defence -- a key nobody thought to ban is."""
    for edit in (
        lambda r: r["systems"][0].update({key: 1.0}),
        lambda r: r["systems"][0]["tautomers"][0].update({key: 1.0}),
        lambda r: r["gates"].update({key: 1.0}),
        lambda r: r.update({key: 1.0}),
    ):
        with pytest.raises(ValidationSpecError, match="unknown key"):
            parse_spec(_mutated(raw, edit))


def test_the_required_systems_are_the_ones_decided_in_advance(spec):
    assert [s.id for s in spec.required_systems] == [
        "cytosine", "acetylacetone", "acetaldimine_vinylamine", "pyridone",
    ]
    assert {s.id for s in spec.systems if not s.required} == {
        "formamide_formamidic_acid", "acetaldehyde_vinyl_alcohol",
    }


def test_every_required_row_has_a_doi_a_table_units_a_zero_and_flags(spec):
    for system in spec.required_systems:
        assert system.source["doi"].startswith("10.") and system.source["locator"]
        assert system.reference["units"] == "kcal/mol" and system.reference["zero"]
        assert dict(system.reference["protocol"]) == dict(spec.quantity)
        assert "value_kcal" in system.reference["uncertainty"]


def test_the_declared_model_is_a_real_offered_preset(spec):
    from openchem.chem.orca_engine import METHOD_BASIS_PRESETS

    assert spec.model_under_test["method_basis"] in METHOD_BASIS_PRESETS
    assert spec.model_under_test["charge"] == spec.quantity["charge"] == 0


def test_the_tolerances_are_the_planned_ones(spec):
    assert spec.gates == GATES


def test_a_required_row_without_a_verified_source_is_refused(raw):
    with pytest.raises(ValidationSpecError, match="verified source"):
        parse_spec(_mutated(raw, lambda r: r["systems"][0]["source"].update({"doi": ""})))


@pytest.mark.parametrize(
    ("flag", "value"),
    [("solvent", "water"), ("zpe_included", True), ("thermal_included", True),
     ("vertical", True), ("experimental", True), ("phase", "solution"), ("energy_kind", "free")],
)
def test_a_row_that_is_not_the_declared_quantity_cannot_gate(raw, flag, value):
    """The right number for the wrong physical quantity is still inadmissible."""
    with pytest.raises(ValidationSpecError, match="not the quantity the model computes"):
        parse_spec(_mutated(raw, lambda r: r["systems"][1]["reference"]["protocol"].update({flag: value})))


def test_a_reference_value_must_match_the_sources_own_absolute_energies(raw):
    """A derived column is a checksum: a transcription slip in either is caught."""
    with pytest.raises(ValidationSpecError, match="does not match its own absolutes"):
        parse_spec(_mutated(raw, lambda r: r["systems"][1]["tautomers"][1].update({"reference_kcal": 5.85,
                            "variants": [{"label": "diketo", "reference_kcal": 5.85, "locator": "x"}]})))
    with pytest.raises(ValidationSpecError, match="does not match its own absolutes"):
        parse_spec(_mutated(raw, lambda r: r["systems"][1]["tautomers"][1].update({"absolute_hartree": -345.1})))


def test_a_tautomers_reference_is_its_lowest_variant(raw):
    with pytest.raises(ValidationSpecError, match="lowest variant"):
        parse_spec(_mutated(raw, lambda r: r["systems"][0]["tautomers"][0].update({"reference_kcal": 0.69})))


def test_the_lowest_reference_value_is_the_sources_zero(raw):
    def edit(r):
        for t in r["systems"][0]["tautomers"]:
            t["reference_kcal"] += 1.0
            for v in t["variants"]:
                v["reference_kcal"] += 1.0

    with pytest.raises(ValidationSpecError, match="must be 0.0"):
        parse_spec(_mutated(raw, edit))


def test_two_reference_tautomers_cannot_be_one_constitution(raw):
    def edit(r):
        r["systems"][0]["tautomers"][1]["smiles"] = r["systems"][0]["tautomers"][0]["smiles"]

    with pytest.raises(ValidationSpecError, match="same constitution"):
        parse_spec(_mutated(raw, edit))


def test_the_maximum_error_tolerance_cannot_be_tighter_than_the_mae(raw):
    with pytest.raises(ValidationSpecError, match="cannot be tighter"):
        parse_spec(_mutated(raw, lambda r: r["gates"].update({"max_error_tolerance_kcal": 0.5})))


def test_correcting_one_transcribed_value_yields_a_new_bundle_hash(raw, spec):
    def edit(r):
        r["systems"][0]["tautomers"][1]["reference_kcal"] = 1.45
        r["systems"][0]["tautomers"][1]["variants"][0]["reference_kcal"] = 1.45

    corrected = parse_spec(_mutated(raw, edit))
    assert corrected.reference_bundle_hash != spec.reference_bundle_hash
    assert corrected.benchmark_set_hash == spec.benchmark_set_hash
    assert corrected.criteria_hash == spec.criteria_hash


def test_a_changed_tolerance_changes_the_criteria_hash_only(raw, spec):
    changed = parse_spec(_mutated(raw, lambda r: r["gates"].update({"mae_tolerance_kcal": 1.5})))
    assert changed.criteria_hash != spec.criteria_hash
    assert changed.reference_bundle_hash == spec.reference_bundle_hash


# --- matching a reference tautomer to an enumerated one ------------------------------


def _keys(smiles):
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(smiles))
    return {c.tautomer_fingerprint: canonical_key(c.mol) for c in candidates}


@pytest.mark.parametrize("system_id", [
    "cytosine", "acetylacetone", "acetaldimine_vinylamine", "pyridone",
    "formamide_formamidic_acid", "acetaldehyde_vinyl_alcohol",
])
def test_every_reference_tautomer_is_one_the_application_enumerates(spec, system_id):
    """The real enumerator, not a fixture: a reference tautomer RDKit never
    proposes would make its whole system unrunnable, found here and not mid-run."""
    system = spec.system(system_id)
    mapping = map_reference_tautomers(system, _keys(system.input_smiles))
    assert set(mapping) == {t.id for t in system.tautomers}
    assert all(len(group) >= 1 for group in mapping.values())


def test_the_enumerator_also_proposes_tautomers_the_reference_does_not_list(spec):
    system = spec.system("acetylacetone")
    assert unreferenced_tautomers(system, _keys(system.input_smiles))


def test_an_unmatched_reference_tautomer_is_a_loud_error_not_a_nearest_match(spec):
    system = spec.system("pyridone")
    keys = {fingerprint: key for fingerprint, key in _keys(system.input_smiles).items()
            if key != canonical_key("O=c1cccc[nH]1")}
    with pytest.raises(MappingError, match="pyridone"):
        map_reference_tautomers(system, keys)


def test_the_match_does_not_depend_on_atom_order_or_the_written_form():
    one = canonical_key("Oc1ccccn1")
    assert one == canonical_key("c1ccnc(O)c1") == canonical_key("n1c(O)cccc1")
    mol = Chem.MolFromSmiles("Oc1ccccn1")
    shuffled = Chem.RenumberAtoms(mol, list(reversed(range(mol.GetNumAtoms()))))
    assert canonical_key(shuffled) == one


def test_stereochemistry_never_splits_a_constitution():
    assert canonical_key("C/C=C/C") == canonical_key("C/C=C\\C") == canonical_key("CC=CC")


# --- tautomer-level energies ----------------------------------------------------------


def _result(tautomer, fingerprint, energy, status=CandidateStatus.SUCCEEDED):
    return CandidateResult(
        fingerprint=fingerprint, molblock="", status=status,
        absolute_energy_hartree=energy if status is CandidateStatus.SUCCEEDED else None,
        tautomer_fingerprint=tautomer,
    )


def test_a_tautomer_is_its_lowest_successful_stereo_job():
    outcome = build_outcome([_result("T", "a", -100.0), _result("T", "b", -100.002), _result("U", "c", -99.0)])
    energies = reference_tautomer_energies({"ref_t": ("T",), "ref_u": ("U",)}, outcome)
    assert energies["ref_t"].absolute_hartree == -100.002 and energies["ref_t"].representative_fingerprint == "b"
    assert energies["ref_t"].complete and energies["ref_u"].complete


def test_enumerated_tautomers_of_one_constitution_are_one_reference_tautomer():
    outcome = build_outcome([_result("T1", "a", -100.0), _result("T2", "b", -100.001)])
    energies = reference_tautomer_energies({"ref": ("T1", "T2")}, outcome)
    assert energies["ref"].absolute_hartree == -100.001


def test_a_failed_job_makes_its_reference_tautomer_incomplete_not_silently_the_survivor():
    outcome = build_outcome(
        [_result("T", "a", -100.0), _result("T", "b", 0.0, CandidateStatus.FAILED), _result("U", "c", -99.0)]
    )
    energies = reference_tautomer_energies({"ref_t": ("T",), "ref_u": ("U",)}, outcome)
    assert energies["ref_t"].absolute_hartree == -100.0 and not energies["ref_t"].complete
    assert energies["ref_u"].complete


def test_a_tautomer_with_no_successful_job_has_no_energy():
    outcome = build_outcome([_result("T", "a", 0.0, CandidateStatus.FAILED), _result("U", "c", -99.0)])
    energies = reference_tautomer_energies({"ref_t": ("T",)}, outcome)
    assert energies["ref_t"].absolute_hartree is None and not energies["ref_t"].complete


# --- the comparison -----------------------------------------------------------------------


def test_rebaseline_is_relative_to_the_lowest_of_the_values_given():
    assert rebaseline({"a": 3.0, "b": 1.0, "c": 2.5}) == {"a": 2.0, "b": 0.0, "c": 1.5}


def test_computed_energies_are_rebaselined_to_the_lowest_listed_not_to_anything_else(spec):
    """An enumerated tautomer the reference does not list may be the global
    minimum; it is not passed in, so it cannot become the zero."""
    one_kcal = 1.0 / HARTREE_TO_KCAL_PER_MOL
    relative = computed_kcal({"x": -100.0 + one_kcal, "y": -100.0 + 3 * one_kcal})
    assert relative == pytest.approx({"x": 0.0, "y": 2.0})


def test_a_lower_unlisted_tautomer_does_not_move_the_errors(spec):
    system = spec.system("pyridone")
    base = {"hydroxypyridine": -100.0, "pyridone": -100.0 + 2.07 / HARTREE_TO_KCAL_PER_MOL}
    outcome_with_extra = build_outcome([
        _result("HP", "a", base["hydroxypyridine"]), _result("PY", "b", base["pyridone"]),
        _result("EXTRA", "c", -105.0),
    ])
    energies = reference_tautomer_energies({"hydroxypyridine": ("HP",), "pyridone": ("PY",)}, outcome_with_extra)
    listed = {i: e.absolute_hartree for i, e in energies.items()}
    assert evaluate_system(system, listed, GATES).max_error_kcal == pytest.approx(0.0, abs=1e-9)


def _hartree_for(system, reference_plus):
    """Absolute energies whose rebaselined kcal/mol are the reference plus `reference_plus`."""
    return {t.id: -100.0 + (t.reference_kcal + reference_plus.get(t.id, 0.0)) / HARTREE_TO_KCAL_PER_MOL
            for t in system.tautomers}


def test_a_perfect_model_scores_zero_error_and_passes(spec):
    for system in spec.systems:
        evaluation = evaluate_system(system, _hartree_for(system, {}), GATES)
        assert evaluation.mae_kcal == pytest.approx(0.0, abs=1e-9) and evaluation.passed


def test_one_error_is_taken_per_reference_tautomer_not_per_pair(spec):
    system = spec.system("cytosine")  # three tautomers: three errors, not three pairs of correlated ones
    evaluation = evaluate_system(system, _hartree_for(system, {"keto_amino": 0.6}), GATES)
    assert len(evaluation.errors) == 3
    assert evaluation.max_error_kcal == pytest.approx(0.6)
    assert evaluation.mae_kcal == pytest.approx(0.2)


def test_the_reference_lowest_tautomer_can_carry_an_error_when_the_computed_lowest_differs(spec):
    system = spec.system("pyridone")
    flipped = {"hydroxypyridine": -100.0 + 0.3 / HARTREE_TO_KCAL_PER_MOL, "pyridone": -100.0}
    evaluation = evaluate_system(system, flipped, GATES)
    assert evaluation.errors["hydroxypyridine"][2] == pytest.approx(0.3)
    assert evaluation.errors["pyridone"][2] == pytest.approx(2.07)
    assert not evaluation.ranking_ok


def test_the_mae_and_the_maximum_error_are_both_mandatory(spec):
    system = spec.system("cytosine")
    big_one = evaluate_system(system, _hartree_for(system, {"imino_oxo": 2.5}), GATES)
    assert big_one.mae_kcal < GATES.mae_tolerance_kcal < big_one.max_error_kcal  # MAE alone would pass it
    assert not big_one.quantitative_ok
    many_small = evaluate_system(system, _hartree_for(system, {"keto_amino": 1.4, "imino_oxo": 1.4}), GATES)
    assert many_small.max_error_kcal < GATES.max_error_tolerance_kcal and many_small.mae_kcal < 1.0
    assert evaluate_system(system, _hartree_for(system, {"keto_amino": 1.9, "imino_oxo": 1.9}), GATES).mae_kcal > 1.0


def test_an_error_exactly_at_a_tolerance_passes(spec):
    system = spec.system("acetaldimine_vinylamine")
    at_limit = evaluate_system(system, _hartree_for(system, {"vinylamine": 2.0}), GATES)
    assert at_limit.max_error_kcal == pytest.approx(2.0) and at_limit.quantitative_ok


# --- the ranking gate: pairwise and tie-aware -----------------------------------------------


def test_a_pair_the_reference_does_not_separate_asks_for_no_order():
    reference = {"a": 0.0, "b": 0.5}
    for computed in ({"a": 0.0, "b": 0.5}, {"a": 0.5, "b": 0.0}):
        (check,) = ranking_checks(reference, computed, 1.0)
        assert check.tied and check.ok


def test_a_tie_is_strict_so_a_gap_of_exactly_the_window_is_ordered():
    (check,) = ranking_checks({"a": 0.0, "b": 1.0}, {"a": 1.0, "b": 0.0}, 1.0)
    assert not check.tied and not check.ok


def test_the_reference_is_a_set_of_pairwise_constraints_not_a_total_order():
    """A~B, B~C, A<C is legal: forcing a total order would reject a correct
    model for a distinction the reference itself does not make."""
    reference = {"a": 0.0, "b": 0.8, "c": 1.6}
    computed = {"a": 0.0, "b": -0.2, "c": 1.6}  # b below a, which the 0.8 reference gap leaves free
    checks = {(c.a, c.b): c for c in ranking_checks(reference, computed, 1.0)}
    assert checks[("a", "b")].tied and checks[("b", "c")].tied
    assert not checks[("a", "c")].tied and checks[("a", "c")].ok


def test_a_pair_the_reference_separates_must_be_ordered_the_same_way():
    reference, computed = {"a": 0.0, "b": 3.0}, {"a": 4.0, "b": 0.0}
    (check,) = ranking_checks(reference, computed, 1.0)
    assert not check.ok and check.reference_gap_kcal < 0 < check.computed_gap_kcal


def test_a_computed_gap_of_exactly_zero_orders_nothing_so_it_fails_a_separated_pair():
    (check,) = ranking_checks({"a": 0.0, "b": 3.0}, {"a": 1.0, "b": 1.0}, 1.0)
    assert not check.ok


# --- the gate ---------------------------------------------------------------------------------


def _all(spec, plus=None, only_required=False):
    plus = plus or {}
    return {
        s.id: _hartree_for(s, plus.get(s.id, {})) for s in spec.systems if s.required or not only_required
    }


def test_every_required_system_passing_passes_the_gate(spec):
    result = evaluate_gate(spec, _all(spec), execution_complete=True)
    assert result.outcome is GateOutcome.PASSED and result.execution is ExecutionStatus.COMPLETE
    assert result.pooled_mae_kcal == pytest.approx(0.0, abs=1e-9)


def test_right_orderings_with_a_missed_tolerance_is_ranking_only(spec):
    # keto_amino is 1.44 above the zero; moving it 2.5 up keeps every separated pair in order
    result = evaluate_gate(spec, _all(spec, {"cytosine": {"keto_amino": 2.5}}), execution_complete=True)
    assert result.outcome is GateOutcome.RANKING_ONLY


def test_a_wrong_ordering_in_one_required_system_is_attempted_failed(spec):
    flipped = {"pyridone": {"hydroxypyridine": 3.0}}  # 2-pyridone now below the hydroxypyridine
    assert evaluate_gate(spec, _all(spec, flipped), execution_complete=True).outcome is GateOutcome.ATTEMPTED_FAILED


def test_there_is_no_compensation_between_systems(spec):
    """One system badly wrong and the rest perfect: a pooled MAE would pass it."""
    result = evaluate_gate(spec, _all(spec, {"cytosine": {"imino_oxo": 2.4}}), execution_complete=True)
    assert result.pooled_mae_kcal < GATES.mae_tolerance_kcal
    assert result.outcome is GateOutcome.RANKING_ONLY


def test_an_optional_system_failing_never_decides_the_gate(spec):
    plus = {"formamide_formamidic_acid": {"formamide": 30.0}, "acetaldehyde_vinyl_alcohol": {"acetaldehyde": 30.0}}
    result = evaluate_gate(spec, _all(spec, plus), execution_complete=True)
    assert result.outcome is GateOutcome.PASSED
    assert {e.system_id for e in result.systems if not e.passed} == set(plus)


def test_an_incomplete_execution_is_not_evaluable_whatever_the_numbers_say(spec):
    result = evaluate_gate(spec, _all(spec), execution_complete=False)
    assert result.outcome is GateOutcome.NOT_EVALUABLE and result.execution is ExecutionStatus.INCOMPLETE


def test_a_required_system_with_no_energies_is_not_evaluable(spec):
    energies = _all(spec, only_required=True)
    del energies["cytosine"]
    assert evaluate_gate(spec, energies, execution_complete=True).outcome is GateOutcome.NOT_EVALUABLE


# --- the artifact ---------------------------------------------------------------------------------


def _run(spec, system, plus=None, complete=True, mapping_error=""):
    energies = {
        t.id: TautomerEnergy(t.id, hartree, f"fp-{t.id}", complete)
        for t, hartree in zip(system.tautomers, _hartree_for(system, plus or {}).values(), strict=True)
    }
    return SystemRun(system.id, mapping_error, energies, ["extra"], [{"fingerprint": "x", "status": "succeeded"}])


def _artifact(spec, runs):
    return build_artifact(
        spec, runs,
        model_version=model_version(spec.model_under_test["method_basis"], "ETKDGv3", 298.15),
        model_policy=MODEL_POLICY.canonical(), source_commit="abc123", orca_version="6.1.1", rdkit_version="x",
    )


def test_the_artifact_carries_identity_and_both_status_fields(spec):
    artifact = _artifact(spec, [_run(spec, s) for s in spec.systems])
    identity = artifact["identity"]
    assert identity["criteria_hash"] == FROZEN_CRITERIA_HASH
    assert identity["reference_bundle_hash"] == FROZEN_REFERENCE_BUNDLE_HASH
    assert identity["model_version"].startswith("tautomer-boltzmann-v") and "PBE0 def2-TZVP" in identity["model_version"]
    assert artifact["validation_execution_status"] == "complete"
    assert artifact["validation_gate_outcome"] == "passed"


def test_every_compared_value_carries_its_reference_and_its_source(spec):
    artifact = _artifact(spec, [_run(spec, s) for s in spec.systems])
    row = next(s for s in artifact["systems"] if s["id"] == "acetylacetone")["tautomers"][1]
    assert {"reference_kcal", "computed_kcal", "error_kcal", "absolute_hartree", "reference_source",
            "reference_locator", "reference_units", "reference_zero"} <= set(row)


def test_an_incomplete_system_makes_the_whole_artifact_incomplete_and_not_evaluable(spec):
    runs = [_run(spec, s, complete=s.id != "cytosine") for s in spec.systems]
    artifact = _artifact(spec, runs)
    assert artifact["validation_execution_status"] == "incomplete"
    assert artifact["validation_gate_outcome"] == "not_evaluable"
    assert next(s for s in artifact["systems"] if s["id"] == "cytosine")["execution"] == "incomplete"


def test_a_mapping_error_is_recorded_and_makes_the_run_incomplete(spec):
    runs = [_run(spec, s, mapping_error="nothing matched" if s.id == "pyridone" else "") for s in spec.systems]
    artifact = _artifact(spec, runs)
    assert artifact["validation_gate_outcome"] == "not_evaluable"
    assert next(s for s in artifact["systems"] if s["id"] == "pyridone")["mapping_error"] == "nothing matched"


def test_a_required_system_never_run_is_not_evaluable(spec):
    artifact = _artifact(spec, [_run(spec, s) for s in spec.systems if s.id != "acetylacetone"])
    assert artifact["validation_gate_outcome"] == "not_evaluable"


def test_the_artifact_is_plain_json(spec):
    artifact = _artifact(spec, [_run(spec, s) for s in spec.systems])
    assert json.loads(json.dumps(artifact)) == artifact
