"""Naming round 24: the morphinan family is named on the retained parent, not as a von Baeyer pentacycle.

Blue Book P-13.8.1.1 (BlueBookV2.pdf p. 66) prints morphine as
"4,5α-epoxy-17-methyl-7,8-didehydromorphinan-3,6α-diol". Before this round the retained-parent lookup
matched the saturated skeleton only, so every member with the 4,5-ether bridge or a ring double bond
fell to `...-oxa-azapentacyclo[...]octadeca-...` -- a valid name nobody writes, and one the app showed
without its stereodescriptors (see test_derived_name_reaches_opsin.py).

Each expected name was read back through OPSIN to the input structure, stereo included.
"""
import pytest
from rdkit import Chem

from openchem.chem.naming_providers import derived_name_for_structure, opsin_available

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")

FAMILY = [
    ("morphine", "CN1CC[C@]23[C@@H]4[C@H]1CC5=C2C(=C(C=C5)O)O[C@H]3[C@H](C=C4)O",
     "(5R,6S,9R,13S,14R)-4,5-epoxy-17-methyl-7,8-didehydromorphinan-3,6-diol"),
    ("codeine", "COc1ccc2C[C@H]3N(C)CC[C@@]45[C@@H](Oc1c24)[C@@H](O)C=C[C@@H]35",
     "(5R,6S,9R,13S,14R)-4,5-epoxy-3-methoxy-17-methyl-7,8-didehydromorphinan-6-ol"),
    ("heroin", "CC(=O)O[C@H]1C=C[C@H]2[C@H]3Cc4ccc(OC(C)=O)c5O[C@@H]1[C@]2(CCN3C)c45",
     "(5R,6S,9R,13S,14R)-3-(acetyloxy)-4,5-epoxy-17-methyl-7,8-didehydromorphinan-6-yl acetate"),
    ("hydromorphone", "CN1CC[C@]23[C@@H]4C(=O)CC[C@]2([C@H]1CC5=C3C(=C(C=C5)O)O4)O",
     "(5R,9R,13S,14S)-4,5-epoxy-3,14-dihydroxy-17-methylmorphinan-6-one"),
    ("oxycodone", "COc1ccc2C[C@H]3N(C)CC[C@@]45[C@@H](Oc1c24)C(=O)CC[C@@]35O",
     "(5R,9R,13S,14S)-4,5-epoxy-14-hydroxy-3-methoxy-17-methylmorphinan-6-one"),
    ("naloxone", "C=CCN1CC[C@]23[C@@H]4C(=O)CC[C@]2([C@H]1Cc1ccc(O)c(O4)c13)O",
     "(5R,9R,13S,14S)-4,5-epoxy-3,14-dihydroxy-17-(prop-2-en-1-yl)morphinan-6-one"),
    ("thebaine", "COC1=CC=C2[C@H]3Cc4ccc(OC)c5O[C@@H]1[C@]2(CCN3C)c45",
     "(5R,9R,13S)-4,5-epoxy-3,6-dimethoxy-17-methyl-6,7,8,14-tetradehydromorphinan"),
    # the molecule that started the round (a diacetoxy-oxo morphinan, drawn in the app)
    ("3,14-diacetoxy-6-oxo", "CC(=O)Oc1ccc2c3c1O[C@H]1C(=O)CC[C@@]4(OC(C)=O)[C@@H](C2)N(C)CC[C@]314",
     "(5R,9R,13S,14S)-3-(acetyloxy)-4,5-epoxy-17-methyl-6-oxomorphinan-14-yl acetate"),
]


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", FAMILY, ids=[f[0] for f in FAMILY])
def test_morphinan_family_name(label, smiles, expected):
    result = derived_name_for_structure(Chem.MolFromSmiles(smiles))
    assert result.name == expected
    assert not result.note  # reads back to the structure, stereo included


def test_the_retained_lookup_still_names_the_plain_skeleton():
    # a saturated morphinan with no bridge is the plain retained path, untouched by the new strategy
    from openchem.vendor.iupac_namer import name_smiles

    assert name_smiles("CN1CCC23CCCCC2C1Cc1ccc(O)cc13").endswith("17-methylmorphinan-3-ol")
