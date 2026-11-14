"""WP1 of docs/HYPERVALENT_COVERAGE_DESIGN.md: no NaN or infinity is ever published as a result.

Three layers, each held on its own. The WALKER finds a non-finite number wherever a result keeps one. The SERVICES turn it
into a stated limit (`ELEMENT_OUTSIDE_PARAMETER_SET`) for a registry calculator, a descriptor and a per-atom dataset. And
the REAL measured cases (RDKit's Gasteiger charges for P(V), xenon and iodine(III)) no longer reach a panel, while the
ordinary controls publish exactly what they did.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from PySide6.QtCore import QThreadPool

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import (
    CalculationRefusal,
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
)
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.finite_guard import non_finite_in, refusal_for
from openchem.domain.molecule import MoleculeModel
from openchem.domain.refusal_kinds import ELEMENT_OUTSIDE_PARAMETER_SET, REFUSAL_KEY, RefusalKind
from openchem.domain.report import ReportResult
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.events import DescriptorComputed, PerAtomDataComputed, ReportComputed

NAN = float("nan")
INF = float("inf")


def _dataset(values: dict[int, float]) -> PerAtomDataset:
    return PerAtomDataset(property_id="p", name="p", units="", method="m", molecule_uuid="u", values=values)


# --- the walker ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [NAN, INF, -INF, np.float64("nan"), np.float32("inf")])
def test_a_non_finite_per_atom_value_is_found_with_its_atom(bad):
    found = non_finite_in(_dataset({0: 0.1, 3: bad, 4: 0.2}))
    assert [(f.path, f.atom) for f in found] == [("values[3]", 3)]


def test_finite_results_report_nothing():
    assert non_finite_in(_dataset({0: 0.0, 1: -1e300, 2: 12345.678})) == []
    assert non_finite_in(DescriptorValue("d", "d", "", "c", "p", "u", value=1.5)) == []
    assert non_finite_in(DescriptorValue("formula", "f", "", "c", "p", "u", value="nan")) == [], "text is not a number"
    assert non_finite_in(None) == [] and non_finite_in(7) == [] and non_finite_in(True) == []


def test_it_finds_a_number_nested_in_a_descriptor_and_in_arrays():
    assert [f.path for f in non_finite_in(DescriptorValue("d", "d", "", "c", "p", "u", value=NAN))] == ["value"]
    nested = DescriptorValue("d", "d", "", "c", "p", "u", value=[1.0, {"a": (2.0, INF)}])
    assert len(non_finite_in(nested)) == 1
    array = DescriptorValue("d", "d", "", "c", "p", "u", value=np.array([1.0, np.nan]))
    assert len(non_finite_in(array)) == 1
    assert non_finite_in(DescriptorValue("d", "d", "", "c", "p", "u", value=np.array([1, 2, 3]))) == []


def test_a_cycle_does_not_hang_and_a_huge_container_is_bounded():
    loop: list = [1.0]
    loop.append(loop)
    assert non_finite_in(loop) == []
    assert non_finite_in(list(range(10)) + [NAN]) != []


def test_the_refusal_is_a_stated_limit_that_names_the_elements():
    refusal = refusal_for(_dataset({1: NAN, 2: NAN}), "gasteiger_charge", lambda i: {1: "P", 2: "P"}[i])
    assert isinstance(refusal, CalculationRefusal)
    assert refusal.code == ELEMENT_OUTSIDE_PARAMETER_SET and refusal.kind is RefusalKind.LIMIT and refusal.inapplicable
    assert "on P" in refusal.detail and "gasteiger_charge" in refusal.detail
    assert refusal_for(_dataset({1: 0.2}), "x") is None


# --- the services ----------------------------------------------------------------------------------------------


def _drain(qapp, rounds: int = 40) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(rounds):
        qapp.processEvents()


def _service_with(compute):
    from openchem.chem.engine import ChemistryEngine
    from openchem.services.calculator_registry import CalculatorRegistry
    from openchem.events.base import EventBus
    from openchem.services.descriptor_service import DescriptorService

    bus, engine, registry = EventBus(), ChemistryEngine(), CalculatorRegistry()
    registry.register(
        CalculatorDefinition(
            calculator_id="t", display_name="t", category="test", description="", execution=RegistryExecution(compute=compute)
        )
    )
    return bus, engine, DescriptorService(bus, engine, calculator_registry=registry)


def test_a_registry_calculator_returning_nan_is_refused_not_published(qapp):
    bus, engine, service = _service_with(lambda mol, uuid, params: _dataset({0: 0.5, 1: NAN}))
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    seen: list[PerAtomDataset] = []
    bus.subscribe(PerAtomDataComputed, lambda e: seen.append(e.dataset))
    service.run_calculator(model, CalculationRequest(calculator_id="t", molecule_uuid=model.uuid))
    _drain(qapp)
    (dataset,) = seen
    assert dataset.cache_state is CacheState.FAILED and dataset.values == {}
    assert "on C" in dataset.error and dataset.inapplicable
    assert dataset.provenance.parameters[REFUSAL_KEY] == ELEMENT_OUTSIDE_PARAMETER_SET


def test_a_finite_registry_result_is_unchanged(qapp):
    bus, engine, service = _service_with(lambda mol, uuid, params: _dataset({0: 0.5, 1: -0.25}))
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")
    seen: list[PerAtomDataset] = []
    bus.subscribe(PerAtomDataComputed, lambda e: seen.append(e.dataset))
    service.run_calculator(model, CalculationRequest(calculator_id="t", molecule_uuid=model.uuid))
    _drain(qapp)
    assert [d.values for d in seen] == [{0: 0.5, 1: -0.25}]


# --- the measured cases ------------------------------------------------------------------------------------------

#: Every molecule the defect scan found a NaN on, and the controls it found clean.
NAN_MOLECULES = {
    "PF5": "FP(F)(F)(F)F", "XeF4": "F[Xe](F)(F)F", "XeF2": "F[Xe]F", "IF5": "FI(F)(F)(F)F",
    "PCl5": "ClP(Cl)(Cl)(Cl)Cl", "PIDA": "CC(=O)OI(OC(C)=O)c1ccccc1", "CH3PF4": "CP(F)(F)(F)F",
}
CONTROLS = {
    "sulfate": "[O-]S(=O)(=O)[O-]", "DMSO": "CS(C)=O", "perchlorate": "[O-]Cl(=O)(=O)=O", "TMP": "COP(=O)(OC)OC",
    "ethanol": "CCO", "benzene": "c1ccccc1", "SF6": "FS(F)(F)(F)(F)F", "SF4": "FS(F)(F)F",
}


@pytest.fixture(scope="module")
def rig():
    return build_service_container()


def _run_always_on(rig, qapp, smiles: str):
    model = MoleculeModel()
    rig.chemistry_engine.set_structure_from_smiles(model, smiles)
    descriptors: list[DescriptorValue] = []
    datasets: list[PerAtomDataset] = []
    handlers = [
        (DescriptorComputed, lambda e: descriptors.append(e.descriptor)),
        (PerAtomDataComputed, lambda e: datasets.append(e.dataset)),
    ]
    for event_type, handler in handlers:
        rig.event_bus.subscribe(event_type, handler)
    try:
        rig.descriptor_service.request_descriptors(model)
        _drain(qapp)
    finally:
        for event_type, handler in handlers:
            rig.event_bus.unsubscribe(event_type, handler)
    return model, descriptors, datasets


@pytest.mark.parametrize("name", NAN_MOLECULES)
def test_no_always_on_result_is_not_finite_on_the_measured_molecules(rig, qapp, name):
    _, descriptors, datasets = _run_always_on(rig, qapp, NAN_MOLECULES[name])
    published = [d for d in descriptors if d.cache_state is CacheState.COMPLETED]
    assert published, "the finite descriptors are still published"
    for d in published:
        assert not non_finite_in(d), (name, d.descriptor_id)
    for dataset in datasets:
        assert not non_finite_in(dataset), (name, dataset.property_id)
    gasteiger = [d for d in datasets if d.property_id == "gasteiger_charge"]
    assert gasteiger, f"{name}: the refusal is published, so the result is accounted for"
    for d in gasteiger:
        assert d.cache_state is CacheState.FAILED and d.values == {} and d.inapplicable, name
        assert d.provenance.parameters[REFUSAL_KEY] == ELEMENT_OUTSIDE_PARAMETER_SET


@pytest.mark.parametrize("name", NAN_MOLECULES)
def test_gasteiger_at_ph_is_refused_on_the_measured_molecules(rig, qapp, name):
    model = MoleculeModel()
    rig.chemistry_engine.set_structure_from_smiles(model, NAN_MOLECULES[name])
    seen: list[PerAtomDataset] = []
    rig.event_bus.subscribe(PerAtomDataComputed, lambda e: seen.append(e.dataset))
    rig.descriptor_service.run_calculator(
        model, CalculationRequest(calculator_id="gasteiger_charge_at_ph", molecule_uuid=model.uuid)
    )
    _drain(qapp)
    mine = [d for d in seen if d.property_id == "gasteiger_charge_at_ph"]
    assert mine, "the calculator reports, as a refusal"
    last = mine[-1]
    assert last.cache_state is CacheState.FAILED and last.inapplicable
    assert last.provenance.parameters[REFUSAL_KEY] == ELEMENT_OUTSIDE_PARAMETER_SET


@pytest.mark.parametrize("name", CONTROLS)
def test_the_controls_still_publish_finite_gasteiger_charges(rig, qapp, name):
    _, descriptors, datasets = _run_always_on(rig, qapp, CONTROLS[name])
    charges = [d for d in datasets if d.property_id == "gasteiger_charge"]
    assert charges and all(d.cache_state is not CacheState.FAILED and d.values for d in charges)
    assert all(math.isfinite(v) for d in charges for v in d.values.values())
    assert [d for d in descriptors if d.cache_state is CacheState.FAILED and "not finite" in (d.error or "")] == []
