"""P-14.4 (j): when two numberings tie on everything else, R takes the lower locant (and Z, M, r), not whichever the atom order gave.

`C[C@H](O)[C@@H](C)O` (meso butane-2,3-diol) was `(2R,3S)-` or `(2S,3R)-butane-2,3-diol` by the order its atoms were written
in. Both read back to the same structure, so nothing failed and no corpus row could see it; the name was simply not a
function of the molecule. The two numberings tied on every tier of the preference key and on P-14.4 (g), and fell to plan
generation order, which follows atom order. The Blue Book settles it (BlueBookV2.pdf p. 79, criterion (j) of P-14.4): of each
pair of CIP descriptors, Z, R, M and r take the lower locant; the units' locants are compared first and the descriptors in
locant order after, the first point of difference deciding. It is the LAST criterion, after (g).

It is applied in `engine._break_alphanumerical_tie`, between numberings of one parent: a chain, a ring, and the `-diyl` group of a
polyol's diester (`(2R,4S)-pentane-2,4-diyl diacetate`, naming round 26).

It was first NOT applied in `engine._break_ester_tie`, the choice of which ester of a polyester is principal. A tier was built there
and removed: with it, meso dipropylene glycol diacetate came out as the R,R compound. The tier was not the cause. The session cache
was keyed on a SMILES that cannot write the descriptor a carved fragment inherits, so the second ester plan reused the first plan's
tree and its descriptors (`context_stereo_key`; `test_namer_stereo_cache_identity.py`). With that fixed the tier is back, pinned in
`test_namer_stereo_parents_and_citation.py`. `test_every_stereoisomer_of_these_diesters_reads_back` below is the guard that found
it, and it is the reason this file reads names back instead of only comparing them.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from rdkit import Chem

from openchem.chem.naming_providers import opsin_available
from openchem.vendor.iupac_namer import engine, name_smiles
from openchem.vendor.iupac_namer.types import Locant, StereoCenter, StereoDescriptor
from tests.naming_spellings import checked_spellings

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")

SEED = 20261006
SPELLINGS = 12


def _spellings(smiles: str) -> list[str]:
    """Random roots and atom orders of one structure, each checked to BE that structure.

    The check is not decoration: `MolToSmiles(doRandom=True)` on a molecule straight out of `EnumerateStereoisomers` writes
    a different stereoisomer, and a run of this file once "found" instability that was the probe's, not the engine's. (`doRandom` is
    gone from here for another reason too: it ignores the seed, so the spellings were new on every run. See `tests/naming_spellings.py`.)
    """
    return checked_spellings(smiles, SPELLINGS, SEED)


def _names(smiles: str) -> set[str]:
    return {name_smiles(spelling) for spelling in _spellings(smiles)}


# --- the rule itself, on made-up descriptors: no molecule, no OPSIN -------------------------------------------------------

def _carrier(*rows):
    """A stand-in for a plan: `(locant, descriptor, atom)` rows as the engine collects them."""
    return SimpleNamespace(stereo_descriptors=tuple(
        StereoDescriptor(Locant.numeric(loc), desc, StereoCenter(atom, "tetrahedral", desc, None))
        for loc, desc, atom in rows
    ))


def _ranks(carrier):
    key = engine._stereo_locant_key(carrier)
    return key[1], key[2]


def test_r_takes_the_lower_locant_of_a_pair():
    # the two numberings of a meso centre pair: same atoms, labels swapped
    assert _ranks(_carrier((2, "R", 4), (3, "S", 7))) < _ranks(_carrier((2, "S", 7), (3, "R", 4)))


@pytest.mark.parametrize("preferred,other", [("Z", "E"), ("R", "S"), ("M", "P"), ("r", "s")])
def test_each_preferred_descriptor_beats_its_partner(preferred, other):
    assert _ranks(_carrier((2, preferred, 4))) < _ranks(_carrier((2, other, 4)))


def test_the_first_point_of_difference_decides_in_locant_order():
    # the book's own example, `(2Z,4S,8R,9E)-undeca-2,9-diene-4,8-diol`: "the choice is between E and Z for position 2, not
    # between R and S for position 4". The other numbering reads (2E,4R,8S,9Z) and has the preferred letter at 4.
    this_way = _carrier((2, "Z", 1), (4, "S", 5), (8, "R", 9), (9, "E", 12))
    that_way = _carrier((2, "E", 12), (4, "R", 9), (8, "S", 5), (9, "Z", 1))
    assert _ranks(this_way) < _ranks(that_way)


def test_lower_locants_for_the_stereogenic_units_come_first():
    # "lower locants related to the presence of stereogenic centers": one unit specified, numbered 2 or 3
    assert _ranks(_carrier((2, "S", 4))) < _ranks(_carrier((3, "R", 4)))


def test_the_descriptors_are_ordered_by_locant_not_by_the_order_given():
    assert _ranks(_carrier((3, "S", 7), (2, "R", 4))) == _ranks(_carrier((2, "R", 4), (3, "S", 7)))


def test_a_descriptor_that_cannot_be_ranked_declines_the_whole_key():
    assert engine._stereo_locant_key(_carrier((2, "rel-R", 4))) is None
    assert engine._stereo_locant_key(SimpleNamespace(stereo_descriptors=None)) == (frozenset(), (), ())


def test_numberings_that_describe_different_atoms_are_not_compared():
    # A numbering that drops a descriptor (a junction locant a bridged parent cannot cite) describes FEWER atoms, and the
    # shorter tuple would win by length alone: a name that says less would be preferred to one that says more.
    both = engine._stereo_locant_key(_carrier((2, "S", 4), (3, "R", 7)))
    one = engine._stereo_locant_key(_carrier((2, "R", 4)))
    assert engine._comparable_stereo([both, one]) is None
    assert engine._comparable_stereo([both, None]) is None
    assert engine._comparable_stereo([]) is None
    same = engine._comparable_stereo([both, engine._stereo_locant_key(_carrier((2, "R", 7), (3, "S", 4)))])
    assert same is not None and len(same) == 2


# --- the meso structures of the report, by atom order ---------------------------------------------------------------------

MESO = [
    # the four of the report
    ("C[C@H](O)[C@@H](C)O", "(2R,3S)-butane-2,3-diol"),
    ("C[C@H](Cl)[C@@H](C)Cl", "(2R,3S)-2,3-dichlorobutane"),
    ("C[C@H](Br)[C@@H](C)Br", "(2R,3S)-2,3-dibromobutane"),
    ("O[C@H]1CCCC[C@H]1O", "(1R,2S)-cyclohexane-1,2-diol"),
    # the same defect where it was not reported
    ("O[C@H]1CCC[C@@H](O)C1", "(1R,3S)-cyclohexane-1,3-diol"),
    ("Cl[C@H]1CCC[C@@H](Cl)C1", "(1R,3S)-1,3-dichlorocyclohexane"),
    ("C[C@H](O)C[C@@H](C)O", "(2R,4S)-pentane-2,4-diol"),
    ("OC(=O)[C@H](O)[C@H](O)C(=O)O", "(2R,3S)-2,3-dihydroxybutanedioic acid"),
    ("CCOC(=O)[C@H](O)[C@H](O)C(=O)OCC", "diethyl (2R,3S)-2,3-dihydroxybutanedioate"),
    ("OC[C@H](O)[C@@H](O)[C@H](O)CO", "(2R,3r,4S)-pentane-1,2,3,4,5-pentol"),
]

# Examples the book prints, each decided by (j): BlueBookV2.pdf p. 79 and the P-93 trichloropentanedioic acids
BOOK = [
    ("C[C@H](F)C[C@@H](C)F", "(2R,4S)-2,4-difluoropentane"),
    ("OC(=O)/C=C\\C/C=C/C(=O)O", "(2Z,5E)-hepta-2,5-dienedioic acid"),
    ("C/C=C\\C/C=C/C", "(2Z,5E)-hepta-2,5-diene"),
    ("C/C=C\\[C@@H](O)CCC[C@@H](O)/C=C/C", "(2Z,4S,8R,9E)-undeca-2,9-diene-4,8-diol"),
    ("O=C(O)[C@@H](Cl)[C@@H](Cl)[C@@H](Cl)C(=O)O", "(2R,3s,4S)-2,3,4-trichloropentanedioic acid"),
    ("O=C(O)[C@@H](Cl)[C@H](Cl)[C@@H](Cl)C(=O)O", "(2R,3r,4S)-2,3,4-trichloropentanedioic acid"),
]

# One unit specified, the skeleton symmetric: the descriptor takes the lowest locant its numbering allows
PARTIAL = [
    ("C[C@H](O)C(C)O", "(2S)-butane-2,3-diol"),
    ("C/C=C\\CC=C/C", "(2Z)-hepta-2,5-diene"),
]

# Meso diesters of one polyol with one acid: named `<organyl>-diyl diacetate` (P-65.6.3.3.3.1, naming round 26), so the choice is
# which way the `-diyl` group is numbered. Pinned by the FIRST DESCRIPTOR and not by the whole name, because the form is not this
# file's business. The cis-1,3 case is the one that was S-first for as long as it was named `3-(acetyloxy)cyclohexyl acetate`.
DIESTERS = [
    "CC(=O)O[C@H](C)C[C@H](C)OC(C)=O",
    "CC(=O)O[C@@H](C)[C@@H](C)OC(C)=O",
    "CC(=O)O[C@H]1CCCC[C@H]1OC(C)=O",
    "CC(=O)O[C@@H]1CCC[C@H](OC(C)=O)C1",
    "CC(=O)O[C@H](c1ccccc1)[C@@H](OC(C)=O)c1ccccc1",
    "CC(=O)O[C@H](C(C)C)[C@@H](OC(C)=O)C(C)C",
    "CC(=O)O[C@H]([C@H](OC(C)=O)C(F)(F)F)C(F)(F)F",
]

# Diesters whose organyl group is a multiplicative group, which round 26 leaves on the acyloxy form: the choice there is which ester is
# principal (`_break_ester_tie`, which has a (j) tier of its own; see the module docstring). Every stereoisomer must read back.
ESTER_ROUTE_DIESTERS = ["CC(=O)OC(C)COCC(C)OC(C)=O", "CC(=O)OC(C)COC(C)COC(C)=O"]

ALL_PINNED = MESO + BOOK + PARTIAL


@pytest.mark.parametrize("smiles,expected", ALL_PINNED, ids=[expected for _smiles, expected in ALL_PINNED])
def test_the_name_is_the_same_in_every_atom_order_and_gives_the_preferred_descriptors(smiles, expected):
    assert _names(smiles) == {expected}


@pytest.mark.parametrize("smiles", DIESTERS)
def test_a_meso_diester_is_one_name_with_r_at_the_lowest_locant(smiles):
    names = _names(smiles)
    assert len(names) == 1, names
    (name,) = names
    assert re.match(r"\(\d+R,", name), name


@needs_opsin
def test_every_pinned_name_reads_back_to_its_structure():
    from py2opsin import py2opsin

    # OPSIN cannot read a pseudoasymmetric `3r`/`3s` ("Failed to assign CIP stereochemistry"), which round 25 recorded; those
    # names are pinned above for their descriptors and left out here, where there is nothing to read them with.
    pairs = ALL_PINNED + [(smiles, name_smiles(smiles)) for smiles in DIESTERS]
    readable = [(s, n) for s, n in pairs if not re.search(r"\d[rs][,)]", n)]
    assert len(readable) >= len(pairs) - 3
    for smiles, expected in readable:
        back = py2opsin(expected)
        assert back, expected
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


# --- what (j) must not move ------------------------------------------------------------------------------------------------

def test_the_alphanumerical_criterion_outranks_the_stereodescriptors():
    # P-14.4 (g) comes before (j): the chloro takes the 2, although `(2R,3S)-3-chloro-2-fluorobutane` would have R at 2.
    # This isomer is (2S,3R)-2-chloro-3-fluorobutane, and any other answer puts the fluoro first.
    assert _names("C[C@H](Cl)[C@@H](C)F") == {"(2S,3R)-2-chloro-3-fluorobutane"}


@pytest.mark.parametrize("smiles,expected", [
    # SMILES chosen from RDKit's CIP labels (R,R / S,R meso / S,S), not from memory of what `@@` means
    ("C[C@@H](O)[C@@H](C)O", "(2R,3R)-butane-2,3-diol"),
    ("C[C@H](O)[C@@H](C)O", "(2R,3S)-butane-2,3-diol"),
    ("C[C@H](O)[C@H](C)O", "(2S,3S)-butane-2,3-diol"),
])
def test_a_pair_with_no_tie_is_named_as_it_always_was(smiles, expected):
    assert _names(smiles) == {expected}


def test_a_numbering_the_key_already_decides_is_untouched():
    # a suffix and a prefix at different locants: nothing ties, so (j) is never asked
    assert name_smiles("C[C@H](O)[C@H](C)Cl") == "(2S,3S)-3-chlorobutan-2-ol"


# --- the test is not vacuous: without the key, the spellings split ------------------------------------------------------

def test_without_the_stereo_key_the_same_spellings_give_two_names(monkeypatch):
    """The defect, kept alive: these exact spellings give two names when the key declines to decide.

    If this ever stops failing to agree, the fixture no longer reaches the tie and the tests above prove nothing.
    """
    monkeypatch.setattr(engine, "_stereo_locant_key", lambda carrier: None)
    assert _names("C[C@H](O)[C@@H](C)O") == {"(2R,3S)-butane-2,3-diol", "(2S,3R)-butane-2,3-diol"}
    # a `-diyl` group is numbered by the same tie-break, and without the key it was S-first for this one
    (name,) = _names("CC(=O)O[C@H](C)C[C@H](C)OC(C)=O")
    assert name.startswith("(2S,4R)-"), name


# --- every name the ester route writes must still be the molecule's --------------------------------------------------------

@needs_opsin
@pytest.mark.parametrize("flat", ESTER_ROUTE_DIESTERS + ["CC(=O)OC(C)CC(C)OC(C)=O", "CC(=O)OC1CCCC(OC(C)=O)C1", "CC(=O)OC1CCCCC1OC(C)=O"])
def test_every_stereoisomer_of_these_diesters_reads_back(flat):
    """A tie-break only CHOOSES between trees that already exist, so it is only as good as the worst of them.

    With an R-first tier on the ester route and the session cache keyed on the SMILES alone, one stereoisomer here (the meso
    `CC(=O)O[C@H](C)COC[C@H](C)OC(C)=O`) was named `(2R)-1-[(2R)-2-(acetyloxy)propoxy]propan-2-yl acetate`, the R,R compound,
    because one of the two candidate trees carried descriptors that do not describe the molecule and R-first preferred it.
    Reading every isomer back is what finds that.
    """
    from py2opsin import py2opsin
    from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers

    for isomer in EnumerateStereoisomers(Chem.MolFromSmiles(flat)):
        isomer = Chem.MolFromSmiles(Chem.MolToSmiles(isomer))  # an enumerated molecule is not a parsed one; see `_spellings`
        name = name_smiles(Chem.MolToSmiles(isomer))
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(isomer), (Chem.MolToSmiles(isomer), name)
