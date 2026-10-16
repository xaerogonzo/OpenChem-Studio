from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.common import RUN_METHOD_BASIS, Provenance

#: `ConformerModel.method` of a geometry that a quantum-chemistry optimization produced (ORCA's final
#: Cartesian block). It has no force-field energy, and it is the geometry a person means by "the
#: optimized one": `chem.calculation_input.canonical_conformer` prefers it to every force-field conformer.
ORCA_OPTIMIZED = "orca_opt"

#: Every `method` that marks a quantum-optimized geometry. A set because a second engine would add its own
#: label here and nothing else would change.
QUANTUM_OPTIMIZED_METHODS = frozenset({ORCA_OPTIMIZED})

#: Provenance parameter naming the `conformer_id` of the conformer a quantum optimization started from. The id
#: is the identity; the slot below is for a reader who counts conformers 1..N.
OPTIMIZED_FROM_ID = "optimized_from_conformer_id"
#: Provenance parameter: the ONE-BASED slot of the source conformer AS IT STOOD WHEN RUN WAS PRESSED. It describes
#: the input the calculation actually used and does not follow the geometry around: a regeneration that keeps ORCA
#: conformers can move the replacement while the viewer says "4/20", and it was still optimized from "number 7".
#: Where the geometry is NOW is read off the conformer list. Absent = not recorded.
OPTIMIZED_FROM_SLOT = "optimized_from_slot"


@dataclass(slots=True)
class ConformerModel:
    """A single 3D conformer of a molecule.

    Pure data, no RDKit — the molblock carries the 3D coordinates and is
    reconstructed into an RDKit Mol on demand via ChemistryEngine, same
    philosophy as MoleculeModel itself.
    """

    conformer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    molblock: str = ""
    energy: float | None = None
    method: str = ""
    timestamp: float = field(default_factory=time.time)
    # `method`/`.timestamp` above predate `Provenance` (Phase 3 vs Phase 6+)
    # and are left as they are -- this is an additive retrofit for "what
    # produced this, with what parameters" (num_conformers, optimize, ...),
    # which they don't carry. `None` for anything constructed before this
    # field existed (round-tripped from an older saved project).
    provenance: Provenance | None = None
    #: For each conformer atom, the drawing atom it was made from, or -1 for
    #: an atom the drawing does not have (a hydrogen added for the geometry).
    #: `None` means NOT RECORDED -- an older project, or a plugin provider that
    #: dropped the atom tags -- never "the order is the same".
    #:
    #: **ONLY TRUE AGAINST `drawing_fingerprint`.** Conformers deliberately
    #: survive edits that keep canonical SMILES (`EditStructureCommand`), and
    #: an erase-and-redraw is one of them: the drawing's atom order moves and
    #: this map does not. Measured 2026-09-15 in the running app, ethanol's
    #: oxygen showed carbon's 3D charge. `chem.atom_identity` trusts the map
    #: only while the drawing is byte-identical to the one it was made from.
    drawing_atom_ids: list[int] | None = None
    drawing_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "conformer_id": self.conformer_id,
            "molblock": self.molblock,
            "energy": self.energy,
            "method": self.method,
            "timestamp": self.timestamp,
            "provenance": self.provenance.to_dict() if self.provenance is not None else None,
            "drawing_atom_ids": list(self.drawing_atom_ids) if self.drawing_atom_ids is not None else None,
            "drawing_fingerprint": self.drawing_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConformerModel:
        provenance_data = data.get("provenance")
        ids = data.get("drawing_atom_ids")
        return cls(
            conformer_id=data["conformer_id"],
            molblock=data.get("molblock", ""),
            energy=data.get("energy"),
            method=data.get("method", ""),
            timestamp=data.get("timestamp", time.time()),
            provenance=Provenance.from_dict(provenance_data) if provenance_data else None,
            drawing_atom_ids=[int(i) for i in ids] if ids is not None else None,
            drawing_fingerprint=data.get("drawing_fingerprint"),
        )


def is_quantum_optimized(conformer: ConformerModel) -> bool:
    """Did a quantum-chemistry optimization produce this geometry (see `QUANTUM_OPTIMIZED_METHODS`)?"""
    return conformer.method in QUANTUM_OPTIMIZED_METHODS


def quantum_level_of_theory(conformer: ConformerModel) -> str:
    """The level of theory a quantum-optimized conformer was run at, as submitted ("B3LYP def2-SVP"), or "".

    Empty means NOT RECORDED, never "the default": a conformer from a project saved before the run's method
    was written into its provenance has none, and a reader must be able to say so.
    """
    provenance = conformer.provenance
    if provenance is None:
        return ""
    return str(provenance.parameters.get(RUN_METHOD_BASIS, "") or "")

