from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "conformer_id": self.conformer_id,
            "molblock": self.molblock,
            "energy": self.energy,
            "method": self.method,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConformerModel:
        return cls(
            conformer_id=data["conformer_id"],
            molblock=data.get("molblock", ""),
            energy=data.get("energy"),
            method=data.get("method", ""),
            timestamp=data.get("timestamp", time.time()),
        )
