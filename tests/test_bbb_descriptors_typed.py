"""The BBB Score Descriptors calculator carries its aromatic ring count as a NUMBER (typing the values of the report calculators that carry rounded text, `docs/DERIVED_SCORES_DESIGN.md` section 3).

Until now every line of the report was text (`'1'`) that the project table parsed back, so a derived score over the aromatic ring count could not read it. The producer holds the number, so the producer hands it over: the
same `Fact`, with its `value` the count and its `display_value` still the text.

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/bbb_descriptors_lines.json` is: every line, label, unit, basis and table-cell text of the calculator over a panel of molecules and every way of
asking (the decimal places it is given and the ones it is not allowed to take, and the major-microspecies option at two pH values), recorded from the code BEFORE the change. `observe` is the one function that produced the
fixture and that reads it back.

**ONE NUMBER OF THE REPORT IS TYPED, AND ONLY FOR THE DEFAULT ANSWER.** The report carries four numbers and a pKa line. Two of them are the always-on heavy-atom count and the always-on polar surface area under other labels, and
MWHBN has a unit the score language cannot write (`(mol/g)^0.5`: the same reason Hansen's parameters wait), so only the aromatic ring count is new and typeable. The option that computes the major microspecies counts the
rings of another structure under the same label, so its answer stays text.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from openchem.bootstrap import build_service_container
from openchem.chem.result_reduction import reduce_result
from openchem.domain import result_codec
from openchem.domain.calculator import CalculationRefusal

FIXTURE = Path(__file__).parent / "fixtures" / "bbb_descriptors_lines.json"

#: Chosen for what each exercises: no ring, one ring, fused and non-fused aromatic systems, two molecules the two aromatic ring counts of this application disagree on (biphenylene and azulene), a drug with three aromatic
#: rings and a basic amine (the pKa line and the microspecies option have something to say), a zwitterion, a salt the registry reduces to its parent, a salt it computes on its largest component (a refusal until group 3 of the refusal audit), a metal complex it refuses, and a metal ion.
PANEL = {
    "water": "O",
    "butane": "CCCC",
    "cyclohexane": "C1CCCCC1",
    "benzene": "c1ccccc1",
    "pyridine": "c1ccncc1",
    "naphthalene": "c1ccc2ccccc2c1",
    "biphenylene": "c1ccc2c(c1)-c1ccccc1-2",
    "azulene": "c1ccc2cccc2cc1",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "propranolol": "CC(C)NCC(O)COc1cccc2ccccc12",
    "sildenafil": "CCCc1nn(C)c2c1nc([nH]c2=O)-c1cc(ccc1OCC)S(=O)(=O)N1CCN(C)CC1",
    "glycine zwitterion": "[NH3+]CC(=O)[O-]",
    "metformin hydrochloride": "CN(C)C(=N)NC(N)=N.Cl",
    "sodium acetate": "CC(=O)[O-].[Na+]",
    "ionic ferrocene": "[Fe+2].c1cc[cH-]c1.c1cc[cH-]c1",
    "copper(II)": "[Cu+2]",
}

#: Every way of asking: the default, the decimal places at both ends of their range, one past the end (clamped) and one that is not a number (falls back to the default), and the major-microspecies option at two pH values.
ASKS = {
    "default": {},
    "0 places": {"decimal_places": 0},
    "8 places": {"decimal_places": 8},
    "99 places": {"decimal_places": 99},
    "not a number": {"decimal_places": "x"},
    "microspecies 7.4": {"major_microspecies": True, "pH": 7.4},
    "microspecies 2": {"major_microspecies": True, "pH": 2.0},
}


def observe(registry, smiles: str, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values, and the cells the project table would hold (text only)."""
    mol = Chem.MolFromSmiles(smiles)
    try:
        result = registry.compute("bbb_descriptors", mol, "uuid", dict(parameters))
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
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "bbb_descriptors", "BBB Score Descriptors")],
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


AROMATIC_RINGS = "Aromatic rings"
OUTPUT_ID = "calculator:bbb_descriptors:Aromatic rings"


def _compute(registry, smiles: str, parameters: dict | None = None):
    return registry.compute("bbb_descriptors", Chem.MolFromSmiles(smiles), "uuid", dict(parameters or {}))


def _typed(result) -> dict:
    return {f.label: f.value for f in result.facts if not isinstance(f.value, str)}


def _completed(registry, name: str, parameters: dict | None = None):
    """The result for a panel molecule, or None where the registry declines it (a salt, a metal complex): there is no number to type."""
    try:
        result = _compute(registry, PANEL[name], parameters)
    except CalculationRefusal:
        return None
    return result if result.cache_state.value == "completed" else None


def _default_asks() -> list[str]:
    return [ask for ask, parameters in ASKS.items() if not parameters.get("major_microspecies")]


@pytest.mark.parametrize("name", sorted(PANEL))
def test_the_aromatic_ring_count_is_the_one_typed_number_and_an_exact_int(registry, name):
    result = _completed(registry, name)
    if result is None:
        return
    typed = _typed(result)
    assert list(typed) == [AROMATIC_RINGS], name
    assert type(typed[AROMATIC_RINGS]) is int and typed[AROMATIC_RINGS] >= 0, "a count, and the project file's codec takes only the exact types"
    assert all(isinstance(f.value, str) for f in result.facts if f.label != AROMATIC_RINGS), "the other numbers are still text"


@pytest.mark.parametrize("ask", [a for a in ASKS if ASKS[a].get("major_microspecies")])
def test_the_major_microspecies_answer_is_never_typed(registry, ask):
    for name in PANEL:
        result = _completed(registry, name, ASKS[ask])
        if result is not None:
            assert not _typed(result), f"{name} | {ask}: the rings of another structure under the same label"


@pytest.mark.parametrize("ask", _default_asks())
def test_the_line_is_the_typed_count_whatever_the_decimal_places(registry, ask):
    for name in PANEL:
        result = _completed(registry, name, ASKS[ask])
        if result is None:
            continue
        [fact] = [f for f in result.facts if f.label == AROMATIC_RINGS]
        assert fact.display_value == str(fact.value) and fact.units == "", f"{name} | {ask}"


def test_the_count_is_the_one_rdkit_gives_for_the_structure_the_registry_hands_over(registry):
    """Independent of the calculator: RDKit's own function on the drawing (the parent, for a salt)."""
    for name, smiles in PANEL.items():
        result = _completed(registry, name)
        if result is None:
            continue
        mol = Chem.MolFromSmiles("CN(C)C(=N)NC(N)=N" if name == "metformin hydrochloride" else smiles)
        assert _typed(result)[AROMATIC_RINGS] == rdMolDescriptors.CalcNumAromaticRings(mol), name


def test_the_values_a_person_can_check_by_hand(registry):
    expected = {"water": 0, "butane": 0, "cyclohexane": 0, "benzene": 1, "pyridine": 1, "naphthalene": 2, "aspirin": 1, "caffeine": 2, "propranolol": 2, "sildenafil": 3}
    assert {name: _typed(_completed(registry, name))[AROMATIC_RINGS] for name in expected} == expected
    # The module's own worked example: the vendor's sildenafil has 3 aromatic rings, "exact".
    assert expected["sildenafil"] == 3


def test_this_count_and_topology_analysis_s_disagree_on_exactly_two_molecules_of_the_panel(registry):
    """Why THIS count is the one approved. Topology Analysis counts a ring whose ATOMS are all aromatic; RDKit's function wants the ring's BONDS aromatic. Biphenylene's four-membered ring and azulene differ."""
    differ = {}
    for name in PANEL:
        bbb = _completed(registry, name)
        topology = registry.compute("topology_analysis", Chem.MolFromSmiles(PANEL[name]), "uuid", {}) if bbb is not None else None
        if bbb is None:
            continue
        counts = (_typed(bbb)[AROMATIC_RINGS], int([f.display_value for f in topology.facts if f.label == "Aromatic ring count"][0]))
        if counts[0] != counts[1]:
            differ[name] = counts
    assert differ == {"biphenylene": (2, 3), "azulene": (0, 2)}


def test_a_typed_report_is_saved_and_reopened_whole(registry):
    result = _compute(registry, PANEL["sildenafil"])
    restored = result_codec.decode(json.loads(json.dumps(result_codec.encode(result))))
    assert restored == result and _typed(restored) == {AROMATIC_RINGS: 3} and type(_typed(restored)[AROMATIC_RINGS]) is int


def test_the_project_table_cell_holds_the_count_and_shows_the_text(registry):
    result = _compute(registry, PANEL["sildenafil"])
    [(column, cell)] = [(c, k) for c, k in reduce_result(result, "bbb_descriptors", "BBB Score Descriptors") if c.label == AROMATIC_RINGS]
    assert column.column_id == OUTPUT_ID and column.units == "" and column.numeric
    assert cell.text == "3" and cell.value == 3.0


# --- approved as a score output ---------------------------------------------------------------------------------------------------------


def _approved() -> dict:
    from openchem.domain.score_outputs import APPROVED

    return {entry.output_id: entry for entry in APPROVED if entry.output_id.startswith("calculator:bbb_descriptors:")}


def test_exactly_the_aromatic_ring_count_is_approved_from_this_report():
    approved = _approved()
    assert list(approved) == [OUTPUT_ID]
    entry = approved[OUTPUT_ID]
    assert entry.unit == "1" and entry.carried_as == "" and entry.endpoint == "aromatic_ring_count"


def test_the_other_numbers_of_the_report_are_not_approved():
    """Heavy atoms and TPSA are always-on descriptors already; MWHBN's unit cannot be written; the pKa line is the optional tool's."""
    from openchem.domain.score_outputs import approved_output

    for label in ("Heavy atoms", "MWHBN", "TPSA", "pKa (most basic)"):
        assert approved_output(f"calculator:bbb_descriptors:{label}") is None, label


@pytest.mark.parametrize("name", ["sildenafil", "benzene", "caffeine", "naphthalene", "water"])
def test_a_score_reads_the_same_count_whatever_the_decimal_places(registry, name):
    from openchem.domain.score_outputs import accept_value

    entry = _approved()[OUTPUT_ID]
    read = []
    for places in (0, 1, 8):
        [fact] = [f for f in _completed(registry, name, {"decimal_places": places}).facts if f.label == AROMATIC_RINGS]
        read.append(accept_value(entry, fact.value, fact.units))
    assert read[0] == read[1] == read[2] and type(read[0]) is float


def test_the_microspecies_answer_is_refused_by_a_score_and_says_why(registry):
    from openchem.domain.score_formula import Refusal
    from openchem.domain.score_outputs import accept_value

    [fact] = [f for f in _completed(registry, "propranolol", ASKS["microspecies 7.4"]).facts if f.label == AROMATIC_RINGS]
    with pytest.raises(Refusal) as caught:
        accept_value(_approved()[OUTPUT_ID], fact.value, fact.units)
    assert "is text" in str(caught.value) and "default answer" in str(caught.value)
    assert math.isfinite(float(fact.display_value)), "the line still shows the count"
