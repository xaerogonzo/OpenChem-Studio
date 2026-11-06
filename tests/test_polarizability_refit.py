"""The arithmetic of `benchmarks/polarizability/refit.py` and the committed result the shipped table comes from.

The corpus (Bosque and Sales' table) is kept outside git, so the fit itself is not repeated here; what is held is that the functions do what the preregistration says and that the data file shipped
with the application is the committed result.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIR = ROOT / "benchmarks" / "polarizability"


def _refit():
    spec = importlib.util.spec_from_file_location("polarizability_refit_under_test", DIR / "refit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_fit_recovers_known_element_values_without_noise():
    refit = _refit()
    truth = {"C": 1.5, "H": 0.2, "O": 0.6}
    compositions = ({"C": 1, "H": 4}, {"C": 2, "H": 6}, {"C": 2, "H": 6, "O": 1}, {"C": 3, "H": 8, "O": 2}, {"C": 1, "H": 4, "O": 1}, {"C": 6, "H": 6})
    rows = [{"composition": c, "exp": sum(truth[e] * n for e, n in c.items())} for c in compositions]
    x, y = refit.design(rows, ["C", "H", "O"])
    assert refit.fit_relative(x, y) == pytest.approx([1.5, 0.2, 0.6], abs=1e-10)


def test_the_weighting_is_on_the_relative_error():
    """With one small and one large molecule that disagree, the relative fit follows the small one more than the absolute fit does."""
    refit = _refit()
    rows = [{"composition": {"C": 1}, "exp": 1.0}, {"composition": {"C": 100}, "exp": 120.0}]
    x, y = refit.design(rows, ["C"])
    relative, absolute = refit.fit_relative(x, y)[0], refit.fit_relative(x, y, relative=False)[0]
    assert abs(relative - 1.0) < abs(absolute - 1.0)


def test_percent_error_and_summary_arithmetic():
    refit = _refit()
    err = refit.percent_errors(np.array([11.0, 9.0]), np.array([10.0, 10.0]))
    assert err == pytest.approx([10.0, -10.0])
    summary = refit.summarise(err)
    assert summary["mape"] == pytest.approx(10.0) and summary["bias"] == pytest.approx(0.0) and summary["max"] == pytest.approx(10.0)


def test_a_molecule_with_an_element_the_table_lacks_is_not_predicted_at_all():
    refit = _refit()
    assert refit.predict_table([{"composition": {"C": 1, "Xx": 1}}], {"C": 1.0}) is None


def test_the_shipped_table_is_the_committed_result_rounded():
    from openchem.chem.electronic_properties import ADDITIVE_POLARIZABILITY

    from openchem.chem.electronic_properties import ADDITIVE_CONSTANT

    result = json.loads((DIR / "results" / "refit2.json").read_text(encoding="utf-8"))
    for element, row in result["shipped_fit_all_rows"].items():
        if element == "constant":
            assert ADDITIVE_CONSTANT == pytest.approx(row["value"], abs=5e-5)
        else:
            assert ADDITIVE_POLARIZABILITY[element] == pytest.approx(row["value"], abs=5e-5), element


def test_the_preregistered_criteria_hold_in_the_committed_result():
    result = json.loads((DIR / "results" / "refit.json").read_text(encoding="utf-8"))
    assert result["prediction"]["refit"]["mape"] <= result["prediction"]["current_table"]["mape"]
    assert all(v["value"] > 0 for v in result["shipped_fit_all_rows"].values())
    firm = {e for e, n in result["molecules_per_element_working"].items() if n >= 10}
    assert all(result["stability_sd_over_mean"][e] < 0.10 for e in result["stability_sd_over_mean"] if e in firm)
    assert all(0.5 <= ratio <= 2.0 for e, ratio in result["ratio_to_current"].items() if e != "I")
