"""Naming round 50 (D-246, D-247): a bare `imino` after another prefix, and the iminium cations rounds 49 left refused.

D-246: a bare `imino` right after ANOTHER prefix runs together into a SUBSTITUTED imino group. Round 49 bracketed it after `amino` and `hydroxy` only; the anion population of
round 50 found `{[...]methyldiazenyl}iminomethanethiolate`, which OPSIN reads with an N-N bond (`NN=C[S-]`), and measured the general rule: `methyliminomethanethiol` reads `CN=CS`
(the group =N-CH3) while `methyl(imino)methanethiol` reads `CC(S)=N`. So `imino` is enclosed whenever a prefix precedes it.
D-247: an iminium whose NITROGEN carries a heteroatom (an N-sulfonyl iminium, the cation of a quinone imine: `C=[NH+]S(=O)(=O)Ar`) was refused, and so was a QUATERNARY iminium
(no hydrogen on the nitrogen: `C[N+](C)=C(N)S`). The round 49 classifier took only a protonated nitrogen and a heteroatom on the carbon. Identical groups on the nitrogen are
one multiplied prefix (`dimethyl`, not `(methyl)(methyl)`).

Both found by `tools/naming_ion_populations.py`: 285 anions, 1036 cations and 1036 quaternary cations, three refusals and one wrong name between them. Every name read back
through OPSIN to its input, charge included.
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (label, SMILES, the name)
IMINO = [
    ("imino after a bracketed prefix", "N=C([S-])N=NC=C1C=CC(N(O)O)=CC1=O",
     "{[4-(dihydroxyamino)-6-oxocyclohexa-2,4-dien-1-ylidene]methyldiazenyl}(imino)methanethiolate"),
    ("imino after amino (round 49)", "[S-]C(=N)N", "amino(imino)methanethiolate"),
]

IMINIUM = [
    ("an N-sulfonyl quinone imine cation", "O=C1C(Cl)=CC(=[NH+]S(=O)(=O)c2ccc(Cl)cc2)c2ccccc21",
     "(3-chloro-4-oxo-1,4-dihydronaphthalen-1-ylidene)(4-chlorophenylsulfonyl)azanium"),
    ("the same, N-methylated (quaternary)", "C[N+](=C1C=C(Cl)C(=O)c2ccccc21)S(=O)(=O)c1ccc(Cl)cc1",
     "(3-chloro-4-oxo-1,4-dihydronaphthalen-1-ylidene)(4-chlorophenylsulfonyl)(methyl)azanium"),
    ("an N-sulfonyl acetone imine cation", "CC(=[NH+]S(=O)(=O)C)C", "methylsulfonyl(propan-2-ylidene)azanium"),
    ("a quaternary isothiourea cation, identical methyls", "C[N+](C)=C(N)S", "[amino(sulfanyl)methylidene]dimethylazanium"),
    ("a quaternary isourea cation", "C[N+](C)=C(N)OC", "[amino(methoxy)methylidene]dimethylazanium"),
    ("a quaternary imidate cation", "C[N+](C)=C(C)OC", "(1-methoxyethylidene)dimethylazanium"),
    ("the census quaternary amidoxime ether", "C[N+](C(=NOCc1ccccc1)c1ccccc1)=C(N)S",
     "[amino(sulfanyl)methylidene](methyl)[phenyl(phenylmethoxyimino)methyl]azanium"),
    ("a protonated isothiourea (round 49, unchanged)", "NC(S)=[NH2+]", "[amino(sulfanyl)methylidene]azanium"),
]

#: The two ways the first version of the widened classifier went wrong, found by the census on its first run: a RING nitrogen was carved into two separate substituents (the ring
#: cut, a different molecule), and an N-acylamino iminium that the plan search already named correctly was taken from it. Both stay with the route that names them.
KEPT_WITH_THE_OLD_ROUTE = [
    ("a pyrrolidinium ylidene", "C1CC[N+](C1)=C(N)S", "1-[amino(sulfanyl)methylidene]pyrrolidin-1-ium"),
    ("a morpholinium ylidene", "C1COCC[N+]1=C(N)OC", "4-[amino(methoxy)methylidene]morpholin-4-ium"),
    ("a morpholinium amidine", "c1ccccc1C(=[N+]2CCOCC2)N", "4-[amino(phenyl)methylidene]morpholin-4-ium"),
    ("an acylhydrazone cation", "CC(=[NH+]NC(=O)C)C", "acetamido(propan-2-ylidene)azanium"),
    ("a hydrazone cation", "CC(=[NH+]N)C", "amino(propan-2-ylidene)azanium"),
    ("an oxime cation: a carbon-only carbon, the old route", "CC(=[NH+]O)C", "hydroxy(propan-2-ylidene)azanium"),
]

ALL = IMINO + IMINIUM + KEPT_WITH_THE_OLD_ROUTE


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


@needs_opsin
def test_the_bare_form_is_the_one_opsin_misreads():
    """What D-246 removed, measured: `methylimino` is =N-CH3, `methyl(imino)` is methyl and imino on one carbon."""
    from py2opsin import py2opsin

    assert Chem.MolToInchiKey(Chem.MolFromSmiles(py2opsin("methyliminomethanethiol"))) == Chem.MolToInchiKey(Chem.MolFromSmiles("CN=CS"))
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(py2opsin("methyl(imino)methanethiol"))) == Chem.MolToInchiKey(Chem.MolFromSmiles("CC(S)=N"))


def test_an_ordinary_iminium_is_not_taken_from_the_route_that_names_it():
    """A carbon-only iminium (nothing but carbon and hydrogen around the nitrogen and its carbon) keeps the route that already named it."""
    assert name_smiles("C[NH+]=C(C)C") == "methyl(propan-2-ylidene)azanium"


def test_an_ordinary_amidinium_is_still_the_amidinium():
    assert name_smiles("CC(N)=[NH2+]").endswith("amidinium")
