"""A result belongs to the input it was DISPATCHED with, not to what the GUI made of it since.

`DescriptorService` handed a task the live `MoleculeModel`, and the task read
`molblock` and `conformers` at several different moments on a worker thread
while the GUI thread went on editing -- then stamped the result with the
structure version as it stood when the result CAME BACK. AqSolDB (about five
minutes) makes the window reachable; a pause-then-refresh recompute makes it
routine. These tests make it deterministic instead of a race: the pool is
replaced by one that holds the task, the test edits the model between dispatch
and run, and only THEN does the task run -- which is the worst ordering the
race can produce, produced on purpose.
"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculation_input import input_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import (
    DRAWING,
    GEOMETRY,
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
)
from openchem.domain.conformer import ConformerModel
from openchem.domain.input_snapshot import InputSnapshot, snapshot_model
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import ReportResult
from openchem.domain.result_status import READY, STALE, status_of
from openchem.events.base import EventBus
from openchem.events.events import ResultRecorded
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService

ETHANOL = "CCO"
BENZENE = "c1ccccc1"


class _HeldPool:
    """Keeps every queued task until the test decides it may run."""

    def __init__(self) -> None:
        self.tasks: list = []

    def start(self, task) -> None:
        self.tasks.append(task)

    def run_all(self) -> None:
        for task in self.tasks:
            task.run()
        self.tasks.clear()


def _service(structure_version_of=None, registry=None):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(
        bus, engine, calculator_registry=registry or CalculatorRegistry(),
        structure_version_of=structure_version_of,
    )
    pool = _HeldPool()
    service._pool = pool
    recorded: list = []
    bus.subscribe(ResultRecorded, lambda e: recorded.append(e.stored))
    return service, engine, pool, recorded


def _registry(seen: list, calculation_input: str = DRAWING) -> CalculatorRegistry:
    """One calculator that writes down which molecule it was handed."""

    def compute(mol, molecule_uuid, params):
        seen.append((Chem.MolToSmiles(Chem.RemoveHs(mol)), mol))
        return ReportResult(molecule_uuid=molecule_uuid, report_id="probe", name="Probe", facts=())

    registry = CalculatorRegistry()
    registry.register(CalculatorDefinition(
        calculator_id="probe", display_name="Probe", category="test", description="",
        execution=RegistryExecution(compute=compute), calculation_input=calculation_input,
    ))
    return registry


def _request(model: MoleculeModel) -> CalculationRequest:
    return CalculationRequest(calculator_id="probe", molecule_uuid=model.uuid)


# --- the snapshot itself ------------------------------------------------------


def test_a_snapshot_is_a_private_copy_the_live_model_cannot_reach():
    live = MoleculeModel(molblock="A", conformers=[ConformerModel(molblock="C1", energy=1.0)])
    snap = snapshot_model(live)
    live.molblock = "B"
    live.conformers[0].molblock = "C2"
    live.conformers.append(ConformerModel(molblock="C3"))
    live.metadata["late"] = True
    assert snap.molblock == "A"
    assert [c.molblock for c in snap.conformers] == ["C1"]
    assert "late" not in snap.metadata
    assert snap.uuid == live.uuid, "identity is the one thing that must not change"


def test_capture_survives_a_version_counter_that_cannot_be_consulted():
    """A counter that raises costs the version, never the calculation."""
    def broken(_uuid):
        raise RuntimeError("no checker")

    snap = InputSnapshot.capture(MoleculeModel(molblock="A"), broken)
    assert snap.structure_version is None and snap.model.molblock == "A"
    assert InputSnapshot.capture(MoleculeModel(molblock="A")).structure_version is None
    assert InputSnapshot.capture(MoleculeModel(molblock="A"), lambda _u: 7).structure_version == 7


# --- through the service ------------------------------------------------------


def test_a_calculator_is_handed_the_structure_it_was_dispatched_with():
    """Edited between dispatch and run: the calculator must still see ethanol."""
    seen: list = []
    service, engine, pool, _recorded = _service(registry=_registry(seen))
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, ETHANOL)

    service.run_calculator(model, _request(model))
    engine.set_structure_from_smiles(model, BENZENE)  # the GUI moves on
    pool.run_all()

    assert [smiles for smiles, _mol in seen] == ["CCO"]


def test_the_result_is_stamped_with_the_version_it_was_dispatched_at():
    """**THE LATENT BUG.** The version was read when the result returned, so a
    value computed for structure A read as current for structure B."""
    versions = {"now": 3}
    seen: list = []
    service, engine, pool, recorded = _service(
        structure_version_of=lambda _uuid: versions["now"], registry=_registry(seen)
    )
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, ETHANOL)

    service.run_calculator(model, _request(model))
    engine.set_structure_from_smiles(model, BENZENE)
    versions["now"] = 4  # the edit bumped it before the run finished
    pool.run_all()

    (stored,) = recorded
    assert stored.result.structure_version == 3, "stamped at dispatch, not at return"
    assert status_of(stored.result, structure_version=3) == READY
    assert status_of(stored.result, structure_version=4) == STALE, "and so it is stale for the edit"


def test_the_recorded_identity_names_the_input_it_was_computed_on():
    """The fingerprint and the molecule came from two reads of the live model,
    so a result could be filed against an input it was not computed on."""
    service, engine, pool, recorded = _service(registry=_registry([]))
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, ETHANOL)
    dispatched = MoleculeModel(molblock=model.molblock)

    service.run_calculator(model, _request(model))
    engine.set_structure_from_smiles(model, BENZENE)
    pool.run_all()

    (stored,) = recorded
    assert stored.identity.input_fingerprint == input_fingerprint(engine, dispatched, DRAWING)
    assert stored.identity.input_fingerprint != input_fingerprint(engine, model, DRAWING)


def test_a_geometry_calculator_keeps_the_conformer_it_was_dispatched_with():
    """A conformer search finishing mid-run replaced 'the canonical conformer'
    between the resolution and the provenance."""
    seen: list = []
    service, engine, pool, recorded = _service(registry=_registry(seen, GEOMETRY))
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, ETHANOL)
    embedded = Chem.AddHs(Chem.MolFromSmiles(ETHANOL))
    AllChem.EmbedMolecule(embedded, randomSeed=7)
    moved = Chem.Mol(embedded)
    position = moved.GetConformer().GetAtomPosition(0)
    moved.GetConformer().SetAtomPosition(0, (position.x + 0.5, position.y, position.z))
    first, second = (
        ConformerModel(molblock=Chem.MolToMolBlock(mol), energy=-1.0) for mol in (embedded, moved)
    )
    assert first.molblock != second.molblock, "setup: two genuinely different geometries"
    model.conformers = [first]

    service.run_calculator(model, _request(model))
    model.conformers = [second]  # a new search landed
    pool.run_all()

    (_smiles, handed), = seen
    expected = engine.mol_from_molblock(first.molblock).GetConformer().GetPositions()
    assert (handed.GetConformer().GetPositions() == expected).all()
    # ... and the identity names THAT conformer, not the one that arrived later.
    (stored,) = recorded
    dispatched = MoleculeModel(molblock=model.molblock, conformers=[first])
    assert stored.identity.input_fingerprint == input_fingerprint(engine, dispatched, GEOMETRY)
    later = MoleculeModel(molblock=model.molblock, conformers=[second])
    assert stored.identity.input_fingerprint != input_fingerprint(engine, later, GEOMETRY)


def test_the_whole_always_on_set_describes_one_structure():
    """`request_descriptors` starts one task per provider; an edit between two
    `pool.start` calls must not give two providers two structures."""
    service, engine, pool, recorded = _service()
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, ETHANOL)
    dispatched = MoleculeModel(molblock=model.molblock)

    service.request_descriptors(model)
    engine.set_structure_from_smiles(model, BENZENE)
    pool.run_all()

    fingerprints = {stored.identity.input_fingerprint for stored in recorded}
    assert fingerprints == {input_fingerprint(engine, dispatched, DRAWING)}
