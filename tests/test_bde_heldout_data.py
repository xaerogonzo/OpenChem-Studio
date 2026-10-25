"""The held-out X-H bonds of the bond-dissociation benchmark (`benchmarks/bde_heldout/`, written for `benchmarks/restart_v2/PREREGISTRATION.md`): the list, its arithmetic, its exclusions and its overlap with the first run.

The data are the ATcT enthalpies of formation as the table printed them, so the tests recompute every bond enthalpy from the stored numbers and check the structure of each bond, rather than restating the values.
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


def _load():
    spec = importlib.util.spec_from_file_location("bde_heldout_extract_atct", _DIRECTORY / "extract_atct.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bde_heldout_extract_atct"] = module
    spec.loader.exec_module(module)
    return module


extract = _load()
BONDS = json.loads((_DIRECTORY / "candidates.json").read_text(encoding="utf-8"))["bonds"]
CROSS = json.loads((_DIRECTORY / "crosscheck_v1.json").read_text(encoding="utf-8"))
FIRST_RUN = json.loads((_BDE / "reference_values.json").read_text(encoding="utf-8"))["bonds"]


def test_the_list_is_thirty_bonds_of_which_twenty_seven_decide():
    assert len(BONDS) == 30 and len(extract.PAIRS) == 30
    assert sum(1 for b in BONDS if not b["excluded"]) == 27
    by_element = {e: sum(1 for b in BONDS if not b["excluded"] and b["element"] == e) for e in ("C", "N", "O")}
    assert by_element == {"C": 19, "N": 6, "O": 2}  # the N-H bonds are where the proton-affinity bias was largest


@pytest.mark.parametrize("bond", BONDS, ids=lambda b: b["name"])
def test_every_bond_is_the_stored_enthalpies_combined_as_the_definition_says(bond):
    dh = (bond["radical_dfH298_kj"] + bond["hydrogen_atom_dfH298_kj"] - bond["parent_dfH298_kj"]) / extract.KJ_PER_KCAL
    unc = math.sqrt(bond["parent_uncertainty_kj"] ** 2 + bond["radical_uncertainty_kj"] ** 2 + bond["hydrogen_atom_uncertainty_kj"] ** 2) / extract.KJ_PER_KCAL
    assert bond["dh298_kcal"] == pytest.approx(dh, abs=1e-3) and bond["uncertainty_kcal"] == pytest.approx(unc, abs=1e-3)
    assert bond["uncertainty_kcal"] <= 1.0  # the first run's rule for a deciding bond, which every candidate meets


@pytest.mark.parametrize("bond", BONDS, ids=lambda b: b["name"])
def test_every_bond_names_a_real_site_with_a_hydrogen_on_a_parent_the_table_spells_that_way(bond):
    from rdkit import Chem

    mol = Chem.AddHs(Chem.MolFromSmiles(bond["smiles"]))
    atom = mol.GetAtomWithIdx(bond["atom"])
    assert atom.GetSymbol() == bond["element"] and any(n.GetAtomicNum() == 1 for n in atom.GetNeighbors())
    assert {a.GetSymbol() for a in mol.GetAtoms()} <= extract.ELEMENTS and sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() > 1) <= 10


def test_no_held_out_bond_is_one_the_first_run_computed():
    first = {extract.site_class(b["smiles"], b["atom"]) for b in FIRST_RUN}
    overlap = [b["name"] for b in BONDS if extract.site_class(b["smiles"], b["atom"]) in first]
    assert overlap == []


def test_the_site_class_tells_a_methyl_from_a_methylene():
    assert extract.site_class("CCO", 0) != extract.site_class("CCO", 1)
    assert extract.site_class("CCC", 0)[1] == extract.site_class("CCC", 2)[1]  # the two methyls of propane are one bond


def test_the_three_exclusions_are_exactly_the_documented_ones_and_each_says_how_to_lift_it():
    excluded = {(b["parent"], b["radical"]) for b in BONDS if b["excluded"]}
    assert excluded == {("Isocyanic acid", "Cyanooxidanyl"), ("Hydrazoic acid", "Azido radical"), ("Ketene", "Ketenyl")} == set(extract.EXCLUDED)
    for b in BONDS:
        if b["excluded"]:
            assert all(len(b["exclusion"][key]) > 40 for key in ("reason", "evidence", "would_lift"))


def test_the_arithmetic_reproduces_the_first_runs_references_where_both_sources_cover_a_bond():
    differences = [c["difference"] for c in CROSS]
    assert len(CROSS) == 22 and abs(sum(differences) / len(differences) + 0.11) < 0.02
    # beyond three combined standard uncertainties there is exactly one disagreement, and it is the one disclosed, not hidden
    beyond = [c["bond"] for c in CROSS if abs(c["difference"]) > 3 * math.hypot(c["atct_uncertainty"], c["be_uncertainty"])]
    assert beyond == ["propene allylic C-H"]
    # the references the first run held to 0.1 kcal/mol or better agree with ATcT to 0.2
    tight = [c for c in CROSS if c["be_uncertainty"] <= 0.1]
    assert tight and max(abs(c["difference"]) for c in tight) < 0.2


def test_the_parse_refuses_a_different_table(tmp_path):
    page = tmp_path / "other.htm"
    page.write_text("<html><table><tr><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td><td>f</td><td>g</td><td>h</td><td>i</td></tr></table></html>", encoding="utf-8")
    with pytest.raises(SystemExit, match="different version"):
        extract.parse_atct(page)
