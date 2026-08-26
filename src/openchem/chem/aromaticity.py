"""HOMA -- the harmonic oscillator model of aromaticity, per ring.

`[source:krygowski1993]`, and the model's original definition in
`[source:kruszewski1972]`.

    HOMA = 1 - (1/n) * SUM over ring bonds of  alpha(type) * (R_opt(type) - R_i)^2

with `n` every bond in the ring. Eq. 8's multi-bond-type form is the shipped
one: a heterocycle mixes CC, CN, CO and the rest, and each bond is weighted
the SAME regardless of type. Parameters are in `data/homa_parameters.json`.

**IT NEEDS REAL BOND LENGTHS, SO IT NEEDS A 3D CONFORMER.** This project
already records what a 2D depiction's coordinates are worth as measurements:
"a 2D depiction has coordinates, and they are not measurements" -- aspirin's
2D C=O reads 1.5 "units" against a real 1.264 A. Every bond in a layout comes
out about the same length whatever its order, which would make HOMA report
near-perfect aromaticity for anything drawn. So a molecule without a real
conformer is REFUSED rather than answered.

**PER RING, NEVER PER MOLECULE.** HOMA is defined on a pi-electron system,
and the paper's own point is that fusing rings changes each ring's local
aromatic character -- Figure 3 gives perylene's individual rings values from
0.448 to 0.952. A single number for a polycyclic molecule would average away
exactly what the index is for.

**1 IS THE TOP AND THERE IS NO BOTTOM.** 1 means every bond sits at R_opt;
0 is the reference Kekule structure with alternating R_s and R_d. A strongly
bond-alternating or strained ring goes NEGATIVE, and that is meaningful
rather than an error.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from rdkit import Chem

from openchem.domain.common import TOTAL, CacheState, Provenance, decline_total
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

_PARAMETERS_PATH = Path(__file__).parent / "data" / "homa_parameters.json"
_BIRD_PATH = Path(__file__).parent / "data" / "bird_parameters.json"


class GeometricAromaticityRefusal(Enum):
    """Why a geometric aromaticity index cannot be given here.

    A VALUE rather than a message, the shape `JobackRefusal`, `HansenRefusal`
    and `IsotopeRefusal` already use.

    **SHARED BY HOMA AND BIRD, because every reason is a property of the
    QUESTION rather than of one index.** Both read real bond lengths, so both
    refuse a drawing; both walk rings, so both refuse a structure with none;
    and both are parameterised per bond type, so both refuse a bond their
    table does not carry. Two enums with the same members would be two places
    to add the next reason to.

    `UNSUPPORTED_RING_SIZE` is Bird's alone -- HOMA has no size-dependent
    constant -- and lives here rather than in a second enum for the same
    reason.
    """

    NOT_A_STRUCTURE = "the structure could not be read"
    NO_CONFORMER = "this needs a real 3D conformer"
    NO_RINGS = "the structure has no rings"
    UNPARAMETRISED_BOND = "a ring bond has no parameters for this index"
    UNSUPPORTED_RING_SIZE = "this index has no reference value for this ring size"


#: The name HOMA shipped under. Kept as an alias so nothing that imports it
#: breaks, the way `AtomFact = Fact` was kept when the report types merged.
HomaRefusal = GeometricAromaticityRefusal


@lru_cache(maxsize=1)
def _parameters() -> dict:
    return json.loads(_PARAMETERS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _by_elements() -> dict[frozenset[str], dict]:
    """Bond parameters keyed on the unordered element pair.

    The DEPRECATED row is excluded here rather than filtered at the call
    site: the paper's footnote i says outright to use CCa, and leaving CCb
    reachable would make the answer depend on dict ordering. It stays in the
    JSON for provenance.
    """
    out: dict[frozenset[str], dict] = {}
    for name, row in _parameters()["bonds"].items():
        if row.get("deprecated"):
            continue
        key = frozenset(row["elements"])
        if key in out:
            raise ValueError(f"two HOMA parameter sets claim {sorted(key)}")
        out[key] = {"name": name, **row}
    return out


@dataclass(frozen=True)
class RingHoma:
    """HOMA for one ring, or why it could not be given."""

    atom_indices: tuple[int, ...]
    value: float | None = None
    refusal: GeometricAromaticityRefusal | None = None
    detail: str = ""
    #: How many bonds of each parameter set the ring used, so a reader can see
    #: a heterocycle really did mix them rather than trust that it did.
    bond_types: dict[str, int] | None = None

    @property
    def applicable(self) -> bool:
        return self.refusal is None


@dataclass(frozen=True)
class HomaResult:
    rings: tuple[RingHoma, ...] = ()
    refusal: GeometricAromaticityRefusal | None = None
    detail: str = ""

    @property
    def applicable(self) -> bool:
        return self.refusal is None


def _bond_length(conformer: Chem.Conformer, i: int, j: int) -> float:
    a = conformer.GetAtomPosition(i)
    b = conformer.GetAtomPosition(j)
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def ring_homa(mol: Chem.Mol, ring: tuple[int, ...]) -> RingHoma:
    """HOMA for one ring, given by its atom indices in ring order."""
    conformer = mol.GetConformer()
    table = _by_elements()

    total = 0.0
    counts: dict[str, int] = {}
    size = len(ring)
    for position in range(size):
        i = ring[position]
        j = ring[(position + 1) % size]
        bond = mol.GetBondBetweenAtoms(i, j)
        if bond is None:
            return RingHoma(
                atom_indices=ring,
                refusal=GeometricAromaticityRefusal.UNPARAMETRISED_BOND,
                detail=f"atoms {i} and {j} are not bonded",
            )
        pair = frozenset(
            (mol.GetAtomWithIdx(i).GetSymbol(), mol.GetAtomWithIdx(j).GetSymbol())
        )
        row = table.get(pair)
        if row is None:
            return RingHoma(
                atom_indices=ring,
                refusal=GeometricAromaticityRefusal.UNPARAMETRISED_BOND,
                detail=f"{'-'.join(sorted(pair))} has no HOMA parameters",
            )
        measured = _bond_length(conformer, i, j)
        total += row["alpha"] * (row["R_opt"] - measured) ** 2
        counts[row["name"]] = counts.get(row["name"], 0) + 1

    return RingHoma(
        atom_indices=ring,
        value=1.0 - total / size,
        bond_types=counts,
    )


def _require_geometry(
    mol: Chem.Mol | None,
) -> tuple[GeometricAromaticityRefusal, str] | None:
    """The gate both geometric indices need, or None if the structure passes.

    EXTRACTED RATHER THAN COPIED, because it is the same requirement twice:
    HOMA and Bird both read real bond lengths, and a 2D layout has none. Two
    copies would be two places to fix the day the wording or the check moves.
    """
    if mol is None or mol.GetNumAtoms() == 0:
        return (GeometricAromaticityRefusal.NOT_A_STRUCTURE, "")
    if mol.GetNumConformers() == 0:
        return (
            GeometricAromaticityRefusal.NO_CONFORMER,
            "generate one with Structure > Generate Conformers... first",
        )
    if not mol.GetConformer().Is3D():
        return (
            GeometricAromaticityRefusal.NO_CONFORMER,
            "the available conformer is 2D, and a layout's bond lengths are "
            "not measurements -- every bond in one comes out about the same "
            "length whatever its order",
        )
    return None


def compute_homa(mol: Chem.Mol | None) -> HomaResult:
    """HOMA for every ring in the structure's smallest set of rings."""
    gate = _require_geometry(mol)
    if gate is not None:
        return HomaResult(refusal=gate[0], detail=gate[1])

    rings = mol.GetRingInfo().AtomRings()
    if not rings:
        return HomaResult(refusal=GeometricAromaticityRefusal.NO_RINGS)

    return HomaResult(rings=tuple(ring_homa(mol, ring) for ring in rings))


def refusal_text(refusal: GeometricAromaticityRefusal | None, detail: str = "") -> str:
    if refusal is None:
        return ""
    return refusal.value + (f" -- {detail}" if detail else "")


# ---------------------------------------------------------------------------
# The calculator
# ---------------------------------------------------------------------------


def _ring_label(mol: Chem.Mol, ring: tuple[int, ...]) -> str:
    """Name a ring by its size and composition, not by its atom indices.

    An index list sends a reader counting atoms in a SMILES. `6-membered
    C5N` identifies pyridine's ring on sight, and stays meaningful when the
    atom order changes.
    """
    symbols: dict[str, int] = {}
    for index in ring:
        symbol = mol.GetAtomWithIdx(index).GetSymbol()
        symbols[symbol] = symbols.get(symbol, 0) + 1
    composition = "".join(
        symbol + (str(count) if count > 1 else "")
        for symbol, count in sorted(symbols.items())
    )
    return f"{len(ring)}-membered {composition}"


def compute_aromaticity(
    mol: Chem.Mol | None,
    molecule_uuid: str = "",
    parameters: dict | None = None,
) -> ReportResult:
    """HOMA per ring, or a named refusal.

    The third argument is the registry's PARAMETER DICT, not a value -- see
    `chem/hansen.py`, where writing it as a bare int passed every unit test
    and raised the moment the button was pressed.
    """
    places = max(0, min(6, int((parameters or {}).get("decimal_places", 3))))
    result = compute_homa(mol)

    provenance = Provenance(
        created_by="core",
        method="krygowski_1993_homa",
        parameters={
            "decimal_places": places,
            "parameter_set": "Table I, CCa and the heteroatom rows",
            "rings": len(result.rings) if result.applicable else None,
            "refusal": result.refusal.name if result.refusal else None,
            TOTAL: decline_total(
                "HOMA is defined PER RING. Summing or averaging rings would "
                "erase the local aromatic character the index exists to show -- "
                "the paper's own Figure 3 gives perylene's rings values from "
                "0.448 to 0.952."
            ),
        },
    )

    if not result.applicable:
        return ReportResult(
            report_id="homa_aromaticity",
            name="Aromaticity (HOMA)",
            category="aromaticity",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=refusal_text(result.refusal, result.detail),
            # The CELL form. The detail is a whole sentence -- what to press,
            # or why a layout's bond lengths are not measurements -- and that
            # is exactly the half the cell used to eat.
            error_summary=result.refusal.value if result.refusal else None,
            provenance=provenance,
        )

    facts: list[Fact] = []
    for ring in result.rings:
        label = _ring_label(mol, ring.atom_indices)
        if not ring.applicable:
            facts.append(Fact(
                category=FactCategory.STRUCTURE,
                label=label,
                value=None,
                display_value="not available",
                units="",
                source="homa_aromaticity",
                basis=Basis.DETERMINISTIC,
                highlight=tuple(ring.atom_indices),
                limitations=(refusal_text(ring.refusal, ring.detail),),
            ))
            continue
        mixed = ring.bond_types or {}
        facts.append(Fact(
            category=FactCategory.STRUCTURE,
            label=label,
            value=ring.value,
            display_value=f"{ring.value:.{places}f}",
            units="",
            source="homa_aromaticity",
            # DETERMINISTIC: given the geometry and the table this is
            # arithmetic. What it ESTIMATES is a model quantity, which the
            # limitations say, but the computation itself is not a regression.
            basis=Basis.DETERMINISTIC,
            highlight=tuple(ring.atom_indices),
            evidence=(
                "Bond types used: "
                + ", ".join(f"{n}x {t}" for t, n in sorted(mixed.items()))
                + ".",
            ),
            limitations=(
                "1 is every bond at the optimal length and 0 is the reference "
                "Kekule structure. There is NO lower bound -- a bond-alternating "
                "or strained ring goes negative, which is a result rather than "
                "an error.",
            ),
        ))

    return ReportResult(
        report_id="homa_aromaticity",
        name="Aromaticity (HOMA)",
        category="aromaticity",
        molecule_uuid=molecule_uuid,
        cache_state=CacheState.COMPLETED,
        facts=tuple(facts),
        provenance=provenance,
        limitations=(
            "COMPUTED FROM THIS CONFORMER'S BOND LENGTHS. A different conformer, "
            "or a geometry from a different method, gives a different number -- "
            "the paper's own benzene spans 0.969 to 0.996 across electron "
            "diffraction, microwave and X-ray geometries.",
            "A GEOMETRIC index. It says how equalised the ring's bonds are, not "
            "whether the ring sustains a ring current or is energetically "
            "stabilised. Those are different questions with different answers.",
        ),
    )


# ---------------------------------------------------------------------------
# Bird's aromaticity index
# ---------------------------------------------------------------------------
#
# `[source:bird1985]`.
#
#     N = a/R^2 - b                          the Gordy bond order, per type
#     V = (100/Nbar) * sqrt(SUM (N-Nbar)^2 / n)   coefficient of variation
#     I = 100 * (1 - V/V_K)
#
# A DIFFERENT QUESTION FROM HOMA, ON THE SAME GEOMETRY. HOMA asks how far
# each bond sits from ONE optimal length; Bird converts every bond to a bond
# ORDER and asks how UNIFORM those orders are. So a ring whose bonds are all
# equal but all wrong scores 100 on Bird and poorly on HOMA -- they are not
# interchangeable and their numbers must not be compared.
#
# **AND BIRD'S OWN NUMBERS ARE NOT COMPARABLE ACROSS RING SIZES.** p1411:
# index values "are not necessarily comparable for differing ring systems",
# so "it seems desirable to attach a guiding subscript as I5, I6 or I5,6, to
# discourage inappropriate comparisons." That is a labelling requirement from
# the source, and it matters more here than it would elsewhere because HOMA
# sits in the same panel section and DOES share one scale across ring sizes.


@lru_cache(maxsize=1)
def _bird_parameters() -> dict:
    return json.loads(_BIRD_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _bird_by_elements() -> dict[frozenset[str], dict]:
    out: dict[frozenset[str], dict] = {}
    for name, row in _bird_parameters()["bonds"].items():
        key = frozenset(row["elements"])
        if key in out:
            raise ValueError(f"two Bird parameter sets claim {sorted(key)}")
        out[key] = {"name": name, **row}
    return out


def bond_order(elements: frozenset[str], length: float) -> float | None:
    """Gordy's N = a/R^2 - b, or None for a bond type with no constants."""
    row = _bird_by_elements().get(elements)
    if row is None:
        return None
    return row["a"] / (length * length) - row["b"]


def kekule_reference(ring_size: int) -> float | None:
    """V_K for a ring of this size, or None if the paper gives none.

    The paper states three: 35 for a five-membered ring, 33.3 for a
    six-membered one, and 35 for a fused five-and-six SYSTEM.

    **THE FUSED VALUE IS NOT USED HERE, AND THAT IS DELIBERATE.** I5,6 is an
    index of the whole two-ring system; this walks rings individually, so a
    ring in a fused system is scored by its OWN size and the system-level
    quantity is simply not computed. Reporting a per-ring number under the
    I5,6 label would be a different quantity wearing that name.

    Any other size -- three, four, seven -- has no published reference and is
    refused rather than given one by analogy.
    """
    table = _bird_parameters()["_v_kekule"]
    if ring_size == 5:
        return table["five"]
    if ring_size == 6:
        return table["six"]
    return None


@dataclass(frozen=True)
class RingBird:
    """Bird's index for one ring, or why it could not be given."""

    atom_indices: tuple[int, ...]
    value: float | None = None
    refusal: GeometricAromaticityRefusal | None = None
    detail: str = ""
    #: The coefficient of variation of the ring's bond orders, before it is
    #: put on the 0-100 scale. Reported because it is the quantity the method
    #: actually measures, and because V = 0 is what "fully delocalised" means.
    variation: float | None = None
    bond_types: dict[str, int] | None = None

    @property
    def applicable(self) -> bool:
        return self.refusal is None

    @property
    def subscript(self) -> str:
        """`I5` or `I6` -- the paper's own guard against comparing them."""
        return f"I{len(self.atom_indices)}"


@dataclass(frozen=True)
class BirdResult:
    rings: tuple[RingBird, ...] = ()
    refusal: GeometricAromaticityRefusal | None = None
    detail: str = ""

    @property
    def applicable(self) -> bool:
        return self.refusal is None


def ring_bird(mol: Chem.Mol, ring: tuple[int, ...]) -> RingBird:
    """Bird's index for one ring, given its atom indices in ring order."""
    size = len(ring)
    reference = kekule_reference(size)
    if reference is None:
        return RingBird(
            atom_indices=ring,
            refusal=GeometricAromaticityRefusal.UNSUPPORTED_RING_SIZE,
            detail=f"{size}-membered; the paper gives V_K for 5 and 6 only",
        )

    conformer = mol.GetConformer()
    orders: list[float] = []
    counts: dict[str, int] = {}
    for position in range(size):
        i = ring[position]
        j = ring[(position + 1) % size]
        if mol.GetBondBetweenAtoms(i, j) is None:
            return RingBird(
                atom_indices=ring,
                refusal=GeometricAromaticityRefusal.UNPARAMETRISED_BOND,
                detail=f"atoms {i} and {j} are not bonded",
            )
        pair = frozenset(
            (mol.GetAtomWithIdx(i).GetSymbol(), mol.GetAtomWithIdx(j).GetSymbol())
        )
        order = bond_order(pair, _bond_length(conformer, i, j))
        if order is None:
            return RingBird(
                atom_indices=ring,
                refusal=GeometricAromaticityRefusal.UNPARAMETRISED_BOND,
                detail=f"{'-'.join(sorted(pair))} has no Gordy constants",
            )
        orders.append(order)
        row = _bird_by_elements()[pair]
        counts[row["name"]] = counts.get(row["name"], 0) + 1

    mean = sum(orders) / size
    if mean == 0:
        return RingBird(
            atom_indices=ring,
            refusal=GeometricAromaticityRefusal.UNPARAMETRISED_BOND,
            detail="the mean bond order is zero, so V is undefined",
        )
    spread = math.sqrt(sum((order - mean) ** 2 for order in orders) / size)
    variation = 100.0 * spread / mean
    return RingBird(
        atom_indices=ring,
        value=100.0 * (1.0 - variation / reference),
        variation=variation,
        bond_types=counts,
    )


def compute_bird(mol: Chem.Mol | None) -> BirdResult:
    """Bird's index for every ring the structure carries."""
    gate = _require_geometry(mol)
    if gate is not None:
        return BirdResult(refusal=gate[0], detail=gate[1])
    rings = mol.GetRingInfo().AtomRings()
    if not rings:
        return BirdResult(refusal=GeometricAromaticityRefusal.NO_RINGS)
    return BirdResult(rings=tuple(ring_bird(mol, ring) for ring in rings))


def compute_bird_index(
    mol: Chem.Mol | None,
    molecule_uuid: str = "",
    parameters: dict | None = None,
) -> ReportResult:
    """Bird's index per ring, or a named refusal.

    The third argument is the registry's PARAMETER DICT, not a value -- see
    `chem/hansen.py`, where writing it as a bare int passed every unit test
    and raised the moment the button was pressed.
    """
    places = max(0, min(6, int((parameters or {}).get("decimal_places", 1))))
    result = compute_bird(mol)

    provenance = Provenance(
        created_by="core",
        method="bird_1985_aromaticity_index",
        parameters={
            "decimal_places": places,
            "gordy_constants": "Bird 1985 Table 1",
            "rings": len(result.rings) if result.applicable else None,
            "refusal": result.refusal.name if result.refusal else None,
            TOTAL: decline_total(
                "Bird's own p1411: index values 'are not necessarily comparable "
                "for differing ring systems'. Summing or averaging I5 and I6 is "
                "exactly the comparison the paper attaches a subscript to "
                "discourage."
            ),
        },
    )

    if not result.applicable:
        return ReportResult(
            report_id="bird_aromaticity",
            name="Aromaticity (Bird)",
            category="aromaticity",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=refusal_text(result.refusal, result.detail),
            error_summary=result.refusal.value if result.refusal else None,
            provenance=provenance,
        )

    facts: list[Fact] = []
    for ring in result.rings:
        # THE SUBSCRIPT IS IN THE LABEL, and that is the paper's requirement
        # rather than a formatting choice: "it seems desirable to attach a
        # guiding subscript as I5, I6 or I5,6, to discourage inappropriate
        # comparisons" (p1411). HOMA sits in this same section and DOES share
        # one scale across ring sizes, so an unlabelled Bird number here would
        # invite precisely the comparison Bird warns against.
        label = f"{ring.subscript} - {_ring_label(mol, ring.atom_indices)}"
        if not ring.applicable:
            facts.append(Fact(
                category=FactCategory.STRUCTURE,
                label=_ring_label(mol, ring.atom_indices),
                value=None,
                display_value="not available",
                units="",
                source="bird_aromaticity",
                basis=Basis.DETERMINISTIC,
                highlight=tuple(ring.atom_indices),
                limitations=(refusal_text(ring.refusal, ring.detail),),
            ))
            continue
        facts.append(Fact(
            category=FactCategory.STRUCTURE,
            label=label,
            value=ring.value,
            display_value=f"{ring.value:.{places}f}",
            units="",
            source="bird_aromaticity",
            basis=Basis.DETERMINISTIC,
            highlight=tuple(ring.atom_indices),
            evidence=(
                "Bond orders from Gordy's N = a/R^2 - b: "
                + ", ".join(f"{n}x {t}" for t, n in sorted((ring.bond_types or {}).items()))
                + f". Coefficient of variation V = {ring.variation:.2f}.",
            ),
            limitations=(
                f"{ring.subscript} IS NOT COMPARABLE WITH AN INDEX FOR A "
                "DIFFERENT RING SIZE. The paper attaches the subscript for "
                "exactly that reason, because the Kekule reference V_K differs "
                "-- 35 for a five-membered ring and 33.3 for a six-membered one.",
                "Bird's own stated sensitivity is +-2 to 3 index units from "
                "substituent effects.",
            ),
        ))

    return ReportResult(
        report_id="bird_aromaticity",
        name="Aromaticity (Bird)",
        category="aromaticity",
        molecule_uuid=molecule_uuid,
        cache_state=CacheState.COMPLETED,
        facts=tuple(facts),
        provenance=provenance,
        limitations=(
            "A DIFFERENT QUESTION FROM HOMA ON THE SAME GEOMETRY. HOMA measures "
            "how far each bond sits from one optimal length; Bird converts every "
            "bond to a bond ORDER and measures how UNIFORM those orders are. A "
            "ring whose bonds are all equal but all wrong scores 100 here and "
            "poorly on HOMA. The two numbers are not interchangeable.",
            "COMPUTED FROM THIS CONFORMER'S BOND LENGTHS. Bird's own indices "
            "come from experimental geometries, and a force field's are not "
            "those -- see the source entry for what this implementation is and "
            "is not validated against.",
        ),
    )
