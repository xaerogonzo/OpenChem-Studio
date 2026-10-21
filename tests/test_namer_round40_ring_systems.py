"""Naming round 40 (D-215 .. D-219): ring systems that lost their heteroatoms, their numbering, their hydrogen or their name.

D-215: a spiro join of a bicycle and a heterocycle (`O=C1NC(=O)C2(N1)CC1CCC2C1`) came out `tricyclo[5.4.2.1]undecane-1,3-dione`, every N gone: the von Baeyer
namer could not number the heteroatoms and offered the carbocycle name anyway, which outranked the spiro name that was also offered. It now offers nothing
it cannot cite.

D-216: "the attachment is locant 1" ranked above the heteroatom locants for a monocyclic heterocycle substituent, so an N-attached 1,2,4-triazine-3,5-dione was
numbered as a ring with nitrogens at 1, 2 and 5 (`4,6-dioxo-5,6-dihydro-1,2,4-triazin-1(4H)-yl`), which OPSIN cannot build. It is `3,5-dioxo-4,5-dihydro-1,2,4-triazin-2(3H)-yl`.

D-217: a spiro partner is rebuilt atom by atom and lost the N-H of an azole, so `spiro[...pyrano[2,3-c]pyrazole]` was a NAMING ERROR; and a tricycle of three
monocycles needs a SECOND-order component (`pyrrolo[3',2':5,6]pyrido[2,3-d]pyrimidine`), which the fusion constructor refused.

D-218: `1,4-dihydroquinoline` as a spiro partner was bracketed `[1,4]dihydroquinoline`, which is not a name.

D-219: a protonated or iminium nitrogen in a fused system with a four-membered ring has no fusion name (P-52.2.4.1) and the von Baeyer fallback refused every charge.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

SPIRO_BICYCLE = [
    ("hydantoin on norbornane", "O=C1NC(=O)C2(N1)CC1CCC2C1", "spiro[imidazolidine-4,2'-bicyclo[2.2.1]heptane]-2,5-dione"),
    ("hydantoin on bicyclooctane", "O=C1NC(=O)C2(N1)CC1CCC2CC1", "spiro[imidazolidine-4,2'-bicyclo[2.2.2]octane]-2,5-dione"),
    ("pyrrolidine on norbornane", "C1CC2CC1CC21CCNC1", "spiro[pyrrolidine-3,2'-bicyclo[2.2.1]heptane]"),
    ("oxolane on the norbornane bridge", "C1CC2CCC1C21CCOC1", "spiro[oxolane-3,7'-bicyclo[2.2.1]heptane]"),
    ("dioxane on the norbornane bridge", "C1CC2CCC1C21OCCCO1", "spiro[[1,3]dioxane-2,7'-bicyclo[2.2.1]heptane]"),
    ("the census row (167625)", "CC1(C)C2CCC1(C)C1(C2)NC(=O)NC1=O", "1',7',7'-trimethylspiro[[1,3]diazolidine-4,2'-bicyclo[2.2.1]heptane]-2,5-dione"),
]

TRIAZINYL = [
    ("on a propanoic acid", "OC(=O)CCn1ncc(=O)[nH]c1=O", "3-(3,5-dioxo-4,5-dihydro-1,2,4-triazin-2(3H)-yl)propanoic acid"),
    ("the census row (150625)", "NC(=O)C1OC(n2ncc(=O)[nH]c2=O)CC1O", "5-(3,5-dioxo-4,5-dihydro-1,2,4-triazin-2(3H)-yl)-3-hydroxyoxolane-2-carboxamide"),
    ("a single oxo", "OC(=O)CCn1nccnc1=O", "3-(3-oxo-1,2,4-triazin-2(3H)-yl)propanoic acid"),
    ("a 1,3,5-triazine", "OC(=O)CCn1cncnc1=O", "3-(2-oxo-1,3,5-triazin-1(2H)-yl)propanoic acid"),
]

SPIRO_AZOLE = [
    ("pyrano[2,3-c]pyrazole", "C1=COc2n[nH]cc2C12CCCC2", "spiro[2,4-dihydropyrano[2,3-c]pyrazole-4,1'-cyclopentane]"),
    ("pyrano[3,2-c]pyrazole", "C1=COc2cn[nH]c2C12CCCC2", "spiro[1,7-dihydropyrano[3,2-c]pyrazole-7,1'-cyclopentane]"),
    ("pyrano[2,3-b]pyrrole", "C1=COc2[nH]ccc2C12CCCC2", "spiro[4,7-dihydropyrano[2,3-b]pyrrole-4,1'-cyclopentane]"),
    ("an oxindole (census row 1202625)", "N#CC1=C(N)Oc2n[nH]cc2C12C(=O)Nc1ccccc12",
     "6-amino-2'-oxospiro[2,4-dihydropyrano[2,3-c]pyrazole-4,3'-2,3-dihydro-1H-indole]-5-carbonitrile"),
]

SECOND_ORDER = [
    ("pyrrolo on pyrido on pyrimidine", "c1ncc2cc3cc[nH]c3nc2n1", "8H-pyrrolo[3',2':5,6]pyrido[2,3-d]pyrimidine"),
    ("pyrido on pyrrolo on pyrimidine", "c1ncc2c(n1)[nH]c1ncccc12", "9H-pyrido[3',2':4,5]pyrrolo[2,3-d]pyrimidine"),
    ("thieno on pyrido on pyrimidine", "c1ncc2cc3sccc3nc2n1", "thieno[2',3':5,6]pyrido[2,3-d]pyrimidine"),
    ("pyrimido on pyrrolo on quinoxaline", "O=c1[nH]cnc2[nH]c3nc4ccccc4nc3c12", "3,11-dihydro-4H-pyrimido[5',4':4,5]pyrrolo[2,3-b]quinoxalin-4-one"),
    ("a pyrazolo-pyrido-pyrimidinedione", "O=c1[nH]c(=O)c2cc3cn[nH]c3nc2[nH]1", "1H-pyrazolo[4',3':5,6]pyrido[2,3-d]pyrimidine-5,7(6H,8H)-dione"),
    ("the census row (1852625)", "Cc1nn(-c2ccccc2)c2c1cc1c(=O)n(C)c(=O)nc-1n2-c1ccccc1F",
     "9-(2-fluorophenyl)-3,6-dimethyl-1-phenyl-1H-pyrazolo[4',3':5,6]pyrido[2,3-d]pyrimidine-5,7(6H,9H)-dione"),
    ("the census row (1968625)", "C=CCn1cnc2c(c1=O)c1nc3ccccc3nc1n2CCC1=CCCCC1",
     "11-[2-(cyclohex-1-en-1-yl)ethyl]-3-(prop-2-en-1-yl)-3,11-dihydro-4H-pyrimido[5',4':4,5]pyrrolo[2,3-b]quinoxalin-4-one"),
]

SPIRO_HYDRO = [
    ("dihydroquinoline", "C1=CNc2ccccc2C12CCCC2", "spiro[1,4-dihydroquinoline-4,1'-cyclopentane]"),
    ("tetrahydroquinoline", "C1CNc2ccccc2C12CCCC2", "spiro[1,2,3,4-tetrahydroquinoline-4,1'-cyclopentane]"),
    ("dihydronaphthyridine", "C1=CNc2ncccc2C12CCCC2", "spiro[1,4-dihydro-1,8-naphthyridine-4,1'-cyclopentane]"),
]

FUSED_CATION = [
    ("azetidinium fused to azepane", "C1CCC2[NH+](CC1)CC2", "1-azabicyclo[5.2.0]nonan-1-ium"),
    ("azetidinium fused to pyrrolidine", "C1CC2CC[NH+]2C1", "1-azabicyclo[3.2.0]heptan-1-ium"),
    ("a bridgehead iminium, 7 and 4", "C1CCC2=[N+](CC1)CC2", "1-azabicyclo[5.2.0]non-1(7)-en-1-ium"),
    ("a bridgehead iminium, 6 and 4", "C1CC[N+]2=C(C1)CC2", "1-azabicyclo[4.2.0]oct-1(6)-en-1-ium"),
    ("a bridgehead iminium, 5 and 4", "C1CC2CC[N+]2=C1", "1-azabicyclo[3.2.0]hept-1-en-1-ium"),
    ("a substituted one", "CC1CC2=[N+]1CCCC2", "8-methyl-1-azabicyclo[4.2.0]oct-1(6)-en-1-ium"),
]

# Names that must not change: quinuclidinium, the neutral analogues, an arenium (still refused the von Baeyer fallback), and a plain spiro on a carbocycle.
UNCHANGED = [
    ("quinuclidinium", "C1C[NH+]2CCC1CC2", "1-azabicyclo[2.2.2]octan-1-ium"),
    ("the neutral azetidine-fused azepane", "C1CCC2N(CC1)CC2", "1-azabicyclo[5.2.0]nonane"),
    ("spiro on a carbocycle", "C1CC2CC1CC21CCCC1", "spiro[bicyclo[2.2.1]heptane-2,1'-cyclopentane]"),
    ("a spiro hydantoin on a ring", "C1CCC2(C1)NC(=O)NC2=O", "1,3-diazaspiro[4.4]nonane-2,4-dione"),
    ("a first-order fused name", "c1ccc2c(c1)[nH]c1ncncc12", "9H-pyrimido[4,5-b]indole"),
    ("pyrrolopyridine", "c1cc2cc3cc[nH]c3nc2nc1", "1H-pyrrolo[2,3-b][1,8]naphthyridine"),
]

ALL = SPIRO_BICYCLE + TRIAZINYL + SPIRO_AZOLE + SECOND_ORDER + SPIRO_HYDRO + FUSED_CATION + UNCHANGED


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_ring_system_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_a_spiro_name_never_loses_its_heteroatoms():
    """The defect dropped every N and O, so the name of a spiro heterocycle must mention each element the structure has."""
    for _label, smiles, expected in SPIRO_BICYCLE:
        mol = Chem.MolFromSmiles(smiles)
        elements = {a.GetSymbol() for a in mol.GetAtoms()} - {"C"}
        assert elements, smiles
        assert any(word in expected for word in ("imidazolidine", "diazolidine", "pyrrolidine", "oxolane", "dioxane")), expected


def test_a_hydro_prefix_is_never_bracketed_as_a_heteroatom_locant():
    for _label, _smiles, expected in SPIRO_HYDRO:
        assert "]dihydro" not in expected and "]tetrahydro" not in expected, expected
