"""A project's score definitions and the block they are saved in (`domain/score_definition_store.py`).

The property that matters is that **nothing a person wrote is dropped because this build cannot read it**: a definition from a newer format, a damaged
one and a block from a newer envelope are all written back exactly as they were read. Each is tested by saving and comparing, because "kept" that
loses a field on the way through is the same loss as "dropped".
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import MAX_DEFINITIONS, SCHEMA_VERSION, ScoreDefinition
from openchem.domain.score_definition_store import (
    ENVELOPE_VERSION,
    KEPT_DAMAGED,
    KEPT_NEWER,
    ScoreDefinitionStore,
)

_UUID = "project-1"


def _definition(score_id="user.a", **changes) -> ScoreDefinition:
    base = ScoreDefinition(
        score_id=score_id, label=f"Score {score_id}", formula="ramp(psa, 140, 60)", result_unit="1", inputs=(("psa", "descriptor:tpsa"),),
        constants=(Constant("k", 2.0, "1"),), owner="Alex", created="2026-10-14", note="n",
    )
    return replace(base, **changes)


def _roundtrip(store: ScoreDefinitionStore) -> ScoreDefinitionStore:
    return ScoreDefinitionStore.from_dict(json.loads(json.dumps(store.to_dict())), _UUID)


# --- an ordinary store ---------------------------------------------------------------------------------------------------------


def test_a_project_saved_before_scores_existed_has_an_empty_store():
    store = ScoreDefinitionStore.from_dict(None, _UUID)
    assert len(store) == 0 and store.definitions() == () and store.kept() == () and store.load_problems == () and not store.foreign
    assert store.project_uuid == _UUID


def test_an_empty_store_writes_an_empty_envelope():
    assert ScoreDefinitionStore(_UUID).to_dict() == {"version": ENVELOPE_VERSION, "definitions": []}


def test_definitions_keep_the_order_they_were_made_in_through_a_save():
    store = ScoreDefinitionStore(_UUID)
    for score_id in ("user.c", "user.a", "user.b"):
        store.add(_definition(score_id))
    again = _roundtrip(store)
    assert [d.score_id for d in again.definitions()] == ["user.c", "user.a", "user.b"]
    assert again.definitions() == store.definitions()


def test_add_get_replace_and_remove():
    store = ScoreDefinitionStore(_UUID)
    first, second = _definition("user.a"), _definition("user.b")
    store.add(first)
    store.add(second)
    assert store.get("user.a") is first and store.get("nothing") is None and len(store) == 2
    edited = replace(first, label="Renamed")
    store.replace(edited)
    assert store.get("user.a") is edited and [d.score_id for d in store.definitions()] == ["user.a", "user.b"]
    assert store.remove("user.a") is True and store.remove("user.a") is False
    assert [d.score_id for d in store.definitions()] == ["user.b"]


def test_a_duplicate_id_is_refused():
    store = ScoreDefinitionStore(_UUID)
    store.add(_definition("user.a"))
    with pytest.raises(ValueError, match="already exists"):
        store.add(_definition("user.a"))


def test_replacing_something_that_is_not_there_is_an_error_and_not_an_add():
    with pytest.raises(KeyError):
        ScoreDefinitionStore(_UUID).replace(_definition("user.a"))


def test_a_project_holds_at_most_the_limit():
    store = ScoreDefinitionStore(_UUID)
    for i in range(MAX_DEFINITIONS):
        store.add(_definition(f"user.s{i}"))
    with pytest.raises(ValueError, match=f"at most {MAX_DEFINITIONS}"):
        store.add(_definition("user.one_more"))
    assert MAX_DEFINITIONS == 100


# --- a definition from a newer format is kept ----------------------------------------------------------------------------------


def _newer() -> dict:
    return {"schema_version": SCHEMA_VERSION + 1, "score_id": "user.future", "label": "From the future", "weights": [1, 2, 3], "novel": {"x": [None]}}


def test_a_newer_definition_is_kept_exactly_and_not_evaluated():
    raw = {"version": ENVELOPE_VERSION, "definitions": [_definition("user.a").to_dict(), _newer()]}
    store = ScoreDefinitionStore.from_dict(json.loads(json.dumps(raw)), _UUID)
    assert [d.score_id for d in store.definitions()] == ["user.a"]
    (kept,) = store.kept()
    assert kept.kind == KEPT_NEWER and kept.score_id == "user.future" and kept.label == "From the future" and "newer version" in kept.reason
    assert store.load_problems == (), "a newer definition is not damage"
    assert _roundtrip(store).to_dict() == raw, "everything, including the fields this build has never heard of, goes back as it was"


def test_a_save_of_a_store_holding_a_newer_definition_puts_it_back_where_it_was():
    raw = {"version": ENVELOPE_VERSION, "definitions": [_newer(), _definition("user.a").to_dict()]}
    store = ScoreDefinitionStore.from_dict(raw, _UUID)
    store.add(_definition("user.b"))
    written = store.to_dict()
    assert written["definitions"][0] == _newer() and written["definitions"][1]["score_id"] == "user.a" and written["definitions"][2]["score_id"] == "user.b"


def test_an_id_that_is_only_being_carried_is_never_handed_out_again():
    store = ScoreDefinitionStore.from_dict({"version": 1, "definitions": [_newer()]}, _UUID)
    assert "user.future" in store.score_ids()
    with pytest.raises(ValueError, match="already exists"):
        store.add(_definition("user.future"))


def test_a_kept_entry_cannot_be_replaced_or_removed_through_an_id():
    store = ScoreDefinitionStore.from_dict({"version": 1, "definitions": [_newer()]}, _UUID)
    with pytest.raises(KeyError):
        store.replace(_definition("user.future"))
    assert store.remove("user.future") is False and len(store.kept()) == 1


# --- a damaged definition is kept ------------------------------------------------------------------------------------------------


def test_a_damaged_definition_is_kept_with_its_reason_and_the_others_still_load():
    broken = {"score_id": "user.broken", "label": "Broken", "schema_version": 1, "formula": 7}
    raw = {"version": 1, "definitions": [broken, _definition("user.a").to_dict(), "garbage", None, 5, []]}
    store = ScoreDefinitionStore.from_dict(json.loads(json.dumps(raw)), _UUID)
    assert [d.score_id for d in store.definitions()] == ["user.a"]
    assert [k.kind for k in store.kept()] == [KEPT_DAMAGED] * 5
    assert store.kept()[0].score_id == "user.broken" and "formula" in store.kept()[0].reason
    assert len(store.load_problems) == 5 and all("kept as it is" in p for p in store.load_problems)
    assert _roundtrip(store).to_dict() == raw, "a damaged entry is kept byte for byte so a person can mend the file"


def test_the_same_id_twice_keeps_the_second_aside_and_does_not_replace_the_first():
    first = _definition("user.a", label="First").to_dict()
    second = _definition("user.a", label="Second").to_dict()
    store = ScoreDefinitionStore.from_dict({"version": 1, "definitions": [first, second]}, _UUID)
    assert store.get("user.a").label == "First" and len(store.kept()) == 1 and "appears twice" in store.kept()[0].reason
    assert _roundtrip(store).to_dict() == {"version": 1, "definitions": [first, second]}


# --- a block from a newer envelope is kept whole ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block",
    [
        {"version": 2, "definitions": [{"anything": 1}], "extra": True},
        {"version": 0, "definitions": []},
        {"version": "1", "definitions": []},
        {"version": True, "definitions": []},
        {"definitions": []},
        {"version": 1},
        {"version": 1, "definitions": {"a": 1}},
        ["a", "list"],
        "text",
        7,
    ],
)
def test_a_block_this_build_cannot_read_is_kept_whole_and_written_back_unchanged(block):
    store = ScoreDefinitionStore.from_dict(json.loads(json.dumps(block)), _UUID)
    assert store.foreign and store.definitions() == () and store.kept() == () and len(store.load_problems) == 1
    assert store.to_dict() == block


def test_a_store_holding_a_foreign_block_refuses_every_change():
    store = ScoreDefinitionStore.from_dict({"version": 9, "definitions": []}, _UUID)
    for action in (lambda: store.add(_definition()), lambda: store.replace(_definition()), lambda: store.remove("user.a")):
        with pytest.raises(ValueError, match="newer version"):
            action()
    assert store.to_dict() == {"version": 9, "definitions": []}


def test_the_envelope_version_is_one():
    assert ENVELOPE_VERSION == 1 and SCHEMA_VERSION == 1
