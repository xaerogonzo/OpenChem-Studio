from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from openchem.domain.affinity_range import AffinityRange
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
class DockingReplicate:
    """One search of a replicate set: the seed it ran under, and the best
    affinity it found.

    `best_affinity_kcal_mol` is None when this replicate produced no affinity,
    and `error` says why. The row is KEPT rather than dropped, so a set never
    looks like a clean 4 when 5 runs were attempted -- the same shape as
    `ScreeningEntry`, which keeps a failed ligand's row for the same reason.

    THE SHIPPED SERVICE NEVER PUBLISHES A SET WITH A CRASHED REPLICATE IN IT,
    and this docstring said the opposite before the service existed to check it
    against. `DockingService` fails the WHOLE run when `provider.dock()`
    raises, because a spread over "the 3 of 5 that worked" is a spread over a
    selected subset and the selection is not random -- a replicate that crashed
    may well be one whose search went somewhere unusual. What does reach this
    field is the milder case the provider reports as success: a run that
    returned no poses at all. The field stays general because the TYPE is not
    the place to encode one producer's failure policy.

    `seed` is None when the provider does not accept `search_options` at all --
    it then runs on its own defaults and the seed we derived was never sent, so
    recording it would name a setting the run did not use.
    """

    seed: int | None
    best_affinity_kcal_mol: float | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "best_affinity_kcal_mol": self.best_affinity_kcal_mol,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DockingReplicate:
        return cls(
            seed=data.get("seed"),
            best_affinity_kcal_mol=data.get("best_affinity_kcal_mol"),
            error=data.get("error"),
        )


@dataclass(slots=True)
class DockingReplicateSet:
    """Every run of one docking request, and which of them the stored poses
    came from.

    TWO SEED CONCEPTS, NAMED SEPARATELY, because one field cannot be both:

        protocol_seed 4712              what the user pinned
          └─ derived per (protocol_seed, ligand_uuid)
               ├─ replicates[0].seed  881423     the actual Vina seeds
               ├─ replicates[1].seed  1990277
               └─ replicates[2].seed  47122019
        representative_index 1          so DockingResultModel.seed == 1990277

    `protocol_seed` is None when the user pinned nothing -- the provider then
    chooses each seed itself and every one is still recorded, so the run is
    reproducible after the fact. Fabricating a root the user never chose would
    make an unpinned run look pinned.

    DERIVED PER LIGAND, which is a statistical requirement rather than a
    convenience: the separation rule in `domain/affinity_range.py` is an exact
    rank-sum calculation and needs the two ligands' replicate sets to be
    independent. Sharing one seed set across two ligands would make the values
    arrive as correlated pairs and void it.
    """

    protocol_seed: int | None
    representative_index: int
    replicates: list[DockingReplicate] = field(default_factory=list)

    @property
    def successes(self) -> list[DockingReplicate]:
        return [r for r in self.replicates if r.best_affinity_kcal_mol is not None]

    def affinity_range(self) -> AffinityRange | None:
        """The spread over the runs that SUCCEEDED, or None if none did.

        None rather than an empty range, for the reason `AffinityRange` refuses
        to be constructed empty: "every replicate failed" and "not measured"
        must stay distinguishable.
        """
        values = tuple(
            r.best_affinity_kcal_mol
            for r in self.replicates
            if r.best_affinity_kcal_mol is not None
        )
        return AffinityRange(values) if values else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_seed": self.protocol_seed,
            "representative_index": self.representative_index,
            "replicates": [r.to_dict() for r in self.replicates],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DockingReplicateSet:
        return cls(
            protocol_seed=data.get("protocol_seed"),
            representative_index=int(data.get("representative_index", 0)),
            replicates=[DockingReplicate.from_dict(r) for r in data.get("replicates", [])],
        )


def median_replicate_index(replicates: Sequence[DockingReplicate]) -> int:
    """Which replicate's poses represent the set: the MEDIAN by best affinity.

    NOT THE BEST-SCORING ONE, which was this design's first answer and is
    disqualified rather than merely second choice. Best-of-N is a MAX
    SELECTION, so the headline affinity would drift more negative purely as the
    replicate count rose -- the reported number becoming a function of how many
    times it was run, which is the exact harm replicates exist to expose,
    reintroduced in the first number a reader sees.

    `sorted(values)[n // 2]`, which for even n takes the LESS NEGATIVE of the
    two middle values: the conservative side for a Vina score, and one rule for
    both parities rather than a special case. Ties break on the smaller
    replicate index, so the answer is deterministic.

    It also makes the pose table's row 1 equal BY CONSTRUCTION to the reported
    centre, so the panel never prints two different numbers for one quantity.

    A replicate with no affinity is not a candidate. With none at all the
    answer is 0 -- some replicate has to hold the poses, and index 0 is the
    only choice that does not assert an ordering over an empty set.
    """
    scored = sorted(
        (replicate.best_affinity_kcal_mol, index)
        for index, replicate in enumerate(replicates)
        if replicate.best_affinity_kcal_mol is not None
    )
    if not scored:
        return 0
    return scored[len(scored) // 2][1]


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
    #: Every run behind this result, or None when the count was never
    #: recorded -- which is every result saved before replicates existed.
    #:
    #: NONE IS A THIRD STATE AND NOT A SYNONYM FOR ONE RUN. See `from_dict`.
    replicates: DockingReplicateSet | None = None
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
            # EMITTED EXPLICITLY AS null WHEN ABSENT, so that re-saving a
            # project written before replicates existed does not quietly give
            # its results a replicate count on the way through.
            "replicates": self.replicates.to_dict() if self.replicates else None,
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
            # AN OLD PROJECT FILE GETS None, NEVER A SYNTHESISED ONE-RUN SET.
            #
            # The tempting alternative is to manufacture
            # `[DockingReplicate(seed=data["seed"], best=min(poses))]`, and it
            # is wrong three ways. It would make this application the author of
            # a count nobody measured -- while the whole point of showing the
            # count is that n=1 and n=30 say different things. It would make a
            # synthesised single run byte-indistinguishable from a deliberate
            # one, so "why does this old result show no spread" becomes
            # unanswerable. And computing the best affinity here would be a
            # SECOND implementation of it, beside the provider's and the
            # screening service's -- the drift class `is_stripped_residue` and
            # `filter_altlocs` each exist to close.
            replicates=(
                DockingReplicateSet.from_dict(data["replicates"])
                if data.get("replicates")
                else None
            ),
            timestamp=data.get("timestamp", 0.0),
        )
