"""The gate's two scripts and its tolerance file keep the PREREGISTERED ORDER (`benchmarks/lewis_gate/PREREGISTRATION.md`).

The order is the point of a preregistration: the noise floor is measured on carbon monoxide alone, a tolerance follows by a
rule, it is committed, and only then does BH3 or BF3 meet ORCA. Nothing here runs ORCA. These tests make the order
mechanical, so it does not depend on anybody remembering it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

import openchem.app.debug_drive as debug_drive
from openchem.app.lewis_gate import METHOD_BASIS, tolerance_from_floor
from openchem.domain.quantum_methods import METHOD_BASIS_PRESETS
from tests import conftest as tests_conftest

ROOT = Path(__file__).resolve().parents[1]
FLOOR_SCRIPT = ROOT / "benchmarks" / "visual" / "lewis_gate_floor.json"
PAIR_SCRIPT = ROOT / "benchmarks" / "visual" / "lewis_gate_pair.json"
TOLERANCE = ROOT / "benchmarks" / "lewis_gate" / "tolerance.json"

#: What the gate's molecules are drawn as. Boranes meet ORCA only in the pair script.
BORANES = {"B", "FB(F)F"}


def _steps(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def window(qapp):
    built = QWidget()
    yield built
    tests_conftest.dispose(built)


# --- the scripts ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("script", [FLOOR_SCRIPT, PAIR_SCRIPT], ids=lambda p: p.name)
def test_every_step_is_one_the_driver_has(script):
    unknown = sorted({step["do"] for step in _steps(script) if not hasattr(debug_drive._Driver, f"_do_{step['do']}")})
    assert unknown == []


@pytest.mark.parametrize("script", [FLOOR_SCRIPT, PAIR_SCRIPT], ids=lambda p: p.name)
def test_every_job_is_at_the_one_method_of_the_gate_and_a_calculation_the_recipe_reads(script):
    jobs = [step for step in _steps(script) if step["do"] == "qc_run"]
    assert jobs and {job["method"] for job in jobs} == {METHOD_BASIS}
    assert METHOD_BASIS in METHOD_BASIS_PRESETS
    assert {job["calc_type"] for job in jobs} == {"Geometry Optimization", "Single Point", "Hardness / Softness (delta-SCF)"}


@pytest.mark.parametrize("script", [FLOOR_SCRIPT, PAIR_SCRIPT], ids=lambda p: p.name)
def test_a_job_is_never_started_while_another_may_still_be_running(script):
    steps = _steps(script)
    for position, step in enumerate(steps):
        if step["do"] == "qc_run":
            assert steps[position + 1]["do"] == "qc_wait", f"step {position}: a job with nothing waiting for it"


@pytest.mark.parametrize("script", [FLOOR_SCRIPT, PAIR_SCRIPT], ids=lambda p: p.name)
def test_each_molecule_is_run_through_optimization_then_single_point_then_delta_scf_at_that_geometry(script):
    steps = _steps(script)
    by_molecule: list[list[str]] = []
    for step in steps:
        if step["do"] == "smiles":
            by_molecule.append([])
        elif step["do"] == "qc_run":
            by_molecule[-1].append(step["calc_type"])
        elif step["do"] == "conformer_report":
            assert step["expect"]["canonical_method"] == "orca_opt", "a job at a geometry that is not the optimized one"
            by_molecule[-1].append("conformer_report")
    for sequence in by_molecule:
        assert sequence[:3] == ["Geometry Optimization", "conformer_report", "Single Point"], sequence
        assert sequence[3] == "Hardness / Softness (delta-SCF)"


def test_the_floor_script_never_touches_a_borane():
    steps = _steps(FLOOR_SCRIPT)
    assert {s["smiles"] for s in steps if s["do"] == "smiles"} == {"[C-]#[O+]"}
    assert not [s for s in steps if s["do"] in ("lewis_gate_pair", "lewis_pairing")]


def test_the_floor_repeats_the_same_input_and_then_the_whole_chain_on_a_second_molecule():
    steps = _steps(FLOOR_SCRIPT)
    first = [s["calc_type"] for s in steps[: next(i for i, s in enumerate(steps) if s["do"] == "smiles" and i > 0)] if s["do"] == "qc_run"]
    assert first == ["Geometry Optimization", "Single Point", "Hardness / Softness (delta-SCF)", "Single Point", "Hardness / Softness (delta-SCF)"]
    assert [s["do"] for s in steps].count("smiles") == 2


def test_the_pair_script_cannot_start_a_job_before_the_tolerance_is_checked():
    steps = _steps(PAIR_SCRIPT)
    assert steps[0]["do"] == "lewis_gate_begin"
    assert not [s for s in steps[:1] if s["do"] in ("smiles", "qc_run", "conformers")]


def test_the_pair_script_runs_the_three_molecules_of_the_gate_and_then_the_gate():
    steps = _steps(PAIR_SCRIPT)
    assert [s["smiles"] for s in steps if s["do"] == "smiles"] == ["B", "FB(F)F", "[C-]#[O+]"]
    gate_step = next(s for s in steps if s["do"] == "lewis_gate_pair")
    assert (gate_step["bh3"], gate_step["bf3"], gate_step["co"]) == (-3, -2, -1)
    assert steps.index(gate_step) > max(i for i, s in enumerate(steps) if s["do"] == "qc_wait")


# --- the tolerance file ---------------------------------------------------------------------------------------------


def _tolerance() -> dict:
    return json.loads(TOLERANCE.read_text(encoding="utf-8"))


def test_the_tolerance_is_either_unset_or_exactly_what_the_rule_gives_the_recorded_floor():
    fixed = _tolerance()
    if fixed["T_ev"] is None:
        assert fixed["floor_ev"] is None, "a floor with no tolerance, or a tolerance that was cleared"
        return
    artifact = json.loads((ROOT / fixed["floor_artifact"]).read_text(encoding="utf-8"))
    assert fixed["floor_ev"] == artifact["floor_ev"]
    assert tolerance_from_floor(artifact["floor_ev"]).value_ev == pytest.approx(fixed["T_ev"])


def test_the_tolerance_file_names_the_artifact_the_floor_script_writes():
    steps = _steps(FLOOR_SCRIPT)
    written = next(s["artifact"] for s in steps if s["do"] == "lewis_gate_floor")
    assert _tolerance()["floor_artifact"] == written


# --- the refusal ----------------------------------------------------------------------------------------------------


def _driver(window, monkeypatch):
    driver = debug_drive._Driver(window, [])
    quit_calls = []
    monkeypatch.setattr(driver, "_do_quit", lambda step: quit_calls.append(step))
    return driver, quit_calls


def _floor(tmp_path: Path, floor_ev: float) -> Path:
    path = tmp_path / "floor.json"
    path.write_text(json.dumps({"floor_ev": floor_ev}), encoding="utf-8")
    return path


def _fixed(tmp_path: Path, t_ev, floor_ev, artifact: Path) -> Path:
    path = tmp_path / "tolerance.json"
    path.write_text(json.dumps({"T_ev": t_ev, "floor_ev": floor_ev, "floor_artifact": str(artifact)}), encoding="utf-8")
    return path


def _refused(driver) -> bool:
    return any(a["step"] == "lewis_gate_begin" and not a["ok"] for a in driver._assertions)


def test_with_no_tolerance_fixed_the_run_ends_before_any_job(window, monkeypatch, tmp_path):
    driver, quit_calls = _driver(window, monkeypatch)
    driver._do_lewis_gate_begin({"tolerance": str(_fixed(tmp_path, None, None, _floor(tmp_path, 0.0)))})
    assert quit_calls and _refused(driver)
    assert driver.__dict__.get("_hold_chain") is True, "the chain must not go on to the next step"
    assert getattr(driver, "_gate_tolerance", None) is None


def test_a_missing_tolerance_file_ends_the_run_too(window, monkeypatch, tmp_path):
    driver, quit_calls = _driver(window, monkeypatch)
    driver._do_lewis_gate_begin({"tolerance": str(tmp_path / "nowhere.json")})
    assert quit_calls and _refused(driver)


def test_a_tolerance_the_rule_does_not_give_the_floor_is_refused(window, monkeypatch, tmp_path):
    """A number typed in by hand, however reasonable, is not the preregistered tolerance."""
    driver, quit_calls = _driver(window, monkeypatch)
    floor = _floor(tmp_path, 0.004)
    driver._do_lewis_gate_begin({"tolerance": str(_fixed(tmp_path, 0.05, 0.004, floor))})
    assert quit_calls and _refused(driver)


def test_a_floor_recorded_in_the_tolerance_file_that_is_not_the_artifacts_is_refused(window, monkeypatch, tmp_path):
    driver, quit_calls = _driver(window, monkeypatch)
    driver._do_lewis_gate_begin({"tolerance": str(_fixed(tmp_path, 0.01, 0.0, _floor(tmp_path, 0.004)))})
    assert quit_calls and _refused(driver)


def test_a_floor_artifact_that_cannot_be_read_is_refused(window, monkeypatch, tmp_path):
    driver, quit_calls = _driver(window, monkeypatch)
    driver._do_lewis_gate_begin({"tolerance": str(_fixed(tmp_path, 0.01, 0.004, tmp_path / "gone.json"))})
    assert quit_calls and _refused(driver)


def test_a_floor_above_the_window_leaves_no_tolerance_to_fix(window, monkeypatch, tmp_path):
    driver, quit_calls = _driver(window, monkeypatch)
    driver._do_lewis_gate_begin({"tolerance": str(_fixed(tmp_path, 0.4, 0.4, _floor(tmp_path, 0.4)))})
    assert quit_calls and _refused(driver)


@pytest.mark.parametrize(("floor", "tolerance"), [(0.0, 0.01), (0.004, 0.01), (0.0123, 0.02), (0.37, 0.37)])
def test_the_tolerance_the_rule_gives_the_floor_lets_the_pair_start_and_is_the_one_used(window, monkeypatch, tmp_path, floor, tolerance):
    driver, quit_calls = _driver(window, monkeypatch)
    driver._do_lewis_gate_begin({"tolerance": str(_fixed(tmp_path, tolerance, floor, _floor(tmp_path, floor)))})
    assert quit_calls == [] and not _refused(driver)
    assert driver._gate_tolerance == tolerance
    assert driver.__dict__.get("_hold_chain") is not True
