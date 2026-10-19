"""Which jobs a Fukui run has and which finished one it reads: `chem/fukui_plan.py`, pure, so every number here is invented or worked by hand."""

from __future__ import annotations

import pytest

from openchem.chem.fukui_plan import (
    EXTRA_STARTS,
    START_DEFAULT,
    START_HCORE,
    START_HUECKEL,
    START_MARGIN_EV,
    STATE_N,
    STATE_OXIDISED,
    STATE_REDUCED,
    FukuiJob,
    JobResult,
    choose_solutions,
    has_diffuse_functions,
    plan_fukui,
    state_name,
    state_of,
)

HARTREE_TO_EV = 27.211386245988


def _shape(plan):
    return [(job.state, job.charge, job.multiplicity, job.start) for job in plan.jobs]


# --- the plan -----------------------------------------------------------------------------------------------------------


def test_a_neutral_species_has_three_states_in_the_order_the_parse_assigns_them():
    plan = plan_fukui(0, 1, diffuse=False)
    assert _shape(plan) == [
        (STATE_N, 0, 1, START_DEFAULT),
        (STATE_OXIDISED, 1, 2, START_DEFAULT),
        (STATE_REDUCED, -1, 2, START_DEFAULT),
    ]


def test_a_cation_has_three_states_too():
    assert _shape(plan_fukui(1, 1, diffuse=False)) == [
        (STATE_N, 1, 1, START_DEFAULT),
        (STATE_OXIDISED, 2, 2, START_DEFAULT),
        (STATE_REDUCED, 0, 2, START_DEFAULT),
    ]


@pytest.mark.parametrize("charge", [-1, -2, -3])
def test_an_anion_has_an_n_plus_one_state_which_is_a_dianion_and_the_last_job(charge):
    """Fukui v2 left the dianion out (its second gate decided f- alone for an anion); it is back, and last, because f- does not need it."""
    plan = plan_fukui(charge, 1, diffuse=False)
    assert [job.state for job in plan.jobs] == [STATE_N, STATE_OXIDISED, STATE_REDUCED]
    assert [(job.charge, job.multiplicity) for job in plan.jobs] == [(charge, 1), (charge + 1, 2), (charge - 1, 2)]


@pytest.mark.parametrize("diffuse", [False, True])
@pytest.mark.parametrize("charge", [-3, -2, -1, 0, 1])
def test_nothing_f_minus_needs_comes_after_the_n_plus_one_state(charge, diffuse):
    """The invariant behind the order: ORCA ends a compound input at the first job that does not converge, so every job of the N and N-1 states (their extra starts
    included) precedes the N+1 state, and what follows the N+1 state's default job is its own extra starts and nothing else. A dianion that fails costs f+ only."""
    jobs = plan_fukui(charge, 1, diffuse=diffuse).jobs
    first_reduced = next(index for index, job in enumerate(jobs) if job.state == STATE_REDUCED)
    assert jobs[first_reduced].start == START_DEFAULT
    assert all(job.state != STATE_REDUCED for job in jobs[:first_reduced])
    assert all(job.state == STATE_REDUCED for job in jobs[first_reduced:])


@pytest.mark.parametrize("diffuse", [False, True])
@pytest.mark.parametrize("charge", [-3, -2, -1])
def test_an_anion_with_f_plus_switched_off_has_the_plan_fukui_v2_had(charge, diffuse):
    """The Settings switch: no N+1 state, so no dianion and no extra start of it; what is left is N, N-1 and the extra starts of those two, in the order they had."""
    plan = plan_fukui(charge, 1, diffuse=diffuse, anion_f_plus=False)
    assert all(job.state != STATE_REDUCED for job in plan.jobs)
    expected = [(STATE_N, START_DEFAULT), (STATE_OXIDISED, START_DEFAULT)]
    if diffuse:
        expected += [(STATE_N, start) for start in EXTRA_STARTS]
        if charge + 1 < 0:  # the N-1 state of a species of charge -2 or less is itself an anion
            expected += [(STATE_OXIDISED, start) for start in EXTRA_STARTS]
    assert [(job.state, job.start) for job in plan.jobs] == expected


@pytest.mark.parametrize("diffuse", [False, True])
@pytest.mark.parametrize("charge", [0, 1])
def test_the_switch_does_not_touch_a_neutral_species_or_a_cation(charge, diffuse):
    assert plan_fukui(charge, 1, diffuse=diffuse, anion_f_plus=False) == plan_fukui(charge, 1, diffuse=diffuse)


@pytest.mark.parametrize("charge", [-2, -1, 0, 1])
def test_f_plus_of_an_anion_is_on_unless_asked_off(charge):
    assert plan_fukui(charge, 1, diffuse=True) == plan_fukui(charge, 1, diffuse=True, anion_f_plus=True)


@pytest.mark.parametrize("multiplicity", [2, 3, 4])
def test_an_open_shell_species_has_no_plan(multiplicity):
    with pytest.raises(ValueError, match="closed-shell"):
        plan_fukui(0, multiplicity, diffuse=False)


def test_without_diffuse_functions_no_state_gets_an_extra_start():
    for charge in (-2, -1, 0, 1):
        assert {job.start for job in plan_fukui(charge, 1, diffuse=False).jobs} == {START_DEFAULT}


def test_with_diffuse_functions_the_anionic_n_plus_one_state_of_a_neutral_gets_two_extra_starts_after_every_default_job():
    """The order is load-bearing: ORCA ends the whole compound input at the first job that does not converge, so what the answer cannot do without is first."""
    plan = plan_fukui(0, 1, diffuse=True)
    assert [(job.state, job.start) for job in plan.jobs] == [
        (STATE_N, START_DEFAULT),
        (STATE_OXIDISED, START_DEFAULT),
        (STATE_REDUCED, START_DEFAULT),
        (STATE_REDUCED, START_HCORE),
        (STATE_REDUCED, START_HUECKEL),
    ]
    assert EXTRA_STARTS == (START_HCORE, START_HUECKEL)
    assert all(job.charge == -1 and job.multiplicity == 2 for job in plan.jobs[2:])


def test_with_diffuse_functions_the_anion_gets_them_before_its_dianion_and_the_dianion_after_it_and_the_neutral_radical_none():
    plan = plan_fukui(-1, 1, diffuse=True)
    assert [(job.state, job.charge, job.start) for job in plan.jobs] == [
        (STATE_N, -1, START_DEFAULT),
        (STATE_OXIDISED, 0, START_DEFAULT),
        (STATE_N, -1, START_HCORE),
        (STATE_N, -1, START_HUECKEL),
        (STATE_REDUCED, -2, START_DEFAULT),
        (STATE_REDUCED, -2, START_HCORE),
        (STATE_REDUCED, -2, START_HUECKEL),
    ]


def test_a_cation_has_no_anionic_state_so_diffuse_functions_add_nothing():
    assert len(plan_fukui(1, 1, diffuse=True).jobs) == 3


def test_a_dianion_has_three_anionic_states_and_the_n_plus_one_state_with_its_extra_starts_is_last():
    plan = plan_fukui(-2, 1, diffuse=True)
    assert [(job.state, job.start) for job in plan.jobs] == [
        (STATE_N, START_DEFAULT),
        (STATE_OXIDISED, START_DEFAULT),
        (STATE_N, START_HCORE),
        (STATE_N, START_HUECKEL),
        (STATE_OXIDISED, START_HCORE),
        (STATE_OXIDISED, START_HUECKEL),
        (STATE_REDUCED, START_DEFAULT),
        (STATE_REDUCED, START_HCORE),
        (STATE_REDUCED, START_HUECKEL),
    ]


def test_a_plan_is_immutable():
    plan = plan_fukui(0, 1, diffuse=False)
    with pytest.raises(AttributeError):
        plan.charge = 1
    with pytest.raises(AttributeError):
        plan.jobs[0].start = "x"


# --- which basis sets have diffuse functions -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method_basis",
    [
        "B3LYP 6-31+G*", "B3LYP 6-31++G**", "HF 6-311+G**", "HF 6-311++G(d,p)", "B3LYP 6-31+G(d)", "b3lyp 6-31+g*", "wB97X-D3 6-311++G**",
        "B3LYP aug-cc-pVDZ", "B3LYP AUG-CC-PVTZ", "HF d-aug-cc-pVDZ", "B3LYP heavy-aug-cc-pVTZ", "B3LYP jun-cc-pVDZ", "B3LYP may-cc-pVTZ", "B3LYP maug-cc-pVDZ",
        "B3LYP def2-SVPD", "B3LYP def2-TZVPD", "B3LYP def2-TZVPPD", "PBE0 def2-QZVPPD", "B3LYP ma-def2-SVP", "B3LYP ma-def2-TZVP",
        "B3LYP 3-21+G",
    ],
)
def test_a_basis_set_with_diffuse_functions_is_recognised(method_basis):
    assert has_diffuse_functions(method_basis)


@pytest.mark.parametrize(
    "method_basis",
    [
        "B3LYP 6-31G*", "B3LYP 6-31G**", "HF 6-311G**", "HF STO-3G", "B3LYP 3-21G", "B3LYP def2-SVP", "B3LYP def2-TZVP", "B3LYP def2-TZVPP", "B3LYP def2-QZVPP",
        "B3LYP cc-pVDZ", "B3LYP cc-pVTZ", "PBE0 pcseg-1", "B3LYP 6-31G(d,p)", "", "B3LYP",
        # A functional or dispersion keyword with a '+' or a 'D' in it is not a basis set
        "wB97X-D3 def2-SVP", "B3LYP-D3BJ def2-SVP", "B3LYP D4 6-31G*", "M06-2X 6-31G*",
    ],
)
def test_a_basis_set_without_them_is_not(method_basis):
    assert not has_diffuse_functions(method_basis)


def test_a_missing_method_is_no_diffuse_basis():
    assert not has_diffuse_functions(None)  # type: ignore[arg-type]


# --- the state names ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reference,charge,multiplicity,state",
    [
        (0, 0, 1, STATE_N), (0, 1, 2, STATE_OXIDISED), (0, -1, 2, STATE_REDUCED),
        (-1, -1, 1, STATE_N), (-1, 0, 2, STATE_OXIDISED), (-1, -2, 2, STATE_REDUCED),
        (1, 1, 1, STATE_N), (1, 2, 2, STATE_OXIDISED), (1, 0, 2, STATE_REDUCED),
    ],
)
def test_a_job_is_a_state_by_its_echoed_charge_and_multiplicity(reference, charge, multiplicity, state):
    assert state_of(reference, charge, multiplicity) == state


@pytest.mark.parametrize("charge,multiplicity", [(0, 2), (1, 1), (-1, 1), (2, 2), (3, 2), (0, 3)])
def test_a_job_that_is_no_state_of_a_neutral_species_is_none(charge, multiplicity):
    assert state_of(0, charge, multiplicity) is None


@pytest.mark.parametrize(
    "charge,name", [(2, "dication"), (1, "cation"), (0, "neutral radical"), (-1, "anion"), (-2, "dianion"), (5, "state of charge +5")]
)
def test_state_names(charge, name):
    assert state_name(charge) == name


# --- reading the finished jobs ---------------------------------------------------------------------------------------------------


def _job(state, start=START_DEFAULT, energy=-100.0, charges=(0.1, -0.1), charge=-1, multiplicity=2, s_squared=None):
    return JobResult(
        state=state, charge=charge, multiplicity=multiplicity, start=start,
        energy_hartree=energy, charges=None if charges is None else tuple(charges), s_squared=s_squared,
    )


def _ev(delta_ev):
    """An energy `delta_ev` BELOW -100 Eh."""
    return -100.0 - delta_ev / HARTREE_TO_EV


def test_a_state_with_one_start_is_read_from_it_and_says_nothing_about_starts():
    jobs = [_job(STATE_N, energy=-101.0), _job(STATE_OXIDISED, energy=-100.5)]
    solutions = choose_solutions(jobs)
    assert set(solutions) == {STATE_N, STATE_OXIDISED}
    for solution in solutions.values():
        assert not solution.replaced_default and solution.gain_ev == 0.0 and solution.failed == () and solution.finished == 1


def test_an_extra_start_replaces_the_default_only_when_it_is_lower_by_more_than_the_margin():
    default = _job(STATE_REDUCED, energy=_ev(0.0), charges=(0.20, -0.20))
    just_inside = _job(STATE_REDUCED, START_HCORE, energy=_ev(START_MARGIN_EV * 0.99), charges=(0.50, -0.50))
    kept = choose_solutions([default, just_inside])[STATE_REDUCED]
    assert kept.chosen is default and not kept.replaced_default and kept.gain_ev == 0.0

    just_outside = _job(STATE_REDUCED, START_HCORE, energy=_ev(START_MARGIN_EV * 1.01), charges=(0.50, -0.50))
    replaced = choose_solutions([default, just_outside])[STATE_REDUCED]
    assert replaced.chosen is just_outside and replaced.replaced_default
    assert replaced.gain_ev == pytest.approx(START_MARGIN_EV * 1.01)


def test_the_margin_is_ten_millielectronvolts_which_is_above_every_gated_or_bound_spread_measured():
    """Every start of every gated and every bound-anion case ended within 0.004 eV of the default's solution (benchmarks/fukui_gate_2/DESIGN.md)."""
    assert START_MARGIN_EV == 0.01


def test_the_lowest_of_several_lower_starts_is_read():
    default = _job(STATE_REDUCED, energy=_ev(0.0))
    first = _job(STATE_REDUCED, START_HCORE, energy=_ev(0.6))
    second = _job(STATE_REDUCED, START_HUECKEL, energy=_ev(1.0), charges=(0.4, -0.4))
    solution = choose_solutions([default, first, second])[STATE_REDUCED]
    assert solution.chosen is second
    assert solution.gain_ev == pytest.approx(1.0) and solution.finished == 3


def test_a_start_that_landed_above_the_default_is_never_read():
    """HCore started carbon monoxide's anion 7.26 eV above its default solution at HF/6-31G**: a different, higher solution, and not a candidate."""
    default = _job(STATE_REDUCED, energy=_ev(0.0))
    higher = _job(STATE_REDUCED, START_HCORE, energy=_ev(-7.26), charges=(0.9, -0.9))
    solution = choose_solutions([default, higher])[STATE_REDUCED]
    assert solution.chosen is default and solution.finished == 2


def test_the_choice_does_not_depend_on_the_order_the_extra_starts_were_written_in():
    default = _job(STATE_REDUCED, energy=_ev(0.0))
    low = _job(STATE_REDUCED, START_HCORE, energy=_ev(0.8), charges=(0.3, -0.3))
    high = _job(STATE_REDUCED, START_HUECKEL, energy=_ev(0.3), charges=(0.2, -0.2))
    assert choose_solutions([default, low, high])[STATE_REDUCED].chosen is low
    assert choose_solutions([default, high, low])[STATE_REDUCED].chosen is low


def test_the_charge_difference_is_the_largest_change_in_any_atoms_charge():
    default = _job(STATE_REDUCED, energy=_ev(0.0), charges=(0.20, -0.30, 0.10))
    lower = _job(STATE_REDUCED, START_HCORE, energy=_ev(1.0), charges=(0.20, -0.62, 0.42))
    assert choose_solutions([default, lower])[STATE_REDUCED].max_charge_difference == pytest.approx(0.32)


def test_a_start_that_did_not_finish_is_listed_and_not_read():
    default = _job(STATE_REDUCED, energy=_ev(0.0))
    died = _job(STATE_REDUCED, START_HCORE, energy=None, charges=None)
    no_table = _job(STATE_REDUCED, START_HUECKEL, energy=_ev(2.0), charges=None)
    solution = choose_solutions([default, died, no_table])[STATE_REDUCED]
    assert solution.chosen is default and solution.failed == (START_HCORE, START_HUECKEL) and solution.finished == 1


def test_a_state_whose_default_start_did_not_finish_is_absent_even_if_an_extra_one_did():
    """ORCA ends the run at the first job that fails, so this cannot be a real output; if it is ever seen, nothing is read from an extra start in place of the
    start the answer is defined against."""
    died = _job(STATE_REDUCED, energy=None, charges=None)
    extra = _job(STATE_REDUCED, START_HCORE, energy=_ev(1.0))
    assert STATE_REDUCED not in choose_solutions([died, extra])


def test_states_are_chosen_independently():
    jobs = [
        _job(STATE_N, energy=-101.0, charge=-1, multiplicity=1),
        _job(STATE_OXIDISED, energy=-100.5, charge=0),
        _job(STATE_N, START_HCORE, energy=-101.0 - 1.0 / HARTREE_TO_EV, charge=-1, multiplicity=1),
    ]
    solutions = choose_solutions(jobs)
    assert solutions[STATE_N].replaced_default and not solutions[STATE_OXIDISED].replaced_default


def test_the_jobs_of_a_plan_are_hashable_values():
    assert FukuiJob(STATE_N, 0, 1) == FukuiJob(STATE_N, 0, 1, START_DEFAULT)
    assert len({FukuiJob(STATE_N, 0, 1), FukuiJob(STATE_N, 0, 1)}) == 1
