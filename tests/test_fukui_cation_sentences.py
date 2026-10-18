"""What a Fukui result says about the cation's state: `chem/fukui.py`'s sentences for the search of `chem/fukui_states.py`, pure, with invented charges."""

from __future__ import annotations

import pytest

from openchem.chem.fukui import (
    NOT_VALIDATED_SENTENCE,
    cation_state_sentences,
    condensed_fukui,
    no_search_sentence,
    summary_lines,
)
from openchem.chem.fukui_plan import START_DEFAULT, STATE_N, STATE_OXIDISED, JobResult, hole_start
from openchem.chem.fukui_states import WINDOW_EV, read_cation
from openchem.domain.scientific_result import PerAtomDataset
from openchem.domain.common import Provenance

HARTREE_TO_EV = 27.211386245988
BASE = -100.0

SYMBOLS = ["O", "C", "H"]
NEUTRAL = (-0.30, 0.10, 0.20)
#: Three states whose charges sum to +1 (a cation of the three-atom species above).
PI = (0.20, 0.50, 0.30)
SIGMA = (0.60, 0.30, 0.10)
THIRD = (0.40, 0.40, 0.20)


def _job(start: str, above_ev: float, charges=PI) -> JobResult:
    return JobResult(STATE_OXIDISED, 1, 2, start, BASE + above_ev / HARTREE_TO_EV, tuple(charges), 0.76)


def _reading(*jobs: JobResult, planned=None):
    """The reading of these N-1 jobs, with a search written for the holes they include (a hole start that is listed and never began is `planned` and absent)."""
    from openchem.chem.fukui_plan import hole_of_start

    holes = tuple(sorted({hole_of_start(job.start) for job in jobs} - {0})) if planned is None else planned
    return read_cation([JobResult(STATE_N, 0, 1, START_DEFAULT, BASE - 9.0, NEUTRAL), *jobs], planned_holes=holes)


# --- the sentences --------------------------------------------------------------------------------------------------------


def test_a_search_that_found_one_state_and_ran_to_the_end_says_nothing():
    reading = _reading(_job(START_DEFAULT, 0.0), _job(hole_start(1), 0.0), _job(hole_start(2), 0.0), _job(hole_start(3), 0.0))
    assert cation_state_sentences(reading, 0, SYMBOLS) == []


def test_another_state_within_the_window_is_named_with_its_gap_its_f_minus_difference_and_the_atom():
    reading = _reading(_job(START_DEFAULT, 0.146, SIGMA), _job(hole_start(1), 0.0, PI), _job(hole_start(2), 0.0, PI), _job(hole_start(3), 0.0, PI))
    # Charge differences between the two states: 0.40, 0.20, 0.20; the biggest is atom 0, the oxygen.
    assert cation_state_sentences(reading, 0, SYMBOLS) == [
        "Another state of the cation lies 0.15 eV (its f- differs by up to 0.400, at O (atom 1)) above the one f- is read from, which is the lowest found. "
        "f- depends on which state is meant."
    ]


def test_two_competing_states_are_said_in_one_sentence_nearest_first():
    reading = _reading(_job(START_DEFAULT, 0.30, THIRD), _job(hole_start(1), 0.0, PI), _job(hole_start(2), 0.12, SIGMA))
    [sentence] = cation_state_sentences(reading, 0, SYMBOLS)
    assert sentence == (
        "Other states of the cation lie 0.12 eV (its f- differs by up to 0.400, at O (atom 1)) and 0.30 eV (its f- differs by up to 0.200, at O (atom 1)) above the one f- "
        "is read from, which is the lowest found. f- depends on which state is meant."
    )


def test_more_than_three_competing_states_are_counted_and_not_all_listed():
    states = [(0.05, SIGMA), (0.10, THIRD), (0.15, (0.30, 0.60, 0.10)), (0.20, (0.25, 0.45, 0.30)), (0.25, (0.50, 0.30, 0.20))]
    reading = _reading(_job(START_DEFAULT, 0.0, PI), *(_job(hole_start(index + 1), gap, charges) for index, (gap, charges) in enumerate(states)))
    [sentence] = cation_state_sentences(reading, 0, SYMBOLS)
    assert sentence.startswith("Other states of the cation lie 0.05 eV") and sentence.count(" eV (its f- differs") == 3 and ", and 2 more above the one f- is read from" in sentence


def test_a_state_whose_f_minus_is_the_same_is_not_a_reason_to_say_anything():
    """Two solutions 0.2 eV apart with no atom's charge differing by more than the tolerance give one f-: the sentence would be noise."""
    reading = _reading(_job(START_DEFAULT, 0.0, PI), _job(hole_start(1), 0.2, PI))
    assert len(reading.competing) == 1 and cation_state_sentences(reading, 0, SYMBOLS) == []


def test_the_window_decides_what_is_competing_and_a_state_beyond_it_is_not_said():
    assert WINDOW_EV == 0.5
    reading = _reading(_job(START_DEFAULT, 0.0, PI), _job(hole_start(1), 0.6, SIGMA))
    assert reading.competing == () and reading.farther == 1 and cation_state_sentences(reading, 0, SYMBOLS) == []


def test_a_degenerate_level_is_averaged_and_says_so_with_how_far_apart_its_states_are():
    reading = _reading(_job(START_DEFAULT, 0.0, PI), _job(hole_start(1), 0.002, SIGMA))
    [sentence] = cation_state_sentences(reading, 0, SYMBOLS)
    assert sentence == (
        "The cation has 2 states within 0.01 eV of each other (a degenerate level), and f- is read from the average of their Hirshfeld charges because which of them an SCF "
        "reaches is arbitrary; they differ by up to 0.400 electrons in one atom's charge."
    )


def test_the_n_minus_one_state_of_an_anion_is_a_neutral_radical_and_of_a_cation_a_dication():
    reading = _reading(_job(START_DEFAULT, 0.0, SIGMA), _job(hole_start(1), 0.2, PI))
    assert cation_state_sentences(reading, -1, SYMBOLS)[0].startswith("Another state of the neutral radical lies 0.20 eV")
    assert cation_state_sentences(reading, 1, SYMBOLS)[0].startswith("Another state of the dication lies 0.20 eV")


def test_atoms_are_named_from_one_as_the_atom_inspector_names_them_and_without_elements_by_number():
    reading = _reading(_job(START_DEFAULT, 0.0, SIGMA), _job(hole_start(1), 0.2, PI))
    assert "at O (atom 1)" in cation_state_sentences(reading, 0, SYMBOLS)[0]
    assert "at atom 1)" in cation_state_sentences(reading, 0)[0] and "at atom 1)" in cation_state_sentences(reading, 0, [])[0]


def test_a_job_that_did_not_finish_and_a_hole_that_never_began_are_named_in_one_sentence():
    results = [_job(START_DEFAULT, 0.0), _job(hole_start(1), 0.0), JobResult(STATE_OXIDISED, 1, 2, hole_start(2), None, None)]
    reading = read_cation([JobResult(STATE_N, 0, 1, START_DEFAULT, BASE - 9.0, NEUTRAL), *results], planned_holes=(1, 2, 3))
    [sentence] = cation_state_sentences(reading, 0, SYMBOLS)
    assert sentence == (
        "The HOMO-2 and HOMO-3 starts of the search for other states of the cation did not run to the end (ORCA ended the run at a job that did not converge), so the search "
        "covered fewer holes than it was written with."
    )
    only_one = read_cation([JobResult(STATE_N, 0, 1, START_DEFAULT, BASE - 9.0, NEUTRAL), *results[:2]], planned_holes=(1, 2))
    assert cation_state_sentences(only_one, 0, SYMBOLS)[0].startswith("The HOMO-2 start of the search")


@pytest.mark.parametrize("gap, said", [(0.30, True), (0.60, True), (0.61, False), (3.0, False), (None, False)])
def test_a_search_that_stopped_short_of_orbitals_close_to_the_homo_says_so(gap, said):
    """The orbital below the deepest hole lies within the window and the slack (0.5 + 0.1 eV) of the HOMO: a state with the hole there may exist and was not looked for."""
    reading = _reading(_job(START_DEFAULT, 0.0), _job(hole_start(1), 0.0), _job(hole_start(2), 0.0), _job(hole_start(3), 0.0))
    sentences = cation_state_sentences(reading, 0, SYMBOLS, gap)
    assert bool(sentences) is said
    if said:
        assert sentences == [
            f"The search put the hole in the HOMO-1, HOMO-2 and HOMO-3, but the occupied orbital below them lies only {gap:.2f} eV under the HOMO, so a state with the hole there may "
            "exist and was not looked for."
        ]


def test_no_search_is_said_with_the_reason_the_name_of_the_state_and_what_it_cost_benzaldehyde():
    sentence = no_search_sentence(0, "it was switched off in Settings > Quantum chemistry")
    assert sentence == (
        "No search for other states of the cation was run (it was switched off in Settings > Quantum chemistry), so f- is read from the one state ORCA's SCF reached from the "
        "neutral's orbitals. For a molecule whose cation has close-lying states, a different orientation of the same structure can reach another: benzaldehyde did, 6 of 14 runs "
        "one state and 8 the other, 0.05 apart in f-."
    )
    assert no_search_sentence(-1, "it has no occupied valence orbital below its HOMO").startswith("No search for other states of the neutral radical was run (it has no occupied valence")


# --- how they reach the result ------------------------------------------------------------------------------------------------


def _fukui(**kwargs):
    return condensed_fukui(NEUTRAL, PI, (0.10, -0.40, -0.70), total_charge=0, **kwargs)


def test_a_result_without_a_search_and_without_a_reason_says_nothing_about_the_cations_state_as_v2_did():
    result = _fukui()
    assert result.cation_note == "" and result.cation_reading is None
    assert not any("other states" in caveat.lower() for caveat in result.caveats)


def test_a_result_that_was_not_searched_carries_the_no_search_sentence_among_its_caveats():
    result = _fukui(cation_unsearched="it has an element heavier than krypton")
    assert result.cation_note == no_search_sentence(0, "it has an element heavier than krypton")
    assert result.cation_note in result.caveats and result.caveats[-1] == NOT_VALIDATED_SENTENCE


def test_a_result_that_searched_carries_the_reading_and_its_sentences_between_the_start_notes_and_the_spin_sentences():
    reading = _reading(_job(START_DEFAULT, 0.145, SIGMA), _job(hole_start(1), 0.0, PI))
    result = _fukui(cation_reading=reading, symbols=SYMBOLS)
    assert result.cation_reading is reading and result.cation_note
    assert result.cation_note in result.caveats
    assert result.caveats.index(result.cation_note) < len(result.caveats) - 1 and result.caveats[-1] == NOT_VALIDATED_SENTENCE


def test_f_minus_is_differenced_from_the_charges_it_is_given_and_the_reading_only_adds_sentences():
    """The reading's charges are what the caller passes as the cation; `condensed_fukui` does not look inside the reading for numbers."""
    reading = _reading(_job(START_DEFAULT, 0.145, SIGMA), _job(hole_start(1), 0.0, PI))
    with_reading, without = _fukui(cation_reading=reading, symbols=SYMBOLS), _fukui()
    assert with_reading.f_minus == without.f_minus == tuple(c - n for n, c in zip(NEUTRAL, PI))
    assert with_reading.f_plus == without.f_plus


def _dataset(**parameters) -> PerAtomDataset:
    return PerAtomDataset(
        property_id="orca.fukui_minus", name="Fukui f- (Hirshfeld)", units="", method="orca", molecule_uuid="m", values={0: 0.4, 1: 0.6},
        provenance=Provenance(created_by="core", method="orca", parameters={"reference_charge": 0, **parameters}, timestamp=0.0), timestamp=0.0,
    )


def test_the_summary_prints_the_cation_note_after_the_start_note_and_before_the_spin_sentences_and_the_standing_sentence_last():
    lines = summary_lines(
        [_dataset(start_note="START NOTE", cation_note="CATION NOTE", cation_s_squared=0.97)], ["C", "O"]
    )
    assert lines.index("START NOTE") < lines.index("CATION NOTE") < next(i for i, line in enumerate(lines) if "spin-contaminated" in line)
    assert lines[-1] == NOT_VALIDATED_SENTENCE


def test_the_summary_prints_no_cation_line_for_a_run_that_has_no_cation_note():
    assert not any("CATION NOTE" in line for line in summary_lines([_dataset()], ["C", "O"]))
