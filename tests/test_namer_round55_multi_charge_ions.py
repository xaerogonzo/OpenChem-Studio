"""Naming round 55 (D-265 .. D-267): what the multi-charge populations found.

`tools/naming_ion_populations.py` gained three modes this round: `zwitterion` (an acid deprotonated AND a base protonated in one molecule), `dianion` (two acid sites) and `dication` (two base
sites). A net-neutral ion was never judged by the charge guard at all, and the single-site populations could not reach a molecule with two charges.

D-265: a ring-nitrogen amide whose ring is a CATION was written `4-methylpiperazin-4-iume-1-carbonyl`: the acyl-prefix builder turns `...-1-yl` into `...e-1-carbonyl`, and the `e` landed after
  the `ium` infix. OPSIN cannot read it; `4-methylpiperazin-4-ium-1-carbonyl` it can.
D-266: a curated ring whose NAME carries its ketone (`pyrido[1,2-a]pyrimidin-4-on`), cationic, as a SUBSTITUENT put the `ium` after the ketone (`...-4-on-1-ium-2-yl`, unreadable); it goes before
  it, as in the standalone form (`...-1-ium-4-one`).
D-267: the charge guard judged only the NET charge, so a zwitterion (net 0) was never judged, and an ion with both a cation and an anion could lose one while the other kept its word. Each
  polarity must now have a word in the name. The case that found it, an acylsulfonamide anion beside a thiazolium, was named with the anion dropped; it is refused now.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.engine import _check_charge_named

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
RING_ACYL_CATION = [
    ("a piperazinium amide on an anilinium", "[NH3+]c1ccccc1C(=O)N1CC[NH+](C)CC1", "2-(4-methylpiperazin-4-ium-1-carbonyl)benzen-1-aminium"),
    ("the same, drawn from the other end", "C[NH+]1CCN(C(=O)c2ccccc2[NH3+])CC1", "2-(4-methylpiperazin-4-ium-1-carbonyl)benzen-1-aminium"),
]

KETONE_RING_CATION = [
    ("a pyridopyrimidinone cation as a substituent", "COc1ccccc1[NH2+]c1nnc(SCc2cc(=O)n3cc(C)ccc3[nH+]2)s1",
     "N-(2-methoxyphenyl)-5-{[(7-methyl-4H-pyrido[1,2-a]pyrimidin-1-ium-4-on-2-yl)methyl]sulfanyl}-1,3,4-thiadiazol-2-aminium"),
]

ALL = RING_ACYL_CATION + KETONE_RING_CATION


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), (expected, back)


def test_the_standalone_ketone_ring_cation_is_unchanged():
    assert name_smiles("Cc1ccc2[nH+]c(CSC)cc(=O)n2c1") == "7-methyl-2-[(methylsulfanyl)methyl]-4H-pyrido[1,2-a]pyrimidin-1-ium-4-one"


def test_a_neutral_ring_nitrogen_acyl_keeps_its_e():
    assert name_smiles("[NH3+]c1ccccc1C(=O)N1CCCCC1") == "2-(piperidine-1-carbonyl)anilinium"


def test_a_zwitterion_that_lost_its_anion_is_refused():
    """The acylsulfonamide anion beside a thiazolium was named with the anion dropped, and nothing checked a net-neutral ion."""
    with pytest.raises(ValueError, match="negative charge"):
        name_smiles("N#C/C(=C\\Nc1ccc(S(=O)(=O)[N-]C(N)=O)cc1)c1[nH+]c(-c2ccc(Br)cc2)cs1")


@pytest.mark.parametrize(
    "smiles",
    ["C[NH2+]CC(=O)[O-]", "C[N+](C)(C)CC(=O)[O-]", "[O-]C(=O)c1ccc(cc1)C[NH3+]", "O=[N+]([O-])c1ccccc1C[NH3+]", "C[N+]([O-])(C)C", "[NH3+]CCS(=O)(=O)[O-]"],
)
def test_the_ordinary_zwitterions_and_charge_separated_groups_are_not_refused(smiles):
    name_smiles(smiles)


def test_the_guard_asks_each_polarity_of_a_net_neutral_ion():
    mol = Chem.MolFromSmiles("C[NH2+]CC(=O)[O-]")
    _check_charge_named(mol, "(methylazaniumyl)acetate")
    with pytest.raises(ValueError):
        _check_charge_named(mol, "2-(methylamino)acetic acid")
    with pytest.raises(ValueError):
        _check_charge_named(mol, "2-(methylaminium)acetic acid")
    with pytest.raises(ValueError):
        _check_charge_named(mol, "(methylamino)acetate")


def test_the_guard_does_not_count_a_nitro_group_as_an_ion():
    _check_charge_named(Chem.MolFromSmiles("O=[N+]([O-])c1ccccc1C[NH3+]"), "[(2-nitrophenyl)methyl]azanium")
    _check_charge_named(Chem.MolFromSmiles("C[N+]([O-])(C)C"), "N,N-dimethylmethanamine N-oxide")


@pytest.mark.parametrize(
    "smiles,name",
    [
        ("CC(=O)[N+]#[C-]", "acetyl isocyanide"),
        ("Cl(=O)O", "chlorous acid"),
        ("Cl(=O)(=O)[O-]", "chlorate"),
    ],
)
def test_a_positive_and_a_negative_on_bonded_atoms_are_one_dipole_not_two_ions(smiles, name):
    """The first version of the guard refused an isocyanide and the halogen oxoacids (33 vendored tests): `[N+]#[C-]` and `[Cl+]([O-])O` are neutral dipoles."""
    _check_charge_named(Chem.MolFromSmiles(smiles), name)
    assert name_smiles(smiles) == name
