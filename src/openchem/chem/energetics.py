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

WHAT IS DELIBERATELY NOT HERE
=============================

**The detonation properties.** Kamlet-Jacobs needs the heat of detonation,
which needs the enthalpy of formation of the CONDENSED explosive. Joback
gives the ideal-GAS value, and the published bridge between them --
Trouton's rule as `188 x Tm` -- has a domain that **excludes every classic
energetic material**, measured: TNT, RDX and HMX carry 3-4 internal rotors
against the source's limit of two, PETN 12, nitroglycerin 8, while picric
acid and nitroguanidine fail its hydrogen-bonding arm as well. The nitro
groups ARE the rotors. See `docs/VALIDATION.md`.

**Flash point.** Lange's Table 5.23 is reference DATA -- autoignition
temperatures and flammability limits -- and not an estimation method. Having
the numbers is not having the model.
"""

from __future__ import annotations

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
