"""The Phase B evidence inventory: generated, not typed, and no count without a locator.

`benchmarks/energetics_props/inventory.json` holds counts read from the held sources; `inventory_report.py` renders them
into `INVENTORY.md` and refuses a malformed inventory. What is held here is the discipline, not the numbers (the books
are copyrighted and not in the repository, so the counts themselves cannot be re-derived in CI): the committed markdown
is exactly what the JSON renders, a count with no locator or an unknown property is an error, and the ceilings the
preregistration quotes in its section 13 are the ones the JSON holds.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "energetics_props"


def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


report = _load("epb_inventory_report", BENCH / "inventory_report.py")
INV = json.loads((BENCH / "inventory.json").read_text(encoding="utf-8"))


def test_committed_markdown_is_what_the_json_renders():
    assert (BENCH / "INVENTORY.md").read_text(encoding="utf-8") == report.render(INV)


def test_the_committed_inventory_is_well_formed():
    report.validate(INV)
    # every source that claims a count has at least one, and every count names a locator
    counted = [s for s in INV["sources"] if s.get("counts")]
    assert len(counted) >= 10
    assert all(c["locator"].strip() for s in counted for c in s["counts"])


def _one_count(inv):
    return next(s for s in inv["sources"] if s.get("counts"))["counts"][0]


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda c: c.update(locator=""), "locator"),
        (lambda c: c.update(locator="   "), "locator"),
        (lambda c: c.update(property="density"), "unknown property"),
        (lambda c: c.update(n=-1), "non-negative"),
        (lambda c: c.update(n=True), "non-negative"),
        (lambda c: c.update(n=3.5), "non-negative"),
        (lambda c: c.update(method="remembered"), "method"),
        (lambda c: c.update(what=""), "what"),
    ],
)
def test_a_malformed_count_is_refused(mutation, message):
    inv = copy.deepcopy(INV)
    mutation(_one_count(inv))
    with pytest.raises(report.InventoryError, match=message):
        report.validate(inv)


def test_a_duplicated_source_and_a_bad_ceiling_are_refused():
    inv = copy.deepcopy(INV)
    inv["sources"].append(copy.deepcopy(inv["sources"][0]))
    with pytest.raises(report.InventoryError, match="duplicated"):
        report.validate(inv)
    inv = copy.deepcopy(INV)
    inv["upper_bounds"][0]["n_largest"] = inv["upper_bounds"][0]["n"] + 1
    with pytest.raises(report.InventoryError, match="n_largest"):
        report.validate(inv)


def test_a_printed_error_needs_a_locator():
    inv = copy.deepcopy(INV)
    src = next(s for s in inv["sources"] if s.get("printed_errors"))
    src["printed_errors"][0]["locator"] = ""
    with pytest.raises(report.InventoryError, match="printed error"):
        report.validate(inv)


def test_a_sub_count_never_exceeds_its_parent():
    # the Encyclopedia lists 'of those' counts under 'covered entries printing ...': a child cannot be bigger
    klap = next(s for s in INV["sources"] if s["id"] == "klapotke2021")
    counts = klap["counts"]
    parent = None
    for c in counts:
        if c["what"].startswith("covered entries"):
            parent = c
        elif c["what"].startswith("of those"):
            assert parent is not None and c["n"] <= parent["n"], c["what"]


def test_the_preregistration_quotes_the_inventory_ceilings():
    text = (BENCH / "PREREGISTRATION.md").read_text(encoding="utf-8")
    table = text.split("**The ceilings", 1)[1].split("What this does and does not say", 1)[0]
    cells = {c.strip() for row in table.splitlines() if row.startswith("|") for c in row.strip("|").split("|")}
    for ub in INV["upper_bounds"]:
        if ub["property"].startswith(("crystal density", "density, any", "condensed-phase", "enthalpy of formation",
                                       "melting point", "decomposition")):
            assert str(ub["n"]) in cells or any(cell.startswith(f"{ub['n']} ") for cell in cells), ub["property"]
            assert any(cell.startswith(str(ub["n_largest"])) for cell in cells), ub["property"]


def test_the_preregistration_is_a_draft_with_every_section():
    text = (BENCH / "PREREGISTRATION.md").read_text(encoding="utf-8")
    assert "Status: DRAFT" in text.splitlines()[2]
    headings = re.findall(r"^## (\d+)\. ", text, flags=re.MULTILINE)
    assert headings == [str(i) for i in range(1, 19)]    # 15 is Amendment 1, 16 is Amendment 2, 17 is Amendment 3 (2026-10-27), 18 is Amendment 4 (2026-10-28)
