"""The condensed Fukui functions as arithmetic: `chem/fukui.py` knows nothing about ORCA.

Every expected number here is worked out by hand from the invented charges in the test, or taken from a real
ORCA run's printed Hirshfeld rows in `test_orca_fukui.py`; nothing is recomputed with the function under test.
"""

from __future__ import annotations

import math
import random

import pytest

from openchem.chem.fukui import HARTREE_TO_EV, condensed_fukui

#: A four-atom invented molecule whose three states each sum to the state's charge (0, +1 and -1).
NEUTRAL = [0.2, -0.4, 0.1, 0.1]
CATION = [0.5, -0.1, 0.3, 0.3]
ANION = [0.0, -0.8, -0.1, -0.1]


def test_the_four_values_are_the_finite_differences_of_the_charges():
    """f+ = q(N) - q(N+1); f- = q(N-1) - q(N); f0 is their mean; the dual descriptor their difference.

    Worked by hand: f+ = [0.2-0.0, -0.4+0.8, 0.1+0.1, 0.1+0.1]; f- = [0.5-0.2, -0.1+0.4, 0.3-0.1, 0.3-0.1].
    """
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    assert result
    assert result.f_plus == pytest.approx([0.2, 0.4, 0.2, 0.2])
    assert result.f_minus == pytest.approx([0.3, 0.3, 0.2, 0.2])
    assert result.f_zero == pytest.approx([0.25, 0.35, 0.2, 0.2])
    assert result.dual == pytest.approx([-0.1, 0.1, 0.0, 0.0])


def test_the_sign_convention_puts_an_added_electron_where_the_anion_is_more_negative():
    """The sign is the whole content of f+: an atom whose charge FALLS most on gaining an electron is the one
    a nucleophile attacks. Atom 1 goes from -0.4 to -0.8 and atom 0 from 0.2 to 0.0."""
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    assert result.f_plus.index(max(result.f_plus)) == 1
    # and f- is where the cation LOSES most negative charge: atoms 0 and 1 tie here
    assert max(result.f_minus) == pytest.approx(0.3)


def test_f_plus_and_f_minus_each_sum_to_one_and_the_dual_to_zero():
    """The sum rule, on random valid input rather than the one hand-picked example."""
    rng = random.Random(11)
    for _ in range(50):
        size = rng.randint(2, 12)
        neutral = [rng.uniform(-0.5, 0.5) for _ in range(size)]
        neutral[-1] -= sum(neutral)
        cation = [rng.uniform(-0.5, 0.5) for _ in range(size)]
        cation[-1] += 1.0 - sum(cation)
        anion = [rng.uniform(-0.5, 0.5) for _ in range(size)]
        anion[-1] += -1.0 - sum(anion)
        result = condensed_fukui(neutral, cation, anion)
        assert result
        assert sum(result.f_plus) == pytest.approx(1.0)
        assert sum(result.f_minus) == pytest.approx(1.0)
        assert sum(result.f_zero) == pytest.approx(1.0)
        assert sum(result.dual) == pytest.approx(0.0, abs=1e-12)


def test_a_charged_closed_shell_species_is_checked_against_its_own_states():
    """A carboxylate (charge -1) has a neutral of -1, a cation of 0 and an anion of -2; the same function
    differences them and the sum rule still holds."""
    neutral = [-0.1, -0.6, -0.3]
    cation = [0.3, -0.3, 0.0]
    anion = [-0.4, -0.9, -0.7]
    result = condensed_fukui(neutral, cation, anion, total_charge=-1)
    assert result
    assert sum(result.f_plus) == pytest.approx(1.0)
    assert sum(result.f_minus) == pytest.approx(1.0)


def test_the_same_tables_are_refused_for_the_wrong_total_charge():
    """The tables above sum to -1, 0 and -2. Read as a neutral molecule's, the neutral state is off by a whole
    electron and the function says which state and by how much rather than differencing it."""
    result = condensed_fukui([-0.1, -0.6, -0.3], [0.3, -0.3, 0.0], [-0.4, -0.9, -0.7], total_charge=0)
    assert not result
    assert "neutral" in result.reason and "-1.000" in result.reason


def test_a_table_of_the_wrong_state_is_refused_and_named():
    """The commonest real mistake: the cation's table taken for the anion's. Its charges sum to +1 where the
    anion's must sum to -1, and every difference after it would still look like a reasonable number."""
    result = condensed_fukui(NEUTRAL, CATION, CATION)
    assert not result
    assert "anion" in result.reason and "+1.000" in result.reason
    assert result.f_plus == () and result.f_minus == ()


@pytest.mark.parametrize("which", [0, 1, 2])
def test_each_state_is_checked(which):
    tables = [list(NEUTRAL), list(CATION), list(ANION)]
    tables[which][0] += 0.5
    result = condensed_fukui(*tables)
    assert not result
    assert ("neutral", "cation", "anion")[which] in result.reason


def test_an_empty_table_is_refused():
    result = condensed_fukui([], CATION, ANION)
    assert not result and "neutral" in result.reason


def test_states_with_different_numbers_of_atoms_are_refused():
    short = [0.2, -0.4, 0.2]
    result = condensed_fukui(short, [0.6, -0.1, 0.5], [0.0, -0.9, -0.1])
    assert result  # these three are self-consistent...
    result = condensed_fukui(NEUTRAL, [0.6, -0.1, 0.5], ANION)
    assert not result and "different numbers of atoms" in result.reason


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_a_non_finite_charge_is_refused(bad):
    neutral = list(NEUTRAL)
    neutral[1] = bad
    result = condensed_fukui(neutral, CATION, ANION)
    assert not result and "finite" in result.reason


def test_equivalent_atoms_get_equal_values():
    """Atoms 2 and 3 carry the same charge in every state, so they must come out identical, to the digit."""
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    for series in (result.f_plus, result.f_minus, result.f_zero, result.dual):
        assert series[2] == series[3]


# --- the unbound-anion caveat ---------------------------------------------------------------------------------------


def test_an_anion_above_the_neutral_is_flagged_with_its_energy():
    """E(N+1) - E(N) = +0.01 Eh = 0.2721 eV: the anion is unbound, and the caveat says by how much."""
    result = condensed_fukui(NEUTRAL, CATION, ANION, energy_neutral_hartree=-100.0, energy_anion_hartree=-99.99)
    assert result.unbound_anion_ev == pytest.approx(0.01 * HARTREE_TO_EV)
    joined = " ".join(result.caveats)
    assert "ABOVE" in joined and "0.27 eV" in joined and "negative electron affinity" in joined


def test_a_bound_anion_is_not_flagged():
    result = condensed_fukui(NEUTRAL, CATION, ANION, energy_neutral_hartree=-100.0, energy_anion_hartree=-100.01)
    assert result.unbound_anion_ev is None
    assert not any("ABOVE" in caveat for caveat in result.caveats)


def test_without_energies_nothing_is_claimed_about_the_anion():
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    assert result.unbound_anion_ev is None
    assert not any("unbound" in caveat for caveat in result.caveats)


def test_an_anion_exactly_level_with_the_neutral_counts_as_unbound():
    """An electron affinity of exactly zero is not a bound anion."""
    result = condensed_fukui(NEUTRAL, CATION, ANION, energy_neutral_hartree=-5.0, energy_anion_hartree=-5.0)
    assert result.unbound_anion_ev == 0.0


# --- negative values are kept and flagged ------------------------------------------------------------------------------


def test_a_negative_condensed_value_is_kept_and_flagged_not_clipped():
    """Atom 0 goes from charge 0.20 in the neutral to 0.10 in the cation, so f- = 0.10 - 0.20 = -0.10: its charge
    FELL on removing an electron. The number stays negative (clipping would break the sum rule) and the result
    says so."""
    neutral = [0.20, -0.20]
    cation = [0.10, 0.90]
    anion = [-0.30, -0.70]
    result = condensed_fukui(neutral, cation, anion)
    assert result
    assert result.f_minus[0] == pytest.approx(-0.10)
    assert result.has_negative
    assert sum(result.f_minus) == pytest.approx(1.0)
    assert any("negative" in caveat for caveat in result.caveats)


def test_all_positive_values_carry_no_negative_caveat():
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    assert not result.has_negative
    assert not any("negative" in caveat for caveat in result.caveats)


def test_every_result_says_which_scheme_and_that_it_is_vertical():
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    assert "Hirshfeld" in result.caveats[0] and "vertical" in result.caveats[0]


def test_the_values_are_plain_floats_in_atom_order():
    result = condensed_fukui(NEUTRAL, CATION, ANION)
    for series in (result.f_plus, result.f_minus, result.f_zero, result.dual):
        assert all(type(value) is float and math.isfinite(value) for value in series)
        assert len(series) == len(NEUTRAL)


# --- the sentences a panel shows --------------------------------------------------------------------------------------


def _dataset(property_id, values, *, unbound_ev=None):
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import PerAtomDataset

    parameters = {} if unbound_ev is None else {"unbound_anion_ev": unbound_ev}
    return PerAtomDataset(
        property_id=property_id, name=property_id, units="", method="orca", molecule_uuid="m",
        values=dict(enumerate(values)), provenance=Provenance(created_by="core", method="orca", parameters=parameters),
    )


def _water_like(unbound_ev=None):
    return [
        _dataset("orca.fukui_plus", [0.373, 0.314, 0.314], unbound_ev=unbound_ev),
        _dataset("orca.fukui_minus", [0.643, 0.179, 0.179]),
        _dataset("orca.fukui_zero", [0.508, 0.246, 0.246]),
        _dataset("orca.fukui_dual", [-0.270, 0.135, 0.135]),
    ]


def test_the_summary_names_where_each_value_is_largest():
    from openchem.chem.fukui import summary_lines

    lines = summary_lines(_water_like(), ["O", "H", "H"])
    assert lines[0] == "Fukui functions (Hirshfeld, vertical) for 3 atoms:"
    assert lines[1:] == [
        "Largest f+ (attack by a nucleophile): O (atom 1): 0.373",
        "Largest f- (attack by an electrophile): O (atom 1): 0.643",
        "Largest f0 (attack by a radical): O (atom 1): 0.508",
    ]


def test_atoms_tied_to_the_printed_digits_are_named_together_not_picked_by_index():
    from openchem.chem.fukui import summary_lines

    tied = [_dataset("orca.fukui_plus", [0.1, 0.45, 0.45])]
    assert summary_lines(tied, ["O", "H", "H"])[1] == (
        "Largest f+ (attack by a nucleophile): H (atom 2) and H (atom 3): 0.450"
    )
    three = [_dataset("orca.fukui_plus", [0.3, 0.3, 0.3, 0.1])]
    assert "H (atom 1), H (atom 2), H (atom 3): 0.300" in summary_lines(three, ["H", "H", "H", "O"])[1]


def test_the_unbound_anion_warning_is_added_only_when_the_run_recorded_one():
    from openchem.chem.fukui import summary_lines, unbound_anion_sentence

    assert summary_lines(_water_like(), ["O", "H", "H"])[-1].startswith("Largest f0")
    with_gap = summary_lines(_water_like(unbound_ev=15.98), ["O", "H", "H"])
    assert with_gap[-1] == unbound_anion_sentence(15.98)
    assert "15.98 eV ABOVE" in with_gap[-1]
    # a flag that happens to be True is not an energy
    assert summary_lines(_water_like(unbound_ev=True), ["O", "H", "H"])[-1].startswith("Largest f0")


def test_the_caveat_and_the_panel_say_the_same_thing_about_the_anion():
    """One sentence in two places is how they come apart."""
    from openchem.chem.fukui import unbound_anion_sentence

    result = condensed_fukui(NEUTRAL, CATION, ANION, energy_neutral_hartree=-1.0, energy_anion_hartree=-0.5)
    assert unbound_anion_sentence(result.unbound_anion_ev) in result.caveats


def test_other_datasets_and_empty_input_give_no_summary():
    from openchem.chem.fukui import summary_lines

    assert summary_lines([], ["O"]) == []
    assert summary_lines([_dataset("gasteiger_charge", [0.1, 0.2])], ["O", "H"]) == []
    # the dual descriptor alone has no "largest" line to give
    assert summary_lines([_dataset("orca.fukui_dual", [0.1, -0.1])], ["O", "H"]) == []


def test_an_atom_with_no_symbol_is_marked_rather_than_failing():
    from openchem.chem.fukui import summary_lines

    assert "? (atom 2)" in summary_lines([_dataset("orca.fukui_plus", [0.1, 0.9])], ["C"])[1]


def test_the_open_shell_message_names_the_multiplicity_and_the_reason():
    from openchem.chem.fukui import open_shell_message

    message = open_shell_message(3)
    assert "multiplicity 3" in message and "closed-shell" in message and "spin state" in message


def test_a_value_of_exactly_zero_is_not_a_negative_one():
    """An atom whose charge is the same in the neutral and the anion has f+ = 0.0: no density went there, which is not the
    partition compensating. Only a value BELOW zero is flagged."""
    result = condensed_fukui([0.5, -0.5], [0.8, 0.2], [0.5, -1.5])
    assert result
    assert result.f_plus == pytest.approx([0.0, 1.0])
    assert not result.has_negative
    assert not any("negative" in caveat for caveat in result.caveats)


def test_atoms_that_tie_to_the_printed_digits_are_one_site_and_atoms_a_digit_apart_are_not():
    from openchem.chem.fukui import summary_lines

    # 0.4500004 and 0.4500000 are the same six-decimal number as ORCA prints them: named together
    tied = [_dataset("orca.fukui_plus", [0.1, 0.4500004, 0.4500000])]
    assert "H (atom 2) and H (atom 3)" in summary_lines(tied, ["O", "H", "H"])[1]
    # 0.450002 is two millionths ahead: a different value, so only the larger is named
    apart = [_dataset("orca.fukui_plus", [0.1, 0.450002, 0.4500000])]
    line = summary_lines(apart, ["O", "H", "H"])[1]
    assert "H (atom 2)" in line and "H (atom 3)" not in line
