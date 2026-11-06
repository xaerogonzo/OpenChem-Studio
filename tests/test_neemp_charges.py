"""NEEMP 2016's Ccd2016 EEM as a method of `geometry_partial_charge` (the wiring; the solver is held by test_eem_second_models.py)."""

from __future__ import annotations

import uuid

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import geometry_charges as gc
from openchem.chem import typed_eem as te
from openchem.domain.refusal_kinds import RefusalKind, refusal_kind_of

M = gc.EEM_NEEMP2016_CCD_GEN_NPA


def _run(smiles, **params):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=7) == 0
    return gc.compute_geometry_charges(mol, str(uuid.uuid4()), {"method": M, **params})


def _code(result):
    return result.provenance.parameters.get("refusal")


def test_method_is_appended_and_labelled():
    assert gc.GEOMETRY_CHARGE_METHODS[4] == M  # appended after Ionescu's; Jiroušková's is appended after it
    assert M in gc.GEOMETRY_CHARGE_METHOD_LABELS


def test_charges_sum_to_the_net_charge():
    r = _run("CC(=O)[O-]")
    assert r.values and sum(r.values.values()) == pytest.approx(-1.0, abs=1e-9)
    r = _run("CCO")
    assert sum(r.values.values()) == pytest.approx(0.0, abs=1e-9)


def test_provenance_names_the_source_scheme_and_resonance():
    p = _run("C[N+](=O)[O-]").provenance.parameters
    assert p["resonance"] == te.RESONANCE_AVERAGED
    assert "neemp2016" in p["source"] and "NPA" in p["scheme"]
    assert p["resonance_variable_atoms"] and p["resonance_forms_averaged"] >= 2
    assert p["summary"]


def test_nitro_oxygens_are_equal_when_averaged_and_differ_as_drawn():
    mol = Chem.AddHs(Chem.MolFromSmiles("C[N+](=O)[O-]"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    oxy = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "O"]
    avg = gc.compute_geometry_charges(mol, str(uuid.uuid4()), {"method": M}).values
    drawn = gc.compute_geometry_charges(mol, str(uuid.uuid4()), {"method": M, "resonance": "as_drawn"}).values
    assert abs(avg[oxy[0]] - avg[oxy[1]]) < 0.02  # geometry only
    assert abs(drawn[oxy[0]] - drawn[oxy[1]]) > abs(avg[oxy[0]] - avg[oxy[1]])


def test_refuse_option_refuses_a_resonance_dependent_structure_but_not_others():
    r = _run("C[N+](=O)[O-]", resonance="refuse")
    assert not r.values and _code(r) == te.REFUSE_RESONANCE_DEPENDENT
    assert _run("CCO", resonance="refuse").values


@pytest.mark.parametrize("smiles,code", [
    ("B(C)(C)C", te.REFUSE_TYPE_NOT_PARAMETERISED),
    ("CCI", te.REFUSE_TYPE_NOT_PARAMETERISED),
    ("CC.O", "REFUSE_MULTIPLE_COMPONENTS"),
])
def test_refusals_are_named_and_classified(smiles, code):
    r = _run(smiles)
    assert not r.values and _code(r) == code
    assert refusal_kind_of(code) is RefusalKind.LIMIT


def test_unknown_resonance_value_is_a_bug_not_a_default():
    with pytest.raises(ValueError):
        _run("CCO", resonance="whatever")


def test_other_methods_ignore_the_resonance_option():
    a = _run("C[N+](=O)[O-]", method=gc.EEM_BULTINCK2002_PART1)
    b = _run("C[N+](=O)[O-]", method=gc.EEM_BULTINCK2002_PART1, resonance="refuse")
    assert a.values == b.values and a.values


def test_oxidised_sulfur_and_phosphorus_above_the_bound_carry_a_warning():
    s = _run("CS(=O)(=O)C").provenance.parameters["summary"]
    assert "unreliable" in s
    assert "unreliable" not in _run("CCO").provenance.parameters["summary"]
