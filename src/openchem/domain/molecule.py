from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.conformer import ConformerModel


@dataclass(slots=True)
class MoleculeModel:
    """Pure data representation of a molecule.

    No RDKit or Qt dependency — this is what flows through services, commands,
    events, and project files. RDKit `Mol` objects are reconstructed on demand
    by `openchem.chem.engine.ChemistryEngine`, never stored here.
    """

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str = "Untitled molecule"
    molblock: str | None = None
    canonical_smiles: str | None = None
    inchi: str | None = None
    inchikey: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    notes: str = ""
    conformers: list[ConformerModel] = field(default_factory=list)
    #: Canonical SMILES, as drawn, of the component of a multi-piece drawing the person chose to
    #: compute on. Empty is the automatic pick (`chem/components.py`). Keyed by the component's
    #: structure and not its position, so redrawing the pieces in another order keeps the choice.
    component_choice: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "molblock": self.molblock,
            "canonical_smiles": self.canonical_smiles,
            "inchi": self.inchi,
            "inchikey": self.inchikey,
            "metadata": self.metadata,
            "tags": list(self.tags),
            "favorite": self.favorite,
            "notes": self.notes,
            "conformers": [c.to_dict() for c in self.conformers],
        }
        # Written only when set, so a project nobody chose a component in is byte-for-byte what it was.
        if self.component_choice:
            data["component_choice"] = self.component_choice
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MoleculeModel:
        return cls(
            uuid=data["uuid"],
            display_name=data.get("display_name", "Untitled molecule"),
            molblock=data.get("molblock"),
            canonical_smiles=data.get("canonical_smiles"),
            inchi=data.get("inchi"),
            inchikey=data.get("inchikey"),
            metadata=dict(data.get("metadata", {})),
            tags=list(data.get("tags", [])),
            favorite=data.get("favorite", False),
            notes=data.get("notes", ""),
            conformers=[ConformerModel.from_dict(c) for c in data.get("conformers", [])],
            component_choice=str(data.get("component_choice") or ""),
        )
