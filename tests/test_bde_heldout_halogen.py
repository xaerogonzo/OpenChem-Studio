"""The halogen arm's references (`benchmarks/bde_heldout/candidates_halogen.json`, from `extract_atct_halogen.py`, for `benchmarks/restart_v3/PREREGISTRATION.md`).

Like the first held-out arm's test, this recomputes every bond enthalpy from the stored ATcT numbers and checks each bond's structure, instead of restating the values. What it adds is the SCOPE
the six bonds were chosen under, so a seventh bond cannot be added after a result is seen without a test going red.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "bde_heldout"
_BDE = Path(__file__).parent.parent / "benchmarks" / "bde"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# `extract_atct_halogen` imports its sibling by the bare name `extract_atct`, so that name is registered first.
extract = _load("extract_atct", "extract_atct.py")
halogen = _load("extract_atct_halogen", "extract_atct_halogen.py")
BONDS = json.loads((_DIRECTORY / "candidates_halogen.json").read_text(encoding="utf-8"))["bonds"]
FIRST_RUN = json.loads((_BDE / "reference_values.json").read_text(encoding="utf-8"))["bonds"]
FIRST_HELD_OUT = json.loads((_DIRECTORY / "candidates.json").read_text(encoding="utf-8"))["bonds"]


def test_the_arm_is_six_halogen_bonds_and_the_list_in_the_file_is_the_list_in_the_code():
    assert len(BONDS) == 6 == len(halogen.HALOGEN_PAIRS)
    assert [(b["parent"], b["radical"]) for b in BONDS] == [(p, r) for p, _s, _a, r in halogen.HALOGEN_PAIRS]
    assert sorted(b["element"] for b in BONDS) == ["C"] * 6, "every bond is a C-H bond"


@pytest.mark.parametrize("bond", BONDS, ids=lambda b: b["name"])
def test_every_bond_is_the_stored_enthalpies_combined_as_the_definition_says(bond):
    dh = (bond["radical_dfH298_kj"] + bond["hydrogen_atom_dfH298_kj"] - bond["parent_dfH298_kj"]) / extract.KJ_PER_KCAL
    unc = math.sqrt(bond["parent_uncertainty_kj"] ** 2 + bond["radical_uncertainty_kj"] ** 2 + bond["hydrogen_atom_uncertainty_kj"] ** 2) / extract.KJ_PER_KCAL
    assert bond["dh298_kcal"] == pytest.approx(dh, abs=1e-3) and bond["uncertainty_kcal"] == pytest.approx(unc, abs=1e-3)
    assert bond["uncertainty_kcal"] <= 1.0, "the first run's rule for a deciding bond"
    assert not bond["excluded"]


@pytest.mark.parametrize("bond", BONDS, ids=lambda b: b["name"])
def test_every_bond_names_a_real_carbon_with_a_hydrogen_and_the_scope_it_was_chosen_under(bond):
    from rdkit import Chem

    mol = Chem.AddHs(Chem.MolFromSmiles(bond["smiles"]))
    atom = mol.GetAtomWithIdx(bond["atom"])
    elements = {a.GetSymbol() for a in mol.GetAtoms()}
    assert atom.GetSymbol() == "C" and any(n.GetAtomicNum() == 1 for n in atom.GetNeighbors())
    assert elements <= {"H", "C", "O", "F", "Cl"} and elements & {"F", "Cl"}, "a halogen, and no bromine: the table holds no bromo radical of this kind"
    assert sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() > 1) <= 10


def test_no_halogen_bond_is_one_the_first_run_or_the_first_held_out_arm_computed():
    seen = {extract.site_class(b["smiles"], b["atom"]) for b in FIRST_RUN} | {extract.site_class(b["smiles"], b["atom"]) for b in FIRST_HELD_OUT}
    assert [b["name"] for b in BONDS if extract.site_class(b["smiles"], b["atom"]) in seen] == []


def test_the_table_row_chosen_is_the_neutral_one_where_a_name_is_shared_with_an_anion():
    rows = [
        {"name": "Formyl fluoride", "formula": "CHFO  (g)", "units": "kJ/mol"},
        {"name": "Formyl fluoride", "formula": "[FCO]-  (g)", "units": "kJ/mol"},
    ]
    assert halogen.neutral_gas_row(rows, "Formyl fluoride")["formula"] == "CHFO  (g)"
    with pytest.raises(SystemExit):
        halogen.neutral_gas_row(rows[1:], "Formyl fluoride")
