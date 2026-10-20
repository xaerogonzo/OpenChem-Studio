"""Naming round 65 (D-305): an amide anion whose acyl group carries a ring cation.

`O=C([N-]C)c1cc[nH+]cc1` was refused: the acyl group of an anionic nitrogen is named by cutting the nitrogen off, putting an -OH where it was and naming the ACID (`acetic acid` ->
`acetyl`), and the acid of a ring-cation acyl (`OC(=O)c1cc[nH+]cc1`) was named by the plan search as the NEUTRAL `pyridine-4-carboxylic acid`, so the acyl was
`pyridine-4-carbonyl` and the cation was gone (`methyl(pyridine-4-carbonyl)azanide`, which the guard refused). It was 52 of the betaine population's 56 refusals. The acid is named as a
CATION when it holds a ring cation (`4-carboxypyridin-1-ium`), and that name becomes the acyl: `methyl(pyridin-1-ium-4-carbonyl)azanide`, which OPSIN reads. An aminium is a suffix, not a
ring cation: `...thiophen-2-aminium-3-carbonyl` cannot be read, so that case keeps the `(azaniumyl...)(oxo)methyl` form it had.
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
    ("a pyridinium acyl on a methylazanide", "O=C([N-]C)c1cc[nH+]cc1", "methyl(pyridin-1-ium-4-carbonyl)azanide"),
    ("a bromopyridinium acyl on an anilide", "O=C([N-]c1ccccc1)c1c[nH+]cc(Br)c1", "(3-bromopyridin-1-ium-5-carbonyl)(phenyl)azanide"),
    ("a substituted pyridinium acyl", "CCOC(=O)Cc1[nH+]cccc1C(=O)[N-]c1ccc(OC(F)(F)F)cc1",
     "[[2-(2-ethoxy-2-oxoethyl)pyridin-1-ium-3-yl](oxo)methyl][4-(trifluoromethoxy)phenyl]azanide"),
    ("an ammonium acyl keeps its prefix form", "[NH3+]c1sc2c(c1C(=O)[N-]c1ccc(Cl)cc1)CCCC2",
     "[(2-azaniumyl-4,5,6,7-tetrahydro-1-benzothiophen-3-yl)(oxo)methyl](4-chlorophenyl)azanide"),
]

KEPT = [
    ("a neutral acyl on an amide anion", "O=C([N-]C)c1ccccc1", "benzoyl(methyl)azanide"),
    ("an amide anion beside a pyridinium on the N side", "CC(=O)[N-]c1cc[nH+]cc1", "acetyl(pyridinium-4-yl)azanide"),
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
