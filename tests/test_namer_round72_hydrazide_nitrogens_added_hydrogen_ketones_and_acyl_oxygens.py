"""Naming round 72 (D-329 .. D-331): a hydrazide's nitrogens, a ketone with added hydrogen, and the oxygen of an acylamino prefix.

Round 71's population was run again with TWO labels of different elements per census molecule (13C with 15N, 13C with 18O, 18O with 34S, 2H with 13C; 300 each), then the
single-label ones once more. Three defects were cheap and each was a visible one:

* D-329 a ring ketone written with its added hydrogen, `pyrrolo[1,2-c]pyrimidin-1(2H)-one`, cited its oxygen in front of the whole name with the carbon's locant,
  `(1-18O)pyrrolo[1,2-c]pyrimidin-1(2H)-one`, which OPSIN cannot read: the suffix match for "a locant, then the word" did not allow the parenthesised hydrogen. The label goes
  before the word, as for every other suffix: `pyrrolo[1,2-c]pyrimidin-1(2H)-(18O)one`.
* D-330 the two nitrogens of a hydrazide were both `(1-15N)acetohydrazide`: one name for two molecules (the amide nitrogen labelled, and the terminal one), and unreadable. The book
  tells them apart as it tells its N-substituents apart, `(N-15N)acetohydrazide` and `(N'-15N)acetohydrazide`; OPSIN reads both.
* D-331 the oxygen of an acyl group in an acylamino prefix, `4-[hexadecan-1-(18O)amido]naphthalene-1-sulfonic acid`, was cited with a locant OPSIN cannot read in an amido. It reads
  `(18O)hexadecanamido`, and means the one oxygen there is. With a second oxygen in the prefix (`furan-2-carboxamido`) OPSIN takes the wrong one, the ring's, so that stays refused.
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
    ("a fused ring ketone with added hydrogen", "Cc1cc2cc(-c3cccs3)cn2c(=[18O])[nH]1", "3-methyl-6-(thien-2-yl)pyrrolo[1,2-c]pyrimidin-1(2H)-(18O)one"),
    ("the amide nitrogen of a hydrazide", "CC(=O)[15NH]N", "(N-15N)acetohydrazide"),
    ("the terminal nitrogen of a hydrazide", "CC(=O)N[15NH2]", "(N'-15N)acetohydrazide"),
    ("both nitrogens", "CC(=O)[15NH][15NH2]", "(N-15N,N'-15N)acetohydrazide"),
    ("a hydrazone's amide nitrogen", "C=N[15NH]C(C)=O", "N'-methylidene(N-15N)acetohydrazide"),
    ("a hydrazone's imine nitrogen", "C=[15N]NC(C)=O", "N'-methylidene(N'-15N)acetohydrazide"),
    ("the oxygen of a long acyl in an acylamino prefix", "CCCCCCCCCCCCCCCC(=[18O])Nc1ccc(S(=O)(=O)O)c2ccccc12", "4-(18O)hexadecanamidonaphthalene-1-sulfonic acid"),
    ("...a short one", "CCC(=[18O])Nc1ccc(C(=O)O)cc1", "4-(18O)propanamidobenzoic acid"),
    ("the nitrogen of an amide anion", "CC(=O)[15N-]c1ccccc1", "acetyl(phenyl)(15N)azanide"),
    ("...beside a ring nitrogen", "CC(=O)[15N-]c1ccncc1", "acetyl(pyridin-4-yl)(15N)azanide"),
    ("...a diacylazanide", "CC(=O)[15N-]C(=O)C", "diacetyl(15N)azanide"),
    ("...as a prefix on another anion", "O=C([15N-]c1ccccc1)[O-]", "[phenyl(15N)azanidyl]methanoate"),
    ("the oxygen of an acyl on an amide anion", "CC[N-]C(=[18O])C", "ethyl[(18O)acetyl]azanide"),
    ("...with a substituent on the acyl", "CC[N-]C(=[18O])CCCl", "[3-chloro(18O)propanoyl](ethyl)azanide"),
    ("...with an oxygen of its own in a substituent", "CC[N-]C(=[18O])CCOC", "ethyl[3-methoxy(18O)propanoyl]azanide"),
    ("...and two of them", "CC[N-]C(=[18O])CC(SC)SC", "[3,3-bis(methylsulfanyl)(18O)propanoyl](ethyl)azanide"),
]

KEPT = [
    ("a ring ketone whose name numbers nothing there keeps the bare label", "[18O]=c1cccc[nH]1", "(18O)pyridin-2(1H)-one"),
    ("an unlabelled hydrazide", "CC(=O)NN", "acetohydrazide"),
    ("an unlabelled acylamino prefix", "CCC(=O)Nc1ccc(C(=O)O)cc1", "4-propanamidobenzoic acid"),
    ("a ketone suffix keeps its place", "CCC(=[18O])C", "butan-2-(18O)one"),
]

REFUSED = [
    # OPSIN reads `(18O)furan-2-carboxamido` as the RING oxygen: a wrong molecule, so the name is not written
    ("a second oxygen in the prefix", "[18O]=C(Nc1ccc(C(=O)O)cc1)c1ccco1"),
]

ALL = NAMED + KEPT


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize("label,smiles", REFUSED, ids=[row[0] for row in REFUSED])
def test_a_name_a_reader_would_get_wrong_is_refused(label, smiles):
    with pytest.raises(ValueError, match="isotopic labelling"):
        name_smiles(smiles)


def test_the_two_nitrogens_of_a_hydrazide_have_two_names():
    assert name_smiles("CC(=O)[15NH]N") != name_smiles("CC(=O)N[15NH2]")


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", NAMED, ids=[row[0] for row in NAMED])
def test_the_name_reads_back_to_the_labelled_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert pop._inchikey(back) == pop._inchikey(smiles), (expected, back)
