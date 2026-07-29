from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MacromoleculeModel:
    """Pure data representation of a macromolecular/crystallographic
    structure (a protein, a PDB/CIF deposit) — deliberately NOT RDKit-
    Mol-backed like `MoleculeModel`: full proteins don't fit V2000 molblock
    assumptions well, and aren't edited or conformer-generated the way
    small molecules are. Rendered via the Mol*-based `ViewerBackend`
    sibling implementation, not the 3Dmol.js one.

    `structure_text`/`source_format` are split (rather than assuming raw
    PDB text forever) so BinaryCIF/MMTF support can be added later without
    another schema change — V1 only ever writes `source_format == "pdb"`.
    `source_format` values match Mol*'s own vocabulary directly (`"pdb"` or
    `"mmcif"` — confirmed against the installed `molstar` package's
    `BuiltInTrajectoryFormats`), not a separate naming scheme, so
    `ViewerBackend.load_macromolecule` never needs a translation layer.
    `metadata` is the intended home for lightweight structural
    info (resolution, experimental method, title, chain list) as
    unstructured key-value for V1; full structured chain/residue/assembly
    parsing is a later phase, not built here.
    """

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str = "Untitled macromolecule"
    structure_text: str = ""
    source_format: str = "pdb"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "structure_text": self.structure_text,
            "source_format": self.source_format,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MacromoleculeModel:
        return cls(
            uuid=data["uuid"],
            display_name=data.get("display_name", "Untitled macromolecule"),
            structure_text=data.get("structure_text", ""),
            source_format=data.get("source_format", "pdb"),
            metadata=dict(data.get("metadata", {})),
        )
