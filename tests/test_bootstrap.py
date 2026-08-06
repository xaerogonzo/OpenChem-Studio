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
    assert qm_ids == {
        "orca.sp",
        "orca.opt",
        "orca.opt_freq",
        "orca.nmr",
        "orca.nmr_coupling",
        # Three single points in one compound job, giving vertical I and A
        # as energy DIFFERENCES rather than from orbital energies.
        "orca.delta_scf",
    }

    for definition in registry.by_category("docking") + registry.by_category("quantum_chemistry"):
        assert isinstance(definition.execution, ServiceExecution)


def test_the_lewis_category_is_registered_with_both_its_calculators(qapp):
    """The same guard, for the Lewis work: an empirical site analysis that
    runs anywhere, and a discovery-only entry for the hardness/softness
    quantities that need a real quantum run."""
    registry = build_service_container().calculator_registry

    assert "lewis" in registry.categories()
    by_id = {d.calculator_id: d for d in registry.by_category("lewis")}
    assert set(by_id) == {"lewis_sites", "lewis_hsab"}
    assert by_id["lewis_sites"].prediction_basis == "empirical"
    assert by_id["lewis_hsab"].prediction_basis == "ab_initio"
    assert isinstance(by_id["lewis_hsab"].execution, ServiceExecution)


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
    from openchem.bootstrap import _CALCULATOR_INTERPRETER_SETTING
    from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING

    for calculator in ("pka_microspecies", "isoelectric_point", "logd_curve"):
        assert _CALCULATOR_INTERPRETER_SETTING.get(calculator) == PKASOLVER_PYTHON_SETTING


def test_naming_calculator_is_registered_and_needs_no_sidecar():
    from openchem.bootstrap import _CALCULATOR_INTERPRETER_SETTING

    registry = build_service_container().calculator_registry
    assert "naming" in registry.categories()
    registered = {d.calculator_id for d in registry.by_category("naming")}
    # "locants" joined this category in Thread 1 -- it projects the same
    # engine's numbering onto the structure. The assertion below used to
    # pin the category to exactly ["iupac_name"], but exclusivity was never
    # what this test was about; the sidecar binding is.
    assert "iupac_name" in registered
    # Naming used to need STOUT's interpreter. STOUT is gone and the
    # vendored nomenclature engine runs in-process, so NO calculator in this
    # category may be bound to a sidecar -- a stale binding would hand one
    # an interpreter path it has no use for.
    for calculator_id in registered:
        assert calculator_id not in _CALCULATOR_INTERPRETER_SETTING


def test_phase30_calculators_are_registered():
    registry = build_service_container().calculator_registry
    expected = {
        "huckel_analysis", "huckel_pi_density", "dipole_moment",
        "molecular_dynamics", "cns_mpo", "structural_frameworks",
    }
    registered = {
        definition.calculator_id
        for category in registry.categories()
        for definition in registry.by_category(category)
    }
    assert expected <= registered
    assert {"quantum", "dynamics"} <= set(registry.categories())


def test_every_sidecar_calculator_is_bound_to_its_own_interpreter():
    """Two sidecars share one mapping. The failure this guards is a
    calculator pointed at the wrong environment -- pkasolver's interpreter
    cannot run ADMET-AI, and the error would appear only when clicked."""
    from openchem.bootstrap import _CALCULATOR_INTERPRETER_SETTING
    from openchem.chem.admet_providers import ADMET_PYTHON_SETTING
    from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING

    assert _CALCULATOR_INTERPRETER_SETTING["admet_ml"] == ADMET_PYTHON_SETTING
    assert _CALCULATOR_INTERPRETER_SETTING["pka"] == PKASOLVER_PYTHON_SETTING
    # Two distinct environments, not one shared by accident.
    assert len(set(_CALCULATOR_INTERPRETER_SETTING.values())) == 2


def test_the_admet_calculator_is_registered_and_declared_a_prediction():
    registry = build_service_container().calculator_registry
    definition = registry.get("admet_ml")

    assert definition is not None
    assert definition.category == "admet"
    # hERG/CYP are model outputs. Labelling them anything else would put
    # them on the same footing as the measured descriptors beside them.
    assert definition.prediction_basis == "empirical"
