"""Quantum goal actions: separate from `GoalRun.calculator_ids`, staging only."""

from __future__ import annotations

from openchem.domain.calculator_goals import GOALS, SCOPE_ALL, SCOPE_THIS, validate_goals
from openchem.domain.quantum_goal_action import (
    ENGINE_CALC_TYPES,
    NMR_LIMITATION,
    QUANTUM_ACTIONS,
    XTB_FREQ_LIMITATION,
    QuantumGoalAction,
    action_of,
    actions_for_goal,
    decide_stage,
    engine_supports,
    validate_action,
    validate_quantum_actions,
)


def test_shipped_actions_are_sound():
    assert validate_quantum_actions() == []


def test_actions_are_not_on_goal_calculator_ids():
    goal_ids = {e.calculator_id for g in GOALS for e in g.entries}
    action_ids = {a.action_id for a in QUANTUM_ACTIONS}
    assert goal_ids.isdisjoint(action_ids)


def test_spectra_keeps_database_1h_as_a_lookup():
    spectra = next(g for g in GOALS if g.goal_id == "spectra")
    assert "nmr_database" in spectra.recommended_ids()
    nmr = action_of("orca.nmr")
    assert nmr is not None
    assert "database" in NMR_LIMITATION.lower()
    assert nmr.calc_type == "nmr"
    assert "1h" not in nmr.action_id and "13c" not in nmr.action_id


def test_one_nmr_action_not_two_nuclei():
    assert [a.action_id for a in QUANTUM_ACTIONS if a.calc_type == "nmr"] == ["orca.nmr"]


def test_psi4_is_not_offered_for_nmr_or_frequencies():
    assert "psi4" not in {a.provider_id for a in QUANTUM_ACTIONS}
    assert not engine_supports("psi4", "nmr")
    assert not engine_supports("psi4", "opt_freq")
    assert ENGINE_CALC_TYPES["psi4"] == frozenset({"sp", "opt"})
    fake = QuantumGoalAction(
        action_id="psi4.nmr",
        goal_id="spectra",
        calc_type="nmr",
        provider_id="psi4",
        reason="should fail",
        label="Psi4 NMR",
    )
    problems = validate_action(fake)
    assert any("does not run nmr" in p for p in problems)


def test_xtb_frequency_limitation_is_disclosed():
    xtb = action_of("xtb.opt_freq")
    assert xtb is not None
    assert xtb.calc_type == "opt_freq"
    assert "intensit" in xtb.limitation.lower() or "vibspectrum" in xtb.limitation.lower()
    assert XTB_FREQ_LIMITATION in (xtb.limitation, xtb.reason)
    silent = QuantumGoalAction(
        action_id="xtb.opt_freq.silent",
        goal_id="spectra",
        calc_type="opt_freq",
        provider_id="xtb",
        reason="frequencies",
        label="xtb freq",
        limitation="frequencies",
    )
    assert any("intensit" in p or "vibspectrum" in p for p in validate_action(silent))


def test_orca_ir_is_opt_freq():
    ir = action_of("orca.opt_freq")
    assert ir is not None
    assert ir.calc_type == "opt_freq"
    assert ir.provider_id == "orca"


def test_validate_goals_is_unchanged_by_quantum_actions():
    from openchem.bootstrap import build_service_container
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    registry = build_service_container().calculator_registry
    assert validate_goals(registry.get) == []


def test_stage_this_molecule_ok_does_not_imply_start():
    action = action_of("orca.nmr")
    decision = decide_stage(
        action,
        available_engines=set(),
        scope_mode=SCOPE_THIS,
        molecule_count=1,
        selected=True,
    )
    assert decision.ok
    assert decision.calc_type == "nmr"
    assert decision.provider_id == "orca"


def test_multi_molecule_scope_is_refused():
    action = action_of("orca.nmr")
    decision = decide_stage(
        action,
        available_engines={"orca"},
        scope_mode=SCOPE_ALL,
        molecule_count=3,
        selected=True,
    )
    assert not decision.ok
    assert "wizard" in decision.message.lower()
    assert "properties" not in decision.message.lower()
    assert "several molecules" in decision.message.lower() or "this molecule" in decision.message.lower()
    assert "nothing started" in decision.message.lower()


def test_xtb_without_setup_is_refused():
    action = action_of("xtb.opt_freq")
    decision = decide_stage(
        action,
        available_engines=set(),
        scope_mode=SCOPE_THIS,
        molecule_count=1,
        selected=True,
    )
    assert not decision.ok
    assert "not set up" in decision.message.lower()


def test_xtb_with_setup_stages():
    action = action_of("xtb.opt_freq")
    decision = decide_stage(
        action,
        available_engines={"xtb"},
        scope_mode=SCOPE_THIS,
        molecule_count=1,
        selected=True,
    )
    assert decision.ok
    assert "intensit" in decision.limitation.lower() or "vibspectrum" in decision.limitation.lower()


def test_spectra_offers_the_three_actions():
    ids = [a.action_id for a in actions_for_goal("spectra")]
    assert ids == ["orca.nmr", "orca.opt_freq", "xtb.opt_freq"]
    assert actions_for_goal("charge") == ()


def test_two_nmr_actions_fail_the_table():
    extra = QUANTUM_ACTIONS + (
        QuantumGoalAction(
            action_id="orca.nmr_13c",
            goal_id="spectra",
            calc_type="nmr",
            provider_id="orca",
            reason="second NMR",
            label="13C",
            limitation="One NMR calculation.",
        ),
    )
    problems = validate_quantum_actions(extra)
    assert any("more than one NMR" in p for p in problems)
