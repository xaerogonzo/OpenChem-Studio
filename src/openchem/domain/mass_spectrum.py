"""A mass spectrum, and the ion it is a spectrum OF.

**THE ION IS A COMPOSITION, AND THAT DECIDES THE WHOLE MODEL.** A scalar
mass delta expresses `[M+H]+` and `[M+Na]+` perfectly well and cannot
express `[M+Cl]-`: chlorine is 75.8% 35Cl and 24.2% 37Cl, so a chloride
adduct contributes its own 3:1 envelope, and a single number has nowhere
to put it. The invariant is therefore

    ion composition -> exact atomic mass delta -> electron correction -> m/z

and never `hard-coded delta_mass -> m/z`. A scalar may be CACHED as a
derived value; it is never the identity.

This module is the domain half: what an ion is, what a peak is, what a
spectrum carries. `chem/mass_spectrum.py` is the arithmetic, because the
masses and abundances come from RDKit and `domain/` imports no toolkit.

**WHAT THIS DELIBERATELY DOES NOT SOLVE.** A tandem (MS/MS) spectrum needs
a precursor ion, a fragment-to-precursor relationship, an activation
method and a collision energy. `MassPeak.label` is a string, and a string
is not a fragment hierarchy -- see the roadmap's MS/MS gate rather than
reading this shape as ready for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SpectrumBasis(str, Enum):
    """Where a mass spectrum came from. THREE VALUES, NOT TWO.

    A measured spectrum, a calculated isotope envelope and a predicted
    fragmentation pattern all render as sticks on an m/z axis and are
    completely different claims. The producer DECLARES which; nothing
    infers it, the same rule `ReportResult.spatial` follows.

    Collapsing CALCULATED and PREDICTED into one "not measured" value is
    the tempting simplification and the wrong one: a natural-abundance
    envelope is arithmetic anybody can redo, and a fragmentation pattern
    is a model's guess that needs a validation corpus before it ships.
    """

    #: An instrument produced it.
    MEASURED = "measured"
    #: Arithmetic over tabulated isotope abundances. Deterministic, and
    #: still not what an instrument will show -- see `MassSpectrum`.
    CALCULATED = "calculated"
    #: A model's prediction. Nothing in this application produces one yet,
    #: and the value exists so that when something does, it cannot quietly
    #: render as a calculation.
    PREDICTED = "predicted"


@dataclass(frozen=True)
class AtomDelta:
    """One element added to or removed from the neutral molecule.

    **`isotope` IS None FOR NATURAL ABUNDANCE AND A MASS NUMBER FOR ONE
    SPECIFIC NUCLIDE, AND THAT DISTINCTION IS THE POINT.** Some ionisation
    operations name a nuclide by definition and some genuinely introduce a
    naturally distributed element:

        [M+H]+   protonation adds a PROTON      -> isotope=1
        [M-H]-   deprotonation removes one      -> isotope=1
        [M+Cl]-  a chloride ion is chlorine     -> isotope=None, 3:1
        [M+K]+   a potassium ion is potassium   -> isotope=None, 6.7% 41K

    Potassium is the case that proves this is not a chloride special case:
    a `[M+K]+` adduct carries its own M+2 satellite from the adduct alone.
    Sodium happens to be monoisotopic, so it cannot tell the two rules
    apart and is declared natural because that is what it chemically is.

    NOT `0`-as-a-sentinel for "natural": 0 is a plausible typo for a mass
    number and would read as one.
    """

    symbol: str
    #: Signed. Negative removes atoms; zero is refused by
    #: `composition_delta`, since an entry that changes nothing is either a
    #: mistake or noise in an ion's identity.
    count: int
    isotope: int | None = None


def composition_delta(changes) -> "CompositionDelta":
    """A canonical `CompositionDelta`, or a `ValueError` saying why not.

    **CANONICAL BY CONSTRUCTION, BECAUSE THIS IS AN ION'S IDENTITY.**
    `IonSpecies` is frozen and hashable and gets compared and used as a
    key; without a canonical form `(H, Na)` and `(Na, H)` are two
    identities for one ion, and `(H +1, H 0)` is a legal spelling of a
    contradiction. So: sorted by `(symbol, isotope)`, no zero counts, no
    duplicate `(symbol, isotope)` pair.

    Merging duplicates instead of refusing them was the alternative and is
    worse -- `(H +1, H -1)` would silently become "no change", which is a
    plausible ion nobody meant to write.
    """
    ordered = sorted(changes, key=lambda change: (change.symbol, change.isotope or 0))
    seen: set[tuple[str, int | None]] = set()
    for change in ordered:
        if not isinstance(change.count, int) or isinstance(change.count, bool):
            raise ValueError(f"an atom count must be a whole number: {change!r}")
        if change.count == 0:
            raise ValueError(f"an atom delta of zero changes nothing: {change!r}")
        if change.isotope is not None and change.isotope <= 0:
            raise ValueError(f"a mass number must be positive: {change!r}")
        key = (change.symbol, change.isotope)
        if key in seen:
            raise ValueError(f"{change.symbol} appears twice in one composition delta")
        seen.add(key)
    return CompositionDelta(changes=tuple(ordered))


@dataclass(frozen=True)
class CompositionDelta:
    """Atoms added to or removed from the neutral, as counts.

    **NEUTRAL ATOMS ONLY.** No proton or electron bookkeeping lives here,
    so an adduct table can never store an electron-adjusted mass and have
    the electron correction applied to it a second time. The engine
    applies `charge * m_e` itself, in one place.

    Build one through `composition_delta`, which is what enforces the
    canonical form. The constructor is left open rather than made private
    because a frozen dataclass with a validating factory beside it is the
    shape the rest of this package already uses.
    """

    changes: tuple[AtomDelta, ...] = ()


@dataclass(frozen=True)
class IonSpecies:
    """One ion a spectrum can be of.

    **IDENTITY IS `composition + charge`; THE LABEL IS DISPLAY TEXT.** On
    a frozen dataclass every field joins `__eq__` and `__hash__` by
    default, which would make two spellings of one ion two different ions
    -- and, worse, let one spelling stand in for two different
    compositions without anything noticing. `compare=False` is what stops
    a presentation string becoming a scientific identity.
    """

    label: str = field(compare=False)
    composition: CompositionDelta = CompositionDelta()
    #: Signed, and never zero: a mass spectrum is of an ION.
    charge: int = 1

    def __post_init__(self) -> None:
        if self.charge == 0:
            raise ValueError("an ion species must carry a charge")


@dataclass(frozen=True)
class MassPeak:
    """One line of a mass spectrum."""

    #: **THE PLOT AND EXPORT X COORDINATE, AND WHICH QUANTITY IT IS
    #: DEPENDS ON THE SPECTRUM'S RESOLUTION:**
    #:
    #:     exact       the isotopologue's own m/z
    #:     unit        nominal monoisotopic m/z + nominal_shift / |charge|
    #:
    #: At unit resolution exact-mass information is absent BY DESIGN
    #: rather than lost by accident, and `MassSpectrum.unit_resolution`
    #: says which you are holding. The renderer, the export, the labels
    #: and any later spectrum comparison all read this field, so leaving
    #: it implicit would have each of them assume differently.
    mz: float
    #: Relative to the base peak, which is 1.0. See `MassSpectrum.peaks`.
    intensity: float
    #: **THE INTEGER ISOTOPE-SPACE COORDINATE, WHICH IS NOT THE m/z
    #: SPACING.** The mass-number shift from the monoisotopic ion. For a
    #: 1+ ion a shift of 1 moves m/z by 1.0; for a 2+ ion it moves m/z by
    #: 0.5. Collapsing the two works perfectly for singly charged ions and
    #: silently draws every multiply-charged spectrum at the wrong
    #: spacing, which is the ESI case the charge model exists to support.
    nominal_shift: int = 0
    label: str = ""


@dataclass(frozen=True, kw_only=True)
class MassSpectrum:
    """A spectrum of one ion, with the summary values it supports.

    **A THEORETICAL DISTRIBUTION IS NOT THE OBSERVED ONE.** Even a
    perfectly computed envelope differs from what an instrument records:
    ion sampling, ion-ion interactions, detector response, centroiding and
    apodisation all move a measured spectrum. That is why `basis` exists
    and why a calculated spectrum's caption says what it is rather than
    calling itself a spectrum and leaving the reader to assume.
    """

    #: **BASE-PEAK NORMALISED: `max(intensity) == 1.0`, and an empty peak
    #: list is refused.** The convolution works in absolute isotope
    #: probabilities; the public object reports relative intensities.
    #: Stating the invariant is what stops the two conventions being mixed
    #: by a later consumer reading "intensity" and guessing.
    peaks: tuple[MassPeak, ...]
    ion: IonSpecies
    basis: SpectrumBasis
    #: The NEUTRAL molecule's exact mass -- distinct from the ion's m/z
    #: below, and equal to it only for a neutral molecular ion at charge 1
    #: before the electron correction. Kept as its own field because
    #: conflating the two is the easiest wrong invariant to write down.
    neutral_exact_mass: float
    #: The m/z of the all-lightest-isotopes ion.
    #:
    #: **THE SUMMARY MASSES BELOW ARE EXACT EVEN WHEN THE PEAKS ARE
    #: BINNED, so they are not comparable with `peaks[i].mz` at unit
    #: resolution.** They come off the full theoretical distribution;
    #: a unit-resolution peak's `mz` is the nominal coordinate of its
    #: bin. Bromine makes the difference concrete: the base peak is at
    #: 78.9178 while the peak drawn for it sits at 79.0. Two
    #: quantities, both wanted, and asserting one against the other is
    #: a mistake this file's own tests made once.
    monoisotopic_mz: float
    #: Probability-weighted mean m/z over the FULL theoretical
    #: distribution, with probabilities normalised across that
    #: distribution rather than across the pruned peak list, and computed
    #: BEFORE pruning -- so it does not move when the threshold does.
    #: "Average" has at least three defensible meanings here, and an
    #: undefined one is worse than none.
    average_mz: float
    #: The m/z of the tallest peak. **Ties go to the LOWEST m/z**, so this
    #: is deterministic rather than "whichever the sort happened to put
    #: first" -- a scientific value object may not depend on that.
    base_peak_mz: float
    #: Whether the peaks are binned to nominal mass. See `MassPeak.mz`.
    unit_resolution: bool = False
    #: Branches below this relative intensity were left out of `peaks`.
    #: **0.0 means no ALGORITHMIC pruning -- which still is not "exact":**
    #: the result remains subject to floating-point arithmetic, to the
    #: finite isotope table it was computed from, and to that table's own
    #: revisions. "Unpruned theoretical distribution" is the honest phrase.
    prune_threshold: float = 0.0


#: **PROTONATION ADDS A PROTON, SO ITS HYDROGEN IS 1H BY DEFINITION.**
#: Adding a deuteron is a different, separately-named experiment. Every
#: other adduct below carries the element at natural abundance, because a
#: sodium ion is sodium and a chloride ion is chlorine.
_PROTON = 1

#: The ions this application can compute a spectrum for.
#:
#: **A CLOSED VOCABULARY, AND THE ONLY WAY TO CHOOSE AN ION.** The label
#: is presentation; the composition and charge are the identity. Letting a
#: UI offer a free-text ion string, or a charge spinbox independent of the
#: chosen species, is how `[M+2H]2+` ends up meaning "charge 2, and the
#: composition of something else" -- so charge comes from the ion here and
#: never from a separate control.
#:
#: `[M+2H]2+` is in the FIRST vocabulary rather than merely representable:
#: once identity is composition-based it costs nothing beyond the fixture
#: that has to exist anyway, and shipping the charge model with no
#: multiply-charged member would leave that path untravelled.
SUPPORTED_IONS: tuple[IonSpecies, ...] = (
    # The EI molecular ion: an electron is removed and no atom is added,
    # so the composition really is empty and the whole shift is `-m_e`.
    IonSpecies(label="[M]+.", composition=CompositionDelta(), charge=1),
    IonSpecies(
        label="[M+H]+",
        composition=composition_delta([AtomDelta("H", 1, _PROTON)]),
        charge=1,
    ),
    IonSpecies(
        label="[M+2H]2+",
        composition=composition_delta([AtomDelta("H", 2, _PROTON)]),
        charge=2,
    ),
    # Natural abundance: sodium is monoisotopic so it cannot tell the two
    # rules apart, and declaring it natural is what it chemically is.
    IonSpecies(
        label="[M+Na]+", composition=composition_delta([AtomDelta("Na", 1)]), charge=1
    ),
    # **THE CASE THAT PROVES NATURAL ADDUCTS ARE NOT A CHLORIDE SPECIAL
    # CASE.** Potassium is 6.7% 41K, so this adduct carries its own M+2
    # satellite whatever the molecule is.
    IonSpecies(
        label="[M+K]+", composition=composition_delta([AtomDelta("K", 1)]), charge=1
    ),
    IonSpecies(
        label="[M+NH4]+",
        composition=composition_delta([AtomDelta("N", 1), AtomDelta("H", 4)]),
        charge=1,
    ),
    IonSpecies(
        label="[M-H]-",
        composition=composition_delta([AtomDelta("H", -1, _PROTON)]),
        charge=-1,
    ),
    # Chlorine is 3:1, so this adduct brings an envelope of its own.
    IonSpecies(
        label="[M+Cl]-", composition=composition_delta([AtomDelta("Cl", 1)]), charge=-1
    ),
)

#: What Elemental Analysis draws and what the Mass Spectrum calculator
#: starts on: the neutral molecule's own isotope envelope, as the EI
#: molecular ion. Named rather than written as `SUPPORTED_IONS[0]`, which
#: would silently become a different ion the day somebody reorders them.
DEFAULT_ION = SUPPORTED_IONS[0]


def ion_by_label(label: str) -> IonSpecies | None:
    """The supported ion with this label, or None.

    A lookup rather than a parser: `[M+H]+` is a name in a closed
    vocabulary, and parsing arbitrary adduct notation would be inventing
    an ion nobody has fixtures for.
    """
    for ion in SUPPORTED_IONS:
        if ion.label == label:
            return ion
    return None
