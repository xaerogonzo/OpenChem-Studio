"""P-45.2.3: of two parent structures that tie on everything else, the one whose prefixes have the lower locants IN THEIR ORDER OF CITATION.

BlueBookV2.pdf p. 419: "The preferred IUPAC name is based on the senior parent structure that has the lower locant or set of locants
for substituents cited as prefixes to the parent structure (other than 'hydro/dehydro' prefixes) in their order of citation in the name."
It is the criterion after P-45.2.1 (the number of prefixes) and P-45.2.2 (their locant SET), and both of those are tiers of the preference
key, so two plans that tie on the key have the same set and only the ORDER is left: `3-chloro-7-[(4-chloro-3-nitroquinolin-7-yl)sulfanyl]-4-
nitroquinoline` reads `3,7,4` and the other way round of the same molecule reads `4,7,3`.

The book prints FIFTEEN examples, five to a page on pp. 420-422, and every one is a FLAT structure, so the rule reaches achiral molecules,
which is why it is a change of its own: P-14.4 (g) compares two numberings of ONE parent (`_break_alphanumerical_tie`) and the stereo
tie-break only ran for a molecule that carried stereo. Here two PARENTS are compared, and the molecule is the same with either as the parent.
Before the rule the choice was plan order, which follows the order the SMILES atoms were written in: over 13 spellings each the book's name
came out 7, 4, 5, 8 and 10 of 13 (examples 1 to 5), 8, 7 and 8 (examples 7, 8, 10), and 8 and 6 (examples 14, 15), the other name, the one
the book says is NOT preferred, the rest. Both names of each pair are read back through OPSIN below and are the same molecule, so nothing
failed and no corpus row could see it; the name was not a function of the molecule.

Where the fifteen stand, each measured on 13 spellings (`CHANGELOG.md`, 2026-10-06, has the table; the counts before are from the tree before D-191 and D-192):

* **Decided by this rule (fourteen):** 1 to 5, 7, 8, 10 to 12, 14, 15, and 6 and 9. Both names appeared before; the book's is the only one now. (11 and 12 only since D-191 and
  D-192, xaerogonzo/OpenChem-Studio#238, made the engine name a `[PH4]` group with its lambda number and a labelled bromine with its label; 6 and 9 only since naming
  round 27, below.)
* **13** compares two numberings of one chain (`5,8,3,6` against `6,3,8,5`), the choice P-14.4 (g) makes: it was the book's name on every
  spelling before the rule too, so it cannot show the split.
* **6 and 9** needed a criterion that comes BEFORE this one: P-44.4.1.1 (p. 401), "the senior ... principal chain has the greater number of multiple bonds".
  `strategy._parent_selection_score` counted unsaturation INFIXES, so a `1,3-diene` and a `1,3,13-triene` counted one each and tied, and the `unsaturation_locants`
  tier, which is only meaningful between numberings of one parent, ranked the shorter set higher: the engine named both molecules with an ethenyl substituent
  on a diene, on every spelling. It counts the bonds the infixes name now (`tests/test_namer_multiple_bonds_parent.py`).

P-45.5, the rule after this one (the name earlier in alphanumerical order), decides the examples that tie here: `tests/test_namer_alphanumerical_order.py`.

What is pinned: the book's names exactly, over 16 spellings of each structure (every spelling checked to BE that structure by InChIKey);
that the same spellings split without the rule; that the other name is the same molecule; and the comparison itself on made-up trees, where
each case is one that a plausible mutation of the rule gets wrong (the order of the comparison, a grouped instead of a flat reading, the
letter locants, the guard that the parents are the same).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from rdkit import Chem

from openchem.chem.naming_providers import opsin_available
from openchem.vendor.iupac_namer import engine, name_smiles
from openchem.vendor.iupac_namer.types import Locant
from tests.naming_spellings import checked_spellings

needs_opsin = pytest.mark.skipif(not opsin_available(), reason="needs the managed JRE and py2opsin")

SEED = 20261006
SPELLINGS = 16

# (example, SMILES of the structure, the book's PIN, the name the book says is not preferred). Each SMILES is OPSIN's reading of the book's
# name; `test_the_other_name_is_the_same_molecule` reads the other name back to the same InChIKey.
DECIDED = [
    ("1", "O=[N+]([O-])c1cnc2cc(Sc3ccc4c([N+](=O)[O-])c(Cl)cnc4c3)ccc2c1Cl",
     "3-chloro-7-[(4-chloro-3-nitroquinolin-7-yl)sulfanyl]-4-nitroquinoline",
     "4-chloro-7-[(3-chloro-4-nitroquinolin-7-yl)sulfanyl]-3-nitroquinoline"),
    ("2", "Clc1ccc(Nc2ccc(Br)cc2Cl)c(Br)c1",
     "2-bromo-N-(4-bromo-2-chlorophenyl)-4-chloroaniline",
     "4-bromo-N-(2-bromo-4-chlorophenyl)-2-chloroaniline"),
    ("3", "CCCc1ccc2ccc(Oc3ccc4ccc(CC)c(CCC)c4c3)cc2c1CC",
     "1-ethyl-7-[(7-ethyl-8-propylnaphthalen-2-yl)oxy]-2-propylnaphthalene",
     "2-ethyl-7-[(8-ethyl-7-propylnaphthalen-2-yl)oxy]-1-propylnaphthalene"),
    ("4", "CC(F)C(Br)C(CCC(=O)O)C(F)C(C)Br",
     "5-bromo-4-(2-bromo-1-fluoropropyl)-6-fluoroheptanoic acid",
     "6-bromo-4-(1-bromo-2-fluoropropyl)-5-fluoroheptanoic acid"),
    ("5", "O=C(O)C(C(O)CBr)C(Br)CO",
     "3-bromo-2-(2-bromo-1-hydroxyethyl)-4-hydroxybutanoic acid",
     "4-bromo-2-(1-bromo-2-hydroxyethyl)-3-hydroxybutanoic acid"),
    ("7", "OCC(CCCl)CCBr",
     "2-(2-bromoethyl)-4-chlorobutan-1-ol",
     "4-bromo-2-(2-chloroethyl)butan-1-ol"),
    ("8", "ClCC(CBr)CCCC(Cl)Br",
     "1-bromo-5-(bromomethyl)-1,6-dichlorohexane",
     "1,6-dibromo-1-chloro-5-(chloromethyl)hexane"),
    ("10", "CCCNC(=O)CCc1cc(CCC(=O)NC)ccc1C",
     "N-methyl-3-{4-methyl-3-[3-oxo-3-(propylamino)propyl]phenyl}propanamide",
     "3-{2-methyl-5-[3-(methylamino)-3-oxopropyl]phenyl}-N-propylpropanamide"),
    ("14", "CCCc1ccc(CC)c2cc([Se]c3ccc4c(CC)ccc(CCC)c4c3)ccc12",
     "1-ethyl-6-[(8-ethyl-5-propylnaphthalen-2-yl)selanyl]-4-propylnaphthalene",
     "4-ethyl-6-[(5-ethyl-8-propylnaphthalen-2-yl)selanyl]-1-propylnaphthalene"),
    ("15", "ClCC(Br)C(CCC(Cl)Br)C(I)CBr",
     "1,5-dibromo-4-(2-bromo-1-iodoethyl)-1,6-dichlorohexane",
     "1,6-dibromo-4-(1-bromo-2-chloroethyl)-1-chloro-5-iodohexane"),
    # 11 and 12 could not be decided here until D-191 and D-192 (xaerogonzo/OpenChem-Studio#238) made the engine name a PH4 group with its lambda number and a labelled
    # bromine with its label: before, each came out as a different molecule. The engine writes `lambda5`, where the book prints the glyph.
    ("11", "CC(Cl)C([PH4])C(CC(=O)O)C([PH4])C(C)Br",
     "3-[2-bromo-1-(lambda5-phosphanyl)propyl]-5-chloro-4-(lambda5-phosphanyl)hexanoic acid",
     "5-bromo-3-[2-chloro-1-(lambda5-phosphanyl)propyl]-4-(lambda5-phosphanyl)hexanoic acid"),
    ("12", "CC(Cl)C([81Br])C(CC(=O)O)C([81Br])C(C)Br",
     "4-(81Br)bromo-3-[1-(81Br)bromo-2-bromopropyl]-5-chlorohexanoic acid",
     "4-(81Br)bromo-5-bromo-3-[1-(81Br)bromo-2-chloropropyl]hexanoic acid"),
    # 6 and 9 were blocked by P-44.4.1.1 (the principal chain has the greater number of multiple bonds) until naming round 27: `parent_selection` counted
    # unsaturation INFIXES, so a diene and a triene tied and the diene with an ethenyl substituent won on every spelling.
    ("6", "C=CC=CCCCC(CCC(C)C(C=C)CC)CCC(CC)C(C)C=C",
     "11-ethyl-8-(4-ethyl-3-methylhex-5-en-1-yl)-12-methyltetradeca-1,3,13-triene",
     "12-ethyl-8-(3-ethyl-4-methylhex-5-en-1-yl)-11-methyltetradeca-1,3,13-triene"),
    ("9", "C=CC=CCC(C(C)C(C=C)CC)C(CC)C(C)C=C",
     "7-ethyl-6-(3-ethylpent-4-en-2-yl)-8-methyldeca-1,3,9-triene",
     "8-ethyl-7-methyl-6-(4-methylhex-5-en-3-yl)deca-1,3,9-triene"),
]

# Example 13 was already the book's name on every spelling BEFORE the rule: the book compares two numberings of one chain, which is the choice
# P-14.4 (g) makes (`_break_alphanumerical_tie`). It cannot show the split, so it is pinned here and not in the test that needs one.
KEPT = [
    ("13", "CCCCC(CC(C)CC)C(CCC)CC(CC)CC",
     "5-butyl-8-ethyl-3-methyl-6-propyldecane",
     "6-butyl-3-ethyl-8-methyl-5-propyldecane"),
]

# P-45.6.2 example 3 (p. 426), whose second name was recorded as this gap and not a stereo one: the book prints the first, the engine used to
# print the second on 9 of 12 spellings.
P4562_EX3 = (
    "C[C@H](Cl)c1ccc(Oc2ccc([C@H](C)Cl)c([C@@H](C)Cl)c2)cc1[C@H](C)Cl",
    "1,2-bis[(1S)-1-chloroethyl]-4-{3-[(1R)-1-chloroethyl]-4-[(1S)-1-chloroethyl]phenoxy}benzene",
    "4-{3,4-bis[(1S)-1-chloroethyl]phenoxy}-2-[(1R)-1-chloroethyl]-1-[(1S)-1-chloroethyl]benzene",
)


def _spellings(smiles: str, count: int = SPELLINGS) -> list[str]:
    """Random roots and atom orders of one structure, each checked to BE that structure (a spelling of another one proves nothing)."""
    return checked_spellings(smiles, count, SEED)


def _names(smiles: str) -> set[str]:
    return {name_smiles(spelling) for spelling in _spellings(smiles)}


# --- the book's examples ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("example,smiles,book,other", DECIDED + KEPT, ids=[f"example {e}" for e, *_rest in DECIDED + KEPT])
def test_the_books_name_is_the_one_name_in_every_spelling(example, smiles, book, other):
    assert _names(smiles) == {book}


@pytest.mark.parametrize("example,smiles,book,other", DECIDED, ids=[f"example {e}" for e, *_rest in DECIDED])
def test_without_the_rule_the_same_spellings_give_two_names(monkeypatch, example, smiles, book, other):
    """The defect, kept alive: if this ever stops splitting, the fixture no longer reaches the tie and the test above proves nothing.

    The rule is one function, so one switch takes it away. What is left is plan order, which follows the order the SMILES atoms were written
    in, and both of the book's names appear: the preferred one and the one the book says is not.
    """
    monkeypatch.setattr(engine, "_senior_by_citation_locants", lambda trees: None)
    # P-45.5 (the rule after this one) also decides some of these, which it would do in this rule's place; it is switched off too, so that what is left is plan order
    monkeypatch.setattr(engine, "_senior_by_alphanumerical_order", lambda trees: None)
    assert _names(smiles) == {book, other}


@needs_opsin
@pytest.mark.parametrize("example,smiles,book,other", DECIDED + KEPT,
                         ids=[f"example {e}" for e, *_rest in DECIDED + KEPT])
def test_the_other_name_is_the_same_molecule(example, smiles, book, other):
    """Both names of each pair read back to the structure above, so the choice is between two names of ONE molecule and nothing else."""
    from py2opsin import py2opsin

    key = Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))
    for name in (book, other):
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == key, name


def test_the_rule_reaches_molecules_that_carry_no_stereo():
    """The reason it is a change of its own: the stereo tie-break was gated on `_carries_stereo`, and none of these is."""
    for _example, smiles, book, _other in DECIDED + KEPT:
        assert not engine._carries_stereo(Chem.MolFromSmiles(smiles)), smiles
        assert not re.search(r"\d[RSEZ][,)]", book), book                                    # and the book's name cites no descriptor


# --- the latent wrong tree that comparing two parents exposed ---------------------------------------------------------------

# N,N'-diacylhydrazines. Comparing the two parents (either acyl half) found that the half which came out second named the SAME nitrogen N
# where N' was meant: `N-benzoylbenzohydrazide`, which OPSIN reads as the N,N-diacyl isomer. The cause was `_role_primes`: the two hydrazide
# groups of a diacylhydrazine share one N-N, and it processed the group of the OTHER parent too, whose roles then overwrote the first's.
# Plan order had always taken the half that came out right, so no name was wrong until a rule that prefers the lower locant (N is lower than
# N') met the wrong tree. The vendored suite's D-075f, D-088a and D-117e are what caught it.
DIACYLHYDRAZINES = [
    ("O=C(NNC(=O)c1ccccc1)c1ccccc1", "N'-benzoylbenzohydrazide"),
    ("CC(=O)NNC(C)=O", "N'-acetylacetohydrazide"),
    ("CC(=O)NNC(=O)c1ccccc1", "N'-acetylbenzohydrazide"),
    # the one row of the 2000-row census that was a wrong locant (`mismatch_same_formula`): an UNSYMMETRICAL diacylhydrazine, so it was wrong on the
    # tree before the rule too, and is not only something comparing two parents exposed
    ("O=C(C=Cc1ccc(F)cc1)NNC(=O)Cc1ccccc1", "3-(4-fluorophenyl)-N'-(phenylacetyl)prop-2-enehydrazide"),
]


@pytest.mark.parametrize("smiles,expected", DIACYLHYDRAZINES, ids=[expected for _s, expected in DIACYLHYDRAZINES])
def test_a_diacylhydrazine_cites_the_terminal_nitrogen_as_n_prime(smiles, expected):
    assert _names(smiles) == {expected}


@needs_opsin
@pytest.mark.parametrize("smiles,expected", DIACYLHYDRAZINES, ids=[expected for _s, expected in DIACYLHYDRAZINES])
def test_the_diacylhydrazine_names_read_back_to_their_structures(smiles, expected):
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, expected
    assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), expected


def test_only_the_hydrazide_group_of_this_parent_sets_the_roles():
    """`CC(=O)NNC(C)=O` with the left acetyl as the parent: N3 is bonded to its acyl carbon (role N), N4 is terminal (N').

    The right acetyl's group is in the list too, because the hydrazine is shared, and it is not this parent's: its acyl carbon is neither
    in the parent nor bonded to it. Before, it ran second and set N4 to N, so the plan for this parent cited the wrong nitrogen.
    """
    mol = Chem.MolFromSmiles("CC(=O)NNC(C)=O")                        # 0 C, 1 C(=O) 2 O, 3 N, 4 N, 5 C(=O) 6 C 7 O
    left = SimpleNamespace(type="hydrazide", anchor=1, atoms=frozenset({1, 2, 3, 4}))
    right = SimpleNamespace(type="hydrazide", anchor=5, atoms=frozenset({3, 4, 5, 7}))
    assert engine._role_primes([left, right], frozenset({0, 1}), mol) == {3: "", 4: "'"}
    assert engine._role_primes([left, right], frozenset({5, 6}), mol) == {3: "'", 4: ""}
    assert engine._role_primes([left], frozenset({0, 1}), mol) == {3: "", 4: "'"}


# --- the example the stereo work recorded as this gap ------------------------------------------------------------------------

def test_p_45_6_2_example_3_second_name_is_the_books():
    smiles, book, other = P4562_EX3
    assert engine._carries_stereo(Chem.MolFromSmiles(smiles))
    assert _names(smiles) == {book}


# --- every name pinned here is the molecule's -------------------------------------------------------------------------------

@needs_opsin
def test_the_names_pinned_above_read_back_to_their_structures():
    from py2opsin import py2opsin

    for smiles, name in [(s, b) for _e, s, b, _o in DECIDED + KEPT] + [(P4562_EX3[0], P4562_EX3[1])]:
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), name


# --- what the rule reads ----------------------------------------------------------------------------------------------------

def test_hydro_prefixes_are_not_among_the_locants_it_reads():
    """The rule says "other than 'hydro/dehydro' prefixes". They are part of the parent here, which is also why two parents with different
    hydro prefixes are different parents (`_parent_name_alone`) and never compared."""
    from openchem.vendor.iupac_namer.strategy import default_strategy

    tree = engine.name(Chem.MolFromSmiles("CC1CCC(Cl)c2ccccc21"), default_strategy())
    assert [loc.label for loc in engine._citation_locants(tree)] == ["1", "4"]            # chloro 1, methyl 4: no 2, 3 of the hydro set
    assert engine._parent_name_alone(tree) == "1,2,3,4-tetrahydronaphthalene"


def test_the_parent_alone_is_named_without_prefixes_or_descriptors():
    from openchem.vendor.iupac_namer.strategy import default_strategy

    tree = engine.name(Chem.MolFromSmiles("Clc1ccc(Nc2ccc(Br)cc2Cl)c(Br)c1"), default_strategy())
    assert engine._parent_name_alone(tree) == "aniline"
    tree = engine.name(Chem.MolFromSmiles("C[C@H](Cl)[C@@H](C)O"), default_strategy())
    assert engine._parent_name_alone(tree) == "butan-2-ol"                                 # no (2R,3S)-, no 3-chloro-
    assert engine._parent_name_alone(None) is None


# --- the comparison on made-up trees: one case per plausible mutation ---------------------------------------------------------

def _loc(value):
    return Locant.hetero(value) if isinstance(value, str) else Locant.numeric(value)


def _trees(monkeypatch, *rows):
    """Stand-in trees: each row is `(parent name, locants grouped by prefix in citation order or None)`."""
    monkeypatch.setattr(engine, "_alphanumerical_locant_key", lambda tree: tree.grouped)
    monkeypatch.setattr(engine, "_parent_name_alone", lambda tree: tree.parent)
    return [SimpleNamespace(parent=parent, grouped=None if grouped is None else tuple(tuple(_loc(v) for v in group) for group in grouped))
            for parent, grouped in rows]


def test_the_lower_locants_in_the_order_of_citation_win(monkeypatch):
    worse, better = _trees(monkeypatch, ("quinoline", [(4,), (7,), (3,)]), ("quinoline", [(3,), (7,), (4,)]))     # the book's example 1
    assert engine._senior_by_citation_locants([worse, better]) == [better]
    assert engine._senior_by_citation_locants([better, worse]) == [better]              # the order the trees are given in does not matter


def test_the_first_point_of_difference_decides(monkeypatch):
    a, b = _trees(monkeypatch, ("aniline", [(2,), ("N",), (4,)]), ("aniline", [(4,), ("N",), (2,)]))              # the book's example 2
    assert engine._senior_by_citation_locants([b, a]) == [a]


def test_a_letter_locant_is_lower_than_a_number(monkeypatch):
    a, b = _trees(monkeypatch, ("propanamide", [("N",), (3,)]), ("propanamide", [(3,), ("N",)]))                  # the book's example 10
    assert engine._senior_by_citation_locants([b, a]) == [a]


def test_the_locants_are_read_as_the_name_writes_them_not_group_by_group(monkeypatch):
    """One name reads 1,4,2 and the other 1,2,3, so the second is lower, although group by group (1,) comes before (1, 2).

    Between two numberings of one parent the groups line up and the two readings agree; between two parents the prefixes are split
    differently and they need not. The book's example 8 is such a pair, but the two readings happen to agree on it, so it cannot tell
    them apart and this can.
    """
    grouped_wins, flat_wins = _trees(monkeypatch, ("hexane", [(1,), (4,), (2,)]), ("hexane", [(1, 2), (3,)]))
    assert engine._senior_by_citation_locants([grouped_wins, flat_wins]) == [flat_wins]


def test_trees_that_tie_are_all_returned_in_the_order_given(monkeypatch):
    a, b, c = _trees(monkeypatch, ("hexane", [(1,), (5,)]), ("hexane", [(1,), (5,)]), ("hexane", [(2,), (3,)]))
    assert engine._senior_by_citation_locants([c, a, b]) == [a, b]
    assert engine._senior_by_citation_locants([a, b]) == [a, b]


def test_trees_that_are_not_the_same_parent_are_never_compared(monkeypatch):
    """The key does not hold every criterion that tells two different parents apart; the locants must not stand in for one."""
    a, b = _trees(monkeypatch, ("quinoline", [(3,), (4,)]), ("isoquinoline", [(1,), (2,)]))
    assert engine._senior_by_citation_locants([a, b]) is None


def test_a_tree_with_nothing_to_read_leaves_the_choice_alone(monkeypatch):
    a, b = _trees(monkeypatch, ("butan-1-ol", None), ("butan-1-ol", [(2,)]))
    assert engine._senior_by_citation_locants([a, b]) is None
    c, d = _trees(monkeypatch, ("butan-1-ol", [(2,)]), (None, [(2,)]))                                            # a tree that will not read alone
    assert engine._senior_by_citation_locants([c, d]) is None


def test_trees_with_a_different_number_of_locants_are_not_compared(monkeypatch):
    """A shorter reading would win by length alone: a name that says less preferred to one that says more."""
    a, b = _trees(monkeypatch, ("hexane", [(1,), (2,)]), ("hexane", [(1, 2, 3)]))
    assert engine._senior_by_citation_locants([a, b]) is None


def test_the_citation_locants_flatten_the_groups_in_order(monkeypatch):
    (tree,) = _trees(monkeypatch, ("hexane", [(1,), (5,), (1, 6)]))
    assert [loc.label for loc in engine._citation_locants(tree)] == ["1", "5", "1", "6"]
    (bare,) = _trees(monkeypatch, ("hexane", None))
    assert engine._citation_locants(bare) is None


# --- `_break_parent_tie`'s own wiring, over made-up parent hypotheses -------------------------------------------------------
# Three tied parents are rare in a real molecule, and the choices below (which survivor, whether P-45.6 runs, in which order) are only reachable
# with three, so the plans and trees are stand-ins and the two comparison functions are stubbed to say exactly what each case needs.

class _Plan:
    def __init__(self, hypothesis, tree):
        self.hypothesis, self.tree = hypothesis, tree


def _wired(monkeypatch, senior, configuration=None, hypotheses=("A", "B", "C")):
    from openchem.vendor.iupac_namer.preference import TIER_SPECS, NomenclaturePreferenceKey

    key = NomenclaturePreferenceKey(tuple(0 for _ in TIER_SPECS))
    seen: list = []
    monkeypatch.setattr(engine, "SubstitutivePlan", _Plan)
    monkeypatch.setattr(engine, "_parent_hypothesis_key", lambda plan: plan.hypothesis)
    monkeypatch.setattr(engine, "_break_alphanumerical_tie", lambda plans, *args, **kwargs: plans[0][2].tree)
    monkeypatch.setattr(engine, "_senior_by_citation_locants", senior)
    monkeypatch.setattr(engine, "_choose_by_configuration", lambda trees: seen.append(list(trees)) or configuration)
    # ascending, the best plan last, as `_search_plans` returns them: the trees come out T1 (the best plan's parent), T2, T3
    ranked = [(key, i, _Plan(h, f"T{n}")) for i, (h, n) in enumerate(zip(reversed(hypotheses), range(len(hypotheses), 0, -1)))]
    return ranked, seen


def _tie(ranked, smiles="CC"):
    return engine._break_parent_tie(ranked, Chem.MolFromSmiles(smiles), None, None, None, None, None, 0)


def test_of_the_parents_left_the_first_is_the_answer(monkeypatch):
    ranked, _seen = _wired(monkeypatch, lambda trees: ["T2", "T3"])
    assert _tie(ranked) == "T2"


def test_a_parent_the_rule_chose_is_the_answer_although_it_was_not_the_best_plan(monkeypatch):
    """Falling through would name the TOP plan's parent, T1, which the rule has just ruled out."""
    ranked, _seen = _wired(monkeypatch, lambda trees: ["T3"])
    assert _tie(ranked) == "T3"


def test_when_nothing_is_ruled_out_an_achiral_molecule_is_left_to_the_old_path(monkeypatch):
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees))
    assert _tie(ranked) is None
    assert seen == []                                   # and the configuration comparison, which only stereo pays for, never ran


def test_a_rule_that_cannot_apply_leaves_the_old_path_too(monkeypatch):
    ranked, seen = _wired(monkeypatch, lambda trees: None)
    assert _tie(ranked) is None and seen == []


def test_a_stereo_molecule_goes_on_to_the_configuration_comparison(monkeypatch):
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees), configuration="CONFIGURATION")
    assert _tie(ranked, "C[C@H](F)Cl") == "CONFIGURATION"
    assert seen == [["T1", "T2", "T3"]]
    ranked, seen = _wired(monkeypatch, lambda trees: None, configuration="CONFIGURATION")
    assert _tie(ranked, "C[C@H](F)Cl") == "CONFIGURATION" and seen == [["T1", "T2", "T3"]]


def test_the_configuration_comparison_only_sees_the_parents_the_rule_left(monkeypatch):
    ranked, seen = _wired(monkeypatch, lambda trees: ["T2", "T3"], configuration="T3")
    assert _tie(ranked, "C[C@H](F)Cl") == "T3"
    assert seen == [["T2", "T3"]]
    ranked, seen = _wired(monkeypatch, lambda trees: ["T2", "T3"], configuration=None)
    assert _tie(ranked, "C[C@H](F)Cl") == "T2"          # nothing to choose on: the first of them


def test_p_45_2_3_is_applied_before_the_configuration_comparison(monkeypatch):
    """The book orders it so (P-45.2.3 before P-45.6): when the rule leaves one parent, the descriptors are not looked at."""
    ranked, seen = _wired(monkeypatch, lambda trees: ["T2"], configuration="CONFIGURATION")
    assert _tie(ranked, "C[C@H](F)Cl") == "T2"
    assert seen == []


def test_more_than_the_bound_of_tied_parents_are_left_alone(monkeypatch):
    """Made-up plans have no identity to merge on (`_plan_identity` is None for them), so every hypothesis counts as one choice: the bound is the
    most it names. It was 4 here until the choice of parent by configuration (#235) raised it to 12 to count DISTINCT choices."""
    bound = engine._PARENT_TIE_HYPOTHESES
    names = tuple(f"H{i}" for i in range(bound + 1))
    ranked, _seen = _wired(monkeypatch, lambda trees: ["T2"], hypotheses=names)
    assert _tie(ranked) is None
    ranked, _seen = _wired(monkeypatch, lambda trees: ["T2"], hypotheses=names[:bound])
    assert _tie(ranked) == "T2"                         # the bound is the most it names


def test_one_parent_is_not_a_tie(monkeypatch):
    ranked, _seen = _wired(monkeypatch, lambda trees: ["T1"], hypotheses=("A",))
    assert _tie(ranked) is None
