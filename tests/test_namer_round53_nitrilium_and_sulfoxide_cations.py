"""Naming round 53 (D-253, D-254): a nitrilium with a heteroatom in its group, and an O-protonated or O-alkylated sulfoxide.

D-253: `[NH+]#Cc1ccc(O)cc1` (a nitrilium) was named by the plan search as the neutral nitrile with an `azanylidyne` prefix, whose cation the charge guard refused (77 census-derived
protonated nitriles, all with a hydroxy, amino or halogen in the group; the hydrocarbon ones were named). The cation is senior to every neutral class (P-41), so it is the parent and the
carbon's group an `ylidyne` prefix: `[(4-hydroxyphenyl)methylidyne]azanium`.
D-254: `CS(C)=[OH+]` had no classifier; the same cation drawn with the S-O bond single is a sulfonium with a hydroxy substituent, which the engine names: `hydroxydi(methyl)sulfanium`, OPSIN
reads it. Acyclic sulfur only.

Both found by `tools/naming_ion_populations.py`, round 52's `nitrile_n` and `sulfoxide_o` sites.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NITRILIUM = [
    ("a hydroxyphenyl nitrilium", "[NH+]#Cc1ccc(O)cc1", "[(4-hydroxyphenyl)methylidyne]azanium"),
    ("a hydroxyalkyl nitrilium", "[NH+]#CC(O)C", "(2-hydroxypropylidyne)azanium"),
    ("an N-methyl nitrilium", "C[N+]#Cc1ccc(O)cc1", "[(4-hydroxyphenyl)methylidyne](methyl)azanium"),
    ("a chloroalkyl nitrilium", "[NH+]#CCCl", "(2-chloroethylidyne)azanium"),
    ("a stilbene nitrilium", "[NH+]#CC(=Cc1ccc(O)cc1)c1ccc(O)cc1", "[2,3-bis(4-hydroxyphenyl)prop-2-en-1-ylidyne]azanium"),
]

#: Hydrocarbon nitriliums keep the route that already named them.
NITRILIUM_KEPT = [
    ("a benzonitrilium", "[NH+]#Cc1ccccc1", "benzylidyneazanium"),
    ("an N-methyl alkyl nitrilium", "C[N+]#CC", "ethylidyne(methyl)azanium"),
]

SULFOXIDE = [
    ("O-protonated dimethyl sulfoxide", "CS(C)=[OH+]", "hydroxydi(methyl)sulfanium"),
    ("O-methylated dimethyl sulfoxide", "CS(C)=[O+]C", "(methoxy)di(methyl)sulfanium"),
    ("a protonated vinyl sulfoxide", "C=CS(=[OH+])CCCl", "(2-chloroethyl)(ethenyl)(hydroxy)sulfanium"),
]

#: D-255, found beside D-253: an acyl PREFIX whose fragment also holds a second acid. The acid's name is a diacid, and turning it into the acyl name made a DIACYL group:
#: `4-propanedioylanilinium` (the free acid dropped, a different molecule). The generic substituent path writes the carboxy.
DIACYL_PREFIX = [
    ("a malonyl half on an anilinium", "[NH3+]c1ccc(C(=O)CC(=O)O)cc1", "4-(2-carboxy-1-oxoethyl)anilinium"),
    ("an oxalyl half on an anilinium", "[NH3+]c1ccc(C(=O)C(=O)O)cc1", "4-[carboxy(oxo)methyl]anilinium"),
    ("a succinyl half on an anilinium", "[NH3+]c1ccc(C(=O)CCC(=O)O)cc1", "4-(3-carboxy-1-oxopropyl)anilinium"),
    ("a dioxobutanoic half on a nitrilium", "[NH+]#Cc1ccc(C(=O)CC(=O)C(=O)O)cc1", "[[4-(3-carboxy-1,3-dioxopropyl)phenyl]methylidyne]azanium"),
]

ALL = NITRILIUM + NITRILIUM_KEPT + SULFOXIDE + DIACYL_PREFIX


def _as_sulfonium(smiles: str) -> str:
    """The sulfoxide cation drawn with a single S-O bond and the charge on sulfur: the drawing OPSIN returns for `hydroxy...sulfanium`."""
    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
    for bond in mol.GetBonds():
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        if {a.GetSymbol(), b.GetSymbol()} == {"S", "O"} and bond.GetBondTypeAsDouble() == 2.0 and (a.GetFormalCharge() + b.GetFormalCharge()) == 1:
            bond.SetBondType(Chem.BondType.SINGLE)
            for atom in (a, b):
                atom.SetFormalCharge(1 if atom.GetSymbol() == "S" else 0)
                atom.SetNoImplicit(True)
    Chem.SanitizeMol(mol)
    return Chem.MolToSmiles(mol)


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_cation(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    key = lambda s: Chem.MolToInchiKey(Chem.MolFromSmiles(_as_sulfonium(s)))  # noqa: E731
    assert key(back) == key(smiles), (expected, back)


def test_a_ring_sulfoxide_cation_is_not_taken_by_the_sulfonium_route():
    """A ring sulfur is named by a path that does not survive the recursive drive; it must not be claimed and then fail."""
    assert "sulfanium" not in name_smiles("C1CCS(=[OH+])C1")


def test_a_neutral_sulfoxide_and_a_sulfonium_are_untouched():
    assert name_smiles("CS(C)=O") == "(methanesulfinyl)methane"
    assert name_smiles("C[S+](C)C") == "trimethylsulfanium"


def test_an_ordinary_acyl_prefix_keeps_the_acyl_route():
    assert name_smiles("[NH3+]c1ccc(C(=O)CC)cc1") == "4-propanoylanilinium"


def test_a_neutral_hydroxy_nitrile_is_untouched():
    assert name_smiles("N#Cc1ccc(O)cc1") == "4-hydroxybenzonitrile"
