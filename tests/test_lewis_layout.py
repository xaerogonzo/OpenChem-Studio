"""Which layout the Lewis diagram is drawn from, and why.

The scoring is pure, so almost all of this needs no RDKit and no window.
The two tests that build real molecules are the ones asserting the
chooser really picks a different engine on a case each one wins -- which
is a different claim from the scoring being right.
"""

from __future__ import annotations

import math

import pytest

from openchem.chem.lewis_layout import (
    LayoutScore,
    count_crossings,
    crowding,
    score,
)

#: A unit square: four atoms, four bonds, no crossings.
SQUARE = {0: (0.0, 0.0), 1: (1.0, 0.0), 2: (1.0, 1.0), 3: (0.0, 1.0)}
SQUARE_BONDS = [(0, 1), (1, 2), (2, 3), (3, 0)]


# --- the crossing semantics, one row of the contract at a time -------------


def test_a_plain_ring_crosses_itself_nowhere():
    assert count_crossings(SQUARE, SQUARE_BONDS) == 0


def test_two_diagonals_cross_once():
    positions = dict(SQUARE)
    assert count_crossings(positions, [(0, 2), (1, 3)]) == 1


def test_bonds_sharing_an_atom_are_an_ANGLE_and_never_a_crossing():
    """They meet at an atom by construction. Counting that would score
    every molecule by its bond count."""
    positions = {0: (0.0, 0.0), 1: (1.0, 0.0), 2: (0.0, 1.0)}

    assert count_crossings(positions, [(0, 1), (0, 2)]) == 0


def test_two_bonds_leaving_one_atom_in_OPPOSITE_directions_are_not_an_overlap():
    """A 180-degree angle, which is ordinary -- every linear fragment has
    one. They are collinear by construction, so an overlap test that did
    not exempt a shared endpoint would flag every alkyne and every CO2.
    """
    positions = {0: (-1.0, 0.0), 1: (0.0, 0.0), 2: (1.0, 0.0)}

    assert count_crossings(positions, [(0, 1), (1, 2)]) == 0


def test_two_bonds_drawn_on_top_of_each_other_are_counted():
    """Worse than a crossing, not better. A version that ignored collinear
    overlap would score the most degenerate layout best.

    **CAUGHT BY THE ATOM PASS, NOT THE SEGMENT PASS**, which a mutation
    established rather than review: deleting the collinear branch from
    `_segments_cross` changed no test and no benchmark number. Two
    collinear segments that overlap must put an endpoint of one strictly
    inside the other, and that is an atom at distance zero from it.
    """
    positions = {0: (0.0, 0.0), 1: (2.0, 0.0), 2: (0.5, 0.0), 3: (1.5, 0.0)}

    assert count_crossings(positions, [(0, 1), (2, 3)]) > 0


def test_an_overlap_is_counted_ONCE_per_atom_and_not_twice():
    """The reason the redundant branch was removed rather than kept.

    With both mechanisms live, every overlap scored twice -- once as a
    segment intersection and once per buried atom -- so a layout with one
    overlap was ranked as though it had several. Two buried atoms, two
    counts, and no third from the segment pass.
    """
    positions = {0: (0.0, 0.0), 1: (2.0, 0.0), 2: (0.5, 0.0), 3: (1.5, 0.0)}

    assert count_crossings(positions, [(0, 1), (2, 3)]) == 2


def test_a_bond_passing_through_an_unrelated_atom_is_counted():
    """A real defect, and invisible to a segment-versus-segment test."""
    positions = {0: (0.0, 0.0), 1: (2.0, 0.0), 2: (1.0, 0.0), 3: (1.0, 2.0)}

    assert count_crossings(positions, [(0, 1), (2, 3)]) > 0


def test_a_bond_does_not_pass_through_its_OWN_endpoints():
    """**THE ROW THAT WOULD OTHERWISE MAKE EVERY BOND A DEFECT.** Atom
    intersections are evaluated only against atoms that are not an
    endpoint of the segment being tested -- without that, every bond in
    every molecule "passes through" both of its own atoms."""
    positions = {0: (0.0, 0.0), 1: (1.0, 0.0)}

    assert count_crossings(positions, [(0, 1)]) == 0


def test_a_double_bond_is_one_segment_not_two():
    """The layout has one line per BOND whatever its order, so a repeated
    pair must not be counted twice -- and must not be read as two bonds
    lying on top of each other, which is the degenerate case above."""
    assert count_crossings(SQUARE, SQUARE_BONDS + [(0, 1)]) == count_crossings(
        SQUARE, SQUARE_BONDS
    )


# --- the score is a tuple, and its field order was chosen elsewhere ---------


def test_the_score_is_compared_lexicographically_and_never_summed():
    """`lewis_svg._lone_pair_slots` already established this: scoring
    clearance and spread as a SUM put water's lone pairs between its two
    hydrogens. Inventing a weight between crossings and clearance would
    be the same mistake in a new place."""
    roomy_but_crossed = LayoutScore(1.0, -5)
    cramped_but_clean = LayoutScore(0.2, 0)

    assert roomy_but_crossed > cramped_but_clean


def test_clearance_leads_and_crossings_only_break_a_tie():
    """**THE ORDERING THE HELD-OUT EXPERIMENT CHOSE**, and not the
    intuitive one. `benchmarks/lewis_layout/choose.py` fixed it on a
    design half (B 21/21 not worse against A's 19/21) and evaluated the
    frozen choice on the other half. Putting crossings first makes two of
    twenty-one design molecules WORSE on clearance to remove a crossing.
    """
    assert LayoutScore(0.5, -9) > LayoutScore(0.4, 0), "clearance must lead"
    assert LayoutScore(0.5, 0) > LayoutScore(0.5, -1), "crossings break the tie"


def test_more_crossings_score_worse_at_equal_clearance():
    assert score(SQUARE, SQUARE_BONDS) > score(SQUARE, [(0, 2), (1, 3)])


def test_crowding_ignores_bonded_neighbours():
    """Two bonded atoms are SUPPOSED to be a bond length apart; counting
    them would make every molecule maximally crowded."""
    assert crowding(SQUARE, SQUARE_BONDS) == pytest.approx(math.sqrt(2.0))


# --- the chooser, against real molecules -----------------------------------

MORPHINE = "CN1CC[C@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@H]3[C@H]1C5"
CHOLESTEROL = "CC(C)CCC[C@@H](C)[C@H]1CC[C@H]2[C@@H]3CC=C4C[C@@H](O)CC[C@]4(C)[C@H]3CC[C@]12C"


def _built(smiles: str):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from openchem.chem.lewis_builder import build

    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return build(Chem.MolToMolBlock(mol))


def test_the_chooser_takes_coordgen_where_coordgen_wins():
    """Cholesterol: 0.036 under Compute2DCoords, 0.565 under CoordGen --
    a sixteenfold difference, and the case that motivated looking."""
    provenance = _built(CHOLESTEROL).provenance

    assert provenance.layout_engine == "coordgen"
    assert provenance.layout_crowding > 0.4


def test_the_chooser_keeps_compute2dcoords_where_coordgen_LOSES():
    """**THE TEST THAT STOPS SOMEBODY "SIMPLIFYING" THIS TO ALWAYS-COORDGEN.**

    Morphine is essentially the structure this work was reported for, and
    CoordGen draws it at 0.186 against Compute2DCoords' 0.303. Swapping
    the engine outright -- the obvious change -- would have made the
    reported case worse.
    """
    provenance = _built(MORPHINE).provenance

    assert provenance.layout_engine == "compute2dcoords"
    assert provenance.layout_crowding > 0.25


def test_the_score_that_decided_is_recorded_not_just_the_winner():
    """"Layout engine: coordgen" six months from now answers nothing, and
    "why did this molecule switch engines after the RDKit upgrade?" is a
    question that needs evidence rather than a name."""
    provenance = _built(CHOLESTEROL).provenance

    assert provenance.layout_crowding is not None
    assert provenance.layout_crossings is not None
    assert provenance.layout_crossings >= 0


def test_the_chooser_is_deterministic():
    """Both engines are, so the choice must be -- otherwise the diagram
    somebody exported is not the one they would get again."""
    first = _built(MORPHINE).provenance
    second = _built(MORPHINE).provenance

    assert first.layout_engine == second.layout_engine
    assert first.layout_crowding == pytest.approx(second.layout_crowding)
