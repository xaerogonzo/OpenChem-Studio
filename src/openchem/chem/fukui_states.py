"""Which state of the cation f- is read from, and what else the search for states found. Pure: nothing here knows ORCA's syntax.

**The problem (Fukui v3).** f- is the difference of an atom's Hirshfeld charge between the neutral and its CATION, and a cation can have several states a few tenths
of an eV apart, one for each orbital the electron may have left. A calculation with one N-1 job reaches ONE of them, whichever its SCF relaxes into from the guess, and
measured on benzaldehyde (`benchmarks/fukui_gate_2/PREREGISTRATION.md` 11.4) that was not a function of the structure: 6 of 14 runs of the same molecule reached one state
and 8 the other, 0.145 eV apart and up to 0.05 apart in f-, depending on a rotation of one geometry, a 0.001 A displacement or the embedding it was optimized from.

**The rule** (`read_cation`), applied to every finished job of the N-1 state (the default one, the extra starts of an anion, and the hole starts of
`chem.fukui_plan`): two jobs reached the SAME STATE when their energies agree to `LEVEL_MARGIN_EV` and no atom's charge differs by more than `CHARGE_TOLERANCE`, and f-
is read from the LOWEST state. States within `LEVEL_MARGIN_EV` of the lowest that are nevertheless different (a degenerate level: the two components of an e1g hole in
benzene, which differ in f- by atom although they have one energy) are AVERAGED, so that the result does not depend on which component the SCF happened to find. Every other
state within `WINDOW_EV` of the lowest is REPORTED as competing, with how far its f- is from the one read, and the states beyond the window are counted.

**Where the numbers come from, and how little they are.** Eleven molecules were run with the default start and holes in the HOMO-1, HOMO-2 and HOMO-3 (the probe, 44 jobs,
all converged): jobs that reached one state agreed to 0.0004 in every atom's charge and to 0.004 eV, and the closest two DIFFERENT states were 0.018 eV apart (and 0.22 apart in a
charge), so `LEVEL_MARGIN_EV` (0.01 eV, the margin `chem.fukui_plan` already uses to tell two SCF solutions from one) and `CHARGE_TOLERANCE` (0.005) sit in the gap on both axes.
The window, `WINDOW_EV`, is NOT measured: it is the size of difference a B3LYP energy difference between cation states cannot be trusted to order, taken as 0.5 eV, which
includes the three molecules whose published numbers belong to a state 0.09 to 0.45 eV above the lowest and excludes the next closest (HCN's sigma state, 0.39 eV, is inside it; the
nearest outside was pyrrole's, at 0.84). The three of them were seen before the window was chosen, and the gate that tests this (`benchmarks/fukui_v3/PREREGISTRATION.md`) says so.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from openchem.chem.fukui_plan import START_DEFAULT, START_MARGIN_EV, STATE_OXIDISED, JobResult, hole_of_start

#: Two jobs are one ENERGY LEVEL when their energies differ by no more than this, in eV: the margin `chem.fukui_plan` uses to tell one SCF solution from two.
LEVEL_MARGIN_EV = START_MARGIN_EV

#: Two jobs are one STATE when, besides sharing a level, no atom's Hirshfeld charge differs by more than this, in electrons. Jobs that reached one state agreed to 0.0004;
#: different states 0.085 or more apart (`benchmarks/fukui_gate_2/artifacts/cation_states_probe.json`).
CHARGE_TOLERANCE = 0.005

#: A state this close above the lowest is reported as competing, in eV. An assumption with the reasons in the module docstring, not a measurement.
WINDOW_EV = 0.5

#: A hole start's neighbour is "close" when the neutral's orbital just below the last hole searched lies within the window and this much more of the HOMO, in eV: the
#: probe's ΔSCF gaps followed the neutral's orbital-energy gaps to within 0.062 eV (0.002 to 0.062), so the orbital gap stands in for the state gap before the state is computed.
ORBITAL_SLACK_EV = 0.1

#: One Hartree in eV (the CODATA value `conceptual_dft` uses), to compare energies in the unit the margins are in.
_HARTREE_TO_EV = 27.211386245988
#: `LEVEL_MARGIN_EV` in Hartree, the unit a job's energy is in.
_LEVEL_MARGIN_HARTREE = LEVEL_MARGIN_EV / _HARTREE_TO_EV


@dataclass(frozen=True)
class CationState:
    """One distinct state of the N-1 species that at least one job reached."""

    #: The lowest energy any job reached it at, in Hartree.
    energy_hartree: float
    #: How far above the lowest state found it is, in eV.
    above_ev: float
    #: Its Hirshfeld charges (the job read: the default start's if that reached it, else the lowest job's).
    charges: tuple[float, ...]
    #: The starts that reached it, in the order the jobs ran: `START_DEFAULT`, "HOMO-2", "HCore" ...
    starts: tuple[str, ...]
    s_squared: float | None = None
    #: How far its f- is from the f- that is read, at the atom where it is furthest, and which atom (from 0); 0.0 and -1 for the states that are read.
    max_difference: float = 0.0
    atom: int = -1


@dataclass(frozen=True)
class CationReading:
    """What a run's N-1 jobs say about the cation: the charges f- is read from, and what else was found."""

    #: The charges f- is differenced from: the lowest state's, or the mean of the degenerate level's states (`averaged`).
    charges: tuple[float, ...]
    energy_hartree: float
    #: The largest <S**2> of the states read, or None when none printed one.
    s_squared: float | None
    #: The states the charges come from: one, or several when the lowest level is degenerate.
    averaged: tuple[CationState, ...]
    #: Other states within `WINDOW_EV` of the lowest, nearest first, each with how far its f- is from the one read.
    competing: tuple[CationState, ...]
    #: How many further states lie beyond the window.
    farther: int
    #: How many jobs of this state finished, and which starts did not (named, in the order written): jobs that began and printed no energy and table.
    finished: int
    failed: tuple[str, ...]
    #: The hole offsets (`chem.fukui_plan.hole_start`) the run was written with, whether or not their jobs ran, and those among them whose job never began because ORCA ended
    #: the run at an earlier one that did not converge.
    holes_planned: tuple[int, ...]
    unreached: tuple[int, ...]
    #: The default start's job, whose solution is what a run without hole starts would have read.
    default: JobResult

    @property
    def degenerate(self) -> bool:
        """The lowest level holds more than one state, and `charges` is their mean."""
        return len(self.averaged) > 1

    @property
    def searched(self) -> bool:
        """The run was written with hole starts, so it looked (or tried to look) for states the default start does not reach."""
        return bool(self.holes_planned)

    @property
    def incomplete(self) -> bool:
        """Some job of the search did not finish or never began."""
        return bool(self.failed or self.unreached)


def _same_charges(first: Sequence[float], second: Sequence[float]) -> bool:
    return len(first) == len(second) and all(abs(a - b) <= CHARGE_TOLERANCE for a, b in zip(first, second))


def _biggest_difference(charges: Sequence[float], reference: Sequence[float]) -> tuple[float, int]:
    """(the largest |difference|, the atom it is at) between two charge tables of one molecule."""
    differences = [abs(a - b) for a, b in zip(charges, reference)]
    atom = max(range(len(differences)), key=differences.__getitem__) if differences else -1
    return (differences[atom], atom) if differences else (0.0, -1)


def read_cation(results: Sequence[JobResult], planned_holes: Sequence[int] = ()) -> CationReading | None:
    """The reading of the N-1 jobs among `results`, or None when none of them finished (the caller says which job and why).

    `planned_holes` are the hole offsets the input was written with, when the output says (ORCA echoes the input), so that a hole start whose job never began is not
    mistaken for a search that was never asked for.

    Deterministic and independent of the order the jobs ran in, apart from which of two jobs that reached the SAME state is the one whose charges are read, and that
    is the default start's when it is one of them, so a run with a single state gives exactly the charges a run without a search would have. A state's energy is the
    lowest any job reached it at.
    """
    jobs = [result for result in results if result.state == STATE_OXIDISED]
    finished = [job for job in jobs if job.complete]
    if not finished:
        return None
    default = next((job for job in finished if job.start == START_DEFAULT), finished[0])

    # Each group is the jobs that reached one state, lowest first; `finished` is in the order the jobs ran, which the starts of a state are reported in.
    groups: list[list[JobResult]] = []
    for job in sorted(finished, key=lambda job: job.energy_hartree):
        for group in groups:
            lead = group[0]
            if job.energy_hartree - lead.energy_hartree <= _LEVEL_MARGIN_HARTREE and _same_charges(job.charges, lead.charges):
                group.append(job)
                break
        else:
            groups.append([job])

    lowest = groups[0][0].energy_hartree

    def state_of(group: list[JobResult]) -> CationState:
        read = default if any(job is default for job in group) else group[0]
        return CationState(
            energy_hartree=group[0].energy_hartree,
            above_ev=(group[0].energy_hartree - lowest) * _HARTREE_TO_EV,
            charges=tuple(read.charges),
            starts=tuple(job.start for job in finished if any(job is member for member in group)),
            s_squared=read.s_squared,
        )

    states = [state_of(group) for group in groups]
    # The states are in ascending energy, so the lowest level is a prefix of them.
    level = [state for state in states if state.energy_hartree - lowest <= _LEVEL_MARGIN_HARTREE]
    charges = tuple(sum(values) / len(level) for values in zip(*(state.charges for state in level)))
    squares = [state.s_squared for state in level if state.s_squared is not None]

    def against_read(state: CationState) -> CationState:
        difference, atom = _biggest_difference(state.charges, charges)
        return CationState(state.energy_hartree, state.above_ev, state.charges, state.starts, state.s_squared, difference, atom)

    others = [against_read(state) for state in states[len(level):]]
    competing = tuple(state for state in others if state.above_ev <= WINDOW_EV)
    ran = {hole_of_start(job.start) for job in jobs} - {0}
    planned = (set(planned_holes) | ran) - {0}
    return CationReading(
        charges=charges,
        energy_hartree=lowest,
        s_squared=max(squares) if squares else None,
        averaged=tuple(level),
        competing=competing,
        farther=len(others) - len(competing),
        finished=len(finished),
        failed=tuple(job.start for job in jobs if not job.complete),
        holes_planned=tuple(sorted(planned)),
        unreached=tuple(sorted(planned - ran)),
        default=default,
    )
