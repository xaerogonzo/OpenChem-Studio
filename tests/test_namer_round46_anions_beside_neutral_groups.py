"""Naming round 46 (D-235 .. D-238): an anion beside a neutral group keeps its charge.

Census row 2072 (`...S(=O)(=O)[N-]c3ncccn3` beside an acetamide) was named `...ethanamide` with the sulfonamide written neutral: the charge was in no word of the name, a
different molecule, and nothing said so. Looking for its neighbours (deprotonating one acidic site of every census molecule and naming it) found the same silence in the anions of imides,
acylureas and N-aryl sulfamides, and a wrong sulfamoyl prefix.

D-235: an anion outranks EVERY neutral class (P-41: anions 4, acids 7, amides 8 ...), not only a neutral instance of its own type. The sulfonamide anion is the parent and the amide is `acetamido`.
D-236: the anion of an imide, an acylurea or an N-aryl sulfamide is `diacetylazanide` / `acetyl(methylcarbamoyl)azanide` (P-72.2.2.2, the parent azanide), and a ring nitrogen is the ring's own
`-ide` (`2,5-dioxopyrrolidin-1-ide`, a barbiturate, phthalimide).
D-237: a sulfamide off a carboxylate was `2-(N,N-dimethylsulfamoyl)benzoate`: the linking NH and the second nitrogen's methyls went to one `sulfamoyl`, a different molecule.
D-238: the net under all of them. A single-fragment ion whose name has no word for its charge is refused, not returned.

Every name pinned here is read back through OPSIN. OPSIN reads `-sulfonamidate` as the neutral sulfonamide, so those rows are compared on neutral connectivity, with the anion word asserted
separately; every other row is compared with its charge.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _check_charge_named

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
SULFONAMIDATE_BESIDE_NEUTRAL = [
    ("acetamide", "CC(=O)Nc1ccc(S(=O)(=O)[N-]c2ncccn2)cc1", "4-acetamido-N-(pyrimidin-2-yl)benzene-1-sulfonamidate"),
    ("census row 2072", "Cc1cc(OCC(=O)Nc2ccc(S(=O)(=O)[N-]c3ncccn3)cc2)ccc1[N+](=O)[O-]",
     "4-[(3-methyl-4-nitrophenoxy)acetamido]-N-(pyrimidin-2-yl)benzene-1-sulfonamidate"),
    ("primary amide", "NC(=O)c1ccc(S(=O)(=O)[N-]C)cc1", "4-carbamoyl-N-methylbenzene-1-sulfonamidate"),
    ("nitrile", "N#Cc1ccc(S(=O)(=O)[N-]C)cc1", "4-cyano-N-methylbenzene-1-sulfonamidate"),
    ("ester", "COC(=O)c1ccc(S(=O)(=O)[N-]C)cc1", "4-(methoxycarbonyl)-N-methylbenzene-1-sulfonamidate"),
]

AZANIDES = [
    ("a diacylamide", "CC(=O)[N-]C(C)=O", "diacetylazanide"),
    ("an acylurea", "CC(=O)[N-]C(=O)NC", "acetyl(methylcarbamoyl)azanide"),
    ("an N-aryl amide", "CC(=O)[N-]c1ccccc1", "acetyl(phenyl)azanide"),
    ("a benzoylurea", "O=C([N-]C(=O)c1ccccc1)Nc1ccccc1", "benzoyl(phenylcarbamoyl)azanide"),
    ("a compound prefix is bracketed", "CCCCCCN(C)C(=O)[N-]C", "[hexyl(methyl)carbamoyl](methyl)azanide"),
    ("an N-aryl sulfamide", "CNS(=O)(=O)[N-]c1ccccc1", "(N-methylsulfamoyl)(phenyl)azanide"),
    ("an N,N-dimethyl sulfamide", "CN(C)S(=O)(=O)[N-]c1ccccc1", "(N,N-dimethylsulfamoyl)(phenyl)azanide"),
    ("succinimide", "O=C1CCC(=O)[N-]1", "2,5-dioxopyrrolidin-1-ide"),
    ("phthalimide", "O=C1[N-]C(=O)c2ccccc12", "1,3-dioxo-1,3-dihydro-2H-isoindol-2-ide"),
    ("barbituric acid", "O=C1CC(=O)[N-]C(=O)N1", "2,4,6-trioxo-1,3-diazinan-1-ide"),
    ("barbital", "O=C1NC(=O)C(CC)(CC)C(=O)[N-]1", "5,5-diethyl-2,4,6-trioxo-1,3-diazinan-1-ide"),
    ("a lactam", "O=C1CCCC[N-]1", "2-oxopiperidin-1-ide"),
    ("a cyclic carbamate", "O=C1[N-]C(=O)OC1", "2,4-dioxo-1,3-oxazolidin-3-ide"),
]

SULFAMIDE_OFF_AN_ANION = [
    ("a carboxylate", "[O-]C(=O)c1ccccc1NS(=O)(=O)N(C)C", "2-[(dimethylaminosulfonyl)amino]benzoate"),
    ("a phenolate", "[O-]c1ccccc1NS(=O)(=O)N(C)C", "2-[(dimethylaminosulfonyl)amino]benzen-1-olate"),
    ("on a chain", "[O-]C(=O)CCNS(=O)(=O)N(C)C", "3-[(dimethylaminosulfonyl)amino]propanoate"),
]

#: The ordinary sulfonamide anion and a carboxylate beside a sulfonamide were right before and must not move.
UNCHANGED = [
    ("a sulfonamidate with no neighbour", "O=[N+]([O-])c1ccc(S(=O)(=O)[N-]C)cc1", "N-methyl-4-nitrobenzene-1-sulfonamidate"),
    ("an N-acyl sulfonamidate", "CS(=O)(=O)[N-]C(C)=O", "N-acetylmethanesulfonamidate"),
    ("a plain sulfonamide off a carboxylate", "[O-]C(=O)c1ccccc1S(=O)(=O)N(C)C", "2-(N,N-dimethylsulfamoyl)benzoate"),
]

ALL = SULFONAMIDATE_BESIDE_NEUTRAL + AZANIDES + SULFAMIDE_OFF_AN_ANION + UNCHANGED
_uncharge = rdMolStandardize.Uncharger()


def _neutral_key(smiles_or_mol) -> str:
    mol = Chem.MolFromSmiles(smiles_or_mol) if isinstance(smiles_or_mol, str) else smiles_or_mol
    return Chem.MolToInchiKey(_uncharge.uncharge(Chem.Mol(mol)))


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_carries_the_charge_in_a_word(label, smiles, expected):
    """The failure this round fixed: a name with no anion word at all."""
    assert expected.endswith(("ate", "ide", "olate")) or "azanide" in expected, expected
    assert not expected.endswith("amide") or "sulfonamidate" in expected, expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    back_mol = Chem.MolFromSmiles(back)
    if "sulfonamidate" in expected:
        assert _neutral_key(back_mol) == _neutral_key(smiles), expected
    else:
        assert Chem.MolToInchiKey(back_mol) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_an_anion_is_not_named_as_its_neutral_amide():
    for _label, smiles, _expected in SULFONAMIDATE_BESIDE_NEUTRAL:
        assert "ethanamide" not in name_smiles(smiles)
        assert "sulfamoyl" not in name_smiles(smiles)


@pytest.mark.parametrize(
    "smiles,wrong_name",
    [
        ("O=C1CCC(=O)[N-]1", "pyrrolidine-2,5-dione"),
        ("CNS(=O)(=O)[N-]c1ccccc1", "sulfamoylmethane"),
        ("CC(=O)Nc1ccc(S(=O)(=O)[N-]C)cc1", "N-methyl-4-acetamidobenzene-1-sulfonamide"),
        ("c1cc[nH+]cc1", "pyridine"),
        ("CC(=O)[N-]c1ccccc1", "N-phenylethanamide"),
    ],
)
def test_a_name_without_a_word_for_the_charge_is_refused(smiles, wrong_name):
    with pytest.raises(ValueError, match="keeps the (negative|positive) charge"):
        _check_charge_named(Chem.MolFromSmiles(smiles), wrong_name)


@pytest.mark.parametrize(
    "smiles,name",
    [
        ("O=C1CCC(=O)[N-]1", "2,5-dioxopyrrolidin-1-ide"),
        ("c1cc[nH+]cc1", "pyridin-1-ium"),
        ("[Na+].[Cl-]", "sodium chloride"),             # a salt is two fragments: not judged here
        ("C[NH2+]CC(=O)[O-]", "2-(methylazaniumyl)acetate"),  # net zero: a zwitterion is not judged here
        ("O=[N+]([O-])c1ccccc1", "nitrobenzene"),         # charge-separated, net zero
        ("CC(=O)Nc1ccccc1", "N-phenylacetamide"),         # neutral
    ],
)
def test_the_guard_leaves_everything_else_alone(smiles, name):
    _check_charge_named(Chem.MolFromSmiles(smiles), name)


def test_an_ion_the_engine_cannot_name_is_refused_not_named_neutral():
    with pytest.raises(ValueError):
        name_smiles("NC(=[NH2+])C(C(=O)O)(C(=O)O)CC(=O)[O-]")  # a carboxylate beside TWO neutral acids on an amidinium: no renderer, the name used to be the neutral compound's (saccharin's anion is named since round 49, the pyrazolone anion since round 51)
