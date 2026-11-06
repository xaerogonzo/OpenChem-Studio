"""Jiroušková 2009's EEM as a method of `geometry_partial_charge`, offered only for chlorine, bromine and sulfur (`eem_second_models_preregistration.md` sections 19 and 20).

The solver is held by test_eem_second_models.py; this file holds the wiring and the scope: the refusal of a molecule with none of the checked elements, the warning every result
carries, and that the committed measurement still stands behind the sentences quoted on screen.
"""

from __future__ import annotations

import json
import pathlib
import uuid

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import geometry_charges as gc
from openchem.chem import typed_eem as te
from openchem.domain.refusal_kinds import RefusalKind, refusal_kind_of

M = gc.EEM_JIROUSKOVA2009_B3LYP_MK
RESULT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "charges" / "models" / "eem_second_models_results" / "model_j_halogen_sulfur.json"


def _run(smiles, **params):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    return gc.compute_geometry_charges(mol, str(uuid.uuid4()), {"method": M, **params})


def _code(result):
    return result.provenance.parameters.get("refusal")


def test_method_is_appended_last_and_labelled_with_its_scope():
    assert gc.GEOMETRY_CHARGE_METHODS[-1] == M
    assert "Cl, Br, S" in gc.GEOMETRY_CHARGE_METHOD_LABELS[M]


@pytest.mark.parametrize("smiles", ["CCl", "CBr", "CSC", "Clc1ccccc1Cl", "ClC(Cl)Cl"])
def test_a_molecule_with_chlorine_bromine_or_sulfur_is_computed_and_sums_to_its_net_charge(smiles):
    r = _run(smiles)
    assert r.values and sum(r.values.values()) == pytest.approx(0.0, abs=1e-9)


def test_chlorine_is_negative_and_the_hydrogens_positive_in_chloromethane():
    r = _run("CCl")
    symbols = [a.GetSymbol() for a in Chem.AddHs(Chem.MolFromSmiles("CCl")).GetAtoms()]
    assert r.values[symbols.index("Cl")] < 0
    assert all(r.values[i] > 0 for i, s in enumerate(symbols) if s == "H")


@pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1", "CC(=O)N"])
def test_a_molecule_with_none_of_the_checked_elements_is_refused_and_it_is_a_limit(smiles):
    r = _run(smiles)
    assert not r.values and _code(r) == gc.REFUSE_OUTSIDE_MEASURED_SCOPE
    assert refusal_kind_of(gc.REFUSE_OUTSIDE_MEASURED_SCOPE) is RefusalKind.LIMIT


def test_the_other_eem_methods_still_compute_that_molecule():
    assert _run("CCO", method=gc.EEM_BULTINCK2002_PART1).values
    assert _run("CCO", method=gc.EEM_NEEMP2016_CCD_GEN_NPA).values


@pytest.mark.parametrize("smiles,code", [
    ("CS(C)=O", te.REFUSE_TYPE_NOT_PARAMETERISED),  # sulfur bonded to oxygen: no type in this model
    ("CC#N", None),
    ("CI", None),
])
def test_what_the_model_cannot_type_is_refused_by_name(smiles, code):
    r = _run(smiles)
    assert not r.values
    if code:
        assert _code(r) == code


def test_every_result_carries_the_measured_error_beside_it():
    s = _run("CCl").provenance.parameters["summary"]
    assert "0.23 e" in s and "0.68 e" in s
    assert _run("CCl").provenance.parameters["validation"]["scope_id"] == gc.JIROUSKOVA_SCOPE_ID


def test_a_charged_molecule_is_computed_with_a_warning_that_it_was_not_checked():
    s = _run("C[S+](C)C").provenance.parameters
    # a sulfonium has a three-bonded sulfur: if the model types it, the note must say charged molecules were not checked; if not, it is refused by name
    if s.get("refusal"):
        assert s["refusal"] == te.REFUSE_TYPE_NOT_PARAMETERISED
    else:
        assert "charged" in s["summary"]
    r = _run("[O-]c1ccc(Cl)cc1")
    if r.values:
        assert "charged" in r.provenance.parameters["summary"]


def test_the_quoted_numbers_are_the_committed_result():
    """The sentences shown to a person quote this measurement, so the measurement must say it (a change of either fails here, not on screen)."""
    r = json.loads(RESULT.read_text(encoding="utf-8"))
    assert r["judge"]["offer_for_these_elements"] is True
    assert round(r["worst_atom_J"], 2) == 0.23 and round(r["mean_abs_J"], 2) == 0.09
    assert r["molecules"] == 26 and r["scope_atoms"] == 40
    assert "0.23 e" in gc.JIROUSKOVA_NOTE and "0.09 e" in gc.JIROUSKOVA_NOTE and "40 atoms" in gc.JIROUSKOVA_NOTE
    assert round(r["mean_abs_N_on_common"], 3) == 0.125 and "0.125 e" in gc.JIROUSKOVA_VALIDATION_SCOPE


def test_the_carbon_figures_quoted_come_from_the_panel_rows():
    r = json.loads(RESULT.read_text(encoding="utf-8"))
    errors = [abs(row["J"][i] - row["mk"][i]) for row in r["rows"].values() if row["J"] for i, e in enumerate(row["elements"]) if e == "C"]
    assert len(errors) == 85 and round(sum(errors) / len(errors), 2) == 0.18  # the note says 0.18 e on average over 85 carbons
    assert round(max(errors), 2) == 0.68 and "0.68 e" in gc.JIROUSKOVA_NOTE
