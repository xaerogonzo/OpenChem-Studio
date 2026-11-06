"""The registered rule of `eem_second_models_preregistration.md` section 19 and the shape of its panel (`benchmarks/charges/models/eem_model_j_halogen_sulfur.py`)."""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

DIR = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "charges" / "models"


def _module():
    spec = importlib.util.spec_from_file_location("model_j_halogen_sulfur_under_test", DIR / "eem_model_j_halogen_sulfur.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_rule_needs_all_three_conditions():
    m = _module()
    assert m.judge(0.10, 0.40, 0.10, 0.09)["offer_for_these_elements"] is True
    assert m.judge(0.16, 0.40, 0.10, 0.09)["mean_ok"] is False
    assert m.judge(0.10, 0.51, 0.10, 0.09)["worst_atom_ok"] is False
    assert m.judge(0.10, 0.40, 0.126, 0.10)["ratio_to_n_ok"] is False
    assert m.judge(0.10, 0.40, 0.125, 0.10)["offer_for_these_elements"] is True


def test_the_panel_is_registered_as_written():
    m = _module()
    assert len(m.PANEL) == 26 and len(m.REFUSED_BY_J_EXPECTED) == 3
    counts = {e: sum(1 for s in m.PANEL.values() if e in s) for e in ("Cl", "Br", "S")}
    assert counts["Cl"] >= 12 and counts["Br"] >= 6 and counts["S"] >= 6
    assert (m.MAX_MEAN_E, m.MAX_RATIO_TO_N, m.MAX_ATOM_E) == (0.15, 1.25, 0.5)


def test_the_committed_result_agrees_with_its_judge():
    path = DIR / "eem_second_models_results" / "model_j_halogen_sulfur.json"
    if not path.exists():
        pytest.skip("the halogen and sulfur panel has not been run")
    m = _module()
    r = json.loads(path.read_text(encoding="utf-8"))
    assert r["checks"]["implementation_ok"]
    assert m.judge(r["mean_abs_J"], r["worst_atom_J"], r["mean_abs_J_on_common"], r["mean_abs_N_on_common"]) == r["judge"]
