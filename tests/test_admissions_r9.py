"""The round-9 fix ledger is a machine-checked cap, not a promise.

`benchmarks/naming/admissions_r9.toml` holds at most EIGHT admitted fixes. Round 8's lesson was that a scope stated in prose is a scope that
grows: a four-workstream plan became a second day of unplanned fixes because nothing failed when it did. These tests are the thing that fails.

The ledger is EMPTY until the end of the instruments stage, then filled once and frozen by a hash. Every rule here is applied to the entries
that exist, and to a synthetic ledger in `_ledger()` so that the rules are proven to bite before there is anything for them to bite on.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "benchmarks" / "naming" / "admissions_r9.toml"

SOURCES = {"B1", "B2", "B3", "existing_open_list"}
LAYERS = {"serialization", "candidate_generation", "preference", "numbering", "ownership", "retained_parent", "charge_ledger", "scope"}
STATUSES = {"admitted", "in_progress", "done", "abandoned"}
REQUIRED = {"item_id", "slot_number", "discovery_source", "admission_reason", "wrong_molecule", "diagnosed_against_fixture",
            "target_source", "measured_primary_layer", "dependencies", "status"}


def load(path: Path = LEDGER) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def frozen_hash(items: list[dict]) -> str:
    """sha256 over the sorted (item_id, slot, reason, target source, discovery source) tuples: the fields that say WHAT was admitted and why.
    Progress fields (status, measured layer, dependencies) are deliberately outside it, so recording progress never re-freezes the set."""
    rows = sorted(
        (i["item_id"], int(i["slot_number"]), i["admission_reason"], i["target_source"], ",".join(sorted(i["discovery_source"])))
        for i in items
    )
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def problems(ledger: dict) -> list[str]:
    """Every rule the ledger must satisfy, as a list of messages (empty = valid). Kept a pure function so the rules can be tested on
    ledgers that do not exist in the repository."""
    out: list[str] = []
    cap = ledger.get("cap", {})
    slots = cap.get("slots")
    minimum = cap.get("natural_frequency_min")
    if slots != 8:
        out.append(f"the cap is 8 slots, not {slots!r}")
    if not isinstance(minimum, float) or not 0 < minimum < 1:
        out.append(f"natural_frequency_min must be a fraction in (0, 1), got {minimum!r}")
    items = ledger.get("item", [])
    if len(items) > (slots or 0):
        out.append(f"{len(items)} items admitted against a cap of {slots}")
    seen_ids: set[str] = set()
    seen_slots: set[int] = set()
    for item in items:
        name = item.get("item_id", "<no id>")
        missing = REQUIRED - set(item)
        if missing:
            out.append(f"{name}: missing {sorted(missing)}")
            continue
        if name in seen_ids:
            out.append(f"{name}: duplicate item_id")
        seen_ids.add(name)
        slot = item["slot_number"]
        if not isinstance(slot, int) or not 1 <= slot <= (slots or 0):
            out.append(f"{name}: slot_number {slot!r} is not in 1..{slots}")
        elif slot in seen_slots:
            out.append(f"{name}: slot {slot} is taken twice")
        seen_slots.add(slot)
        if not item["discovery_source"] or not set(item["discovery_source"]) <= SOURCES:
            out.append(f"{name}: discovery_source must be a non-empty subset of {sorted(SOURCES)}")
        if item["measured_primary_layer"] not in LAYERS:
            out.append(f"{name}: measured_primary_layer {item['measured_primary_layer']!r} is not one of {sorted(LAYERS)}")
        if item["status"] not in STATUSES:
            out.append(f"{name}: status {item['status']!r} is not one of {sorted(STATUSES)}")
        target = item["target_source"]
        if not (target.startswith("book:p.") or target.startswith("derived:") or target == "none"):
            out.append(f"{name}: target_source must be 'book:p.N', 'derived:<rule>' or 'none', got {target!r}")
        if item["wrong_molecule"]:
            if not item["diagnosed_against_fixture"]:
                out.append(f"{name}: a wrong molecule must be diagnosed against the INTENDED structure, not inferred from PubChem")
        else:
            if item["diagnosed_against_fixture"]:
                out.append(f"{name}: diagnosed_against_fixture is only meaningful for a wrong molecule")
            if target == "none":
                out.append(f"{name}: an item that is not a wrong molecule needs a printed or derived target, not 'none'")
            frequency = item.get("frequency")
            if not isinstance(frequency, float) or not (isinstance(minimum, float) and frequency >= minimum):
                out.append(f"{name}: NATURAL_FREQUENCY {frequency!r} does not clear the committed floor {minimum!r}")
        if not isinstance(item["dependencies"], list):
            out.append(f"{name}: dependencies must be a list")
    if cap.get("frozen"):
        if not cap.get("frozen_sha256"):
            out.append("the ledger says it is frozen but records no frozen_sha256")
        elif not [m for m in out if "missing" in m] and cap["frozen_sha256"] != frozen_hash(items):
            out.append("the admitted set changed after the freeze (frozen_sha256 no longer matches)")
    elif cap.get("frozen_sha256"):
        out.append("frozen_sha256 is set but frozen is false")
    return out


def _item(n: int, **overrides) -> dict:
    item = {
        "item_id": f"F{n}", "slot_number": n, "discovery_source": ["existing_open_list"], "admission_reason": f"reason {n}",
        "wrong_molecule": False, "diagnosed_against_fixture": False, "frequency": 0.01, "target_source": "book:p.619",
        "seed_layer": "serialization", "measured_primary_layer": "serialization", "dependencies": [], "status": "admitted",
    }
    item.update(overrides)
    return item


def _ledger(*items: dict, frozen: bool = False) -> dict:
    ledger = {"cap": {"slots": 8, "natural_frequency_min": 0.005, "frozen": frozen, "frozen_sha256": ""}, "item": list(items)}
    if frozen:
        ledger["cap"]["frozen_sha256"] = frozen_hash(list(items))
    return ledger


# --- the committed ledger ------------------------------------------------------------------------------------------------------------

def test_the_committed_ledger_is_valid():
    assert problems(load()) == []


def test_the_frequency_floor_was_committed_before_any_census_exists():
    """It is the ledger's own header, in the R0 commit. The census file (B3) cannot move it: the census only reports counts against it."""
    assert load()["cap"]["natural_frequency_min"] == 0.005  # 10 hits in a 2,000-structure sample


# --- the rules, on ledgers that do not exist -----------------------------------------------------------------------------------------

def test_eight_items_fit_and_nine_do_not():
    assert problems(_ledger(*[_item(n) for n in range(1, 9)])) == []
    nine = _ledger(*[_item(n) for n in range(1, 10)])
    assert any("9 items admitted against a cap of 8" in m for m in problems(nine))


def test_a_wrong_molecule_takes_a_slot_like_any_other_item():
    """The first draft of the plan let wrong molecules escape the cap, which is not a cap. Eight items INCLUDING wrong molecules still fit;
    a ninth of either kind does not."""
    wrong = [_item(n, wrong_molecule=True, diagnosed_against_fixture=True, target_source="none", frequency=0.0) for n in range(1, 5)]
    ordinary = [_item(n) for n in range(5, 9)]
    assert problems(_ledger(*wrong, *ordinary)) == []
    ninth_wrong = _item(9, wrong_molecule=True, diagnosed_against_fixture=True, target_source="none")
    assert any("cap of 8" in m for m in problems(_ledger(*wrong, *ordinary, ninth_wrong)))


def test_a_slot_is_used_once_and_lies_in_range():
    assert any("taken twice" in m for m in problems(_ledger(_item(1), _item(2, slot_number=1))))
    assert any("not in 1..8" in m for m in problems(_ledger(_item(1, slot_number=9))))
    assert any("not in 1..8" in m for m in problems(_ledger(_item(1, slot_number=0))))


def test_an_item_needs_a_target_source_of_the_declared_kinds():
    assert any("target_source must be" in m for m in problems(_ledger(_item(1, target_source="pubchem"))))
    assert any("target_source must be" in m for m in problems(_ledger(_item(1, target_source=""))))
    assert problems(_ledger(_item(1, target_source="derived:P-16.5.1.3.1"))) == []


def test_none_is_a_target_only_for_a_wrong_molecule():
    assert any("printed or derived target" in m for m in problems(_ledger(_item(1, target_source="none"))))
    assert problems(_ledger(_item(1, wrong_molecule=True, diagnosed_against_fixture=True, target_source="none", frequency=0.0))) == []


def test_a_wrong_molecule_must_be_diagnosed_against_the_fixture_structure():
    """PubChem disagreeing is the discovery signal, never the classification."""
    inferred = _item(1, wrong_molecule=True, diagnosed_against_fixture=False, target_source="none")
    assert any("INTENDED structure" in m for m in problems(_ledger(inferred)))
    assert any("only meaningful for a wrong molecule" in m for m in problems(_ledger(_item(1, diagnosed_against_fixture=True))))


def test_an_ordinary_item_must_clear_the_frequency_floor_mechanically():
    assert any("does not clear" in m for m in problems(_ledger(_item(1, frequency=0.004))))
    assert any("does not clear" in m for m in problems(_ledger(_item(1, frequency=None))))
    assert problems(_ledger(_item(1, frequency=0.005))) == []  # at the floor, not below it


def test_a_measured_layer_from_the_declared_vocabulary_is_required():
    assert any("measured_primary_layer" in m for m in problems(_ledger(_item(1, measured_primary_layer="vibes"))))
    incomplete = _item(1)
    del incomplete["measured_primary_layer"]
    assert any("missing" in m and "measured_primary_layer" in m for m in problems(_ledger(incomplete)))


def test_a_discovery_source_is_recorded_and_from_the_declared_set():
    assert any("discovery_source" in m for m in problems(_ledger(_item(1, discovery_source=[]))))
    assert any("discovery_source" in m for m in problems(_ledger(_item(1, discovery_source=["a hunch"]))))
    assert problems(_ledger(_item(1, discovery_source=["B1", "B3"]))) == []


def test_the_cap_and_the_floor_themselves_cannot_be_edited_quietly():
    raised = _ledger()
    raised["cap"]["slots"] = 9
    assert any("cap is 8" in m for m in problems(raised))
    for bad in (0, 1, -0.1, "0.005", None):
        loosened = _ledger()
        loosened["cap"]["natural_frequency_min"] = bad
        assert any("natural_frequency_min" in m for m in problems(loosened)), bad


def test_after_the_freeze_the_admitted_set_does_not_move():
    frozen = _ledger(_item(1), _item(2), frozen=True)
    assert problems(frozen) == []
    # progress may be recorded without re-freezing
    frozen["item"][0]["status"] = "done"
    frozen["item"][0]["dependencies"] = ["F2"]
    assert problems(frozen) == []
    # but the SET may not change: a swap, a late addition, a rewritten reason or a moved slot each fail
    swapped = _ledger(_item(1), _item(2), frozen=True)
    swapped["item"][1]["item_id"] = "F9"
    assert any("changed after the freeze" in m for m in problems(swapped))
    added = _ledger(_item(1), _item(2), frozen=True)
    added["item"].append(_item(3))
    assert any("changed after the freeze" in m for m in problems(added))
    reworded = _ledger(_item(1), _item(2), frozen=True)
    reworded["item"][0]["admission_reason"] = "a different reason"
    assert any("changed after the freeze" in m for m in problems(reworded))
    moved = _ledger(_item(1), _item(2), frozen=True)
    moved["item"][0]["slot_number"] = 5
    assert any("changed after the freeze" in m for m in problems(moved))


def test_a_ledger_that_claims_to_be_frozen_must_record_its_hash_and_an_unfrozen_one_must_not():
    claimed = _ledger(_item(1))
    claimed["cap"]["frozen"] = True
    assert any("records no frozen_sha256" in m for m in problems(claimed))
    stray = _ledger(_item(1))
    stray["cap"]["frozen_sha256"] = "0" * 64
    assert any("frozen is false" in m for m in problems(stray))


@pytest.mark.parametrize("field", sorted(REQUIRED - {"measured_primary_layer"}))
def test_every_required_field_is_required(field):
    item = _item(1)
    del item[field]
    assert any(f"missing" in m and field in m for m in problems(_ledger(item))), field
