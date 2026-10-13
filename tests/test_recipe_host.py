"""Is a run's stored input still this molecule: constitution, isotopes, charge, and the stereochemistry specified.

Real RDKit molecules and real embedded conformers, written to molblocks the way a quantum-chemistry run stores them.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.recipe_host import constitution_key, formal_charge, run_describes


def _drawing(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def _run_input(smiles: str, seed: int = 7) -> str:
    """A 3D conformer's molblock, hydrogens explicit, as a run's `input_molblock` is."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0, smiles
    return Chem.MolToMolBlock(mol)


# --- the key -----------------------------------------------------------------------------------------------


def test_the_key_is_the_same_for_the_same_drawing_however_it_was_written():
    assert constitution_key(_drawing("OCC")) == constitution_key(_drawing("CCO")) == constitution_key(_drawing("C(O)C"))


@pytest.mark.parametrize(
    ("a", "b"),
    [("CCO", "CCCO"), ("CCO", "CCN"), ("C[N+](C)(C)C", "CN(C)C"), ("[13CH4]", "C"), ("C[C@H](F)Cl", "C[C@@H](F)Cl"), ("C/C=C/C", "C/C=C\\C")],
    ids=["chain length", "heteroatom", "charge", "isotope", "chirality", "double-bond geometry"],
)
def test_the_key_tells_apart_what_a_person_would_call_an_edit(a, b):
    assert constitution_key(_drawing(a)) != constitution_key(_drawing(b))


def test_the_key_ignores_explicit_hydrogens():
    assert constitution_key(Chem.AddHs(_drawing("CCO"))) == constitution_key(_drawing("CCO"))


def test_specifying_a_centre_the_drawing_left_open_changes_the_key():
    """Deliberately: a run recorded before the wedge was drawn reads as stale and is asked again."""
    assert constitution_key(_drawing("CC(F)Cl")) != constitution_key(_drawing("C[C@H](F)Cl"))


def test_a_structure_rdkit_will_not_sanitise_is_not_a_crash():
    """Pentavalent carbon: `RemoveHs` raises, and the key is None (cannot tell) and not an exception."""
    bad = Chem.MolFromSmiles("C(C)(C)(C)(C)C", sanitize=False)
    assert bad is not None
    assert constitution_key(bad) is None


def test_formal_charge_is_the_nets():
    assert formal_charge(_drawing("CCO")) == 0
    assert formal_charge(_drawing("C[N+](C)(C)C")) == 1
    assert formal_charge(_drawing("[O-]C(=O)C")) == -1


# --- the comparison ---------------------------------------------------------------------------------------


def test_a_conformer_of_the_drawing_is_the_drawing():
    assert run_describes(_run_input("CCO"), _drawing("CCO")) is True


def test_a_conformer_is_the_drawing_whatever_its_geometry():
    assert run_describes(_run_input("CCCO", seed=1), _drawing("CCCO")) is True
    assert run_describes(_run_input("CCCO", seed=99), _drawing("CCCO")) is True


@pytest.mark.parametrize(
    ("ran", "drawn"),
    [
        ("CCO", "CCCO"), ("CCCO", "CCO"),
        ("CCO", "CCN"), ("CCN", "CCO"),
        ("CN(C)C", "C[N+](C)(C)C"), ("C[N+](C)(C)C", "CN(C)C"),
        ("C", "[13CH4]"), ("[13CH4]", "C"),
        ("c1ccccc1", "C1CCCCC1"), ("C1CCCCC1", "c1ccccc1"),
    ],
    ids=[
        "a carbon more", "a carbon fewer", "a nitrogen for an oxygen", "an oxygen for a nitrogen",
        "protonated", "deprotonated", "drawn as an isotopologue", "run as an isotopologue",
        "drawn saturated", "run saturated",
    ],
)
def test_an_edit_makes_the_run_describe_another_molecule_whichever_way_round(ran, drawn):
    """BOTH DIRECTIONS, because a substructure match is not symmetric: a run of propanol CONTAINS an ethanol drawing,
    and a natural-abundance atom in the drawing matches a carbon-13 in the run. Only the constitution comparison
    catches those."""
    assert run_describes(_run_input(ran), _drawing(drawn)) is False


def test_a_drawing_that_specifies_a_centre_is_matched_only_by_that_configuration():
    s_input = _run_input("C[C@H](F)Cl")
    assert run_describes(s_input, _drawing("C[C@H](F)Cl")) is True
    assert run_describes(s_input, _drawing("C[C@@H](F)Cl")) is False


def test_a_drawing_that_leaves_a_centre_open_is_matched_by_either_configuration():
    """The conformer had stereo perceived from its coordinates; the drawing never said, so it is not an edit."""
    open_centre = _drawing("CC(F)Cl")
    assert run_describes(_run_input("C[C@H](F)Cl"), open_centre) is True
    assert run_describes(_run_input("C[C@@H](F)Cl"), open_centre) is True


def test_a_double_bond_the_drawing_specifies_must_match():
    assert run_describes(_run_input("C/C=C/C"), _drawing("C/C=C/C")) is True
    assert run_describes(_run_input("C/C=C/C"), _drawing("C/C=C\\C")) is False


@pytest.mark.parametrize("blank", ["", "   ", "\n"], ids=["empty", "spaces", "newline"])
def test_a_run_with_no_stored_input_cannot_be_compared(blank):
    assert run_describes(blank, _drawing("CCO")) is None


def test_an_unparseable_stored_input_cannot_be_compared():
    assert run_describes("this is not a molblock", _drawing("CCO")) is None


def test_the_answer_is_never_a_yes_by_default():
    """None, not True, whenever the comparison could not be made: callers treat None as unverifiable."""
    assert run_describes("", _drawing("CCO")) is not True
    assert run_describes("garbage", _drawing("CCO")) is not True
