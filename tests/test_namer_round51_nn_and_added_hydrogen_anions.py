"""Naming round 51 (D-248, D-249): the anion of a hydrazide, and a ring anion whose attachment locant cites an added hydrogen or a prime.

D-248: `CC(=O)[N-]N` (the nitrogen of a hydrazide) had no classifier: the azanide route refused any neighbour that was not carbon or a sulfamoyl sulfur, so the plan search
neutralised it and the name carried `NAMING ERROR: ... [NH-]N`. A neutral nitrogen beside the anionic one is the hydrazide's other nitrogen; the name is `acetyl(amino)azanide`,
which OPSIN reads back (P-72.2.2.2).
D-249 (and a nitro group beside a ring anion): a ring anion is named as the ring's substituent group with `yl` changed to `ide`, and the attachment locant was read with a regex that stopped at `3(2H)-` or `1'-`. A group
the regex could not read fell through to the parent-hydride splice, which wrote `1,3-benzothiazol-2(3H)-on-1-ide` (the locant wrong too, and a spelling OPSIN cannot parse), or refused
(a spiro oxindole anion). The locant may now carry an added hydrogen or a prime.

Both found by `tools/naming_ion_populations.py` with five site patterns it had not tried (a lactam NH, a hydrazide NH, an azole NH, a hydroxamic acid, and the oxygen of an amide
or a ketone).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.perception.charge_perception import _split_substituent_locant

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
HYDRAZIDE = [
    ("acethydrazide anion", "CC(=O)[N-]N", "acetyl(amino)azanide"),
    ("benzohydrazide anion", "N[N-]C(=O)c1ccccc1", "amino(benzoyl)azanide"),
    ("the other nitrogen carries an alkyl", "CN[N-]C(C)=O", "acetyl(methylamino)azanide"),
    ("the other nitrogen carries a pentenyl and the acyl is a ring acyl", "CC=CCCN[N-]C(=O)c1ccncc1",
     "[(pent-3-en-1-yl)amino](pyridine-4-carbonyl)azanide"),
    ("the pyrazolone anion round 46 left refused", "O=C1[N-]N=CC1", "5-oxo-4,5-dihydro-1H-pyrazol-1-ide"),
    ("a diacylhydrazine anion", "CC(=O)[N-]NC(C)=O", "(acetamido)(acetyl)azanide"),
]

ADDED_HYDROGEN = [
    ("a benzothiazolone anion", "O=c1[n-]c2ccccc2s1", "2-oxo-1,3-benzothiazol-3(2H)-ide"),
    ("a pyranopyrazole anion", "CSc1ccc([C@H]2C(C#N)=C(N)Oc3n[n-]c(-c4ccccc4)c32)cc1",
     "(4S)-6-amino-5-cyano-4-[4-(methylsulfanyl)phenyl]-3-phenylpyrano[2,3-c]pyrazol-2(4H)-ide"),
    ("a pyrazolidinedione anion, the other ring nitrogen substituted", "O=C1[N-]N(c2ccccc2)C(=O)C1", "3,5-dioxo-2-phenylpyrazolidin-1-ide"),
]

NITRO_BESIDE = [
    ("a triazolide with a nitroaryl elsewhere", "CC(C)c1nc(SCC(=O)Nc2ccc(F)c([N+](=O)[O-])c2)n[n-]1",
     "3-{[2-(4-fluoro-3-nitroanilino)-2-oxoethyl]sulfanyl}-5-(propan-2-yl)-1H-1,2,4-triazol-1-ide"),
    ("a nitropyrrolide", "c1cc([N+](=O)[O-])c[n-]1", "3-nitro-1H-pyrrol-1-ide"),
]

PRIMED = [
    ("a spiro oxindole anion", "O=C1[N-]c2ccccc2C11CCNC1", "2'-oxospiro[pyrrolidine-3,3'-2,3-dihydro-1H-indole]-1'-ide"),
]

ALL = HYDRAZIDE + ADDED_HYDROGEN + NITRO_BESIDE + PRIMED


def _neutral_key(smiles: str) -> str:
    """The InChIKey of the molecule with its negative charge removed: standard InChI places a proton, so the question is the connectivity."""
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
def test_the_name_reads_back_to_the_anion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    mol = Chem.MolFromSmiles(back)
    assert Chem.GetFormalCharge(mol) == -1, (expected, back)
    assert _neutral_key(back) == _neutral_key(smiles), (expected, back)


@pytest.mark.parametrize(
    "group,expected",
    [
        ("propan-2-yl", (2, "propan-2-")),
        ("2-oxo-1,3-benzothiazol-3(2H)-yl", (3, "2-oxo-1,3-benzothiazol-3(2H)-")),
        ("pyrano[2,3-c]pyrazol-2(4H)-yl", (2, "pyrano[2,3-c]pyrazol-2(4H)-")),
        ("2'-oxospiro[pyrrolidine-3,3'-indol]-1'-yl", (1, "2'-oxospiro[pyrrolidine-3,3'-indol]-1'-")),
        ("cyclohexylmethyl", (None, "cyclohexylmeth")),
    ],
)
def test_the_attachment_locant_is_read_through_an_added_hydrogen_and_a_prime(group, expected):
    assert _split_substituent_locant(group) == expected


def test_a_hydrazine_with_an_acyl_on_each_nitrogen_still_has_one_charge():
    mol = Chem.MolFromSmiles("CC(=O)[N-]NC(C)=O")
    assert Chem.GetFormalCharge(mol) == -1
    assert name_smiles("CC(=O)[N-]NC(C)=O").endswith("azanide")


def test_the_neutral_hydrazide_is_still_named_as_one():
    assert name_smiles("CC(=O)NN") == "acetohydrazide"


def test_a_sulfonamide_anion_is_still_a_sulfonamidate():
    assert name_smiles("CS(=O)(=O)[N-]C").endswith("sulfonamidate")
