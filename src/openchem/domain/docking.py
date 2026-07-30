from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.common import Provenance


@dataclass(slots=True)
class DockingBox:
    """The search region for docking — a box center + size, both in
    Angstroms, matching AutoDock Vina's own `center_x/y/z`/`size_x/y/z`
    parameters directly (see `chem/vina_engine.py`)."""

    center: tuple[float, float, float]
    size: tuple[float, float, float]

    def to_dict(self) -> dict[str, Any]:
        return {"center": list(self.center), "size": list(self.size)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DockingBox:
        center = data["center"]
        size = data["size"]
        return cls(center=(center[0], center[1], center[2]), size=(size[0], size[1], size[2]))


@dataclass(slots=True)
class DockingPoseModel:
    """One docked pose. `metadata` is an open escape hatch for future
    per-pose interaction data (H-bonds, clashes, pharmacophore contacts)
    that Vina/Open Babel don't produce natively today — not computed here,
    just given a home so it doesn't need another schema change later.
    """

    pose_molblock: str
    binding_affinity_kcal_mol: float
    rmsd_lb: float
    rmsd_ub: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose_molblock": self.pose_molblock,
            "binding_affinity_kcal_mol": self.binding_affinity_kcal_mol,
            "rmsd_lb": self.rmsd_lb,
            "rmsd_ub": self.rmsd_ub,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DockingPoseModel:
        return cls(
            pose_molblock=data["pose_molblock"],
            binding_affinity_kcal_mol=data["binding_affinity_kcal_mol"],
            rmsd_lb=data["rmsd_lb"],
            rmsd_ub=data["rmsd_ub"],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class DockingResultModel:
    """A (ligand, receptor) docking run's poses plus everything needed to
    actually reproduce it — not just the poses themselves. A `MoleculeModel`
    field would lose the receptor linkage (a pose is inherently a pair),
    so this lives on `ProjectModel.docking_results` instead.
    """

    ligand_molecule_uuid: str
    receptor_macromolecule_uuid: str
    box: DockingBox
    poses: list[DockingPoseModel]
    provenance: Provenance
    engine: str  # e.g. "vina-python", "vina-executable" -- which VinaEngine ran
    engine_version: str
    scoring_function: str
    exhaustiveness: int
    seed: int | None
    receptor_prep_params: dict[str, Any] = field(default_factory=dict)
    ligand_prep_params: dict[str, Any] = field(default_factory=dict)
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "ligand_molecule_uuid": self.ligand_molecule_uuid,
            "receptor_macromolecule_uuid": self.receptor_macromolecule_uuid,
            "box": self.box.to_dict(),
            "poses": [p.to_dict() for p in self.poses],
            "provenance": self.provenance.to_dict(),
            "engine": self.engine,
            "engine_version": self.engine_version,
            "scoring_function": self.scoring_function,
            "exhaustiveness": self.exhaustiveness,
            "seed": self.seed,
            "receptor_prep_params": self.receptor_prep_params,
            "ligand_prep_params": self.ligand_prep_params,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DockingResultModel:
        return cls(
            uuid=data.get("uuid", str(uuid.uuid4())),
            ligand_molecule_uuid=data["ligand_molecule_uuid"],
            receptor_macromolecule_uuid=data["receptor_macromolecule_uuid"],
            box=DockingBox.from_dict(data["box"]),
            poses=[DockingPoseModel.from_dict(p) for p in data.get("poses", [])],
            provenance=Provenance.from_dict(data["provenance"]),
            engine=data["engine"],
            engine_version=data.get("engine_version", "unknown"),
            scoring_function=data.get("scoring_function", "vina"),
            exhaustiveness=data.get("exhaustiveness", 8),
            seed=data.get("seed"),
            receptor_prep_params=dict(data.get("receptor_prep_params", {})),
            ligand_prep_params=dict(data.get("ligand_prep_params", {})),
            timestamp=data.get("timestamp", 0.0),
        )
