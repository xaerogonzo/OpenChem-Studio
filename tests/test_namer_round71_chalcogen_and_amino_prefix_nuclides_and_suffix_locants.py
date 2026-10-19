"""Naming round 71 (D-325 .. D-328): a sulfur, oxygen or nitrogen nuclide in a prefix OPSIN could not read, and an amide nitrogen on a ring that has a nitrogen of its own.

Round 70's population (one 15N or 18O per census molecule) was run again with 34S, 37Cl, 81Br and 18F. 37Cl, 81Br and 18F read back in every case (171 of 171); 34S did not:
seven of 138 were wrong under a reader and 27 were refused. The sulfur ones were the same defect:

* D-325 `[(34S)ethylsulfanyl]` is no name OPSIN can read. Alone it answers nothing; inside a longer name it DROPS the label and reads the unlabelled molecule (six of the seven),
  which is the worst case: a name that parses back to another compound. `sulfanyl` is not contracted with its alkyl as `oxy` is (`ethoxy`), so the label belongs before the
  `sulfanyl` it modifies: `ethyl(34S)sulfanyl`.
* D-326 the prefix of a thione, `sulfanylidene`, and the `oxo` / `thioxo` of a carbonyl cited as a prefix had no place for their atom's label (`2-sulfanylidene-1,3-thiazolidin-4-one`
  for the 34S compound), nor had the sulfur of `methylsulfonyl` (`methyl(34S)sulfonyl`, OPSIN reads that and not `(34S)methylsulfonyl`) or of `N,N-dimethylsulfamoyl`.
* D-327 the nitrogen of `methylamino`, `phenylamino` and the amino of a demoted amide (`3-(methylamino)-3-oxopropanoic acid`) was never cited: the commonest labelled secondary amine
  was refused. It sits before the `amino` it modifies, after the groups on it: `methyl(15N)amino`.
* D-328 a suffix atom whose element the retained RING also has (the nitrogen of `pyridine-2-carboxamide`) cannot be cited bare, because `(15N)pyridine-2-carboxamide` reads as the
  ring's. It is cited before its suffix word with the locant of the ring atom the group hangs on: `pyridine-2-(15N)carboxamide`, as a systematic parent's is. Not inside a bigger
  name, which is built from this one by rewriting its ending (`5-methylfuran-2-(18O)carboxamido`: OPSIN cannot read it).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from openchem.vendor.iupac_namer import name_smiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import naming_ion_populations as pop  # noqa: E402

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

NAMED = [
    ("a thioether in a prefix", "CC[34S]c1ccc(C#N)cc1", "4-[ethyl(34S)sulfanyl]benzonitrile"),
    ("a thioether with an aryl", "c1ccccc1[34S]c1ccc(C(N)=O)cc1", "4-[phenyl(34S)sulfanyl]benzamide"),
    ("a thioether of an acid", "C[34S]CC(=O)O", "[methyl(34S)sulfanyl]acetic acid"),
    ("the label dropped by a reader, inside a longer name", "CC[34S]c1c(C#N)c(NC(=O)/C=C/c2ccco2)nn1-c1ccccc1", "(2E)-N-{4-cyano-5-[ethyl(34S)sulfanyl]-1-phenyl-1H-pyrazol-3-yl}-3-(furan-2-yl)prop-2-enamide"),
    ("a thione beside a ketone suffix", "O=C1NC(=[34S])SC1", "2-(34S)sulfanylidene-1,3-thiazolidin-4-one"),
    ("the ring sulfur of the same compound", "S=C1NC(=O)C[34S]1", "2-sulfanylidene(1-34S)-1,3-thiazolidin-4-one"),
    ("a thioxo prefix", "[34S]=c1cccc[nH]1", "2-(34S)thioxo-1H-pyridine"),
    ("an oxo prefix beside an oxo", "O=C1CC[C@@H](C(=O)O)C(=[18O])N1", "(3R)-2-(18O)oxo-6-oxopiperidine-3-carboxylic acid"),
    ("a methylsulfonyl prefix, 34S", "C[34S](=O)(=O)c1ccc(C(N)=O)cc1", "4-[methyl(34S)sulfonyl]benzamide"),
    ("a methylsulfonyl prefix, 18O", "CS(=O)(=[18O])c1ccc(Cl)cc1", "1-chloro-4-[methyl(18O)sulfonyl]benzene"),
    ("a sulfinyl prefix", "O=C(O)c1ccc(cc1)[34S](=O)c1ccccc1", "4-[phenyl(34S)sulfinyl]benzoic acid"),
    ("a ring-N sulfonyl keeps the longhand spelling when labelled", "O=C(O)c1ccc(cc1)[34S](=O)(=O)N1CCCCC1", "4-[piperidin-1-yl(34S)sulfonyl]benzoic acid"),
    ("a compound sulfamoyl", "CN(C)[34S](=O)(=O)c1ccc(C(N)=O)cc1", "4-[N,N-dimethyl(34S)sulfamoyl]benzamide"),
    ("a compound sulfamoyl, 18O", "CN(C)S(=O)(=[18O])c1ccc(C(N)=O)cc1", "4-[N,N-dimethyl(18O)sulfamoyl]benzamide"),
    ("a secondary amine in a prefix", "OC(=O)CC[15NH]C", "3-[methyl(15N)amino]propanoic acid"),
    ("an aniline in a prefix", "OC(=O)CC[15NH]c1ccccc1", "3-[phenyl(15N)amino]propanoic acid"),
    ("an amine in a prefix beside another nitrogen elsewhere", "NC(=O)CC[15NH]C", "3-[methyl(15N)amino]propanamide"),
    ("a tertiary amine in a prefix", "O=C(O)CC[15N](C)C", "3-[dimethyl(15N)amino]propanoic acid"),
    ("the amide of a demoted group", "OC(=O)CC(=O)[15NH]C", "3-[methyl(15N)amino]-3-oxopropanoic acid"),
    ("the primary amide of a demoted group", "OC(=O)CC(=O)[15NH2]", "3-(15N)amino-3-oxopropanoic acid"),
    ("an anilide beside an ester", "Cc1ccc([15NH]C(=O)[C@H](C)OC(=O)c2ccc(C)cc2)cc1", "(2S)-1-[(4-methylphenyl)(15N)amino]-1-oxopropan-2-yl 4-methylbenzoate"),
    ("an amide nitrogen on a ring with a nitrogen", "O=C(c1ccccn1)[15NH]C", "N-methylpyridine-2-(15N)carboxamide"),
    ("...a primary one", "O=C(c1ccccn1)[15NH2]", "pyridine-2-(15N)carboxamide"),
    ("...on a fused ring", "O=C([15NH]c1ccccc1)c1ccnc2ccccc12", "N-phenylquinoline-4-(15N)carboxamide"),
    ("...with a substituent on the ring", "O=C(c1ccc(Cl)cn1)[15NH]CC", "5-chloro-N-ethylpyridine-2-(15N)carboxamide"),
    ("a sulfonamide nitrogen on a ring with a nitrogen", "Cc1ccc([15NH]S(=O)(=O)c2ccccn2)cc1", "N-(4-methylphenyl)pyridine-2-(15N)sulfonamide"),
    ("an oxygen alone of its element beside a ring nitrogen stays bare", "NC(=[18O])c1ccccn1", "(18O)pyridine-2-carboxamide"),
]

KEPT = [
    ("an unlabelled thioether", "CCSc1ccc(C#N)cc1", "4-(ethylsulfanyl)benzonitrile"),
    ("an unlabelled sulfonyl", "CS(=O)(=O)c1ccc(C(N)=O)cc1", "4-(methanesulfonyl)benzamide"),
    ("an unlabelled ring-N sulfonyl keeps its spelling", "O=C(O)c1ccc(cc1)S(=O)(=O)N1CCCCC1", "4-(piperidine-1-sulfonyl)benzoic acid"),
    ("an unlabelled secondary amine", "OC(=O)CCNC", "3-(methylamino)propanoic acid"),
    ("an unlabelled pyridine carboxamide", "O=C(c1ccccn1)NC", "N-methylpyridine-2-carboxamide"),
    ("a retained amide with no ring nitrogen is still bare", "O=C(c1ccccc1)[15NH]C", "N-methyl(15N)benzamide"),
]

REFUSED = [
    # a part of a bigger name is built from the suffix form by rewriting its ending, and OPSIN reads neither `-2-(18O)carboxamido` nor `-2-(18O)carbonyl`
    ("a labelled amide inside a bigger name stays refused", "COc1cc(-c2ccc(NC(=[18O])c3ccc(C)o3)c(OC)c2)ccc1NC(=O)c1ccc(C)o1"),
    ("a labelled acyl inside a bigger name stays refused", "COc1cccc2cc(C(=[18O])[C@H]3C(=O)C(=O)N(CCCN4CCOCC4)[C@@H]3c3ccc(F)cc3)oc12"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles", REFUSED, ids=[row[0] for row in REFUSED])
def test_a_name_that_would_be_unreadable_is_refused(label, smiles):
    with pytest.raises(ValueError, match="isotopic labelling"):
        name_smiles(smiles)


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name_reads_back_to_the_labelled_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert pop._inchikey(back) == pop._inchikey(smiles), (expected, back)
