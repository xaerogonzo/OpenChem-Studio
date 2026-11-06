"""The arithmetic of `benchmarks/polarizability/refit2.py` and the criteria its committed result must meet (`PREREGISTRATION_2.md`).

The corpora are kept outside git, so the fit is not repeated here; what is held is that the functions do what the registration says and that the committed result meets the ship criteria.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import numpy as np
import pytest

DIR = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "polarizability"


def _refit2():
    spec = importlib.util.spec_from_file_location("polarizability_refit2_under_test", DIR / "refit2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hydrogen_is_typed_by_its_neighbour_only_when_asked():
    refit = _refit2()
    assert refit.atom_counts("CO", False) == {"C": 1, "O": 1, "H": 4}
    assert refit.atom_counts("CO", True) == {"C": 1, "O": 1, "H": 3, "H(O)": 1}
    assert refit.atom_counts("CN", True)["H(N)"] == 2


def test_a_constant_per_molecule_is_recovered_without_noise():
    refit = _refit2()
    smiles = ["O", "C", "C#C", "C=C", "CO", "OO", "O=C=O", "CC=O"]  # compositions that are not collinear with the constant
    rows = [{"smiles": s, "exp": 1.5 * refit.atom_counts(s, False).get("C", 0) + 0.2 * refit.atom_counts(s, False).get("H", 0) + 0.6 * refit.atom_counts(s, False).get("O", 0) + 0.4} for s in smiles]
    keys = ["C", "H", "O"]
    assert refit.fit(rows, keys, False, True) == pytest.approx([1.5, 0.2, 0.6, 0.4], abs=1e-9)


def test_a_molecule_with_an_atom_type_the_fit_lacks_is_not_predicted():
    refit = _refit2()
    prediction = refit.predict([{"smiles": "CCl"}], ["C", "H"], np.array([1.0, 0.2]), False, False)
    assert np.isnan(prediction[0])


def test_the_choice_rule_prefers_the_simpler_variant_unless_the_gain_is_large_enough():
    refit = _refit2()
    assert refit.choose_variant({"A": 7.70, "B": 7.13, "C": 7.68, "D": 7.09}) == "B"  # D beats B by 0.04: not enough for the extra parameters
    assert refit.choose_variant({"A": 8.0, "B": 7.0, "C": 8.0, "D": 6.0}) == "D"
    assert refit.choose_variant({"A": 5.0, "B": 5.1, "C": 5.2, "D": 5.3}) == "A"


def test_the_committed_result_meets_the_registered_ship_criteria():
    result = json.loads((DIR / "results" / "refit2.json").read_text(encoding="utf-8"))
    chosen = result["variants"][result["chosen"]]
    shipped = result["shipped"]
    assert chosen["crc_holdout"]["mape"] < shipped["crc_holdout"]["mape"]
    assert chosen["bosque_holdout"]["mape"] <= shipped["bosque_holdout"]["mape"] + 0.5
    assert abs(chosen["crc_by_size"]["up_to_6"]["bias"]) < abs(shipped["crc_by_size"]["up_to_6"]["bias"])


def test_every_fitted_element_has_the_registered_minimum_of_molecules():
    result = json.loads((DIR / "results" / "refit2.json").read_text(encoding="utf-8"))
    for name, row in result["shipped_fit_all_rows"].items():
        assert row["value"] > 0, name
        if name != "constant":
            assert row["molecules"] >= 5, name
            assert row["weakly_determined"] == (row["molecules"] < 10), name
