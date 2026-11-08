"""NL-090 (WS2): letter locants on fused hydro/bridged parents — 6a and 13a methyls read back; 12b not drawable."""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# Parents from `data_loader` atom_locants (round 25 probing).
IBOG_PARENT = "c1ccc2c3c([nH]c2c1)C1CC2CCC1N(CC3)C2"
VIN_PARENT = "C1=CC2CCC3Nc4ccccc4C34CCN(C1)C24"
GAL_PARENT = "C1=CC23CCNCc4cccc(c42)OC3CC1"

IBOG_6A_METHYL = (
    "6a-methyl-5,6,6a,7,8,9,10,12,13-nonahydro-6,9-methanopyrido[1',2':1,2]azepino[4,5-b]indole"
)
VIN_13A_METHYL = "13a-methyl-3a,4,5,5a,6,11,12,13-octahydro-1H-indolizino[8,1-cd]carbazole"
IBOG_6A_KEY = "CTIHOLHUXZQGLM-UHFFFAOYSA-N"
VIN_13A_KEY = "DJGRNFGUFAXVQK-UHFFFAOYSA-N"

# atom_locants: 6a → idx 14; 13a → idx 18; 12b → idx 12 (fusion carbon, no hydrogen).
_ATOM_IDX = {"6a": 14, "13a": 18, "12b": 12}


def _methylated_smiles(parent: str, atom_idx: int) -> str | None:
    mol = Chem.MolFromSmiles(parent)
    editor = Chem.EditableMol(mol)
    editor.AddBond(atom_idx, editor.AddAtom(Chem.Atom(6)), Chem.BondType.SINGLE)
    product = editor.GetMol()
    try:
        Chem.SanitizeMol(product)
        Chem.Kekulize(product, clearAromaticFlags=True)
    except ValueError:
        return None
    return Chem.MolToSmiles(product)


def test_nl090_12b_methyl_does_not_sanitize():
    """Fusion carbon 12b has no hydrogen; RDKit cannot build a methyl substituent there."""
    assert _methylated_smiles(GAL_PARENT, _ATOM_IDX["12b"]) is None


def test_nl090_6a_methyl_name_and_key():
    smiles = _methylated_smiles(IBOG_PARENT, _ATOM_IDX["6a"])
    assert smiles
    assert name_smiles(smiles) == IBOG_6A_METHYL
    want = inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))
    assert want == IBOG_6A_KEY


def test_nl090_13a_methyl_name_and_key():
    smiles = _methylated_smiles(VIN_PARENT, _ATOM_IDX["13a"])
    assert smiles
    assert name_smiles(smiles) == VIN_13A_METHYL
    want = inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))
    assert want == VIN_13A_KEY


@needs_opsin
def test_nl090_6a_methyl_opsin_read_back():
    from py2opsin import py2opsin

    smiles = _methylated_smiles(IBOG_PARENT, _ATOM_IDX["6a"])
    assert smiles
    assert name_smiles(smiles) == IBOG_6A_METHYL
    back = py2opsin(IBOG_6A_METHYL)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == IBOG_6A_KEY


@needs_opsin
def test_nl090_13a_methyl_opsin_read_back():
    from py2opsin import py2opsin

    smiles = _methylated_smiles(VIN_PARENT, _ATOM_IDX["13a"])
    assert smiles
    assert name_smiles(smiles) == VIN_13A_METHYL
    back = py2opsin(VIN_13A_METHYL)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == VIN_13A_KEY
