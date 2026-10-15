"""Naming round 58 (D-275 .. D-277): carbon acids, an ester-shaped name that is not an anion, and a cation parent hydride fused with a suffix.

The anion population gained the first CARBON acids (the CH between two carbonyls or two nitriles) this round, and with them a class the earlier populations could not reach.

D-275: a stabilised carbanion on a ring the simple-carbon classifier refuses (`O=C1[CH-]C(=O)NC(=O)N1`, the barbiturate carbon RDKit calls aromatic; the fused indane-1,3-dione carbon; a
  pyrimidinedione with a 5-butyl). Nothing claimed it, the plan search neutralised the carbon, and the name was the neutral compound's. It is named like any carbanion, `...-5-ide`, from the
  Kekule drawing.
D-276: the charge guard accepted an ESTER's `...butanoate` as an anion word: `COC(=O)CCC(=O)[c-]1nc(...)oc1=O` was `methyl 4-oxo-4-(5-oxo-2-phenyl-1,3-oxazol-4-yl)butanoate`, the neutral
  compound, passed as an anion. A name that opens with an alkyl word and a space is an ester; its final `ate` says nothing. (The carbanion beside a ring nitrogen is refused, visibly.)
D-277: a cation parent hydride fused with a suffix (`CNC(=N)[SH+]C` was `dimethylsulfaniumcarboximidamide`) is never a name and is refused; and an O-methylated or O-protonated sulfoxide whose sulfur
  carries one carbon and a sulfonyl or phosphoryl (a thiosulfonate S-oxide) is named as the sulfonium, `(benzenesulfonyl)(methoxy)(phenyl)sulfanium`.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _check_charge_named

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
CARBANIONS = [
    ("the barbiturate carbanion", "O=C1[CH-]C(=O)NC(=O)N1", "2,4,6-trioxo-1,3-diazinan-5-ide"),
    ("the indane-1,3-dione carbanion", "O=C1[CH-]C(=O)c2ccccc12", "1,3-dioxo-2,3-dihydro-1H-inden-2-ide"),
    ("a 5-butyl pyrimidinedione carbanion", "CCCC[c-]1c(=O)nc(S)n(C)c1=O", "5-butyl-1-methyl-4,6-dioxo-2-sulfanyl-1,4,5,6-tetrahydropyrimidin-5-ide"),
]

CARBANIONS_KEPT = [
    ("acetylacetonate", "CC(=O)[CH-]C(C)=O", "2,4-dioxopentan-3-ide"),
    ("the cyclohexane-1,3-dione carbanion", "O=C1CCCC(=O)[CH-]1", "2,6-dioxocyclohexan-1-ide"),
    ("dicyanomethanide", "[CH-](C#N)C#N", "dicyanomethanide"),
]

SULFONIUM = [
    ("a thiosulfonate S-oxide, O-methylated", "C[O+]=S(c1ccccc1)S(=O)(=O)c1ccccc1", "(benzenesulfonyl)(methoxy)(phenyl)sulfanium"),
    ("a sulfinyl on a phosphoryl", "CCS(=[O+]C)P1(=O)O[C@H](c2ccccc2)[C@H](C)N1C",
     "[(4S,5R)-3,4-dimethyl-2-oxo-5-phenyl-2lambda5-1,3,2-oxazaphospholidin-2-yl](ethyl)(methoxy)sulfanium"),
]

ALL = CARBANIONS + CARBANIONS_KEPT + SULFONIUM


def _normalised_key(smiles: str) -> str:
    """InChIKey of the ion with a protonated or alkylated sulfoxide drawn as its sulfonium, and an anion's charge removed (standard InChI places a proton)."""
    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        if {a.GetSymbol(), b.GetSymbol()} == {"S", "O"} and bond.GetBondTypeAsDouble() == 1.0 and (a.GetFormalCharge() + b.GetFormalCharge()) == 1:
            bond.SetBondType(Chem.BondType.DOUBLE)
            for atom in (a, b):
                hydrogens = atom.GetTotalNumHs()
                atom.SetFormalCharge(0 if atom.GetSymbol() == "S" else 1)
                atom.SetNoImplicit(True)
                atom.SetNumExplicitHs(hydrogens)
    for atom in mol.GetAtoms():
        if atom.GetFormalCharge() < 0 and not any(n.GetFormalCharge() > 0 for n in atom.GetNeighbors()):
            atom.SetFormalCharge(0)
            atom.SetNoImplicit(True)
            atom.SetNumExplicitHs(atom.GetTotalNumHs() + 1)
    Chem.SanitizeMol(mol)
    return Chem.MolToInchiKey(mol)


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.GetFormalCharge(Chem.MolFromSmiles(back)) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert _normalised_key(back) == _normalised_key(smiles), (expected, back)


def test_an_ester_shaped_name_is_not_an_anion_word():
    carbanion = Chem.MolFromSmiles("COC(=O)CCC(=O)[c-]1nc(-c2ccccc2)oc1=O")
    with pytest.raises(ValueError, match="ester"):
        _check_charge_named(carbanion, "methyl 4-oxo-4-(5-oxo-2-phenyl-1,3-oxazol-4-yl)butanoate")


def test_the_carbanion_beside_a_ring_nitrogen_is_refused_not_named_as_its_ester():
    with pytest.raises(ValueError):
        name_smiles("COC(=O)CCC(=O)[c-]1nc(-c2ccccc2)oc1=O")


@pytest.mark.parametrize(
    "smiles,name",
    [
        ("COC(=O)c1ccc(C(=O)[O-])cc1", "4-(methoxycarbonyl)benzoate"),
        ("COC(=O)CCC(=O)[O-]", "4-methoxy-4-oxobutanoate"),
        ("CCOC(=O)CC(=O)[O-]", "3-ethoxy-3-oxopropanoate"),
    ],
)
def test_a_carboxylate_with_an_ester_elsewhere_keeps_its_name(smiles, name):
    assert name_smiles(smiles) == name


def test_a_neutral_ester_is_untouched():
    assert name_smiles("COC(=O)c1ccccc1") == "methyl benzoate"


def test_a_cation_parent_fused_with_a_suffix_is_refused():
    with pytest.raises(ValueError, match="fuses"):
        name_smiles("CNC(=N)[SH+]C")


def test_the_guard_names_the_fusion():
    mol = Chem.MolFromSmiles("CNC(=N)[SH+]C")
    with pytest.raises(ValueError, match="fuses"):
        _check_charge_named(mol, "dimethylsulfaniumcarboximidamide")


def test_the_ordinary_protonated_thioether_and_isothiouronium_keep_their_names():
    assert name_smiles("CC[SH+]C") == "ethyl(methyl)sulfanium"
    assert name_smiles("CNC(=[NH2+])SC") == "[(methylamino)(methylsulfanyl)methylidene]azanium"


def test_the_carbanion_classifier_wants_carbon_neighbours_and_an_acceptor():
    from openchem.vendor.iupac_namer.perception.charge_perception import _classify_stabilised_carbanion

    taken = lambda smiles: list(_classify_stabilised_carbanion(Chem.MolFromSmiles(smiles)))  # noqa: E731
    assert taken("O=C1[CH-]C(=O)NC(=O)N1")
    assert taken("[CH-](C#N)C#N")
    # no acceptor: a fluorenide is not a stabilised carbanion in this sense
    assert taken("[CH-]1c2ccccc2-c2ccccc12") == []
    # a ring nitrogen beside the carbanion (the oxazolone): not claimed, so the guard refuses it
    assert taken("COC(=O)CCC(=O)[c-]1nc(-c2ccccc2)oc1=O") == []
