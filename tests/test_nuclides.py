"""Nuclides and decay, as a domain model.

Pure: no RDKit, no Qt, no window. The corpus tests walk all 3,557 shipped
ground states, which costs under a second and is the only way to know the
grammar holds for modes no fixture happens to name.
"""

from __future__ import annotations

import pytest

from openchem.chem import decay
from openchem.chem import nuclides as N


# --- the three predicates, as one contract ---------------------------------


@pytest.mark.parametrize(
    "symbol, natural, stable, radioactive",
    [
        # Uranium separates the first two: abundant AND entirely radioactive.
        ("U", True, False, True),
        # Carbon separates the second two: stable AND radioactive.
        ("C", True, True, True),
        # Technetium has none of the first two.
        ("Tc", False, False, True),
        ("Th", True, False, True),
        ("Fe", True, True, True),
    ],
)
def test_the_three_predicates_are_three_different_questions(
    symbol, natural, stable, radioactive
):
    """**`is_radioactive = not has_natural_isotope` IS WRONG ABOUT BOTH
    URANIUM AND CARBON**, which is why these stay three functions.

    Written as a matrix so it reads as the contract it is rather than as
    scattered assertions -- and so a later tidy-up that merged any two of
    them fails here, on the row that separates them.
    """
    assert N.has_natural_isotope(symbol) is natural
    assert N.has_stable_isotope(symbol) is stable
    assert N.has_radioactive_isotope(symbol) is radioactive


def test_particle_unstable_counts_as_radioactive_and_that_is_measured():
    """All three `p-unst` rows carry a real decay mode -- `p ?` and
    `2p ?` -- so they are unstable with no measured half-life, not
    unclassifiable. Derived from the source rather than chosen.

    **ASSERTED ON THE NUCLIDE, NOT THROUGH THE ELEMENT.** A mutation
    removing the particle-unstable clause SURVIVED an earlier version of
    this test, because every element owning one of those three rows also
    owns several ordinary radioactive nuclides -- so `has_radioactive_
    isotope("Li")` answers True either way and could not see it.
    """
    for z, a in ((3, 3), (4, 5), (5, 6)):
        nuclide = N.nuclide(z, a)
        assert nuclide.half_life.qualifier == N.PARTICLE_UNSTABLE, nuclide.name
        assert not nuclide.half_life.is_known, nuclide.name
        assert nuclide.decays, nuclide.name
        assert N.is_radioactive(nuclide) is True, nuclide.name


def test_particle_unstable_alone_is_enough_to_be_radioactive():
    """**THE CASE THAT DISTINGUISHES THE CLAUSE, and it took a surviving
    mutation to find where it lives.**

    All three shipped `p-unst` rows also carry a decay mode, so removing
    the particle-unstable clause changes none of them -- the next clause
    answers True anyway. The clause is not redundant as a CLAIM, though:
    "particle unstable" is itself evidence of instability, whatever the
    mode list says. So it is asserted on the one construction that can
    tell the two apart, which the shipped table happens not to contain.
    """
    bare = N.Nuclide(
        z=3,
        a=3,
        symbol="Li",
        half_life=N.HalfLife(seconds=None, qualifier=N.PARTICLE_UNSTABLE),
        decays=(),
    )

    assert N.is_radioactive(bare) is True


def test_a_stable_nuclide_is_not_radioactive():
    """The control for the predicates above."""
    assert N.is_radioactive(N.nuclide(6, 12)) is False
    assert N.is_radioactive(N.nuclide(92, 238)) is True


def test_a_nuclide_with_no_evidence_either_way_says_so():
    """`None` is the third answer, and it is not False."""
    silent = N.Nuclide(
        z=99,
        a=999,
        symbol="Es",
        half_life=N.HalfLife(seconds=None, qualifier=N.UNAVAILABLE),
        decays=(),
    )

    assert N.is_radioactive(silent) is None


# --- "longest-lived" is two questions --------------------------------------


def test_the_longest_lived_carbon_isotope_is_a_STABLE_one():
    """C-12, not C-14. One function answering both questions is how it
    ends up answering the wrong one."""
    assert N.longest_lived_isotope("C").name == "C-12"
    assert N.longest_radioactive_isotope("C").name == "C-14"


def test_for_an_element_with_no_stable_isotope_the_two_agree():
    """Polonium has no stable nuclide, so both mean Po-209 -- which is
    the case the atom drawing needs."""
    assert N.longest_lived_isotope("Po").name == "Po-209"
    assert N.longest_radioactive_isotope("Po").name == "Po-209"


def test_polonium_209_is_124_years():
    """The number the atom drawing prints."""
    half_life = N.nuclide(84, 209).half_life

    assert half_life.seconds / 3.1556952e7 == pytest.approx(124.0, rel=0.01)
    assert half_life.qualifier == N.EXACT


def test_every_element_in_the_table_has_a_radioactive_isotope(monkeypatch):
    """**A MEASURED OUTCOME, REPORTED -- not a shortcut the code may
    take.** All 118 of them, which is why `has_radioactive_isotope`'s
    False branch is unreachable through the shipped data and is asserted
    below on a constructed element instead.
    """
    answers = {sym: N.has_radioactive_isotope(sym) for sym in N._by_element()}

    assert len(answers) == 118
    assert set(answers.values()) == {True}


def test_an_element_of_only_stable_nuclides_answers_False(monkeypatch):
    """The rollup's other two answers, reached the only way they can be.

    A mutation that inverted this branch SURVIVED the corpus, because no
    real element takes it -- so it is asserted against a constructed set
    rather than left looking exercised.
    """
    only_stable = (
        N.Nuclide(1, 1, "H", N.HalfLife(seconds=None, qualifier=N.STABLE)),
    )
    monkeypatch.setattr(N, "nuclides_for", lambda symbol: only_stable)

    assert N.has_radioactive_isotope("H") is False


def test_an_element_with_nothing_recorded_answers_None(monkeypatch):
    nothing = (
        N.Nuclide(1, 1, "H", N.HalfLife(seconds=None, qualifier=N.UNAVAILABLE)),
    )
    monkeypatch.setattr(N, "nuclides_for", lambda symbol: nothing)

    assert N.has_radioactive_isotope("H") is None


def test_an_unknown_element_answers_None_rather_than_guessing():
    assert N.longest_lived_isotope("Xx") is None
    assert N.longest_radioactive_isotope("Xx") is None
    assert N.has_radioactive_isotope("Xx") is None


# --- a half-life is not a float --------------------------------------------


def test_a_qualified_half_life_says_so():
    """`>4.6 zs` and `4.6 zs` carry the same number and mean different
    things. Anything reading only the float renders the first as the
    second."""
    exact = N.HalfLife(seconds=1.0, qualifier=N.EXACT)
    bound = N.HalfLife(seconds=1.0, qualifier=N.LOWER_BOUND)

    assert not exact.is_qualified
    assert bound.is_qualified
    assert bound.seconds == exact.seconds


def test_stable_is_not_a_number():
    """Encoding it as a very large one would make every scale that reads
    this a lie at its top end."""
    stable = N.HalfLife(seconds=None, qualifier=N.STABLE)

    assert stable.is_stable
    assert not stable.is_known
    assert stable.seconds is None


def test_natural_occurrence_is_not_stability():
    """U-238 is 99.27% of natural uranium and decays."""
    uranium_238 = N.nuclide(92, 238)

    assert uranium_238.occurs_naturally
    assert not uranium_238.is_stable


# --- the decay grammar ------------------------------------------------------


@pytest.mark.parametrize(
    "mode, delta",
    [
        ("A", (-2, -4)),
        ("n", (0, -1)),
        ("2n", (0, -2)),
        ("p", (-1, -1)),
        ("B-", (1, 0)),
        ("B+", (-1, 0)),
        ("EC", (-1, 0)),
        ("2B-", (2, 0)),
        ("B-n", (1, -1)),
        ("B-3n", (1, -3)),
        ("B+p", (-2, -1)),
        ("B+2p", (-3, -2)),
        # **THE ONE THE PROTOTYPE GOT WRONG.** `pA` was tokenised as a
        # single symbol, found to be no fragment, and the whole mode
        # written off as unfollowable -- a silent dead branch on every
        # chain through it.
        ("B+pA", (-4, -5)),
        ("14C", (-6, -14)),
        ("28Mg", (-12, -28)),
    ],
)
def test_each_token_sequence_has_a_deterministic_delta(mode, delta):
    """Tested on the SEQUENCE, not only on a final daughter. A
    daughter-only test on a chain that happens not to contain `B+pA`
    would never have looked."""
    assert decay.delta_for(mode) == delta


def test_a_cluster_multiplier_is_a_mass_number_not_a_count():
    """`14C` is one carbon-14, not fourteen carbons. Read as a count it
    would give Z-84, which is not even an element."""
    assert decay.delta_for("14C") == (-6, -14)
    assert decay.delta_for("2n") == (0, -2), "but a bare multiplier IS a count"


def test_the_five_unfollowable_modes_are_recognised_but_have_no_daughter():
    """Followability is about the stoichiometry, not about being a
    cluster: single-cluster emission is perfectly derivable, and what
    cannot be followed is fission and the two combined expressions."""
    for mode in ("SF", "B-SF", "B+SF", "24Ne+26Ne", "28Mg+30Mg"):
        assert decay.is_recognised(mode), mode
        assert decay.delta_for(mode) is None, mode


def test_an_invented_mode_is_not_recognised():
    """The guard is worth what its ability to say NO is worth."""
    assert not decay.is_recognised("Q-")
    assert decay.delta_for("Q-") is None


def test_every_mode_in_the_shipped_table_is_recognised():
    """**ZERO UNRECOGNISED MODES.** A mode that neither parses nor is
    explicitly unfollowable means NUBASE introduced a notation nobody
    anticipated -- and it would otherwise become a silently dead branch
    rather than a build failure."""
    unrecognised = {
        d.mode
        for group in N._by_element().values()
        for n in group
        for d in n.decays
        if not decay.is_recognised(d.mode)
    }

    assert unrecognised == set()


# --- the trees --------------------------------------------------------------


def test_uranium_238_reaches_lead_206():
    """The textbook 4n+2 chain, through the whole branching tree."""
    tree = decay.decay_tree(N.nuclide(92, 238))

    assert (82, 206) in tree.nodes
    assert tree.nodes[(82, 206)].is_stable
    for step in ((90, 234), (91, 234), (88, 226), (86, 222), (84, 210)):
        assert step in tree.nodes, N.nuclide(*step).name


def test_every_leaf_states_a_PHYSICAL_reason():
    """Three reasons and no fourth. A `cycle` leaf would be a bug wearing
    a leaf's clothes."""
    tree = decay.decay_tree(N.nuclide(92, 238))

    reasons = set(tree.leaves().values())

    assert reasons <= {decay.STABLE, decay.UNFOLLOWABLE_MODE, decay.OFF_TABLE}
    assert decay.STABLE in reasons


def test_a_cycle_is_raised_rather_than_drawn():
    """**NOT A LEAF REASON.** A tree that reported one would terminate
    happily and satisfy every corpus assertion while a reversed daughter
    calculation hid inside it -- which is exactly the mutation the corpus
    test exists to catch.
    """
    tree = decay.DecayTree(root=(1, 1))
    tree.nodes[(1, 1)] = N.nuclide(1, 1)
    tree.nodes[(1, 2)] = N.nuclide(1, 2)
    tree.edges[(1, 1)] = [decay.DecayEdge("B-", 100.0, None, (1, 2))]
    tree.edges[(1, 2)] = [decay.DecayEdge("B+", 100.0, None, (1, 1))]

    with pytest.raises(decay.DecayGraphError, match="cycle"):
        decay._refuse_cycles(tree)


def test_no_shipped_nuclide_produces_a_cycle():
    """Which is what makes the error above unreachable in practice, and
    the assertion a real claim rather than a hope."""
    for group in N._by_element().values():
        for start in group:
            decay.decay_tree(start)


def test_every_tree_is_structurally_sound():
    """The whole corpus, not one chain: every edge carries a classified
    mode, every followable daughter resolves to a shipped ground state,
    and every leaf states its reason."""
    for group in N._by_element().values():
        for start in group:
            tree = decay.decay_tree(start)
            assert tree.root in tree.nodes
            for key, outgoing in tree.edges.items():
                assert key in tree.nodes
                for edge in outgoing:
                    assert decay.is_recognised(edge.mode), edge.mode
                    if edge.to is None:
                        assert edge.leaf_reason
                    else:
                        assert edge.to in tree.nodes
            for reason in tree.leaves().values():
                assert reason in {decay.STABLE, decay.UNFOLLOWABLE_MODE, decay.OFF_TABLE}


def test_decay_tree_size_has_not_changed_from_the_pinned_corpus():
    """**A CHANGE DETECTOR, NOT A PHYSICAL INVARIANT** -- named so that a
    maintainer meeting it after a legitimate NUBASE update knows the
    answer is to re-measure rather than to argue with the number.

    Measured across all 3,557 shipped ground states with no threshold and
    no cap, because chains converge on stability and the trees are
    bounded by the physics: median 8, mean 15, largest 161 at Au-169. A
    cap would be a constant somebody chose over a number nobody needed.
    """
    sizes = [
        decay.decay_tree(start).size
        for group in N._by_element().values()
        for start in group
    ]

    assert max(sizes) == 161
    assert sorted(sizes)[len(sizes) // 2] == 8
    assert sum(1 for s in sizes if s > 60) == 54
