"""The leakage rule and the row schema, on synthetic rows.

Nothing here is chemistry data: the molecules are ordinary ones chosen so that each test isolates one rule.
What is guarded is that leakage is judged on chemical identity, per model and per property, that an unknown
population is an error rather than "clean", and that a row without a reference state stays out of the common set.

The second half guards the amendment for the melting- and boiling-point benchmark (`benchmarks/mp_bp/`): the
complete event vocabulary and an admission decision for every (target, event) pair, a normal-boiling-point
admission that checks the pressure, a record type that has no value for "there was no clean event", ranges
scored as intervals, a deterministic entity-level split, and unknown leakage carried as a status that can
never clear a held-out claim. **The one existing test changed by the amendment** is the vocabulary test above,
whose example of an invalid event was `"boiling"`; that is a real event now, so the example is `"freezing"`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def vr():
    spec = importlib.util.spec_from_file_location("validation_rows", ROOT / "tools" / "validation_rows.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # a dataclass looks its module up here
    spec.loader.exec_module(module)
    return module


def _row(vr, row_id, smiles, prop="tb", **kw):
    base = dict(value=1.0, units="K", source_id="synthetic", record_id=row_id, partition="holdout",
                temperature_k=298.15, phase="solid")
    base.update(kw)
    return vr.ValidationRow(row_id=row_id, smiles=smiles, property=prop, **base)


def test_two_spellings_of_one_molecule_have_one_identity(vr):
    assert vr.identity_block("C1=CC=CC=C1") == vr.identity_block("c1ccccc1")


def test_a_different_molecule_has_a_different_identity(vr):
    assert vr.identity_block("c1ccccc1") != vr.identity_block("Cc1ccccc1")


def test_two_enantiomers_share_an_identity_and_that_errs_toward_excluding(vr):
    """The first InChIKey block ignores stereo. That merges genuinely different stereoisomers, which can only
    over-exclude, never leak."""
    assert vr.identity_block("C[C@H](N)C(=O)O") == vr.identity_block("C[C@@H](N)C(=O)O")


def test_an_unreadable_string_raises_rather_than_sharing_a_placeholder(vr):
    with pytest.raises(ValueError, match="cannot read"):
        vr.identity_block("not a molecule")


def test_a_row_in_the_fit_population_is_excluded_however_it_is_spelled(vr):
    populations = {("m", "tb"): vr.population_blocks(["c1ccccc1"])}
    rows = [_row(vr, "benzene-kekule", "C1=CC=CC=C1"), _row(vr, "toluene", "Cc1ccccc1")]

    kept, excluded = vr.exclude_leaked(rows, "m", populations)

    assert [r.row_id for r in excluded] == ["benzene-kekule"]
    assert [r.row_id for r in kept] == ["toluene"]


def test_leakage_is_per_property(vr):
    """Benzene is in the model's Tb fit but not its Tc fit, so it is honest Tc validation data."""
    populations = {
        ("m", "tb"): vr.population_blocks(["c1ccccc1"]),
        ("m", "tc"): vr.population_blocks(["Cc1ccccc1"]),
    }
    rows = [_row(vr, "b-tb", "c1ccccc1", prop="tb"), _row(vr, "b-tc", "c1ccccc1", prop="tc")]

    kept, excluded = vr.exclude_leaked(rows, "m", populations)

    assert [r.row_id for r in excluded] == ["b-tb"] and [r.row_id for r in kept] == ["b-tc"]


def test_leakage_is_per_model(vr):
    populations = {("a", "tb"): vr.population_blocks(["c1ccccc1"]), ("b", "tb"): vr.population_blocks(["CCO"])}
    rows = [_row(vr, "benzene", "c1ccccc1")]
    assert vr.exclude_leaked(rows, "a", populations)[1] and not vr.exclude_leaked(rows, "b", populations)[1]


def test_an_unrecorded_population_is_an_error_not_no_leakage(vr):
    """The general Cp population in Burkhardt 2026 cannot be enumerated from its SI: unknown must not read as clean."""
    with pytest.raises(vr.UnknownFitPopulation, match="unknown"):
        vr.exclude_leaked([_row(vr, "r", "CCO", prop="cp")], "m", {("m", "tb"): frozenset()})


@pytest.mark.parametrize(
    ("kw", "phrase"),
    [({"temperature_k": None}, "reference temperature"), ({"phase": None}, "reference phase")],
)
def test_a_row_without_a_reference_state_stays_out_of_the_common_set(vr, kw, phrase):
    assert phrase in vr.admit_to_common_set(_row(vr, "r", "CCO", **kw))


def test_a_complete_row_may_enter(vr):
    assert vr.admit_to_common_set(_row(vr, "r", "CCO")) is None


def test_a_partition_and_a_phase_outside_the_vocabulary_are_refused(vr):
    with pytest.raises(ValueError, match="partition"):
        _row(vr, "r", "CCO", partition="test")
    with pytest.raises(ValueError, match="phase"):
        _row(vr, "r", "CCO", phase="plasma")


def test_there_are_three_partitions_never_two(vr):
    """Development, selection and holdout are different uses of data."""
    assert vr.PARTITIONS == {"development", "selection", "holdout"}


def test_a_transition_type_and_value_source_outside_the_vocabulary_are_refused(vr):
    with pytest.raises(ValueError, match="transition_type"):
        _row(vr, "r", "CCO", prop="tm", transition_type="freezing")
    with pytest.raises(ValueError, match="value_source"):
        _row(vr, "r", "CCO", prop="tm", value_source="tertiary")


def test_a_decomposition_row_never_enters_the_melting_point_set(vr):
    """The whole reason `transition_type` exists: an energetic material's reported thermal event can be
    a melting point OR a decomposition temperature, and scoring a Tm predictor against the wrong one
    silently compares different physical quantities."""
    row = _row(vr, "r", "CCO", prop="tm", transition_type="decomposition")
    assert "decomposition" in vr.admit_to_melting_point_set(row)


def test_an_untyped_row_never_enters_the_melting_point_set_either(vr):
    row = _row(vr, "r", "CCO", prop="tm")
    assert "no transition_type" in vr.admit_to_melting_point_set(row)


def test_a_clean_melting_row_may_enter(vr):
    row = _row(vr, "r", "CCO", prop="tm", transition_type="melting")
    assert vr.admit_to_melting_point_set(row) is None


def test_melting_with_decomposition_and_not_observed_also_stay_out(vr):
    for t in ("melting_with_decomposition", "not_observed"):
        row = _row(vr, "r", "CCO", prop="tm", transition_type=t)
        assert vr.admit_to_melting_point_set(row) is not None


# ---------------------------------------------------------------------------------------------------------
# the amendment: events, targets, pressure, no-event records, ranges, split, leakage status
# ---------------------------------------------------------------------------------------------------------

EVENTS = {
    "melting", "boiling", "sublimation", "decomposition", "melting_with_decomposition", "not_observed", "unknown",
}
TARGETS = {"melting_point", "normal_boiling_point", "decomposition_temperature"}


def _admit(vr, target):
    return {
        "melting_point": vr.admit_to_melting_point_set,
        "normal_boiling_point": vr.admit_to_normal_boiling_point_set,
    }.get(target) or (lambda row: vr.admit_to_target(row, target))


def test_the_event_vocabulary_is_complete_and_includes_boiling_and_sublimation(vr):
    assert vr.TRANSITION_TYPES == EVENTS
    assert vr.TARGET_PROPERTIES == TARGETS


def test_every_target_and_event_pair_has_an_explicit_admission_decision(vr):
    """Adding an event or a target without deciding what it may be scored against must fail here."""
    assert set(vr.ADMISSION_POLICY) == {(t, e) for t in TARGETS for e in EVENTS}
    assert all(isinstance(v, bool) for v in vr.ADMISSION_POLICY.values())
    assert sorted(k for k, v in vr.ADMISSION_POLICY.items() if v) == [
        ("decomposition_temperature", "decomposition"),
        ("melting_point", "melting"),
        ("normal_boiling_point", "boiling"),
    ]


@pytest.mark.parametrize("event", sorted(EVENTS))
@pytest.mark.parametrize("target", sorted(TARGETS))
def test_admit_to_target_follows_the_policy_for_every_pair(vr, target, event):
    row = _row(vr, "r", "CCO", prop=target, transition_type=event)
    reason = vr.admit_to_target(row, target)
    assert (reason is None) == vr.ADMISSION_POLICY[(target, event)]
    if reason is not None:
        assert event in reason


def test_an_unknown_event_is_admitted_to_no_score_with_a_deterministic_reason(vr):
    for target in TARGETS:
        row = _row(vr, "r", "CCO", prop=target, transition_type="unknown")
        assert vr.admit_to_target(row, target) == "transition_type is 'unknown', not a clean %r value" % (
            vr._CLEAN_EVENT[target]
        )


def test_an_invalid_target_fails_explicitly(vr):
    with pytest.raises(ValueError, match="target"):
        vr.admit_to_target(_row(vr, "r", "CCO", transition_type="melting"), "freezing_point")


def test_a_row_with_no_event_is_never_scoreable_whatever_its_units(vr):
    row = _row(vr, "r", "CCO", prop="melting_point", units="K")
    assert "no transition_type" in vr.admit_to_target(row, "melting_point")
    assert "no transition_type" in vr.admit_to_normal_boiling_point_set(row)


def test_a_clean_boiling_row_is_not_a_melting_point_and_the_reverse(vr):
    boiling = _row(vr, "b", "CCO", prop="tb", transition_type="boiling", reference_pressure_pa=101325.0,
                   pressure_basis="stated")
    melting = _row(vr, "m", "CCO", prop="tm", transition_type="melting")
    assert vr.admit_to_melting_point_set(boiling) is not None
    assert vr.admit_to_normal_boiling_point_set(melting) is not None
    assert vr.admit_to_normal_boiling_point_set(boiling) is None


# ----- pressure ------------------------------------------------------------------------------------------


def _boil(vr, row_id="b", **kw):
    return _row(vr, row_id, "CCO", prop="tb", transition_type="boiling", **kw)


@pytest.mark.parametrize("pressure", [101325.0, 101325.0 + 1500.0, 101325.0 - 1500.0])
def test_a_pressure_within_the_tolerance_is_a_normal_boiling_point(vr, pressure):
    row = _boil(vr, reference_pressure_pa=pressure, pressure_basis="stated")
    assert vr.admit_to_normal_boiling_point_set(row) is None


@pytest.mark.parametrize("pressure", [101325.0 + 1500.1, 101325.0 - 1500.1, 13332.2, 202650.0])
def test_a_pressure_outside_the_tolerance_is_refused_and_says_how_far(vr, pressure):
    reason = vr.admit_to_normal_boiling_point_set(_boil(vr, reference_pressure_pa=pressure, pressure_basis="stated"))
    assert "normal pressure" in reason and "outside" in reason


def test_a_boiling_row_with_no_pressure_is_refused_unless_the_source_says_its_column_is_normal(vr):
    assert "not a normal boiling point" in vr.admit_to_normal_boiling_point_set(_boil(vr))
    assert vr.admit_to_normal_boiling_point_set(_boil(vr, pressure_basis="table_convention_normal")) is None


def test_a_stated_pressure_basis_without_a_pressure_is_an_error_at_construction(vr):
    with pytest.raises(ValueError, match="stated"):
        _boil(vr, pressure_basis="stated")


@pytest.mark.parametrize("kw", [{"pressure_basis": "assumed"}, {"reference_pressure_pa": 0.0},
                                {"reference_pressure_pa": -5.0}])
def test_a_pressure_field_outside_its_vocabulary_is_refused(vr, kw):
    with pytest.raises(ValueError):
        _boil(vr, **kw)


def test_units_never_change_an_admission_decision(vr):
    """A conversion cannot bypass the event or the pressure: the decision does not read the units."""
    kelvin = _boil(vr, units="K", reference_pressure_pa=13332.2, pressure_basis="stated")
    celsius = _boil(vr, units="C", reference_pressure_pa=13332.2, pressure_basis="stated")
    assert vr.admit_to_normal_boiling_point_set(kelvin) == vr.admit_to_normal_boiling_point_set(celsius) is not None


def test_sublimation_and_decomposition_are_not_boiling_points(vr):
    for event in ("sublimation", "decomposition", "melting_with_decomposition", "not_observed"):
        row = _row(vr, "r", "CCO", prop="tb", transition_type=event, reference_pressure_pa=101325.0,
                   pressure_basis="stated")
        assert event in vr.admit_to_normal_boiling_point_set(row)


# ----- a target with no numeric label --------------------------------------------------------------------


def test_a_no_event_record_has_no_value_and_cannot_be_scored(vr):
    record = vr.NoEventRecord(
        record_id="n1", smiles="CCO", target_property="normal_boiling_point", observed_event="decomposition",
        source_id="synthetic", locator="synthetic p1", reason="decomposes before it boils",
    )
    assert not hasattr(record, "value")
    with pytest.raises(TypeError, match="no numeric value"):
        vr.admit_to_target(record, "normal_boiling_point")
    with pytest.raises(TypeError):
        vr.admit_to_normal_boiling_point_set(record)
    with pytest.raises(TypeError):
        vr.admit_to_melting_point_set(record)


@pytest.mark.parametrize("kw", [{"target_property": "boiling"}, {"observed_event": "melting"},
                                {"observed_event": "boiling"}, {"reason": "   "}])
def test_a_no_event_record_outside_its_vocabulary_or_without_a_reason_is_refused(vr, kw):
    base = dict(record_id="n", smiles="CCO", target_property="normal_boiling_point", observed_event="not_observed",
                source_id="s", locator="l", reason="no clean event")
    base.update(kw)
    with pytest.raises(ValueError):
        vr.NoEventRecord(**base)


# ----- ranges --------------------------------------------------------------------------------------------


def _range_row(vr, **kw):
    return _row(vr, "r", "CCO", prop="tm", transition_type="melting", value=80.0, range_low=79.0, range_high=81.0, **kw)


@pytest.mark.parametrize(("predicted", "expected"), [(79.0, 0.0), (80.0, 0.0), (81.0, 0.0), (78.0, 1.0),
                                                     (84.5, 3.5), (70.0, 9.0)])
def test_a_range_is_scored_as_an_interval_and_never_by_its_midpoint(vr, predicted, expected):
    assert vr.absolute_error(_range_row(vr), predicted) == pytest.approx(expected)


def test_a_point_value_is_scored_by_distance(vr):
    assert vr.absolute_error(_row(vr, "r", "CCO", value=100.0), 97.5) == pytest.approx(2.5)


@pytest.mark.parametrize("kw", [{"range_low": 79.0}, {"range_high": 81.0}, {"range_low": 82.0, "range_high": 81.0},
                                {"range_low": 85.0, "range_high": 90.0}])
def test_a_malformed_range_is_an_error_at_construction(vr, kw):
    with pytest.raises(ValueError):
        _row(vr, "r", "CCO", prop="tm", transition_type="melting", value=80.0, **kw)


def test_the_original_reported_fields_are_kept_beside_the_normalised_ones(vr):
    row = _row(vr, "r", "CCO", value=351.65, reported_value="78.5", reported_unit="C", reported_pressure="760 mm",
               normalisation_method="C to K", locator="synthetic edition, table 1, p 1, entry 1",
               physical_form="alpha")
    assert (row.reported_value, row.reported_unit, row.normalisation_method) == ("78.5", "C", "C to K")
    assert row.value == pytest.approx(351.65)


def test_a_row_built_the_old_way_keeps_its_meaning_and_is_not_admitted_by_default(vr):
    """Additive: legacy arguments still work, the new fields are empty, and nothing becomes scoreable."""
    row = vr.ValidationRow(row_id="r", smiles="CCO", property="tb", value=1.0, units="K", source_id="s",
                           record_id="r", partition="holdout")
    assert row.reference_pressure_pa is None and row.pressure_basis is None and row.range_low is None
    assert row.reported_value == "" and row.locator == "" and row.physical_form == ""
    assert vr.admit_to_normal_boiling_point_set(row) is not None
    assert vr.admit_to_melting_point_set(row) is not None


# ----- the split ------------------------------------------------------------------------------------------


def test_the_partition_shares_sum_to_one_hundred_and_name_the_three_partitions(vr):
    assert sum(share for _, share in vr.PARTITION_SHARES) == 100
    assert {name for name, _ in vr.PARTITION_SHARES} == vr.PARTITIONS


def test_every_spelling_and_stereoisomer_of_a_skeleton_lands_in_one_partition(vr):
    spellings = ["c1ccccc1", "C1=CC=CC=C1", "[cH]1[cH][cH][cH][cH][cH]1"]
    assert len({vr.partition_for(vr.split_group_key(s)) for s in spellings}) == 1
    pair = ["C[C@H](N)C(=O)O", "C[C@@H](N)C(=O)O", "CC(N)C(=O)O"]
    assert len({vr.partition_for(vr.split_group_key(s)) for s in pair}) == 1


def test_charge_and_isotope_variants_share_their_skeleton_key_so_they_cannot_straddle_partitions(vr):
    for neutral, variant in [("CC(=O)O", "CC(=O)[O-]"), ("CCN", "CC[NH3+]"), ("c1ccccc1", "[2H]c1ccccc1")]:
        assert vr.split_group_key(neutral) == vr.split_group_key(variant)
        assert vr.partition_for(vr.split_group_key(neutral)) == vr.partition_for(vr.split_group_key(variant))


def test_the_partition_of_a_key_does_not_depend_on_which_other_keys_exist(vr):
    alone = vr.partition_manifest(["CCO"])
    crowd = vr.partition_manifest(["CCO", "c1ccccc1", "CC(=O)O", "CCN"])
    key = vr.split_group_key("CCO")
    assert alone[key] == crowd[key]


def test_the_partition_manifest_is_deterministic_and_its_checksum_notices_a_change(vr):
    smiles = ["CCO", "c1ccccc1", "CC(=O)O", "CCN", "CCCC"]
    one, two = vr.partition_manifest(smiles), vr.partition_manifest(list(reversed(smiles)))
    assert one == two and vr.manifest_checksum(one) == vr.manifest_checksum(two)
    changed = dict(one)
    key = next(iter(changed))
    changed[key] = "holdout" if changed[key] != "holdout" else "development"
    assert vr.manifest_checksum(changed) != vr.manifest_checksum(one)


def test_the_hash_split_comes_out_near_sixty_twenty_twenty(vr):
    from collections import Counter

    counts = Counter(vr.partition_for(f"KEY{i:06d}") for i in range(6000))
    assert counts["development"] / 6000 == pytest.approx(0.60, abs=0.03)
    assert counts["selection"] / 6000 == pytest.approx(0.20, abs=0.03)
    assert counts["holdout"] / 6000 == pytest.approx(0.20, abs=0.03)


def test_several_observations_of_one_molecule_all_follow_the_molecule(vr):
    rows = [_row(vr, f"obs{i}", smi, prop="tm", transition_type="melting", source_id=f"src{i}")
            for i, smi in enumerate(["c1ccccc1", "C1=CC=CC=C1"])]
    assert len({vr.partition_for(vr.split_group_key(r.smiles)) for r in rows}) == 1


# ----- leakage as a status -------------------------------------------------------------------------------


def test_an_unrecorded_population_is_the_unknown_status_and_clears_nothing(vr):
    rows = [_row(vr, "r1", "CCO", prop="tm"), _row(vr, "r2", "CCN", prop="tm")]
    result = vr.assess_leakage(rows, "m", {("m", "tb"): frozenset()})
    assert result.status == "unknown"
    assert result.kept == () and result.excluded == () and len(result.exploratory) == 2
    assert vr.may_claim_independent_holdout(result) is False


def test_exclude_leaked_still_raises_for_the_same_case(vr):
    with pytest.raises(vr.UnknownFitPopulation):
        vr.exclude_leaked([_row(vr, "r", "CCO", prop="tm")], "m", {("m", "tb"): frozenset()})


def test_a_known_population_with_no_overlap_clears_the_rows(vr):
    result = vr.assess_leakage([_row(vr, "r", "CCO", prop="tm")], "m", {("m", "tm"): vr.population_blocks(["CCN"])})
    assert result.status == "known_population_no_overlap" and len(result.kept) == 1
    assert vr.may_claim_independent_holdout(result) is True


def test_a_known_population_with_overlap_removes_and_says_so(vr):
    rows = [_row(vr, "in", "c1ccccc1", prop="tm"), _row(vr, "out", "CCN", prop="tm")]
    result = vr.assess_leakage(rows, "m", {("m", "tm"): vr.population_blocks(["C1=CC=CC=C1"])})
    assert result.status == "known_population_overlap_removed"
    assert [r.row_id for r in result.excluded] == ["in"] and [r.row_id for r in result.kept] == ["out"]


def test_recorded_evidence_of_no_overlap_is_its_own_status_and_needs_words(vr):
    rows = [_row(vr, "r", "CCO", prop="tm")]
    ok = vr.assess_leakage(rows, "m", {}, {("m", "tm"): "fitted on a disjoint data set, see the paper's Table 2"})
    assert ok.status == "no_overlap_by_evidence" and vr.may_claim_independent_holdout(ok)
    blank = vr.assess_leakage(rows, "m", {}, {("m", "tm"): "   "})
    assert blank.status == "unknown"


def test_assess_leakage_takes_one_property_at_a_time_and_the_status_vocabulary_is_closed(vr):
    with pytest.raises(ValueError, match="one property"):
        vr.assess_leakage([_row(vr, "a", "CCO", prop="tm"), _row(vr, "b", "CCO", prop="tb")], "m", {})
    with pytest.raises(ValueError, match="status"):
        vr.LeakageAssessment("m", "tm", "clean")


def test_the_leakage_status_vocabulary_has_unknown_and_no_clean(vr):
    assert "unknown" in vr.LEAKAGE_STATUSES and "clean" not in vr.LEAKAGE_STATUSES
