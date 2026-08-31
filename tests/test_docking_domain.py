from __future__ import annotations

from pathlib import Path

from openchem.domain.common import Provenance
from openchem.domain.docking import (
    DockingBox,
    DockingPoseModel,
    DockingReplicate,
    DockingReplicateSet,
    DockingResultModel,
)
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.services.project_service import ProjectService


def _make_result() -> DockingResultModel:
    return DockingResultModel(
        ligand_molecule_uuid="lig-1",
        receptor_macromolecule_uuid="rec-1",
        box=DockingBox(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0)),
        poses=[
            DockingPoseModel(
                pose_molblock="mock molblock",
                binding_affinity_kcal_mol=-6.5,
                rmsd_lb=0.0,
                rmsd_ub=0.0,
                metadata={"note": "best pose"},
            )
        ],
        provenance=Provenance(created_by="core", method="vina", parameters={"num_poses": 9}),
        engine="vina-python",
        engine_version="1.2.7",
        scoring_function="vina",
        exhaustiveness=8,
        seed=42,
        receptor_prep_params={"addh": True},
        ligand_prep_params={"addh": True},
    )


def test_docking_result_to_dict_from_dict_roundtrip():
    result = _make_result()
    restored = DockingResultModel.from_dict(result.to_dict())

    assert restored.uuid == result.uuid
    assert restored.ligand_molecule_uuid == "lig-1"
    assert restored.receptor_macromolecule_uuid == "rec-1"
    assert restored.box.center == (1.0, 2.0, 3.0)
    assert restored.box.size == (20.0, 20.0, 20.0)
    assert len(restored.poses) == 1
    assert restored.poses[0].binding_affinity_kcal_mol == -6.5
    assert restored.poses[0].metadata == {"note": "best pose"}
    assert restored.provenance.method == "vina"
    assert restored.engine == "vina-python"
    assert restored.seed == 42
    assert restored.receptor_prep_params == {"addh": True}


def test_project_find_docking_result():
    project = ProjectModel()
    result = _make_result()
    project.docking_results.append(result)

    assert project.find_docking_result(result.uuid) is result
    assert project.find_docking_result("nope") is None


def test_docking_results_survive_project_roundtrip(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="Docking project")
    result = _make_result()
    project.docking_results.append(result)

    path = tmp_path / "test.ocsproj"
    service.save(project, path)
    loaded = service.load(path)

    assert len(loaded.docking_results) == 1
    assert loaded.docking_results[0].uuid == result.uuid
    assert loaded.docking_results[0].poses[0].binding_affinity_kcal_mol == -6.5


def test_old_project_file_without_docking_results_key_loads_fine(tmp_path: Path, qapp):
    service = ProjectService(EventBus())
    project = ProjectModel(name="Old project")
    path = tmp_path / "old.ocsproj"
    service.save(project, path)

    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    del data["docking_results"]
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = service.load(path)
    assert loaded.docking_results == []


# --- replicate sets -----------------------------------------------------------


def test_an_old_project_file_has_no_replicate_record_rather_than_an_invented_one():
    """MUTATION: synthesising `[DockingReplicate(seed, min(poses))]` in
    `from_dict` when the key is absent.

    An old payload records a seed and poses and NO replicate count. Inventing
    a one-run set would make this application the author of a measurement
    nobody took -- and would make it indistinguishable from a deliberate
    single-replicate run, so "why does this old result show no spread" could
    never be answered.

    Asserted as `is None` explicitly, and explicitly NOT as an empty set or a
    set of length one, because those are the two shapes a synthesis would
    plausibly take.
    """
    payload = _make_result().to_dict()
    del payload["replicates"]

    restored = DockingResultModel.from_dict(payload)

    assert restored.replicates is None
    assert restored.replicates != []
    assert restored.seed == 42  # the seed survives; only the COUNT is absent


def test_resaving_an_old_result_does_not_give_it_a_replicate_count():
    """MUTATION: `to_dict` emitting `[]` or omitting the key.

    The round trip is where a synthesis would launder itself: read an old file,
    write it back, and the result has silently acquired a count. Catches what
    the previous test alone cannot.
    """
    payload = _make_result().to_dict()
    del payload["replicates"]

    once = DockingResultModel.from_dict(payload)
    twice = DockingResultModel.from_dict(once.to_dict())

    assert once.to_dict()["replicates"] is None
    assert twice.replicates is None


def test_a_replicate_set_round_trips_through_real_json():
    """MUTATION: dropping `error` or `protocol_seed` from `to_dict`.

    Through `json.dumps`/`loads` rather than the dict alone, because these go
    into the project file and a tuple or a dataclass that survives an in-memory
    round trip can still fail to serialise.

    Includes a FAILED replicate, which is the row most likely to be dropped.
    """
    import json

    result = _make_result()
    result.replicates = DockingReplicateSet(
        protocol_seed=4712,
        representative_index=1,
        replicates=[
            DockingReplicate(seed=881423, best_affinity_kcal_mol=-8.85),
            DockingReplicate(seed=1990277, best_affinity_kcal_mol=-8.79),
            DockingReplicate(seed=47122019, best_affinity_kcal_mol=None,
                             error="Vina exited 1"),
        ],
    )

    restored = DockingResultModel.from_dict(json.loads(json.dumps(result.to_dict())))

    assert restored.replicates is not None
    assert restored.replicates.protocol_seed == 4712
    assert restored.replicates.representative_index == 1
    assert len(restored.replicates.replicates) == 3
    assert restored.replicates.replicates[2].best_affinity_kcal_mol is None
    assert restored.replicates.replicates[2].error == "Vina exited 1"


def test_the_range_covers_the_successes_and_the_failed_run_still_has_a_row():
    """MUTATION: dropping failed replicates from the set instead of keeping
    them with a reason.

    The spread must come from the runs that PRODUCED a number -- but the failed
    run keeps its row, so the record says 3 were attempted and 2 answered. A
    set that silently held 2 would overstate what was tried.
    """
    replicates = DockingReplicateSet(
        protocol_seed=None,
        representative_index=0,
        replicates=[
            DockingReplicate(seed=1, best_affinity_kcal_mol=-8.85),
            DockingReplicate(seed=2, best_affinity_kcal_mol=None, error="prep failed"),
            DockingReplicate(seed=3, best_affinity_kcal_mol=-8.73),
        ],
    )

    spread = replicates.affinity_range()

    assert len(replicates.replicates) == 3
    assert len(replicates.successes) == 2
    assert spread is not None
    assert spread.n == 2
    assert spread.low == -8.85
    assert spread.high == -8.73


def test_a_set_whose_every_replicate_failed_has_no_range_at_all():
    """MUTATION: returning an empty `AffinityRange` instead of None.

    "Every run failed" and "not measured" must stay distinguishable, and an
    empty range would leave `low`/`high` nothing to answer with.
    """
    replicates = DockingReplicateSet(
        protocol_seed=None,
        representative_index=0,
        replicates=[
            DockingReplicate(seed=1, best_affinity_kcal_mol=None, error="boom"),
            DockingReplicate(seed=2, best_affinity_kcal_mol=None, error="boom"),
        ],
    )

    assert replicates.affinity_range() is None


def test_the_stored_seed_is_the_seed_that_produced_the_stored_poses():
    """MUTATION: storing `protocol_seed` in `DockingResultModel.seed`.

    `seed` has always meant "the seed of the run behind these poses", which is
    what makes a result repeatable after the fact. The pinned root is a
    DIFFERENT number and lives in `protocol_seed`; conflating them would break
    every pre-existing project file's meaning and would let a future cache
    mistake the representative seed for the whole protocol identity.
    """
    result = _make_result()
    result.replicates = DockingReplicateSet(
        protocol_seed=4712,
        representative_index=1,
        replicates=[
            DockingReplicate(seed=881423, best_affinity_kcal_mol=-8.85),
            DockingReplicate(seed=1990277, best_affinity_kcal_mol=-8.79),
        ],
    )
    result.seed = result.replicates.replicates[result.replicates.representative_index].seed

    assert result.seed == 1990277
    assert result.replicates.protocol_seed == 4712
    assert result.seed != result.replicates.protocol_seed
