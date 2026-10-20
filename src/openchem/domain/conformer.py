from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.common import RUN_METHOD_BASIS, Provenance

#: `ConformerModel.method` of a geometry that a quantum-chemistry optimization produced (ORCA's final
#: Cartesian block). It has no force-field energy, and it is the geometry a person means by "the
#: optimized one": `chem.calculation_input.canonical_conformer` prefers it to every force-field conformer.
ORCA_OPTIMIZED = "orca_opt"

#: The same, from Psi4 (`chem/psi4_engine.py`): the final geometry of an `optimize()` job. Never relabelled as ORCA's,
#: because a geometry says which program and level made it.
PSI4_OPTIMIZED = "psi4_opt"

#: Every `method` that marks a quantum-optimized geometry. A set because a second engine adds its own
#: label here and nothing else changes: the canonical-conformer rule, the keep-on-regenerate rule and the scores'
#: geometry rule all read this set.
QUANTUM_OPTIMIZED_METHODS = frozenset({ORCA_OPTIMIZED, PSI4_OPTIMIZED})

#: How a person names the engine behind each quantum-optimized `method`, for labels ("4 - Psi4 optimized (...)").
QUANTUM_ENGINE_NAMES = {ORCA_OPTIMIZED: "ORCA", PSI4_OPTIMIZED: "Psi4"}

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


def quantum_engine_name(conformer: ConformerModel) -> str:
    """The engine behind a quantum-optimized conformer ("ORCA", "Psi4"), or "quantum" for a method this build does not name."""
    return QUANTUM_ENGINE_NAMES.get(conformer.method, "quantum")


def quantum_engine_of(conformers: Sequence[ConformerModel]) -> str:
    """The one engine every quantum-optimized conformer here came from, "quantum" when two engines made them, and "" when there are none."""
    engines = {quantum_engine_name(c) for c in conformers if is_quantum_optimized(c)}
    if not engines:
        return ""
    return engines.pop() if len(engines) == 1 else "quantum"


def quantum_level_of_theory(conformer: ConformerModel) -> str:
    """The level of theory a quantum-optimized conformer was run at, as submitted ("B3LYP def2-SVP"), or "".

    Empty means NOT RECORDED, never "the default": a conformer from a project saved before the run's method
    was written into its provenance has none, and a reader must be able to say so.
    """
    provenance = conformer.provenance
    if provenance is None:
        return ""
    return str(provenance.parameters.get(RUN_METHOD_BASIS, "") or "")


def conformer_choice_text(conformers: Sequence[ConformerModel], index: int) -> str:
    """How one conformer reads where somebody CHOOSES between them: `4 - ORCA optimized (HF STO-3G)`.

    The number is the one-based slot the 3D viewer shows, so "conformer 4" means the same thing in both
    places. A force-field conformer says how far above the lowest it is (`2 - +0.55 kcal/mol`, `1 - lowest
    energy`), as the viewer's status line does; an ORCA geometry says so and says at what level of theory,
    because it has no energy on the force-field scale to put beside the others.
    """
    conformer = conformers[index]
    position = index + 1
    if is_quantum_optimized(conformer):
        level = quantum_level_of_theory(conformer)
        engine = quantum_engine_name(conformer)
        return f"{position} - {engine} optimized ({level})" if level else f"{position} - {engine} optimized"
    energies = [c.energy for c in conformers if c.energy is not None]
    if conformer.energy is None or not energies:
        return f"{position} - no energy"
    relative = conformer.energy - min(energies)
    if relative < 0.005:
        return f"{position} - lowest energy"
    return f"{position} - +{relative:.2f} kcal/mol"


def quantum_optimized_note(conformers: Sequence[ConformerModel]) -> str:
    """The badge a molecule wears when it holds ORCA-optimized geometry, or "" when it holds none.

    `ORCA-optimized geometry (HF STO-3G)` for one, `2 ORCA-optimized conformers (newest: HF STO-3G)` for
    several: the NEWEST is the one every later calculation uses (`chem.calculation_input.canonical_conformer`),
    so it is the level of theory worth naming. An unrecorded level is left out rather than guessed.
    """
    optimized = [c for c in conformers if is_quantum_optimized(c)]
    if not optimized:
        return ""
    newest = max(optimized, key=lambda c: c.timestamp)
    level = quantum_level_of_theory(newest)
    # One engine's name when every geometry is from it; "quantum" when two engines made them, rather than
    # naming the newest's engine for all of them.
    engine = quantum_engine_of(optimized)
    if len(optimized) == 1:
        return f"{engine}-optimized geometry ({level})" if level else f"{engine}-optimized geometry"
    suffix = f" (newest: {level})" if level else ""
    return f"{len(optimized)} {engine}-optimized conformers{suffix}"

