"""The Molecular Surface Area (3D) calculator carries five of its numbers as numbers, and a derived score reads them only at the settings that make them one thing (`docs/DERIVED_SCORES_DESIGN.md`, section 12).

Until now every line was text (`'361.31'`), which a score must not rest on: it would move with a display setting. The producer holds the numbers, so the producer hands them over: the same `Fact`, its `value` the float and its
`display_value` still the rounded text. Five are typed (the accessible area, its hydrophobic and polar parts, and the van der Waals area and volume); ASA+ and ASA- stay text, because they are the sum of the area of the atoms whose
Gasteiger charge is above or below nothing, and that sign is decided by tiny charges (7% of caffeine's accessible area sits on atoms whose charge is under 0.02 in size).

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/surface_lines.json` is: every line, label, unit, basis and table-cell text of the calculator over `tests/conformer_panel.py`'s molecules and every way
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

FIXTURE = Path(__file__).parent / "fixtures" / "surface_lines.json"

#: Every way of asking: the defaults, three probes (the label of the first line carries a probe that is not 1.4), the major microspecies with and without another probe, and four decimals.
ASKS = {
    "default": {},
    "probe 1.2": {"solvent_radius": 1.2},
    "probe 0": {"solvent_radius": 0.0},
    "probe 2": {"solvent_radius": 2.0},
    "microspecies": {"major_microspecies": True, "pH": 7.4},
    "microspecies probe 2": {"major_microspecies": True, "pH": 7.4, "solvent_radius": 2.0},
    "four decimals": {"decimal_places": 4},
}


def observe(registry, mol, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values and the cells the project table would hold (text only)."""
    try:
        result = registry.compute("surface_analysis", mol, "uuid", dict(parameters))
    except CalculationRefusal as refusal:
        return {"refused": refusal.code}
    return {
        "state": result.cache_state.value,
        "error": result.error,
        "summary": result.error_summary,
        "inapplicable": result.inapplicable,
        "method": result.provenance.method,
        "provenance_keys": sorted(result.provenance.parameters),
        "lines": list(result.matched),
        "facts": [[f.category.value, f.label, f.display_value, f.units, f.source, f.basis.value] for f in result.facts],
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "surface_analysis", "Molecular Surface Area (3D)")],
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
def test_no_line_label_unit_or_cell_text_moved(registry, golden, molecules, ask):
    moved = {
        f"{name} | {ask}": seen
        for name, mol in molecules.items()
        if (seen := observe(registry, mol, ASKS[ask])) != golden[f"{name} | {ask}"]
    }
    assert not moved, f"what a person sees moved for: {sorted(moved)}"
