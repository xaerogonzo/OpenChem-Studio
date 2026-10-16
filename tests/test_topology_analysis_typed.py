"""The Topology Analysis calculator carries the graph indices of its report as NUMBERS (typing the values of the report calculators that carry rounded text, `docs/DERIVED_SCORES_DESIGN.md` section 3).

Until now every line of the report was text (`'6.11'`) that the project table parsed back, so a derived score over the Randic index would have changed with the decimal-places setting. The producer holds
the number, so the producer hands it over: the same `Fact`, with its `value` the number and its `display_value` still the rounded text.

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/topology_analysis_lines.json` is: every line, label, unit, basis and table-cell text of the calculator over a panel of molecules and
every way of asking (the decimal places it is given, and the ones it is not allowed to take), recorded from the code BEFORE the change. `observe` is the one function that produced the fixture and that
reads it back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.result_reduction import reduce_result
from openchem.domain.calculator import CalculationRefusal

FIXTURE = Path(__file__).parent / "fixtures" / "topology_analysis_lines.json"

#: Chosen for what each exercises: a one-atom molecule (every index is zero), a chain whose Szeged index must equal its Wiener index and a ring and a cage it must exceed it on, a fused system, a molecule
#: whose two stereogenic centres are not asymmetric atoms (the module's own example), a ring of 18, a zwitterion, a salt the registry reduces to its parent, a salt and a metal complex it refuses, and a metal ion.
PANEL = {
    "water": "O",
    "methane": "C",
    "ethanol": "CCO",
    "butane": "CCCC",
    "isobutane": "CC(C)C",
    "cyclopropane": "C1CC1",
    "benzene": "c1ccccc1",
    "pyridine": "c1ccncc1",
    "naphthalene": "c1ccc2ccccc2c1",
    "cubane": "C12C3C4C1C5C2C3C45",
    "adamantane": "C1C2CC3CC1CC(C2)C3",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "L-alanine": "N[C@@H](C)C(=O)O",
    "trans-1,4-dimethylcyclohexane": "C[C@H]1CC[C@@H](C)CC1",
    "18-crown-6": "C1COCCOCCOCCOCCOCCO1",
    "glycine zwitterion": "[NH3+]CC(=O)[O-]",
    "metformin hydrochloride": "CN(C)C(=N)NC(N)=N.Cl",
    "sodium acetate": "CC(=O)[O-].[Na+]",
    "ionic ferrocene": "[Fe+2].c1cc[cH-]c1.c1cc[cH-]c1",
    "tetramethylsilane": "C[Si](C)(C)C",
    "copper(II)": "[Cu+2]",
}

#: Every way of asking: the default, the decimal places at both ends of their range, one past each end (clamped) and one that is not a number (falls back to the default).
ASKS = {
    "default": {},
    "0 places": {"decimal_places": 0},
    "1 place": {"decimal_places": 1},
    "8 places": {"decimal_places": 8},
    "99 places": {"decimal_places": 99},
    "not a number": {"decimal_places": "x"},
}


def observe(registry, smiles: str, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values, and the cells the project table would hold (text only)."""
    mol = Chem.MolFromSmiles(smiles)
    try:
        result = registry.compute("topology_analysis", mol, "uuid", dict(parameters))
    except CalculationRefusal as refusal:
        return {"refused": refusal.code}
    return {
        "state": result.cache_state.value,
        "error": result.error,
        "summary": result.error_summary,
        "inapplicable": result.inapplicable,
        "method": result.provenance.method,
        "lines": list(result.matched),
        "facts": [[f.category.value, f.label, f.display_value, f.units, f.source, f.basis.value] for f in result.facts],
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "topology_analysis", "Topology Analysis")],
    }


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_covers_every_molecule_asked_every_way(golden):
    assert set(golden) == {f"{name} | {ask}" for name in PANEL for ask in ASKS}


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_no_line_label_unit_basis_or_cell_text_moved(registry, golden, ask):
    moved = {
        f"{name} | {ask}": observe(registry, smiles, ASKS[ask])
        for name, smiles in PANEL.items()
        if observe(registry, smiles, ASKS[ask]) != golden[f"{name} | {ask}"]
    }
    assert not moved, f"what a person sees moved for: {sorted(moved)}"
