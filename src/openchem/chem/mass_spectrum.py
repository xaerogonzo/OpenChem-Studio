"""The isotope envelope of an ion, by convolution. Deterministic.

No fitting, no model, no constant nobody sourced -- given a formula and an
ion, this is arithmetic over a tabulated isotope distribution, and two
people doing it by hand get the same answer.

**WHERE THE NUMBERS COME FROM.** RDKit's own periodic table
(`GetAbundanceForIsotope` / `GetMassForIsotope`), which is the source
`chem/element_reference.isotopes_for` already reads and which
`data/elements.json` already declares with `_source_key = "rdkit"`. That
makes the result depend on RDKit's table, so the version is recorded in
provenance: "RDKit says it" is not immutable across releases.

**THE ADDUCT GOES THROUGH THE SAME CONVOLUTION AS THE MOLECULE**, which is
the entire reason `IonSpecies` carries a composition rather than a mass. A
natural-abundance `AtomDelta` contributes its own envelope -- chloride is
3:1, potassium is 6.7% 41K -- and a nuclide-specific one contributes a
single mass.

**THE ELECTRON, ONCE, IN ONE PLACE.**

    [M+H]+   = M + mass(1H atom)  - m_e
    [M+Na]+  = M + mass(Na atom)  - m_e
    [M-H]-   = M - mass(1H atom)  + m_e
    m/z      = (M_neutral + sum of neutral-atom masses - charge*m_e) / |charge|

A composition delta is neutral ATOMS before any electron accounting, so an
adduct table cannot store an electron-adjusted mass and have the
correction applied to it twice.

**EXACT-MASS CALCULATION, AND DETERMINISTIC NOMINAL-MASS BINNING** -- not
"two resolutions, both exact", because binning deliberately discards
exact-mass information. The path is integer arithmetic in isotope space
and only the last step touches m/z:

    isotope composition -> integer nominal isotope shift
                        -> exact ion m/z -> nominal ion m/z coordinate

Nominal binning must never be implemented by rounding the final exact m/z:
mass defect is composition-dependent, and a multiply charged ion decouples
isotope mass-number shifts from m/z spacing entirely (a +1 shift moves a
2+ ion by 0.5).

**WHAT PRUNING TOUCHES, stated once:**

    full theoretical distribution -> derived summary values
                                  -> optional pruning for reported peaks

so `monoisotopic_mz`, `average_mz` and `base_peak_mz` come off the full
distribution and never move with the threshold. At `threshold = 0` the
result is the UNPRUNED THEORETICAL distribution -- still not "exact",
since it remains subject to floating-point arithmetic and to a finite
isotope table.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from openchem.domain.mass_spectrum import (
    DEFAULT_ION,
    AtomDelta,
    IonSpecies,
    MassPeak,
    MassSpectrum,
    SpectrumBasis,
)

#: The electron rest mass in daltons.
#:
#: **SOURCED, NOT REMEMBERED.** Taken from RDKit's own table by difference
#: -- see `_electron_mass` -- so it comes from the same place as every
#: other mass here rather than from a constant typed in from memory, which
#: is the field this project's citation audit found six errors in.
#:
#: Ignoring it is the common shortcut and is wrong by 0.00055 Da per
#: charge: enough to matter at the fourth decimal, which is exactly where
#: a high-resolution instrument is read.
ELECTRON_MASS_DA = 0.000548579909

#: Relative intensity below which a branch is dropped from the REPORTED
#: peaks. Chosen to keep every line a published pattern names while
#: keeping a 40-atom molecule's convolution finite; the summary values are
#: computed before it applies, so it can never move a reported mass.
DEFAULT_PRUNE_THRESHOLD = 1e-6

#: The relative intensity a peak must reach to be reported at all, when a
#: caller asks for the display form. Marvin's own elemental-analysis
#: spectrum shows lines down to about this, and below it a stick is a
#: pixel of noise on a plot rather than a peak anybody reads.
DISPLAY_THRESHOLD = 0.005


def _periodic_table():
    from rdkit import Chem

    return Chem.GetPeriodicTable()


def _electron_mass() -> float:
    """The electron mass, for callers that want it explicitly.

    Kept as a function beside the constant so a future revision has one
    place to change, and so nothing is tempted to re-derive it inline.
    """
    return ELECTRON_MASS_DA


def isotopes_of(symbol: str) -> tuple[tuple[int, float, float], ...]:
    """`(mass_number, exact_mass, fraction)` for one element's naturally
    occurring isotopes, fractions summing to ~1.

    Scanned rather than looked up, because RDKit exposes abundance per
    (element, mass number) with no way to enumerate -- the same reason
    `element_reference._isotopes_for` scans. Returns empty for an element
    with no natural isotope, which is a real answer rather than an error:
    a spectrum of a technetium compound is not something this can compute.
    """
    table = _periodic_table()
    z = table.GetAtomicNumber(symbol)
    found: list[tuple[int, float, float]] = []
    for mass_number in range(max(1, z), 4 * z + 30):
        try:
            abundance = table.GetAbundanceForIsotope(z, mass_number)
        except Exception:  # noqa: BLE001 - RDKit raises for absent nuclides
            continue
        if abundance and abundance > 0:
            found.append(
                (mass_number, table.GetMassForIsotope(z, mass_number), abundance / 100.0)
            )
    return tuple(found)


def _nuclide(symbol: str, mass_number: int) -> tuple[int, float, float]:
    """One named nuclide, as a single-member distribution."""
    table = _periodic_table()
    z = table.GetAtomicNumber(symbol)
    mass = table.GetMassForIsotope(z, mass_number)
    if not mass:
        raise ValueError(f"no isotope {symbol}-{mass_number}")
    return (mass_number, mass, 1.0)


def _distribution_for(symbol: str, isotope: int | None):
    """The isotope distribution one `AtomDelta` contributes.

    **THIS IS WHERE THE ION MODEL EARNS ITS KEEP.** `isotope=None` means
    the element at natural abundance, so a chloride adduct brings its 3:1
    envelope and a potassium adduct its 6.7% 41K satellite; a mass number
    means one nuclide, so protonation adds exactly 1H and no hydrogen
    envelope appears.
    """
    if isotope is not None:
        return (_nuclide(symbol, isotope),)
    found = isotopes_of(symbol)
    if not found:
        raise ValueError(f"{symbol} has no naturally occurring isotope to distribute")
    return found


def _convolve(accumulated: dict, distribution, count: int, sign: int) -> dict:
    """Fold one element's distribution into the running envelope `count`
    times, keyed by nominal mass-number shift from the lightest branch.

    `sign` is -1 for atoms being REMOVED, which is what lets `[M-H]-` go
    through the identical path as every adduct rather than needing a
    branch of its own.
    """
    lightest = min(mass_number for mass_number, _mass, _fraction in distribution)
    for _ in range(count):
        folded: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for shift, entries in accumulated.items():
            for mass, probability in entries:
                for mass_number, exact_mass, fraction in distribution:
                    folded[shift + sign * (mass_number - lightest)].append(
                        (mass + sign * exact_mass, probability * fraction)
                    )
        accumulated = dict(folded)
    return accumulated


def _collapse(accumulated: dict) -> dict[int, tuple[float, float]]:
    """`{nominal_shift: (probability-weighted mean exact mass, probability)}`.

    Isotopologues sharing a nominal shift are combined, which is what
    makes the result a NOMINAL envelope. Their individual exact masses are
    lost here by design, and recovering them is the fine-structure
    extension on the roadmap -- 278.943 being 81Br rather than 13C + 79Br
    is a question this deliberately cannot answer yet.
    """
    collapsed: dict[int, tuple[float, float]] = {}
    for shift, entries in accumulated.items():
        probability = sum(p for _mass, p in entries)
        if probability <= 0.0:
            continue
        mean_mass = sum(mass * p for mass, p in entries) / probability
        collapsed[shift] = (mean_mass, probability)
    return collapsed


def base_peak_shift(collapsed: dict[int, tuple[float, float]]) -> int:
    """Which shift carries the tallest branch. **TIES GO TO THE LOWEST.**

    Extracted as its own function so the tie rule can be TESTED, which it
    could not be through the engine: no two real elements produce branches
    of exactly equal probability, so `min` and `max` are indistinguishable
    on every input the convolution can actually generate. An unreachable
    branch is a question about where to assert, and the answer is here.

    Deterministic rather than "whichever the iteration reached first" --
    a scientific value object may not depend on that.
    """
    peak = max(probability for _mass, probability in collapsed.values())
    return min(
        shift
        for shift, (_mass, probability) in collapsed.items()
        if probability == peak
    )


def element_counts(mol: Any) -> dict[str, int]:
    """Every atom of `mol`, counted by symbol, hydrogens included.

    The caller is responsible for having added explicit hydrogens --
    `compute_mass_spectrum` does, for the reason
    `elemental_analysis.element_composition` records: RDKit keeps them
    implicit and an implicit hydrogen contributes no atom to count.
    """
    counts: dict[str, int] = defaultdict(int)
    for atom in mol.GetAtoms():
        counts[atom.GetSymbol()] += 1
        counts["H"] += atom.GetTotalNumHs()
    return {symbol: count for symbol, count in counts.items() if count}


def isotope_envelope(
    counts: dict[str, int],
    ion: IonSpecies = DEFAULT_ION,
    prune_threshold: float = DEFAULT_PRUNE_THRESHOLD,
    unit_resolution: bool = True,
) -> MassSpectrum:
    """The isotope envelope of `counts` ionised as `ion`.

    `counts` is the NEUTRAL molecule; the ion's own composition is folded
    in here, through the same convolution, which is what gives a chloride
    or potassium adduct its own satellites.
    """
    charge = ion.charge
    magnitude = abs(charge)

    accumulated: dict[int, list[tuple[float, float]]] = {0: [(0.0, 1.0)]}
    for symbol, count in sorted(counts.items()):
        accumulated = _convolve(accumulated, _distribution_for(symbol, None), count, 1)
    neutral = _collapse(accumulated)
    neutral_exact_mass = neutral[min(neutral)][0] if neutral else 0.0

    for change in ion.composition.changes:
        distribution = _distribution_for(change.symbol, change.isotope)
        accumulated = _convolve(
            accumulated,
            distribution,
            abs(change.count),
            1 if change.count > 0 else -1,
        )

    collapsed = _collapse(accumulated)
    if not collapsed:
        raise ValueError("nothing to compute a spectrum from")

    # **THE FULL DISTRIBUTION FIRST, AND THE SUMMARY VALUES OFF IT.**
    # Everything below this line up to the pruning is computed from every
    # branch, so no reported mass can move when the threshold does.
    total = sum(probability for _mass, probability in collapsed.values())
    lowest_shift = min(collapsed)
    monoisotopic_mass = collapsed[lowest_shift][0]
    monoisotopic_mz = _mz(monoisotopic_mass, charge)
    average_mz = _mz(
        sum(mass * probability for mass, probability in collapsed.values()) / total,
        charge,
    )
    peak_probability = max(probability for _mass, probability in collapsed.values())
    base_shift = base_peak_shift(collapsed)
    base_peak_mz = _mz(collapsed[base_shift][0], charge)

    nominal_monoisotopic_mz = round(monoisotopic_mz)
    peaks: list[MassPeak] = []
    for shift in sorted(collapsed):
        mass, probability = collapsed[shift]
        relative = probability / peak_probability
        if relative < prune_threshold:
            continue
        nominal_shift = shift - lowest_shift
        # **NOMINAL BINNING DIVIDES THE SHIFT BY THE CHARGE.** An isotope
        # shift of 1 moves a 1+ ion by 1.0 m/z and a 2+ ion by 0.5, and
        # rounding the exact m/z instead would be wrong for both reasons
        # in the module header.
        peaks.append(
            MassPeak(
                mz=(
                    nominal_monoisotopic_mz + nominal_shift / magnitude
                    if unit_resolution
                    else _mz(mass, charge)
                ),
                intensity=relative,
                nominal_shift=nominal_shift,
                label=f"M+{nominal_shift}" if nominal_shift else "M",
            )
        )

    return MassSpectrum(
        peaks=tuple(peaks),
        ion=ion,
        basis=SpectrumBasis.CALCULATED,
        neutral_exact_mass=neutral_exact_mass,
        monoisotopic_mz=monoisotopic_mz,
        average_mz=average_mz,
        base_peak_mz=base_peak_mz,
        unit_resolution=unit_resolution,
        prune_threshold=prune_threshold,
    )


def _mz(neutral_mass: float, charge: int) -> float:
    """`(mass - charge*m_e) / |charge|`, the one place the electron enters.

    A POSITIVE ion has lost electrons, so its mass is lower; a negative
    ion has gained them. Writing `- charge * m_e` rather than branching on
    the sign is what makes that true for both without two code paths to
    keep in agreement.
    """
    return (neutral_mass - charge * ELECTRON_MASS_DA) / abs(charge)
