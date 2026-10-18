"""Which ORCA jobs a Fukui calculation runs, and which of the finished ones it reads. Pure: nothing here knows ORCA's syntax.

The condensed Fukui functions are differences of an atom's Hirshfeld charge between states of the SAME nuclei, so a run is a list of single
points at one geometry, each a state of the species (`STATE_N`, `STATE_OXIDISED`, `STATE_REDUCED`) started from some initial guess (`FukuiJob`).
`plan_fukui` says which jobs to write, and `choose_solutions` says which finished ones to read. Both rules come from measurements, listed where
each is used (`benchmarks/fukui_gate/PREREGISTRATION.md` 11.5, 11.6 and `benchmarks/fukui_gate_2/DESIGN.md`).

**An anion has no f+ here.** Its N+1 state is a dianion, which no basis set binds in the gas phase: the state a calculation reaches is the
basis set's, not the molecule's. The three anions the first gate decided on were computed against such a state, and at a diffuse basis it is
the state whose Hirshfeld charges fell 0.010 to 0.073 short of the dianion's charge and whose f+ changed by up to 0.31 between two SCF solutions. So for
a species with a negative charge the plan holds two states and the result holds f- only, where f- is the answer to the question one asks of an
anion (where an electron comes from), and the other three numbers are said not to have been computed.

**Extra starts, for a basis set with diffuse functions.** An anionic state at such a basis can have more than one SCF solution, and ORCA's default
start, inside a compound input, is the previous job's orbitals, so the solution it reaches depends on the path to it. Of six cases probed at 6-311+G**
the default start's solution was 0.6 to 1.0 eV above one that another start found in three, and where another start lowered the energy it moved f+ by
up to 0.31; HCore or Hueckel found the lowest in all six. At the 6-31G** levels the first gate decided on, and for bound anions at 6-31+G*, every
start ended in the same solution to within 0.004 eV, so a basis with no diffuse functions gets no extra start and a run costs what it did.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: The species as given: the state whose charge is the input's, closed shell.
STATE_N = "N"
#: One electron fewer (a doublet): where f- comes from.
STATE_OXIDISED = "N-1"
#: One electron more (a doublet): where f+ comes from, and the state an anion does not have.
STATE_REDUCED = "N+1"

#: ORCA's own initial guess, which inside a compound input reads the previous job's orbitals for every job but the first.
START_DEFAULT = "default"
#: The core-Hamiltonian guess.
START_HCORE = "HCore"
#: The extended-Hueckel guess.
START_HUECKEL = "Hueckel"
#: The extra starts an anionic state gets at a basis with diffuse functions, in the order they are written.
EXTRA_STARTS = (START_HCORE, START_HUECKEL)

#: A start replaces ORCA's default one only if its energy is LOWER by more than this. Two starts that reach the same solution differ by
#: the SCF's own convergence (0.004 eV in every bound or gated case measured), and a choice made on that would be a choice made on noise; the
#: solutions that mattered were 0.6 eV or more apart.
START_MARGIN_EV = 0.01

#: One Hartree in eV (the CODATA value `conceptual_dft` uses).
_HARTREE_TO_EV = 27.211386245988

#: The families of basis set that carry diffuse functions, by the spelling ORCA accepts: a Pople "+" or "++" before the G (6-31+G*, 6-311++G**); the
#: Dunning augmentations (aug-cc-pVDZ, d-aug-, heavy-aug-, the calendar sets jun-, jul-, may-, apr-, maug-); the minimally augmented ma-def2 sets and the
#: Ahlrichs def2 sets whose name ends in D (def2-SVPD, def2-TZVPPD). Anything else is taken to have none, which is the safe error: it costs the extra
#: starts a run would have had, and the standing caveat about f+ at a diffuse basis is the same.
_DIFFUSE_BASIS = re.compile(
    r"(?:\d-\d+\+{1,2}g)"
    r"|(?:(?:^|[\s(,_/-])(?:d-)?(?:heavy-)?(?:aug|jun|jul|may|apr|maug)-)"
    r"|(?:(?:^|[\s(,_/-])ma-def2)"
    r"|(?:def2-[sdtq]z?vp{1,2}d(?![a-z0-9]))",
    re.IGNORECASE,
)


def has_diffuse_functions(method_basis: str) -> bool:
    """Whether the basis set named in `method_basis` ("B3LYP 6-31+G*") is one that carries diffuse functions."""
    return bool(_DIFFUSE_BASIS.search(method_basis or ""))


@dataclass(frozen=True)
class FukuiJob:
    """One single point of a Fukui run."""

    state: str
    charge: int
    multiplicity: int
    #: `START_DEFAULT`, or the extra start that replaces ORCA's default one for this job.
    start: str = START_DEFAULT


@dataclass(frozen=True)
class FukuiPlan:
    """The jobs of one Fukui run, in the order they are written: every state's default start first, then the extra starts.

    The order is load-bearing. ORCA ends the whole compound input at the first job that does not converge, so the jobs the answer cannot do without
    come first and an extra start that fails costs nothing but itself.
    """

    charge: int
    jobs: tuple[FukuiJob, ...]

    @property
    def computes_f_plus(self) -> bool:
        return any(job.state == STATE_REDUCED for job in self.jobs)


def state_charges(charge: int) -> dict[str, tuple[int, int]]:
    """state -> (charge, multiplicity) of a closed-shell species of `charge`: the ions of a closed shell are doublets."""
    return {STATE_N: (charge, 1), STATE_OXIDISED: (charge + 1, 2), STATE_REDUCED: (charge - 1, 2)}


def state_of(reference_charge: int, charge: int, multiplicity: int) -> str | None:
    """The state a job with this charge and multiplicity is, for a species whose own charge is `reference_charge`, or None for one that is no state of it."""
    for state, (state_charge, state_multiplicity) in state_charges(reference_charge).items():
        if (charge, multiplicity) == (state_charge, state_multiplicity):
            return state
    return None


def state_name(charge: int) -> str:
    """What a state of this total charge is called in a sentence: the words the first release used for a neutral species' states, extended."""
    names = {2: "dication", 1: "cation", 0: "neutral radical", -1: "anion", -2: "dianion"}
    return names.get(charge, f"state of charge {charge:+d}")


def plan_fukui(charge: int, multiplicity: int, *, diffuse: bool) -> FukuiPlan:
    """The jobs for a species of this charge, or ValueError for one with unpaired electrons.

    A species with a negative charge gets two states (see the module docstring); every other gets three. At a basis with diffuse functions each ANIONIC
    state (a total charge below zero: the N+1 state of a neutral or cation, and the N state of an anion) also gets `EXTRA_STARTS`, after all the default ones.
    """
    if multiplicity != 1:
        raise ValueError(f"A Fukui plan needs a closed-shell species (multiplicity 1); this has multiplicity {multiplicity}.")
    states = state_charges(charge)
    wanted = [STATE_N, STATE_OXIDISED] + ([STATE_REDUCED] if charge >= 0 else [])
    jobs = [FukuiJob(state, *states[state]) for state in wanted]
    if diffuse:
        for state in wanted:
            state_charge, state_multiplicity = states[state]
            if state_charge < 0:
                jobs.extend(FukuiJob(state, state_charge, state_multiplicity, start) for start in EXTRA_STARTS)
    return FukuiPlan(charge=charge, jobs=tuple(jobs))


@dataclass(frozen=True)
class JobResult:
    """What one finished job of a run printed: its state, how it was started, and the three things read from it."""

    state: str
    charge: int
    multiplicity: int
    start: str
    #: None when ORCA printed no final energy for the job (it did not converge, or the run ended before it).
    energy_hartree: float | None
    #: The Hirshfeld charges in atom order, or None when ORCA printed no table.
    charges: tuple[float, ...] | None
    #: <S**2> as ORCA printed it (an unrestricted job only), else None.
    s_squared: float | None = None

    @property
    def complete(self) -> bool:
        return self.energy_hartree is not None and self.charges is not None


@dataclass(frozen=True)
class Solution:
    """The job a state is READ from, and what the other starts of that state said about the choice."""

    state: str
    chosen: JobResult
    #: The default start's job, whose solution is what the run would have given without extra starts.
    default: JobResult
    #: Starts of this state that ended the run without an energy and a table (named, in the order written).
    failed: tuple[str, ...] = ()
    #: How many jobs of this state finished (the default one included).
    finished: int = 1

    @property
    def gain_ev(self) -> float:
        """How far BELOW the default start's solution the chosen one is, in eV; 0 when the default was kept."""
        return (self.default.energy_hartree - self.chosen.energy_hartree) * _HARTREE_TO_EV

    @property
    def max_charge_difference(self) -> float:
        """The largest change, over the atoms, in this state's Hirshfeld charge between the default solution and the chosen one: the most
        the f of this state moves at any atom for having taken the lower solution."""
        return max(abs(a - b) for a, b in zip(self.default.charges, self.chosen.charges))

    @property
    def replaced_default(self) -> bool:
        return self.chosen is not self.default


def choose_solutions(results: Sequence[JobResult]) -> dict[str, Solution]:
    """state -> the solution to read, for every state whose DEFAULT start finished.

    The default start's job is kept unless another start of the same state finished more than `START_MARGIN_EV` below it, and then the lowest is read:
    the variational choice among SCF solutions, which is deterministic and does not depend on which guess was tried first. A state whose default start did
    not finish is absent from the answer, and the caller says which job it was.
    """
    solutions: dict[str, Solution] = {}
    for state in dict.fromkeys(result.state for result in results):
        of_state = [result for result in results if result.state == state]
        default = next((r for r in of_state if r.start == START_DEFAULT and r.complete), None)
        if default is None:
            continue
        others = [r for r in of_state if r is not default]
        finished = [r for r in others if r.complete]
        threshold = default.energy_hartree - START_MARGIN_EV / _HARTREE_TO_EV
        lower = [r for r in finished if r.energy_hartree < threshold]
        chosen = min(lower, key=lambda r: r.energy_hartree) if lower else default
        solutions[state] = Solution(
            state=state,
            chosen=chosen,
            default=default,
            failed=tuple(r.start for r in others if not r.complete),
            finished=1 + len(finished),
        )
    return solutions
