"""Naming round 70 (D-322 .. D-324): a nitrogen or oxygen nuclide in a group, an acylamino prefix and an amine.

Round 69's population (one 13C or 2H per molecule) was run again with one 15N and one 18O: 86 of 356 labelled nitrogens and 75 of 366 labelled oxygens were refused (the labelled atom had no
place in the name; none was a wrong molecule). Three causes were common:

* D-322 the two oxygens of a nitro group, of a sulfonyl and of a carboxylate are ONE position to a reader (terminal atoms of one element on one neighbour with the same hydrogens: the nitro's
  `=O` and `O-` are one resonance form), but the labelled-atom rules counted two and refused `(18O)nitro`, `4-methyl(18O)benzene-1-sulfonamide`. They count once now; both labelled is `(18O2)nitro`.
* D-323 an acylamino PREFIX had no place for its nitrogen's nuclide: `methyl 4-acetamidobenzoate` for the 15N compound. A simple acyl is `(15N)acetamido` (OPSIN reads it); a compound acyl is
  `[3-(furan-2-yl)prop-2-enoyl(15N)amino]` (it reads neither `(15N)3-(furan-2-yl)prop-2-enamido` nor `...-(15N)carboxamido`). The acid the prefix is built from is the amide with its
  nitrogen turned into the hydroxyl oxygen, and that oxygen kept the 15N (`4-[(O-15O,15N)acetamido]...`): the isotope is cleared.
* D-324 the nitrogen of an `-amine` suffix is the group's own anchor, so it mapped to no locant and a labelled amine was refused (`[15NH2]CC`, the commonest labelled compound there is):
  `(15N)ethanamine`, `2-phenylethan-1-(15N)amine`, `N-ethyl(15N)ethanamine`.
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
    ("an oxygen of a nitro group", "Clc1ccc(cc1)[N+](=[18O])[O-]", "1-chloro-4-(18O)nitrobenzene"),
    ("both oxygens of a nitro group", "Clc1ccc(cc1)[N+](=[18O])[18O-]", "1-chloro-4-[(18O2)nitro]benzene"),
    ("an oxygen of a sulfonamide", "Cc1ccc(S(=O)(=[18O])N)cc1", "4-methyl(18O)benzene-1-sulfonamide"),
    ("an oxygen of an N-aryl sulfonamide", "c1ccccc1S(=O)(=[18O])Nc1ccccc1", "N-phenyl(18O)benzenesulfonamide"),
    ("an oxygen of a sulfonamide on a retained ring parent", "c1ccc2ccccc2c1S(=O)(=[18O])N", "(18O)naphthalene-1-sulfonamide"),
    ("an oxygen of a sulfonamide on a chain: the sulfur is outside the numbering, the chain carbon is cited", "CCCS(=O)(=[18O])N", "propane-1-(18O)sulfonamide"),
    ("...with an N-substituent", "CCCS(=O)(=[18O])Nc1ccccc1", "N-phenylpropane-1-(18O)sulfonamide"),
    ("...on methane", "CS(=O)(=[18O])N", "(18O)methanesulfonamide"),
    ("the nitrogen of a simple acylamino prefix", "COC(=O)c1ccc([15NH]C(C)=O)cc1", "methyl 4-(15N)acetamidobenzoate"),
    ("the carbonyl oxygen of the same prefix", "COC(=O)c1ccc(NC(C)=[18O])cc1", "methyl 4-(18O)acetamidobenzoate"),
    ("the nitrogen of a compound acylamino prefix", "O=C(O)C[15NH]C(=O)C=Cc1ccco1", "[3-(furan-2-yl)prop-2-enoyl(15N)amino]acetic acid"),
    ("a benzamido prefix", "c1ccccc1C(=O)[15NH]c1ccc(C(=O)OC)cc1", "methyl 4-(15N)benzamidobenzoate"),
    ("a substituted benzoyl", "Clc1ccc(cc1)C(=O)[15NH]c1ccc(C(=O)OC)cc1", "methyl 4-[4-chlorobenzoyl(15N)amino]benzoate"),
    ("an N-methylated acylamino prefix", "COC(=O)c1ccc([15N](C)C(C)=O)cc1", "methyl 4-[acetyl(methyl)(15N)amino]benzoate"),
    ("ethylamine", "[15NH2]CC", "(15N)ethanamine"),
    ("a primary amine on a chain", "[15NH2]CCc1ccccc1", "2-phenylethan-1-(15N)amine"),
    ("a secondary amine", "CC[15NH]CC", "N-ethyl(15N)ethanamine"),
    ("benzylamine", "[15NH2]Cc1ccccc1", "phenyl(15N)methanamine"),
    ("a tertiary amine", "C[15N](C)C", "N,N-dimethyl(15N)methanamine"),
    ("an amine on a ring", "[15NH2]C1CCCCC1", "(15N)cyclohexanamine"),
    ("an amine whose neighbour is quaternary", "[15NH2]CC(C)(C)C", "2,2-dimethylpropan-1-(15N)amine"),
]

KEPT = [
    ("an amine that is a prefix keeps its bracket", "[15NH2]CCO", "2-(15N)aminoethan-1-ol"),
    ("an unlabelled nitro group", "Clc1ccc(cc1)[N+](=O)[O-]", "1-chloro-4-nitrobenzene"),
    ("an unlabelled acylamino prefix", "COC(=O)c1ccc(NC(C)=O)cc1", "methyl 4-acetamidobenzoate"),
]

REFUSED = [
    ("a sulfonic acid's oxygens are not alone (=O, =O, OH): the name `(1-18O)propane-1-sulfonic acid` is unreadable", "CCCS(=O)(=[18O])O"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles", REFUSED, ids=[row[0] for row in REFUSED])
def test_a_name_that_would_lose_a_nuclide_is_refused(label, smiles):
    with pytest.raises(ValueError, match="isotopic labelling"):
        name_smiles(smiles)


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_labelled_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert pop._inchikey(back) == pop._inchikey(smiles), (expected, back)
