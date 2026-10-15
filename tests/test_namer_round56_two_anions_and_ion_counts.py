"""Naming round 56 (D-268 .. D-270): two anions in one molecule, the charge guard that counts centres, and a ketone ring cation with a cation suffix.

D-268: an anionic nitrogen as a PREFIX. A molecule with two anions names one as the parent and cites the other; the carved `CC(=O)[N-]` fragment was named as a standalone anion and failed
  (`NAMING ERROR ... [NH-]`), and a sulfonamide anion beside a phenolate was named `[N-(4-oxidophenyl)sulfamoyl]methane` with the sulfonamide charge dropped. The prefix is `azanidyl`, which OPSIN
  reads: `4-(acetylazanidyl)benzen-1-olate`.
D-269: the guard looked for A word of each polarity, not a word per centre, so the two-anion name above (one `oxido`) and a protonated amidoxime beside a second cation passed. A name that never
  multiplies an ion word now needs as many ion words as the molecule has centres of that polarity.
D-270: a curated ketone ring cation that also carries a cation suffix was `...-4-on-1-ium-2-aminium`, which OPSIN cannot read: the cation suffix outranks the ketone, which is the prefix `oxo`.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _check_charge_named

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
TWO_ANIONS = [
    ("an anilide anion beside a phenolate", "CC(=O)[N-]c1ccc([O-])cc1", "4-(acetylazanidyl)benzen-1-olate"),
    ("an anilide anion beside a carboxylate", "CC(=O)[N-]c1ccc(C(=O)[O-])cc1", "1-(acetylazanidyl)-4-[oxido(oxo)methyl]benzene"),
    ("a sulfonamide anion beside a phenolate", "CS(=O)(=O)[N-]c1ccc([O-])cc1", "4-(methylsulfonylazanidyl)benzen-1-olate"),
    ("a sulfonamide anion beside a thiolate", "CS(=O)(=O)[N-]c1ccc([S-])cc1", "4-(methylsulfonylazanidyl)benzene-1-thiolate"),
    ("a sulfamide anion beside a carboxylate", "CN(C)S(=O)(=O)[N-]c1ccc(C(=O)[O-])cc1", "1-[(N,N-dimethylsulfamoyl)azanidyl]-4-[oxido(oxo)methyl]benzene"),
    ("an acylurea anion beside a thiolate", "Cc1ccccc1C(=O)[N-]C(=O)N=C([S-])c1ccccc1", "[((2-methylbenzoyl)azanidyl)carbonylimino]phenylmethanethiolate"),
]

KETONE_RING_CATION = [
    ("a pyridopyrimidinone cation with an aminium suffix", "Cc1ccc2[nH+]c([NH3+])cc(=O)n2c1", "7-methyl-4-oxo-4H-pyrido[1,2-a]pyrimidin-1-ium-2-aminium"),
    ("the same, N-methylated aminium", "C[NH2+]c1cc(=O)n2ccccc2[nH+]1", "N-methyl-4-oxo-4H-pyrido[1,2-a]pyrimidin-1-ium-2-aminium"),
]

ALL = TWO_ANIONS + KETONE_RING_CATION


def _neutral_key(smiles: str) -> str:
    """InChIKey with the anions' charge removed (standard InChI places a proton), cations kept."""
    mol = Chem.RWMol(Chem.MolFromSmiles(smiles))
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
    mol = Chem.MolFromSmiles(back)
    assert Chem.GetFormalCharge(mol) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert _neutral_key(back) == _neutral_key(smiles), (expected, back)


def test_a_single_anionic_nitrogen_is_still_the_azanide_parent():
    assert name_smiles("CC(=O)[N-]C") == "acetyl(methyl)azanide"


def test_the_standalone_ketone_ring_cation_without_a_suffix_is_unchanged():
    assert name_smiles("Cc1ccc2[nH+]c(CSC)cc(=O)n2c1") == "7-methyl-2-[(methylsulfanyl)methyl]-4H-pyrido[1,2-a]pyrimidin-1-ium-4-one"


def test_the_guard_counts_centres_not_words():
    mol = Chem.MolFromSmiles("CS(=O)(=O)[N-]c1ccc([O-])cc1")
    _check_charge_named(mol, "4-(methylsulfonylazanidyl)benzen-1-olate")
    with pytest.raises(ValueError, match="every negative charge"):
        _check_charge_named(mol, "[N-(4-oxidophenyl)sulfamoyl]methane")


def test_the_guard_counts_cations_too():
    mol = Chem.MolFromSmiles("C[NH+]1CCN(C(=O)c2ccccc2[NH3+])CC1")
    _check_charge_named(mol, "2-(4-methylpiperazin-4-ium-1-carbonyl)benzen-1-aminium")
    with pytest.raises(ValueError, match="every positive charge"):
        _check_charge_named(mol, "2-(4-methylpiperazine-1-carbonyl)benzen-1-aminium")


@pytest.mark.parametrize(
    "smiles,name",
    [
        ("[O-]C(=O)CCC(=O)[O-]", "butanedioate"),
        ("[O-]c1ccc([O-])cc1", "benzene-1,4-diolate"),
        ("[O-]C(=O)c1ccc(C(=O)[O-])cc1", "benzene-1,4-dicarboxylate"),
        ("[NH3+]CC[NH3+]", "ethane-1,2-bis(aminium)"),
        ("C[N+](C)(C)CC[N+](C)(C)C", "N1,N1,N1,N2,N2,N2-hexamethylethane-1,2-bis(aminium)"),
    ],
)
def test_a_multiplied_ion_word_stands_for_several_centres(smiles, name):
    _check_charge_named(Chem.MolFromSmiles(smiles), name)
    assert name_smiles(smiles) == name


def test_the_protonated_amidoxime_beside_a_second_cation_keeps_both_charges():
    """Round 56 refused it (a neutral hydroxyimino hid one of two cations); round 57 writes the prefix `hydroxyazaniumylidene`."""
    name = name_smiles("O[NH+]=C(c1ncc(C(F)(F)F)cc1Cl)N1CC[NH+](Cc2ccccc2)CC1")
    assert "hydroxyazaniumylidene" in name and name.endswith("piperazin-1-ium")
