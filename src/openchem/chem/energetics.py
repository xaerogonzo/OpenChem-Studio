"""Oxygen balance for C/H/N/O substances [source:klapotke2017].

Oxygen balance says whether a substance carries enough oxygen to burn its own
carbon and hydrogen, as a percentage of its mass. Zero means exactly enough;
positive means an excess; negative means a deficiency.

WHY THERE ARE TWO OF THEM, AND WHY BOTH ARE REPORTED
====================================================

The number depends on what you burn the carbon TO, and the two answers differ
by a factor of three for TNT: **-74.0% to CO2, -24.7% to CO**. The source
subscripts them for exactly that reason and prints both closed forms, and
elsewhere writes that TAGNF "only has a positive oxygen balance with respect
to CO (not to CO2)".

So both are reported as separate named facts. **A `basis` PARAMETER WAS
CONSIDERED AND REJECTED**: it lets a screenshot collapse back to "oxygen
balance: -74%", which is the ambiguity the naming exists to prevent. Same
call `Copy Structure As` makes in refusing to collapse SMILES, InChI and
InChIKey into one entry -- choosing between them IS the point.

The project ships this under the specific convention and never as a bare
"oxygen balance", for the reason TSEI ships as *Cao-Liu TSEI*: a name that
covers two incompatible quantities is not a contract.

THIS IS FORMULA ARITHMETIC, WHICH IS WHY IT ACCEPTS A SALT
==========================================================

`chem/joback.py` refuses a disconnected structure, because it has to
decompose a molecule into groups and the union of two molecules is not a pure
component. Oxygen balance has no such need -- it reads the empirical formula.
**Ammonium nitrate is the case that settles it**: a two-fragment ionic solid,
and one of the nine rows of the source's own reference table. Refusing salts
here would refuse the source's own fixture.

THE DETONATION ESTIMATE, AND WHAT IT REFUSES TO GUESS
=====================================================

Kamlet-Jacobs [source:kamlet1968] estimates detonation pressure and velocity
from the elemental composition, the loading density, and the enthalpy of
formation of the CONDENSED explosive.

**THAT LAST INPUT IS REQUIRED AND IS NEVER ESTIMATED HERE.** Joback gives an
ideal-GAS enthalpy of formation, and the published bridge between the two --
Trouton's rule as `188 x Tm` -- has a domain that **excludes every classic
energetic material**, measured against the primary source's own criterion:
TNT, RDX and HMX carry 3-4 internal rotors against its limit of two, PETN 12,
nitroglycerin 8, while picric acid and nitroguanidine fail its
hydrogen-bonding arm as well. The nitro groups ARE the rotors. See
[source:westwell1995].

**Flash point.** Lange's Table 5.23 is reference DATA -- autoignition
temperatures and flammability limits -- and not an estimation method. Having
the numbers is not having the model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from openchem.domain.common import TOTAL, CacheState, Provenance, decline_total
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

#: DECLARED USER-FACING. `tests/test_calculator_reachability.py` fails if
#: nothing a user can press reaches this module.
USER_FACING_PROVIDER = "Oxygen balance, through the 'Oxygen Balance' calculator"

#: The elements the published formula is stated for: `CaHbNcOd`.
#:
#: A CLOSED SET, and the refusal it drives is the point. Sulfur, a halogen or
#: a metal each need their own oxidation accounting -- silently ignoring
#: those atoms would return a confident wrong number for, say, a
#: perchlorate, which is exactly the substance class somebody would ask
#: about.
CHNO = frozenset({"C", "H", "N", "O"})

#: 100 x the atomic mass of oxygen. The source writes the constant as 1600
#: rather than deriving it, and it is kept that way so the expression can be
#: read straight off the page.
_PERCENT_TIMES_OXYGEN_MASS = 1600.0


class OxygenBalanceRefusal(Enum):
    """Why oxygen balance does not apply to this structure.

    A VALUE rather than a message, so no consumer starts matching on prose --
    the shape `JobackRefusal`, `HlbRefusal` and `IsotopeRefusal` already use.
    """

    NOT_A_STRUCTURE = "the structure could not be read"
    NOT_CHNO = "the structure contains an element outside C, H, N and O"
    NO_ATOMS = "the structure has no atoms"


@dataclass(frozen=True)
class OxygenBalance:
    """Both conventions for one substance, or why neither applies.

    `to_carbon_dioxide` and `to_carbon_monoxide` are None exactly when
    `refusal` is set.
    """

    to_carbon_dioxide: float | None = None
    to_carbon_monoxide: float | None = None
    refusal: OxygenBalanceRefusal | None = None
    #: Which element disqualified it, when that is why it was refused.
    detail: str = ""
    formula: str = ""
    molecular_weight: float = 0.0
    #: The a, b, d of `CaHbNcOd`, so a reader can check the arithmetic.
    carbon: int = 0
    hydrogen: int = 0
    oxygen: int = 0

    @property
    def applicable(self) -> bool:
        return self.refusal is None


def oxygen_balance(mol: Chem.Mol | None) -> OxygenBalance:
    """Both oxygen balances for a C/H/N/O substance.

        Omega_CO2 = (d - 2a - b/2) x 1600 / M
        Omega_CO  = (d -  a - b/2) x 1600 / M

    Note there is **no leading minus**, which is worth stating because a
    review of this work supplied one: with it, TNT comes out +74% and
    nitroglycerin -3.5%, both exactly backwards from the values the same
    review quoted. The source's own worked example is TNT = -74%.
    """
    if mol is None:
        return OxygenBalance(refusal=OxygenBalanceRefusal.NOT_A_STRUCTURE)
    if mol.GetNumAtoms() == 0:
        return OxygenBalance(refusal=OxygenBalanceRefusal.NO_ATOMS)

    # Explicit hydrogens, because the formula counts every one of them and a
    # drawn structure carries most of its hydrogens implicitly.
    try:
        counted = Chem.AddHs(Chem.Mol(mol))
    except Exception:
        return OxygenBalance(refusal=OxygenBalanceRefusal.NOT_A_STRUCTURE)

    tally: dict[str, int] = {}
    for atom in counted.GetAtoms():
        tally[atom.GetSymbol()] = tally.get(atom.GetSymbol(), 0) + 1

    outside = sorted(set(tally) - CHNO)
    if outside:
        return OxygenBalance(
            refusal=OxygenBalanceRefusal.NOT_CHNO,
            detail=", ".join(outside),
            formula=rdMolDescriptors.CalcMolFormula(mol),
        )

    a = tally.get("C", 0)
    b = tally.get("H", 0)
    d = tally.get("O", 0)
    mass = Descriptors.MolWt(mol)
    if mass <= 0:
        return OxygenBalance(refusal=OxygenBalanceRefusal.NO_ATOMS)

    scale = _PERCENT_TIMES_OXYGEN_MASS / mass
    return OxygenBalance(
        to_carbon_dioxide=(d - 2 * a - b / 2) * scale,
        to_carbon_monoxide=(d - a - b / 2) * scale,
        formula=rdMolDescriptors.CalcMolFormula(mol),
        molecular_weight=mass,
        carbon=a,
        hydrogen=b,
        oxygen=d,
    )


def refusal_text(result: OxygenBalance) -> str:
    """One sentence saying what could not be done, and why.

    Generated in ONE place so `if "refused" in message` never becomes
    application logic.
    """
    if result.refusal is None:
        return ""
    if result.refusal is OxygenBalanceRefusal.NOT_CHNO:
        return (
            f"Oxygen balance as published is defined for C/H/N/O substances, and this "
            f"structure contains {result.detail}. Sulfur, the halogens and metals each "
            "need their own oxidation accounting, so ignoring those atoms would give a "
            "confident wrong number rather than a rougher one."
        )
    if result.refusal is OxygenBalanceRefusal.NO_ATOMS:
        return "This structure has no atoms to balance."
    return "This structure could not be read."


def compute_oxygen_balance(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """Both oxygen balances as the "energetic" category's calculator."""
    parameters = parameters or {}
    places = int(parameters.get("decimal_places", 1))
    result = oxygen_balance(mol)

    provenance = Provenance(
        created_by="core",
        method="oxygen_balance_chno",
        parameters={
            "decimal_places": places,
            "formula": result.formula,
            "refusal": result.refusal.name if result.refusal else None,
            TOTAL: decline_total(
                "Two conventions for one substance, not two components of a sum. "
                "Adding them together means nothing."
            ),
        },
    )

    if not result.applicable:
        return ReportResult(
            report_id="oxygen_balance",
            name="Oxygen Balance",
            category="energetic",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=refusal_text(result),
            provenance=provenance,
        )

    shared = (
        "Positive means the substance carries more oxygen than it needs to burn "
        "its own carbon and hydrogen; negative means less; zero means exactly "
        "enough.",
    )
    limits = (
        "A composition figure, not a performance one. It says nothing on its own "
        "about how powerful, sensitive or stable a substance is.",
    )

    facts = (
        Fact(
            category=FactCategory.STRUCTURE,
            label="Oxygen balance (CO₂ basis)",
            value=result.to_carbon_dioxide,
            display_value=f"{result.to_carbon_dioxide:+.{places}f}",
            units="%",
            source="oxygen_balance",
            basis=Basis.DETERMINISTIC,
            evidence=(
                f"(d - 2a - b/2) x 1600 / M, with a={result.carbon}, "
                f"b={result.hydrogen}, d={result.oxygen}, "
                f"M={result.molecular_weight:.2f}.",
            ) + shared,
            limitations=limits,
        ),
        Fact(
            category=FactCategory.STRUCTURE,
            label="Oxygen balance (CO basis)",
            value=result.to_carbon_monoxide,
            display_value=f"{result.to_carbon_monoxide:+.{places}f}",
            units="%",
            source="oxygen_balance",
            basis=Basis.DETERMINISTIC,
            evidence=(
                f"(d - a - b/2) x 1600 / M -- carbon burned only to CO, so each "
                "carbon needs one oxygen rather than two.",
            ) + shared,
            limitations=limits + (
                "A DIFFERENT QUANTITY from the CO2 figure above, not a refinement "
                "of it. They differ by a factor of three for TNT (-74.0% against "
                "-24.7%), and a substance can be positive on one and negative on "
                "the other.",
            ),
        ),
        Fact(
            category=FactCategory.IDENTITY,
            label="Formula",
            value=result.formula,
            display_value=result.formula,
            source="oxygen_balance",
            basis=Basis.DETERMINISTIC,
            evidence=("Hydrogens counted explicitly, since the formula needs all of them.",),
        ),
    )

    return ReportResult(
        report_id="oxygen_balance",
        name="Oxygen Balance",
        category="energetic",
        molecule_uuid=molecule_uuid,
        facts=facts,
        limitations=(
            "Reported on both conventions because they are different quantities. "
            "A figure quoted as a bare 'oxygen balance' is ambiguous between them.",
        ),
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Kamlet-Jacobs detonation properties [source:kamlet1968]
# ---------------------------------------------------------------------------
#
#     P [kbar]  = K rho0^2 phi           Eq. (8),  K = 15.58
#     D [mm/us] = A phi^0.5 (1 + B rho0) Eq. (9),  A = 1.01, B = 1.30
#     phi       = N M^0.5 Q^0.5
#
# **K IS 15.58, AND THE TEXTBOOK THAT SUPPLIES THIS PROJECT'S OXYGEN BALANCE
# SAYS 15.88.** [source:klapotke2017] prints 15.88 at p253 and again in its
# Appendix; the paper it cites for the equations states 15.58 FOUR times --
# the abstract, Eq. (8), the slope of its Fig. 1, and again on the Table III
# page. '15.88' occurs nowhere in it. The difference is 1.9% on every
# pressure, and BOTH VALUES PRODUCE ENTIRELY PLAUSIBLE NUMBERS (HMX comes out
# 392.1 against the paper's own 384.7), so nothing downstream can catch it.
# `tests/test_energetics.py` mutates it by name for that reason.

#: Eq. (8) and Eq. (9). Named separately from their values so a reader can
#: see which constant belongs to which equation.
DETONATION_PRESSURE_K = 15.58
DETONATION_VELOCITY_A = 1.01
DETONATION_VELOCITY_B = 1.30

#: Eq. (15b)'s two constants, which are standard heats of formation already
#: folded in -- 28.9 per hydrogen is -(1/2)(-57.8) for water(g), and 47.0 per
#: (d - b/2) is -(1/2)(-94.1) for CO2. Carbon is taken as nil, and nitrogen
#: is zero by definition. So NO enthalpy of formation is typed here from
#: memory: the paper pre-computed them into the equation.
_Q_WATER_PER_HYDROGEN = 28.9
_Q_CARBON_DIOXIDE = 47.0

#: The paper's footnote 19: below this the H2/H2O equilibrium "would tend to
#: introduce complications". Its own tables still go down to 1.000 g/cc, so
#: this is a stated limitation and NOT a refusal.
LOADING_DENSITY_FLOOR = 1.0

#: Eq. (16). Explicitly for matching RUBY and, in the paper's own words, "not
#: necessarily applicable for the prediction of actual detonation
#: parameters". An OPT-IN that says so, never a default.
RUBY_CORRECTION_G_THRESHOLD = 0.93
RUBY_CORRECTION_FRACTION = 0.06


class DetonationRefusal(Enum):
    """Why Kamlet-Jacobs does not apply."""

    NOT_A_STRUCTURE = "the structure could not be read"
    NOT_CHNO = "the structure contains an element outside C, H, N and O"
    OUTSIDE_THE_ARBITRARY = "the oxygen content is outside Eq. (12)'s range"
    NO_LOADING_DENSITY = "no loading density was supplied"
    NO_ENTHALPY_OF_FORMATION = "no condensed-phase enthalpy of formation was supplied"


@dataclass(frozen=True)
class Detonation:
    """A Kamlet-Jacobs estimate, or why it could not be made."""

    pressure_kbar: float | None = None
    velocity_mm_per_us: float | None = None
    #: phi = N M^0.5 Q^0.5, the paper's own grouping.
    phi: float | None = None
    #: Eq. (13): moles of gaseous detonation product per gram of explosive.
    moles_gas_per_gram: float | None = None
    #: Eq. (14): mean molar mass of those gases, g/mol.
    mean_gas_mass: float | None = None
    #: Eq. (15b): heat of detonation, cal/g.
    heat_of_detonation: float | None = None
    #: G = N x M, which Eq. (16)'s correction is keyed on.
    g_factor: float | None = None
    refusal: DetonationRefusal | None = None
    detail: str = ""

    @property
    def applicable(self) -> bool:
        return self.refusal is None


def arbitrary_gas(a: int, b: int, c: int, d: int) -> tuple[float, float]:
    """N and M from the H2O-CO2 arbitrary, Eqs. (13) and (14).

        CaHbNcOd -> (c/2) N2 + (b/2) H2O + (d/2 - b/4) CO2 + (a - d/2 + b/4) C

    **EQUATION (14) IS MISPRINTED IN THE PAPER, AND THE PAPER'S OWN TABLES
    PROVE IT.** It appears as

        M = (56c - 88d - 8b) / (2c + 2d + b)

    with two minus signs -- read at 3x magnification, where the typeface makes
    a minus plainly distinct from the bold `+` of Eq. (13) directly above it,
    and the text layer agrees. That form is impossible: it gives RDX a
    detonation gas of **-8.0 g/mol**.

    The form below follows from Eq. (12) by direct derivation, and reproduces
    the M values the paper's own Table VI prints, exactly:

        TATB   27.20     R-salt 23.00
        TNB    32.00     TNA    30.00

    against the printed equation's -8.00, 1.00, -18.29 and -14.00. Four for
    four, so this is a typesetting error in the source rather than a reading
    error here.
    """
    moles_gas_x4 = 2 * c + 2 * d + b
    n = moles_gas_x4 / (48 * a + 4 * b + 56 * c + 64 * d)
    m = (56 * c + 88 * d - 8 * b) / moles_gas_x4
    return n, m


def heat_of_detonation(a: int, b: int, c: int, d: int, enthalpy_kcal_per_mol: float) -> float:
    """Eq. (15b), in cal/g.

    `enthalpy_kcal_per_mol` is the CONDENSED-phase standard enthalpy of
    formation of the explosive, in kcal/mol -- the paper's own unit.

    THE FACTOR OF 1000 IS THE UNIT CONVERSION AND IS EASY TO LOSE: the
    numerator is kcal/mol and the denominator g/mol, so the quotient is
    kcal/g while Eq. (8) wants cal/g. Checked by inverting the paper's own
    printed Q values -- TATB's 1075 cal/g implies -37.05 kcal/mol against a
    literature -36.9, and three further compounds land equally sensibly.
    """
    formula_weight = 12 * a + b + 14 * c + 16 * d
    numerator = (_Q_WATER_PER_HYDROGEN * b
                 + _Q_CARBON_DIOXIDE * (d - b / 2)
                 + enthalpy_kcal_per_mol)
    return 1000.0 * numerator / formula_weight


def detonation_from_parameters(
    moles_gas_per_gram: float,
    mean_gas_mass: float,
    heat_cal_per_gram: float,
    loading_density: float,
    *,
    ruby_correction: bool = False,
) -> Detonation:
    """Eqs. (8) and (9) alone, from N, M, Q and rho0.

    Separated from the structure path deliberately: the paper's Table III
    prints all four inputs AND the resulting P and D, so this layer has a
    correctness oracle that needs no thermochemistry at all. Eight rows
    reproduce to 0.08 kbar and 0.012 mm/us.
    """
    if min(moles_gas_per_gram, mean_gas_mass, heat_cal_per_gram, loading_density) <= 0:
        return Detonation(refusal=DetonationRefusal.NOT_A_STRUCTURE)
    phi = moles_gas_per_gram * math.sqrt(mean_gas_mass) * math.sqrt(heat_cal_per_gram)
    pressure = DETONATION_PRESSURE_K * loading_density ** 2 * phi
    g = moles_gas_per_gram * mean_gas_mass
    if ruby_correction and g > RUBY_CORRECTION_G_THRESHOLD:
        pressure *= 1.0 - RUBY_CORRECTION_FRACTION
    velocity = (DETONATION_VELOCITY_A * math.sqrt(phi)
                * (1.0 + DETONATION_VELOCITY_B * loading_density))
    return Detonation(
        pressure_kbar=pressure,
        velocity_mm_per_us=velocity,
        phi=phi,
        moles_gas_per_gram=moles_gas_per_gram,
        mean_gas_mass=mean_gas_mass,
        heat_of_detonation=heat_cal_per_gram,
        g_factor=g,
    )


def detonation(
    mol: Chem.Mol | None,
    loading_density: float | None,
    enthalpy_kcal_per_mol: float | None,
    *,
    ruby_correction: bool = False,
) -> Detonation:
    """The full estimate from a structure, a density and a measured enthalpy.

    Both of the latter are REQUIRED. The app has no source-backed route to a
    loading density -- and it is the density the charge was actually loaded
    at, not a predicted crystal density, which is a different number that P
    depends on as its square.
    """
    balance = oxygen_balance(mol)
    if not balance.applicable:
        mapped = {
            OxygenBalanceRefusal.NOT_CHNO: DetonationRefusal.NOT_CHNO,
        }.get(balance.refusal, DetonationRefusal.NOT_A_STRUCTURE)
        return Detonation(refusal=mapped, detail=balance.detail)

    if loading_density is None or loading_density <= 0:
        return Detonation(refusal=DetonationRefusal.NO_LOADING_DENSITY)
    if enthalpy_kcal_per_mol is None:
        return Detonation(refusal=DetonationRefusal.NO_ENTHALPY_OF_FORMATION)

    a, b, d = balance.carbon, balance.hydrogen, balance.oxygen
    c = _nitrogen_count(mol)

    # Eq. (12) is stated for a compound with "at least enough oxygen to
    # convert hydrogen to H2O but no more than is also required to convert
    # carbon to CO2". Outside that, the decomposition it assumes is not the
    # one that happens -- nitroglycerin is over-oxidised and would need an
    # excess-O2 product, which this arbitrary does not model.
    low, high = b / 2, 2 * a + b / 2
    if not (low <= d <= high):
        side = "over-oxidised" if d > high else "too little oxygen to form water"
        return Detonation(
            refusal=DetonationRefusal.OUTSIDE_THE_ARBITRARY,
            detail=f"{side}: needs {low:g} <= O <= {high:g}, has {d}",
        )

    n, m = arbitrary_gas(a, b, c, d)
    q = heat_of_detonation(a, b, c, d, enthalpy_kcal_per_mol)
    if q <= 0:
        return Detonation(
            refusal=DetonationRefusal.OUTSIDE_THE_ARBITRARY,
            detail="the heat of detonation comes out non-positive",
        )
    return detonation_from_parameters(n, m, q, loading_density,
                                      ruby_correction=ruby_correction)


def _nitrogen_count(mol: Chem.Mol) -> int:
    return sum(1 for atom in Chem.AddHs(Chem.Mol(mol)).GetAtoms()
               if atom.GetSymbol() == "N")


def detonation_refusal_text(result: Detonation) -> str:
    """One sentence, generated in one place."""
    if result.refusal is None:
        return ""
    if result.refusal is DetonationRefusal.NO_LOADING_DENSITY:
        return (
            "Kamlet-Jacobs needs the INITIAL LOADING DENSITY of the charge, in "
            "g/cm3, and there is no source-backed way to obtain it from a structure. "
            "It is not a predicted crystal density: detonation pressure goes as its "
            "square, so substituting one would quietly change the answer."
        )
    if result.refusal is DetonationRefusal.NO_ENTHALPY_OF_FORMATION:
        return (
            "Kamlet-Jacobs needs the CONDENSED-phase enthalpy of formation, in "
            "kcal/mol. Joback's is the ideal-gas value, and the published rule for "
            "bridging the two excludes every classic energetic material -- its domain "
            "stops at two internal rotors, and the nitro groups are the rotors. Supply "
            "a measured value."
        )
    if result.refusal is DetonationRefusal.OUTSIDE_THE_ARBITRARY:
        return (
            f"The H2O-CO2 arbitrary is stated for a compound with at least enough "
            f"oxygen to form water and no more than is needed to form CO2, and this "
            f"one is {result.detail}. Outside that range the decomposition it assumes "
            "is not the one that occurs."
        )
    if result.refusal is DetonationRefusal.NOT_CHNO:
        return (
            f"Kamlet-Jacobs is stated for C/H/N/O explosives, and this structure "
            f"contains {result.detail}."
        )
    return "This structure could not be read."


#: Sentinel for "the user has not supplied one".
#:
#: A REAL enthalpy of formation of zero is legitimate, so it cannot double as
#: "unset" -- and getting that wrong would compute a confident number from a
#: value nobody entered. CHNO explosives run roughly -200 to +200 kcal/mol,
#: so this is outside anything real by a wide margin.
ENTHALPY_NOT_SUPPLIED = -1000.0


def compute_detonation(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """Kamlet-Jacobs detonation pressure and velocity, or a named refusal.

    TWO INPUTS ARE REQUIRED AND NEITHER IS ESTIMATED. See the module
    docstring: the loading density is a property of the charge rather than of
    the molecule, and the condensed-phase enthalpy of formation has no
    honest route from Joback's ideal-gas value for this compound class.
    """
    parameters = parameters or {}
    places = int(parameters.get("decimal_places", 1))
    density = float(parameters.get("loading_density_g_cm3", 0.0) or 0.0)
    enthalpy = float(parameters.get("enthalpy_of_formation_kcal_mol", ENTHALPY_NOT_SUPPLIED))
    ruby = bool(parameters.get("ruby_correction", False))

    supplied = None if enthalpy <= ENTHALPY_NOT_SUPPLIED else enthalpy
    result = detonation(mol, density or None, supplied, ruby_correction=ruby)

    provenance = Provenance(
        created_by="core",
        method="kamlet_jacobs_1968",
        parameters={
            "decimal_places": places,
            "loading_density_g_cm3": density or None,
            "enthalpy_of_formation_kcal_mol": supplied,
            "enthalpy_source": "supplied_by_user" if supplied is not None else None,
            "ruby_correction": ruby,
            "K": DETONATION_PRESSURE_K,
            "refusal": result.refusal.name if result.refusal else None,
            TOTAL: decline_total(
                "A pressure and a velocity are not components of a sum."
            ),
        },
    )

    if not result.applicable:
        return ReportResult(
            report_id="detonation",
            name="Detonation (Kamlet-Jacobs)",
            category="energetic",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=detonation_refusal_text(result),
            provenance=provenance,
        )

    density_note: tuple[str, ...] = ()
    if density < LOADING_DENSITY_FLOOR:
        density_note = (
            f"Below {LOADING_DENSITY_FLOOR:g} g/cm3 the paper notes the hydrogen "
            "equilibrium 'would tend to introduce complications'. Its own tables "
            "still go this low, so this is a caution rather than a refusal.",
        )

    shared = (
        "Estimated from the elemental composition, the loading density and a "
        "SUPPLIED condensed-phase enthalpy of formation. Nothing here is measured.",
    )
    ruby_note = (
        ("A -6% correction was applied because G > 0.93. The paper offers it for "
         "matching the RUBY code and says it is 'not necessarily applicable for the "
         "prediction of actual detonation parameters'.",)
        if ruby and result.g_factor and result.g_factor > RUBY_CORRECTION_G_THRESHOLD
        else ()
    )

    facts = (
        Fact(
            category=FactCategory.STRUCTURE,
            label="Detonation pressure (C-J)",
            value=result.pressure_kbar,
            display_value=f"{result.pressure_kbar:.{places}f}",
            units="kbar",
            source="detonation",
            basis=Basis.HEURISTIC,
            evidence=(f"Eq. (8): P = K rho0^2 phi, with K = {DETONATION_PRESSURE_K}.",) + shared,
            limitations=(
                "Goes as the SQUARE of the loading density, so an approximate "
                "density is not an approximate answer.",
            ) + density_note + ruby_note,
        ),
        Fact(
            category=FactCategory.STRUCTURE,
            label="Detonation velocity",
            value=result.velocity_mm_per_us,
            display_value=f"{result.velocity_mm_per_us:.3f}",
            units="mm/us",
            source="detonation",
            basis=Basis.HEURISTIC,
            evidence=(
                f"Eq. (9): D = A phi^0.5 (1 + B rho0), with A = "
                f"{DETONATION_VELOCITY_A} and B = {DETONATION_VELOCITY_B}.",
            ) + shared,
            limitations=density_note,
        ),
        Fact(
            category=FactCategory.STRUCTURE,
            label="Heat of detonation",
            value=result.heat_of_detonation,
            display_value=f"{result.heat_of_detonation:.0f}",
            units="cal/g",
            source="detonation",
            basis=Basis.HEURISTIC,
            evidence=("Eq. (15b), from the supplied enthalpy of formation.",),
        ),
        Fact(
            category=FactCategory.STRUCTURE,
            label="Gas per gram (N)",
            value=result.moles_gas_per_gram,
            display_value=f"{result.moles_gas_per_gram:.4f}",
            units="mol/g",
            source="detonation",
            basis=Basis.DETERMINISTIC,
            evidence=("Eq. (13), from the H2O-CO2 arbitrary decomposition.",),
        ),
        Fact(
            category=FactCategory.STRUCTURE,
            label="Mean gas mass (M)",
            value=result.mean_gas_mass,
            display_value=f"{result.mean_gas_mass:.2f}",
            units="g/mol",
            source="detonation",
            basis=Basis.DETERMINISTIC,
            evidence=(
                "Eq. (14) -- as DERIVED from Eq. (12), because the equation is "
                "misprinted in the paper and the printed form gives a negative "
                "molar mass.",
            ),
        ),
    )

    return ReportResult(
        report_id="detonation",
        name="Detonation (Kamlet-Jacobs)",
        category="energetic",
        molecule_uuid=molecule_uuid,
        facts=facts,
        limitations=(
            "An empirical correlation fitted to reproduce a 1968 computer code, not "
            "a measurement and not a safety assessment.",
            "The loading density is the density of the CHARGE. It is not a crystal "
            "density and is not inferred from the structure.",
        ),
        provenance=provenance,
    )
