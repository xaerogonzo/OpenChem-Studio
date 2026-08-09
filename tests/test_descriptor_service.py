from __future__ import annotations

from PySide6.QtCore import QThreadPool

from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import (
    GEOMETRY,
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
)
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import AlertComputed, DescriptorComputed, PerAtomDataComputed
from openchem.services.calculator_registry import CalculatorRegistry
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


def test_queued_and_running_placeholders_carry_the_real_category(qapp):
    """Regression test for the Property Panel category-bucketing bug:
    QUEUED/RUNNING placeholders must carry the same category the final
    COMPLETED value does, so a UI that binds a row to its first-seen
    category never has to re-parent it (see PropertyPanel's defensive
    re-parenting for when a provider doesn't declare categories up front)."""
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "c1ccccc1")

    categories_seen: dict[str, set[str]] = {}
    bus.subscribe(
        DescriptorComputed,
        lambda e: categories_seen.setdefault(e.descriptor.descriptor_id, set()).add(e.descriptor.category),
    )
    service.request_descriptors(model)
    _drain(qapp)

    assert categories_seen["formula"] == {"identity"}
    assert categories_seen["mol_wt"] == {"physicochemical"}
    assert categories_seen["num_rotatable_bonds"] == {"topology"}


def test_requesting_GEOMETRY_computes_against_the_conformer(qapp):
    """Shape descriptors need a real 3D conformer (Is3D()) -- asking for
    GEOMETRY is what lets them compute for real instead of permanently
    reporting "needs a conformer" (see MainWindow's
    _on_conformers_changed).

    The caller used to resolve the conformer itself and hand over a raw
    molblock. It now states the policy and `select_calculation_input`
    owns the choice, the validation and the fallback -- one selector for
    this path and for `run_calculator`, which had already moved."""
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCCCCCO")  # flat 2D molblock
    original_molblock = model.molblock

    conformer_mol, _energy = RDKitConformerProvider().generate_conformers(
        engine.mol_from_model(model), num_conformers=1, optimize=False
    )[0]
    model.conformers.append(
        ConformerModel(molblock=engine.mol_to_molblock(conformer_mol), energy=-1.0)
    )

    completed_values: dict[str, object] = {}
    completed_states: dict[str, CacheState] = {}

    def handler(event: DescriptorComputed) -> None:
        if event.descriptor.cache_state in (CacheState.COMPLETED, CacheState.FAILED):
            completed_values[event.descriptor.descriptor_id] = event.descriptor.value
            completed_states[event.descriptor.descriptor_id] = event.descriptor.cache_state

    bus.subscribe(DescriptorComputed, handler)
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    assert completed_states["radius_of_gyration"] == CacheState.COMPLETED
    assert isinstance(completed_values["radius_of_gyration"], float)
    # Request-scoped -- the drawing itself is untouched.
    assert model.molblock == original_molblock


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

    # A subset, not a count: what this test is about is that alerts reach
    # the bus at all, and pinning the exact number just makes it fail
    # whenever a new alert family ships without saying anything about the
    # publishing path.
    alerts_by_id = {a.alert_id: a for a in alerts}
    assert {"pains", "brenk", "mutagenicity_alerts"} <= set(alerts_by_id)
    assert alerts_by_id["pains"].matched
    assert alerts_by_id["brenk"].matched


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


def _definition(calculator_id: str, compute) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id,
        category="test",
        description="",
        execution=RegistryExecution(compute=compute),
    )


def test_run_calculator_publishes_per_atom_data_computed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()

    def compute(mol, molecule_uuid, params):
        return PerAtomDataset(
            property_id="test_calc", name="Test", units="", method="rdkit",
            molecule_uuid=molecule_uuid, values={0: 1.5},
        )

    registry.register(_definition("test_calc", compute))
    service = DescriptorService(bus, engine, calculator_registry=registry)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    datasets = []
    bus.subscribe(PerAtomDataComputed, lambda e: datasets.append(e.dataset))
    service.run_calculator(model, CalculationRequest(calculator_id="test_calc", molecule_uuid=model.uuid))
    _drain(qapp)

    assert len(datasets) == 1
    assert datasets[0].property_id == "test_calc"
    assert datasets[0].values == {0: 1.5}


def test_run_calculator_publishes_alert_computed_for_an_alert_result(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()

    def compute(mol, molecule_uuid, params):
        return AlertResult(alert_id="test_alert", name="Test Alert", molecule_uuid=molecule_uuid, matched=["x"])

    registry.register(_definition("test_alert_calc", compute))
    service = DescriptorService(bus, engine, calculator_registry=registry)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    alerts = []
    bus.subscribe(AlertComputed, lambda e: alerts.append(e.alert))
    service.run_calculator(model, CalculationRequest(calculator_id="test_alert_calc", molecule_uuid=model.uuid))
    _drain(qapp)

    assert len(alerts) == 1
    assert alerts[0].alert_id == "test_alert"


def test_run_calculator_with_unknown_calculator_id_publishes_a_failed_result(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine, calculator_registry=CalculatorRegistry())

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    datasets = []
    bus.subscribe(PerAtomDataComputed, lambda e: datasets.append(e.dataset))
    service.run_calculator(model, CalculationRequest(calculator_id="does-not-exist", molecule_uuid=model.uuid))
    _drain(qapp)

    assert len(datasets) == 1
    assert datasets[0].cache_state == CacheState.FAILED
    assert "does-not-exist" in datasets[0].error


def test_run_calculator_passes_parameters_through_to_compute(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    received_params = []

    def compute(mol, molecule_uuid, params):
        received_params.append(params)
        return PerAtomDataset(
            property_id="test_calc", name="Test", units="", method="rdkit",
            molecule_uuid=molecule_uuid, values={},
        )

    registry.register(_definition("test_calc", compute))
    service = DescriptorService(bus, engine, calculator_registry=registry)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    service.run_calculator(
        model, CalculationRequest(calculator_id="test_calc", molecule_uuid=model.uuid, parameters={"pH": 2.0})
    )
    _drain(qapp)

    assert received_params == [{"pH": 2.0}]


def test_run_calculator_when_compute_raises_publishes_a_failed_result(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()

    def compute(mol, molecule_uuid, params):
        raise ValueError("boom")

    registry.register(_definition("test_calc", compute))
    service = DescriptorService(bus, engine, calculator_registry=registry)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    datasets = []
    bus.subscribe(PerAtomDataComputed, lambda e: datasets.append(e.dataset))
    service.run_calculator(model, CalculationRequest(calculator_id="test_calc", molecule_uuid=model.uuid))
    _drain(qapp)

    assert len(datasets) == 1
    assert datasets[0].cache_state == CacheState.FAILED
    assert "boom" in datasets[0].error


def test_run_calculator_publishes_spectrum_computed_for_a_spectrum_result(qapp):
    """Phase 22: a RegistryExecution calculator can return a SpectrumResult
    (the empirical NMR estimator) -- must publish SpectrumComputed, not
    fall through to the 'unpublishable result type' error path."""
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()

    def compute(mol, molecule_uuid, params):
        from openchem.domain.scientific_result import NMRSpectrumResult

        return NMRSpectrumResult(
            spectrum_type="nmr_empirical", name="NMR Shift", units="ppm", method="smarts_lookup",
            molecule_uuid=molecule_uuid, values={0: 1.4},
        )

    registry.register(_definition("nmr_empirical", compute))
    service = DescriptorService(bus, engine, calculator_registry=registry)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    from openchem.events.events import SpectrumComputed

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    service.run_calculator(model, CalculationRequest(calculator_id="nmr_empirical", molecule_uuid=model.uuid))
    _drain(qapp)

    assert len(spectra) == 1
    assert spectra[0].spectrum_type == "nmr_empirical"


def test_run_calculator_end_to_end_with_the_real_charge_at_ph_calculator(qapp):
    """Regression test wiring bootstrap.py's real CALCULATOR_DEFINITIONS
    through DescriptorService, not just a fake compute function -- catches
    a bootstrap.py registration mistake a fake-only test wouldn't."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        registry.register(definition)
    service = DescriptorService(bus, engine, calculator_registry=registry)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CC(=O)O")  # acetic acid

    datasets = []
    bus.subscribe(PerAtomDataComputed, lambda e: datasets.append(e.dataset))
    service.run_calculator(
        model,
        CalculationRequest(calculator_id="gasteiger_charge_at_ph", molecule_uuid=model.uuid, parameters={"pH": 2.0}),
    )
    _drain(qapp)

    assert len(datasets) == 1
    assert datasets[0].cache_state == CacheState.COMPLETED
    assert datasets[0].property_id == "gasteiger_charge_at_ph"
    assert len(datasets[0].values) > 0


def test_an_unusable_conformer_falls_back_instead_of_failing_every_descriptor(qapp):
    """What the caller's inline copy left out.

    It resolved `canonical_conformer(model).molblock` and handed the
    string over, so a conformer that would not parse raised inside the
    task and took EVERY descriptor from that provider down as FAILED.
    `select_calculation_input` logs it and computes on the drawing, which
    is the answer the user can still use.
    """
    bus = EventBus()
    engine = ChemistryEngine()
    service = DescriptorService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    model.conformers.append(ConformerModel(molblock="not a molblock at all", energy=-1.0))

    states: dict[str, CacheState] = {}

    def handler(event: DescriptorComputed) -> None:
        if event.descriptor.cache_state in (CacheState.COMPLETED, CacheState.FAILED):
            states[event.descriptor.descriptor_id] = event.descriptor.cache_state

    bus.subscribe(DescriptorComputed, handler)
    service.request_descriptors(model, GEOMETRY)
    _drain(qapp)

    # The whole provider used to go down together. The descriptors that
    # need no geometry must survive an unusable conformer.
    assert states["mol_wt"] == CacheState.COMPLETED
    assert states["formula"] == CacheState.COMPLETED
    # The SHAPE descriptors still fail, and that is correct rather than a
    # weaker result: falling back to the drawing means there is genuinely
    # no 3D geometry, and `GEOMETRY` means prefer, not require. They say
    # "needs a conformer", which is the honest answer.
    assert states["radius_of_gyration"] == CacheState.FAILED
