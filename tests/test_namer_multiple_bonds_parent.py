"""P-44.4.1.1: the principal chain has the greater number of multiple bonds.

BlueBookV2.pdf p. 401: "The senior ring, ring system or principal chain has the greater number of multiple bonds". It comes after the chain LENGTH
(P-44.3) and before everything that only tells two numberings or two substituent sets apart.

`strategy._parent_selection_score` used to count unsaturation INFIXES, and one infix names every bond of its kind: `1,3,13-triene` is one infix and three bonds.
A diene and a triene therefore tied on that band, the next tier that sees them (`unsaturation_locants`) is only meaningful between numberings of ONE parent and
ranks the SHORTER locant set higher across parents, and the diene with an ethenyl substituent won on every spelling: the book's P-45.2.3 examples 6 and 9 (pinned in
`test_namer_parent_citation_locants.py`), and any molecule of the same shape. Counting the bonds the infixes name is the whole change.

What is pinned here is the converse as much as the case: a parent with more bonds must win only AMONG chains of equal length (a longer chain with fewer bonds is still the
parent), and the two neighbouring criteria this one must not be mistaken for (double over triple, P-44.4.1.2, is NOT implemented and is pinned as open).
"""
from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.naming_providers import opsin_available
from openchem.vendor.iupac_namer import name_smiles
from tests.naming_spellings import checked_spellings

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")

SEED = 20261007
SPELLINGS = 12

# (label, SMILES, the one name every spelling gets). Each name was read back through OPSIN to the structure's InChIKey
# (`test_the_names_read_back_to_their_structures`).
CHOSEN_BY_BOND_COUNT = [
    # Two arms of the same length on one carbon: a buta-1,3-dienyl and a but-1-enyl. The chains through them tie on length and on the number of infixes (one each), so
    # the parent was the ene and the diene was a substituent: `5-(buta-1,3-dien-1-yl)dec-3-ene`, on all 12 spellings.
    ("diene arm against an ene arm", "CCCCCC(C=CC=C)C=CCC", "5-(but-1-en-1-yl)deca-1,3-diene"),
    # A triple bond is ONE multiple bond (not two): a diene arm (two) is senior to an equal-length yne arm (one). Counting a triple bond double ties them and the parent
    # follows plan order (found by a mutant that did exactly that).
    ("diene arm against an yne arm", "CCCCCC(C=CC=C)C#CCC", "5-(but-1-yn-1-yl)deca-1,3-diene"),
]

# Not moved by the change: a longer chain with fewer bonds is still the parent (length is a band of its own, and dominates), and the cases that were already right
# because the INFIX count already told them apart.
UNCHANGED = [
    ("a longer chain beats more bonds", "CCCCCCC(C=C)C=C", "3-ethenylnon-1-ene"),
    ("ene against yne of equal length", "CCCCC(C#CC)C=CCC", "5-(prop-1-yn-1-yl)non-3-ene"),
    ("diene and yne against a diene", "CCCCC(C=CC=C)C#CCC", "5-butylnona-1,3-dien-6-yne"),
    ("four bonds against three", "C=CC=CCC(CC#C)C=CC=C", "5-(prop-2-yn-1-yl)deca-1,3,7,9-tetraene"),
    ("a ring with a double bond against benzene", "C1=CCCCC1c1ccccc1", "(cyclohex-2-en-1-yl)benzene"),
]


def _spellings(smiles: str, count: int = SPELLINGS) -> list[str]:
    """Random roots and atom orders of one structure, each checked to BE that structure."""
    return checked_spellings(smiles, count, SEED)


def _names(smiles: str) -> set[str]:
    return {name_smiles(spelling) for spelling in _spellings(smiles)}


@pytest.mark.parametrize("label,smiles,expected", CHOSEN_BY_BOND_COUNT, ids=[row[0] for row in CHOSEN_BY_BOND_COUNT])
def test_the_chain_with_more_multiple_bonds_is_the_parent(label, smiles, expected):
    assert _names(smiles) == {expected}


@pytest.mark.parametrize("label,smiles,expected", UNCHANGED, ids=[row[0] for row in UNCHANGED])
def test_what_the_count_does_not_move(label, smiles, expected):
    assert _names(smiles) == {expected}


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", CHOSEN_BY_BOND_COUNT + UNCHANGED, ids=[row[0] for row in CHOSEN_BY_BOND_COUNT + UNCHANGED])
def test_the_names_read_back_to_their_structures(label, smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_the_band_counts_bonds_not_infixes():
    """The change itself, at the score: a triene and a diene are one infix each and differ by one bond.

    Both plans come from the same molecule (the book's example 9), so nothing but the multiple-bond band differs between the chain that carries three and the one that
    carries two.
    """
    from openchem.vendor.iupac_namer import strategy
    from openchem.vendor.iupac_namer.types import Locant, UnsaturationInfix

    owner = next(cls for cls in vars(strategy).values() if isinstance(cls, type) and "_parent_selection_score" in vars(cls))
    score = owner._parent_selection_score

    def plan(*infixes):
        return type("P", (), {"unsaturation": infixes})()

    def infix(*locants):
        return UnsaturationInfix("en", tuple(Locant.numeric(v) for v in locants), None)

    assert infix(1, 3, 9).locants and len(infix(1, 3, 9).locants) == 3
    # The band alone: subtract the score of a plan with no unsaturation, which every other band sees identically.
    from types import SimpleNamespace

    def band(*infixes):
        fake = SimpleNamespace(
            named_parent=SimpleNamespace(candidate=SimpleNamespace(type="chain", ring_system=None, atom_indices=frozenset(), length=0),
                                         naming_method="x"),
            suffix_groups=(), pcg_instances=(), pcg_type=None, prefix_assignments=(), unsaturation=infixes,
        )
        return score(object.__new__(owner), fake)

    triene, diene, none_ = band(infix(1, 3, 9)), band(infix(1, 3)), band()
    assert triene > diene > none_
    assert triene - diene == pytest.approx(0.001)
    assert diene - none_ == pytest.approx(0.002)


@pytest.mark.xfail(strict=True, reason="open defect, P-44.4.1.2 (the principal chain has the greater number of DOUBLE bonds: hepta-1,6-diene before hept-1-en-6-yne) is not implemented")
def test_a_diene_is_senior_to_an_ene_yne_of_the_same_length():
    """`C=CCCC(CCC=C)CCC#C` has chains of nine carbons that carry two multiple bonds either way; the book's P-44.4.1.2 example 5 prefers the diene.

    Not decided by anything yet, so the name follows plan order: three names over 12 spellings (two of them the ene-yne). The count of bonds is equal, which is why
    this is a separate criterion and not this one.
    """
    assert _names("C=CCCC(CCC=C)CCC#C") == {"5-(but-3-yn-1-yl)nona-1,8-diene"}
