"""Condensed Fukui functions from atomic populations of three states.

Pure arithmetic, no ORCA -- the engine hands in the per-atom charges of the
neutral, the cation and the anion and this turns them into the four numbers
per atom, so all of it is testable without a quantum chemistry package, the
pattern `conceptual_dft` set.

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
set; a refusal would remove ``f+`` from nearly every molecule.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: How far the charges of a state may sit from the state's total charge, in
#: electrons. ORCA prints six decimals but integrates a density on a grid, so
#: a correct Hirshfeld table is off by a few 1e-6; a table of another state
#: is off by a whole electron. Between those two the margin is wide.
_STATE_SUM_TOLERANCE = 0.01

#: One Hartree in eV (the CODATA value `conceptual_dft` uses), to say by how much an anion lies above its neutral.
HARTREE_TO_EV = 27.211386245988


@dataclass(frozen=True)
class CondensedFukui:
    """The four condensed values per atom, in the atom order the charges came in.

    `refused` rather than partial numbers, following `ConceptualDFT`: a
    difference of two tables that do not describe the states it names is not a
    reduced-quality Fukui function, it is a different quantity.
    """

    f_plus: tuple[float, ...] = ()
    f_minus: tuple[float, ...] = ()
    f_zero: tuple[float, ...] = ()
    dual: tuple[float, ...] = ()
    #: E(N+1) - E(N) in eV when both energies were given and the anion is not
    #: lower than the neutral (it is unbound), else None.
    unbound_anion_ev: float | None = None
    has_negative: bool = False
    refused: bool = False
    reason: str = ""
    caveats: tuple[str, ...] = field(default_factory=tuple)

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
        "state that this basis set only describes: f+ depends on the basis set more than f- does. "
        "Adding diffuse functions is the check."
    )


def _refuse(reason: str) -> CondensedFukui:
    return CondensedFukui(refused=True, reason=reason)


def _bad_table(name: str, charges, expected_charge: int) -> str:
    """Why `charges` cannot be the table of the state called `name`, or "" if it can."""
    if not charges:
        return f"The {name} state has no atomic charges."
    if any(not math.isfinite(value) for value in charges):
        return f"The {name} state has a charge that is not a finite number."
    total = sum(charges)
    if abs(total - expected_charge) > _STATE_SUM_TOLERANCE:
        return (
            f"The {name} state's charges sum to {total:+.3f} but that state has charge {expected_charge:+d}; "
            "the table read is not that state's, so the difference would be about something else."
        )
    return ""


def condensed_fukui(
    neutral: list[float],
    cation: list[float],
    anion: list[float],
    *,
    total_charge: int = 0,
    energy_neutral_hartree: float | None = None,
    energy_anion_hartree: float | None = None,
) -> CondensedFukui:
    """The condensed Fukui functions from the per-atom charges of N, N-1 and N+1 electrons.

    `total_charge` is the neutral state's charge (0 for a neutral molecule); the cation is checked against
    ``total_charge + 1`` and the anion against ``total_charge - 1``. The two energies are optional and only
    decide whether the unbound-anion caveat is attached.
    """
    states = (
        ("neutral", neutral, total_charge),
        ("cation (N-1 electrons)", cation, total_charge + 1),
        ("anion (N+1 electrons)", anion, total_charge - 1),
    )
    for name, charges, expected in states:
        problem = _bad_table(name, charges, expected)
        if problem:
            return _refuse(problem)
    if not (len(neutral) == len(cation) == len(anion)):
        return _refuse(
            "The three states list different numbers of atoms "
            f"({len(neutral)}, {len(cation)} and {len(anion)}), so their charges cannot be matched atom to atom."
        )

    f_plus = tuple(n - a for n, a in zip(neutral, anion))
    f_minus = tuple(c - n for n, c in zip(neutral, cation))
    f_zero = tuple((p + m) / 2.0 for p, m in zip(f_plus, f_minus))
    dual = tuple(p - m for p, m in zip(f_plus, f_minus))

    caveats = [_METHOD_CAVEAT]
    unbound = None
    if energy_neutral_hartree is not None and energy_anion_hartree is not None:
        gap = (energy_anion_hartree - energy_neutral_hartree) * HARTREE_TO_EV
        if gap >= 0.0:
            unbound = gap
            caveats.append(unbound_anion_sentence(gap))
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
        has_negative=has_negative,
        caveats=tuple(caveats),
    )


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
    gap = (provenance.parameters if provenance is not None else {}).get("unbound_anion_ev")
    if isinstance(gap, (int, float)) and not isinstance(gap, bool):
        lines.append(unbound_anion_sentence(float(gap)))
    return lines
