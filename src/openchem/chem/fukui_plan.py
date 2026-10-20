"""Which ORCA jobs a Fukui calculation runs, and which of the finished ones it reads. Pure: nothing here knows ORCA's syntax.

The condensed Fukui functions are differences of an atom's Hirshfeld charge between states of the SAME nuclei, so a run is a list of single
points at one geometry, each a state of the species (`STATE_N`, `STATE_OXIDISED`, `STATE_REDUCED`) started from some initial guess (`FukuiJob`).
`plan_fukui` says which jobs to write, and `choose_solutions` says which finished ones to read. Both rules come from measurements, listed where
each is used (`benchmarks/fukui_gate/PREREGISTRATION.md` 11.5, 11.6 and `benchmarks/fukui_gate_2/DESIGN.md`).

**An anion's f+ comes from a dianion, and is the least trustworthy number here.** Its N+1 state is a dianion, which no basis set binds in the gas
phase: the state a calculation reaches is the basis set's, not the molecule's. The three anions the first gate decided on were computed against such a
state (and their f+ reproduced the published values to 0.0101 at the 6-31G** levels), and at a diffuse basis it is the state whose Hirshfeld charges fell
0.010 to 0.073 short of the dianion's charge at ORCA's default grid and whose f+ changed by up to 0.31 between two SCF solutions. Fukui v2 left it out (its
second gate decided f- alone for an anion); it is back at Alex's request, as the LAST job of the plan, because f- (where an electron comes from, the function
that describes an anion) needs only the anion and the neutral radical it becomes: a dianion that does not converge, or whose Hirshfeld table does not sum to
its charge, then costs f+, f0 and the dual descriptor and nothing else (`chem.fukui.condensed_fukui` gives f- alone and says why).

**Extra starts, for a basis set with diffuse functions.** An anionic state at such a basis can have more than one SCF solution, and ORCA's default
start, inside a compound input, is the previous job's orbitals, so the solution it reaches depends on the path to it. Of six cases probed at 6-311+G**
the default start's solution was 0.6 to 1.0 eV above one that another start found in three, and where another start lowered the energy it moved f+ by
up to 0.31; HCore or Hueckel found the lowest in all six. At the 6-31G** levels the first gate decided on, and for bound anions at 6-31+G*, every
start ended in the same solution to within 0.004 eV, so a basis with no diffuse functions gets no extra start and a run costs what it did.

**Hole starts, for the N-1 state (Fukui v3).** The cation of a molecule can have several states a few tenths of an eV apart, one for each orbital the electron
may have left, and ORCA's default start reaches ONE of them: the one that empties the neutral's HOMO, and then whichever the SCF relaxes into. Measured
(`benchmarks/fukui_gate_2/PREREGISTRATION.md` 11.4), the state it reached for benzaldehyde was not a function of the structure: 6 of 14 runs reached one state
and 8 the other, 0.145 eV apart and 0.05 apart in f-, depending on a rotation of the molecule, a displacement of 0.001 A or the embedding it was optimized from.
A hole start begins the cation from the NEUTRAL's orbitals with the electron taken from the HOMO-k instead (`%scf Rotate {HOMO-k, HOMO, 90, 1, 1} end` on the
beta orbitals, the procedure of that probe), so that the lowest of several states can be read and a close second reported (`chem.fukui_states`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: The species as given: the state whose charge is the input's, closed shell.
STATE_N = "N"
#: One electron fewer (a doublet): where f- comes from.
STATE_OXIDISED = "N-1"
#: One electron more (a doublet): where f+ comes from. For an anion it is a dianion, which no basis set binds (see the module docstring).
STATE_REDUCED = "N+1"

#: ORCA's own initial guess, which inside a compound input reads the previous job's orbitals for every job but the first.
START_DEFAULT = "default"
#: The core-Hamiltonian guess.
START_HCORE = "HCore"
#: The extended-Hueckel guess.
START_HUECKEL = "Hueckel"
#: The extra starts an anionic state gets at a basis with diffuse functions, in the order they are written.
EXTRA_STARTS = (START_HCORE, START_HUECKEL)

#: The orbitals below the HOMO that the cation search puts a hole in: the HOMO-1, the HOMO-2 and the HOMO-3, each a job that starts from the NEUTRAL's orbitals
#: (the default N-1 job already empties the HOMO). Three is what the probe that found the problem used (the default start and holes in the HOMO-1, HOMO-2 and
#: HOMO-3), and on the eleven molecules it ran a hole in the HOMO-3 ended in a state one of the others had already found. That is a choice made from eleven
#: small molecules and not a derived number: a molecule with more orbitals close to its HOMO is said to have been searched only so far (`chem.fukui_states`).
HOLE_OFFSETS = (1, 2, 3)

#: A hole start's name as `hole_start` writes it ("HOMO-2"), which is also how a job's start is named once it has been read back out of ORCA's output.
_HOLE_START = re.compile(r"HOMO-(\d+)")


def hole_start(offset: int) -> str:
    """The name of the start that puts the N-1 state's hole in the orbital `offset` below the HOMO."""
    return f"HOMO-{offset}"


def hole_of_start(start: str) -> int:
    """How far below the HOMO a start's hole is, or 0 for a start that is not a hole start (`START_DEFAULT`, `START_HCORE`, ...)."""
    match = _HOLE_START.fullmatch(start or "")
    return int(match.group(1)) if match else 0


#: The orbitals of the noble-gas core of an atom, by the largest atomic number of its period: none for hydrogen and helium, the 1s for lithium to neon, 1s 2s 2p for
#: sodium to argon, and the argon core for potassium to krypton. A hole in one of these is a core-ionized state, thirty eV or more up, which is nothing a Fukui function means.
_CORE_ORBITALS = ((2, 0), (10, 1), (18, 5), (36, 9))

#: The heaviest element the search is written for. Beyond krypton the basis sets that carry the app's methods use an effective core potential, which takes
#: electrons out of the orbital count, so the HOMO's number cannot be read off the species' electron count.
_HEAVIEST_ELEMENT = 36


@dataclass(frozen=True)
class HoleSearch:
    """Which holes a species can be searched with, and why none if there are none."""

    offsets: tuple[int, ...]
    #: A phrase that completes "The search for other cation states was not run: ...", or "" when `offsets` is not empty.
    reason: str = ""
    #: The HOMO's orbital number (ORCA numbers from 0) when there are offsets, which is what a hole job swaps the orbital `homo - offset` with; -1 otherwise.
    homo: int = -1


def searchable_holes(atomic_numbers: Sequence[int], charge: int, offsets: Sequence[int] = HOLE_OFFSETS) -> HoleSearch:
    """The hole offsets (`HOLE_OFFSETS`) whose orbital is a VALENCE orbital of this species, or the reason it has none.

    The HOMO of a closed-shell species with ``n`` electrons is orbital ``n/2 - 1`` (ORCA numbers from 0), which is how a job names the orbital to swap
    without the neutral's output in hand: the plan is written before anything runs. The count is exact only where no electron is taken out of the problem, so
    an element beyond krypton, whose basis sets carry a core potential, gets no search. A hole offset is dropped when it reaches into the core.
    """
    if any(number > _HEAVIEST_ELEMENT for number in atomic_numbers):
        return HoleSearch((), "it has an element heavier than krypton, whose basis set may replace its core electrons, so the HOMO's number cannot be read off the electron count")
    electrons = sum(atomic_numbers) - charge
    if electrons % 2 or electrons < 2:
        return HoleSearch((), "its electron count is not that of a closed shell")
    core = sum(next(orbitals for largest, orbitals in _CORE_ORBITALS if number <= largest) for number in atomic_numbers)
    homo = electrons // 2 - 1
    usable = tuple(offset for offset in offsets if homo - offset >= core)
    if not usable:
        return HoleSearch((), "it has no occupied valence orbital below its HOMO")
    return HoleSearch(usable, homo=homo)

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
    #: `START_DEFAULT`, or the extra start that replaces ORCA's default one for this job (`hole_start(k)` for a hole start).
    start: str = START_DEFAULT
    #: For a hole start, how far below the HOMO the hole is (`hole_start`); 0 for every other job.
    hole: int = 0


@dataclass(frozen=True)
class FukuiPlan:
    """The jobs of one Fukui run, in the order they are written (`plan_fukui`).

    The order is load-bearing. ORCA ends the whole compound input at the first job that does not converge, so the jobs the answer cannot do without
    come first and an extra start, a hole start, or the N+1 state of an anion, that fails costs nothing but itself.
    """

    charge: int
    jobs: tuple[FukuiJob, ...]


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


def plan_fukui(charge: int, multiplicity: int, *, diffuse: bool, anion_f_plus: bool = True, holes: Sequence[int] = ()) -> FukuiPlan:
    """The jobs for a species of this charge, or ValueError for one with unpaired electrons.

    **`anion_f_plus=False` leaves the N+1 state out of a species with a negative charge** (its dianion, and the extra starts of it): the plan Fukui v2 had, which
    its second gate tested, and the one a person who switched f+ of an anion off in Settings asks for. A neutral species or a cation always has its N+1 state.

    **`holes` are the hole starts of the N-1 state** (`hole_start`, from `searchable_holes`): one job each, started from the NEUTRAL's orbitals, so that the lowest
    of several cation states can be read. With none (the default) the plan is the one Fukui v2 and the anion's f+ had, job for job.

    Every species gets three states: N and N-1, which f- needs, then N+1, which f+ needs. At a basis with diffuse functions each ANIONIC state (a total
    charge below zero: the N+1 state of a neutral, and the N and N-1 states of an anion or a dianion, and the N+1 state of an anion) also gets
    `EXTRA_STARTS` after its default job. **The jobs the answer needs come first and each optional job after everything it is optional for**: N, N-1 and the
    extra starts of those two, and then, for a neutral species or a cation, whose N+1 state is needed, the N+1 state and its extra starts and the hole starts
    last, since a hole start that does not converge ends the run and f+ must not be lost to it; but for an anion, whose dianion is optional and is the one job here
    that is a state the basis set merely describes, the hole starts (which make f-, the function that describes an anion, reproducible) come BEFORE the dianion.
    """
    if multiplicity != 1:
        raise ValueError(f"A Fukui plan needs a closed-shell species (multiplicity 1); this has multiplicity {multiplicity}.")
    states = state_charges(charge)

    def job(state: str, start: str = START_DEFAULT, hole: int = 0) -> FukuiJob:
        return FukuiJob(state, *states[state], start, hole)

    def extra_starts(state: str) -> list[FukuiJob]:
        return [job(state, start) for start in EXTRA_STARTS] if diffuse and states[state][0] < 0 else []

    hole_jobs = [job(STATE_OXIDISED, hole_start(offset), offset) for offset in dict.fromkeys(holes)]
    jobs = [job(STATE_N), job(STATE_OXIDISED), *extra_starts(STATE_N), *extra_starts(STATE_OXIDISED)]
    if charge < 0:
        jobs += hole_jobs
        if anion_f_plus:
            jobs += [job(STATE_REDUCED), *extra_starts(STATE_REDUCED)]
    else:
        jobs += [job(STATE_REDUCED), *extra_starts(STATE_REDUCED), *hole_jobs]
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
