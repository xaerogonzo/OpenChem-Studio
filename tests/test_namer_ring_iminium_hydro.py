"""Naming round 34 (D-207): a partly saturated ring whose nitrogen is cationic keeps its hydro prefixes.

A monocyclic ring cation with a C=N+ in it (a protonated cyclic imine, an N-alkyl iminium, a cyclic amidinium: `C1CC=[NH+]C1`, `C[N+]1=C(C)NCC1`, `CC1=[NH+]CCCC1`) was named
as the FULLY unsaturated or fully saturated ring with an `-ium`, a different molecule: `azol-1-ium` (an aromatic pyrrolium), `2,3-dimethyl-1,3-diazol-3-ium` (an
imidazolium), `azinan-1-ium` (piperidinium). Two refusals in the same shape caused it. `monocyclic._collect_hydro_locants` returned nothing on the first charged ring atom,
although a ring N+ in a double bond is no hydro position, and `retained_lookup._try_derive_hydro_retained` did the same for the pyridine family and then looked the ring up
as the CATION entry (`pyridinium`), which is no parent for hydro prefixes; a charged ring is now looked up on its neutral copy first.

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
    ("protonated 1-pyrroline", "C1CC=[NH+]C1", "3,4-dihydro-2H-azol-1-ium"),
    ("N-methyl 1-pyrrolinium", "C[N+]1=CCCC1", "1-methyl-3,4-dihydro-2H-azol-1-ium"),
    ("protonated 2-methylimidazoline", "CC1=[NH+]CCN1", "2-methyl-4,5-dihydro-1H-1,3-diazol-3-ium"),
    ("N-methyl imidazolinium", "C[N+]1=C(C)NCC1", "2,3-dimethyl-4,5-dihydro-1H-1,3-diazol-3-ium"),
    ("protonated 2-methyloxazoline", "CC1=[NH+]CCO1", "2-methyl-4,5-dihydro-1,3-oxazol-3-ium"),
    ("protonated 2-methylthiazoline", "CC1=[NH+]CCS1", "2-methyl-4,5-dihydro-1,3-thiazol-3-ium"),
    ("protonated tetrahydropyrimidine", "CC1=[NH+]CCCN1", "2-methyl-3,4,5,6-tetrahydropyrimidin-1-ium"),
    ("protonated 2,3,4,5-tetrahydropyridine", "C1CC[NH+]=CC1", "2,3,4,5-tetrahydropyridin-1-ium"),
    ("N-methyl 2,3,4,5-tetrahydropyridinium", "C[N+]1=CCCCC1", "1-methyl-2,3,4,5-tetrahydropyridin-1-ium"),
    ("N-ethyl 6-methyl iminium", "CC[N+]1=C(C)CCCC1", "1-ethyl-6-methyl-2,3,4,5-tetrahydropyridin-1-ium"),
    ("the iminium with the N-methyl written first", "C1CC[N+](C)=CC1", "1-methyl-2,3,4,5-tetrahydropyridin-1-ium"),
    ("protonated 2,3-dihydropyridine", "C1=CCC[NH+]=C1", "2,3-dihydropyridin-1-ium"),
    ("protonated 1,2,3,4-tetrahydropyridine", "C1CC=C[NH2+]C1", "1,2,3,4-tetrahydropyridin-1-ium"),
    ("N-methyl 1,2,3,4-tetrahydropyridinium", "C[NH+]1CCCC=C1", "1-methyl-1,2,3,4-tetrahydropyridin-1-ium"),
]

# Names that existed before the round keep them: a ring cation whose ring has no saturated atom, a saturated one, a charged sp3 nitrogen, and the neutral rings.
UNCHANGED = [
    ("pyridinium", "c1cc[nH+]cc1", "pyridin-1-ium"),
    ("N-methylpyridinium", "C[n+]1ccccc1", "1-methylpyridin-1-ium"),
    ("piperidinium", "C1CC[NH2+]CC1", "piperidin-1-ium"),
    ("a charged sp3 nitrogen", "C1=CC[NH2+]CC1", "1,2,3,6-tetrahydropyridin-1-ium"),
    ("a charged sp3 nitrogen in a five ring", "C1=CC[NH2+]C1", "2,5-dihydro-1H-pyrrol-1-ium"),
    ("the neutral imidazoline", "CC1=NCCN1", "2-methyl-4,5-dihydro-1H-imidazole"),
    ("the neutral tetrahydropyridine", "C1CCN=CC1", "3,4,5,6-tetrahydropyridine"),
]


@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_ring_cation_is_named(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED + UNCHANGED, ids=[row[0] for row in NAMED + UNCHANGED])
def test_the_name_reads_back_to_the_cation(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_a_name_that_drops_the_hydro_prefixes_is_a_different_molecule():
    # What the defect printed, so the read-back above cannot be satisfied by two molecules that merely share a skeleton.
    assert name_smiles("C1CC=[NH+]C1") != "azol-1-ium"
    assert name_smiles("C[N+]1=C(C)NCC1") != "2,3-dimethyl-1,3-diazol-3-ium"
    assert name_smiles("CC1=[NH+]CCCC1") != "6-methylazinan-1-ium"
