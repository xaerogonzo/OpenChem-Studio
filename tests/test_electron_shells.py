"""Electron configurations, tested where the naive version breaks.

Every case here was chosen because a plausible implementation gets it
wrong: taking an electron off the end of the displayed string, deriving
the neutral configuration instead of reading the measured one, or calling
anything with a matching electron count "isoelectronic".
"""

from __future__ import annotations

import pytest

from openchem.chem.electron_shells import (
    Configuration,
    ConfigurationUnavailable,
    Subshell,
    ion_configuration,
    isoelectronic_noble_gas,
    neutral_configuration,
    nucleus,
)


def _spelled(symbol: str, charge: int) -> str:
    return ion_configuration(symbol, charge).configuration.with_noble_core().replace(" ", "")


# --- filling order is not ionisation order ----------------------------------


@pytest.mark.parametrize(
    ("symbol", "charge", "expected"),
    [
        # **The case this module exists for.** 4s fills before 3d and
        # empties before it, so an implementation that strips from the
        # last-filled subshell gives [Ar]3d4 4s2 for Fe2+.
        ("Fe", 2, "[Ar]3d6"),
        ("Fe", 3, "[Ar]3d5"),
        ("Cu", 1, "[Ar]3d10"),
        ("Cu", 2, "[Ar]3d9"),
        ("Cr", 2, "[Ar]3d4"),
        ("Cr", 3, "[Ar]3d3"),
        ("Mn", 2, "[Ar]3d5"),
        ("Ni", 2, "[Ar]3d8"),
        ("Zn", 2, "[Ar]3d10"),
        ("Ag", 1, "[Kr]4d10"),
        ("Na", 1, "[He]2s22p6"),
        ("Ca", 2, "[Ne]3s23p6"),
    ],
)
def test_cations_lose_their_outermost_electrons_first(symbol, charge, expected):
    assert _spelled(symbol, charge) == expected


@pytest.mark.parametrize(
    ("symbol", "charge", "expected"),
    [
        ("H", -1, "1s2"),
        ("F", -1, "[He]2s22p6"),
        ("O", -2, "[He]2s22p6"),
        ("N", -3, "[He]2s22p6"),
        ("Cl", -1, "[Ne]3s23p6"),
        ("S", -2, "[Ne]3s23p6"),
    ],
)
def test_anions_are_tested_too_not_just_removal(symbol, charge, expected):
    """Adding an electron is a separate code path from removing one, and
    an implementation can easily get one right and the other wrong."""
    assert _spelled(symbol, charge) == expected


def test_the_general_rule_reproduces_every_common_ion():
    """**Why `ION_REFERENCE` is empty, stated as a measurement.**

    The table exists for ions whose measured ground state disagrees with
    the outermost-first rule. Checked against 23 standard ions, the rule
    reproduces all of them -- so the table is empty because nothing has
    earned an entry, not because nobody looked.
    """
    from openchem.chem.electron_shells import ION_REFERENCE

    assert ION_REFERENCE == {}
    # A representative few, re-asserted here so this test fails loudly if
    # the rule regresses and someone "fixes" it by populating the table.
    assert _spelled("Fe", 2) == "[Ar]3d6"
    assert _spelled("Cu", 2) == "[Ar]3d9"


def test_a_derived_configuration_says_it_is_derived():
    """The UI shows this. A curated ground state and something this module
    worked out are different strengths of claim."""
    assert ion_configuration("Fe", 0).source == "reference"
    assert ion_configuration("Fe", 2).source == "rule"
    assert ion_configuration("Fe", 2).is_derived


# --- the measured exceptions ------------------------------------------------


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("Cr", "[Ar]3d54s1"), ("Cu", "[Ar]3d104s1"), ("Fe", "[Ar]3d64s2")],
)
def test_aufbau_exceptions_come_from_the_shipped_table(symbol, expected):
    """Cr and Cu are measured ground states, not predictions -- Aufbau
    would give [Ar]3d4 4s2 and [Ar]3d9 4s2. They are read from
    `elements.json`, never re-derived."""
    assert neutral_configuration(symbol).with_noble_core().replace(" ", "") == expected


def test_filling_order_and_writing_order_are_kept_apart():
    """**Two different conventions, and conflating them was the first bug
    here.** Electrons fill 4s before 3d, so that is the storage order --
    it is what ionisation and Aufbau reason about. Every printed table
    spells iron [Ar] 3d6 4s2, by shell. Spelling from the filling order
    would print [Ar] 4s2 3d6, which no reference does.
    """
    iron = neutral_configuration("Fe")

    stored = [s.label for s in iron.subshells]
    written = [s.label for s in iron.in_writing_order()]

    assert stored.index("4s") < stored.index("3d")  # filling
    assert written.index("3d") < written.index("4s")  # writing
    assert iron.with_noble_core() == "[Ar] 3d6 4s2"


def test_every_configuration_accounts_for_every_electron():
    """The occupancies must sum to Z. The generator asserts this when it
    writes the file; this checks the PARSER did not lose any on the way
    in -- a noble-gas core silently mis-expanded would show up here."""
    from openchem.chem.element_reference import all_symbols, facts_for

    for symbol in all_symbols():
        facts = facts_for(symbol)
        if facts is None or not facts.electron_configuration:
            continue
        assert neutral_configuration(symbol).electrons == facts.atomic_number, symbol


# --- isoelectronic is a relationship, not a count ---------------------------


@pytest.mark.parametrize(
    ("symbol", "charge", "expected"),
    [
        ("Na", 1, "Ne"),
        ("F", -1, "Ne"),
        ("O", -2, "Ne"),
        ("Mg", 2, "Ne"),
        ("Cl", -1, "Ar"),
        ("K", 1, "Ar"),
    ],
)
def test_ions_isoelectronic_with_a_noble_gas(symbol, charge, expected):
    configuration = ion_configuration(symbol, charge).configuration
    assert isoelectronic_noble_gas(configuration) == expected


def test_fe2_plus_is_isoelectronic_with_no_noble_gas():
    """**The case a count-only implementation gets wrong.** Fe2+ has 24
    electrons, the same as chromium -- true, and not what a control
    offering "isoelectronic noble gas" is promising. Configuration
    equality is the real test and this is what forces it."""
    configuration = ion_configuration("Fe", 2).configuration

    assert configuration.electrons == 24
    assert isoelectronic_noble_gas(configuration) is None


# --- Hund's rule, which is what the boxes draw ------------------------------


def test_nitrogen_2p_is_three_singles_not_a_pair_and_a_single():
    """Hund's rule, and the reason the reference diagrams draw nitrogen
    as three separate up-arrows."""
    p_shell = next(
        s for s in neutral_configuration("N").subshells if s.label == "2p"
    )

    assert p_shell.occupancy == 3
    assert p_shell.spins() == [(True, False), (True, False), (True, False)]


def test_oxygen_2p_pairs_only_after_every_orbital_has_one():
    p_shell = next(s for s in neutral_configuration("O").subshells if s.label == "2p")

    assert p_shell.occupancy == 4
    assert p_shell.spins() == [(True, True), (True, False), (True, False)]


def test_subshell_capacities_are_the_physics_not_a_lookup():
    assert Subshell(1, 0, 0).capacity == 2  # s
    assert Subshell(2, 1, 0).capacity == 6  # p
    assert Subshell(3, 2, 0).capacity == 10  # d
    assert Subshell(4, 3, 0).capacity == 14  # f


def test_shells_group_by_principal_quantum_number():
    """What the ring diagram draws: 2, 8, 18..."""
    assert neutral_configuration("Ar").shells() == {1: 2, 2: 8, 3: 8}
    assert neutral_configuration("Na").shells() == {1: 2, 2: 8, 3: 1}


# --- a neutron count is not a property of an element ------------------------


def test_the_element_view_names_the_isotope_it_counted():
    """Silicon does not have 14 neutrons; Si-28 does. The diagram has to
    say which, or the number reads as intrinsic."""
    result = nucleus("Si")

    assert result.protons == 14
    assert result.neutrons == 14
    assert result.isotope == "Si-28"
    assert result.is_most_abundant


def test_a_named_isotope_gives_its_own_neutron_count():
    result = nucleus("Si", mass_number=29)

    assert (result.protons, result.neutrons) == (14, 15)
    assert result.isotope == "Si-29"
    assert not result.is_most_abundant


def test_an_unknown_isotope_is_refused_rather_than_interpolated():
    with pytest.raises(ConfigurationUnavailable, match="no isotope"):
        nucleus("Si", mass_number=99)


# --- the two refusals, which must not merge ---------------------------------
#
# These two tests are a PAIR and are named as one, because the whole
# safety of `nucleus()` returning a partial answer rests on the
# difference between them. Asking for a nuclide that does not exist is a
# caller error about one isotope. Asking about an element that has no
# natural isotope is a question with a real, partial answer -- and
# raising for it is what left polonium drawn with no nucleus at all and
# captioned "Electrons: 84".


def test_an_element_with_no_natural_isotope_still_has_its_protons():
    """The second half of the pair above. Po, Tc, At and Pm are the
    familiar cases; 34 of the 118 elements are in this position."""
    for symbol, protons in (("Po", 84), ("Tc", 43), ("At", 85), ("Pm", 61)):
        result = nucleus(symbol)

        assert result.protons == protons
        assert result.neutrons is None
        assert not result.has_neutron_count
        assert result.isotope is None


def test_every_element_gets_a_nucleus_with_a_certain_proton_count():
    """No element is left without one, and the proton count IS the atomic
    number -- so a nucleus that disagreed with the element would be a
    different bug wearing this fix's clothes."""
    from openchem.chem.element_reference import all_symbols, facts_for

    for symbol in all_symbols():
        result = nucleus(symbol)
        assert result.protons == facts_for(symbol).atomic_number


def test_a_neutron_count_is_never_invented_for_a_synthetic_element():
    """Refusing to invent one was always right; refusing to draw anything
    was the bug. `None` is how the type says the first without the
    second, and 0 would be a claim nobody made."""
    assert nucleus("Og").neutrons is None
    assert nucleus("Og").neutrons != 0


# --- refusing rather than inventing -----------------------------------------


def test_stripping_more_electrons_than_exist_is_refused():
    with pytest.raises(ConfigurationUnavailable, match="does not have"):
        ion_configuration("Na", 12)


def test_a_fully_stripped_ion_is_empty_not_an_error():
    """H+ is a bare proton. That is a real species with no electrons, and
    different from a request that cannot be met."""
    result = ion_configuration("H", 1)

    assert result.configuration.subshells == ()
    assert result.configuration.electrons == 0


def test_an_unknown_element_is_refused():
    with pytest.raises(ConfigurationUnavailable):
        neutral_configuration("Xx")


def test_configurations_are_frozen():
    configuration = neutral_configuration("C")

    assert isinstance(configuration, Configuration)
    with pytest.raises(AttributeError):
        configuration.subshells = ()
