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
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from rdkit import Chem

from openchem.domain.common import TOTAL, CacheState, Provenance, decline_total
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

_PARAMETERS_PATH = Path(__file__).parent / "data" / "homa_parameters.json"


class HomaRefusal(Enum):
    """Why HOMA cannot be given for this structure or ring.

    A VALUE rather than a message, the shape `JobackRefusal`, `HansenRefusal`
    and `IsotopeRefusal` already use.
    """

    NOT_A_STRUCTURE = "the structure could not be read"
    NO_CONFORMER = "this needs a real 3D conformer"
    NO_RINGS = "the structure has no rings"
    UNPARAMETRISED_BOND = "a ring bond has no HOMA parameters"


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
    refusal: HomaRefusal | None = None
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
    refusal: HomaRefusal | None = None
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
                refusal=HomaRefusal.UNPARAMETRISED_BOND,
                detail=f"atoms {i} and {j} are not bonded",
            )
        pair = frozenset(
            (mol.GetAtomWithIdx(i).GetSymbol(), mol.GetAtomWithIdx(j).GetSymbol())
        )
        row = table.get(pair)
        if row is None:
            return RingHoma(
                atom_indices=ring,
                refusal=HomaRefusal.UNPARAMETRISED_BOND,
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


def compute_homa(mol: Chem.Mol | None) -> HomaResult:
    """HOMA for every ring in the structure's smallest set of rings."""
    if mol is None or mol.GetNumAtoms() == 0:
        return HomaResult(refusal=HomaRefusal.NOT_A_STRUCTURE)
    if mol.GetNumConformers() == 0:
        return HomaResult(
            refusal=HomaRefusal.NO_CONFORMER,
            detail="generate one with Structure > Generate Conformers... first",
        )
    if not mol.GetConformer().Is3D():
        return HomaResult(
            refusal=HomaRefusal.NO_CONFORMER,
            detail=(
                "the available conformer is 2D, and a layout's bond lengths are "
                "not measurements -- every bond in one comes out about the same "
                "length whatever its order"
            ),
        )

    rings = mol.GetRingInfo().AtomRings()
    if not rings:
        return HomaResult(refusal=HomaRefusal.NO_RINGS)

    return HomaResult(rings=tuple(ring_homa(mol, ring) for ring in rings))


def refusal_text(refusal: HomaRefusal | None, detail: str = "") -> str:
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
