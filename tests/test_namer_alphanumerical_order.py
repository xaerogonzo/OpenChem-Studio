"""P-45.5: of two parents that tie on everything before it, the name that is earlier in alphanumerical order ("bromo" before "dibromo").

BlueBookV2.pdf p. 424: "The preferred IUPAC name is the name that is earlier in alphanumerical order (see P-14.5). Alphabetic letters are considered first
in the order that they appear in the name; all Roman letters are considered before any italic letters, unless the latter are used as locants ...
Then, if still there is a choice, numerical locants are considered in the order of their appearance in the name."

It is the rule after P-45.2.3 (the lower locants in their order of citation), so its examples are exactly the ones that tie there: "in both names the locant
set is '1,2,4' and the locants appear in the name in the same order ... but 'bromo' in the PIN is earlier alphabetically than 'dibromo'". They were two names
over the spellings of each structure, chosen by the order the SMILES atoms were written in, and every pair read back to the same molecule, so nothing failed.

The book prints five examples. Three are decided here (1, 2 and 4). Example 3 is a cyclophane (`...tribenzenaheptaphane`) the engine does not name. Example 5
carries nuclides, and P-45.4 (isotopes) comes BEFORE this rule and is not applied across parents, so this rule declines a name that carries a bonding number or a
nuclide rather than decide it by the wrong criterion: example 5 stays two names, as it was, pinned as open below.
"""
from __future__ import annotations

import shutil
from types import SimpleNamespace

import pytest
from rdkit import Chem

from openchem.vendor.iupac_namer import assembly, engine, name_smiles
from tests.naming_spellings import checked_spellings

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

SEED = 20261007
SPELLINGS = 16

# (example, SMILES of the structure, the book's PIN, the name the book says is not preferred)
DECIDED = [
    ("1", "Clc1cc(CCOCc2cc(Br)c3ccccc3c2Br)c(Br)c2ccccc12",
     "1-bromo-4-chloro-2-{2-[(1,4-dibromonaphthalen-2-yl)methoxy]ethyl}naphthalene",
     "1,4-dibromo-2-{[2-(1-bromo-4-chloronaphthalen-2-yl)ethoxy]methyl}naphthalene"),
    ("2", "Clc1ccc(Nc2ccc(Br)cc2Br)c(Br)c1",
     "2-bromo-4-chloro-N-(2,4-dibromophenyl)aniline",
     "2,4-dibromo-N-(2-bromo-4-chlorophenyl)aniline"),
    ("4", "CC(F)C(F)C(CCC(=O)O)C(C(C)[N+](=O)[O-])[N+](=O)[O-]",
     "4-(1,2-difluoropropyl)-5,6-dinitroheptanoic acid",
     "4-(1,2-dinitropropyl)-5,6-difluoroheptanoic acid"),
]

# Example 5 carries nuclides: P-45.4 (isotopes) decides before this rule (tests/test_namer_substituent_modification.py). Both names read back to the molecule; the book's is the
# first (the second is what the book prints, with a typo, as "not"). It was 9 and 4 of 13 spellings until naming round 29.
ISOTOPIC = (
    "[81Br]C(C(C(CC(=O)O)C(C)C(C)[81Br])[N+](=O)[O-])C",
    "5-(81Br)bromo-3-[3-(81Br)bromobutan-2-yl]-4-nitrohexanoic acid",
    "5-(81Br)bromo-3-[2-(81Br)bromo-1-nitropropyl]-4-methylhexanoic acid",
)


def _spellings(smiles: str, count: int = SPELLINGS) -> list[str]:
    return checked_spellings(smiles, count, SEED)


def _names(smiles: str) -> set[str]:
    return {name_smiles(spelling) for spelling in _spellings(smiles)}


# --- the book's examples ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("example,smiles,book,other", DECIDED, ids=[f"example {e}" for e, *_rest in DECIDED])
def test_the_books_name_is_the_one_name_in_every_spelling(example, smiles, book, other):
    assert _names(smiles) == {book}


@pytest.mark.parametrize("example,smiles,book,other", DECIDED, ids=[f"example {e}" for e, *_rest in DECIDED])
def test_without_the_rule_the_same_spellings_give_two_names(monkeypatch, example, smiles, book, other):
    """The defect, kept alive: if this ever stops splitting, the fixture no longer reaches the tie and the test above proves nothing."""
    monkeypatch.setattr(engine, "_senior_by_alphanumerical_order", lambda trees: None)
    assert _names(smiles) == {book, other}


@needs_opsin
@pytest.mark.parametrize("example,smiles,book,other", DECIDED, ids=[f"example {e}" for e, *_rest in DECIDED])
def test_both_names_are_the_same_molecule(example, smiles, book, other):
    from py2opsin import py2opsin

    key = Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))
    for name in (book, other):
        back = py2opsin(name)
        assert back, name
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(back)) == key, name


def test_the_rule_is_reached_by_molecules_that_carry_no_stereo():
    for _example, smiles, _book, _other in DECIDED:
        assert not engine._carries_stereo(Chem.MolFromSmiles(smiles)), smiles


def test_example_5_carries_nuclides_and_is_the_books_name_now():
    """P-45.4 (isotopes) is applied across parents since naming round 29, so a nuclide tie is decided before this rule or by it: the book's own example 5 ("The `B` of
    the element symbol `Br` is not a factor in the alphabetization") was two names, 9 and 4 of 13, while this rule declined a name with a nuclide."""
    smiles, book, other = ISOTOPIC
    assert _names(smiles) == {book}


@needs_opsin
def test_the_isotopic_names_read_back_to_the_molecule():
    from py2opsin import py2opsin

    smiles, book, other = ISOTOPIC
    for name in (book, other):
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(py2opsin(name))) == Chem.MolToInchiKey(Chem.MolFromSmiles(smiles)), name


# --- what the rule reads ------------------------------------------------------------------------------------------------------

def _letters(monkeypatch, text):
    monkeypatch.setattr(assembly, "assemble_without_stereo", lambda tree: text)
    return engine._alphanumerical_letters(object())


@pytest.mark.parametrize("text,letters", [
    ("2-bromo-4-chloro-N-(2,4-dibromophenyl)aniline", "bromochlorodibromophenylaniline"),     # the multiplying prefix is a letter; N is a locant, not one
    ("2,4-dibromo-N-(2-bromo-4-chlorophenyl)aniline", "dibromobromochlorophenylaniline"),
    ("N,N'-dimethyl-N-propylbutanamide", "dimethylpropylbutanamide"),                          # primed and repeated locants
    ("2-(methylselanyl)-4a-methylnaphthalene", "methylselanylmethylnaphthalene"),              # `Se` inside a word is lowercase; `4a` is a locant
    ("3-ethyl-1H-indole", "ethylindole"),                                                       # indicated hydrogen is italic
    ("1-[(1,4-dibromonaphthalen-2-yl)methoxy]ethane", "dibromonaphthalenylmethoxyethane"),
    # hydro and dehydro prefixes are not alphabetized (P-31.1.4.2.4): the census row whose two names differ only in where `dihydro` sits
    ("7-(pyridinium-4-yl)-2,3-dihydro-7H-thiazolo[3,2-a]pyridin-2-yl", "pyridiniumylthiazolopyridinyl"),
    ("2-chloro-1,2,3,4-tetrahydronaphthalene", "chloronaphthalene"),
    ("3-hydroxy-2-didehydro-1-hydroxyhexane", "hydroxyhydroxyhexane"),                         # but `hydroxy` is a letter-bearing prefix
    ("hydrogen phosphate", "hydrogenphosphate"),
    ("Se-methyl benzenecarboselenoate", "methylbenzenecarboselenoate"),                          # a two-letter italic locant and a two-letter element symbol
])
def test_letters_are_the_names_letters_in_order(monkeypatch, text, letters):
    assert _letters(monkeypatch, text) == letters


@pytest.mark.parametrize("text", [
    "3-[2-bromo-1-(lambda5-phosphanyl)propyl]-5-chlorohexanoic acid",            # a bonding number: P-45.3 decides first
    "3-(λ5-phosphanyl)-2-(phosphanylmethyl)propanoic acid",
    "({[NAMING ERROR: No valid naming plan found for [SeH]c1ccccc1]}tellanyl)benzene",        # an embedded failure: not ordered against another one
])
def test_a_name_with_a_bonding_number_is_declined(monkeypatch, text):
    assert _letters(monkeypatch, text) is None


def test_an_unassemblable_tree_is_declined(monkeypatch):
    def boom(tree):
        raise ValueError("no")

    monkeypatch.setattr(assembly, "assemble_without_stereo", boom)
    assert engine._alphanumerical_letters(object()) is None


# --- the comparison on made-up trees: one case per plausible mutation ---------------------------------------------------------------

def _trees(monkeypatch, *rows):
    """Stand-in trees: each row is `(parent name, the letters of its name)`."""
    monkeypatch.setattr(engine, "_parent_name_alone", lambda tree: tree.parent)
    monkeypatch.setattr(engine, "_alphanumerical_letters", lambda tree: tree.letters)
    return [SimpleNamespace(parent=parent, letters=letters) for parent, letters in rows]


def test_the_earlier_letters_win_and_the_order_given_does_not_matter(monkeypatch):
    worse, better = _trees(monkeypatch, ("aniline", "dibromobromochloro"), ("aniline", "bromochlorodibromo"))
    assert engine._senior_by_alphanumerical_order([worse, better]) == [better]
    assert engine._senior_by_alphanumerical_order([better, worse]) == [better]


def test_trees_with_the_same_letters_all_survive_in_the_order_given(monkeypatch):
    a, b, c = _trees(monkeypatch, ("aniline", "bromo"), ("aniline", "bromo"), ("aniline", "dibromo"))
    assert engine._senior_by_alphanumerical_order([a, b, c]) == [a, b]
    assert engine._senior_by_alphanumerical_order([c, b, a]) == [b, a]


def test_the_first_letter_that_differs_decides_not_the_length(monkeypatch):
    """`bromo` is earlier than `bromochloro` only by being a prefix of it; `chloro` is later than both, and a shorter text is not an earlier one."""
    short, long_, other = _trees(monkeypatch, ("x", "chloro"), ("x", "bromochloro"), ("x", "bromo"))
    assert engine._senior_by_alphanumerical_order([short, long_, other]) == [other]


def test_different_parents_are_never_compared(monkeypatch):
    a, b = _trees(monkeypatch, ("aniline", "bromo"), ("benzamide", "chloro"))
    assert engine._senior_by_alphanumerical_order([a, b]) is None


def test_a_declined_name_declines_the_comparison(monkeypatch):
    a, b = _trees(monkeypatch, ("aniline", "bromo"), ("aniline", None))
    assert engine._senior_by_alphanumerical_order([a, b]) is None
    a, b = _trees(monkeypatch, ("aniline", "bromo"), (None, "chloro"))
    assert engine._senior_by_alphanumerical_order([a, b]) is None


# --- `_break_parent_tie`'s wiring: where the rule sits between P-45.2.3 and P-45.6 -----------------------------------------------
# Real molecules rarely offer three tied parents, so the plans and trees are stand-ins and the comparisons are stubbed to say what each case needs.

class _Plan:
    def __init__(self, hypothesis, tree):
        self.hypothesis, self.tree = hypothesis, tree


def _wired(monkeypatch, citation, letters, configuration=None):
    """Trees T1 (the best plan's parent), T2, T3; `letters` maps a tree to its letters, `citation` is what P-45.2.3 answers."""
    from openchem.vendor.iupac_namer.preference import TIER_SPECS, NomenclaturePreferenceKey

    key = NomenclaturePreferenceKey(tuple(0 for _ in TIER_SPECS))
    seen: list = []

    def alphabetical(trees):
        if letters is None:
            return None
        earliest = min(letters[t] for t in trees)
        return [t for t in trees if letters[t] == earliest]

    monkeypatch.setattr(engine, "SubstitutivePlan", _Plan)
    monkeypatch.setattr(engine, "_parent_hypothesis_key", lambda plan: plan.hypothesis)
    monkeypatch.setattr(engine, "_break_alphanumerical_tie", lambda plans, *args, **kwargs: plans[0][2].tree)
    monkeypatch.setattr(engine, "_senior_by_citation_locants", citation)
    monkeypatch.setattr(engine, "_senior_by_alphanumerical_order", alphabetical)
    monkeypatch.setattr(engine, "_choose_by_configuration", lambda trees: seen.append(list(trees)) or configuration)
    ranked = [(key, i, _Plan(h, f"T{n}")) for i, (h, n) in enumerate(zip("CBA", (3, 2, 1)))]
    return ranked, seen


def _tie(ranked, smiles="CC"):
    return engine._break_parent_tie(ranked, Chem.MolFromSmiles(smiles), None, None, None, None, None, 0)


def test_the_rule_reads_only_the_parents_p_45_2_3_left(monkeypatch):
    """T1 has the earliest letters but P-45.2.3 ruled it out: of T2 and T3 the earlier is T3, and T1 must not come back."""
    ranked, _seen = _wired(monkeypatch, lambda trees: ["T2", "T3"], {"T1": "a", "T2": "c", "T3": "b"})
    assert _tie(ranked) == "T3"


def test_the_rule_reads_every_parent_when_p_45_2_3_could_not_apply(monkeypatch):
    ranked, _seen = _wired(monkeypatch, lambda trees: None, {"T1": "c", "T2": "b", "T3": "a"})
    assert _tie(ranked) == "T3"


def test_the_rule_decides_when_p_45_2_3_left_everything_tied(monkeypatch):
    """The book's examples: P-45.2.3 ties (`1,4,2` against `1,4,2`) and returns every parent, and the rule is what chooses."""
    ranked, _seen = _wired(monkeypatch, lambda trees: list(trees), {"T1": "dibromo", "T2": "bromo", "T3": "dibromo"})
    assert _tie(ranked) == "T2"


def test_a_tie_the_rule_leaves_is_left_to_the_old_path(monkeypatch):
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees), {"T1": "a", "T2": "a", "T3": "a"})
    assert _tie(ranked) is None and seen == []
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees), None)                          # the rule declined
    assert _tie(ranked) is None and seen == []


def test_p_45_5_is_applied_before_the_configuration_comparison(monkeypatch):
    """The book orders it so (P-45.5 before P-45.6): when the rule leaves one parent, the descriptors are not looked at."""
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees), {"T1": "b", "T2": "a", "T3": "b"}, configuration="CONFIGURATION")
    assert _tie(ranked, "C[C@H](F)Cl") == "T2"
    assert seen == []


def test_the_configuration_comparison_only_sees_the_parents_the_rule_left(monkeypatch):
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees), {"T1": "b", "T2": "a", "T3": "a"}, configuration="T3")
    assert _tie(ranked, "C[C@H](F)Cl") == "T3"
    assert seen == [["T2", "T3"]]
    ranked, seen = _wired(monkeypatch, lambda trees: list(trees), {"T1": "b", "T2": "a", "T3": "a"}, configuration=None)
    assert _tie(ranked, "C[C@H](F)Cl") == "T2"
