"""The Polarizability calculator carries its default number as a NUMBER (typing the values of the report calculators that carry rounded text, `docs/DERIVED_SCORES_DESIGN.md` section 3).

Until now its first line was text (`'3.82'`) the batch table parsed back, so a derived score over it would have changed with a display setting. The producer holds the number, so the
producer hands it over: the same `Fact`, with its `value` the float and its `display_value` still the rounded text.

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/polarizability_lines.json` is: every line, label, unit, basis and table-cell text of the calculator over a panel of
molecules and every way of asking (all three methods, the microspecies option, an unknown method label), recorded from the code BEFORE the change. `observe` is the one function that produced the
fixture and that reads it back.

**THE TYPED NUMBER IS ONLY THE DEFAULT ANSWER.** The calculator has three estimators behind one id and one fact label, and an option that computes the major microspecies instead of the drawing. A score
reads one number under one id, so a number that came from Miller's method or from another structure must not be readable as the default: only the Jensen answer on the drawing is typed, and the others
stay text (a score over them is refused, never a different number).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.result_reduction import reduce_result
from openchem.domain.calculator import CalculationRefusal

FIXTURE = Path(__file__).parent / "fixtures" / "polarizability_lines.json"

#: Chosen for what each exercises: a one-atom-type molecule, an aromatic, two halogenated ones the three methods separate on (CBr4 by 16%), an acid and an amino acid the microspecies option
#: changes, a salt, an element outside Jensen's table, and a metal ion.
PANEL = {
    "water": "O",
    "methane": "C",
    "ethanol": "CCO",
    "benzene": "c1ccccc1",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "carbon tetrachloride": "ClC(Cl)(Cl)Cl",
    "carbon tetrabromide": "BrC(Br)(Br)Br",
    "acetic acid": "CC(=O)O",
    "glycine": "NCC(=O)O",
    "ammonium chloride": "[NH4+].[Cl-]",
    "tetramethylsilane": "C[Si](C)(C)C",
    "copper(II)": "[Cu+2]",
}

#: Every way of asking: the default, each method by its label, the microspecies option with the default and with a Miller method, and a label this build does not know (which falls back to Jensen).
ASKS = {
    "default": {},
    "jensen": {"method": "Jensen (additive)"},
    "miller ahc": {"method": "Miller ahc"},
    "miller ahp": {"method": "Miller ahp"},
    "microspecies": {"major_microspecies": True, "pH": 7.4},
    "microspecies miller ahp": {"major_microspecies": True, "pH": 7.4, "method": "Miller ahp"},
    "unknown label": {"method": "from a later version"},
}


def observe(registry, smiles: str, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values, and the cells the project table would hold (text only)."""
    mol = Chem.MolFromSmiles(smiles)
    try:
        result = registry.compute("polarizability", mol, "uuid", dict(parameters))
    except CalculationRefusal as refusal:
        return {"refused": refusal.code}
    seen = {
        "state": result.cache_state.value,
        "error": result.error,
        "summary": result.error_summary,
        "inapplicable": result.inapplicable,
        "method": result.provenance.method,
        "lines": list(result.matched),
        "facts": [[f.category.value, f.label, f.display_value, f.units, f.source, f.basis.value] for f in result.facts],
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "polarizability", "Polarizability")],
    }
    return seen


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


def _typed(result) -> list:
    return [f for f in result.facts if isinstance(f.value, float)]


def _compute(registry, smiles: str, parameters: dict):
    return registry.compute("polarizability", Chem.MolFromSmiles(smiles), "uuid", dict(parameters))


@pytest.mark.parametrize("name", sorted(PANEL))
def test_the_default_answer_has_its_number_typed_and_it_is_the_one_the_line_rounds(registry, name):
    try:
        result = _compute(registry, PANEL[name], {})
    except CalculationRefusal:
        return  # the registry declined before any calculation (a mixture): there is no number to type
    if result.cache_state.value == "failed":
        assert not _typed(result)
        return
    typed = _typed(result)
    assert [f.label for f in typed] == ["Molecular polarizability"], name
    fact = typed[0]
    assert math.isfinite(fact.value) and fact.units == "A^3" and fact.display_value == f"{fact.value:.2f}"
    assert fact.value == result.provenance.parameters["polarizability_a3"], "the typed number is the one the provenance records, unrounded"
    assert result.matched[0] == f"Molecular polarizability: {fact.value:.2f} A^3"


@pytest.mark.parametrize("ask", ["miller ahc", "miller ahp", "microspecies", "microspecies miller ahp"])
def test_an_answer_from_another_method_or_another_structure_is_never_typed(registry, ask):
    for smiles in (PANEL["benzene"], PANEL["acetic acid"], PANEL["carbon tetrabromide"]):
        result = _compute(registry, smiles, ASKS[ask])
        assert not _typed(result), f"{ask} on {smiles}: a number a score could read as the default"


def test_the_jensen_label_and_an_unknown_label_are_the_default_and_are_typed(registry):
    assert [f.value for f in _typed(_compute(registry, PANEL["benzene"], ASKS["jensen"]))] == [f.value for f in _typed(_compute(registry, PANEL["benzene"], {}))]
    assert _typed(_compute(registry, PANEL["benzene"], ASKS["unknown label"])), "an unknown label runs Jensen, so it is the default answer"


def test_the_project_table_cell_holds_the_exact_number_and_shows_the_rounded_text(registry):
    result = _compute(registry, PANEL["aspirin"], {})
    [(column, cell)] = [(c, k) for c, k in reduce_result(result, "polarizability", "Polarizability") if c.label == "Molecular polarizability"]
    assert column.column_id == "calculator:polarizability:Molecular polarizability" and column.units == "A^3" and column.numeric
    assert cell.text == f"{cell.value:.2f}" and cell.value == result.provenance.parameters["polarizability_a3"]
    assert cell.value != float(cell.text), "the exact number, not the rounded one (aspirin's is not a two-decimal number)"
