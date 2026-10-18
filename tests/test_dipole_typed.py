"""The Dipole Moment calculator carries its MAGNITUDE as a number, and a derived score reads it only when the dipole means one thing (`docs/DERIVED_SCORES_DESIGN.md`, section 11).

Until now its first line was text (`'1.62'`), which a score must not rest on: it would move with a display setting. The producer holds the number, so the producer hands it over: the same `Fact`, its `value` the float and its
`display_value` still the rounded text. The three components stay text: they are the dipole in the conformer's own frame, so the same molecule turned over gives other components, and no score may rest on a frame.

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/dipole_lines.json` is: every line, label, unit, basis, arrow and table-cell text of the calculator over `tests/conformer_panel.py`'s molecules and every way
of asking, recorded from the code BEFORE the change. `observe` is the one function that produced the fixture and that reads it back.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.bootstrap import build_service_container
from openchem.chem.result_reduction import reduce_result
from openchem.domain.calculator import CalculationRefusal
from openchem.domain.score_outputs import APPROVED, approved_output
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
    detail = {k: {f: (v, golden[k].get(f)) for f, v in seen.items() if v != golden[k].get(f)} for k, seen in moved.items()}
    assert not moved, f"what a person sees moved for: {sorted(moved)} DETAIL {detail!r}"


# --- the magnitude is a number, and it is the one the line rounds ----------------------------------------------------------------------------------


_DIPOLE = "calculator:dipole_moment:Dipole"
_COMPONENTS = ("Dipole X", "Dipole Y", "Dipole Z")


def _compute(registry, mol, parameters: dict):
    return registry.compute("dipole_moment", mol, "uuid", dict(parameters))


def _typed(result) -> list:
    return [f for f in result.facts if isinstance(f.value, float)]


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_the_magnitude_is_the_one_typed_number_and_it_is_the_one_the_line_rounds(registry, molecules, ask):
    places = ASKS[ask].get("decimal_places", 2)
    computed = 0
    for name, mol in molecules.items():
        result = _compute(registry, mol, ASKS[ask])
        if result.cache_state.value == "failed":
            assert not _typed(result), f"{name}: a refusal has no number to type"
            continue
        computed += 1
        typed = _typed(result)
        assert [f.label for f in typed] == ["Dipole"], name
        fact = typed[0]
        assert fact.units == "Debye" and math.isfinite(fact.value) and fact.value >= 0, name
        assert fact.display_value == f"{fact.value:.{places}f}", name
        assert fact.value == result.provenance.parameters["debye"], f"{name}: the typed number is the one the provenance records, unrounded"
        assert result.matched[0] == f"Dipole: {fact.value:.{places}f} Debye", name
        assert all(isinstance(fact.value, str) for fact in result.facts if fact.label in _COMPONENTS), f"{name}: the three components stay text"
    assert computed >= 12, "the panel computes for most molecules under every model"


def test_a_model_that_declines_a_molecule_leaves_no_typed_number(registry, molecules):
    for name in ("chloroform", "dimethyl sulfoxide", "sodium acetate"):
        result = _compute(registry, molecules[name], ASKS["eem"])
        assert result.cache_state.value == "failed" and result.inapplicable and not _typed(result), name


def test_the_project_table_cell_holds_the_exact_number_and_shows_the_rounded_text(registry, molecules):
    result = _compute(registry, molecules["aspirin"], {})
    [(column, cell)] = [(c, k) for c, k in reduce_result(result, "dipole_moment", "Dipole Moment") if c.column_id == _DIPOLE]
    assert column.units == "Debye" and column.numeric
    assert cell.text == f"{cell.value:.2f}" and cell.value == result.provenance.parameters["debye"]
    assert cell.value != float(cell.text), "the exact number, not the rounded one (aspirin's is not a two-decimal number)"


def test_the_entry_is_the_magnitude_in_debye_of_the_whole_structure_and_nothing_else_of_the_report_is_approved():
    entry = approved_output(_DIPOLE)
    assert entry is not None and entry.unit == "D" and entry.carried_as == "Debye" and entry.input == "geometry"
    assert entry.whole_structure and entry.run_with == "gasteiger_neutral"
    assert [e.output_id for e in APPROVED if e.output_id.startswith("calculator:dipole_moment:")] == [_DIPOLE], "the components are in the conformer's own frame, and the notes are text"


# --- what the number is, reproduced by a route that shares no code with the producer ---------------------------------------------------------------

#: One elementary charge times one angstrom, in debye (CODATA: 1 D = 3.33564095e-30 C m, e = 1.602176634e-19 C), written here and not read from the producer.
_E_ANGSTROM_IN_DEBYE = 4.80320471


def _gasteiger_dipole(mol, origin: str = "mass") -> float:
    """Gasteiger's partial charges from RDKit's own routine, and the point-charge dipole about the centre of mass (or the unweighted centroid) by numpy over the atom positions."""
    charged = Chem.Mol(mol)
    AllChem.ComputeGasteigerCharges(charged)
    charges = np.nan_to_num(np.array([float(atom.GetProp("_GasteigerCharge")) for atom in charged.GetAtoms()]))
    xyz = mol.GetConformer().GetPositions()
    table = Chem.GetPeriodicTable()
    masses = np.array([table.GetAtomicWeight(atom.GetAtomicNum()) for atom in mol.GetAtoms()])
    centre = (masses[:, None] * xyz).sum(axis=0) / masses.sum() if origin == "mass" else xyz.mean(axis=0)
    return float(np.linalg.norm((charges[:, None] * (xyz - centre)).sum(axis=0)) * _E_ANGSTROM_IN_DEBYE)


@pytest.mark.parametrize("name", sorted(panel()))
def test_the_gasteiger_magnitude_is_the_point_charge_dipole_about_the_centre_of_mass(registry, molecules, name):
    result = _compute(registry, molecules[name], {})
    assert result.cache_state.value != "failed", name
    assert _typed(result)[0].value == pytest.approx(_gasteiger_dipole(molecules[name]), rel=1e-5, abs=1e-6), name


def test_a_neutral_species_has_the_same_dipole_wherever_it_sits_and_however_it_is_turned(registry, molecules):
    """It is the molecule's, not the frame's: moving or turning the conformer moves the three components and not the magnitude."""
    for name in ("acetone", "aspirin", "glycine zwitterion"):
        mol = molecules[name]
        before = _compute(registry, mol, {})
        moved = Chem.Mol(mol)
        conformer = moved.GetConformer()
        rotation = np.array([[0.0, -1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]])
        for index, position in enumerate(conformer.GetPositions() @ rotation.T + np.array([5.0, -3.0, 2.0])):
            conformer.SetAtomPosition(index, position.tolist())
        after = _compute(registry, moved, {})
        assert _typed(after)[0].value == pytest.approx(_typed(before)[0].value, rel=1e-9), name
        components = lambda result: [float(f.value) for f in result.facts if f.label in _COMPONENTS]  # noqa: E731
        assert components(after) != pytest.approx(components(before), abs=0.05), f"{name}: the components follow the frame, which is why none of them is approved"


def test_a_charged_species_has_a_dipole_that_depends_on_the_origin_and_the_result_records_it(registry, molecules):
    """Acetate about its centre of mass and about the centroid of its atoms: two reasonable origins, more than a debye apart. The calculator says so in its own line and records `origin_independent`."""
    for name, net in (("acetate", -1), ("ammonium", 1), ("glycine zwitterion", 0), ("aspirin", 0)):
        result = _compute(registry, molecules[name], {})
        assert result.provenance.parameters["origin_independent"] is (net == 0), name
    mass, centroid = _gasteiger_dipole(molecules["acetate"]), _gasteiger_dipole(molecules["acetate"], "centroid")
    assert abs(mass - centroid) > 1.0, (mass, centroid)
    assert _gasteiger_dipole(molecules["aspirin"]) == pytest.approx(_gasteiger_dipole(molecules["aspirin"], "centroid"), rel=1e-6), "a neutral species does not care where the origin is"
