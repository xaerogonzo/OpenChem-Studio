"""Naming round 64 (D-303, D-304): a lactam anion beside an acid anion, and a nitro carbon acid the round 63 ylide test took for an ylide.

D-303: a lactam's ring `[N-]` (a pyroglutamate anion, 5-oxopyrrolidine-2-carboxylate with the amide nitrogen deprotonated too) beside a carboxylate was REFUSED in 29 of the dianion
  population's ions: the acid anion is the parent and the ring `[N-]` is cited as the infix of round 59, which was written only for an aromatic `[n-]` (and, since round 60, for a lactam
  as a SUBSTITUENT). `3-methyl-5-oxopyrrolidin-1-id-2-carboxylate` is the name OPSIN reads. It is cited when it is the ONE ring anion: two of them are written with the multiplied
  `-ide` after the suffixes (`...-5-carbonitrile-1',2-diide`), which OPSIN cannot read, so the lactam is then left out and the guard refuses.
D-304: round 63 declined the stabilised-carbanion claim when a cation was bonded to the carbanion (a diazo carbon is an ylide); a nitro group's N+ is bonded to the carbon of a nitro carbon
  acid and is charge-separated and neutral, so `2-amino-5-nitro-4,6-dioxo-1,4,5,6-tetrahydropyrimidin-5-ide` was refused. The nitro group is not an ylide cation.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a methylpyroglutamate anion", "CC1CC(=O)[N-]C1C(=O)[O-]", "3-methyl-5-oxopyrrolidin-1-id-2-carboxylate"),
    ("a pyroglutamate anion", "O=C1CCC(C(=O)[O-])[N-]1", "5-oxopyrrolidin-1-id-2-carboxylate"),
    ("an oxindole anion with an acetate", "O=C1[N-]c2ccccc2C1CC(=O)[O-]", "(2-oxo-2,3-dihydro-1H-indol-1-id-3-yl)acetate"),
    ("a nitro carbon acid", "O=c1[nH]c(N)nc(=O)[c-]1[N+](=O)[O-]", "2-amino-5-nitro-4,6-dioxo-1,4,5,6-tetrahydropyrimidin-5-ide"),
    ("a nitro carbon acid beside an oxonium", "C[OH+]c1ccccc1Nc1nc(=O)[c-]([N+](=O)[O-])c(=O)[nH]1",
     "2-{[2-(methyloxidaniumyl)phenyl]amino}-5-nitro-4,6-dioxo-1,4,5,6-tetrahydropyrimidin-5-ide"),
]

KEPT = [
    ("a lactam anion alone", "O=C1CCC(=O)[N-]1", "2,5-dioxopyrrolidin-1-ide"),
    ("a lactam anion beside an ammonium", "O=C1[N-]CCCC1[NH3+]", "3-azaniumyl-2-oxopiperidin-1-ide"),
    ("an anilide beside a carboxylate", "CC(=O)[N-]c1ccc(C(=O)[O-])cc1", "4-(acetylazanidyl)benzoate"),
    ("a diazo ylide stays its own classifier's", "C[CH-][N+]#N", "ethan-1-id-1-yldiazonium"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_ion(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.GetFormalCharge(Chem.MolFromSmiles(back)) == Chem.GetFormalCharge(Chem.MolFromSmiles(smiles)), (expected, back)
    assert pop._inchikey(back, neutral=True) == pop._inchikey(smiles, neutral=True), (expected, back)


@pytest.mark.parametrize("smiles", [
    "COc1ccc(OC)c(-c2[n-]nc3c2[C@]2(C(=O)[N-]c4ccc(C)c(Br)c42)C(C#N)=C(N)O3)c1",     # a lactam anion and an azolide: two ring anions
    "O=C1[N-]c2c(ccc3c2[N-]CCC3)C2CCCC12",                                         # two ring anions
])
def test_two_ring_anions_with_a_lactam_are_refused_not_written_with_a_trailing_diide(smiles):
    with pytest.raises(ValueError):
        name_smiles(smiles)
