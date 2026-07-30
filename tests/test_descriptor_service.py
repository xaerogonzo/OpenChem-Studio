from __future__ import annotations

from PySide6.QtCore import QThreadPool

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import AlertComputed, DescriptorComputed, PerAtomDataComputed
from openchem.services.descriptor_service import DescriptorService


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def test_descriptor_lifecycle_reaches_completed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "c1ccccc1")

    seen_states: dict[str, list[CacheState]] = {}
    bus.subscribe(
        DescriptorComputed,
        lambda e: seen_states.setdefault(e.descriptor.descriptor_id, []).append(e.descriptor.cache_state),
    )

    service.request_descriptors(model)
    _drain(qapp)

    assert "mol_wt" in seen_states
    assert CacheState.QUEUED in seen_states["mol_wt"]
    assert CacheState.RUNNING in seen_states["mol_wt"]
    assert CacheState.COMPLETED in seen_states["mol_wt"]

    completed = [e for e in seen_states["mol_wt"] if e == CacheState.COMPLETED]
    assert len(completed) == 1


def test_descriptor_completed_values_are_correct(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "c1ccccc1")  # benzene

    completed_values: dict[str, object] = {}

    def handler(event: DescriptorComputed) -> None:
        if event.descriptor.cache_state == CacheState.COMPLETED:
            completed_values[event.descriptor.descriptor_id] = event.descriptor.value

    bus.subscribe(DescriptorComputed, handler)
    service.request_descriptors(model)
    _drain(qapp)

    assert completed_values["formula"] == "C6H6"
    assert completed_values["ring_count"] == 1
    assert completed_values["heavy_atom_count"] == 6
    assert round(completed_values["mol_wt"], 2) == 78.11


def test_descriptor_request_is_a_no_op_when_no_structure(qapp):
    """A freshly-created molecule with no molblock yet (e.g. right after
    File > New Molecule, before anything is drawn) must not produce a
    permanent "failed" row in the Properties panel -- request_descriptors
    should silently skip it rather than running a doomed computation."""
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)
    model = MoleculeModel()  # no molblock

    results: dict[str, CacheState] = {}
    bus.subscribe(DescriptorComputed, lambda e: results.__setitem__(e.descriptor.descriptor_id, e.descriptor.cache_state))

    service.request_descriptors(model)
    _drain(qapp)

    assert results == {}


def test_descriptor_completed_values_carry_provenance(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "c1ccccc1")

    completed = []
    bus.subscribe(
        DescriptorComputed,
        lambda e: completed.append(e.descriptor) if e.descriptor.cache_state == CacheState.COMPLETED else None,
    )
    service.request_descriptors(model)
    _drain(qapp)

    assert completed
    for descriptor in completed:
        assert descriptor.provenance is not None
        assert descriptor.provenance.created_by == "core"
        assert descriptor.provenance.method == "rdkit"


def test_request_descriptors_publishes_alert_computed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "O=C1CSC(=S)N1")  # rhodanine, a known PAINS hit

    alerts = []
    bus.subscribe(AlertComputed, lambda e: alerts.append(e.alert))
    service.request_descriptors(model)
    _drain(qapp)

    assert len(alerts) == 1
    assert alerts[0].alert_id == "pains"
    assert alerts[0].matched


def test_request_descriptors_publishes_per_atom_data_computed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    datasets = []
    bus.subscribe(PerAtomDataComputed, lambda e: datasets.append(e.dataset))
    service.request_descriptors(model)
    _drain(qapp)

    property_ids = {d.property_id for d in datasets}
    assert property_ids == {"crippen_logp_contrib", "crippen_mr_contrib", "gasteiger_charge"}
