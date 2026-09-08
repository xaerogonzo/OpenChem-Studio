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

**WHAT PRUNING TOUCHES, stated once** -- and the trade it makes is the
one [source:snider2007] names: polynomial methods "rely on pruning to
reduce the complexity", the strategies "use a threshold to eliminate
permutations whose contribution falls below some preset value", and that
"creates errors in the isotopic distribution profile". Which is why the
threshold is declared rather than hidden, why the summary values are
computed before it applies, and why zero is called unpruned rather than
exact:

    full theoretical distribution -> derived summary values
                                  -> optional pruning for reported peaks

so `monoisotopic_mz`, `average_mz` and `base_peak_mz` come off the full
distribution and never move with the threshold. At `threshold = 0` the
result is the UNPRUNED THEORETICAL distribution -- still not "exact",
since it remains subject to floating-point arithmetic and to a finite
isotope table.

**AND A THEORETICAL DISTRIBUTION IS NOT AN OBSERVED ONE.**
[source:claesen2023] is the modern account of the gap: ion sampling,
ion-ion interactions, detector response and centroiding all move a
measured distribution away from the computed one. `SpectrumBasis` carries
that architecturally and `CALCULATED_CAPTION` says it in words.

The algorithm here is the naive convolution, which is what
[source:dittwald2014] describes scaling quadratically and improves on,
and [source:alves2014] is the survey of what an adjustable-accuracy
alternative costs. Neither supplies a number used here; both are where a
future version starts rather than re-deriving the ground.
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
    is a question this deliberately cannot answer yet, and
    [source:ipsen2014] is the route to answering it.
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


#: What the caption says a calculated envelope IS, and what it is not.
#:
#: **"CALCULATED" AND NOT "THEORETICAL SPECTRUM".** A theoretical isotope
#: distribution is not what an instrument records: ion sampling, ion-ion
#: interactions, detector response, centroiding and apodisation all move a
#: measured spectrum away from it. `SpectrumBasis` is the architectural
#: protection and this is the wording half -- a picture that calls itself
#: a spectrum invites the reader to compare it with one.
#:
#: One string, used by both callers, so the two cannot drift into saying
#: different things about the same arithmetic.
CALCULATED_CAPTION = (
    "CALCULATED -- natural-abundance isotope distribution for {ion}, not a "
    "measured spectrum. A theoretical distribution differs from what an "
    "instrument records: ion sampling, detector response and centroiding "
    "all move a real spectrum. No fragmentation is modelled."
)


def spectrum_chart(spectrum: MassSpectrum, title: str = "Isotope pattern"):
    """`spectrum` as a declared chart annotation.

    **THE PRODUCER'S DECLARATION, BUILT IN ONE PLACE.** Elemental Analysis
    and the Mass Spectrum calculator both show this picture, and two
    builders would be two captions to keep in step -- which is the drift
    this repository has paid for four times.

    `x_descending=False`: m/z runs LOW MASS TO THE LEFT, the opposite of
    NMR and IR. Declared here rather than guessed by the renderer, because
    a mirrored spectrum does not look broken, it looks like a different
    compound.
    """
    from openchem.domain.report import Stick, StickChartAnnotation

    return StickChartAnnotation(
        sticks=tuple(
            Stick(peak.mz, peak.intensity, peak.label)
            for peak in spectrum.peaks
            if peak.intensity >= DISPLAY_THRESHOLD
        ),
        x_label="m/z",
        y_label="Relative abundance",
        x_descending=False,
        y_units="",
        title=f"{title} {spectrum.ion.label}",
        caption=CALCULATED_CAPTION.format(ion=spectrum.ion.label),
    )


#: The resolutions a reader can ask for, as the settings dialog spells
#: them. A CLOSED pair: "exact" and "unit" are the two things the engine
#: computes, and a free-text field here would be a third answer nobody
#: implements.
UNIT_RESOLUTION = "Unit (nominal mass)"
EXACT_RESOLUTION = "Exact mass"

#: Percent. What a peak must reach to be reported at all -- a stick below
#: this is a pixel on a plot rather than a line anybody reads. Expressed
#: as a percentage because that is how a chemist states it, and converted
#: once at the point of use.
DEFAULT_MINIMUM_PERCENT = 0.5


def compute_mass_spectrum(mol, molecule_uuid: str, parameters=None):
    """The "mass_spectrometry" category's calculator.

    **THE MODES LIVE HERE AND NOT ON ELEMENTAL ANALYSIS.** That calculator
    is about composition and draws the molecular ion's envelope beside its
    percentages, the way Marvin's own window does; a `[M+Na]+` selector on
    it would be an ionisation control on a composition readout. Both call
    ONE engine, so the two can never disagree about the same ion.

    **CHARGE COMES FROM THE CHOSEN ION, NEVER FROM A SEPARATE CONTROL.**
    A charge spinbox beside a short list of hard-coded species is how
    `[M+2H]2+` comes to mean "charge 2, and the composition of something
    else".
    """
    from rdkit import Chem

    from openchem.chem.calculator_options import apply_microspecies, microspecies_note
    from openchem.domain.common import CacheState, Provenance
    from openchem.chem.report_adapter import report_from_fields
    from openchem.domain.mass_spectrum import DEFAULT_ION, ion_by_label

    parameters = parameters or {}
    label = str(parameters.get("ion") or DEFAULT_ION.label)
    ion = ion_by_label(label) or DEFAULT_ION
    unit_resolution = str(
        parameters.get("resolution") or UNIT_RESOLUTION
    ) != EXACT_RESOLUTION
    minimum = float(parameters.get("minimum_percent", DEFAULT_MINIMUM_PERCENT)) / 100.0

    provenance = Provenance(
        created_by="core",
        method="isotope convolution",
        parameters={
            "ion": ion.label,
            "charge": ion.charge,
            # WHICH TABLE THIS CAME FROM AND WHICH RELEASE OF IT. The
            # abundances are RDKit's, so the answer depends on its
            # version: "RDKit says it" is not immutable across releases.
            "isotope_data": "rdkit",
            "rdkit_version": _rdkit_version(),
            "prune_threshold": DEFAULT_PRUNE_THRESHOLD,
            "unit_resolution": unit_resolution,
        },
    )

    def failed(error: str):
        return report_from_fields(
            alert_id="mass_spectrum",
            name="Mass Spectrum",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="mass_spectrometry",
            cache_state=CacheState.FAILED,
            error=error,
            provenance=provenance,
        )

    with_hydrogens = Chem.AddHs(apply_microspecies(mol, parameters))
    try:
        spectrum = isotope_envelope(
            element_counts(with_hydrogens), ion, unit_resolution=unit_resolution
        )
    except ValueError as exc:
        return failed(str(exc))

    lines = [
        f"Ion: {ion.label} (charge {ion.charge:+d})",
        f"Neutral exact mass: {spectrum.neutral_exact_mass:.6f}",
        f"Monoisotopic m/z: {spectrum.monoisotopic_mz:.6f}",
        f"Average m/z: {spectrum.average_mz:.4f}",
        f"Base peak m/z: {spectrum.base_peak_mz:.4f}",
    ]
    reported = [peak for peak in spectrum.peaks if peak.intensity >= minimum]
    lines.append(f"Peaks reported: {len(reported)}")
    for peak in reported:
        lines.append(f"  {peak.label}: m/z {peak.mz:.4f}, {peak.intensity * 100:.2f}%")
    lines.extend(microspecies_note(parameters))
    lines.append(
        "Calculated from natural isotope abundances. NOT a measured spectrum, "
        "and no fragmentation is modelled -- every line here is the molecular "
        "ion's own isotope distribution."
    )

    return report_from_fields(
        alert_id="mass_spectrum",
        name="Mass Spectrum",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="mass_spectrometry",
        provenance=provenance,
        charts=(spectrum_chart(spectrum, title="Mass spectrum"),),
    )


def _rdkit_version() -> str:
    """RDKit's version, or "" if it cannot be asked.

    Recorded in provenance because the abundances are RDKit's: a result
    computed under one release is not guaranteed identical under the next,
    and a stored spectrum that cannot say which table it used cannot be
    reproduced."""
    try:
        import rdkit

        return str(rdkit.__version__)
    except Exception:  # noqa: BLE001 - never lose a result over its metadata
        return ""
