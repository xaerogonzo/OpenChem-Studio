"""Naming round 37 (D-210): a fused ring system with a bridgehead N+ in a double bond is named, instead of a NAMING ERROR.

Quinolizinium (`c1cc[n+]2ccccc2c1`), a tetrahydroquinolizinium, an indolizinium, and the bicyclic amidiniums written with the charge on the bridgehead (`C1C[N+]2=C(CCCCC2)NC1`, the
protonated DBU skeleton drawn the other way) had no name: `fusion_general` describes a ring on a NEUTRAL copy, and a bridgehead N+ with three ring bonds and a double bond has no neutral
copy with the same bonds (valence 4). 190 of 288 such bicycles were a visible `[NAMING ERROR ...]`. Two copies are made now: a twin for the fusion namer (the N+=C bond made single, the carbon
given its hydrogen: `4H-quinolizine`), and a CARBON ANALOGUE for the hydrogen planner, because the bridgehead N+ is a pi atom of the cation as the carbon of the isoelectronic carbocycle is
(quinolizinium plans as naphthalene). The `-ium` is added at the nitrogen's own locant, as for every ring cation.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
NAMED = [
    ("quinolizinium", "c1cc[n+]2ccccc2c1", "quinolizin-5-ium"),
    ("tetrahydroquinolizinium", "c1cc[n+]2c(c1)CCCC2", "1,2,3,4-tetrahydroquinolizin-5-ium"),
    ("a methyl tetrahydroquinolizinium", "Cc1cc[n+]2c(c1)CCCC2", "2-methyl-6,7,8,9-tetrahydroquinolizin-5-ium"),
    ("dihydroindolizinium", "c1cc[n+]2c(c1)CCC2", "2,3-dihydro-1H-indolizin-4-ium"),
    ("a pyridinium fused to a seven ring", "c1cc[n+]2c(c1)CCCCC2", "7,8,9,10-tetrahydro-6H-pyrido[1,2-a]azepin-5-ium"),
    ("a saturated bridgehead iminium, 5-5", "C1CC[N+]2=C(C1)CCC2", "2,3,5,6,7,8-hexahydro-1H-indolizin-4-ium"),
    ("a bridgehead iminium, 6-7", "C1CCC2=[N+](CC1)CCCC2", "2,3,4,6,7,8,9,10-octahydro-1H-pyrido[1,2-a]azepin-5-ium"),
    ("a methyl on a bridgehead iminium", "CC1CCC[N+]2=C(CC1)CCC2", "8-methyl-2,3,5,6,7,8,9,10-octahydro-1H-pyrrolo[1,2-a]azocin-4-ium"),
    ("the DBU skeleton, charge on the bridgehead", "C1C[N+]2=C(CCCCC2)NC1", "2,3,4,6,7,8,9,10-octahydro-1H-pyrimido[1,2-a]azepin-5-ium"),
    ("the same with an N-methyl", "C1C[N+]2=C(CCCCC2)N(C)C1", "1-methyl-2,3,4,6,7,8,9,10-octahydro-1H-pyrimido[1,2-a]azepin-5-ium"),
    ("an imidazo-pyridine amidinium", "C1CC[N+]2=C(C1)NCC2", "2,3,5,6,7,8-hexahydro-1H-imidazo[1,2-a]pyridin-4-ium"),
    ("a pyrido-pyrimidine amidinium", "C1CC[N+]2=C(C1)NCCC2", "1,2,3,4,6,7,8,9-octahydropyrido[1,2-a]pyrimidin-5-ium"),
]

# Names that existed before keep them: the same amidinium with the charge on the other nitrogen, its neutral base, and a pyridinium.
UNCHANGED = [
    ("the DBU skeleton, charge on the imine nitrogen", "C1CCC2=[NH+]CCCN2CC1", "2,3,4,6,7,8,9,10-octahydropyrimido[1,2-a]azepin-1-ium"),
    ("the neutral base", "C1CCC2=NCCCN2CC1", "2,3,4,6,7,8,9,10-octahydropyrimido[1,2-a]azepine"),
    ("an N-methylpyridinium", "C[n+]1ccccc1", "1-methylpyridin-1-ium"),
    ("a quaternary bridgehead ammonium (no double bond)", "C[N+]12CCCC1CCC2", "4-methylhexahydro-1H-pyrrolizin-4-ium"),
    ("a quaternary quinolizidinium", "C[N+]12CCCCC1CCCC2", "5-methylquinolizidin-5-ium"),
    ("a bridgehead NH+ ammonium", "C1CC[NH+]2CCCC2C1", "indolizidin-4-ium"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_cation_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_cation(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_two_charge_placements_of_an_amidinium_are_one_ion():
    """Why the DBU rows above may differ in name and still agree: the InChI of both drawings is the same."""
    a = Chem.MolFromSmiles("C1C[N+]2=C(CCCCC2)NC1")
    b = Chem.MolFromSmiles("C1CCC2=[NH+]CCCN2CC1")
    assert Chem.MolToInchiKey(a) == Chem.MolToInchiKey(b)


def test_the_helper_finds_only_a_bridgehead_nitrogen_in_a_double_bond():
    from openchem.vendor.iupac_namer.ring_naming.fusion_general import _bridgehead_iminium

    class Ring:
        def __init__(self, mol):
            self.atom_indices = frozenset(a.GetIdx() for a in mol.GetAtoms() if a.IsInRing())  # as the engine's ring system: ring atoms only

    for smiles, expected in [("c1cc[n+]2ccccc2c1", 1), ("C1CC[N+]2=C(C1)CCC2", 1), ("C1CCC2=[NH+]CCCN2CC1", 0), ("C[n+]1ccccc1", 0), ("C1CC[NH+]2CCCC2C1", 0)]:
        mol = Chem.MolFromSmiles(smiles)
        assert len(_bridgehead_iminium(mol, Ring(mol))) == expected, smiles
