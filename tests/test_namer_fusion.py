"""General fusion nomenclature, P-25.3 (naming round 5, N3).

The engine named a fused ring system by fusion only through a ring table
and one narrow route (a [1,3]-dihetero or mono-hetero five-ring on a known
base); anything else fell to a von Baeyer name, and the narrow route itself
chose the wrong parent ("furo[2,3-b]thiophene" for thieno[2,3-b]furan) and
invented names ("selenolo[2,3-b]selenofuran"). Measured on the book's own
P-25 examples before this stage: 13 of 125 ortho- and peri-fused systems
named exactly.

`fusion_general` builds the name the book's way and `fusion_orientation`
numbers it by the book's drawing rules. THE SUPPORTED CLASS, as the module
states it: one parent component, first-order attached components, rings of
three to eight members. Outside it the constructor refuses with a code, and
a refusal whose fusion name needs a second-order or multiparent construction
goes to von Baeyer rather than to the older fusion route.

Expected names below are the book's, with its page; every one was also
parsed back by OPSIN to the structure it names when this file was written.
"""

from __future__ import annotations

import logging
import random

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import name_smiles
from openchem.vendor.iupac_namer.ring_naming import fusion_general as fg
from openchem.vendor.iupac_namer.ring_naming.fusion_orientation import Unsupported

# (SMILES of the parent, as OPSIN parses the book's name; the book's PIN;
# pdf page). Retained-table names are included where this stage fixed them.
BOOK = [
    ("c1cc2ccsc2o1", "thieno[2,3-b]furan", 222),
    ("c1cc2cc[se]c2[se]1", "selenopheno[2,3-b]selenophene", 210),
    ("C1=Nc2ccccc2CO1", "4H-3,1-benzoxazine", 207),
    ("C1=Cc2ccccc2C=CO1", "3-benzoxepine", 207),
    ("c1cc2c(o1)OCO2", "2H-furo[2,3-d][1,3]dioxole", 218),
    ("c1cc2ccc3ncccc3cc-2c1", "azuleno[6,5-b]pyridine", 217),
    ("c1ccc2c(c1)[nH]c1cc3nccnc3cc12", "6H-pyrazino[2,3-b]carbazole", 217),
    ("C1=COC2=CCOC2=C1", "2H-furo[3,2-b]pyran", 217),
    ("c1cc2ccc3cc4ccccc4cc3cc-2c1", "naphtho[2,3-f]azulene", 217),
    ("C1=NOCc2cccnc21", "5H-pyrido[2,3-d][1,2]oxazine", 218),
    ("c1cn2ccsc2n1", "imidazo[2,1-b][1,3]thiazole", 220),
    ("C1=CC2=C3C=CC=CN3C=CN2C=C1", "dipyrido[1,2-a:2',1'-c]pyrazine", 220),
    ("c1coc2cccc-2c1", "cyclopenta[b]pyran", 221),
    ("c1cc2nc3ccoc3cc2o1", "difuro[3,2-b:2',3'-e]pyridine", 225),
    ("c1cc2nc3ccsc3cc2o1", "furo[3,2-b]thieno[2,3-e]pyridine", 229),
    ("c1ccc2cc3ncccc3cc2c1", "benzo[g]quinoline", 239),
    ("c1ccc2cc3[nH]nnc3cc2c1", "1H-naphtho[2,3-d][1,2,3]triazole", 239),
    ("c1cc2ccc3ccnc4ccc(c1)c2c34", "naphtho[2,1,8-def]quinoline", 239),
    ("C1=CC=CC2=C(C=C1)C=CC2", "1H-cyclopenta[8]annulene", 238),
    ("c1ccc2c(c1)COc1ccccc1-2", "6H-dibenzo[b,d]pyran", 234),
    ("C1=c2ccccc2=c2ccccc2=CO1", "dibenzo[c,e]oxepine", 234),
    ("c1ccc2nc3cc4cnc5ccccc5c4cc3cc2c1", "quinolino[4,3-b]acridine", 218),
    ("c1ccc2c(c1)cc1ccc3cccc4ccc2c1c34", "benzo[pqr]tetraphene", 219),
    ("c1poc2c1OCO2", "5H-[1,3]dioxolo[4,5-d][1,2]oxaphosphole", 218),
    ("c1nc2[se]cnc2s1", "[1,3]selenazolo[5,4-d][1,3]thiazole", 218),
    ("[nH]1oc2os[nH]c=2s1", "3H,5H-[1,3,2]oxathiazolo[4,5-d][1,2,3]oxathiazole", 219),
    ("c1cc2cc3csnc3cc2s1", "thieno[3,2-f][2,1]benzothiazole", 233),
    ("C1=CSc2cc3cccnc3cc2N1", "4H-[1,4]thiazino[2,3-g]quinoline", 234),
    ("C1=Cc2cc3ccccc3c3cccc1c23", "acephenanthrylene", 219),
    ("c1ccc2cc3cc4ccccc4cc3cc2c1", "tetracene", 220),
    # the book's table prints the ring without its indicated hydrogen and
    # says "the PIN is 4H-quinolizine" (p. 203)
    ("C1=CCN2C=CC=CC2=C1", "4H-quinolizine", 205),
]


def _quiet():
    logging.disable(logging.WARNING)


@pytest.fixture(autouse=True)
def _no_warnings():
    _quiet()
    yield
    logging.disable(logging.NOTSET)


@pytest.mark.parametrize("smiles,expected,page", BOOK, ids=[n for _s, n, _p in BOOK])
def test_the_book_parent_is_named_as_the_book_names_it(smiles, expected, page):
    assert name_smiles(smiles) == expected, f"pdf p. {page}"


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # P-25.3.2.4 (a): O is senior to S, so furan is the parent.
        ("c1cc2ccsc2o1", "thieno[2,3-b]furan"),
        # P-25.2.2.4: a benzene on a heteromonocycle is ONE component unit.
        ("C1=Cc2ccccc2C=CO1", "3-benzoxepine"),
        # P-25.3.5: two benzenes on one heterocycle are "dibenzo", not a
        # benzo name inside a benzo name.
        ("C1=c2ccccc2=c2ccccc2=CO1", "dibenzo[c,e]oxepine"),
        # P-25.3.8.1: a monocyclic hydrocarbon prefix cites letters only...
        ("c1ccc2nc3c(cc2c1)CCCCC3", "cyclohepta[b]quinoline"),
        # ...and none when the parent is one too.
        ("C1=CC=CC2=C(C=C1)C=CC2", "cyclopenta[8]annulene"),
        # P-25.3.1.3: a peri descriptor cites only the attached component's
        # nonfused atoms (not "[2,1,8a,8-def]").
        ("c1cc2ccc3ccnc4ccc(c1)c2c34", "naphtho[2,1,8-def]quinoline"),
    ],
)
def test_the_construction_follows_the_rule_it_cites(smiles, expected):
    mol = Chem.MolFromSmiles(smiles)
    assert fg.name_fusion(mol, mol.GetRingInfo().AtomRings()).text == expected


@pytest.mark.parametrize(
    "smiles,code,why",
    [
        # benzo[1,2-b:4,5-c']difuran (p. 234): multiparent beats a fusion name
        ("c1cc2cc3cocc3cc2o1", Unsupported.NEEDS_UNBUILT_CONSTRUCTION, "multiparent"),
        # cyclopenta[4,5]pyrrolo[2,3-c]pyridine (p. 239): a second-order component
        ("C1=CC2=c3ccncc3=NC2=C1", Unsupported.NEEDS_UNBUILT_CONSTRUCTION, "second order"),
        # 1H-cyclopropabenzene: P-52.2.4.1, fewer than two rings of five or more
        ("C1C2=CC=CC=C12", Unsupported.OUTSIDE_CLASS, "P-52.2.4.1"),
        # 6H-quinolizino[3,4,5,6-ija]quinoline (p. 223): an interior N
        ("C1=CC2=CC=C3C=CCC4=C3N2C(=C1)C=C4", Unsupported.OUTSIDE_CLASS, "P-25.3.3.2"),
        # hexahelicene (p. 221): its own orientation rule
        ("c1ccc2c(c1)ccc1ccc3ccc4ccc5ccccc5c4c3c12", Unsupported.OUTSIDE_CLASS, "helicene"),
    ],
)
def test_a_refusal_says_what_kind_it_is(smiles, code, why):
    mol = Chem.MolFromSmiles(smiles)
    with pytest.raises(Unsupported) as exc:
        fg.name_fusion(mol, mol.GetRingInfo().AtomRings())
    assert exc.value.code == code, why


def test_a_multiparent_system_is_not_handed_to_the_older_fusion_route():
    """Before: "furo[2,3-f]2-benzofuran", a fusion-looking name that is not
    the book's construction (nor well formed: a benzo parent takes brackets).
    The older route no longer stands in; what remains is a von Baeyer name
    where that construction succeeds, and a stated refusal where it does not
    (it does not for this one) -- never the stand-in."""
    got = name_smiles("c1cc2cc3cocc3cc2o1")
    assert "2-benzofuran" not in got
    assert "cyclo[" in got or got.startswith("[NAMING ERROR")


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("C1CC2CCC1C2", "bicyclo[2.2.1]heptane"),          # bridged: von Baeyer is right
        ("C1CN2CCC1CC2", "1-azabicyclo[2.2.2]octane"),
        ("C1C2=CC=CC=C12", "bicyclo[4.1.0]hepta-1,3,5-triene"),  # P-52.2.4.1, p. 450
        ("c1ccc2ncccc2c1", "quinoline"),                   # retained: the table wins
        ("Clc1c2ccccc2cc2ccccc12", "9-chloroanthracene"),  # traditional numbering kept
        ("Clc1c2ccccc2nc2ccccc12", "9-chloroacridine"),
        # the table's cis/trans override keeps its stereo; a competing
        # constructed "decahydronaphthalene" took it away once (N3)
        ("C1CC[C@H]2CCCC[C@@H]2C1", "trans-decalin"),
    ],
)
def test_the_converses_do_not_move(smiles, expected):
    assert name_smiles(smiles) == expected


def test_the_orientation_decides_where_the_heteroatom_falls():
    """Without the drawing, the heteroatom criterion alone puts the
    nitrogen of cyclohepta[b]quinoline at 1. The book's drawing puts three
    rings in a row and numbers from the upper right, so the carboxamide the
    held-out molecule carries is on C11 and the hydro block reads 7,8,9,10 --
    PubChem prints the same name."""
    got = name_smiles("CCN(CC)C(=O)c1c2c(nc3ccccc13)CCCCC2")
    assert got == "N,N-diethyl-7,8,9,10-tetrahydro-6H-cyclohepta[b]quinoline-11-carboxamide"


@pytest.mark.parametrize(
    "smiles",
    [
        "c1coc2sccc12",
        "c1ccc2nc3c(cc2c1)CCCCC3",
        "CN1CCN([C@H]2c3cc(Cl)ccc3Sc3ccccc3[C@H]2O)CC1",
        "c1ccc2c(c1)[nH]c1cc3nccnc3cc12",
    ],
)
def test_the_name_does_not_depend_on_atom_order(smiles):
    reference = name_smiles(smiles)
    mol = Chem.MolFromSmiles(smiles)
    rng = random.Random(20260919)
    for _ in range(4):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        shuffled = Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False)
        assert name_smiles(shuffled) == reference, shuffled
