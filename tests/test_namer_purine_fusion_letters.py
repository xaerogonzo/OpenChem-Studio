"""Naming round 33 (D-206): a fused ring on purine is lettered along the periphery, not by sorting its locants.

`fusion_general._periphery_order` listed a component's peripheral atoms in the order of its locants, which is the order of the periphery wherever the numbering runs
once round the ring system. Purine's does not: its fusion atoms are 4 and 5 and the periphery runs 1, 2, 3, 4, 9, 8, 7, 5, 6, so the sides are a 1-2, b 2-3, c 3-4,
d 4-9, e 9-8, f 8-7, g 7-5, h 5-6, i 6-1. Sorting the locants made 7-8 'g' (it is 'f') and 8-9 'h' (it is 'e'): `imidazo[1,2-g]purine` for the skeleton OPSIN calls
`imidazo[2,1-f]purine`, a name OPSIN reads as another molecule, and `imidazo[2,1-h]purine`, `pyrimido[2,1-h]purine` ... which it cannot read at all.
The periphery is walked from the side 1-2 towards the lower neighbour (P-25.3.1.3) and used when it differs from the locant order, so ordinary numbering cannot move.

32 structures OPSIN builds from `X[n,m-L]purine` names, master -> now: exact 21 -> 32 (9 unreadable, 1 wrong molecule, 1 naming error before).
Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (SMILES, the name, whether master named it differently)
ROWS = [
    ('c1cn2cc3[nH]cnc3nc2n1', '1H-imidazo[1,2-a]purine', False),
    ('c1cn2c(n1)[nH]c1cncnc12', '5H-imidazo[1,2-e]purine', True),
    ('c1cn2c(n1)ncc1[nH]cnc12', '3H-imidazo[2,1-b]purine', False),
    ('C1=Nc2nc3ncncc3n2C1', '6H-imidazo[2,1-f]purine', True),
    ('c1cn2cnc3nc[nH]c3c2n1', '1H-imidazo[2,1-i]purine', True),
    ('c1cnc2nc3ncnc-3cn2c1', 'pyrimido[1,2-a]purine', False),
    ('C1=CN2C=NC=C3NC=NC32N=C1', '2,4,7,9,13-pentaazatricyclo[7.4.0.0^{1,5}]trideca-2,5,7,10,12-pentaene', False),
    ('c1cnc2nc3cncnc3n2c1', 'pyrimido[1,2-e]purine', True),
    ('C1=CN2C=NC3=NC=NCC32N=C1', '2,6,8,10,12-pentaazatricyclo[7.4.0.0^{1,6}]trideca-2,4,7,9,11-pentaene', False),
    ('c1ccn2cc3ncnc-3nc2c1', 'pyrido[1,2-a]purine', False),
    ('C1=CN2C=NC=C3NC=NC32C=C1', '2,4,7,9-tetraazatricyclo[7.4.0.0^{1,5}]trideca-2,5,7,10,12-pentaene', False),
    ('c1ccn2c(c1)nc1cncnc12', 'pyrido[1,2-e]purine', True),
    ('C1=CN2C=NC3=NC=NCC32C=C1', '3,5,7,9-tetraazatricyclo[7.4.0.0^{1,6}]trideca-3,5,7,10,12-pentaene', False),
    ('c1nc2cn3ccsc3nc-2n1', '[1,3]thiazolo[3,2-a]purine', False),
    ('C1=CN2C=NC=C3NC=NC32S1', '12-thia-2,4,7,9-tetraazatricyclo[7.3.0.0^{1,5}]dodeca-2,5,7,10-tetraene', False),
    ('c1ncc2nc3sccn3c2n1', '[1,3]thiazolo[3,2-e]purine', True),
    ('C1=CN2C=NC3=NC=NCC32S1', '2-thia-5,7,9,11-tetraazatricyclo[6.4.0.0^{1,5}]dodeca-3,6,8,10-tetraene', False),
    ('c1nc2cn3ccoc3nc-2n1', '[1,3]oxazolo[3,2-a]purine', False),
    ('C1=CN2C=NC=C3NC=NC32O1', '12-oxa-2,4,7,9-tetraazatricyclo[7.3.0.0^{1,5}]dodeca-2,5,7,10-tetraene', False),
    ('c1ncc2nc3occn3c2n1', '[1,3]oxazolo[3,2-e]purine', True),
    ('C1=CN2C=NC3=NC=NCC32O1', '2-oxa-5,7,9,11-tetraazatricyclo[6.4.0.0^{1,5}]dodeca-3,6,8,10-tetraene', False),
    ('c1nc2nc3nncn3cc2[nH]1', '6H-[1,2,4]triazolo[4,3-a]purine', False),
    ('c1ncc2[nH]c3nncn3c2n1', '9H-[1,2,4]triazolo[4,3-e]purine', True),
    ('c1nc2nc3nc[nH]c3cn2n1', '1H-[1,2,4]triazolo[1,5-a]purine', False),
    ('c1ncc2[nH]c3ncnn3c2n1', '9H-[1,2,4]triazolo[1,5-e]purine', True),
    ('c1cc2nc3nc[nH]c3cn2n1', '1H-pyrazolo[1,5-a]purine', False),
    ('c1ncc2[nH]c3ccnn3c2n1', '5H-pyrazolo[1,5-e]purine', True),
    ('c1cc2nc3nc[nH]c3cn2c1', '1H-pyrrolo[1,2-a]purine', False),
    ('c1cc2[nH]c3cncnc3n2c1', '5H-pyrrolo[1,2-e]purine', True),
    ('C1=CC23N=CN=C2N=CN=C3S1', '10-thia-2,4,6,8-tetraazatricyclo[7.3.0.0^{1,5}]dodeca-2,4,6,8,11-pentaene', False),
    ('C1=CC23N=CN=C2N=CN=C3O1', '10-oxa-2,4,6,8-tetraazatricyclo[7.3.0.0^{1,5}]dodeca-2,4,6,8,11-pentaene', False),
    ('C1=CC2=NC=NC3=NC=NC23C=C1', '2,4,6,8-tetraazatricyclo[7.4.0.0^{1,5}]trideca-2,4,6,8,10,12-hexaene', False),
]


@pytest.mark.parametrize("smiles,expected,moved", ROWS, ids=[row[1] for row in ROWS])
def test_the_fused_purine_is_lettered_along_its_periphery(smiles, expected, moved):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("smiles,expected,moved", ROWS, ids=[row[1] for row in ROWS])
def test_the_name_reads_back_to_the_molecule(smiles, expected, moved):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_six_ring_sides_keep_their_letters():
    """Purine's sides a to c (1-2, 2-3, 3-4) are the same in both orders: the walk changes nothing there."""
    assert name_smiles("c1cn2cc3[nH]cnc3nc2n1") == "1H-imidazo[1,2-a]purine"


def test_a_ring_system_numbered_once_round_is_lettered_as_before():
    """Mutation guard for the walk: naphthalene-like and indole-like bases (numbering runs round the periphery) keep every letter."""
    assert name_smiles("c1ccc2c(c1)ccc1ccccc12") == "phenanthrene"
    assert name_smiles("c1ccc2c(c1)[nH]c1ccccc12") == "9H-carbazole"
    assert name_smiles("c1ccc2[nH]cnc2c1") == "1H-benzimidazole"
    assert name_smiles("c1ccc2nc3ccccc3cc2c1") == "acridine"
    assert name_smiles("Cc1cn2c(n1)[nH]c1ccccc12") == "2-methyl-9H-imidazo[1,2-a][1,3]benzimidazole"
