from __future__ import annotations

import pytest

from openchem.domain.calculator import CalculatorDefinition, CalculatorParameter, RegistryExecution, ServiceExecution
from openchem.domain.common import CacheState
from openchem.domain.scientific_result import PerAtomDataset
from openchem.services.calculator_registry import CalculatorRegistry


def _fake_result(mol, molecule_uuid, params) -> PerAtomDataset:
    return PerAtomDataset(
        property_id="test",
        name="Test",
        units="",
        method="test",
        molecule_uuid=molecule_uuid,
        values={},
        provenance=None,
        timestamp=0.0,
        cache_state=CacheState.COMPLETED,
    )


def _definition(calculator_id: str, category: str = "charge", compute=_fake_result) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.title(),
        category=category,
        description="test calculator",
        execution=RegistryExecution(compute=compute),
        parameters=[CalculatorParameter(name="pH", label="pH", kind="float", default=7.4)],
    )


def _service_definition(calculator_id: str, category: str = "docking") -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id.title(),
        category=category,
        description="run from its own panel",
        execution=ServiceExecution(service_name="some_service", panel_name="Some Panel"),
    )


def test_register_and_get():
    registry = CalculatorRegistry()
    definition = _definition("gasteiger_charge_at_ph")

    registry.register(definition)

    assert registry.get("gasteiger_charge_at_ph") is definition


def test_get_unknown_calculator_returns_none():
    registry = CalculatorRegistry()
    assert registry.get("does-not-exist") is None


def test_compute_dispatches_to_the_registered_function():
    registry = CalculatorRegistry()
    calls = []

    def compute(mol, molecule_uuid, params):
        calls.append((mol, molecule_uuid, params))
        return _fake_result(mol, molecule_uuid, params)

    registry.register(_definition("crippen_logp_contrib", category="logp", compute=compute))

    result = registry.compute("crippen_logp_contrib", "fake-mol", "mol-1", {"pH": 2.0})

    assert calls == [("fake-mol", "mol-1", {"pH": 2.0})]
    assert isinstance(result, PerAtomDataset)
    assert result.molecule_uuid == "mol-1"


def test_compute_unknown_calculator_raises_key_error():
    registry = CalculatorRegistry()
    with pytest.raises(KeyError):
        registry.compute("does-not-exist", "fake-mol", "mol-1", {})


def test_register_service_execution_definition_is_discoverable():
    """A ServiceExecution-backed definition (Docking, QuantumChemistry) has
    no compute function -- it must still be a real registry citizen for
    get()/by_category()/categories(), just not compute()-dispatchable."""
    registry = CalculatorRegistry()
    definition = _service_definition("docking.vina", category="docking")

    registry.register(definition)

    assert registry.get("docking.vina") is definition
    assert registry.by_category("docking") == [definition]
    assert "docking" in registry.categories()


def test_compute_against_service_execution_definition_raises_value_error():
    registry = CalculatorRegistry()
    registry.register(_service_definition("docking.vina", category="docking"))

    with pytest.raises(ValueError, match="docking.vina"):
        registry.compute("docking.vina", "fake-mol", "mol-1", {})


def test_by_category_returns_only_matching_definitions():
    registry = CalculatorRegistry()
    registry.register(_definition("gasteiger_charge_at_ph", category="charge"))
    registry.register(_definition("crippen_logp_contrib", category="logp"))
    registry.register(_definition("crippen_mr_contrib", category="molar_refractivity"))

    charge_calculators = registry.by_category("charge")

    assert [d.calculator_id for d in charge_calculators] == ["gasteiger_charge_at_ph"]


def test_by_category_with_two_calculators_in_the_same_category():
    """Regression test for the Property Panel's row-generation code path
    actually being generic: two calculators sharing a category must both
    be returned, proving a section isn't hardcoded to exactly one."""
    registry = CalculatorRegistry()
    registry.register(_definition("calc_a", category="charge"))
    registry.register(_definition("calc_b", category="charge"))

    assert {d.calculator_id for d in registry.by_category("charge")} == {"calc_a", "calc_b"}


def test_by_category_with_no_matches_returns_empty_list():
    registry = CalculatorRegistry()
    assert registry.by_category("nonexistent") == []


def test_categories_returns_every_distinct_registered_category():
    registry = CalculatorRegistry()
    registry.register(_definition("calc_a", category="charge"))
    registry.register(_definition("calc_b", category="charge"))
    registry.register(_definition("calc_c", category="logp"))
    registry.register(_definition("calc_d", category="pka"))

    assert registry.categories() == ["charge", "logp", "pka"]


def test_categories_with_nothing_registered_is_empty():
    assert CalculatorRegistry().categories() == []
