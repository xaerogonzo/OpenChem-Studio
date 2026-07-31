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


def test_phase26_calculators_are_registered():
    """Regression guard: a future bootstrap/descriptor_providers edit must
    not silently drop these, the way a registration list can."""
    registry = build_service_container().calculator_registry
    expected = {
        "elemental_analysis",
        "topology_analysis",
        "topology_eccentricity",
        "topology_distance_degree",
        "geometry_analysis",
        "surface_analysis",
        "atom_sasa",
        "polar_surface_area",
        "substructure_search",
        "interaction_analysis",
    }

    registered = {
        definition.calculator_id
        for category in registry.categories()
        for definition in registry.by_category(category)
    }

    assert expected <= registered


def test_new_categories_appear_in_the_registry():
    registry = build_service_container().calculator_registry
    assert {"geometry", "surface", "substructure", "interactions"} <= set(registry.categories())


def test_registered_calculators_carry_tags():
    """Tags exist to make ~15 calculators searchable. A definition without
    them still works, but the Phase 26 batch should have them."""
    registry = build_service_container().calculator_registry
    assert registry.get("topology_analysis").tags
    assert registry.get("interaction_analysis").tags


def test_phase27_and_28_calculators_are_registered():
    registry = build_service_container().calculator_registry
    expected = {
        "stereoisomers", "tautomers", "resonance_forms", "markush_enumeration",
        "pka_microspecies", "major_microspecies", "isoelectric_point",
        "logd_curve", "hbond_vs_ph",
    }
    registered = {
        definition.calculator_id
        for category in registry.categories()
        for definition in registry.by_category(category)
    }
    assert expected <= registered


def test_ph_curve_calculators_get_the_pkasolver_interpreter_injected():
    """They take an extra `interpreter_path` argument that `chem/` cannot
    read itself -- the composition root closes over Settings. A missing
    binding would surface as a TypeError only at click time."""
    from openchem.bootstrap import _SETTINGS_BOUND_CALCULATORS

    assert {"pka_microspecies", "isoelectric_point", "logd_curve"} <= _SETTINGS_BOUND_CALCULATORS


def test_naming_calculator_is_registered_and_stout_bound():
    from openchem.bootstrap import _STOUT_BOUND_CALCULATORS

    registry = build_service_container().calculator_registry
    assert "naming" in registry.categories()
    assert [d.calculator_id for d in registry.by_category("naming")] == ["iupac_name"]
    # Needs the STOUT interpreter, NOT pkasolver's -- a wrong binding would
    # hand it the wrong environment and fail only at click time.
    assert "iupac_name" in _STOUT_BOUND_CALCULATORS
