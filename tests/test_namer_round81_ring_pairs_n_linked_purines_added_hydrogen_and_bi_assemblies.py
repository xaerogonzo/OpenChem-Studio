"""Naming round 81 (D-367 .. D-370): the defects a SCAN OF PAIRS OF CURATED RINGS finds.

The population is new. Two curated rings (371 entries, 16 atoms or fewer, no charge, no B/Si/P/As/Se/Te/Sb) are joined at a random hydrogen-bearing atom of each, directly or through
CH2, O or NH (4 x 1,500 molecules and two wider seeds of 2,500), named and read back through OPSIN on the standard InChIKey. Clean apart from OPSIN's stereo defaults for a cephem,
a penam, a cepham and a carbapenem, and a hypoxanthine drawn with no ring N-H; the finds:

* D-367 a purine joined through a ring NITROGEN kept the curated `9H`: `(9H-purin-7-yl)acetic acid`, which is another molecule (a hydrogen on N9 AND the substituent on N7). The nitrogen the
  ring hangs on is the indicated-hydrogen site: `(7H-purin-7-yl)`, `(1H-purin-1-yl)`, `(3H-purin-3-yl)`.
* D-368 the added hydrogen of a curated ring ketone (`4(3H)`) stayed on N3 when the substituent was on N1: `1-methyl-5,6,7,8-tetrahydropteridin-4(3H)-one` (a hydrogen on N3 AND a methyl
  on N1), and the same in the substituent form `(imidazo[5,1-f][1,2,4]triazin-4(3H)-on-1-yl)`. It moves to the substituted nitrogen: `4(1H)`.
* D-369 a ring assembly of an indicated-hydrogen component in fusion brackets ran the hydrogen into the `bi`: `3,1'-bi5H-dibenz[b,f]azepine`, which OPSIN reads as another molecule
  (`3,1'-bi(5H-dibenz[b,f]azepine)` reads). `bi1H-indole` reads and keeps its spelling.
* D-370 adenine joined through its AMINO nitrogen to a ring nitrogen was `1-(adenin-9-yl)-...`, the nucleoside form, another molecule. The retained nucleobase substituent forms apply to a
  ring attachment only: `1-[(9H-purin-6-yl)amino]-...`.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a purine joined at N7", "O=C(O)Cn1cnc2ncncc12", "(7H-purin-7-yl)acetic acid"),
    ("...at N1", "O=C(O)Cn1cnc2ncnc-2c1", "(1H-purin-1-yl)acetic acid"),
    ("...at N3", "O=C(O)Cn1cncc2ncnc12", "(3H-purin-3-yl)acetic acid"),
    ("a methyl on N1 of tetrahydropteridinone", "Cn1cnc(=O)c2c1NCCN2", "1-methyl-5,6,7,8-tetrahydropteridin-4(1H)-one"),
    ("an N-linked imidazotriazinone", "O=C(O)Cn1cnc(=O)c2cncn12", "(imidazo[5,1-f][1,2,4]triazin-4(1H)-on-1-yl)acetic acid"),
    ("an N1-linked tetrahydropteridinone", "O=C(O)Cn1cnc(=O)c2c1NCCN2", "(5,6,7,8-tetrahydropteridin-4(1H)-on-1-yl)acetic acid"),
    ("two dibenzazepines", "C1=Cc2ccc(-c3cccc4c3C=Cc3ccccc3N4)cc2Nc2ccccc21", "3,1'-bi(5H-dibenz[b,f]azepine)"),
    ("adenine joined through its amino nitrogen", "O=C1NCCc2cnn(Nc3ncnc4[nH]cnc34)c21", "1-[(9H-purin-6-yl)amino]-1,4,5,6-tetrahydro-7H-pyrazolo[3,4-c]pyridin-7-one"),
]

KEPT = [
    ("a purine joined at N9", "O=C(O)Cn1cnc2c1ncnc2", "(9H-purin-9-yl)acetic acid"),
    ("a methyl on N3 of tetrahydropteridinone", "Cn1cnc2c(c1=O)NCCN2", "3-methyl-5,6,7,8-tetrahydropteridin-4(3H)-one"),
    ("an N3-linked tetrahydropteridinone", "O=C(O)Cn1cnc2c(c1=O)NCCN2", "(5,6,7,8-tetrahydropteridin-4(3H)-on-3-yl)acetic acid"),
    ("two indoles", "c1ccc2[nH]ccc2c1-c1cccc2[nH]ccc12", "4,4'-bi1H-indole"),
    ("adenine as a nucleoside base", "OC1C(O)C(CO)OC1n1cnc2c(N)ncnc12", "2-(6-amino-9H-purin-9-yl)-5-(hydroxymethyl)oxolane-3,4-diol"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[r[0] for r in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


def _key(smiles: str) -> str:
    return inchi.MolToInchiKey(Chem.MolFromSmiles(smiles))


@needs_opsin
@pytest.mark.parametrize("label,smiles", [(r[0], r[1]) for r in ALL], ids=[r[0] for r in ALL])
def test_the_name_reads_back_to_the_same_molecule(label, smiles):
    from py2opsin import py2opsin

    name = name_smiles(smiles)
    back = py2opsin(name)
    assert back, name
    assert _key(back) == _key(smiles), (name, back)
