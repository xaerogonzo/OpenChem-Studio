"""Naming round 83 (D-375): the one defect round 81 left open as a known limit.

A hypoxanthine drawn with NO ring N-H (`O=C1N=CN=C2N=C(R)N=C12`, a quinoid 6H-purin-6-one) was named as a ring parent with the curated `9H-` indicated hydrogen:
`methyl 6-oxo-9H-purine-8-carboxylate`, `6-oxo-9H-purin-8-yl` as a substituent. That puts a hydrogen on N9 the drawing does not have, and OPSIN reads another tautomer (or, beside
the ring in an ester, nothing). The indicated hydrogen of a ring with no N-H is the oxo carbon's: `6-oxo-6H-purine-8-carboxylate`, `6-oxo-6H-purin-8-yl`, which OPSIN reads.

Four populations of 1,700 to 6,000 molecules each (two curated rings joined by a 12-link set of functional linkers, 1-2 richer substituents on every curated ring, charged rings,
and 1,500 pairs joined by a bond / CH2 / O / NH on a new seed) were otherwise clean apart from OPSIN's stereo defaults for a cephem, penam, cepham, carbapenem and morphinan.
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
    ("an ester of a ring with no N-H", "O=C1N=CN=C2N=C(C(=O)OC)N=C12", "methyl 6-oxo-6H-purine-8-carboxylate"),
    ("...with the group at C2", "O=C1N=C(C(=O)OC)N=C2N=CN=C12", "methyl 6-oxo-6H-purine-2-carboxylate"),
    ("...as an aromatic spelling", "O=C(OC)c1nc2ncnc(=O)c2n1", "methyl 6-oxo-6H-purine-8-carboxylate"),
    ("a thione, which is the same shape", "S=C1N=CN=C2N=C(C(=O)OC)N=C12", "methyl 6-thioxo-6H-purine-8-carboxylate"),
    ("an amide on the ring", "O=C1N=CN=C2N=C(NC(=O)C)N=C12", "N-(6-oxo-6H-purin-8-yl)acetamide"),
    ("the ring as the alcohol part of an ester", "O=C1N=CN=C2N=C(OC(=O)C3C=CC=CO3)N=C12", "6-oxo-6H-purin-8-yl 2H-pyran-2-carboxylate"),
]

KEPT = [
    ("the ketone, which names the oxo as a suffix", "O=C1N=C(C)N=C2N=CN=C12", "2-methyl-6H-purin-6-one"),
    ("the lactam with its ring N-H", "O=c1[nH]cnc2nc(C(=O)OC)[nH]c12", "methyl 6-oxo-1H,7H-purine-8-carboxylate"),
    ("a purine with no oxo", "COC(=O)c1nc2ncncc2[nH]1", None),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", NAMED + KEPT[:2], ids=[r[0] for r in NAMED + KEPT[:2]])
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
