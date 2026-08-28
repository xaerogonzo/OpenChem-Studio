"""Where a powder pattern's peaks fall, and why their heights are refused.

A calculated powder X-ray diffraction pattern for a periodic structure:
the (hkl) reflections a cell and its symmetry allow, each with an
interplanar spacing, a Bragg angle and a multiplicity.

## POSITIONS ARE SHIPPED. INTENSITIES ARE REFUSED, AND THE REASON IS MEASURED

This is deliberately half of what a powder-pattern calculator usually
does, and the split is not arbitrary -- the two halves rest on different
kinds of evidence:

    positions    lattice geometry and Bragg's law. Nothing is fitted,
                 nothing is tabulated, and the answer is checkable by
                 arithmetic a reader can do: for a cubic cell the general
                 expression below must reduce to a/sqrt(h2+k2+l2), and it
                 does, to six decimal places.

    intensities  |F(hkl)|2 needs an atomic scattering factor per element,
                 f0(sin(theta)/lambda). That is a TABLE of fitted
                 parameters, and this project does not have a trustworthy
                 copy of one.

**THE REFUSAL IS A MEASUREMENT, NOT AN ESTIMATE OF EFFORT.** The standard
parameterisation is Waasmaier & Kirfel (1995), *Acta Cryst.* A51,
416-431 -- five Gaussians, eleven parameters per species. The copy held
locally is a scan whose text layer is damaged, measured over the four
pages of its Table 1:

    numeric tokens on the table pages     2267
    visibly corrupted                      673   (29.7%)

...and 70.3% "clean" is an UPPER bound on correctness, because a token
can be well formed and still wrong. Element labels are corrupted too:
the row for calcium extracts as `Cs`, which would silently put caesium's
scattering factors on calcium.

**THE DECISIVE POINT IS THAT ONLY SIX OF THE ELEVEN PARAMETERS CAN BE
CHECKED.** A neutral atom's scattering factor at zero angle is its
electron count, so `sum(a_i) + c = Z` is a per-row oracle covering
`a1..a5` and `c`. The five `b` values have no such check -- a wrong `b`
is wrong at every non-zero angle while being exactly right at
theta = 0, which is the one place the checksum looks. Transcribing a
table where nearly a third of the numbers are visibly damaged and 5 of
every 11 are unverifiable would produce plausible intensities of unknown
correctness, which is worse than none.

So `intensity_refusal()` says this in one place, `PowderPattern` carries
it, and nothing here computes a structure factor. A machine-readable
Waasmaier-Kirfel table, or the tabulated values of *International Tables
for Crystallography* Vol. C that it was fitted to, is what would lift it.

## WHAT A CALCULATED ZERO WOULD MEAN, IF THERE WERE ONE

Stated now, because it is the trap the intensity half would arrive with:
a reflection is listed here when the LATTICE and its symmetry allow it.
A systematic absence computed below is a statement about the space
group, not a prediction that an experiment sees nothing -- and a peak
listed here with no intensity is not a claim about how strong it is.

## KINEMATIC, AND IDEALISED

Even the positions describe an idealised experiment. There is no
preferred orientation, no strain, no instrument broadening, no zero-point
offset, no sample displacement, and no peak shape at all -- a reflection
is a line at an angle, not a profile. Anything comparing this against a
measured diffractogram is comparing a stick pattern with data that has
all of those in it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from openchem.domain.crystal import Crystal, Lattice, SymmetryOperation

#: **NO `USER_FACING_PROVIDER` HERE, and its absence is a decision.**
#: That marker means "reachable from a REGISTERED CALCULATOR", and this
#: is not: it reaches the user through `build_crystal_report`, which a
#: CIF import opens. `chem/crystal_report.py` declares nothing for the
#: identical reason. Declaring it anyway would make
#: `test_every_declared_provider_is_reachable_from_a_calculator` fail
#: while the feature was perfectly reachable -- a false claim about the
#: route rather than about the destination.

#: Below this, two computed d-spacings are the same reflection family.
#: Angstrom. Generous next to the 1e-6 agreement the tensor gives on
#: exactly-equivalent planes, and far tighter than the spacing between
#: genuinely distinct families in any cell this reads.
D_TOLERANCE = 1e-6

#: How far a phase may sit from an integer before a reflection counts as
#: systematically absent. The translations are exact ratios (`1/2`,
#: `1/3`), so the real values are integers or clearly not; this only
#: absorbs floating-point noise.
PHASE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class PowderReflection:
    """One allowed reflection family.

    `hkl` is the REPRESENTATIVE of the family -- the symmetry-equivalent
    planes it stands for are counted in `multiplicity` rather than listed,
    because a powder superimposes them into one peak. Which member is the
    representative is chosen deterministically so two runs agree.
    """

    h: int
    k: int
    l: int
    d_spacing: float
    two_theta: float
    multiplicity: int

    @property
    def hkl(self) -> tuple[int, int, int]:
        return (self.h, self.k, self.l)

    @property
    def label(self) -> str:
        """`(1 1 1)`, with a bar for a negative index as crystallography
        writes it -- `(1 -1 1)` reads as three separate numbers."""
        return "(" + " ".join(f"{i}" if i >= 0 else f"-{abs(i)}" for i in self.hkl) + ")"


@dataclass(frozen=True)
class PowderPattern:
    """The calculated positions, and what is deliberately not here."""

    wavelength: float
    reflections: tuple[PowderReflection, ...] = ()
    max_two_theta: float = 0.0
    #: How many families the range HOLDS, before any cap. Kept beside the
    #: list rather than left implicit: a large cell with Mo radiation
    #: reaches ~30000 out to 60 degrees, and a truncated list that does
    #: not say so reads as the whole pattern. `truncated_by` is what a
    #: caller renders.
    total_reflections: int = 0
    #: Why no intensity column exists. Always populated -- see the module
    #: docstring. Carried on the result rather than left to the caller to
    #: remember, so a consumer cannot render a pattern without it.
    intensity_refusal: str = ""
    limitations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def reflection_count(self) -> int:
        return len(self.reflections)

    @property
    def truncated_by(self) -> int:
        """How many families are in range and NOT listed."""
        return max(0, self.total_reflections - len(self.reflections))


def intensity_refusal() -> str:
    """Why this pattern carries no intensities, in ONE place.

    One function rather than a string repeated at each call site, for the
    reason `predicted_only_reason()` exists in `chem/abraham.py`: two
    copies of a refusal drift into disagreeing about what was refused.
    """
    return (
        "Peak POSITIONS only. Intensities need a tabulated atomic scattering "
        "factor per element, and the available copy of the standard "
        "parameterisation (Waasmaier & Kirfel 1995) is a scan with 29.7% of "
        "its table numerically corrupted, of which only 6 of the 11 "
        "parameters per element could be checked even after transcription. "
        "A plausible intensity of unknown correctness is worse than none."
    )


def _limitations() -> tuple[str, ...]:
    return (
        intensity_refusal(),
        "A CALCULATED pattern from an idealised cell: no preferred "
        "orientation, no strain, no instrument broadening and no peak shape. "
        "Reflections are lines at angles, not profiles.",
        "Kinematic. Extinction, multiple scattering and anomalous dispersion "
        "are not represented.",
        "A systematic absence here is a statement about the space group, not "
        "a prediction that an experiment sees nothing.",
    )


def is_systematically_absent(
    operations: tuple[SymmetryOperation, ...], hkl: tuple[int, int, int]
) -> bool:
    """Whether the space group forbids (hkl).

    **DERIVED FROM THE OPERATIONS, NEVER FROM A TABLE OF EXTINCTION
    RULES.** A reflection invariant under an operation's rotation must
    also be unchanged by its translation, or the contributions of the
    atoms it relates cancel exactly:

        if h.R == h  and  h.t is not an integer   ->  F(hkl) = 0

    That one rule reproduces every centring and glide/screw condition a
    textbook lists separately. Verified against the F-centring rule
    (allowed only when h, k and l share a parity) on all eight test
    cases in `test_powder_xrd.py`, which is the point: a hand-kept list
    of conditions per space group is the `inapplicable_calculators`
    failure waiting to happen, 230 rows deep.
    """
    for operation in operations:
        rotation = operation.rotation
        transformed = tuple(
            sum(hkl[i] * rotation[i][j] for i in range(3)) for j in range(3)
        )
        if any(abs(transformed[i] - hkl[i]) > 1e-9 for i in range(3)):
            continue
        phase = sum(hkl[i] * operation.translation[i] for i in range(3))
        if abs(phase - round(phase)) > PHASE_TOLERANCE:
            return True
    return False


def equivalent_reflections(
    operations: tuple[SymmetryOperation, ...], hkl: tuple[int, int, int]
) -> frozenset[tuple[int, int, int]]:
    """Every (hkl) that lands on the same powder peak.

    **FRIEDEL PAIRS ARE INCLUDED, and that is a fact about POWDER rather
    than about symmetry.** (hkl) and (-h-k-l) have the same d-spacing in
    every crystal system, so they arrive at the same Bragg angle and are
    one line whatever the point group does -- including in a
    non-centrosymmetric group, where they are genuinely distinct
    reflections with distinct structure factors. A single-crystal
    treatment must not reuse this.

    Only the ROTATION acts: a translation moves atoms within the cell and
    cannot change which plane a reflection names.
    """
    family: set[tuple[int, int, int]] = set()
    for operation in operations:
        rotation = operation.rotation
        transformed = tuple(
            int(round(sum(hkl[i] * rotation[i][j] for i in range(3))))
            for j in range(3)
        )
        family.add(transformed)
        family.add(tuple(-index for index in transformed))
    return frozenset(family)


def _index_bound(lattice: Lattice, min_d: float) -> int:
    """How far to enumerate h, k and l so nothing above `min_d` is missed.

    **DERIVED, NOT A CONSTANT.** `1/d^2 = h^2 a*^2 + ...` for an
    orthogonal cell, so |h| <= a/d bounds it there; the diagonal of G*
    gives the same bound in general, since a reciprocal-lattice vector's
    length is at least the smallest contribution any one index makes.
    One is added because the bound is a real number and the indices are
    integers.

    A fixed ceiling would be silently wrong in both directions: too small
    drops reflections from a large cell, and too large costs the cube of
    itself on a small one.
    """
    star = lattice.reciprocal_metric_tensor
    bound = 1
    for axis in range(3):
        # a*, b*, c* are the square roots of G*'s diagonal.
        reciprocal_length = math.sqrt(star[axis][axis])
        bound = max(bound, int(math.ceil(1.0 / (min_d * reciprocal_length))) + 1)
    return bound


def calculate_pattern(
    crystal: Crystal,
    *,
    wavelength: float | None = None,
    max_two_theta: float = 90.0,
    max_reflections: int | None = None,
) -> PowderPattern:
    """The reflections a cell and its symmetry allow, out to `max_two_theta`.

    `wavelength` in angstrom. It defaults to the CIF's own
    `_diffrn_radiation_wavelength` when the file states one, and is
    REQUIRED otherwise: a wavelength is a property of the experiment and
    nothing about a structure supplies it, so guessing a laboratory tube
    would be inventing the one number the whole angle axis scales with.

    `max_reflections` keeps only the lowest-angle families and records how
    many were dropped in `truncated_by`. **Never a silent cap**: a large
    organic cell reaches ~30000 families out to 60 degrees with Mo
    radiation, and a list of the first 40 that does not say so reads as
    the whole pattern. Lowest-angle is the only honest ordering available
    here, since without intensities there is nothing to rank by.

    Raises `ValueError` rather than returning an empty pattern when there
    is no wavelength to use -- an empty pattern reads as "this structure
    diffracts nowhere", which is a different and false statement.
    """
    if wavelength is None:
        wavelength = crystal.radiation_wavelength
    if not wavelength or wavelength <= 0.0:
        raise ValueError(
            "a powder pattern needs a wavelength in angstrom; this structure "
            "states no _diffrn_radiation_wavelength, so one must be supplied"
        )
    if not 0.0 < max_two_theta < 180.0:
        raise ValueError("max_two_theta must lie strictly between 0 and 180 degrees")

    # Bragg at the largest angle asked for. Below this spacing a
    # reflection is outside the requested range; at any spacing under
    # lambda/2 it does not exist at all, for any angle.
    half_angle = math.radians(max_two_theta / 2.0)
    min_d = wavelength / (2.0 * math.sin(half_angle))

    lattice = crystal.lattice
    operations = crystal.operations
    bound = _index_bound(lattice, min_d)
    # **HOISTED, and this is the difference between usable and not.**
    # `Lattice.d_spacing` inverts the metric tensor on every call, which
    # is right for a readable single-reflection API and ruinous inside an
    # enumeration that reaches ~226000 index triples for a 15 A cell:
    # measured over the six CIF fixtures at 60 degrees, hoisting it alone
    # took the range from 1.9-3.9 s to 0.02-0.91 s, with every pattern
    # unchanged. The maximum 1/d^2 that is still in range is
    # precomputed too, so the inner test is a comparison rather than a
    # square root.
    star = lattice.reciprocal_metric_tensor
    max_inverse_d_squared = 1.0 / (min_d * min_d)

    seen: set[tuple[int, int, int]] = set()
    found: list[PowderReflection] = []
    for h in range(-bound, bound + 1):
        for k in range(-bound, bound + 1):
            for l in range(-bound, bound + 1):
                hkl = (h, k, l)
                if hkl == (0, 0, 0):
                    continue
                # **THE SPACING IS TESTED BEFORE THE ORBIT, and the order
                # is what makes this usable rather than a nicety.** The
                # orbit costs one matrix product per symmetry operation
                # -- 192 of them for an Fm-3m cell -- while the spacing
                # is nine multiply-adds, and most of an enumeration is
                # out of range. Skipping without recording the family is
                # safe because every member of a family has the SAME
                # spacing by construction, so each is rejected by this
                # identical test when the loop reaches it.
                inverse_d_squared = sum(
                    hkl[i] * star[i][j] * hkl[j] for i in range(3) for j in range(3)
                )
                if inverse_d_squared > max_inverse_d_squared:
                    continue
                if hkl in seen:
                    continue
                spacing = 1.0 / math.sqrt(inverse_d_squared)
                family = equivalent_reflections(operations, hkl)
                seen |= family
                if is_systematically_absent(operations, hkl):
                    continue
                sin_theta = wavelength / (2.0 * spacing)
                if sin_theta > 1.0:
                    continue
                # The representative is the family member a reader would
                # write: most positive indices first, then largest h.
                representative = max(
                    family, key=lambda v: (sum(1 for i in v if i > 0), v)
                )
                found.append(
                    PowderReflection(
                        h=representative[0],
                        k=representative[1],
                        l=representative[2],
                        d_spacing=spacing,
                        two_theta=2.0 * math.degrees(math.asin(sin_theta)),
                        multiplicity=len(family),
                    )
                )

    found.sort(key=lambda r: (r.two_theta, -r.d_spacing, r.hkl))
    total = len(found)
    kept = found if max_reflections is None else found[:max_reflections]
    return PowderPattern(
        wavelength=wavelength,
        reflections=tuple(kept),
        max_two_theta=max_two_theta,
        total_reflections=total,
        intensity_refusal=intensity_refusal(),
        limitations=_limitations(),
    )
