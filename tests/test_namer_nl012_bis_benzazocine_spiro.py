"""NL-012 shape 4 (D-395): spiro of two methano-benzazocines.

The matrix re-measure (2026-11-03) found the engine's ``...-4,1'-...`` name
OPSIN reads as another molecule.  The fix cites the ring-table PIN on the
unprimed partner and the von Baeyer systematic name on the primed one with
locants OPSIN accepts (``4,8'``).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

SMILES = "c1ccc2c(c1)CC1CC2CC2(N1)c1ccccc1C1CCNC2C1"
EXPECTED = (
    "spiro[1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine-4,8'-"
    "10-azatricyclo[7.3.1.0^{2,7}]trideca-2(7),3,5-triene]"
)
FORMER = (
    "spiro[1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine-4,1'-"
    "1,2,3,4,5,6-hexahydro-2,6-methano-3-benzazocine]"
)


def test_d395_name():
    assert name_smiles(SMILES) == EXPECTED


@needs_opsin
def test_d395_opsin_read_back():
    from py2opsin import py2opsin

    back = py2opsin(EXPECTED)
    assert back
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(SMILES)
    )
