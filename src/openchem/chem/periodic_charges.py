"""Partial charges for a periodic solid, by Wilmer et al.'s extended charge equilibration (EQeq).

**What a result means:** these are the charges EQeq assigns to this structure — not "the charges of
this material". The method is an empirical equilibration built on measured ionisation energies, and
its own paper reports a mean |q - q_REPEAT| of 0.11 to 0.24 e against DFT-derived ESP charges on the
twelve MOFs it was published with. That number travels with every result.

**Validated against the source's own numbers.** TRIAGE check 2.9 reproduces all 3,452 atoms of those
twelve MOFs at their printed precision, and the pre-registration for this calculator is
`benchmarks/charges/periodic/calculator_preregistration.md`.

**Written from the equations, never ported.** The published `EQeq_v1_00.cpp` was read to resolve four
things the article does not state, each recorded in TRIAGE 2.9-A2 and in the comments below; no code
was copied, and this repository stays GPL-3.0-or-later.

**What it refuses rather than approximating:** a disordered structure, an element the sources do not
parameterise, an element at a neutral centre whose affinity the sources do not give, and a structure
with no unit cell.

**THE ANSWER DEPENDS ON WHICH CELL THE ATOMS ARE WRITTEN IN, and this reads them all into one.** A
direct lattice sum of a 1/r kernel is conditionally convergent, so its value depends on the region
summed: translating the *whole* structure changes nothing, and translating *one atom* by a cell edge
changes its pair terms by eV. Two of the twelve published structures place atoms up to 26 A outside
their cell, and their published charges are what those representatives give -- so `Crystal.expand`'s
wrapping, which a CIF's own coordinates get anyway, is what this computes, and `wrapped_sites` says
how many sites it moved. Pre-registration amendment 4-A1 measures all of it.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from openchem.domain.crystal import POSITION_TOLERANCE, Crystal

#: Where the two shipped tables live, resolved relative to this module so a frozen build finds them.
#: They are listed individually in `packaging/openchem.spec`; miss that and this raises
#: FileNotFoundError the first time anybody opens a CIF, having worked from a checkout.
_DATA = Path(__file__).resolve().parent / "data"

#: The published code's constants, which the article does not state (TRIAGE 2.9-A2).
#:
#: `EQeq_v1_00.cpp` carries k = 14.4 exactly and a "Coulomb scaling parameter" lambda = 1.2 -- the
#: 2/eps_R the paper's SI quotes -- so every pair term is lambda * k / 2 = 8.64 eV A. Reading the
#: article alone gives 14.399645 / 1.67 = 8.6226, and that 0.2% moves the third decimal of a charge.
COULOMB_EV_ANGSTROM = 14.4
#: See `COULOMB_EV_ANGSTROM`.
COULOMB_SCALING = 1.2
#: Hydrogen's affinity is overridden, the paper's own ad hoc parameter: "we found that setting
#: I0 = -2 eV for hydrogen (the measured value is +0.754 eV) ... led to reasonable charges".
HYDROGEN_AFFINITY_EV = -2.0
#: Unit cells summed in each direction. **The published charges are this setting**: at L = 3 ten of
#: MIL-47's 72 charges change in their third decimal (TRIAGE 3.9), so it is not a free parameter.
LATTICE_SHELLS = 2
#: The precision the method's own output carries, and the neutrality rule that follows it.
CHARGE_DIGITS = 3
#: Two expanded atoms closer than this are a disorder alternative, not two atoms.
MINIMUM_SEPARATION_ANGSTROM = 0.5

#: The structure carries partial occupancy or coincident sites, so which atoms are present is a
#: choice the file does not make. The validating corpus was fully ordered.
REFUSE_DISORDERED_STRUCTURE = "REFUSE_DISORDERED_STRUCTURE"
#: An element with no entry, or a charge centre deeper than the printed potentials.
REFUSE_ELEMENT_NOT_PARAMETERISED = "REFUSE_ELEMENT_NOT_PARAMETERISED"
#: An element at a neutral centre whose sources print no bound electron affinity ("<0").
REFUSE_NO_AFFINITY = "REFUSE_NO_AFFINITY"
#: A structure with no unit cell is not what this method computes.
REFUSE_NO_CELL = "REFUSE_NO_CELL"

#: What each refusal SAYS, keyed by its code, with `{detail}` filled in per structure.
#:
#: Separated from the codes above because a code is an identity a caller matches on and a message is
#: prose a reader reads: rewording one must not change the other. Every message names what would
#: resolve it where anything can -- a charge centre for an element with no affinity, for instance --
#: rather than only reporting that it stopped.
REFUSAL_MESSAGES = {
    REFUSE_DISORDERED_STRUCTURE: (
        "This structure has {detail}. EQeq charges are computed for a definite set of atoms, and "
        "choosing between disorder alternatives is not something the file decides."
    ),
    REFUSE_ELEMENT_NOT_PARAMETERISED: (
        "{detail} has no EQeq parameters in the ionisation table shipped with this application."
    ),
    REFUSE_NO_AFFINITY: (
        "{detail} is treated as a neutral atom here, and the source table prints no bound electron "
        "affinity for it, so its electronegativity cannot be formed. A charge centre for the "
        "element would resolve it; a zero would be invented."
    ),
    REFUSE_NO_CELL: "This structure has no unit cell, so there is nothing periodic to equilibrate.",
}

#: The paper's own comparison, carried on every result: EQeq is not a DFT charge.
MODEL_SCOPE = (
    "EQeq (Wilmer et al. 2012) on the unit cell as expanded, with a direct lattice sum over "
    "5 x 5 x 5 cells. Against DFT-derived REPEAT charges the method's own paper reports a mean "
    "absolute difference of 0.11 to 0.24 e per atom across its twelve MOFs."
)


def _load(name: str) -> dict:
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


def ionization_table() -> dict[str, dict]:
    return _load("eqeq_ionization.json")["elements"]


def charge_centres() -> dict[str, dict]:
    return _load("eqeq_charge_centres.json")["centres"]


@dataclass(frozen=True)
class PeriodicCharges:
    """Charges for one unit cell, or a refusal saying why there are none."""

    charges: tuple[float, ...] = ()
    elements: tuple[str, ...] = ()
    centres: dict[str, int] = field(default_factory=dict)
    centre_sources: dict[str, str] = field(default_factory=dict)
    adjusted_atoms: int = 0
    #: How many input sites the expansion moved into the cell. See the module docstring: a truncated
    #: direct sum is not invariant to moving one atom by a lattice vector, so this is the condition
    #: under which these charges and the ones a file's own representatives would give diverge.
    wrapped_sites: int = 0
    refusal: str = ""
    detail: str = ""

    @property
    def message(self) -> str:
        if not self.refusal:
            return ""
        return REFUSAL_MESSAGES[self.refusal].format(detail=self.detail)


def _outside_cell(position: tuple[float, float, float], tolerance: float = POSITION_TOLERANCE) -> bool:
    """Whether `Crystal.expand` moves this site, under that wrapping's own rule.

    `domain.crystal._wrap` snaps a coordinate within `tolerance` of EITHER boundary to 0.0 and folds
    everything else, so a coordinate just below 1 moves a whole cell edge while a coordinate just
    below 0 does not move at all. Expressed here rather than imported because the private helper
    answers "where does this go" and the question here is "did it go anywhere".
    """
    return any(not -tolerance < value < 1.0 - tolerance for value in position)


def _energies(element: str, table: dict[str, dict]) -> dict[int, float]:
    """I_n by n, with I_0 the electron affinity: the energy to go from a charge of -1 to 0."""
    entry = table[element]
    out = {stage: value for stage, value in enumerate(entry["ionization_potentials_eV"], start=1)}
    affinity = HYDROGEN_AFFINITY_EV if element == "H" else entry["electron_affinity_eV"]
    if affinity is not None:
        out[0] = affinity
    return out


def _electronegativity_and_hardness(element: str, centre: int, table: dict[str, dict]) -> tuple[float, float]:
    """chi = (I_{Q*+1} + I_{Q*}) / 2 and J = I_{Q*+1} - I_{Q*}, about the charge centre Q*."""
    available = _energies(element, table)
    if centre not in available or centre + 1 not in available:
        raise KeyError(centre)
    lower, upper = available[centre], available[centre + 1]
    return 0.5 * (upper + lower), upper - lower


def _orbital_overlap(hardness_pair: np.ndarray, distance: np.ndarray, coulomb: float) -> np.ndarray:
    """The short-range damping: exp(-(a r)^2) (2a - a^2 r - 1/r), with a = J_km / k.

    **THE FIRST COEFFICIENT IS 2a, AND THE ARTICLE'S EQ 64 PRINTS a** (TRIAGE 2.9-A2). Read as
    printed, this term contributes -0.235 at a bonded 1.5 A where the published code's contributes
    -0.0004, which is a spurious short-range term on every bonded pair: it moved IRMOF-1's worst
    atom from 0.0012 to 0.216 e.
    """
    safe = np.where(np.isfinite(distance), distance, 1.0)
    a = hardness_pair / coulomb
    return np.exp(-((a * safe) ** 2)) * (2.0 * a - a * a * safe - 1.0 / safe)


def _pair_matrix(positions: np.ndarray, vectors: np.ndarray, hardness: np.ndarray, shells: int) -> np.ndarray:
    """lambda (k/2) [1/r + E_O(r)] over every periodic image, an atom's own images included.

    The home-cell self term is skipped: an atom interacts with its images but not with itself.
    """
    count = len(positions)
    geometric_mean = np.sqrt(np.abs(np.outer(hardness, hardness)))
    total = np.zeros((count, count))
    # The separations are the same for every shell, so they are formed once and the shift added per
    # shell. Measured on HKUST-1's 624 atoms: rebuilding them inside the loop is 2.8 s of a 4.6 s
    # solve, and this is 1.5 s of a 3.2 s one. The arithmetic is unchanged -- the twelve published
    # structures reproduce byte-identically either way.
    separation = positions[:, None, :] - positions[None, :, :]
    shifted = np.empty_like(separation)
    for u, v, w in itertools.product(range(-shells, shells + 1), repeat=3):
        shift = u * vectors[0] + v * vectors[1] + w * vectors[2]
        np.add(separation, shift, out=shifted)
        distance = np.sqrt(np.einsum("ijk,ijk->ij", shifted, shifted))
        if u == v == w == 0:
            np.fill_diagonal(distance, np.inf)
        contribution = (COULOMB_SCALING * COULOMB_EV_ANGSTROM / 2.0) * (
            1.0 / distance + _orbital_overlap(geometric_mean, distance, COULOMB_EV_ANGSTROM))
        total += np.where(np.isfinite(distance), contribution, 0.0)
    return total


def round_charges(charges: np.ndarray, digits: int = CHARGE_DIGITS) -> tuple[np.ndarray, int]:
    """The published post-processing: round, then restore neutrality by moving the FIRST atoms.

    Returns the rounded charges and how many atoms the neutrality step moved, because that count is
    a thing a reader should see rather than a silent adjustment.
    """
    factor = 10.0 ** digits
    rounded = np.round(charges * factor) / factor
    total = rounded.sum()
    if abs(total) < 0.5 / factor:
        return rounded, 0
    count = int(abs(total * factor) + 0.5)
    rounded = rounded.copy()
    rounded[:count] += (-1.0 if total > 0 else 1.0) / factor
    return np.round(rounded * factor) / factor, count


def compute_periodic_charges(crystal: Crystal, *, shells: int = LATTICE_SHELLS) -> PeriodicCharges:
    """EQeq charges for every atom of one unit cell, or a refusal."""
    if crystal.lattice is None or crystal.lattice.volume <= 0:
        return PeriodicCharges(refusal=REFUSE_NO_CELL)
    atoms = crystal.expand()
    if not atoms:
        return PeriodicCharges(refusal=REFUSE_NO_CELL)

    partial = sorted({atom.site_label for atom in atoms if atom.occupancy < 1.0})
    if partial:
        listed = ", ".join(partial[:3]) + (" and others" if len(partial) > 3 else "")
        return PeriodicCharges(refusal=REFUSE_DISORDERED_STRUCTURE,
                               detail=f"{len(partial)} site(s) with partial occupancy ({listed})")

    wrapped = sum(1 for site in crystal.sites if _outside_cell(site.position))
    elements = tuple(atom.element for atom in atoms)
    positions = np.array([crystal.lattice.to_cartesian(*atom.position) for atom in atoms], dtype=float)
    vectors = np.array([crystal.lattice.to_cartesian(*basis) for basis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))])

    close = _closest_pair(positions, vectors)
    if close is not None:
        first, second, separation = close
        return PeriodicCharges(refusal=REFUSE_DISORDERED_STRUCTURE,
                               detail=f"atoms {first + 1} and {second + 1} only {separation:.3f} A apart")

    table = ionization_table()
    centre_table = charge_centres()
    missing = sorted({element for element in elements if element not in table})
    if missing:
        return PeriodicCharges(refusal=REFUSE_ELEMENT_NOT_PARAMETERISED, detail=", ".join(missing))

    centres, sources = {}, {}
    for element in sorted(set(elements)):
        entry = centre_table.get(element)
        centres[element] = int(entry["centre"]) if entry else 0
        sources[element] = entry["from"] if entry else "not listed; a neutral centre is assumed"

    parameters = {}
    for element in centres:
        try:
            parameters[element] = _electronegativity_and_hardness(element, centres[element], table)
        except KeyError:
            if centres[element] == 0 and table[element]["electron_affinity_eV"] is None:
                return PeriodicCharges(refusal=REFUSE_NO_AFFINITY, detail=element)
            return PeriodicCharges(
                refusal=REFUSE_ELEMENT_NOT_PARAMETERISED,
                detail=f"{element} at a charge centre of {centres[element]:+d}")

    chi = np.array([parameters[element][0] for element in elements])
    hardness = np.array([parameters[element][1] for element in elements])
    count = len(elements)
    matrix = np.zeros((count + 1, count + 1))
    matrix[:count, :count] = _pair_matrix(positions, vectors, hardness, shells)
    matrix[np.diag_indices(count)] += hardness
    matrix[:count, count] = -1.0
    matrix[count, :count] = 1.0
    right_hand_side = np.zeros(count + 1)
    right_hand_side[:count] = -chi + hardness * np.array([centres[element] for element in elements], dtype=float)
    solved = np.linalg.solve(matrix, right_hand_side)[:count]
    rounded, adjusted = round_charges(solved)
    return PeriodicCharges(charges=tuple(float(value) for value in rounded), elements=elements,
                           centres=centres, centre_sources=sources, adjusted_atoms=adjusted,
                           wrapped_sites=wrapped)


def _closest_pair(positions: np.ndarray, vectors: np.ndarray) -> tuple[int, int, float] | None:
    """The closest pair under the minimum image convention, when it is closer than two atoms can be."""
    inverse = np.linalg.inv(vectors.T)
    delta = positions[:, None, :] - positions[None, :, :]
    fractional = delta @ inverse.T
    fractional -= np.round(fractional)
    distance = np.linalg.norm(fractional @ vectors, axis=-1)
    np.fill_diagonal(distance, np.inf)
    first, second = np.unravel_index(np.argmin(distance), distance.shape)
    separation = float(distance[first, second])
    if separation >= MINIMUM_SEPARATION_ANGSTROM:
        return None
    return int(first), int(second), separation
