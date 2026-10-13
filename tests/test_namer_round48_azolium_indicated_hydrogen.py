"""Naming round 48 (D-240): in a hydro azolium, the cation and the indicated hydrogen are on different nitrogens.

`Cn1c[n+](C)c2CCCCc12` was `1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-1-ium`: the `-ium` and the indicated hydrogen on N1, which OPSIN reads with a hydrogen too many
(`C[NH+]1CN(C2=C1CCCC2)C`, a different molecule). An N-substituted [n+] takes the `-ium` and cannot also be the indicated-hydrogen site, so the retag moves the `1H` to a neutral
substituted nitrogen (`1,3-dimethyl-1H-benzimidazol-3-ium`). That retag read only the START of the name, and a hydro block comes first (`4,5,6,7-tetrahydro-1H-...`), so a hydro
parent was never retagged. Of the two candidates (one numbering with the cation at 3, one at 1), the wrong one won on the lowest cation locant.

Found by methylating one basic nitrogen of every census molecule (1036 quaternary cations): the hypothesis was a hydro omission like round 47's, and there was none; this was the one
real defect. Every name pinned here is read back through OPSIN to its input, charge included.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
ROWS = [
    ("a tetrahydrobenzimidazolium", "Cn1c[n+](C)c2CCCCc12", "1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium"),
    ("the same ring written the other way round", "Cn1c[n+](C)c2c1CCCC2", "1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium"),
    ("with a 2-acyl group", "Cn1c(C(C)=O)[n+](C)c2CCCCc12", "2-acetyl-1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium"),
    ("the census structure, N-hydroxy", "Cc1ccc(C(=O)c2n(O)c3c([n+]2C)CCCC3)cc1",
     "1-hydroxy-3-methyl-2-(4-methylbenzoyl)-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium"),
    ("an imidazolinium (dihydro)", "Cn1c[n+](C)CC1", "1,3-dimethyl-4,5-dihydro-1H-imidazol-3-ium"),
    ("a hexahydro benzimidazolium", "C[N+]1=CN(C)C2CCCCC12", "1,3-dimethyl-3a,4,5,6,7,7a-hexahydro-1H-1,3-benzimidazol-3-ium"),
    ("two different N-substituents, the ethyl on the cation", "Cn1c[n+](CC)c2CCCCc12", "3-ethyl-1-methyl-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium"),
    ("two different N-substituents, the methyl on the cation", "CCn1c[n+](C)c2CCCCc12", "1-ethyl-3-methyl-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium"),
    ("unchanged: the aromatic benzimidazolium", "Cn1c[n+](C)c2ccccc12", "1,3-dimethyl-1H-benzimidazol-3-ium"),
    ("unchanged: an imidazolium", "Cn1cc[n+](C)c1", "1,3-dimethyl-1H-imidazol-3-ium"),
    ("unchanged: an N-hydroxy imidazolium", "Cn1cc[n+](O)c1", "3-hydroxy-1-methyl-1H-imidazol-3-ium"),
]


@pytest.mark.parametrize("label,smiles,expected", ROWS, ids=[row[0] for row in ROWS])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles,expected", ROWS, ids=[row[0] for row in ROWS])
def test_the_ium_and_the_indicated_hydrogen_are_on_different_atoms(label, smiles, expected):
    """The symptom: `...-1H-...-1-ium`."""
    import re

    indicated = re.search(r"(\d+)H-", expected)
    cation = re.search(r"-(\d+)-ium", expected)
    assert indicated and cation, expected
    assert indicated.group(1) != cation.group(1), expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ROWS, ids=[row[0] for row in ROWS])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_old_name_is_the_one_opsin_misreads():
    """What this round removed: the name that put the cation and the indicated hydrogen on N1."""
    pytest.importorskip("py2opsin")
    if shutil.which("java") is None:
        pytest.skip("needs java on PATH")
    from py2opsin import py2opsin

    back = py2opsin("1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-1-ium")
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) != Chem.MolToInchiKey(Chem.MolFromSmiles("Cn1c[n+](C)c2CCCCc12"))
