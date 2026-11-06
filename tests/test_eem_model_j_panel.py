"""The unpause rule of `eem_second_models_preregistration.md` section 13, and the committed result of the panel it judged (section 15)."""

from __future__ import annotations

import importlib.util
import json
import pathlib

DIR = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "charges" / "models"


def _panel():
    spec = importlib.util.spec_from_file_location("model_j_panel_under_test", DIR / "eem_model_j_panel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_three_conditions_must_hold_to_unpause():
    panel = _panel()
    assert panel.judge_unpause(0.13, 0.14, 0.12, 0.4)["unpause"] is True
    assert panel.judge_unpause(0.16, 0.14, 0.12, 0.4)["unpause"] is False  # mean over 0.15
    assert panel.judge_unpause(0.13, 0.20, 0.12, 0.4)["unpause"] is False  # more than 1.25 times the yardstick
    assert panel.judge_unpause(0.13, 0.14, 0.12, 0.6)["unpause"] is False  # one atom over 0.5


def test_the_committed_result_keeps_model_j_paused_and_agrees_with_its_own_judge():
    result = json.loads((DIR / "eem_second_models_results" / "model_j_panel.json").read_text(encoding="utf-8"))
    judged = _panel().judge_unpause(result["mean_abs_J"], result["mean_abs_J_on_common"], result["mean_abs_yardstick_on_common"], result["worst_atom_J"])
    assert judged == result["judge"]
    assert judged["unpause"] is False
    assert "jirouskova" not in "".join(__import__("openchem.chem.geometry_charges", fromlist=["x"]).GEOMETRY_CHARGE_METHODS).lower()
