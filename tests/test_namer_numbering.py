"""Naming round 5 (N7): a numbering choice must not depend on how the
structure was written.

The hydro-orientation defect (D-092) was a TIE broken by enumeration order,
which is exactly the kind of choice that moves when the input's atom order
does. Each N7 case is named from shuffled atom orders, a Kekule SMILES and
randomly rooted SMILES, and must come out identical every time.
"""
from __future__ import annotations

import random

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

CASES = [
    ("OC(=O)C1=CCNCC1", "1,2,3,6-tetrahydropyridine-4-carboxylic acid"),
    ("CN1CCC(=CC1)c1ccccc1", "1-methyl-4-phenyl-1,2,3,6-tetrahydropyridine"),
    ("OC(=O)CN1CC=CC=C1", "(pyridin-1(2H)-yl)acetic acid"),
    ("OC(=O)CN1CC=CC(Cl)=C1", "(5-chloropyridin-1(2H)-yl)acetic acid"),
    ("OC1=CCCNC1", "1,2,5,6-tetrahydropyridin-3-ol"),
]


def _spellings(smiles: str) -> list[str]:
    mol = Chem.MolFromSmiles(smiles)
    rng = random.Random(20260919)
    out = []
    for _ in range(4):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        out.append(Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False))
    kek = Chem.Mol(mol)
    Chem.Kekulize(kek, clearAromaticFlags=True)
    out.append(Chem.MolToSmiles(kek, kekuleSmiles=True))
    out.append(Chem.MolToSmiles(mol))
    for seed in (1, 2, 3):
        Chem.rdBase.SeedRandomNumberGenerator(seed)
        out.append(Chem.MolToSmiles(mol, doRandom=True, canonical=False))
    return out


@pytest.mark.parametrize("smiles,expected", CASES, ids=[c[1] for c in CASES])
def test_the_numbering_does_not_depend_on_how_it_was_written(smiles, expected):
    assert name_smiles(smiles) == expected
    for spelling in _spellings(smiles):
        assert name_smiles(spelling) == expected, spelling
