"""The nesting order of enclosing marks, and the fact that it CYCLES.

P-16.5.4 (BlueBookV2.pdf p. 134), verbatim: "When multiple types of enclosing
marks are required, the nesting order is as follows: {[({[( )]})]}". Reading
that from the inside out gives ( ) then [ ] then { } then ( ) again, and so on
-- there is no deepest level.

`_choose_brackets` used to return braces for anything that already contained
braces, with the comment "already at the deepest level IUPAC defines". That
produced `{...{...}...}`, which P-16.5.4.1.5 addresses directly: when the
order "results in consecutive enclosing marks of the same level, the next
level of enclosing mark is used". Measured 2026-09-17, 8 of the 227 benchmark
names were affected.

**THE BLUE BOOK SHIPS ITS OWN TEST VECTOR FOR THIS**, as Fig. 1.3 -- a
six-step chain built up one enclosure at a time, ending in the exact case
that was wrong. Using it beats inventing examples, and step (e) is the one
that proves the cycle rather than a monotonic order.

Two exemptions matter as much as the order itself, because getting them wrong
pushes a simple prefix straight to braces:

  P-16.5.4.1.1  the parentheses of added indicated hydrogen are ignored
  P-16.5.4.1.2  square brackets that are part of a parent structure are
                ignored -- ring fusion, spiro fusion, ring assembly and von
                Baeyer names

A NOTE ON GETTING THIS WRONG TWICE. Two ad-hoc conformance checkers written
while fixing this were both subtly wrong, in opposite directions: one asked
for a monotonically increasing level (which flags the correct `(` around a
`{`), the other compared each mark with its ENCLOSING mark (which flags an
`(oxo)` several levels deep, enclosing nothing and therefore correctly a
parenthesis). The rule is about how deep a mark's CONTENTS nest, not about
what surrounds it. Both versions would have sent someone off to "fix" names
that were already right, which is why what is pinned here is the book's own
examples rather than a checker's output.
"""

from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer.assembly import (
    _choose_brackets,
    _nesting_exempt,
    _outermost_nesting_level,
)

# Fig. 1.3, transcribed from BlueBookV2.pdf p. 134. Each row is the name of a
# substituent prefix, and the mark that must enclose it at the next step.
FIG_1_3 = [
    ("4'-cyano[1,1'-biphenyl]-4-yl", "("),
    ("(4'-cyano[1,1'-biphenyl]-4-yl)oxy", "["),
    ("5-[(4'-cyano[1,1'-biphenyl]-4-yl)oxy]pentyl", "{"),
    ("{5-[(4'-cyano[1,1'-biphenyl]-4-yl)oxy]pentyl}oxy", "("),
    (
        "3-({5-[(4'-cyano[1,1'-biphenyl]-4-yl)oxy]pentyl}oxy)-3-oxopropane-1,2-diyl",
        "[",
    ),
]


@pytest.mark.parametrize(
    "inner,expected",
    FIG_1_3,
    ids=[f"fig1.3-{chr(ord('a') + i)}" for i in range(len(FIG_1_3))],
)
def test_the_blue_books_own_nesting_example(inner, expected):
    assert _choose_brackets(inner)[0] == expected


def test_the_order_cycles_back_to_parentheses():
    """Step (e) of Fig. 1.3 on its own, because it is the whole defect.

    `{5-[...]pentyl}oxy` is enclosed in PARENTHESES, not in a second pair of
    braces. Everything else in this file could pass while this one fails.
    """
    assert _choose_brackets("{5-[(a)oxy]pentyl}oxy") == ("(", ")")


def test_a_prefix_with_no_marks_starts_the_cycle():
    assert _choose_brackets("methyl") == ("(", ")")


def test_each_level_steps_to_the_next():
    assert _choose_brackets("(4-chlorophenyl)methyl") == ("[", "]")
    assert _choose_brackets("[(4-chlorophenyl)methyl]amino") == ("{", "}")


# --- the exemptions ------------------------------------------------------


@pytest.mark.parametrize(
    "inner,why",
    [
        ("bicyclo[2.2.1]heptan-1-yl", "von Baeyer"),
        ("tricyclo[8.3.0.0^{3,8}]trideca-3,5,7,10-tetraene", "von Baeyer superscript"),
        ("dibenzo[b,d]furan-1-yl", "ring fusion"),
        ("1,4-dioxaspiro[4.5]decan-8-yl", "spiro fusion"),
        ("4'-cyano[1,1'-biphenyl]-4-yl", "ring assembly"),
        ("[10]annulen-1-yl", "annulene"),
        ("3,4-dihydroquinolin-1(2H)-yl", "added indicated hydrogen"),
    ],
)
def test_a_parent_structures_own_marks_do_not_advance_the_cycle(inner, why):
    """P-16.5.4.1.1 and P-16.5.4.1.2. Counting these would push a simple
    prefix to brackets or braces for no reason -- and `1,4-dioxaspiro[4.5]`
    really did come out `N-{1,4-dioxaspiro[4.5]decan-8-yl}` before this."""
    assert _choose_brackets(inner) == ("(", ")"), why
    assert _outermost_nesting_level(inner) is None, why


def test_the_superscript_brace_is_notation_not_an_enclosing_mark():
    """Von Baeyer superscript locants render as `0^{3,8}`. Three benchmark
    names contain them, and treating those braces as marks would put the
    level at its maximum before the name has any real enclosures at all."""
    assert _outermost_nesting_level("tricyclo[8.3.0.0^{3,8}]trideca-1-ene") is None


def test_a_real_bracket_is_not_exempt():
    """Breaking the exemption, so it is not swallowing everything: a bracket
    containing an actual substituent name must still count."""
    assert not _nesting_exempt("(4-chlorophenyl)methyl", "[")
    assert _outermost_nesting_level("[(4-chlorophenyl)methyl]amino") == 1


def test_an_unbalanced_name_pushes_outward_rather_than_reusing_a_level():
    """Assembly is incremental, so this can be handed a partially built name.
    The safe direction is to treat what was opened as present: that can only
    move the mark outward, never reuse the level that is already there."""
    assert _outermost_nesting_level("[(4-chlorophenyl") is not None


# --- the defect, as names ------------------------------------------------


@pytest.mark.parametrize(
    "smiles,forbidden",
    [
        # atenolol: was 2-{4-{...}phenyl}acetamide
        ("CC(C)NCC(O)COc1ccc(CC(N)=O)cc1", "}phenyl}"),
        # a spiro amide: was N-{1,4-dioxaspiro[4.5]decan-8-yl}-...
        ("O=C(NC1CCC2(CC1)OCCO2)c1ccc(nc1)N1CCOCC1", "N-{1,4-dioxaspiro"),
    ],
)
def test_consecutive_marks_of_one_level_are_gone(smiles, forbidden):
    from openchem.vendor.iupac_namer import name_smiles

    assert forbidden not in name_smiles(smiles)
