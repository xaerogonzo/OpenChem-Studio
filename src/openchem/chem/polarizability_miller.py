"""Miller's atomic-hybrid polarizability, both methods, with the traps.

WHY THIS WAS DEFERRED. `docs/VALIDATION.md`: "The parameters are
unpublished. A reconstruction missed benzene by +27% and CCl4 by -50%, so
there was nothing to validate against." The first sentence was a claim
about ChemAxon's documentation rather than about the literature -- Miller
1990's Table I ([source:miller1990]) prints every one of them.

**TWO METHODS, AND MIXING THEM IS THE FIRST TRAP.**

    ahc   alpha = (4/N) * (SUM_A tau_A)^2      N = TOTAL ELECTRONS
    ahp   alpha = SUM_A alpha_A                plain additivity

The ahc form is [source:miller1979]'s and is what the papers' molecular
tables are computed with. **Squaring a sum is what makes it not a
group-additivity scheme**, so feeding the ahp column into it -- or
summing the tau column -- produces numbers that look entirely reasonable
and are wrong. Both are offered here, named, because the paper offers
both; neither is the default for the other.

**AND `CBR` IS THE SECOND TRAP, WHICH IS ALMOST CERTAINLY WHAT SANK THE
EARLIER RECONSTRUCTION.** Its symbol reads as "carbon in a benzene ring".
It is not. The 1979 paper:

    "The difficulty was traced to the two kinds of carbon atoms present
    in the pi-electronic system. In ethylene AND BENZENE the pi system is
    directed only along two bonds, whereas in the 9 and 10 positions of
    naphthalene it is directed along all three bonds."

So a benzene carbon is `CTR`, and `CBR` belongs to the pi-BRANCHED
carbons -- ring-fusion positions in polycyclics. Measured here: assigning
benzene's carbons to CBR gives 13.99 A^3 against an experimental 10.39,
which is +36% and the same error class as the +27% on record.

THE ACCEPTANCE ORACLE IS BENZENE AND CCl4, for exactly that reason: they
are the two the earlier attempt got wrong. `tests/test_polarizability_
miller.py` fails if either drifts, and a failure there means the table or
the assignment is wrong rather than that a tolerance wants widening.

WHAT THIS IS NOT. It is an EMPIRICAL scheme fitted to ~240 molecules, so
it says nothing about a structure unlike those; and it is isotropic --
an average polarizability, not a tensor. The 1990 paper's companion --
"Calculation of the molecular polarizability tensor", JACS 112, 8543 --
treats the tensor and is NOT implemented. Its DOI is deliberately not
written here: the registry's backstop treats any DOI in the tree as a
citation that must resolve to an entry, and an unused source inflates
the registry rather than documenting it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdkit import Chem

_DATA = Path(__file__).resolve().parent / "data"


class MillerAssignmentError(ValueError):
    """An atom Miller's table has no hybrid row for.

    RAISED RATHER THAN GUESSED AT. The table covers H, C, N, O, S, P and
    the four halogens; a boron or a metal has no parameter, and inventing
    one would produce a plausible number for a molecule the method was
    never fitted to.
    """


@dataclass(frozen=True)
class MillerPolarizability:
    """Both of Miller's answers for one structure, in A^3."""

    ahc: float
    ahp: float
    #: `{paper symbol: count}` -- the assignment, so a disagreement can be
    #: traced to a row of Table I rather than merely observed.
    assignment: dict[str, int]
    electrons: int


@lru_cache(maxsize=1)
def _payload() -> dict:
    return json.loads(
        (_DATA / "miller_polarizability.json").read_text(encoding="utf-8")
    )


def parameters() -> dict[str, dict]:
    return _payload()["parameters"]


def _carbon_symbol(atom: Chem.Atom) -> str:
    hybridisation = atom.GetHybridization()
    if hybridisation == Chem.HybridizationType.SP3:
        return "CTE"
    if hybridisation == Chem.HybridizationType.SP:
        return "CDI"
    if hybridisation != Chem.HybridizationType.SP2:
        raise MillerAssignmentError(
            f"carbon {atom.GetIdx()} is {hybridisation}, which Table I has no row for"
        )
    # THE CBR RULE, and it is the one thing in this file most worth
    # getting right. A trigonal carbon is `CBR` only when its pi system
    # runs along all THREE bonds -- naphthalene's 9,10 positions -- which
    # means three heavy neighbours, every one of them also trigonal. A
    # benzene carbon has two such neighbours and a hydrogen, so it is
    # `CTR`, which is what the 1979 paper says in as many words.
    heavy = [n for n in atom.GetNeighbors() if n.GetAtomicNum() > 1]
    if len(heavy) == 3 and all(
        n.GetHybridization() == Chem.HybridizationType.SP2 for n in heavy
    ):
        return "CBR"
    return "CTR"


def _symbol_for(atom: Chem.Atom) -> str:
    """Which row of Table I this atom belongs to."""
    number = atom.GetAtomicNum()
    simple = {1: "H", 9: "F", 17: "Cl", 35: "Br", 53: "I", 15: "PTE"}
    if number in simple:
        return simple[number]
    if number == 6:
        return _carbon_symbol(atom)

    hybridisation = atom.GetHybridization()
    if number == 7:
        if hybridisation == Chem.HybridizationType.SP3:
            return "NTE"
        if hybridisation == Chem.HybridizationType.SP:
            return "NDI"
        # A trigonal nitrogen donating its lone pair to the pi system --
        # pyrrole, an amide, an aniline -- is NPI2; one holding it in
        # plane, as in pyridine, is NTR2. `GetIsAromatic` on the nitrogen
        # plus a ring is not enough to tell those apart, so the test is
        # whether the lone pair is conjugated: RDKit marks the pyrrole
        # case with an explicit or implicit H, or three sigma bonds.
        if atom.GetTotalDegree() == 3:
            return "NPI2"
        return "NTR2"
    if number == 8:
        if hybridisation == Chem.HybridizationType.SP3:
            return "OTE"
        if atom.GetTotalDegree() == 2:
            return "OPI2"
        return "OTR4"
    if number == 16:
        if hybridisation == Chem.HybridizationType.SP3:
            return "STE"
        if atom.GetTotalDegree() == 2:
            return "SPI2"
        return "STR4"
    raise MillerAssignmentError(
        f"atomic number {number} has no row in Miller's Table I"
    )


def miller_polarizability(mol: Chem.Mol) -> MillerPolarizability:
    """Both methods, on a structure with EXPLICIT hydrogens.

    Hydrogens are added here rather than demanded of the caller, because
    they carry their own parameter and their own electrons: computing
    this on an implicit-H molecule silently drops both, and the answer
    still looks like a polarizability.
    """
    mol = Chem.AddHs(mol)
    table = parameters()

    assignment: dict[str, int] = {}
    tau_sum = 0.0
    alpha_sum = 0.0
    electrons = 0
    for atom in mol.GetAtoms():
        symbol = _symbol_for(atom)
        row = table[symbol]
        assignment[symbol] = assignment.get(symbol, 0) + 1
        tau_sum += row["tau_ahc"]
        alpha_sum += row["alpha_ahp"]
        electrons += atom.GetAtomicNum()

    if electrons == 0:  # pragma: no cover - a molecule with no atoms
        raise MillerAssignmentError("a structure with no electrons has no polarizability")
    return MillerPolarizability(
        ahc=4.0 / electrons * tau_sum**2,
        ahp=alpha_sum,
        assignment=assignment,
        electrons=electrons,
    )
