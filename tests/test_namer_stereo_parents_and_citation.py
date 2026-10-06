"""The rest of "R before S": which prefix is cited first, which parent a meso compound is named on, and the ester route.

`test_namer_stereo_locant_tie.py` settled the NUMBERING (P-14.4 (j)). Three more places chose by atom order, each found by naming the
Blue Book's own examples and the stereoisomers of a handful of skeletons over random spellings of each:

* **The order two prefixes are cited in** when they read alike but for their descriptors (P-45.6.3, BlueBookV2.pdf p. 427: "R precedes
  S"). `derive_sort_name` sets the descriptors aside, so the sort was stable on the order the tree held them in, and the R,S
  compound was `1-[(2R)-...]-3-[(2S)-...]benzene` or `3-[(2S)-...]-1-[(2R)-...]benzene` by spelling. Z precedes E the same way; the
  rank is the one (j) uses, so the order of citation and the numbering criterion that reads "the prefix cited first" cannot disagree.
  The E/Z case was worse: (g) broke the tie on name TEXT, and "E" sorts before "Z", so E took the lower locant.
* **Which half is the parent** of a meso diether or diamide (P-45.6.2, p. 426): the two halves are equal, either can be the parent,
  and the two names differ only in their descriptors: "the configurational symbols are compared and 'R' precedes 'S'". When the
  parent itself carries two R/S descriptors, P-44.4.1.12.2 (p. 413) comes first: like (RR, SS) before unlike (RS, SR).
* **The ester route** (`_break_ester_tie`): the R-first tier that was built and taken out of the P-14.4 (j) change, because it named
  a meso diester as the R,R compound. The cause was not the tier. The session cache was keyed on a SMILES that cannot write the
  descriptor a carved fragment inherits (`context_stereo_key`), so the second ester plan reused the first plan's tree and its
  descriptors. With that fixed the tier is safe, and `test_every_stereoisomer_of_these_diesters_reads_back` in the other file, which is
  what found it, covers it too.

Every name pinned here was also read back through OPSIN to the structure it came from, and every structure is checked per spelling by
InChIKey (an enumerated molecule written with `doRandom=True` can be a different stereoisomer; see `_spellings` there).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from rdkit import Chem
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers

from openchem.chem.naming_providers import opsin_available
from openchem.vendor.iupac_namer import engine, name_smiles
from openchem.vendor.iupac_namer.assembly import stereo_citation_key, without_stereo_descriptors
from openchem.vendor.iupac_namer.types import Locant, StereoCenter, StereoDescriptor

from tests.test_namer_stereo_locant_tie import _names, _spellings

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")


# --- the citation key, on made-up names ----------------------------------------------------------------------------------

def test_a_name_with_no_descriptor_has_an_empty_key():
    assert stereo_citation_key("butan-2-yl") == ()
    assert stereo_citation_key("") == ()


# M and P are in (j)'s rank table but not here: assembly's descriptor pattern reads R, S, E, Z, r and s, which are the letters a prefix
# carries today, so a helical descriptor in a prefix would not be ranked (nor stripped from the sort name) by either.
@pytest.mark.parametrize("preferred,other", [("R", "S"), ("Z", "E"), ("r", "s")])
def test_the_preferred_descriptor_is_cited_first(preferred, other):
    assert stereo_citation_key(f"(1{preferred})-x-1-yl") < stereo_citation_key(f"(1{other})-x-1-yl")


def test_z_precedes_e_although_e_sorts_first_alphabetically():
    assert "E" < "Z"
    assert stereo_citation_key("(1Z)-prop-1-en-1-yl") < stereo_citation_key("(1E)-prop-1-en-1-yl")


def test_the_first_point_of_difference_decides_in_the_order_the_name_cites():
    # (2S,3R) is cited before (2S,3S): the first letters agree, the second decides, as the book prints them in P-92.5.2.2 example 5
    assert stereo_citation_key("(2S,3R)-3-chlorobutan-2-yl") < stereo_citation_key("(2S,3S)-3-chlorobutan-2-yl")
    # and a descriptor inside a nested substituent counts, in the order it is written
    assert stereo_citation_key("[(1R)-1-[(2S)-x]ethyl]") < stereo_citation_key("[(1S)-1-[(2R)-x]ethyl]")
    # including when the FIRST group is the same and only the nested one differs
    assert stereo_citation_key("(1R)-1-[(2R)-x]ethyl") < stereo_citation_key("(1R)-1-[(2S)-x]ethyl")
    assert stereo_citation_key("(1R)-1-[(2R)-x]ethyl") == (0, 0)


def test_relative_and_racemic_words_and_stars_are_not_ranked_letters():
    assert stereo_citation_key("rel-(1R,2S)-x") == (0, 1)
    assert stereo_citation_key("(1R*,2S*)-x") == (0, 1)
    assert stereo_citation_key("rac-(1S)-x") == (1,)


def test_the_stereo_free_text_of_two_names_is_what_the_comparison_may_ignore():
    assert without_stereo_descriptors("{[(2R,3S)-3-phenoxybutan-2-yl]oxy}benzene") == without_stereo_descriptors(
        "{[(2S,3R)-3-phenoxybutan-2-yl]oxy}benzene")
    assert without_stereo_descriptors("(2R)-butan-2-ol") != without_stereo_descriptors("(2R)-butan-1-ol")


# --- the order two prefixes are cited in --------------------------------------------------------------------------------------

CITED = [
    # the Blue Book's own example under P-14.4 (j), p. 79
    ("CC[C@@H](C)c1cccc([C@@H](C)CC)c1", "1-[(2R)-butan-2-yl]-3-[(2S)-butan-2-yl]benzene"),
    ("CC[C@@H](C)c1cccc([C@H](C)CC)c1", "1,3-bis[(2R)-butan-2-yl]benzene"),
    ("CC[C@H](C)c1cccc([C@@H](C)CC)c1", "1,3-bis[(2S)-butan-2-yl]benzene"),
    # P-45.6.3, p. 427: two prefixes at one position
    ("C[C@H](Br)C1([C@@H](C)Br)CCCC1", "1-[(1R)-1-bromoethyl]-1-[(1S)-1-bromoethyl]cyclopentane"),
    # the same defect at the meta and para positions
    ("C[C@H](Cl)c1cccc([C@@H](C)Cl)c1", "1-[(1R)-1-chloroethyl]-3-[(1S)-1-chloroethyl]benzene"),
    ("C[C@H](Cl)c1ccc([C@@H](C)Cl)cc1", "1-[(1R)-1-chloroethyl]-4-[(1S)-1-chloroethyl]benzene"),
    # Z takes the lower locant over E (the name text said E first)
    ("C/C=C\\c1cccc(/C=C/C)c1", "1-[(1Z)-prop-1-en-1-yl]-3-[(1E)-prop-1-en-1-yl]benzene"),
    # P-45.6.2 examples 2 and 3 (p. 426), which already held and must keep holding
    ("CC[C@@H](C)c1ccc(Sc2ccc([C@@H](C)CC)cc2)cc1", "1-[(2R)-butan-2-yl]-4-({4-[(2S)-butan-2-yl]phenyl}sulfanyl)benzene"),
    ("C[C@H](Cl)c1ccc(Oc2ccc([C@@H](C)Cl)c([C@@H](C)Cl)c2)cc1[C@H](C)Cl",
     "4-{3,4-bis[(1R)-1-chloroethyl]phenoxy}-1,2-bis[(1S)-1-chloroethyl]benzene"),
]


@pytest.mark.parametrize("smiles,expected", CITED, ids=[expected for _s, expected in CITED])
def test_prefixes_that_differ_only_in_their_descriptors_are_cited_r_first(smiles, expected):
    assert _names(smiles) == {expected}


def test_without_the_citation_key_the_same_spellings_give_two_names(monkeypatch):
    """The defect, kept alive: with no citation key the (Z,E) pair is cited in the order the tree holds it, which is atom order.

    The key is used by `assembly` (the order the name is written in) and by `engine._alphanumerical_locant_key` (the locants (g) reads
    "for the substituent cited first"), and both go through the module attribute, so one switch takes them away together. If this ever
    stops disagreeing, the fixture no longer reaches the tie and the tests above prove nothing.
    """
    from openchem.vendor.iupac_namer import assembly

    monkeypatch.setattr(assembly, "stereo_citation_key", lambda name: ())
    assert len(_names("C/C=C\\c1cccc(/C=C/C)c1")) == 2


# --- which half is the parent --------------------------------------------------------------------------------------------------

MESO_HALVES = [
    ("C[C@H](Oc1ccccc1)[C@@H](C)Oc1ccccc1", "{[(2R,3S)-3-phenoxybutan-2-yl]oxy}benzene"),
    ("C[C@H](NC(=O)c1ccccc1)[C@@H](C)NC(=O)c1ccccc1", "N-[(2R,3S)-3-benzamidobutan-2-yl]benzamide"),
    ("C[C@H](C[C@H](C)Oc1ccccc1)Oc1ccccc1", "{[(2R,4S)-4-phenoxypentan-2-yl]oxy}benzene"),
    ("C[C@H](OCc1ccccc1)[C@@H](C)OCc1ccccc1", "({[(2R,3S)-3-(phenylmethoxy)butan-2-yl]oxy}methyl)benzene"),
]


@pytest.mark.parametrize("smiles,expected", MESO_HALVES, ids=[expected for _s, expected in MESO_HALVES])
def test_a_meso_compound_whose_halves_can_both_be_the_parent_has_one_name(smiles, expected):
    assert _names(smiles) == {expected}


# Like before unlike (P-44.4.1.12.2): the parent that carries a like pair is senior to one that carries an unlike pair. Each of these has
# halves of different kinds; R-first by name alone would have chosen the other half as the parent for the first.
LIKE_BEFORE_UNLIKE = [
    ("C[C@H](Cl)[C@H](C)O[C@H](C)[C@H](C)Cl", "(2S,3S)-2-chloro-3-{[(2R,3S)-3-chlorobutan-2-yl]oxy}butane"),
    ("C[C@H](Cl)[C@H](C)O[C@@H](C)[C@@H](C)Cl", "(2S,3S)-2-chloro-3-{[(2S,3R)-3-chlorobutan-2-yl]oxy}butane"),
    ("C[C@H](Cl)[C@H](C)O[C@H](C)[C@@H](C)Cl", "(2R,3R)-2-chloro-3-{[(2S,3S)-3-chlorobutan-2-yl]oxy}butane"),
    ("C[C@H](Cl)[C@@H](C)O[C@@H](C)[C@@H](C)Cl", "(2R,3S)-2-chloro-3-{[(2R,3S)-3-chlorobutan-2-yl]oxy}butane"),
]


@pytest.mark.parametrize("smiles,expected", LIKE_BEFORE_UNLIKE, ids=[expected for _s, expected in LIKE_BEFORE_UNLIKE])
def test_a_like_pair_in_the_parent_comes_before_an_unlike_pair(smiles, expected):
    assert _names(smiles) == {expected}


def _tree(*descriptors):
    """A stand-in for a tree: `(locant, descriptor)` rows, as `SubstitutiveTree.stereo_descriptors` holds them."""
    return SimpleNamespace(stereo_descriptors=tuple(
        StereoDescriptor(Locant.numeric(locant), descriptor, StereoCenter(i, "tetrahedral", descriptor, None))
        for i, (locant, descriptor) in enumerate(descriptors)
    ))


def test_the_parent_configuration_key_orders_like_unlike_then_r_over_s():
    key = engine._parent_configuration_key
    assert key(_tree((2, "S"), (3, "S"))) < key(_tree((2, "R"), (3, "S")))        # like beats unlike although R is first in the other
    assert key(_tree((2, "R"), (3, "R"))) < key(_tree((2, "S"), (3, "S")))        # both like: R over S
    assert key(_tree((2, "R"), (3, "S"))) < key(_tree((2, "S"), (3, "R")))        # both unlike: R over S
    assert key(_tree((1, "Z"), (3, "S"))) < key(_tree((1, "E"), (3, "R")))        # E/Z before anything else (P-44.4.1.12.1)
    assert key(_tree((3, "r"))) < key(_tree((3, "s")))
    assert key(_tree()) == ((), 0, (), ())


def test_like_and_unlike_are_judged_only_where_the_pair_is_unambiguous():
    key = engine._parent_configuration_key
    # three R/S descriptors would need the book's reference-descriptor pairing (P-92.5.2.1), which a finished name does not hold
    assert key(_tree((2, "R"), (3, "S"), (4, "R")))[1] == 0
    assert key(_tree((2, "R")))[1] == 0
    assert key(_tree((2, "R"), (3, "S")))[1] == 1


def _candidates(monkeypatch, *named):
    """Stand-in trees: each is `(name, [(locant, descriptor), ...])`, and `assemble` reads the name back off the tree."""
    from openchem.vendor.iupac_namer import assembly

    trees = []
    for name, rows in named:
        tree = _tree(*rows)
        tree.name = name
        trees.append(tree)
    monkeypatch.setattr(assembly, "assemble", lambda tree: tree.name)
    return trees


def test_names_that_differ_in_more_than_their_descriptors_are_never_chosen_between_here(monkeypatch):
    # The same descriptors would decide it (R before S), but the names are not equal once the descriptors are set aside: a choice
    # between two different names belongs to the rules that decide between names (P-45.2.3, which is not implemented), not to this.
    first, second = _candidates(monkeypatch, ("2-chloro-(2S)-butane", [(2, "S")]), ("3-chloro-(2R)-butane", [(2, "R")]))
    assert engine._choose_by_configuration([first, second]) is None


def test_equal_names_are_decided_by_the_parent_configuration_then_the_whole_name(monkeypatch):
    a, b = _candidates(monkeypatch, ("x-(2R,3S)-y-(2S,3S)", [(2, "R"), (3, "S")]), ("x-(2S,3S)-y-(2R,3S)", [(2, "S"), (3, "S")]))
    assert engine._choose_by_configuration([a, b]) is b        # the parent that carries the like pair, although R is first in the other
    c, d = _candidates(monkeypatch, ("x-(2S,3S)-y-(2S,3S)", [(2, "S"), (3, "S")]), ("x-(2R,3R)-y-(2S,3S)", [(2, "R"), (3, "R")]))
    assert engine._choose_by_configuration([c, d]) is d        # both like: R over S
    # the parents carry the same descriptors; the prefix inside the name decides, in the order the name cites it
    e, f = _candidates(monkeypatch, ("x-(2S)-y-(2S)", [(2, "S")]), ("x-(2S)-y-(2R)", [(2, "S")]))
    assert engine._choose_by_configuration([e, f]) is f


def test_nothing_is_chosen_when_nothing_tells_the_trees_apart(monkeypatch):
    a, b = _candidates(monkeypatch, ("x-(2R)-y", [(2, "R")]), ("x-(2R)-y", [(2, "R")]))
    assert engine._choose_by_configuration([a, b]) is None
    assert engine._choose_by_configuration([a]) is None


def test_a_tree_that_cannot_be_assembled_is_left_to_the_normal_loop(monkeypatch):
    from openchem.vendor.iupac_namer import assembly

    a, b = _candidates(monkeypatch, ("x-(2R)-y", [(2, "R")]), ("x-(2S)-y", [(2, "S")]))
    monkeypatch.setattr(assembly, "assemble", lambda tree: (_ for _ in ()).throw(ValueError("no name")))
    assert engine._choose_by_configuration([a, b]) is None


def test_the_ester_tier_key_counts_the_centres_it_compares():
    """The first slot is the NUMBER of descriptors the alcohol component carries, not its atoms (which are fragment-local)."""
    from openchem.vendor.iupac_namer.strategy import default_strategy

    tree = engine.name(Chem.MolFromSmiles("CC(=O)O[C@H](C)COC[C@H](C)OC(C)=O"), default_strategy())
    key = engine._ester_alcohol_stereo_key(tree)
    assert key is not None and key[0] == 1 and key[2] == (0,)    # one descriptor, the preferred one
    assert engine._ester_alcohol_stereo_key(engine.name(Chem.MolFromSmiles("CC(=O)OCC"), default_strategy())) in (None, (0, (), ()))


def test_a_descriptor_without_a_locant_is_left_alone():
    assert engine._parent_configuration_key(SimpleNamespace(stereo_descriptors=(
        StereoDescriptor(None, "R", StereoCenter(0, "tetrahedral", "R", None)),))) == ((), 0, (), ())


def test_a_molecule_with_no_stereo_never_reaches_the_cross_parent_tie():
    assert not engine._carries_stereo(Chem.MolFromSmiles("c1ccccc1OC(C)C(C)Oc1ccccc1"))
    assert engine._carries_stereo(Chem.MolFromSmiles("C[C@H](Oc1ccccc1)[C@@H](C)Oc1ccccc1"))
    assert engine._carries_stereo(Chem.MolFromSmiles("C/C=C/C"))


# --- the ester route ----------------------------------------------------------------------------------------------------------

# Diesters that round 26 leaves on the acyloxy form (a multiplicative organyl group): the choice there is which ester is principal. The
# meso compound takes R at the lowest locant of the alcohol component, the one place a stereo tier on this route could not be trusted
# until the cache key was fixed.
ESTER_ROUTE = [
    ("CC(=O)O[C@H](C)COC[C@H](C)OC(C)=O", "(2R)-1-[(2S)-2-(acetyloxy)propoxy]propan-2-yl acetate"),
    ("C[C@H](COC[C@H](C)OC(=O)c1ccccc1)OC(=O)c1ccccc1", "(2R)-1-[(2S)-2-(benzoyloxy)propoxy]propan-2-yl benzoate"),
    # the chiral pairs have nothing to choose between
    ("CC(=O)O[C@@H](C)COC[C@H](C)OC(C)=O", "(2S)-1-[(2S)-2-(acetyloxy)propoxy]propan-2-yl acetate"),
    ("CC(=O)O[C@H](C)COC[C@@H](C)OC(C)=O", "(2R)-1-[(2R)-2-(acetyloxy)propoxy]propan-2-yl acetate"),
]


@pytest.mark.parametrize("smiles,expected", ESTER_ROUTE, ids=[expected for _s, expected in ESTER_ROUTE])
def test_a_diester_on_the_acyloxy_form_is_one_name_with_r_at_the_lowest_locant(smiles, expected):
    assert _names(smiles) == {expected}


def test_the_ester_tier_is_what_makes_the_meso_diester_r_first(monkeypatch):
    """Without the tier the meso compound is whichever of the two names the canonical rank gives; with it, R-first in every order."""
    monkeypatch.setattr(engine, "_ester_alcohol_stereo_key", lambda tree: None)
    names = _names("CC(=O)O[C@H](C)COC[C@H](C)OC(C)=O")
    assert names != {"(2R)-1-[(2S)-2-(acetyloxy)propoxy]propan-2-yl acetate"}


# --- every name is still the molecule's: the guard that found the wrong tree --------------------------------------------------

FLAT = [
    "CC(=O)OC(C)COCC(C)OC(C)=O",                                  # dipropylene glycol diacetate
    "CC(=O)OC(C)COC(C)COC(C)COC(C)=O",                            # tripropylene glycol: three centres, eight isomers
    "CC(OC(=O)c1ccccc1)COCC(C)OC(=O)c1ccccc1",                    # the dibenzoate
    "CCOC(=O)C(OC(C)=O)C(OC(C)=O)C(=O)OCC",                       # diethyl tartrate diacetate: a polyol AND a polyacid
    "CC(Oc1ccccc1)C(C)Oc1ccccc1",                                 # the halves
    "CC(NC(=O)c1ccccc1)C(C)NC(=O)c1ccccc1",
    "CC(Cl)C(C)OC(C)C(C)Cl",                                      # the ether whose parent is chosen like before unlike
    "CC=Cc1cccc(C=CC)c1",                                         # E and Z prefixes
    "CC(Cl)c1cccc(C(C)Cl)c1",
]


@needs_opsin
@pytest.mark.parametrize("flat", FLAT)
def test_every_stereoisomer_is_one_name_and_reads_back(flat):
    """A tie-break only CHOOSES between trees that already exist, so it is only as good as the worst of them.

    Each stereoisomer is named over its random spellings (one name), and the name is read back through OPSIN to the structure.
    """
    from py2opsin import py2opsin

    for isomer in EnumerateStereoisomers(Chem.MolFromSmiles(flat)):
        isomer = Chem.MolFromSmiles(Chem.MolToSmiles(isomer))
        smiles = Chem.MolToSmiles(isomer)
        names = {name_smiles(spelling) for spelling in _spellings(smiles)}
        assert len(names) == 1, (smiles, names)
        (name,) = names
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(isomer), (smiles, name)


@needs_opsin
def test_the_names_pinned_above_read_back_to_their_structures():
    from py2opsin import py2opsin

    for smiles, name in CITED + MESO_HALVES + LIKE_BEFORE_UNLIKE + ESTER_ROUTE:
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), name


def test_a_meso_name_cites_r_before_s_wherever_it_cites_both():
    # a property over the meso structures above, not a pin: the first descriptor that differs between the two halves is the R
    for smiles, name in MESO_HALVES:
        letters = re.findall(r"\d([RS])[,)]", name)
        assert letters[0] == "R", name
