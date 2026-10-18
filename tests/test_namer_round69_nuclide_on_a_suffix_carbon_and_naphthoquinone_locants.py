"""Naming round 69 (D-317 .. D-319): a nuclide on the carbon of a suffix group, on a urea core, and a mirrored benzo ring.

A new population (a 13C or 2H on one atom of every census molecule and of ions) found three things, the last one with no isotope in it:

* D-317 a nuclide on the CARBON of a carbon-supplying suffix (`-carboxamide`, `-carboxylic acid`, `-carbaldehyde`, a retained `benzamide`) or on the core of a urea, thiourea or guanidine had no
  place in the name; it was dropped, and the nuclide guard refused the name (a labelled urea had no plan at all and was a `NAMING ERROR`). It is cited with no locant before the suffix word,
  `pyridine-4-(13C)carboxamide`, `benzene-1-(13C)carboxamide` (the retained `(13C)benzamide` names seven carbons: OPSIN calls it ambiguous), `N,N'-diethyl(13C)urea`, and a single nitrogen of a core by its own locant, `N-methyl(N'-15N)urea`. OPSIN reads all of them.
* D-318 the carbon an amide's nitrogen hangs on was listed with the suffix group, so a nuclide on the N-substituent was cited a second time on the parent: `CC(=O)N[13c]1ccccc1` was
  `N-[(1-13C)phenyl](1-13C)acetamide`, a name for two labels where the molecule has one.
* D-320 two alkyls that differ only by a nuclide (`ethyl` and `(2-2H)ethyl`) sort as a tie, so a diester of an unsymmetrical diacid was named without locants and its order said nothing:
  `(2-2H)ethyl ethyl 2-chlorobutanedioate` was read as the deuterium on C1.
* D-321 the hydro-prefix pattern that places a nuclide after the prefixes (OPSIN reads `decahydro(1-2H)naphthalene` and not `(1-2H)decahydronaphthalene`) stopped at `deca`: a steroid is
  `hexadecahydro`, and its name put the bracket in front, which OPSIN cannot read.
* D-319 the curated `1,4-dihydronaphthalene` numbered its benzo ring in the wrong direction (5 bonded to 8a). The parent alone is symmetric, so nothing showed it; with a substituent on the
  2/3 side it named a DIFFERENT MOLECULE: plumbagin `CC1=CC(=O)c2c(O)cccc2C1=O` was `8-hydroxy-2-methylnaphthalene-1,4-dione`.
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
    ("a benzamide carbonyl", "O=[13C](N)c1ccccc1", "benzene-1-(13C)carboxamide"),
    ("a benzoic acid carbon", "O=[13C](O)c1ccccc1", "benzene-1-(13C)carboxylic acid"),
    ("an N-aryl benzamide carbonyl", "O=[13C](Nc1ccccc1)c1ccccc1", "N-phenylbenzene-1-(13C)carboxamide"),
    ("a pyridine carboxamide carbon", "O=[13C](N)c1ccncc1", "pyridine-4-(13C)carboxamide"),
    ("a cyclohexane carboxamide carbon", "O=[13C](N)C1CCCCC1", "cyclohexane-1-(13C)carboxamide"),
    ("a substituted benzoic acid", "O=[13C](O)c1ccc(Cl)cc1", "4-chlorobenzene-1-(13C)carboxylic acid"),
    ("a substituted benzaldehyde", "O=[13CH]c1ccc(Cl)cc1", "4-chlorobenzene-1-(13C)carbaldehyde"),
    ("urea", "N[13C](N)=O", "(13C)urea"),
    ("urea oxygen", "NC(N)=[18O]", "(18O)urea"),
    ("both urea nitrogens", "[15NH2]C(=O)[15NH2]", "(15N2)urea"),
    ("one urea nitrogen", "[15NH2]C(N)=O", "(N-15N)urea"),
    ("the second nitrogen of a substituted urea", "CNC(=O)[15NH2]", "N-methyl(N'-15N)urea"),
    ("a disubstituted urea carbon", "CCN[13C](=O)NCC", "N,N'-diethyl(13C)urea"),
    ("thiourea", "N[13C](N)=S", "(13C)thiourea"),
    ("guanidine", "N[13C](N)=N", "(13C)guanidine"),
    ("a substituted guanidine", "CN=[13C](N)N", "N''-methyl(13C)guanidine"),
    ("the imino nitrogen of guanidine", "N[C](N)=[15NH]", "(N''-15N)guanidine"),
    ("a ring label on an N-aryl acetamide is not cited twice", "CC(=O)N[13c]1ccccc1", "N-[(1-13C)phenyl]acetamide"),
    ("an N-alkyl label is not cited twice", "C[13CH2]NC(C)=O", "N-[(1-13C)ethyl]acetamide"),
    ("the acetamide's own label stays", "C[13C](=O)Nc1ccccc1", "N-phenyl(1-13C)acetamide"),
    ("plumbagin", "CC1=CC(=O)c2c(O)cccc2C1=O", "5-hydroxy-2-methylnaphthalene-1,4-dione"),
    ("its isomer", "CC1=CC(=O)c2cccc(O)c2C1=O", "8-hydroxy-2-methylnaphthalene-1,4-dione"),
    ("a label on the 8 side", "COC1=CC(=O)c2c(Cl)cc[13c](Cl)c2C1=O", "5,8-dichloro-2-methoxy(8-13C)naphthalene-1,4-dione"),
    ("a label on the 5 side", "COC1=CC(=O)c2[13c](Cl)ccc(Cl)c2C1=O", "5,8-dichloro-2-methoxy(5-13C)naphthalene-1,4-dione"),
    ("the parent hydride keeps its locants", "C1=CCc2cccc(Cl)c2C1", "5-chloro-1,4-dihydronaphthalene"),
    ("two alkyls that differ only by a nuclide are told apart by locants", "CCOC(=O)C(Cl)CC(=O)OCC[2H]", "1-ethyl 4-(2-2H)ethyl 2-chlorobutanedioate"),
    ("and the other way round", "[2H]CCOC(=O)C(Cl)CC(=O)OCC", "1-(2-2H)ethyl 4-ethyl 2-chlorobutanedioate"),
    ("a nuclide after a decahydro prefix", "[2H]C1CCCC2CCCCC12", "decahydro(8-2H)naphthalene"),
    ("a nuclide after a hexadecahydro prefix", "[2H]C1CC2CCC3C(CCC4CCCCC43)C2C1", "hexadecahydro(16-2H)-1H-cyclopenta[a]phenanthrene"),
]

KEPT = [
    ("an unlabelled urea", "NC(N)=O", "urea"),
    ("a nitrile carbon stays refused-or-unchanged: the unlabelled name", "N#Cc1ccccc1", "benzonitrile"),
]

REFUSED = [
    ("a bare (13C) would not say which of benzonitrile's carbons", "N#[13C]c1ccccc1"),
    ("two carboxamides would not say which", "O=[13C](N)c1ccc(C(N)=O)cc1"),
    # a labelled amide inside a bigger name is built from this one by rewriting its ending (`-1-(13C)carboxamido`), which OPSIN cannot read: refused, not mis-spelled
    ("a labelled acylamino prefix", "CCOC(=O)CSc1nnc(CN[13C](=O)c2ccc(F)cc2)n1-c1ccccc1"),
    ("a labelled amide whose name is an ester's alcohol part", "CC(=O)OCCN[13C](=O)C1CCCCC1"),
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
