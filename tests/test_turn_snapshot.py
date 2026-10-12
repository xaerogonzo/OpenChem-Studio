"""The turn snapshot: what the assistant may read about the selected molecule, frozen at Send."""

from __future__ import annotations

import dataclasses

import pytest

from openchem.domain.common import CacheState, Provenance
from openchem.domain.refusal_kinds import INPUT_REQUIRED, refusal_parameters, RefusalKind
from openchem.domain.result_store import ResultIdentity, SessionResultStore, StoredResult
from openchem.domain.scientific_result import PerAtomDataset
from openchem.domain.turn_snapshot import (
    Freshness,
    Outcome,
    build_turn_context,
    classify_results,
    read_results,
)

MOL = "mol-1"
FP = {"drawing": "draw-NOW", "geometry": "geom-NOW"}


def _result(**kw):
    base = dict(property_id="p", name="P", units="", method="m", molecule_uuid=MOL, values={0: 1.0})
    base.update(kw)
    return PerAtomDataset(**base)


def _refusal(code, kind=None, inapplicable=False):
    return _result(
        values={}, cache_state=CacheState.FAILED, error="declined", inapplicable=inapplicable,
        provenance=Provenance(created_by="core", method="x", parameters=refusal_parameters(code, kind)),
    )


def _stored(producer="calc", result=None, fingerprint="draw-NOW", calculation_input="drawing", result_id=None):
    result = result if result is not None else _result(property_id=result_id or producer)
    identity = ResultIdentity(
        molecule_uuid=MOL, result_id=result_id or getattr(result, "property_id", producer),
        calculation_input=calculation_input, input_fingerprint=fingerprint, producer=producer,
    )
    return StoredResult(identity=identity, result=result)


def _classify(records, fresh=None):
    return classify_results(records, records if fresh is None else fresh, FP)


# --- freshness ----------------------------------------------------------------------------------


def test_a_result_computed_on_the_current_structure_and_replayed_by_the_app_is_current():
    (entry,) = _classify([_stored()])
    assert entry.freshness is Freshness.CURRENT and entry.note == ""


def test_a_result_computed_on_an_earlier_structure_is_historical_and_says_so():
    (entry,) = _classify([_stored(fingerprint="draw-BEFORE")], fresh=[])
    assert entry.freshness is Freshness.HISTORICAL and "earlier structure" in entry.note


def test_a_superseded_method_stored_beside_the_current_one_is_not_offered_as_current():
    record = _stored()
    (entry,) = classify_results([record], [], FP)  # matches the fingerprint, but the store would not replay it
    assert entry.freshness is Freshness.HISTORICAL and "superseded" in entry.note


def test_a_record_with_no_fingerprint_is_unverifiable_never_current():
    (entry,) = _classify([_stored(fingerprint="")], fresh=[])
    assert entry.freshness is Freshness.UNVERIFIABLE and "no input fingerprint" in entry.note


def test_a_result_for_an_input_the_snapshot_cannot_fingerprint_is_unverifiable():
    record = _stored(calculation_input="ensemble", fingerprint="anything")
    (entry,) = _classify([record], fresh=[record])
    assert entry.freshness is Freshness.UNVERIFIABLE and "ensemble" in entry.note


def test_entries_are_ordered_current_first_then_historical_then_unverifiable():
    current = _stored("a")
    historical = _stored("b", fingerprint="old")
    unverifiable = _stored("c", fingerprint="")
    # Handed to the classifier in the opposite order from the one it must return.
    entries = classify_results([unverifiable, historical, current], [current], FP)
    assert [e.freshness for e in entries] == [Freshness.CURRENT, Freshness.HISTORICAL, Freshness.UNVERIFIABLE]


# --- outcome ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result, outcome, status",
    [
        (_result(), Outcome.COMPUTED, "ready"),
        (_result(values={}), Outcome.COMPUTED, "ready"),  # a result with no values is still a result
        (_result(cache_state=CacheState.FAILED, error="boom"), Outcome.FAILED, "failed"),
        (_refusal("not_a_real_code", None, inapplicable=True), Outcome.REFUSED, "inapplicable"),
        (_refusal(INPUT_REQUIRED, RefusalKind.NEEDS_INPUT), Outcome.REFUSED, "needs_input"),
        (_refusal("sidecar_not_configured", RefusalKind.NEEDS_SETUP), Outcome.REFUSED, "needs_setup"),
    ],
    ids=["computed", "empty-computed", "failed", "limit", "needs-input", "needs-setup"],
)
def test_the_outcome_follows_what_the_result_says(result, outcome, status):
    (entry,) = _classify([_stored(result=result)])
    assert (entry.outcome, entry.status) == (outcome, status)


def test_a_refusal_on_an_earlier_structure_is_a_historical_refusal_not_a_current_one():
    (entry,) = _classify([_stored(result=_refusal(INPUT_REQUIRED, RefusalKind.NEEDS_INPUT), fingerprint="old")], fresh=[])
    assert (entry.freshness, entry.outcome) == (Freshness.HISTORICAL, Outcome.REFUSED)


# --- the turn -----------------------------------------------------------------------------------


def _turn(records, fresh=None, **kw):
    base = dict(
        project_uuid="proj", molecule_uuid=MOL, display_name="Aspirin", canonical_smiles="CC(=O)Oc1ccccc1C(=O)O",
        heavy_atoms=13, has_structure=True, conformer_count=0, fingerprints=FP,
        records=records, fresh=records if fresh is None else fresh,
    )
    base.update(kw)
    return build_turn_context(**base)


def test_a_turn_is_unaffected_by_the_store_changing_after_it_was_taken():
    store = SessionResultStore("proj")
    first = _stored("calc")
    store.put(first)
    turn = _turn(store.all_results(MOL), store.fresh_results(MOL, FP))

    store.put(_stored("late"))          # a result that completes mid-turn
    store.clear()                       # and the store being emptied

    assert [e.producer for e in turn.entries] == ["calc"]
    assert read_results(turn, ["late"]).not_run == ("late",)


def test_the_fingerprints_in_a_turn_cannot_be_edited_by_a_caller():
    turn = _turn([])
    with pytest.raises(TypeError):
        turn.fingerprints["drawing"] = "forged"
    with pytest.raises(dataclasses.FrozenInstanceError):
        turn.molecule_uuid = "another"


def test_each_turn_gets_its_own_id():
    assert _turn([]).turn_id != _turn([]).turn_id


def test_the_store_can_list_every_record_including_the_ones_fresh_results_hides():
    store = SessionResultStore("proj")
    store.put(_stored("now"))
    store.put(_stored("old", fingerprint="draw-BEFORE"))
    assert {s.identity.producer for s in store.all_results(MOL)} == {"now", "old"}
    assert {s.identity.producer for s in store.fresh_results(MOL, FP)} == {"now"}
    assert store.all_results("someone-else") == []


def test_all_results_returns_a_copy():
    store = SessionResultStore("proj")
    store.put(_stored("now"))
    store.all_results(MOL).clear()
    assert len(store.all_results(MOL)) == 1


# --- reading ------------------------------------------------------------------------------------


def _mixed_turn():
    current = _stored("calc_a")
    stale = _stored("calc_b", fingerprint="old")
    unverifiable = _stored("calc_c", fingerprint="")
    return _turn([current, stale, unverifiable], fresh=[current])


def test_by_default_only_current_results_are_returned():
    view = read_results(_mixed_turn())
    assert [e.producer for e in view.entries] == ["calc_a"]


def test_not_current_results_are_returned_only_when_asked_and_keep_their_freshness():
    view = read_results(_mixed_turn(), include_not_current=True)
    assert {(e.producer, e.freshness) for e in view.entries} == {
        ("calc_a", Freshness.CURRENT), ("calc_b", Freshness.HISTORICAL), ("calc_c", Freshness.UNVERIFIABLE),
    }


def test_a_calculator_with_nothing_stored_is_not_run_and_one_with_only_old_records_is_said_so():
    view = read_results(_mixed_turn(), ["calc_a", "calc_b", "calc_c", "calc_z"])
    assert view.not_run == ("calc_z",)
    assert view.only_not_current == ("calc_b", "calc_c")
    assert [e.producer for e in view.entries] == ["calc_a"]


def test_nothing_is_invented_for_a_calculator_that_has_not_run():
    view = read_results(_turn([]), ["pka"])
    assert view.entries == () and view.not_run == ("pka",) and view.only_not_current == ()


def test_a_result_matched_by_both_its_producer_and_its_result_id_appears_once():
    turn = _turn([_stored("gasteiger_charge_at_ph", result_id="gasteiger_charge")])
    view = read_results(turn, ["gasteiger_charge_at_ph", "gasteiger_charge"])
    assert len(view.entries) == 1


def test_the_always_on_set_is_found_by_result_id_too():
    turn = _turn([_stored("rdkit", result_id="mol_wt")])
    assert [e.result_id for e in read_results(turn, ["mol_wt"]).entries] == ["mol_wt"]


def test_the_limit_truncates_and_says_how_many_were_left_out():
    turn = _turn([_stored(f"c{i}") for i in range(5)])
    view = read_results(turn, limit=2)
    assert len(view.entries) == 2 and view.truncated == 3
    assert read_results(turn, limit=0).entries == () and read_results(turn, limit=-4).truncated == 5


def test_a_repeated_calculator_id_is_read_once():
    turn = _turn([_stored("calc_a")])
    assert len(read_results(turn, ["calc_a", "calc_a"]).entries) == 1
