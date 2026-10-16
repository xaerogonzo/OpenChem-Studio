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
#: rings and a basic amine (the pKa line and the microspecies option have something to say), a zwitterion, a salt the registry reduces to its parent, a salt and a metal complex it refuses, and a metal ion.
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
