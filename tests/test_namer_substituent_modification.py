"""P-45.3 and P-45.4, across parents: the nonstandard bonding number and the isotopic modification of the substituents.

BlueBookV2.pdf p. 423. After P-45.2.3 (the lower locants in their order of citation) and before P-45.5 (alphanumerical order), "the preferred IUPAC name is based on the
senior parent structure that has":

* P-45.3.1 the maximum number of substituent groups with the higher bonding number, cited as prefixes and directly connected to the parent (then, a further choice,
  the higher number first: `lambda6` before `lambda4`);
* P-45.3.2 the lower locant set for those substituent groups;
* P-45.4.1 the lowest locants for isotopically modified substituent groups;
* P-45.4.2 the lowest locants for nuclides of higher atomic number; P-45.4.3 for nuclides of higher mass number.

They were "applied in turn until a decision is reached, earlier criteria having been satisfied", and until naming round 29 they were not applied across parents at all: of two
parents that tie on everything before them, the one chosen went by the order the SMILES atoms were written in. Every example of the book was two names over its spellings
(7 and 6 of 13; 8 and 5 and 11 and 2 the wrong way round for 45.4.2 and 45.4.3) and every pair read back to the same molecule, so nothing failed.

What is pinned here: the books' examples one name over 16 spellings, that the same spellings split without the rule, that both names are the one molecule, the comparison
on made-up trees (one case per plausible mutation: the order of the criteria, the direction of each, what counts as "directly connected"), and the wiring in
`_break_parent_tie` between P-45.2.3 and P-45.5. Where the engine spells a substituent differently from the book (`(1-13C)methoxy` for `(13C)methoxy`, `[(lambda4-sulfanyl)methyl]`
for `lambda4-sulfanylmethyl`) the pin is the engine's own name, which is the book's CHOICE of parent.

Not covered, measured: examples 3.1-2 and 3.2 (`2lambda5-diphosphan-1-yl`): the engine drops the lambda number of a multi-atom group, a different defect.
"""
from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest
from rdkit import Chem, rdBase

from openchem.vendor.iupac_namer import assembly, engine, name_smiles
from openchem.vendor.iupac_namer.types import Locant

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

SEED = 20261008
SPELLINGS = 16

# (example, SMILES read from the book's name by OPSIN, the name every spelling gets, the name the rival parent gives)
EXAMPLES = [
    ("P-45.3.1 ex 1: lambda5 directly on the parent, against one a bond further out", "[PH4]CC(C(=O)O)CP",
     "3-(lambda5-phosphanyl)-2-(phosphanylmethyl)propanoic acid", "3-phosphanyl-2-[(lambda5-phosphanyl)methyl]propanoic acid"),
    ("P-45.3.1 ex 3: lambda6 before lambda4", "[SH5]CC(C(=O)O)C[SH3]",
     "3-(lambda6-sulfanyl)-2-[(lambda4-sulfanyl)methyl]propanoic acid", "3-(lambda4-sulfanyl)-2-[(lambda6-sulfanyl)methyl]propanoic acid"),
    ("P-45.4.1: the isotopically modified substituent at the lower locant", "BrC(COCC(CCC)[81Br])CCC",
     "2-bromo-1-{[2-(81Br)bromopentyl]oxy}pentane", "2-(81Br)bromo-1-[(2-bromopentyl)oxy]pentane"),
    ("P-45.4.2: the nuclide of higher atomic number (18O over 13C) at the lower locant", "[13CH3]OCCNCC[18O]C",
     "2-[(1-13C)methoxy]-N-[2-(18O)methoxyethyl]ethan-1-amine", "2-(18O)methoxy-N-{2-[(1-13C)methoxy]ethyl}ethan-1-amine"),
    ("P-45.4.3: the nuclide of higher mass number (14C over 13C) at the lower locant", "C([13CH3])C(CC(CO)CC(CCC)C[14CH3])CCC",
     "4-[(2-13C)ethyl]-2-{[(1-14C)hexan-3-yl]methyl}heptan-1-ol", "4-[(2-14C)ethyl]-2-{[(1-13C)hexan-3-yl]methyl}heptan-1-ol"),
]

# P-45.5 example 5 carries nuclides. It is decided by P-45.5 itself now that the rule no longer declines a name with a nuclide; without P-45.4 it is the same name.
P455_EX5 = ("[81Br]C(C(C(CC(=O)O)C(C)C(C)[81Br])[N+](=O)[O-])C", "5-(81Br)bromo-3-[3-(81Br)bromobutan-2-yl]-4-nitrohexanoic acid")


def _spellings(smiles: str, count: int = SPELLINGS) -> list[str]:
    mol = Chem.MolFromSmiles(smiles)
    key = Chem.MolToInchiKey(mol)
    rdBase.SeedRandomNumberGenerator(SEED)
    out = [smiles]
    for _ in range(count):
        spelling = Chem.MolToSmiles(mol, doRandom=True)
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(spelling)) == key, spelling
        out.append(spelling)
    return out


def _names(smiles: str) -> set[str]:
    return {name_smiles(spelling) for spelling in _spellings(smiles)}


# --- the book's examples ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("label,smiles,chosen,rival", EXAMPLES, ids=[row[0] for row in EXAMPLES])
def test_the_book_chooses_one_name_in_every_spelling(label, smiles, chosen, rival):
    assert _names(smiles) == {chosen}


@pytest.mark.parametrize("label,smiles,chosen,rival", EXAMPLES, ids=[row[0] for row in EXAMPLES])
def test_without_the_rule_the_same_spellings_give_two_names(monkeypatch, label, smiles, chosen, rival):
    """The defect, kept alive: if this ever stops splitting, the fixture no longer reaches the tie and the test above proves nothing."""
    monkeypatch.setattr(engine, "_senior_by_substituent_modification", lambda trees: None)
    assert _names(smiles) == {chosen, rival}


@needs_opsin
@pytest.mark.parametrize("label,smiles,chosen,rival", EXAMPLES, ids=[row[0] for row in EXAMPLES])
def test_both_names_are_the_one_molecule(label, smiles, chosen, rival):
    from py2opsin import py2opsin

    key = Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))
    for name in (chosen, rival):
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == key, name


def test_p_45_5_example_5_is_the_books_name_with_and_without_p_45_4(monkeypatch):
    smiles, book = P455_EX5
    assert _names(smiles) == {book}
    monkeypatch.setattr(engine, "_senior_by_substituent_modification", lambda trees: None)
    assert _names(smiles) == {book}


def test_a_molecule_with_neither_feature_is_untouched():
    """No bonding number and no nuclide in any prefix: the key is empty for both parents and the comparison keeps them all."""
    assert _names("Clc1ccc(Nc2ccc(Br)cc2Br)c(Br)c1") == {"2-bromo-4-chloro-N-(2,4-dibromophenyl)aniline"}


# --- what counts as "directly connected" ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("tree,expected", [
    (SimpleNamespace(text="lambda5-phosphanyl"), 5),
    (SimpleNamespace(text="lambda6-sulfanyl"), 6),
    (SimpleNamespace(text="phosphanyl"), None),
    (SimpleNamespace(text="(lambda5-phosphanyl)methyl"), None),                  # the lambda number is one bond further out
    (SimpleNamespace(text="2-lambda5-phosphanylethyl"), None),
    (SimpleNamespace(named_parent=SimpleNamespace(name="lambda5-phosphane")), 5),    # a hypervalent atom with prefixes of its own: its PARENT is the atom
    (SimpleNamespace(named_parent=SimpleNamespace(name="methane")), None),
])
def test_the_bonding_number_of_a_prefix_is_that_of_the_atom_it_hangs_on(tree, expected):
    assert engine._bonding_number_of_prefix(tree) == expected


# --- the comparison on made-up trees: one case per plausible mutation ---------------------------------------------------------------

def _loc(value):
    return Locant.hetero(value) if isinstance(value, str) else Locant.numeric(value)


def _tree(*prefixes):
    """A stand-in tree whose prefixes are `(text, locants)`; a text beginning `lambdaN-` is a bare hypervalent group."""
    return SimpleNamespace(prefixes=tuple(
        SimpleNamespace(tree=SimpleNamespace(text=text), locants=tuple(_loc(v) for v in locants)) for text, locants in prefixes))


@pytest.fixture
def reading(monkeypatch):
    """`assemble` returns the stand-in text, so a prefix's nuclides are the ones its text cites."""
    monkeypatch.setattr(assembly, "assemble", lambda tree: tree.text)
    monkeypatch.setattr(engine, "_parent_name_alone", lambda tree: "same")


def test_more_directly_bonded_groups_win_before_anything_else(reading):
    two, one = _tree(("lambda5-phosphanyl", [9]), ("lambda5-phosphanyl", [8])), _tree(("lambda6-sulfanyl", [1]))
    assert engine._senior_by_substituent_modification([one, two]) == [two]          # two groups at high locants beat one at the lowest, and a lower number


def test_the_higher_bonding_number_wins_when_the_counts_are_equal(reading):
    six, four = _tree(("lambda6-sulfanyl", [5])), _tree(("lambda4-sulfanyl", [1]))
    assert engine._senior_by_substituent_modification([four, six]) == [six]


def test_the_lower_locants_of_those_groups_decide_next(reading):
    low, high = _tree(("lambda5-phosphanyl", [1]), ("phosphanyl", [9])), _tree(("lambda5-phosphanyl", [2]), ("phosphanyl", [1]))
    assert engine._senior_by_substituent_modification([high, low]) == [low]


def test_bonding_numbers_are_decided_before_isotopes(reading):
    bonded_late_isotope_late = _tree(("lambda5-phosphanyl", [9]), ("(13C)methyl", [8]))
    isotope_early_no_bond = _tree(("(13C)methyl", [1]), ("phosphanyl", [9]))
    assert engine._senior_by_substituent_modification([isotope_early_no_bond, bonded_late_isotope_late]) == [bonded_late_isotope_late]


def test_the_lowest_locant_of_an_isotopically_modified_substituent_decides(reading):
    early, late = _tree(("(81Br)bromo", [1]), ("bromo", [2])), _tree(("(81Br)bromo", [2]), ("bromo", [1]))
    assert engine._senior_by_substituent_modification([late, early]) == [early]


def test_a_nuclide_anywhere_in_a_prefix_makes_it_modified(reading):
    """The book's own example 4.1: the label is inside `[2-(81Br)bromopentyl]oxy` and not on its first atom."""
    deep, bare = _tree(("(2-(81Br)bromopentyl)oxy", [1])), _tree(("(2-bromopentyl)oxy", [1]), ("(81Br)bromo", [2]))
    assert engine._senior_by_substituent_modification([bare, deep]) == [deep]


def test_all_the_isotopic_locants_are_compared_before_the_nuclides_are_ranked(reading):
    """P-45.4.1 first: the lowest locants of the modified substituents as a set. Here A has 1,3 and B has 2,2, so A wins by 4.1 although B puts the oxygen at the lower locant,
    which is all that P-45.4.2 would look at."""
    a, b = _tree(("(13C)methyl", [1]), ("(18O)methoxy", [3])), _tree(("(13C)methyl", [2]), ("(18O)methoxy", [2]))
    assert engine._senior_by_substituent_modification([b, a]) == [a]


def test_the_higher_atomic_number_gets_the_lower_locant_when_the_locants_tie(reading):
    oxygen_first, carbon_first = _tree(("(18O)methoxy", [1]), ("(13C)methoxy", [2])), _tree(("(13C)methoxy", [1]), ("(18O)methoxy", [2]))
    assert engine._senior_by_substituent_modification([carbon_first, oxygen_first]) == [oxygen_first]


def test_the_higher_mass_number_gets_the_lower_locant_when_that_ties_too(reading):
    heavy_first, light_first = _tree(("(14C)ethyl", [2]), ("(13C)ethyl", [4])), _tree(("(13C)ethyl", [2]), ("(14C)ethyl", [4]))
    assert engine._senior_by_substituent_modification([light_first, heavy_first]) == [heavy_first]


def test_atomic_number_is_decided_before_mass_number(reading):
    """Oxygen-17 against carbon-14: the higher ATOMIC number (O) takes the lower locant although its mass number is the lower one."""
    oxygen_first, carbon_first = _tree(("(17O)methoxy", [1]), ("(14C)methyl", [2])), _tree(("(14C)methyl", [1]), ("(17O)methoxy", [2]))
    assert engine._senior_by_substituent_modification([carbon_first, oxygen_first]) == [oxygen_first]


def test_an_equal_key_keeps_every_tree_in_the_order_given(reading):
    a, b = _tree(("lambda5-phosphanyl", [3])), _tree(("lambda5-phosphanyl", [3]))
    assert engine._senior_by_substituent_modification([a, b]) == [a, b]
    assert engine._senior_by_substituent_modification([_tree(("methyl", [1])), _tree(("ethyl", [2]))]) is not None


def test_different_parents_are_never_compared(monkeypatch):
    monkeypatch.setattr(assembly, "assemble", lambda tree: tree.text)
    names = iter(["propanoic acid", "butanoic acid"])
    monkeypatch.setattr(engine, "_parent_name_alone", lambda tree: next(names))
    assert engine._senior_by_substituent_modification([_tree(("(13C)methyl", [1])), _tree(("methyl", [2]))]) is None


def test_a_prefix_that_will_not_assemble_declines_the_comparison(monkeypatch):
    def boom(tree):
        raise ValueError("no")

    monkeypatch.setattr(assembly, "assemble", boom)
    monkeypatch.setattr(engine, "_parent_name_alone", lambda tree: "same")
    assert engine._senior_by_substituent_modification([_tree(("methyl", [1])), _tree(("methyl", [2]))]) is None


# --- `_break_parent_tie`'s wiring: where the rule sits between P-45.2.3 and P-45.5 ---------------------------------------------------
# Real molecules rarely offer three tied parents, so the plans and trees are stand-ins and the comparisons are stubbed to say what each case needs.

class _Plan:
    def __init__(self, hypothesis, tree):
        self.hypothesis, self.tree = hypothesis, tree


def _wired(monkeypatch, citation, modification, alphabetical):
    from openchem.vendor.iupac_namer.preference import TIER_SPECS, NomenclaturePreferenceKey

    key = NomenclaturePreferenceKey(tuple(0 for _ in TIER_SPECS))
    calls: list = []

    def record(name, fn):
        def wrapper(trees):
            calls.append((name, list(trees)))
            return fn(trees)
        return wrapper

    monkeypatch.setattr(engine, "SubstitutivePlan", _Plan)
    monkeypatch.setattr(engine, "_parent_hypothesis_key", lambda plan: plan.hypothesis)
    monkeypatch.setattr(engine, "_break_alphanumerical_tie", lambda plans, *args, **kwargs: plans[0][2].tree)
    monkeypatch.setattr(engine, "_senior_by_citation_locants", record("citation", citation))
    monkeypatch.setattr(engine, "_senior_by_substituent_modification", record("modification", modification))
    monkeypatch.setattr(engine, "_senior_by_alphanumerical_order", record("alphabetical", alphabetical))
    ranked = [(key, i, _Plan(h, f"T{n}")) for i, (h, n) in enumerate(zip("CBA", (3, 2, 1)))]
    return ranked, calls


def _tie(ranked):
    return engine._break_parent_tie(ranked, Chem.MolFromSmiles("CC"), None, None, None, None, None, 0)


def test_the_rule_reads_only_the_parents_p_45_2_3_left_and_p_45_5_reads_only_what_it_left(monkeypatch):
    ranked, calls = _wired(monkeypatch, lambda trees: ["T2", "T3"], lambda trees: ["T3"], lambda trees: list(trees))
    assert _tie(ranked) == "T3"
    assert [name for name, _trees in calls] == ["citation", "modification", "alphabetical"]
    assert calls[1][1] == ["T2", "T3"]                       # P-45.3 and P-45.4 saw what P-45.2.3 left
    assert calls[2][1] == ["T3"]                             # and P-45.5 what they left


def test_p_45_5_decides_what_p_45_3_and_p_45_4_leave_tied(monkeypatch):
    ranked, _calls = _wired(monkeypatch, lambda trees: list(trees), lambda trees: list(trees), lambda trees: ["T2"])
    assert _tie(ranked) == "T2"


def test_a_rule_that_cannot_apply_is_skipped(monkeypatch):
    ranked, _calls = _wired(monkeypatch, lambda trees: list(trees), lambda trees: None, lambda trees: ["T3"])
    assert _tie(ranked) == "T3"                              # P-45.5 still ran on all three


def test_nothing_decided_leaves_the_old_path(monkeypatch):
    ranked, _calls = _wired(monkeypatch, lambda trees: list(trees), lambda trees: list(trees), lambda trees: list(trees))
    assert _tie(ranked) is None
