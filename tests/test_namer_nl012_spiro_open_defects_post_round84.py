"""NL-012 spiro joints that rounds 84–85 left open (adamantane, pteridin diketones, benzazocine).

Shape 4 (D-395) is pinned in ``test_namer_nl012_bis_benzazocine_spiro.py``.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# NL-012 matrix shape (1): round-85 tricyclic + substituent (no longer a naming error).
ADAMANTANE_SUBSTITUENT = (
    "O=C(O)C12CCC3(CC1CCc1ccccc12)C1CC2C3C2(S)C1",
    "6'-sulfanylspiro[1,2,3,4,4a,9,10,10a-octahydrophenanthrene-2,3'-tricyclo[2.2.1.0^{2,6}]heptane]-4a-carboxylic acid",
)

# Shapes (2) and (3): OPSIN reads ``-2',4(3H)-dione``, not ``-2',4-dione``.
PTERIDIN_IMIDAZO = (
    "NC1Nc2c(nc[nH]c2=O)N(O)C12C(=O)NC1=Nc3ccccc3CN12",
    "6-amino-8-hydroxyspiro[5,6,7,8-tetrahydropteridine-7,3'-1,2,3,5-tetrahydroimidazo[2,1-b]quinazoline]-2',4(3H)-dione",
)

PTERIDIN_BENZODIAZEPINE = (
    "O=C1Nc2ccccc2C=NC12CNc1c(nc[nH]c1=O)N2",
    "spiro[5,6,7,8-tetrahydropteridine-7,3'-2,3-dihydro-1H-1,4-benzodiazepine]-2',4(3H)-dione",
)


@pytest.mark.parametrize(
    "smiles,expected",
    [ADAMANTANE_SUBSTITUENT, PTERIDIN_IMIDAZO, PTERIDIN_BENZODIAZEPINE],
    ids=["adamantane_sub", "pteridin_imidazo", "pteridin_bzd"],
)
def test_nl012_spiro_shapes_name(smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize(
    "smiles,expected",
    [ADAMANTANE_SUBSTITUENT, PTERIDIN_IMIDAZO, PTERIDIN_BENZODIAZEPINE],
    ids=["adamantane_sub", "pteridin_imidazo", "pteridin_bzd"],
)
def test_nl012_spiro_shapes_read_back(smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert _key(back) == _key(smiles), (expected, back)