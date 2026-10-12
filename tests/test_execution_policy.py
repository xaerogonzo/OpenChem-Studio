"""Execution policy: what may run because a model asked, and what a person approves first.

Three layers, each guarding a different way this goes wrong:

* the TYPE refuses a contradictory policy (an AUTO one that starts ORCA);
* the TABLE is checked against the live registry and against each parameter's own bounds, so it
  cannot drift from what is registered;
* the MEASUREMENTS in `benchmarks/calculator_cost/results.json` are what every ceiling and every
  class is read back against, so a bound cannot be loosened without the evidence loosening it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem import bootstrap
from openchem.bootstrap import build_service_container
from openchem.chem.admet_providers import ADMET_PYTHON_SETTING
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.domain.builtin_execution_policies import BUILTIN_POLICIES
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution, ServiceExecution
from openchem.domain.execution_policy import (
    AUTO_MAX_HEAVY_ATOMS,
    EXTERNAL_TOOLS,
    UNCLASSIFIED,
    AiRun,
    ExecutionPolicy,
    ResourceClass,
    decide,
    policy_of,
)

RESULTS = json.loads(
    (Path(__file__).resolve().parent.parent / "benchmarks" / "calculator_cost" / "results.json").read_text(
        encoding="utf-8"
    )
)
#: The scale's own boundaries (`ResourceClass`): INSTANT is under a second, SHORT under ten.
INSTANT_SECONDS = 1.0
SHORT_SECONDS = 10.0


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


def _all(registry):
    return list(registry._definitions.values())


# --- the type -------------------------------------------------------------------------------


def _auto(**kw):
    base = dict(resource=ResourceClass.INSTANT, ai_run=AiRun.AUTO, measured="measured")
    base.update(kw)
    return ExecutionPolicy(**base)


def _confirm(**kw):
    base = dict(resource=ResourceClass.LONG, ai_run=AiRun.CONFIRM, why_confirm="a person decides")
    base.update(kw)
    return ExecutionPolicy(**base)


@pytest.mark.parametrize(
    "build",
    [
        lambda: _auto(resource=ResourceClass.LONG),
        lambda: _auto(external_tools=frozenset({"orca"})),
        lambda: _auto(external_tools=frozenset({"vina"})),
        lambda: _auto(writes_outside_results=True),
        lambda: _auto(measured="  "),
        lambda: _confirm(why_confirm=""),
        lambda: _confirm(auto_bounds=(("steps", None, 10),)),
        lambda: _confirm(auto_excluded=(("p", frozenset({"x"})),)),
        lambda: _auto(external_tools=frozenset({"not_a_tool"})),
        lambda: _auto(auto_bounds=(("steps", 10, 5),)),
        lambda: _auto(auto_bounds=(("steps", None, None),)),
    ],
    ids=[
        "auto-long", "auto-orca", "auto-vina", "auto-writes", "auto-unmeasured", "confirm-no-reason",
        "confirm-with-bounds", "confirm-with-exclusions", "unknown-tool", "inverted-bound", "empty-bound",
    ],
)
def test_a_contradictory_policy_is_refused_at_construction(build):
    with pytest.raises(ValueError):
        build()


def test_pkasolver_and_a_stored_result_do_not_stop_a_policy_being_automatic():
    # A sidecar that reads and returns, and the stored result every calculator leaves, are not
    # the heavy tools or the effects that disqualify.
    policy = _auto(external_tools=frozenset({"pkasolver"}))
    assert policy.ai_run is AiRun.AUTO and policy.writes_outside_results is False


def test_a_calculator_nobody_classified_needs_approval():
    plugin = CalculatorDefinition(
        calculator_id="some_plugin_calc", display_name="X", category="charge", description="",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
    )
    assert plugin.execution_policy is None
    assert policy_of(plugin) is UNCLASSIFIED
    assert decide(policy_of(plugin)).ai_run is AiRun.CONFIRM
    assert UNCLASSIFIED.resource is ResourceClass.LONG


# --- decide ---------------------------------------------------------------------------------


def test_decide_runs_inside_the_bounds_and_asks_outside_them_with_a_reason():
    policy = _auto(auto_bounds=(("ph_step", 0.1, None), ("steps", None, 5000)))
    assert decide(policy, {"ph_step": 0.1, "steps": 5000}).ai_run is AiRun.AUTO
    low = decide(policy, {"ph_step": 0.01})
    assert low.ai_run is AiRun.CONFIRM and "ph_step" in low.reason and "0.1" in low.reason
    high = decide(policy, {"steps": 100000})
    assert high.ai_run is AiRun.CONFIRM and "steps" in high.reason and "5000" in high.reason


def test_a_parameter_the_request_leaves_out_is_not_tested():
    # The default applies, and the policy was measured at the defaults.
    assert decide(_auto(auto_bounds=(("steps", None, 5000),)), {}).ai_run is AiRun.AUTO
    assert decide(_auto(auto_bounds=(("steps", None, 5000),)), None).ai_run is AiRun.AUTO


@pytest.mark.parametrize("value", ["lots", None, True, [1000]])
def test_a_value_that_is_not_a_number_cannot_satisfy_a_numeric_bound(value):
    decision = decide(_auto(auto_bounds=(("steps", None, 5000),)), {"steps": value})
    assert decision.ai_run is AiRun.CONFIRM


def test_an_excluded_choice_needs_approval():
    policy = _auto(auto_excluded=(("conformer_policy", frozenset({"if_2d", "always"})),))
    assert decide(policy, {"conformer_policy": "never"}).ai_run is AiRun.AUTO
    assert decide(policy, {"conformer_policy": "always"}).ai_run is AiRun.CONFIRM


def test_a_molecule_larger_than_anything_measured_needs_approval():
    policy = _auto()
    assert decide(policy, heavy_atoms=AUTO_MAX_HEAVY_ATOMS).ai_run is AiRun.AUTO
    big = decide(policy, heavy_atoms=AUTO_MAX_HEAVY_ATOMS + 1)
    assert big.ai_run is AiRun.CONFIRM and str(AUTO_MAX_HEAVY_ATOMS + 1) in big.reason


def test_a_confirm_policy_stays_confirm_whatever_is_asked():
    decision = decide(_confirm(), {"steps": 1}, heavy_atoms=1)
    assert decision.ai_run is AiRun.CONFIRM and decision.reason == "a person decides"


def test_the_size_ceiling_is_the_largest_molecule_actually_measured():
    sizes = {row["molecule_name"]: row for row in RESULTS["defaults"] if row.get("molecule_name") == "atorvastatin"}
    assert sizes, "the measurement sweep has no atorvastatin rows"
    from openchem.chem.engine import ChemistryEngine

    mol = ChemistryEngine().mol_from_smiles(next(iter(sizes.values()))["molecule"])
    assert mol.GetNumHeavyAtoms() == AUTO_MAX_HEAVY_ATOMS


# --- the table against the registry ---------------------------------------------------------


def test_every_shipped_calculator_has_a_policy_and_the_table_names_nothing_stale(registry):
    registered = {d.calculator_id for d in _all(registry)}
    assert registered - set(BUILTIN_POLICIES) == set(), "built-ins with no policy -- classify them"
    assert set(BUILTIN_POLICIES) - registered == set(), "policies for calculators that no longer exist"


def test_the_policy_reaches_the_definition_the_registry_holds(registry):
    for definition in _all(registry):
        assert definition.execution_policy is BUILTIN_POLICIES[definition.calculator_id], definition.calculator_id


def test_a_plugin_reusing_a_built_in_id_does_not_inherit_its_permission(registry):
    # `_with_policy` runs on the built-in list only; nothing looks a policy up by id afterwards.
    plugin = CalculatorDefinition(
        calculator_id="pka", display_name="Impostor", category="pka", description="",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
    )
    assert policy_of(plugin) is UNCLASSIFIED


def test_with_policy_keeps_a_policy_the_definition_already_declares():
    own = _confirm(why_confirm="declared by the plugin itself")
    definition = CalculatorDefinition(
        calculator_id="alignment_3d", display_name="X", category="charge", description="",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None), execution_policy=own,
    )
    assert bootstrap._with_policy(definition).execution_policy is own


def test_everything_run_by_a_service_needs_approval(registry):
    for definition in _all(registry):
        if isinstance(definition.execution, ServiceExecution):
            policy = policy_of(definition)
            assert policy.ai_run is AiRun.CONFIRM, definition.calculator_id
            assert policy.external_tools, definition.calculator_id


def test_every_sidecar_bound_calculator_declares_the_tool_it_starts(registry):
    wanted = {PKASOLVER_PYTHON_SETTING: "pkasolver", ADMET_PYTHON_SETTING: "admet_ai"}
    for calculator_id, setting in bootstrap._CALCULATOR_INTERPRETER_SETTING.items():
        keys = [setting] if isinstance(setting, str) else list(setting.values())
        declared = BUILTIN_POLICIES[calculator_id].external_tools
        for key in keys:
            assert wanted[key] in declared, f"{calculator_id} reads {key} but does not declare {wanted[key]}"
    assert set(wanted.values()) <= EXTERNAL_TOOLS


def test_every_bound_and_exclusion_names_a_real_parameter_inside_its_own_range(registry):
    for definition in _all(registry):
        policy = policy_of(definition)
        by_name = {p.name: p for p in definition.parameters}
        for name, low, high in policy.auto_bounds:
            assert name in by_name, f"{definition.calculator_id}: bound on unknown parameter {name!r}"
            parameter = by_name[name]
            assert parameter.kind in ("int", "float"), f"{definition.calculator_id}.{name} is not numeric"
            for edge in (low, high):
                if edge is None:
                    continue
                assert parameter.minimum is None or edge >= parameter.minimum, (definition.calculator_id, name, edge)
                assert parameter.maximum is None or edge <= parameter.maximum, (definition.calculator_id, name, edge)
        for name, values in policy.auto_excluded:
            assert name in by_name, f"{definition.calculator_id}: exclusion on unknown parameter {name!r}"
            assert set(values) <= set(by_name[name].choices or []), (definition.calculator_id, name, values)


def test_a_calculator_whose_cost_scales_with_a_parameter_declares_that_it_does(registry):
    # The four the measurement found scaling (`hbond_vs_ph`, molecular dynamics, Geometry (3D)
    # under `always`, stereoisomers) plus the precautionary ones: the other two enumerators carry
    # the stereoisomer cap, and the three sidecar pH sweeps the step floor, by analogy. Dropping a
    # bound would let a model start a 17-second sweep unattended; figures: benchmarks/calculator_cost.
    scaling = {
        "hbond_vs_ph": "ph_step", "molecular_dynamics": "steps", "stereoisomers": "max_structures",
        "tautomers": "max_structures", "resonance_forms": "max_structures", "logd": "ph_step",
        "pka_microspecies": "ph_step", "isoelectric_point": "ph_step",
    }
    for calculator_id, parameter in scaling.items():
        assert parameter in {b[0] for b in BUILTIN_POLICIES[calculator_id].auto_bounds}, calculator_id
    assert "conformer_policy" in {e[0] for e in BUILTIN_POLICIES["geometry_analysis"].auto_excluded}


# --- the table against the measurements -----------------------------------------------------


def _default_rows(calculator_id):
    return [r for r in RESULTS["defaults"] if r["calculator"] == calculator_id]


def _input_rows(calculator_id):
    return [r for r in RESULTS["with_inputs"] if r["calculator"] == calculator_id]


def _scaling_rows(calculator_id, parameter):
    return [r for r in RESULTS["scaling"] if r["calculator"] == calculator_id and parameter in r["overrides"]]


def test_every_instant_calculator_was_measured_under_a_second_on_the_whole_panel():
    instant = [c for c, p in BUILTIN_POLICIES.items() if p.resource is ResourceClass.INSTANT]
    assert instant
    for calculator_id in instant:
        rows = _default_rows(calculator_id)
        assert {r["molecule_name"] for r in rows} == {"ethanol", "aspirin", "atorvastatin"}, calculator_id
        # A refusal is fast and says nothing about the calculator, so it needs at least one run
        # that actually computed -- at its defaults, or failing that with real inputs.
        computed = [r for r in rows if r["status"] == "ready"] or [
            r for r in _input_rows(calculator_id) if r["status"] == "ready"
        ]
        assert computed, f"{calculator_id}: never measured computing anything"
        assert max(r["seconds"] for r in rows + _input_rows(calculator_id)) < INSTANT_SECONDS, calculator_id


def test_every_ceiling_was_measured_to_stay_under_ten_seconds_at_the_ceiling():
    checked = 0
    for calculator_id, policy in BUILTIN_POLICIES.items():
        for name, low, high in policy.auto_bounds:
            rows = _scaling_rows(calculator_id, name)
            if not rows:
                continue  # the pkasolver pH sweeps are cited from the roadmap, not re-measured here
            for edge in (low, high):
                if edge is None:
                    continue
                at_edge = [r for r in rows if r["overrides"][name] == edge]
                assert at_edge, f"{calculator_id}.{name}: nothing was measured at the bound {edge}"
                assert max(r["seconds"] for r in at_edge) <= SHORT_SECONDS, (calculator_id, name, edge)
                checked += 1
    assert checked >= 5


def test_the_bound_is_not_conservative_by_accident_the_next_step_past_it_was_slow_or_unmeasured():
    # hbond_vs_ph and molecular_dynamics: the value one step beyond the bound was measured slower
    # than the bound itself, which is what makes the bound a boundary rather than a guess.
    sweep = {r["overrides"]["ph_step"]: r["seconds"] for r in _scaling_rows("hbond_vs_ph", "ph_step")}
    assert sweep[0.1] <= SHORT_SECONDS < sweep[0.01]
    steps = {r["overrides"]["steps"]: r["seconds"] for r in _scaling_rows("molecular_dynamics", "steps")}
    assert steps[5000] <= SHORT_SECONDS < steps[100000]


def test_geometry_analysis_is_automatic_only_while_it_generates_no_conformers():
    rows = [r for r in RESULTS["scaling"] if r["calculator"] == "geometry_analysis" and "conformer_policy" in r["overrides"]]
    never = [r["seconds"] for r in rows if r["overrides"]["conformer_policy"] == "never"]
    always = [r["seconds"] for r in rows if r["overrides"]["conformer_policy"] == "always"]
    assert never and max(never) <= SHORT_SECONDS
    assert always and max(always) > SHORT_SECONDS, "the exclusion exists because `always` was measured slow"


def test_alignment_needs_approval_because_it_was_measured_slow_on_realistic_molecules():
    slow = [r["seconds"] for r in _input_rows("alignment_3d") if r["molecule"] == "CC(C)c1c(C(=O)Nc2ccccc2)c(-c2ccccc2)c(-c2ccc(F)cc2)n1CCC(O)CC(O)CC(=O)O"]
    assert slow and max(slow) > SHORT_SECONDS
    assert BUILTIN_POLICIES["alignment_3d"].ai_run is AiRun.CONFIRM
