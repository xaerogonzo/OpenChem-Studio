from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from openchem.domain.crystal import CrystalModel
from openchem.domain.docking import DockingResultModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel

SCHEMA_VERSION = 1
APPLICATION_VERSION = "0.1.0"

# TypeVar rather than a shared `ChemicalEntity` base class: MoleculeModel,
# MacromoleculeModel and DockingResultModel share exactly three fields
# (uuid, display_name, metadata) and are deliberately routed through
# different code paths everywhere -- small molecules to RDKit/3Dmol.js,
# macromolecules to Mol* (see MacromoleculeModel's own docstring). Nothing
# consumes them polymorphically, so the only real duplication was these
# three identical uuid searches, and structural typing removes it without
# inheritance or a slots=True reparenting exercise.
_HasUuid = TypeVar("_HasUuid")


def _find_by_uuid(items: Sequence[_HasUuid], target_uuid: str) -> _HasUuid | None:
    for item in items:
        if item.uuid == target_uuid:
            return item
    return None


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
    # A crystal is NOT a molecule and gets its own list rather than being
    # squeezed into one of the two above -- see `domain/crystal.py` for
    # why there is no inheritance in either direction. Putting one in
    # `molecules` would hand it to every molecular calculator that
    # iterates that list, which is exactly what `chem/crystal_report.py`
    # exists to refuse.
    crystals: list[CrystalModel] = field(default_factory=list)
    docking_results: list[DockingResultModel] = field(default_factory=list)
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
        return _find_by_uuid(self.molecules, molecule_uuid)

    def find_macromolecule(self, macromolecule_uuid: str) -> MacromoleculeModel | None:
        return _find_by_uuid(self.macromolecules, macromolecule_uuid)

    def find_crystal(self, crystal_uuid: str) -> CrystalModel | None:
        return _find_by_uuid(self.crystals, crystal_uuid)

    def find_docking_result(self, docking_result_uuid: str) -> DockingResultModel | None:
        return _find_by_uuid(self.docking_results, docking_result_uuid)

    def unique_molecule_name(self, base: str) -> str:
        """`base`, or `base` with the lowest free number appended.

        Every new molecule used to be called "New molecule", so a project
        routinely held several with identical labels. That is not just
        untidy: the panels that pick a molecule from a dropdown show only
        the name, so an operation running on the wrong one looked
        completely normal. It cost a real debugging session -- ORCA
        appeared to refuse a molecule that plainly had conformers, because
        the Quantum Chemistry panel was pointing at the OTHER "New
        molecule".

        Duplicate names are still allowed; a user can rename two molecules
        to the same thing and that is their business. This only stops the
        application from generating collisions on its own.
        """
        taken = {m.display_name for m in self.molecules}
        if base not in taken:
            return base
        # Starts at 2 so the pair reads "New molecule" / "New molecule 2"
        # rather than renaming the one that already exists.
        suffix = 2
        while f"{base} {suffix}" in taken:
            suffix += 1
        return f"{base} {suffix}"

    def record_history(self, action: str) -> None:
        self.history.append(HistoryEntry(timestamp=time.time(), action=action))
        self.modified_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "molecules": [m.to_dict() for m in self.molecules],
            "macromolecules": [m.to_dict() for m in self.macromolecules],
            "crystals": [c.to_dict() for c in self.crystals],
            "docking_results": [d.to_dict() for d in self.docking_results],
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
            # `.get` with a default, like every sibling: a project saved
            # before crystals existed loads with an empty list rather
            # than a KeyError, so no schema bump is needed.
            crystals=[CrystalModel.from_dict(c) for c in data.get("crystals", [])],
            docking_results=[
                DockingResultModel.from_dict(d) for d in data.get("docking_results", [])
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
