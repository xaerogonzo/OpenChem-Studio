"""The Dipole Moment calculator carries its MAGNITUDE as a number, and a derived score reads it only when the dipole means one thing (`docs/DERIVED_SCORES_DESIGN.md`, section 12).

Until now its first line was text (`'1.62'`), which a score must not rest on: it would move with a display setting. The producer holds the number, so the producer hands it over: the same `Fact`, its `value` the float and its
`display_value` still the rounded text. The three components stay text: they are the dipole in the conformer's own frame, so the same molecule turned over gives other components, and no score may rest on a frame.

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/dipole_lines.json` is: every line, label, unit, basis, arrow and table-cell text of the calculator over `tests/conformer_panel.py`'s molecules and every way
of asking, recorded from the code BEFORE the change. `observe` is the one function that produced the fixture and that reads it back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem.bootstrap import build_service_container
from openchem.chem.result_reduction import reduce_result
from openchem.domain.calculator import CalculationRefusal
from tests.conformer_panel import panel

FIXTURE = Path(__file__).parent / "fixtures" / "dipole_lines.json"

#: The three charge models by their stored codes, written out here and not read from the producer.
GASTEIGER = "gasteiger"
EEM = "eem_bultinck2002_part1"
QEQ = "qeq_rg1991_lambda_half_h_experimental"

#: Every way of asking: each charge model, and the default at four decimals (which the rounding of the line must follow and the typed number must not).
ASKS = {
    "default": {},
    "gasteiger": {"charge_model": GASTEIGER},
    "eem": {"charge_model": EEM},
    "qeq": {"charge_model": QEQ},
    "four decimals": {"decimal_places": 4},
}


def observe(registry, mol, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values, the arrow and the cells the project table would hold (text only)."""
    try:
        result = registry.compute("dipole_moment", mol, "uuid", dict(parameters))
    except CalculationRefusal as refusal:
        return {"refused": refusal.code}
    return {
        "state": result.cache_state.value,
        "error": result.error,
        "summary": result.error_summary,
        "inapplicable": result.inapplicable,
        "name": result.name,
        "method": result.provenance.method,
        "provenance_keys": sorted(result.provenance.parameters),
        "lines": list(result.matched),
        "facts": [[f.category.value, f.label, f.display_value, f.units, f.source, f.basis.value] for f in result.facts],
        "arrows": [[a.units, a.label, [round(v, 6) for v in a.vector], [round(v, 6) for v in a.anchor]] for a in result.spatial],
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "dipole_moment", "Dipole Moment")],
    }


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def molecules():
    return panel()


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_covers_every_molecule_asked_every_way(golden, molecules):
    assert set(golden) == {f"{name} | {ask}" for name in molecules for ask in ASKS}


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_no_line_label_unit_arrow_or_cell_text_moved(registry, golden, molecules, ask):
    moved = {
        f"{name} | {ask}": seen
        for name, mol in molecules.items()
        if (seen := observe(registry, mol, ASKS[ask])) != golden[f"{name} | {ask}"]
    }
    assert not moved, f"what a person sees moved for: {sorted(moved)}"
