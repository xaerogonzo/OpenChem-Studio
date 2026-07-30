from __future__ import annotations

from openchem.bootstrap import build_service_container
from openchem.domain.calculator import ServiceExecution


def test_calculator_registry_includes_docking_and_quantum_chemistry_categories(qapp):
    """Regression guard (Phase 21): Docking/QuantumChemistry are registered
    as discovery-only (ServiceExecution) CalculatorRegistry entries so
    'what can this app compute' stays queryable in one place -- a future
    bootstrap.py edit dropping this registration should fail a test, not
    go unnoticed."""
    registry = build_service_container().calculator_registry

    assert "docking" in registry.categories()
    assert "quantum_chemistry" in registry.categories()

    docking_ids = {d.calculator_id for d in registry.by_category("docking")}
    assert docking_ids == {"docking.vina"}

    qm_ids = {d.calculator_id for d in registry.by_category("quantum_chemistry")}
    assert qm_ids == {"orca.sp", "orca.opt", "orca.opt_freq", "orca.nmr", "orca.nmr_coupling"}

    for definition in registry.by_category("docking") + registry.by_category("quantum_chemistry"):
        assert isinstance(definition.execution, ServiceExecution)


def test_calculator_registry_still_has_the_four_registry_execution_calculators(qapp):
    """Confirms the Phase 21 addition didn't crowd out or break the
    existing Phase 18 calculators."""
    registry = build_service_container().calculator_registry

    assert registry.get("gasteiger_charge_at_ph") is not None
    assert registry.get("crippen_logp_contrib") is not None
    assert registry.get("crippen_mr_contrib") is not None
    assert registry.get("pka") is not None
