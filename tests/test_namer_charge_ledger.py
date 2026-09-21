"""The site-level charge ledger of the classifier route (naming round 8, W1), unit-tested on the function.

The D-rows (D-100m..q, aa..ac) go through whole molecules; these pin the RULES of `_balance_the_charge_ledger`, which
the D-rows cannot separate: what it converts, what it leaves alone, and when it declines.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openchem.vendor.iupac_namer.perception.charge_perception import _balance_the_charge_ledger as ledger

CARBOXYLATE = "acidic_anion_carboxylate"


def _tree(*locant_counts: int):
    return SimpleNamespace(suffix_groups=[SimpleNamespace(locants=tuple(range(n))) for n in locant_counts])


def test_a_neutral_carboxy_word_on_the_all_anion_route_becomes_the_anionic_prefix():
    """Three sites, two suffix positions, one `carboxy` prefix: the third site is written as the book writes it."""
    assert ledger("2-(4-carboxyphenyl)pentanedioate", _tree(1, 1), 3, CARBOXYLATE) == "2-(4-carboxylatophenyl)pentanedioate"


def test_the_book_prints_this_prefix():
    """pdf p. 619: `sodium hydrogen 2-(carboxylatomethyl)benzoate (PIN)`; a carboxymethyl beside a carboxylate parent."""
    assert ledger("2-(carboxymethyl)benzoate", _tree(1), 2, CARBOXYLATE) == "2-(carboxylatomethyl)benzoate"


def test_a_multiplied_prefix_counts_each_group_and_keeps_its_multiplier():
    assert ledger("2,3-dicarboxybutanedioate", _tree(1, 1), 4, CARBOXYLATE) == "2,3-dicarboxylatobutanedioate"
    assert ledger("2,3-dicarboxybutanedioate", _tree(1, 1), 3, CARBOXYLATE) is None, (
        "two prefixes written for one missing site cannot balance"
    )


def test_a_name_with_no_neutral_acid_prefix_is_returned_unchanged():
    """The overwhelming case: acetate, benzene-1,4-dicarboxylate, glutarate. Nothing to convert, nothing claimed."""
    for name in ("acetate", "benzene-1,4-dicarboxylate", "pentanedioate", "2-hydroxypropane-1,2,3-tricarboxylate"):
        assert ledger(name, _tree(1), 2, CARBOXYLATE) == name


def test_a_retained_parent_has_no_suffix_groups_to_count_and_is_still_repaired():
    """`benzoate` and `acetate` are retained: the tree has no suffix groups, so the count cannot be enforced, but a
    neutral `carboxy` prefix on the all-anion route is still a deprotonated site."""
    assert ledger("(carboxymethyl)benzoate", SimpleNamespace(suffix_groups=[]), 2, CARBOXYLATE) == "(carboxylatomethyl)benzoate"


def test_an_unbalanced_ledger_declines_rather_than_emitting_an_unchecked_charge():
    assert ledger("2-carboxybutanedioate", _tree(1, 1), 5, CARBOXYLATE) is None


def test_carboxylic_is_not_a_carboxy_word():
    """`carboxylic acid` and `carboxylate` contain the letters and are not prefixes."""
    assert ledger("benzene-1,4-dicarboxylate", _tree(2), 2, CARBOXYLATE) == "benzene-1,4-dicarboxylate"
    assert ledger("cyclohexane-1-carboxylic-x", _tree(1), 1, CARBOXYLATE) == "cyclohexane-1-carboxylic-x"


def test_a_site_kind_with_no_table_entry_is_left_alone():
    """Only the carboxylate class has a verified anionic prefix here; a sulfonate is recorded as open, not guessed."""
    assert ledger("4-sulfobenzoate", _tree(1), 2, "acidic_anion_olate") == "4-sulfobenzoate"


@pytest.mark.parametrize("word", ["hydroxycarboxy", "xcarboxy"])
def test_carboxy_glued_to_a_preceding_letter_is_not_a_prefix_word(word):
    """`(?<![a-z])`: the word must start a token, so a longer word that happens to end in `carboxy` is not converted."""
    assert ledger(f"2-{word}butanedioate", _tree(1, 1), 3, CARBOXYLATE) == f"2-{word}butanedioate"
