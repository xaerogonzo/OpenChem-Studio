"""The post-freeze addendum to protocol 3 (`benchmarks/synthesis/RESULT_3_ADDENDUM.md`): the references it holds, its stock rule, and that it leaves the frozen run alone.

The frozen reading (51 references, LOWER) is `tests/test_synthesis_protocol3.py`'s; these tests hold the addendum to its own files and hold the two sets apart.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "synthesis"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _BENCH / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


add = _load("run_addendum_3_under_test", "run_addendum_3.py")
run3 = add.run3


@pytest.fixture(scope="module")
def refs():
    return add.load_references()


def test_the_addendum_holds_the_two_routes_the_readings_gave(refs) -> None:
    assert [r["stem"] for r in refs] == ["kral2024_purpurogallin_carboxamides_influenza", "singh2025_lignan_monoterpenoid_xanthine_oxidase"]
    assert Counter(r["depth"] for r in refs) == {3: 1, 4: 1}
    assert all(r["steps"] <= 4 and r["tier"] == "B" and r["period"] == "2023-2025" for r in refs)


def test_a_paper_whose_lead_route_is_over_four_reactions_is_recorded_and_not_run() -> None:
    document = json.loads((add.OUT / "references" / "ma2025_autotaxin_pyrazolopyridinone.json").read_text(encoding="utf-8"))
    assert document["decision"] == "excluded" and document["exclusion_reason"] == "lead_route_over_4_steps"


def test_the_stock_never_holds_an_addendum_reference_s_own_intermediate_or_target(refs) -> None:
    keys = add.stock_keys(refs)
    assert keys["own_conflicts"] == []
    stock = set(keys["stock"])
    for ref in refs:
        for molecule in ref["intermediates"] + [ref["target"]]:
            assert add.j3.inchikey(molecule) not in stock
        for leaf in ref["leaves"]:
            assert add.j3.inchikey(leaf) in stock
    # the frozen primary stock is the base, and it is not rewritten
    frozen = {line.strip() for line in (add.FROZEN / "stocks" / "primary_inchikeys.txt").read_text(encoding="utf-8").splitlines() if line.strip()}
    assert frozen <= stock and keys["removed_from_frozen"] == 0


def test_the_addendum_does_not_touch_the_frozen_references() -> None:
    frozen = run3.load_references()
    assert len(frozen) == 51
    addendum = {r["stem"] for r in add.load_references()}
    assert not addendum & {r["stem"] for r in frozen}
    assert not {r["target"] for r in add.load_references()} & {r["target"] for r in frozen}
    # the two papers the frozen run had to drop for missing text are still recorded there as dropped
    for stem, reason in (("kral2025_purpurogallin_carboxamides_influenza", "no_synthesis_in_paper"), ("singh2025_lignan_monoterpenoid_xanthine_oxidase", "route_not_explicit")):
        document = json.loads((run3.OUT / "references" / f"{stem}.json").read_text(encoding="utf-8"))
        assert document["decision"] == "excluded" and document["exclusion_reason"] == reason


def test_a_synthetic_record_is_judged_with_protocol_3_s_own_rule(refs) -> None:
    ref = refs[0]
    from_tree = {"type": "mol", "smiles": ref["tree"]["smiles"], "children": ref["tree"]["children"], "scores": {"state score": 1.0}}
    row = run3.target_row(ref, {"status": "completed", "routes": [from_tree], "statistics": {"is_solved": True}})
    assert row["m2_10"] and row["pool"] and not row["same_materials_any"]
