"""Condensed Fukui functions from atomic populations of three states (two, and f- alone, for an anion).

Pure arithmetic, no ORCA -- the engine hands in the per-atom charges of the
neutral, the cation and the anion and this turns them into the four numbers
per atom, so all of it is testable without a quantum chemistry package, the
pattern `conceptual_dft` set. Which jobs a run has and which finished one it
reads are `chem/fukui_plan.py`'s.

**The finite-difference definitions** (Yang and Mortier's condensation of
the Fukui function), with ``q`` an atom's charge in the state named::

    f+  = q(N)   - q(N+1)      attack by a nucleophile: where an added electron goes
    f-  = q(N-1) - q(N)        attack by an electrophile: where a removed electron came from
    f0  = (f+ + f-) / 2        attack by a radical
    df  = f+ - f-              the dual descriptor: positive where an atom is
                               electrophilic, negative where it is nucleophilic

Each of ``f+`` and ``f-`` sums to one over the atoms, because the charges of
a state sum to its total charge; ``f0`` also sums to one and ``df`` to zero.
That is checked on the way in (`_STATE_SUM_TOLERANCE`), and a table that does
not sum to its state's charge is REFUSED rather than differenced: it means a
different table was read (the cation's for the anion's), and every number
after it would look reasonable.

**The states are vertical.** All three are at the neutral geometry, as the
delta-SCF hardness is (`conceptual_dft.from_delta_scf`), because the Fukui
function is the response of the electron density at FIXED nuclei. Relaxing
the ions would measure a different thing, and a smaller one.

**Why the charges are Hirshfeld's, and only Hirshfeld's.** ORCA 6.1.1 prints
five charge schemes for the same job, and the Fukui function is a DIFFERENCE
of two of them, so whatever the scheme does badly is magnified. Measured on
formaldehyde, propene and pyridine (B3LYP, geometry optimized at def2-SVP,
the three states at that geometry), changing only the basis from def2-SVP to
def2-SVPD moved the largest per-atom value like this:

    scheme      f+ moved (per atom)   f- moved    negative f-
    Hirshfeld   0.011 - 0.023         0.003 - 0.009   none
    Loewdin     0.067 - 0.107         0.055 - 0.104   none
    Mulliken    0.106 - 0.222         0.030 - 0.079   one (propene)
    MBIS        0.051 - 0.210         0.023 - 0.032   yes
    CHELPG      0.042 - 0.279         0.045 - 0.077   yes

The same measurement showed Mulliken putting 0.23 on EACH hydrogen of
formaldehyde and about the same on the oxygen as on the carbon, where
Hirshfeld puts 0.38 to 0.40 on the carbon, and showed formaldehyde carbon's
Mulliken charge going from +0.17 to +0.58 when diffuse functions were added.
A negative condensed value is not a physical response of an atom (the sum
rule is kept by another atom compensating); it is the partitioning's, and it
is kept and flagged rather than clipped. The exploration is recorded in
`benchmarks/fukui_gate/exploration.md`.

**The anion is usually UNBOUND, and this says so.** A neutral closed-shell
molecule of any size has a negative electron affinity at a basis set with no
diffuse functions (all six cases measured: -1.06 to -3.02 eV), so the
N+1 state is a state the basis set merely describes, and ``f+`` is the less
trustworthy half. It is computed anyway, with a caveat naming the energy,
because Hirshfeld's ``f+`` moved by at most 0.023 per atom with the diffuse
set on those three molecules; a refusal would remove ``f+`` from nearly every molecule.

**An anion has no f+.** Its N+1 state is a dianion, which no basis set binds in the gas phase, so for a species with
a negative charge the result holds ``f-`` alone (``condensed_fukui(..., anion=None)``) and says why; the N-1 state of an
anion is a neutral radical and is named so. See ``benchmarks/fukui_gate_2/DESIGN.md``.

**Diffuse functions are not the cure, and ``f+`` with them is not reproducible**
(``benchmarks/fukui_gate/PREREGISTRATION.md`` sections 11.4 and 11.6, measured after the
gate, deciding nothing). At 6-311+G** on the seven gate species ``f-`` agreed with the
published values in all 17 rows (largest difference 0.012) and ``f+`` in 6 of 17 (median
0.10 at B3LYP and 0.20 at HF, up to 0.33). Two things sit behind it. Seven of the 14 jobs
were refused because the anion's Hirshfeld charges summed 0.010 to 0.073 short of its
charge, which is ORCA's default integration grid missing part of a diffuse electron (on a
finer grid every anion came within 0.005, and at 6-31G** a finer grid changed no value).
And the unbound anion has more than one SCF solution there: of six cases probed, three had
a solution 0.6 to 1.0 eV below ORCA's default one, with ``f+`` differing by up to 0.31
between them, and for the fulminate and carbon dioxide anions at B3LYP/6-311+G** one
molecule embedded three ways gave two different anions (``f+`` on carbon 0.85 against
0.63, and 0.71 against 0.59) where ``f-`` agreed to 0.0001. At the 6-31G** levels the gate
decided on, the default solution was the lowest found in all 14 cases and all 14 reproduced across three embeddings to 0.0004.
The calculation therefore uses a finer grid in every job and, at a basis set with diffuse functions, reads the lowest of three starts of an anionic
state (``chem/fukui_plan.py``); ``f+`` there is still not validated.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from openchem.chem.fukui_plan import STATE_N, STATE_OXIDISED, STATE_REDUCED, Solution, state_name

#: How far the charges of a state may sit from the state's total charge, in
#: electrons. ORCA prints six decimals but integrates a density on a grid, so
#: a correct Hirshfeld table is off by a few 1e-6; a table of another state
#: is off by a whole electron. Between those two the margin is wide.
_STATE_SUM_TOLERANCE = 0.01

#: A state whose charges miss its charge by more than `_STATE_SUM_TOLERANCE` but by no more than this is the RIGHT state integrated
#: incompletely, not another state's table: another state's table is a whole electron away. Measured: seven anions at 6-311+G** were
#: 0.010 to 0.073 short at ORCA's default grid and 0.005 or less on a finer one (`benchmarks/fukui_gate/PREREGISTRATION.md` 11.5, 11.6),
#: while no neutral or cation state was ever more than 0.0002 off.
_INTEGRATION_SHORTFALL = 0.1

#: One Hartree in eV (the CODATA value `conceptual_dft` uses), to say by how much an anion lies above its neutral.
HARTREE_TO_EV = 27.211386245988


@dataclass(frozen=True)
class CondensedFukui:
    """The condensed values per atom, in the atom order the charges came in: four for a species with an N+1 state, f- alone for one without.

    `refused` rather than partial numbers, following `ConceptualDFT`: a
    difference of two tables that do not describe the states it names is not a
    reduced-quality Fukui function, it is a different quantity.
    """

    #: Empty for an anion (see `chem.fukui_plan`): f+, f0 and the dual descriptor all need the N+1 state.
    f_plus: tuple[float, ...] = ()
    f_minus: tuple[float, ...] = ()
    f_zero: tuple[float, ...] = ()
    dual: tuple[float, ...] = ()
    #: E(N+1) - E(N) in eV when both energies were given and the anion is not
    #: lower than the neutral (it is unbound), else None.
    unbound_anion_ev: float | None = None
    #: <S**2> of the N-1 and of the N+1 state as ORCA printed them (the cation's and the anion's, for a neutral species), or None when it printed none
    #: (a restricted job prints none, and a state that was not computed has none).
    cation_s_squared: float | None = None
    anion_s_squared: float | None = None
    #: The charge of the species as given: the N state's, from which every other state's name follows.
    reference_charge: int = 0
    #: The solution read for each state (`chem.fukui_plan.choose_solutions`), the default start's job where no extra start was lower. A state with extra
    #: starts that did not finish, or that were lower, is said so in the caveats; a state with one start only is here and says nothing.
    solutions: tuple[Solution, ...] = ()
    has_negative: bool = False
    refused: bool = False
    reason: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)

    @property
    def computes_f_plus(self) -> bool:
        return bool(self.f_plus)

    def __bool__(self) -> bool:
        return not self.refused


#: The sentence every result carries about WHAT was computed, first among its caveats: the scheme and that the
#: states are vertical. The conditions (unbound anion, a negative value) are added after it only when they hold.
_METHOD_CAVEAT = (
    "Hirshfeld charges (stockholder partitioning against neutral spherical atoms); each value is a "
    "difference of an atom's charge between two states at the neutral geometry (vertical)."
)


def open_shell_message(multiplicity: int) -> str:
    """Why a species with unpaired electrons is refused. One wording for the engine that raises it and the
    panel that checks before a job is queued."""
    return (
        f"Fukui functions need a closed-shell species (multiplicity 1); this has multiplicity "
        f"{multiplicity}. The cation and the anion of an open-shell molecule each have more than one "
        "spin state, and the Fukui function is not defined until one is chosen."
    )


def conformer_average_message() -> str:
    """Why a Fukui run cannot be averaged over conformers (the Boltzmann option)."""
    return (
        "Fukui functions are computed for one geometry and cannot be averaged over conformers: the averaging "
        "path keeps spectra and the lowest conformer's energies, so the per-atom values would be thrown away "
        "after every conformer had been run. Untick \"Average over all conformers\", or pick the conformer "
        "to use."
    )


def unbound_anion_sentence(gap_ev: float) -> str:
    """The caveat for an anion above the neutral, in the words the caveat, the panel and the docs share."""
    return (
        f"The anion is {gap_ev:.2f} eV ABOVE the neutral (a negative electron affinity), so it is an unbound "
        "state that this basis set only describes: f+ depends on the basis set more than f- does. Diffuse "
        "functions do not fix that: with them the anion can have more than one SCF solution, and f+ changed by up to "
        "0.31 between them in the cases measured, which is why, at a basis set with diffuse functions, the lowest of three starts is read. "
        "The calculator's help has the measurements."
    )


def _refuse(reason: str) -> CondensedFukui:
    return CondensedFukui(refused=True, reason=reason)


def f_plus_not_computed_sentence() -> str:
    """Why an anion's result holds f- alone, in the words the caveat, the panel and the docs share."""
    return (
        "f+, f0 and the dual descriptor were not computed: they need the N+1 state, and the N+1 state of an anion is a dianion, which "
        "no basis set binds in the gas phase, so a calculation of it returns the basis set's state and not the molecule's. "
        "f- (where an electron comes from) is the function that describes an anion."
    )


def _which_function(state: str) -> str:
    """The condensed function(s) a state's charges enter: f+ takes the N+1 state, f- the N-1 state, and both take the N state."""
    return {STATE_REDUCED: "f+", STATE_OXIDISED: "f-"}.get(state, "f+ and f-")


def _state_label(state: str, reference_charge: int) -> str:
    """"anion state", "neutral radical state": what a sentence calls the state of a species whose own charge is `reference_charge`."""
    charge = {STATE_N: reference_charge, STATE_OXIDISED: reference_charge + 1, STATE_REDUCED: reference_charge - 1}[state]
    return f"{state_name(charge)} state"


def start_sentence(solution: Solution, reference_charge: int) -> str:
    """What an extra start found, for a state whose lowest solution was not ORCA's default start's, in the words the caveat and the panel share."""
    return (
        f"The {_state_label(solution.state, reference_charge)} has more than one SCF solution. ORCA's default start reached one {solution.gain_ev:.2f} eV above "
        f"the lowest of the {solution.finished} starts that finished, and the lowest, from the {solution.chosen.start} start, was used. The two differ by up to "
        f"{solution.max_charge_difference:.3f} electrons in one atom's Hirshfeld charge, which is how far one atom's {_which_function(solution.state)} "
        "value moves between them; a value from a state with several solutions is not well defined."
    )


def failed_starts_sentence(solution: Solution, reference_charge: int) -> str:
    """The extra starts of a state that did not converge: said, because a choice among fewer starts is a weaker claim than the one made."""
    names = " and ".join(solution.failed)
    return (
        f"The {names} {'start' if len(solution.failed) == 1 else 'starts'} of the {_state_label(solution.state, reference_charge)} did not converge and "
        f"{'was' if len(solution.failed) == 1 else 'were'} not used; the choice was made among the {solution.finished} that finished."
    )


def start_notes(solutions: Sequence[Solution], reference_charge: int) -> list[str]:
    """The sentences about the SCF starts of a run, in state order: one for each state whose lowest solution was not the default start's, and one for each
    state with a start that did not finish. Empty for a run that had no extra starts, or whose extra starts all ended in the default's solution."""
    notes: list[str] = []
    for solution in solutions:
        if solution.replaced_default:
            notes.append(start_sentence(solution, reference_charge))
        if solution.failed:
            notes.append(failed_starts_sentence(solution, reference_charge))
    return notes


def _state_names(total_charge: int) -> tuple[str, str, str]:
    """(N, N-1, N+1) as a sentence calls them. A neutral species keeps the words the first release used ("neutral", "cation", "anion")."""
    first = "neutral" if total_charge == 0 else f"{state_name(total_charge)} (as given)"
    return (
        first,
        f"{state_name(total_charge + 1)} (N-1 electrons)",
        f"{state_name(total_charge - 1)} (N+1 electrons)",
    )


def _bad_table(name: str, charges, expected_charge: int) -> str:
    """Why `charges` cannot be the table of the state called `name`, or "" if it can."""
    if not charges:
        return f"The {name} state has no atomic charges."
    if any(not math.isfinite(value) for value in charges):
        return f"The {name} state has a charge that is not a finite number."
    total = sum(charges)
    off = abs(total - expected_charge)
    if off > _STATE_SUM_TOLERANCE and off <= _INTEGRATION_SHORTFALL:
        reason = (
            f"The {name} state's charges sum to {total:+.3f}, {off:.3f} electrons from its charge of {expected_charge:+d}. "
            "That is too small to be another state's table, so it is the numerical integration: Hirshfeld charges are integrals "
            "on a grid, and a few hundredths of an electron were left out."
        )
        if expected_charge < 0:
            reason += (
                " ORCA's default grid does not integrate a diffuse electron completely, which is what an unbound anion has at a basis "
                "set with diffuse functions; in the cases measured a finer grid brought the sum within 0.005, and a basis set without "
                "diffuse functions had no shortfall at all. This calculation already uses the finer grid, so a shortfall seen now is a larger one than those."
            )
        return reason
    if off > _STATE_SUM_TOLERANCE:
        return (
            f"The {name} state's charges sum to {total:+.3f} but that state has charge {expected_charge:+d}; "
            "the table read is not that state's, so the difference would be about something else."
        )
    return ""


def condensed_fukui(
    neutral: Sequence[float],
    cation: Sequence[float],
    anion: Sequence[float] | None = None,
    *,
    total_charge: int = 0,
    energy_neutral_hartree: float | None = None,
    energy_anion_hartree: float | None = None,
    cation_s_squared: float | None = None,
    anion_s_squared: float | None = None,
    solutions: Sequence[Solution] = (),
) -> CondensedFukui:
    """The condensed Fukui functions from the per-atom charges of N, N-1 and N+1 electrons, or f- alone when there is no N+1 state.

    `total_charge` is the N state's charge (0 for a neutral molecule); the N-1 state is checked against ``total_charge + 1`` and the N+1 state against
    ``total_charge - 1``. With ``anion=None`` only f- is computed, and the result says the other three were not (`f_plus_not_computed_sentence`). The two
    energies are optional and only decide whether the unbound-anion caveat is attached; `solutions` (from `chem.fukui_plan.choose_solutions`) only decide
    which sentences about the SCF starts are attached.
    """
    names = _state_names(total_charge)
    states = [(names[0], neutral, total_charge), (names[1], cation, total_charge + 1)]
    if anion is not None:
        states.append((names[2], anion, total_charge - 1))
    for name, charges, expected in states:
        problem = _bad_table(name, charges, expected)
        if problem:
            return _refuse(problem)
    sizes = [len(charges) for _name, charges, _expected in states]
    if len(set(sizes)) != 1:
        return _refuse(
            f"The {'three' if anion is not None else 'two'} states list different numbers of atoms "
            f"({', '.join(str(size) for size in sizes[:-1])} and {sizes[-1]}), so their charges cannot be matched atom to atom."
        )

    f_minus = tuple(c - n for n, c in zip(neutral, cation))
    if anion is not None:
        f_plus = tuple(n - a for n, a in zip(neutral, anion))
        f_zero = tuple((p + m) / 2.0 for p, m in zip(f_plus, f_minus))
        dual = tuple(p - m for p, m in zip(f_plus, f_minus))
    else:
        f_plus = f_zero = dual = ()

    caveats = [_METHOD_CAVEAT]
    if anion is None:
        caveats.append(f_plus_not_computed_sentence())
    unbound = None
    if anion is not None and energy_neutral_hartree is not None and energy_anion_hartree is not None:
        gap = (energy_anion_hartree - energy_neutral_hartree) * HARTREE_TO_EV
        if gap >= 0.0:
            unbound = gap
            caveats.append(unbound_anion_sentence(gap))
    caveats.extend(start_notes(solutions, total_charge))
    caveats.extend(
        spin_contamination_sentence(state, value)
        for state, value in contaminated_states(cation_s_squared, anion_s_squared, names=(state_name(total_charge + 1), state_name(total_charge - 1)))
    )
    has_negative = any(value < 0.0 for value in (*f_plus, *f_minus))
    if has_negative:
        caveats.append(
            "At least one condensed value is negative. That is the partitioning compensating, not an atom "
            "that loses density on gaining an electron; it is reported as it came out."
        )
    return CondensedFukui(
        f_plus=f_plus,
        f_minus=f_minus,
        f_zero=f_zero,
        dual=dual,
        unbound_anion_ev=unbound,
        cation_s_squared=cation_s_squared,
        anion_s_squared=anion_s_squared,
        reference_charge=total_charge,
        solutions=tuple(solutions),
        has_negative=has_negative,
        caveats=tuple(caveats) + (NOT_VALIDATED_SENTENCE,),
    )


#: <S**2> of a pure doublet, S(S+1) at S = 1/2. The ions of a closed-shell molecule are doublets, so this is what an uncontaminated one reads.
DOUBLET_S_SQUARED = 0.75

#: A state counts as spin-contaminated here above this <S**2>: about 10% over the doublet's 0.75. A threshold chosen for this calculation, not
#: validated; the one case measured (carbon monoxide's cation at HF/6-31G**, 0.967) is far above it and most DFT doublets measured are below it.
SPIN_CONTAMINATION_WARNING = 0.825

#: What every result says about its own standing. An earlier version of the calculation failed its preregistered check by 0.0014 on one of 54 numbers
#: (`benchmarks/fukui_gate/PREREGISTRATION.md` section 11); the current one (Fukui v2, `benchmarks/fukui_gate_2/DESIGN.md`) has not been checked against
#: published values, and its check is `benchmarks/fukui_gate_2/PREREGISTRATION.md`. It ships as EXPERIMENTAL, which is this sentence in the results.
NOT_VALIDATED_SENTENCE = (
    "Not validated: an earlier version of this calculation did not pass its preregistered check against published Hirshfeld values "
    "(52 of 54 numbers were within 0.02 and all 13 documented sites were reproduced; carbon monoxide's f- at "
    "HF/6-31G** was 0.0214 off, and that cation is spin-contaminated, which may be why), and this version has not been checked. "
    "The calculator's help has the details."
)


def spin_contamination_sentence(state: str, s_squared: float) -> str:
    """The caveat for an ion whose unrestricted density carries visible quartet character, in words the caveat and the panel share."""
    return (
        f"The {state} is spin-contaminated (<S^2> = {s_squared:.2f} where a pure doublet is {DOUBLET_S_SQUARED:.2f}): its unrestricted "
        "density carries some higher-spin character, which spin annihilation, as the published calculations used, would "
        "remove. In the one case measured (carbon monoxide's cation at HF/6-31G**) it moved a value by 0.02."
    )


def contaminated_states(
    cation: float | None, anion: float | None, *, names: tuple[str, str] = ("cation", "anion")
) -> list[tuple[str, float]]:
    """The ions (named) whose <S**2> is above `SPIN_CONTAMINATION_WARNING`, the N-1 state first. An unknown value is not a warning.

    `names` are what the N-1 and the N+1 state are called: a cation and an anion for a neutral species, a neutral radical for the N-1 state of an anion.
    """
    return [
        (state, value)
        for state, value in zip(names, (cation, anion))
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > SPIN_CONTAMINATION_WARNING
    ]


#: Two atoms with the same value to the six decimals ORCA prints are the same atom for this purpose (the two
#: hydrogens of formaldehyde), and are named together rather than one being picked by index.
_TIE = 1e-6

#: (property id, the label of the line saying where it is largest), in the order a summary reads them. The dual
#: descriptor has no line: its sign matters, its maximum does not.
_LARGEST = (
    ("orca.fukui_plus", "Largest f+ (attack by a nucleophile)"),
    ("orca.fukui_minus", "Largest f- (attack by an electrophile)"),
    ("orca.fukui_zero", "Largest f0 (attack by a radical)"),
)


def _where_largest(values: dict[int, float], symbols: list[str]) -> str:
    top = max(values.values())
    atoms = [index for index, value in sorted(values.items()) if value >= top - _TIE]
    # Numbered from 1, as the Atom Inspector titles an atom ("Atom 2 (O)"), because that is where the reader looks next.
    names = [f"{symbols[index] if index < len(symbols) else '?'} (atom {index + 1})" for index in atoms]
    return f"{' and '.join(names) if len(names) < 3 else ', '.join(names)}: {top:.3f}"


def summary_lines(datasets, symbols: list[str]) -> list[str]:
    """What a Fukui run says about itself in one place: where each value is largest, and the unbound-anion
    warning when there is one.

    `datasets` are the run's `PerAtomDataset`s (any order; only the `orca.fukui_*` ones are read) and `symbols`
    the elements in the atom order their indices refer to. Atoms are NAMED from 1, as the Atom Inspector names them. Plain strings, so a panel and a test read the same
    sentences. Empty when the run holds no Fukui dataset.
    """
    by_id = {dataset.property_id: dataset for dataset in datasets}
    named = [(by_id[pid], label) for pid, label in _LARGEST if pid in by_id and by_id[pid].values]
    if not named:
        return []
    lines = [f"Fukui functions (Hirshfeld, vertical) for {len(named[0][0].values)} atoms:"]
    lines.extend(f"{label}: {_where_largest(dataset.values, symbols)}" for dataset, label in named)
    provenance = named[0][0].provenance
    parameters = provenance.parameters if provenance is not None else {}
    if "orca.fukui_plus" not in by_id:
        lines.append(f_plus_not_computed_sentence())
    gap = parameters.get("unbound_anion_ev")
    if isinstance(gap, (int, float)) and not isinstance(gap, bool):
        lines.append(unbound_anion_sentence(float(gap)))
    note = parameters.get("start_note")
    if isinstance(note, str) and note:
        lines.append(note)
    reference = parameters.get("reference_charge")
    charge = reference if isinstance(reference, int) and not isinstance(reference, bool) else 0
    lines.extend(
        spin_contamination_sentence(state, value)
        for state, value in contaminated_states(
            parameters.get("cation_s_squared"), parameters.get("anion_s_squared"), names=(state_name(charge + 1), state_name(charge - 1))
        )
    )
    lines.append(NOT_VALIDATED_SENTENCE)
    return lines
