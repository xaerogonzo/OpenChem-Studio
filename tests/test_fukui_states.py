"""Which state of the cation f- is read from: `chem/fukui_states.py`, pure, so every number here is invented or worked by hand."""

from __future__ import annotations

import itertools

import pytest

from openchem.chem.fukui_plan import START_DEFAULT, STATE_N, STATE_OXIDISED, STATE_REDUCED, JobResult, hole_start
from openchem.chem.fukui_states import (
    CHARGE_TOLERANCE,
    LEVEL_MARGIN_EV,
    WINDOW_EV,
    read_cation,
)

HARTREE_TO_EV = 27.211386245988
BASE = -100.0

#: Three atoms whose charges sum to +1, as a cation's must. A state is a different split of that electron.
PI = (0.60, 0.30, 0.10)
SIGMA = (0.20, 0.50, 0.30)
THIRD = (0.35, 0.35, 0.30)


def _job(start: str, above_ev: float, charges=PI, *, state: str = STATE_OXIDISED, s_squared: float | None = 0.76, finished: bool = True) -> JobResult:
    """A finished job `above_ev` above an arbitrary zero; an unfinished one printed no energy and no table."""
    return JobResult(
        state=state,
        charge=1,
        multiplicity=2,
        start=start,
        energy_hartree=BASE + above_ev / HARTREE_TO_EV if finished else None,
        charges=tuple(charges) if finished else None,
        s_squared=s_squared if finished else None,
    )


def _neutral() -> JobResult:
    return JobResult(STATE_N, 0, 1, START_DEFAULT, BASE - 10.0, (0.0, 0.0, 0.0))


# --- one state ----------------------------------------------------------------------------------------------------------


def test_one_job_is_one_state_and_f_minus_is_read_from_it_unchanged():
    reading = read_cation([_neutral(), _job(START_DEFAULT, 0.0)])
    assert reading.charges == PI and len(reading.averaged) == 1 and reading.competing == () and reading.farther == 0
    assert reading.finished == 1 and reading.failed == () and not reading.searched and not reading.degenerate
    assert reading.default.start == START_DEFAULT


def test_the_other_states_of_a_run_are_not_read():
    """The N and N+1 jobs are no cation: only the N-1 state's jobs say anything here."""
    reading = read_cation([_neutral(), _job(START_DEFAULT, 0.0), _job(START_DEFAULT, 5.0, SIGMA, state=STATE_REDUCED)])
    assert reading.finished == 1 and reading.competing == ()


def test_no_finished_job_of_the_state_gives_no_reading():
    assert read_cation([_neutral(), _job(START_DEFAULT, 0.0, finished=False)]) is None
    assert read_cation([_neutral()]) is None
    assert read_cation([]) is None


def test_starts_that_reach_one_state_are_one_state_and_the_default_starts_charges_are_the_ones_read():
    """Measured: starts that reached one state agreed to 0.0004 in charge and 0.004 eV. The default start's job is the one read, so a run whose search found nothing new gives
    exactly what a run without a search gave, and the state's energy is the lowest any job reached it at."""
    default = _job(START_DEFAULT, 0.003, (0.600, 0.300, 0.100))
    hole = _job(hole_start(1), 0.000, (0.6002, 0.2998, 0.100))
    reading = read_cation([_neutral(), default, hole])
    assert len(reading.averaged) == 1 and reading.charges == default.charges
    assert reading.energy_hartree == hole.energy_hartree
    assert reading.averaged[0].starts == (START_DEFAULT, "HOMO-1")
    assert reading.finished == 2


# --- a lower state than the default start reached -------------------------------------------------------------------------------


def test_a_hole_start_that_finds_a_lower_state_is_the_state_f_minus_is_read_from_and_the_default_one_competes():
    """Benzaldehyde's shape: the default start reached a state 0.145 eV above the lowest, and a hole start the lowest."""
    default = _job(START_DEFAULT, 0.145, SIGMA)
    hole = _job(hole_start(2), 0.0, PI)
    reading = read_cation([_neutral(), default, hole])
    assert reading.charges == PI and reading.energy_hartree == hole.energy_hartree
    assert len(reading.competing) == 1
    other = reading.competing[0]
    assert other.above_ev == pytest.approx(0.145, abs=1e-9) and other.starts == (START_DEFAULT,)
    # The biggest difference between the two charge tables is atom 1 (index 1: 0.30 against 0.50) and then atom 0 (0.60 against 0.20): 0.40 at atom 0.
    assert other.max_difference == pytest.approx(0.40) and other.atom == 0
    assert reading.default is default


def test_the_states_are_listed_nearest_first_whatever_order_the_jobs_ran_in():
    jobs = [_neutral(), _job(START_DEFAULT, 0.30, THIRD), _job(hole_start(1), 0.0, PI), _job(hole_start(2), 0.12, SIGMA)]
    reading = read_cation(jobs)
    assert [round(state.above_ev, 3) for state in reading.competing] == [0.12, 0.30]
    assert reading.competing[0].charges == SIGMA and reading.competing[1].charges == THIRD


@pytest.mark.parametrize("order", list(itertools.permutations(range(4))))
def test_the_reading_does_not_depend_on_the_order_the_jobs_ran_in(order):
    jobs = [_job(START_DEFAULT, 0.12, SIGMA), _job(hole_start(1), 0.0, PI), _job(hole_start(2), 0.0001, PI), _job(hole_start(3), 0.30, THIRD)]
    reading = read_cation([jobs[index] for index in order])
    assert reading.charges == PI
    assert [state.charges for state in reading.competing] == [SIGMA, THIRD]
    assert reading.finished == 4


# --- the margins ----------------------------------------------------------------------------------------------------------


def test_the_margin_between_one_level_and_two_is_the_scf_margin_chem_fukui_plan_already_uses():
    from openchem.chem.fukui_plan import START_MARGIN_EV

    assert LEVEL_MARGIN_EV == START_MARGIN_EV == 0.01


@pytest.mark.parametrize("gap, averaged", [(0.0, True), (0.002, True), (0.0099, True), (0.0101, False), (0.018, False)])
def test_two_different_states_within_the_level_margin_are_a_degenerate_level_and_are_averaged(gap, averaged):
    """The two components of a degenerate hole have one energy and different charges (benzene's e1g pair); the closest two DIFFERENT states measured were 0.018 eV apart."""
    first, second = _job(START_DEFAULT, 0.0, PI), _job(hole_start(1), gap, SIGMA)
    reading = read_cation([_neutral(), first, second])
    assert reading.degenerate is averaged
    if averaged:
        assert len(reading.averaged) == 2 and reading.competing == ()
        assert reading.charges == pytest.approx(tuple((a + b) / 2 for a, b in zip(PI, SIGMA)))
    else:
        assert len(reading.averaged) == 1 and reading.charges == PI and len(reading.competing) == 1


def test_a_degenerate_level_averages_every_state_in_it_and_the_energy_is_the_lowest():
    jobs = [_job(START_DEFAULT, 0.004, PI), _job(hole_start(1), 0.0, SIGMA), _job(hole_start(2), 0.006, THIRD)]
    reading = read_cation([_neutral(), *jobs])
    assert len(reading.averaged) == 3
    assert reading.charges == pytest.approx(tuple(sum(values) / 3 for values in zip(PI, SIGMA, THIRD)))
    assert reading.energy_hartree == jobs[1].energy_hartree
    assert reading.charges and sum(reading.charges) == pytest.approx(1.0)


@pytest.mark.parametrize("difference, same", [(0.0, True), (0.004, True), (0.0049, True), (0.0051, False), (0.02, False)])
def test_two_jobs_with_one_energy_are_one_state_only_if_no_atoms_charge_differs_by_more_than_the_tolerance(difference, same):
    first = _job(START_DEFAULT, 0.0, (0.600, 0.300, 0.100))
    second = _job(hole_start(1), 0.002, (0.600 + difference, 0.300 - difference, 0.100))
    reading = read_cation([_neutral(), first, second])
    assert (len(reading.averaged) == 1) is same
    # A pair of different states with one energy is a degenerate level: it is averaged, not reported as competing.
    assert reading.competing == ()
    assert reading.degenerate is (not same)


def test_the_tolerance_sits_between_what_one_state_reached_two_ways_differs_by_and_what_two_states_do():
    """Measured on eleven molecules (44 jobs): starts that reached one state agreed to 0.0004; the smallest difference between two different states was 0.085."""
    assert 0.0004 < CHARGE_TOLERANCE < 0.085


@pytest.mark.parametrize("gap, competing", [(0.49, True), (0.4999, True), (0.5001, False), (0.51, False), (3.0, False)])
def test_a_state_is_reported_as_competing_only_within_the_window_and_counted_beyond_it(gap, competing):
    reading = read_cation([_neutral(), _job(START_DEFAULT, 0.0, PI), _job(hole_start(1), gap, SIGMA)])
    assert (len(reading.competing) == 1) is competing
    assert reading.farther == (0 if competing else 1)


def test_the_window_is_half_an_electron_volt():
    assert WINDOW_EV == 0.5


def test_a_state_with_the_same_charges_a_little_higher_is_listed_with_no_difference():
    """Two solutions that differ in energy by more than the margin and in no atom's charge: the same f-. It is listed (the sentence builder drops it)."""
    reading = read_cation([_neutral(), _job(START_DEFAULT, 0.0, PI), _job(hole_start(1), 0.2, PI)])
    assert len(reading.competing) == 1 and reading.competing[0].max_difference == 0.0


# --- the spin and the jobs that did not finish --------------------------------------------------------------------------------


def test_the_spin_contamination_read_is_the_largest_of_the_states_read():
    jobs = [_job(START_DEFAULT, 0.0, PI, s_squared=0.76), _job(hole_start(1), 0.003, SIGMA, s_squared=0.91)]
    assert read_cation([_neutral(), *jobs]).s_squared == 0.91
    assert read_cation([_neutral(), _job(START_DEFAULT, 0.0, PI, s_squared=None)]).s_squared is None
    # A competing state's spin is not the state f- is read from.
    assert read_cation([_neutral(), _job(START_DEFAULT, 0.0, PI, s_squared=0.76), _job(hole_start(1), 0.2, SIGMA, s_squared=0.99)]).s_squared == 0.76


def test_a_job_that_began_and_did_not_finish_is_named_and_the_rest_are_still_read():
    jobs = [_neutral(), _job(START_DEFAULT, 0.0), _job(hole_start(1), 0.0), _job(hole_start(2), 0.0, finished=False)]
    reading = read_cation(jobs)
    assert reading.failed == ("HOMO-2",) and reading.finished == 2 and reading.incomplete


def test_a_hole_that_never_began_is_unreached_and_a_search_that_was_not_asked_for_is_not():
    jobs = [_neutral(), _job(START_DEFAULT, 0.0), _job(hole_start(1), 0.0)]
    # ORCA echoed an input written with three holes and the run ended after the first: the other two never began.
    reading = read_cation(jobs, planned_holes=(1, 2, 3))
    assert reading.holes_planned == (1, 2, 3) and reading.unreached == (2, 3) and reading.incomplete and reading.searched
    # Without an echo the holes that ran are the only ones known.
    known = read_cation(jobs)
    assert known.holes_planned == (1,) and known.unreached == () and not known.incomplete
    # A run with no holes at all, planned or run, is no search.
    assert not read_cation([_neutral(), _job(START_DEFAULT, 0.0)]).searched


def test_a_failed_default_start_does_not_stop_the_reading_of_a_hole_that_finished():
    """ORCA ends the run at a job that does not converge, so this does not happen in a real run, but the reading must not assume it."""
    jobs = [_neutral(), _job(START_DEFAULT, 0.0, finished=False), _job(hole_start(1), 0.0, SIGMA)]
    reading = read_cation(jobs)
    assert reading.charges == SIGMA and reading.failed == (START_DEFAULT,)


def test_the_extra_starts_of_an_anionic_n_minus_one_state_are_read_with_the_holes():
    jobs = [_neutral(), _job(START_DEFAULT, 0.0, PI), _job("HCore", 0.0, PI), _job("Hueckel", 0.0, PI), _job(hole_start(1), 0.2, SIGMA)]
    reading = read_cation(jobs)
    assert reading.averaged[0].starts == (START_DEFAULT, "HCore", "Hueckel") and len(reading.competing) == 1
