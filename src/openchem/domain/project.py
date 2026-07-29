from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel

SCHEMA_VERSION = 1
APPLICATION_VERSION = "0.1.0"


@dataclass(slots=True)
class HistoryEntry:
    timestamp: float
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, "action": self.action}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(timestamp=data["timestamp"], action=data["action"])


@dataclass(slots=True)
class ProjectModel:
    """A project is a document: molecules plus notes, tags, folders, and history.

    Carries its own version fields (project/application/schema) from the
    start so a future on-disk format change is a migration in
    `ProjectService`, not a breaking change.
    """

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled project"
    molecules: list[MoleculeModel] = field(default_factory=list)
    macromolecules: list[MacromoleculeModel] = field(default_factory=list)
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    folders: list[str] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    project_version: int = 1
    application_version: str = APPLICATION_VERSION
    schema_version: int = SCHEMA_VERSION

    def find_molecule(self, molecule_uuid: str) -> MoleculeModel | None:
        for molecule in self.molecules:
            if molecule.uuid == molecule_uuid:
                return molecule
        return None

    def find_macromolecule(self, macromolecule_uuid: str) -> MacromoleculeModel | None:
        for macromolecule in self.macromolecules:
            if macromolecule.uuid == macromolecule_uuid:
                return macromolecule
        return None

    def record_history(self, action: str) -> None:
        self.history.append(HistoryEntry(timestamp=time.time(), action=action))
        self.modified_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "molecules": [m.to_dict() for m in self.molecules],
            "macromolecules": [m.to_dict() for m in self.macromolecules],
            "notes": self.notes,
            "tags": list(self.tags),
            "folders": list(self.folders),
            "history": [h.to_dict() for h in self.history],
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "project_version": self.project_version,
            "application_version": self.application_version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectModel:
        return cls(
            uuid=data["uuid"],
            name=data.get("name", "Untitled project"),
            molecules=[MoleculeModel.from_dict(m) for m in data.get("molecules", [])],
            macromolecules=[
                MacromoleculeModel.from_dict(m) for m in data.get("macromolecules", [])
            ],
            notes=data.get("notes", ""),
            tags=list(data.get("tags", [])),
            folders=list(data.get("folders", [])),
            history=[HistoryEntry.from_dict(h) for h in data.get("history", [])],
            created_at=data.get("created_at", time.time()),
            modified_at=data.get("modified_at", time.time()),
            project_version=data.get("project_version", 1),
            application_version=data.get("application_version", APPLICATION_VERSION),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
        )
