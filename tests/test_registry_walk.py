"""Which registered calculators an Inspector walk will open."""

from __future__ import annotations

from openchem.app.registry_walk import (
    PKASOLVER_CALCULATOR_IDS,
    SIDECAR_CALCULATOR_IDS,
    pkasolver_run_ids,
    registry_inspect_plan,
    sidecar_run_ids,
)
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution, ServiceExecution
from openchem.domain.scientific_result import PerAtomDataset, StructureSetResult


def _per_atom(mol, molecule_uuid, params) -> PerAtomDataset:
    raise AssertionError("plan must not compute")


def _structures(mol, molecule_uuid, params) -> StructureSetResult:
    raise AssertionError("plan must not compute")


def _definition(calculator_id: str, compute) -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=calculator_id,
        category="test",
        description="test",
        execution=RegistryExecution(compute=compute),
    )


def test_plan_inspects_per_atom_and_skips_the_rest():
    per_atom = _definition("crippen_logp_contrib", _per_atom)
    markush = _definition("markush_enumeration", _structures)
    sidecar = CalculatorDefinition(
        calculator_id="pka",
        display_name="pKa",
        category="pka",
        description="test",
        execution=RegistryExecution(compute=_per_atom),
    )
    orca = CalculatorDefinition(
        calculator_id="orca.sp",
        display_name="Single Point",
        category="quantum",
        description="test",
        execution=ServiceExecution(
            service_name="quantum",
            panel_name="Quantum Chemistry",
            panel_id="Quantum_Chemistry",
        ),
    )
    plan = registry_inspect_plan([per_atom, markush, sidecar, orca])
    by_id = {row["id"]: row for row in plan}
    assert by_id["crippen_logp_contrib"]["action"] == "inspect"
    assert by_id["markush_enumeration"]["action"] == "skip"
    assert by_id["markush_enumeration"]["reason"] == "not_per_atom"
    assert by_id["pka"]["action"] == "skip"
    assert by_id["pka"]["reason"] == "sidecar"
    assert by_id["orca.sp"]["action"] == "skip"
    assert by_id["orca.sp"]["reason"] == "service"


def test_sidecar_ids_match_bootstrap_bindings():
    from openchem.bootstrap import _CALCULATOR_INTERPRETER_SETTING

    assert SIDECAR_CALCULATOR_IDS == frozenset(_CALCULATOR_INTERPRETER_SETTING)


def test_pkasolver_run_ids_are_the_pka_sidecars_not_admet():
    assert "pka" in PKASOLVER_CALCULATOR_IDS
    assert "gasteiger_charge_at_ph" in PKASOLVER_CALCULATOR_IDS
    assert "admet_ml" not in PKASOLVER_CALCULATOR_IDS
    assert "solubility" not in PKASOLVER_CALCULATOR_IDS
    assert PKASOLVER_CALCULATOR_IDS <= SIDECAR_CALCULATOR_IDS
    ids = pkasolver_run_ids(
        [
            _definition("pka", _per_atom),
            _definition("admet_ml", _per_atom),
            _definition("crippen_logp_contrib", _per_atom),
        ]
    )
    assert ids == ["pka"]


def test_sidecar_run_ids_include_admet():
    ids = sidecar_run_ids(
        [
            _definition("pka", _per_atom),
            _definition("admet_ml", _per_atom),
            _definition("solubility", _per_atom),
            _definition("crippen_logp_contrib", _per_atom),
        ]
    )
    assert ids == ["pka", "admet_ml", "solubility"]
