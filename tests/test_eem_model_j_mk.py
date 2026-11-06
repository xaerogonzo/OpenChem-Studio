"""The pure parts of the Merz-Kollman reference (`benchmarks/charges/models/eem_model_j_mk.py`) and its committed result."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

DIR = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "charges" / "models"


def _mk():
    # the module loads its panel sibling by path, so it must be importable by its own name
    spec = importlib.util.spec_from_file_location("model_j_mk_under_test", DIR / "eem_model_j_mk.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shell_points_lie_outside_every_scaled_atom_sphere():
    mk = _mk()
    coords = np.array([[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]])
    points = mk.shell_points(["C", "C"], coords, scales=(1.4,))
    distance = np.linalg.norm(points[:, None, :] - coords[None, :, :], axis=-1)
    assert distance.min() >= 1.4 * 1.70 - 1e-6
    assert len(points) > 100


def test_the_fit_recovers_charges_that_made_the_potential_and_honours_the_net_charge():
    mk = _mk()
    coords_a = np.array([[0.0, 0.0, 0.0], [1.4, 0.2, 0.0], [-0.5, 1.2, 0.3], [0.3, -0.9, 1.1]])
    truth = np.array([0.6, -0.4, -0.5, 0.5])
    points = mk.shell_points(["C", "O", "N", "C"], coords_a)
    bohr_coords, bohr_points = coords_a / mk.BOHR, points / mk.BOHR
    potential = (1.0 / np.linalg.norm(bohr_points[:, None, :] - bohr_coords[None, :, :], axis=-1)) @ truth
    fitted = mk.fit_charges(bohr_coords, bohr_points, potential, float(truth.sum()))
    assert fitted == pytest.approx(truth, abs=1e-6)
    assert mk.fit_charges(bohr_coords, bohr_points, potential, 1.0).sum() == pytest.approx(1.0)


def test_the_committed_result_passed_its_implementation_checks_and_agrees_with_its_judge():
    path = DIR / "eem_second_models_results" / "model_j_mk.json"
    if not path.exists():
        pytest.skip("the Merz-Kollman panel has not been run")
    result = json.loads(path.read_text(encoding="utf-8"))
    # water is not in the panel, so its check (section 17) is read from its own run
    water = json.loads((DIR / "eem_second_models_results" / "model_j_mk_water.json").read_text(encoding="utf-8"))
    assert result["checks"]["sums_to_net_charge"] and result["checks"]["diff_to_chelpg_ok"] and water["in_registered_range"]
    assert result["judge"]["unpause"] is False
    spec = importlib.util.spec_from_file_location("model_j_panel_for_mk_test", DIR / "eem_model_j_panel.py")
    panel_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel_module)
    assert panel_module.judge_unpause(result["mean_abs_J"], result["mean_abs_J_on_common"], result["mean_abs_yardstick_on_common"], result["worst_atom_J"]) == result["judge"]
