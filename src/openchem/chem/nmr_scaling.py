"""Empirical linear scaling of computed shieldings onto real ppm.

WHY THIS EXISTS. Referencing a computed shielding by subtracting TMS's
(`nmr_reference.py`) assumes the calculation's only error is a constant
offset. It is not: computed shieldings are systematically stretched
relative to experiment, by an amount that depends on the functional, the
basis, the geometry and the solvent model. The standard fix is a linear
regression of experimental shift against computed shielding,

    delta = slope * sigma + intercept

fitted over a set of compounds with known shifts. Slope comes out near
-1 but rarely at -1, and that difference is most of the residual error a
TMS-only referencing leaves behind.

WHY WE FIT OUR OWN RATHER THAN USING A PUBLISHED TABLE. Published
factors (the CHESHIRE repository collects them) are tied to one specific
program, functional, basis AND geometry level; using them against a
different combination reintroduces the error they were meant to remove.
Fitting against the user's own ORCA install removes that mismatch
entirely, and the fit reports its own R^2, so a bad calibration announces
itself instead of silently producing confident wrong numbers. It also
means no scaling factor in this file was recalled from memory.

WHY THESE REFERENCE COMPOUNDS. Every one has a SINGLE carbon environment
and a single proton environment, so there is no assignment step between
computed atoms and literature values -- the usual failure mode of a
calibration set is silently pairing the wrong shift with the wrong
nucleus, and a molecule with one environment cannot be mispaired.

WHAT THIS BUYS, measured against a real ORCA 6.1.1 install rather than
claimed:

    HF/STO-3G       carbon   MAE 5.67 ppm scaled, 11.56 unscaled
    B3LYP/def2-SVP  carbon   MAE 1.51 ppm scaled, ~11.3 unscaled
    B3LYP/def2-SVP  proton   MAE 0.21 ppm scaled,  0.67 unscaled

So scaling is worth roughly a factor of two at a crude level and a factor
of seven for carbon at a usable one. The proton fit at HF/STO-3G came out
at R^2 0.859 and was REFUSED by the guard below rather than applied --
which is the intended behaviour, not a failure.

KNOWN LIMITATION: after the heavy-atom exclusions the carbon set spans
-2.3 to 128.4 ppm, so carbonyls (~170-210) sit outside the fitted range
and are extrapolated. The underlying relationship is linear and the fit
is tight (R^2 0.998), so extrapolation is still far better than raw TMS
subtraction -- but it is extrapolation, and a carbonyl-region reference
compound with a single carbon environment would be a real improvement if
one can be found.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from openchem.domain.nmr import ScalingFactors

__all__ = [
    "CalibrationError",
    "MIN_POINTS",
    "MIN_R_SQUARED",
    "REFERENCE_COMPOUNDS",
    "ReferenceCompound",
    "ScalingFactors",
    "fit_scaling",
    "reference_molecule",
    "reference_points",
    "scale_spectrum",
]


@dataclass(frozen=True)
class ReferenceCompound:
    """A calibration standard. `shifts` maps element symbol to the
    literature shift shared by every nucleus of that element.

    `unsuitable_for` names elements this compound must NOT calibrate even
    though a literature value exists for them -- see the heavy-atom note
    below. Kept as data on the compound rather than as a filter at the
    call site, so the reason travels with the thing it applies to.
    """

    name: str
    smiles: str
    shifts: dict[str, float] = field(default_factory=dict)
    unsuitable_for: frozenset[str] = frozenset()


# HEAVY-ATOM EXCLUSIONS, measured rather than assumed.
#
# A carbon bonded to chlorine or sulfur carries a large spin-orbit
# contribution to its shielding that a standard non-relativistic GIAO
# calculation does not describe. Including such carbons wrecks the carbon
# fit, confirmed live at B3LYP/def2-SVP against this exact set:
#
#     all 11 compounds              R^2 0.902   (refused by the guard)
#     without CH2Cl2 and CHCl3      R^2 0.902   (still refused -- CCl4 and
#                                                CS2 are outliers too)
#     without every C-Cl and CS2    R^2 0.9984, MAE 1.51 ppm
#
# CS2 is the worst single point: a computed shielding of -119.4 against a
# real 192.8 ppm shift.
#
# PROTONS ARE NOT AFFECTED and are NOT excluded -- the effect is on the
# directly bonded nucleus. Measured: including the chlorinated compounds
# gives H a MAE of 0.213 ppm, excluding them 0.256. Slightly BETTER with
# them in, so they stay in for hydrogen. That asymmetry is exactly why
# exclusion is per element rather than per compound.
REFERENCE_COMPOUNDS: tuple[ReferenceCompound, ...] = (
    ReferenceCompound("Tetramethylsilane", "C[Si](C)(C)C", {"C": 0.0, "H": 0.0}),
    ReferenceCompound("Methane", "C", {"C": -2.3, "H": 0.23}),
    ReferenceCompound("Cyclohexane", "C1CCCCC1", {"C": 26.9, "H": 1.43}),
    ReferenceCompound(
        "Dichloromethane", "ClCCl", {"C": 53.8, "H": 5.30}, unsuitable_for=frozenset({"C"})
    ),
    ReferenceCompound("Nitromethane", "C[N+](=O)[O-]", {"C": 62.5, "H": 4.33}),
    ReferenceCompound("Acetylene", "C#C", {"C": 71.9, "H": 1.80}),
    ReferenceCompound(
        "Chloroform", "ClC(Cl)Cl", {"C": 77.2, "H": 7.26}, unsuitable_for=frozenset({"C"})
    ),
    ReferenceCompound(
        "Tetrachloromethane", "ClC(Cl)(Cl)Cl", {"C": 96.1}, unsuitable_for=frozenset({"C"})
    ),
    ReferenceCompound("Ethylene", "C=C", {"C": 123.3, "H": 5.40}),
    ReferenceCompound("Benzene", "c1ccccc1", {"C": 128.4, "H": 7.26}),
    ReferenceCompound(
        "Carbon disulfide", "S=C=S", {"C": 192.8}, unsuitable_for=frozenset({"C"})
    ),
)

# Below this, the fit is not describing a trend. Chosen to be permissive:
# a real calibration over this range lands well above 0.99, so anything
# under 0.95 means something is wrong with the runs, not merely noisy.
MIN_R_SQUARED = 0.95
# Two points define any line exactly, so an R^2 of 1.0 from two points
# means nothing at all.
MIN_POINTS = 4


class CalibrationError(ValueError):
    """The fit cannot be trusted, with a reason worth showing."""


def reference_molecule(compound: ReferenceCompound):
    """A real embedded-and-optimized structure for a calibration standard.

    Goes through the same `RDKitConformerProvider` path every molecule
    takes before an ORCA job -- a calibration run against a shortcut
    geometry would fit the shortcut, not the method. Imported lazily so
    this module stays importable (and its arithmetic testable) without
    RDKit being pulled in.
    """
    from rdkit import Chem

    from openchem.chem.conformer_providers import RDKitConformerProvider

    mol = Chem.MolFromSmiles(compound.smiles)
    if mol is None:
        raise CalibrationError(f"Could not parse reference SMILES for {compound.name}.")
    conformers = RDKitConformerProvider().generate_conformers(mol, num_conformers=1, optimize=True)
    if not conformers:
        raise CalibrationError(f"Could not embed a conformer for {compound.name}.")
    return conformers[0][0]


def fit_scaling(points: list[tuple[float, float]]) -> ScalingFactors:
    """Least-squares fit of experimental shift against computed shielding.

    `points` is (shielding, experimental_shift). Raises rather than
    returning a poor fit: a calibration that silently succeeds with a
    meaningless slope is worse than no calibration, because every shift
    downstream inherits it while looking more precise than before.
    """
    if len(points) < MIN_POINTS:
        raise CalibrationError(
            f"Need at least {MIN_POINTS} reference points to fit a scaling line, got {len(points)}."
        )

    count = len(points)
    mean_x = sum(x for x, _y in points) / count
    mean_y = sum(y for _x, y in points) / count
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in points)
    variance_x = sum((x - mean_x) ** 2 for x, _y in points)
    if variance_x == 0:
        raise CalibrationError(
            "Every reference compound produced the same shielding -- there is no line to fit."
        )

    slope = covariance / variance_x
    intercept = mean_y - slope * mean_x

    residual = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
    total = sum((y - mean_y) ** 2 for _x, y in points)
    r_squared = 1.0 if total == 0 else 1.0 - residual / total
    if r_squared < MIN_R_SQUARED:
        raise CalibrationError(
            f"Calibration fit is too poor to use (R^2 = {r_squared:.3f}). Check that the "
            "reference calculations completed and used consistent settings."
        )
    return ScalingFactors(
        slope=slope, intercept=intercept, r_squared=r_squared, sample_count=count
    )


def reference_points(
    shieldings: dict[str, list[float]], element: str
) -> list[tuple[float, float]]:
    """Pair each reference compound's MEAN computed shielding for `element`
    with its literature shift.

    Averaging over a compound's equivalent nuclei is the point of choosing
    single-environment standards: benzene's six carbons should agree, and
    where they differ slightly it is numerical noise that averaging
    removes rather than a real inequivalence.

    `shieldings` is keyed by compound name; a compound that has no
    literature value for this element, or that did not run, is skipped
    rather than defaulted -- a zero here would drag the whole line.
    """
    points = []
    for compound in REFERENCE_COMPOUNDS:
        if element in compound.unsuitable_for:
            continue
        expected = compound.shifts.get(element)
        computed = shieldings.get(compound.name)
        if expected is None or not computed:
            continue
        points.append((sum(computed) / len(computed), expected))
    return points


def scale_spectrum(
    values: dict[int, float], elements: dict[int, str], factors: dict[str, ScalingFactors]
) -> dict[int, float]:
    """Apply per-element scaling to a whole spectrum's raw shieldings.

    An atom whose element has no fitted factors is DROPPED, not passed
    through: a raw shielding (benzene carbon near 57) sitting in a column
    of real ppm shifts would read as a chemical shift and be wrong by
    seventy ppm.
    """
    scaled = {}
    for index, shielding in values.items():
        element_factors = factors.get(elements.get(index, ""))
        if element_factors is not None:
            scaled[index] = element_factors.apply(shielding)
    return scaled
