"""Naming round 43 (D-226, D-227): an amidinium beside another carbonyl is named, a N-substituted pyrrolinium keeps its retained spelling, and an alkoxide or thiolate beside a
senior group keeps its charge.

D-226: an amidinium with a carboxylate (the zwitterion `NC(=[NH2+])CC(=O)[O-]`), a carboxyl on its own carbon (`NC(=[NH2+])C(=O)O`, whose surrogate acid is OXALIC acid) or a second acid was
refused. The amidinium is the parent (a cation outranks an acid and an anion, P-41 / P-73), the other group a prefix: `carboxylatoacetamidinium`, `carboxyformamidinium`.

D-227: `N#Cc1ccc([O-])cc1` was `4-hydroxybenzene-1-carbonitrile`, the NEUTRAL compound: a nitrile outranks the thiol or alcohol the renderer re-protonates the site to, so the site became a
`hydroxy` / `sulfanyl` prefix and the charge was in no word of the name. Eight of the census's thiolate and phenolate rows had it; the molecule is `4-oxidobenzene-1-carbonitrile` (the anion
cited as the prefix the book uses when it is not the principal group). A name that cannot say where the charge is (a real OH beside the phenolate) is refused.

N-substituted 1-pyrrolinium / 2-imidazolinium (round 41's open item): `C[N+]1=CCCC1` was `1-methyl-3,4-dihydro-2H-azol-1-ium`, the Hantzsch-Widman spelling beside the retained name the neutral ring has;
the carved ring kept its charge on the way to the lookup, so it never matched.

D-228 (the sweep of the curated rings, the one item round 41 left from it): the four helicenes had no atom-locant table, so any substituent landed on the wrong atom
(`N-(hexahelicen-1-yl)acetamide` named four different molecules by their position); 224 of the 260 sweep cases were wrong, now 0. The table is OPSIN's numbering.

Every name pinned here is read back through OPSIN to its input on canonical SMILES and InChIKey.
"""
from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
AMIDINIUM = [
    ('carboxyl on the amidinium carbon', 'NC(=[NH2+])C(=O)O', 'carboxyformamidinium'),
    ('carboxylate on the amidinium carbon', 'NC(=[NH2+])C(=O)[O-]', 'carboxylatoformamidinium'),
    ('zwitterion, one carbon between', 'NC(=[NH2+])CC(=O)[O-]', 'carboxylatoacetamidinium'),
    ('zwitterion, two carbons between', 'NC(=[NH2+])CCC(=O)[O-]', '3-carboxylatopropanamidinium'),
    ('zwitterion on a benzene ring', 'NC(=[NH2+])c1ccc(cc1)C(=O)[O-]', '4-carboxylatobenzamidinium'),
    ('zwitterion on a ring, one carbon between', 'NC(=[NH2+])c1cccc(c1)CC(=O)[O-]', '3-(carboxylatomethyl)benzamidinium'),
    ('zwitterion on a cyclohexane', 'NC(=[NH2+])C1CCC(CC1)C(=O)[O-]', '4-carboxylatocyclohexan-1-amidinium'),
    ('branched zwitterion', 'CC(C)(C(=O)[O-])CC(N)=[NH2+]', '3-carboxylato-3-methylbutanamidinium'),
    ('amidinium beside a carboxylic acid', 'NC(=[NH2+])CC(=O)O', 'carboxyacetamidinium'),
    ('amidinium beside an ester', 'NC(=[NH2+])C(=O)OC', 'methoxy(oxo)acetamidinium'),
    ('amidinium beside an amide', 'NC(=[NH2+])C(=O)N', 'amino(oxo)acetamidinium'),
]

PYRROLINIUM = [
    ('N-methyl 1-pyrrolinium', 'C[N+]1=CCCC1', '1-methyl-3,4-dihydro-2H-pyrrol-1-ium'),
    ('N-ethyl 1-pyrrolinium', 'CC[N+]1=CCCC1', '1-ethyl-3,4-dihydro-2H-pyrrol-1-ium'),
    ('2-methyl N-methyl 1-pyrrolinium', 'CC1=[N+](C)CCC1', '1,5-dimethyl-3,4-dihydro-2H-pyrrol-1-ium'),
    ('N-methyl 2-methylimidazolinium', 'CC1=[N+](C)CCN1', '2,3-dimethyl-4,5-dihydro-1H-imidazol-3-ium'),
    ('1,2,3-trimethylimidazolinium', 'C[N+]1=C(C)N(C)CC1', '1,2,3-trimethyl-4,5-dihydro-1H-imidazol-3-ium'),
    ('1,3-dimethylimidazolinium', 'C[N+]1=CN(C)CC1', '1,3-dimethyl-4,5-dihydro-1H-imidazol-3-ium'),
]

ANION_PREFIX = [
    ('thiolate beside a nitrile', 'N#Cc1ccc([S-])cc1', '4-sulfidobenzene-1-carbonitrile'),
    ('the sodium salt of a thiolate beside a nitrile', 'N#Cc1ccc([S-])cc1.[Na+]', 'sodium 4-sulfidobenzene-1-carbonitrile'),
    ('phenolate beside a nitrile', 'N#Cc1ccc([O-])cc1', '4-oxidobenzene-1-carbonitrile'),
    ('thiolate on a purine with a nitrile chain', 'N#CCCn1cnc2c([S-])ncnc21', '3-(6-sulfido-9H-purin-9-yl)propanenitrile'),
    ('thiolate beside an aldehyde', 'O=Cc1ccc([S-])cc1', '4-sulfidobenzene-1-carbaldehyde'),
    ('thiolate beside an amide', 'NC(=O)c1ccc([S-])cc1', '4-sulfidobenzene-1-carboxamide'),
    ('alkyl thiolate beside a nitrile', 'N#CCC[S-]', '3-sulfidopropanenitrile'),
    ('two phenolates beside a nitrile', 'N#Cc1ccc([O-])c([O-])c1', '3,4-dioxidobenzene-1-carbonitrile'),
    ('thiolate beside a thioether and a nitrile', 'CSc1ccc(C#N)cc1[S-]', '4-(methylsulfanyl)-3-sulfidobenzene-1-carbonitrile'),
]

ANION_UNCHANGED = [
    ('methoxide', 'C[O-]', 'methoxide'),
    ('ethoxide', 'CC[O-]', 'ethoxide'),
    ('tert-butoxide', 'CC(C)(C)[O-]', 'tert-butoxide'),
    ('phenoxide', 'c1ccccc1[O-]', 'phenoxide'),
    ('benzenethiolate', '[S-]c1ccccc1', 'benzenethiolate'),
    ('a diolate', '[O-]CC[O-]', 'ethane-1,2-diolate'),
    ('a hydroxy olate', 'OCC[O-]', '2-hydroxyethan-1-olate'),
    ('a purine thiolate', '[S-]c1ncnc2[nH]cnc12', '9H-purine-6-thiolate'),
]

HELICENES = [
    ('pentahelicene acetamido at 1', 'CC(=O)Nc1cccc2ccc3ccc4ccc5ccccc5c4c3c12', 'N-(pentahelicen-1-yl)acetamide'),
    ('pentahelicene acetamido at 4', 'CC(=O)Nc1cccc2c1ccc1ccc3ccc4ccccc4c3c12', 'N-(pentahelicen-4-yl)acetamide'),
    ('pentahelicene acetamido at 5', 'CC(=O)Nc1cc2ccc3ccc4ccccc4c3c2c2ccccc12', 'N-(pentahelicen-5-yl)acetamide'),
    ('pentahelicene acetamido at 6', 'CC(=O)Nc1cc2ccccc2c2c1ccc1ccc3ccccc3c12', 'N-(pentahelicen-6-yl)acetamide'),
    ('hexahelicene acetamido at 1', 'CC(=O)Nc1cccc2ccc3ccc4ccc5ccc6ccccc6c5c4c3c12', 'N-(hexahelicen-1-yl)acetamide'),
    ('hexahelicene acetamido at 4', 'CC(=O)Nc1cccc2c1ccc1ccc3ccc4ccc5ccccc5c4c3c12', 'N-(hexahelicen-4-yl)acetamide'),
    ('hexahelicene acetamido at 5', 'CC(=O)Nc1cc2ccc3ccc4ccc5ccccc5c4c3c2c2ccccc12', 'N-(hexahelicen-5-yl)acetamide'),
    ('hexahelicene acetamido at 6', 'CC(=O)Nc1cc2ccccc2c2c1ccc1ccc3ccc4ccccc4c3c12', 'N-(hexahelicen-6-yl)acetamide'),
    ('heptahelicene acetamido at 1', 'CC(=O)Nc1cccc2ccc3ccc4ccc5ccc6ccc7ccccc7c6c5c4c3c12', 'N-(heptahelicen-1-yl)acetamide'),
    ('heptahelicene acetamido at 4', 'CC(=O)Nc1cccc2c1ccc1ccc3ccc4ccc5ccc6ccccc6c5c4c3c12', 'N-(heptahelicen-4-yl)acetamide'),
    ('heptahelicene acetamido at 5', 'CC(=O)Nc1cc2ccc3ccc4ccc5ccc6ccccc6c5c4c3c2c2ccccc12', 'N-(heptahelicen-5-yl)acetamide'),
    ('heptahelicene acetamido at 6', 'CC(=O)Nc1cc2ccccc2c2c1ccc1ccc3ccc4ccc5ccccc5c4c3c12', 'N-(heptahelicen-6-yl)acetamide'),
    ('octahelicene acetamido at 1', 'CC(=O)Nc1cccc2ccc3ccc4ccc5ccc6ccc7ccc8ccccc8c7c6c5c4c3c12', 'N-(octahelicen-1-yl)acetamide'),
    ('octahelicene acetamido at 4', 'CC(=O)Nc1cccc2c1ccc1ccc3ccc4ccc5ccc6ccc7ccccc7c6c5c4c3c12', 'N-(octahelicen-4-yl)acetamide'),
    ('octahelicene acetamido at 5', 'CC(=O)Nc1cc2ccc3ccc4ccc5ccc6ccc7ccccc7c6c5c4c3c2c2ccccc12', 'N-(octahelicen-5-yl)acetamide'),
    ('octahelicene acetamido at 6', 'CC(=O)Nc1cc2ccccc2c2c1ccc1ccc3ccc4ccc5ccc6ccccc6c5c4c3c12', 'N-(octahelicen-6-yl)acetamide'),
]

ALL = AMIDINIUM + PYRROLINIUM + ANION_PREFIX + ANION_UNCHANGED + HELICENES


@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name(label, smiles, expected):
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", ALL, ids=[row[0] for row in ALL])
def test_the_name_reads_back_to_the_molecule(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_a_carboxylate_beside_an_amidinium_is_cited_as_carboxylato_not_as_the_acid():
    for _label, smiles, expected in AMIDINIUM:
        if "[O-]" in smiles:
            assert "carboxylato" in expected, expected
            assert "carboxy" not in expected.replace("carboxylato", ""), expected


def test_a_pyrrolinium_has_no_hantzsch_widman_spelling():
    for _label, _smiles, expected in PYRROLINIUM:
        assert "azol-" not in expected.replace("imidazol-", "").replace("diazol-", "").replace("pyrazol-", ""), expected
        assert "diazol" not in expected.replace("imidazol", ""), expected


def test_an_anion_beside_a_senior_group_always_carries_its_charge():
    """The invariant behind D-227: the name of an anion has a word for the anion."""
    for _label, _smiles, expected in ANION_PREFIX:
        assert "sulfido" in expected or "oxido" in expected, expected
        assert "sulfanyl" not in expected.replace("methylsulfanyl", "") and "hydroxy" not in expected, expected


@pytest.mark.parametrize(
    "smiles",
    [
        "N#Cc1ccc([O-])cc1O",  # a real OH beside the phenolate: which one is the anion cannot be said by a count
        "NC(=[NH2+])CC(C(=O)[O-])C(=O)O",  # a zwitterion with a second acid: which carboxy is the carboxylate
    ],
)
def test_a_name_that_cannot_place_the_charge_is_refused_not_written_neutral(smiles):
    with pytest.raises(ValueError):
        name_smiles(smiles)
