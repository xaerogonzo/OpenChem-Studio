"""An anion's Fukui functions (f- alone, or all four when its dianion is usable), and the sentences about SCF starts: the arithmetic and wording half of Fukui v2 and
of the dianion that came back after the second gate (`chem/fukui.py` with `chem/fukui_plan.py`).

Pure, like `test_fukui.py`: every number is invented or worked by hand. The ORCA half is in `test_orca_fukui_v2.py`, on real output.
"""

from __future__ import annotations

import pytest

from openchem.chem.fukui import (
    SPIN_CONTAMINATION_WARNING,
    condensed_fukui,
    f_plus_not_computed_sentence,
    failed_starts_sentence,
    start_notes,
    start_sentence,
    summary_lines,
    unbound_anion_sentence,
)
from openchem.chem.fukui_plan import (
    START_DEFAULT,
    START_HCORE,
    START_HUECKEL,
    STATE_N,
    STATE_OXIDISED,
    STATE_REDUCED,
    JobResult,
    Solution,
)
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import PerAtomDataset

#: A three-atom invented ANION (charge -1) and its N-1 state, a neutral radical (charge 0).
ANION_N = [-0.5, -0.3, -0.2]
RADICAL = [-0.1, 0.0, 0.1]


def test_an_anion_gets_f_minus_alone_and_the_other_three_are_empty():
    """Worked by hand: f- = q(N-1) - q(N) = [-0.1+0.5, 0.0+0.3, 0.1+0.2] = [0.4, 0.3, 0.3]."""
    result = condensed_fukui(ANION_N, RADICAL, None, total_charge=-1)
    assert result
    assert result.f_minus == pytest.approx([0.4, 0.3, 0.3])
    assert result.f_plus == () and result.f_zero == () and result.dual == ()
    assert not result.computes_f_plus
    assert result.reference_charge == -1


def test_f_minus_of_an_anion_sums_to_one():
    assert sum(condensed_fukui(ANION_N, RADICAL, None, total_charge=-1).f_minus) == pytest.approx(1.0)


def test_an_anions_result_says_why_it_has_no_f_plus():
    result = condensed_fukui(ANION_N, RADICAL, None, total_charge=-1)
    assert f_plus_not_computed_sentence() in result.caveats
    sentence = f_plus_not_computed_sentence()
    assert "f+, f0 and the dual descriptor were not computed" in sentence and "dianion" in sentence and "f- (where an electron comes from)" in sentence


def test_a_result_with_all_four_does_not_carry_that_sentence():
    neutral, cation, anion = [0.2, -0.4, 0.1, 0.1], [0.5, -0.1, 0.3, 0.3], [0.0, -0.8, -0.1, -0.1]
    result = condensed_fukui(neutral, cation, anion)
    assert result.computes_f_plus and f_plus_not_computed_sentence() not in result.caveats


def test_an_anion_is_never_called_unbound_because_it_has_no_n_plus_one_state_to_compare():
    """The unbound-anion caveat compares E(N+1) with E(N). With no N+1 energy there is nothing to say, whatever energy is passed for it."""
    result = condensed_fukui(ANION_N, RADICAL, None, total_charge=-1, energy_neutral_hartree=-100.0, energy_anion_hartree=-99.0)
    assert result.unbound_anion_ev is None
    assert not any("ABOVE" in caveat for caveat in result.caveats)


def test_the_states_of_an_anion_are_named_in_a_refusal():
    bad_radical = [-0.1, 0.0, 0.4]
    result = condensed_fukui(ANION_N, bad_radical, None, total_charge=-1)
    assert not result and "neutral radical (N-1 electrons) state's charges sum to +0.300" in result.reason
    bad_anion = [-0.5, -0.3, 0.1]
    result = condensed_fukui(bad_anion, RADICAL, None, total_charge=-1)
    assert not result and "anion (as given) state's charges sum to -0.700" in result.reason


def test_the_neutral_states_keep_the_words_the_first_release_used():
    neutral, cation, anion = [0.2, -0.4, 0.1, 0.1], [0.5, -0.1, 0.3, 0.3], [0.0, -0.8, -0.1, -0.1]
    bad = list(neutral)
    bad[0] += 0.5
    assert "The neutral state's charges sum to" in condensed_fukui(bad, cation, anion).reason
    bad = list(cation)
    bad[0] += 0.5
    assert "The cation (N-1 electrons) state's charges" in condensed_fukui(neutral, bad, anion).reason
    bad = list(anion)
    bad[0] += 0.5
    assert "The anion (N+1 electrons) state's charges" in condensed_fukui(neutral, cation, bad).reason


def test_two_states_of_different_sizes_are_refused_and_counted_as_two():
    result = condensed_fukui(ANION_N, [0.0, 0.0, 0.0, 0.0], None, total_charge=-1)
    assert not result and "The two states list different numbers of atoms (3 and 4)" in result.reason


def test_a_small_shortfall_of_a_negative_state_is_named_as_the_integration_with_the_diffuse_advice():
    """The N state of an anion is itself an anionic state, so the grid advice applies to it as it did to the N+1 state of a neutral molecule."""
    short = [ANION_N[0] + 0.05, *ANION_N[1:]]
    result = condensed_fukui(short, RADICAL, None, total_charge=-1)
    assert not result and "integration" in result.reason and "diffuse" in result.reason


def test_a_small_shortfall_of_a_state_that_is_not_negative_gets_no_diffuse_advice():
    radical = [RADICAL[0] + 0.05, *RADICAL[1:]]  # the neutral radical sums to +0.05
    result = condensed_fukui(ANION_N, radical, None, total_charge=-1)
    assert not result and "integration" in result.reason and "diffuse" not in result.reason


# --- spin contamination, named by what the state is ---------------------------------------------------------------------------


def test_the_oxidised_state_of_an_anion_is_a_neutral_radical_in_the_spin_sentence():
    result = condensed_fukui(ANION_N, RADICAL, None, total_charge=-1, cation_s_squared=0.97)
    assert any(caveat.startswith("The neutral radical is spin-contaminated (<S^2> = 0.97") for caveat in result.caveats)
    assert not any("The cation is spin-contaminated" in caveat for caveat in result.caveats)


def test_a_cations_n_minus_one_state_is_a_dication():
    cation_n, dication, neutral_radical = [0.4, 0.3, 0.3], [0.9, 0.6, 0.5], [0.1, 0.0, -0.1]
    result = condensed_fukui(cation_n, dication, neutral_radical, total_charge=1, cation_s_squared=0.95, anion_s_squared=0.9)
    sentences = [caveat for caveat in result.caveats if "is spin-contaminated" in caveat and caveat.startswith("The ")]
    assert [sentence.split(" is spin")[0] for sentence in sentences] == ["The dication", "The neutral radical"]


def test_the_spin_threshold_is_unchanged():
    assert SPIN_CONTAMINATION_WARNING == 0.825


# --- an anion WITH its dianion: all four numbers, from three states -------------------------------------------------------------------

#: The anion's N+1 state, a dianion (charge -2), invented: its charges sum to -2.
DIANION = [-1.0, -0.5, -0.5]


def test_an_anion_with_a_dianion_gets_all_four_worked_by_hand():
    """f+ = q(N) - q(N+1) = [-0.5+1.0, -0.3+0.5, -0.2+0.5] = [0.5, 0.2, 0.3]; f- = q(N-1) - q(N) = [0.4, 0.3, 0.3];
    f0 = (f+ + f-)/2 = [0.45, 0.25, 0.30]; dual = f+ - f- = [0.1, -0.1, 0.0]. Each of f+, f-, f0 sums to one and the dual descriptor to zero."""
    result = condensed_fukui(ANION_N, RADICAL, DIANION, total_charge=-1)
    assert result and result.computes_f_plus and result.reference_charge == -1
    assert result.f_plus == pytest.approx([0.5, 0.2, 0.3])
    assert result.f_minus == pytest.approx([0.4, 0.3, 0.3])
    assert result.f_zero == pytest.approx([0.45, 0.25, 0.30])
    assert result.dual == pytest.approx([0.1, -0.1, 0.0])
    assert sum(result.f_plus) == pytest.approx(1.0) and sum(result.f_zero) == pytest.approx(1.0) and sum(result.dual) == pytest.approx(0.0)
    assert result.f_plus_note == "" and f_plus_not_computed_sentence() not in result.caveats


def test_the_dianion_is_checked_against_a_charge_of_minus_two_and_named_a_dianion():
    bad = [-1.0, -0.5, -0.1]  # sums to -1.6
    result = condensed_fukui(ANION_N, RADICAL, bad, total_charge=-1)
    assert result and not result.computes_f_plus
    assert "The dianion (N+1 electrons) state's charges sum to -1.600 but that state has charge -2" in result.f_plus_note


def test_a_dianion_above_the_anion_is_an_unbound_state_and_the_caveat_says_so_in_those_words():
    result = condensed_fukui(ANION_N, RADICAL, DIANION, total_charge=-1, energy_neutral_hartree=-100.0, energy_anion_hartree=-99.9)
    assert result.unbound_anion_ev == pytest.approx(0.1 * 27.211386245988)
    sentence = unbound_anion_sentence(result.unbound_anion_ev, -1)
    assert sentence in result.caveats
    assert sentence.startswith("The dianion is 2.72 eV ABOVE the anion (a negative electron affinity), so it is an unbound state")
    assert "with them the dianion can have more than one SCF solution" in sentence


def test_a_dianion_below_the_anion_is_bound_and_gets_no_caveat():
    result = condensed_fukui(ANION_N, RADICAL, DIANION, total_charge=-1, energy_neutral_hartree=-100.0, energy_anion_hartree=-100.1)
    assert result.unbound_anion_ev is None and not any("ABOVE" in caveat for caveat in result.caveats)


def test_the_unbound_sentence_of_a_neutral_species_has_the_words_it_always_had():
    sentence = unbound_anion_sentence(1.5)
    assert sentence == unbound_anion_sentence(1.5, 0)
    assert sentence.startswith("The anion is 1.50 eV ABOVE the neutral (a negative electron affinity), so it is an unbound state")
    assert "with them the anion can have more than one SCF solution" in sentence


def test_an_unusable_dianion_costs_f_plus_and_nothing_else():
    """f- needs the anion and the neutral radical only. A dianion table that does not sum to its charge is dropped WITH ITS REASON and f- is given, where the same table of
    any other species refuses the result (`test_the_neutral_states_keep_the_words_the_first_release_used`)."""
    bad = [-1.0, -0.5, -0.1]
    result = condensed_fukui(ANION_N, RADICAL, bad, total_charge=-1, energy_neutral_hartree=-100.0, energy_anion_hartree=-99.9, anion_s_squared=0.95)
    assert result
    assert result.f_minus == pytest.approx([0.4, 0.3, 0.3])
    assert result.f_plus == () and result.f_zero == () and result.dual == ()
    assert result.f_plus_note in result.caveats
    assert result.f_plus_note.startswith("f+, f0 and the dual descriptor were not computed: they need the N+1 state, which for an anion is a dianion. The dianion")
    assert result.f_plus_note.endswith("f- needs only the anion and the neutral radical it becomes, and is complete.")
    # nothing else of the dropped dianion is kept: not its energy (no unbound sentence), not its spin
    assert result.unbound_anion_ev is None and not any("ABOVE" in caveat for caveat in result.caveats)
    assert result.anion_s_squared is None and not any("dianion is spin-contaminated" in caveat for caveat in result.caveats)


def test_a_dianion_of_the_wrong_size_is_dropped_the_same_way():
    result = condensed_fukui(ANION_N, RADICAL, [-1.0, -1.0], total_charge=-1)
    assert result and not result.computes_f_plus
    assert "The three states list different numbers of atoms (3, 3 and 2)" in result.f_plus_note


def test_the_dropped_dianions_extra_starts_are_not_reported():
    solutions = [_kept(STATE_N), _kept(STATE_OXIDISED), _replaced(state=STATE_REDUCED)]
    result = condensed_fukui(ANION_N, RADICAL, [-1.0, -0.5, -0.1], total_charge=-1, solutions=solutions)
    assert [solution.state for solution in result.solutions] == [STATE_N, STATE_OXIDISED]
    assert not any("SCF solution" in caveat for caveat in result.caveats)


def test_a_dianion_that_is_used_keeps_its_extra_starts_in_the_caveats():
    solutions = [_kept(STATE_N), _kept(STATE_OXIDISED), _replaced(state=STATE_REDUCED)]
    result = condensed_fukui(ANION_N, RADICAL, DIANION, total_charge=-1, solutions=solutions)
    assert start_sentence(_replaced(state=STATE_REDUCED), -1) in result.caveats
    assert start_sentence(_replaced(state=STATE_REDUCED), -1).startswith("The dianion state has more than one SCF solution.")


def test_a_bad_dianion_does_not_hide_a_bad_anion_or_a_bad_radical():
    """Dropping the dianion is only for the dianion: if the first two states are not usable either, the result is refused with their reason."""
    bad_radical = [-0.1, 0.0, 0.4]
    result = condensed_fukui(ANION_N, bad_radical, [-1.0, -0.5, -0.1], total_charge=-1)
    assert not result and "neutral radical (N-1 electrons) state's charges sum to +0.300" in result.reason


def test_a_missing_dianion_with_a_reason_from_the_caller_says_that_reason():
    reason = "ORCA printed no SCF energy and Hirshfeld table for the dianion (job 5), most likely because its SCF did not converge."
    result = condensed_fukui(ANION_N, RADICAL, None, total_charge=-1, anion_unavailable=reason)
    assert result.f_plus_note == f_plus_not_computed_sentence(reason)
    assert result.f_plus_note == (
        "f+, f0 and the dual descriptor were not computed: they need the N+1 state, which for an anion is a dianion. " + reason +
        " f- needs only the anion and the neutral radical it becomes, and is complete."
    )
    assert result.f_plus_note in result.caveats


def test_a_missing_dianion_without_a_reason_says_the_sentence_every_anion_of_the_second_gate_carried():
    result = condensed_fukui(ANION_N, RADICAL, None, total_charge=-1)
    assert result.f_plus_note == f_plus_not_computed_sentence() and "no basis set binds in the gas phase" in result.f_plus_note


def test_a_neutral_species_never_drops_its_n_plus_one_state():
    neutral, cation = [0.2, -0.4, 0.1, 0.1], [0.5, -0.1, 0.3, 0.3]
    result = condensed_fukui(neutral, cation, [0.0, -0.8, -0.1, -0.1 + 0.5])
    assert not result and "anion (N+1 electrons) state's charges" in result.reason


# --- the sentences about starts ----------------------------------------------------------------------------------------------


def _job(state, start, energy, charges, charge=-1, multiplicity=2):
    return JobResult(state, charge, multiplicity, start, energy, tuple(charges), None)


def _replaced(state=STATE_REDUCED, gain_ev=1.013, difference=0.25, finished=3, failed=()):
    default = _job(state, START_DEFAULT, -100.0, (0.2, -0.2))
    chosen = _job(state, START_HCORE, -100.0 - gain_ev / 27.211386245988, (0.2 + difference, -0.2 - difference))
    return Solution(state=state, chosen=chosen, default=default, failed=failed, finished=finished)


def _kept(state=STATE_REDUCED, failed=()):
    default = _job(state, START_DEFAULT, -100.0, (0.2, -0.2))
    return Solution(state=state, chosen=default, default=default, failed=failed, finished=1)


def test_the_start_sentence_gives_the_gain_the_start_and_how_far_a_value_moves():
    sentence = start_sentence(_replaced(), 0)
    assert sentence.startswith("The anion state has more than one SCF solution. ORCA's default start reached one 1.01 eV above")
    assert "1.01 eV above the lowest of the 3 starts that finished" in sentence
    assert "from the HCore start" in sentence
    assert "up to 0.250 electrons in one atom's Hirshfeld charge" in sentence
    assert "one atom's f+ value" in sentence


@pytest.mark.parametrize(
    "state,reference,expected_state,expected_function",
    [
        (STATE_REDUCED, 0, "anion", "f+"),
        (STATE_OXIDISED, 0, "cation", "f-"),
        (STATE_N, -1, "anion", "f+ and f-"),
        (STATE_OXIDISED, -1, "neutral radical", "f-"),
    ],
)
def test_the_start_sentence_names_the_state_and_the_function_it_moves(state, reference, expected_state, expected_function):
    sentence = start_sentence(_replaced(state=state), reference)
    assert sentence.startswith(f"The {expected_state} state has more than one SCF solution.")
    assert f"one atom's {expected_function} value" in sentence


def test_the_failed_starts_sentence_is_singular_or_plural():
    one = failed_starts_sentence(_kept(failed=(START_HCORE,)), 0)
    assert one == (
        "The HCore start of the anion state did not converge and was not used; the choice was made among the 1 that finished."
    )
    two = failed_starts_sentence(_kept(failed=(START_HCORE, START_HUECKEL)), 0)
    assert two.startswith("The HCore and Hueckel starts of the anion state did not converge and were not used")


def test_the_failed_starts_sentence_names_the_state_of_an_anion_as_an_anion():
    assert "start of the anion state" in failed_starts_sentence(_kept(STATE_N, failed=(START_HUECKEL,)), -1)


def test_only_a_replaced_default_or_a_failed_start_has_a_note():
    assert start_notes([_kept()], 0) == []
    assert len(start_notes([_replaced()], 0)) == 1
    assert len(start_notes([_kept(failed=(START_HCORE,))], 0)) == 1
    both = start_notes([_replaced(failed=(START_HUECKEL,))], 0)
    assert len(both) == 2 and "SCF solution" in both[0] and "did not converge" in both[1]


def test_the_notes_come_in_state_order_and_the_caveats_carry_them():
    solutions = [_replaced(state=STATE_N), _replaced(state=STATE_OXIDISED)]
    notes = start_notes(solutions, -2)
    assert notes[0].startswith("The dianion state") and notes[1].startswith("The anion state")
    neutral, cation, anion = [0.2, -0.4, 0.1, 0.1], [0.5, -0.1, 0.3, 0.3], [0.0, -0.8, -0.1, -0.1]
    result = condensed_fukui(neutral, cation, anion, solutions=[_replaced()])
    assert start_sentence(_replaced(), 0) in result.caveats and result.solutions[0].replaced_default


def test_a_run_whose_starts_all_agreed_has_no_start_caveat_and_still_carries_its_solutions():
    neutral, cation, anion = [0.2, -0.4, 0.1, 0.1], [0.5, -0.1, 0.3, 0.3], [0.0, -0.8, -0.1, -0.1]
    result = condensed_fukui(neutral, cation, anion, solutions=[_kept(), _kept(STATE_N)])
    assert not any("SCF solution" in caveat or "did not converge" in caveat for caveat in result.caveats)
    assert len(result.solutions) == 2


# --- what a panel shows -----------------------------------------------------------------------------------------------------------


def _dataset(property_id, values, **parameters):
    return PerAtomDataset(
        property_id=property_id, name=property_id, units="", method="orca", molecule_uuid="m",
        values=dict(enumerate(values)), provenance=Provenance(created_by="core", method="orca", parameters=parameters),
    )


def test_an_anions_summary_says_f_plus_was_not_computed_and_has_no_largest_f_plus_line():
    lines = summary_lines([_dataset("orca.fukui_minus", [0.4, 0.3, 0.3], reference_charge=-1)], ["C", "O", "H"])
    assert lines[0].startswith("Fukui functions (Hirshfeld, vertical) for 3 atoms")
    assert any(line.startswith("Largest f- (attack by an electrophile): C (atom 1): 0.400") for line in lines)
    assert not any(line.startswith("Largest f+") or line.startswith("Largest f0") for line in lines)
    assert f_plus_not_computed_sentence() in lines


def test_an_anions_summary_with_a_dianion_has_all_the_largest_lines_and_the_dianion_sentence():
    lines = summary_lines(
        [
            _dataset("orca.fukui_plus", [0.5, 0.2, 0.3], reference_charge=-1, unbound_anion_ev=2.7),
            _dataset("orca.fukui_minus", [0.4, 0.3, 0.3], reference_charge=-1),
            _dataset("orca.fukui_zero", [0.45, 0.25, 0.30], reference_charge=-1),
        ],
        ["C", "O", "H"],
    )
    assert any(line.startswith("Largest f+ (attack by a nucleophile): C (atom 1): 0.500") for line in lines)
    assert any(line.startswith("Largest f- (attack by an electrophile): C (atom 1): 0.400") for line in lines)
    assert f_plus_not_computed_sentence() not in lines
    assert unbound_anion_sentence(2.7, -1) in lines and unbound_anion_sentence(2.7) not in lines


def test_a_summary_with_a_recorded_reason_for_a_missing_f_plus_says_that_and_not_the_general_sentence():
    note = f_plus_not_computed_sentence("ORCA printed no SCF energy and Hirshfeld table for the dianion (job 5), most likely because its SCF did not converge.")
    lines = summary_lines([_dataset("orca.fukui_minus", [0.4, 0.3, 0.3], reference_charge=-1, f_plus_note=note)], ["C", "O", "H"])
    assert note in lines and f_plus_not_computed_sentence() not in lines


def test_a_full_runs_summary_does_not_say_it():
    lines = summary_lines(
        [_dataset("orca.fukui_plus", [0.6, 0.4]), _dataset("orca.fukui_minus", [0.3, 0.7])], ["C", "O"]
    )
    assert f_plus_not_computed_sentence() not in lines and any(line.startswith("Largest f+") for line in lines)


def test_the_summary_prints_the_start_note_before_the_spin_sentences_and_the_standing_sentence_last():
    note = start_sentence(_replaced(), 0)
    lines = summary_lines(
        [_dataset("orca.fukui_plus", [0.6, 0.4], start_note=note, cation_s_squared=0.97, reference_charge=0)], ["C", "O"]
    )
    assert note in lines
    assert lines.index(note) < next(i for i, line in enumerate(lines) if line.startswith("The cation is spin-contaminated"))
    assert lines[-1].startswith("Not validated:")


def test_the_summary_names_an_anions_oxidised_state_a_neutral_radical():
    lines = summary_lines(
        [_dataset("orca.fukui_minus", [0.4, 0.3, 0.3], reference_charge=-1, cation_s_squared=0.97)], ["C", "O", "H"]
    )
    assert any(line.startswith("The neutral radical is spin-contaminated") for line in lines)


def test_a_dataset_with_no_reference_charge_reads_as_a_neutral_species():
    """A result stored by the first release has no `reference_charge`; it was a neutral species' or an anion's with three states, and its words are the old ones."""
    lines = summary_lines([_dataset("orca.fukui_plus", [0.6, 0.4], cation_s_squared=0.97)], ["C", "O"])
    assert any(line.startswith("The cation is spin-contaminated") for line in lines)


def test_a_bool_reference_charge_is_not_a_charge():
    lines = summary_lines([_dataset("orca.fukui_plus", [0.6, 0.4], cation_s_squared=0.97, reference_charge=True)], ["C", "O"])
    assert any(line.startswith("The cation is spin-contaminated") for line in lines)
