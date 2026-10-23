"""Naming round 80 (D-364 .. D-366): the defects a SCAN OF EVERY CURATED RING AS A SUBSTITUENT finds.

The population is new. Every substitutable ring atom of every curated ring is attached to a more senior parent (acetic acid, acetamide, acetate, thioacetate, a methyl ketone, a secondary
alcohol, acetonitrile: 7 x 1,952 molecules), so that the ring is named as a `-yl` prefix, each named and read back through OPSIN on the standard InChIKey. Clean apart from the stereo OPSIN
gives a cephem, a penam, a carbapenem or a morphinan, and the drawings the generator makes of arsenic and a protonated-free pyridinium; the finds:

* D-364 a ring ketone cited as a substituent put the ring's indicated hydrogen BEFORE the oxo prefixes: `(2H-2,4-dioxo-1H-3,1-benzoxazin-6-yl)acetic acid`, which OPSIN cannot read. The oxo
  prefixes come first and the ring's own hydrogens follow: `(2,4-dioxo-1,4-dihydro-2H-3,1-benzoxazin-6-yl)`.
* D-365 an ESTER of a chalcogen ring cation (chromenylium and its S, Se, Te and iso forms, 61 molecules) was the neutral ring's `chromen-2-yl acetate`, refused by the charge guard. A cation
  outranks an ester (P-73 over P-66), as the ring N+ case already did: `2-(acetyloxy)chromenylium`.
* D-366 the curated octahydro-1H-pyrrolo[3,4-b]pyridine labelled its fusion carbon 3a; it is 4a (OPSIN reads `4a-yl` and not `3a-yl`).
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
    ("a benzoxazinedione as a substituent", "O=C(O)Cc1ccc2[nH]c(=O)oc(=O)c2c1", "(2,4-dioxo-1,4-dihydro-2H-3,1-benzoxazin-6-yl)acetic acid"),
    ("...on another position", "O=C(O)Cc1cccc2c1c(=O)oc(=O)[nH]2", "(2,4-dioxo-1,4-dihydro-2H-3,1-benzoxazin-5-yl)acetic acid"),
    ("a pyranoquinolinedione as a substituent", "O=C(O)Cc1cc(=O)c2cc3c(=O)cc[nH]c3cc2o1", "(4,6-dioxo-4,6-dihydro-9H-pyrano[3,2-g]quinolin-2-yl)acetic acid"),
    ("a chromenylium acetate", "CC(=O)Oc1ccc2ccccc2[o+]1", "2-(acetyloxy)chromenylium"),
    ("a pyrylium acetate", "CC(=O)Oc1cc[o+]cc1", "4-(acetyloxy)pyrylium"),
    ("a thiochromenylium acetate", "CC(=O)Oc1ccc2ccccc2[s+]1", "2-(acetyloxy)thiochromenylium"),
    ("a selenochromenylium acetate", "CC(=O)Oc1ccc2ccccc2[se+]1", "2-(acetyloxy)selenochromenylium"),
    ("a tellurochromenylium acetate", "CC(=O)Oc1ccc2ccccc2[te+]1", "2-(acetyloxy)tellurochromenylium"),
    ("an isochromenylium acetate", "CC(=O)Oc1c[o+]cc2ccccc12", "4-(acetyloxy)isochromenylium"),
    ("a chromenylium mesylate", "CS(=O)(=O)Oc1ccc2ccccc2[o+]1", "2-(methylsulfonyloxy)chromenylium"),
    ("the pyrrolopyridine fusion carbon", "O=C(O)CC12CCCNC1CNC2", "(octahydro-1H-pyrrolo[3,4-b]pyridin-4a-yl)acetic acid"),
]

KEPT = [
    ("a ring ketone with a methyl keeps its suffix form", "Cc1ccc2[nH]c(=O)oc(=O)c2c1", "6-methyl-2H-3,1-benzoxazine-2,4(1H)-dione"),
    ("a quinazolinedione substituent", "O=C(O)Cc1ccc2[nH]c(=O)[nH]c(=O)c2c1", "(2,4-dioxo-1H,3H-quinazolin-6-yl)acetic acid"),
    ("a pyridinium acetate stays a pyridinium", "CC(=O)Oc1cc[n+](C)cc1", "4-(acetyloxy)-1-methylpyridin-1-ium"),
    ("a neutral ring ester stays an ester", "CC(=O)OC1CCOCC1", "oxan-4-yl acetate"),
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
