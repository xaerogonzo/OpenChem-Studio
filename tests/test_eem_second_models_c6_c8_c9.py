"""The arithmetic of `benchmarks/charges/models/eem_second_models_c6_c8_c9.py` and the committed result it writes (checks C6, C8 and C9 of the plan).

The runner is loaded BY PATH under its own name (a bare import of a benchmark script has returned another benchmark's file before). The measurements themselves are not
re-run here (they embed about 1,100 molecules); what is held is that the summary of the spread is the arithmetic it says, and that the committed result says what the plan's
result section quotes.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULT = ROOT / "benchmarks" / "charges" / "models" / "eem_second_models_results" / "c6_c8_c9.json"


def _runner():
    path = ROOT / "benchmarks" / "charges" / "models" / "eem_second_models_c6_c8_c9.py"
    spec = importlib.util.spec_from_file_location("eem_second_models_c6_c8_c9_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_c9_summary_is_the_spread_between_the_four_models_atom_by_atom():
    runner = _runner()
    rows = [
        {"smiles": "O", "source": "x", "elements": ["O", "H"], "J": [-0.5, 0.25], "N": [-0.7, 0.35], "Bultinck": [-0.6, 0.30], "IonescuE": [-0.9, 0.45]},
        {"smiles": "C", "source": "x", "elements": ["C"], "J": [0.0], "N": [0.1], "Bultinck": [0.05], "IonescuE": [-0.05]},
    ]
    summary = runner.summarise_c9(rows)
    assert summary["molecules"] == 2 and summary["atoms"] == 3
    assert summary["spread_by_element"]["O"]["mean"] == pytest.approx(0.4)  # largest -0.5 minus smallest -0.9
    assert summary["spread_by_element"]["H"]["max"] == pytest.approx(0.20)
    assert summary["spread_by_element"]["C"]["mean"] == pytest.approx(0.15)
    assert summary["mean_charge_by_model_and_element"]["N"]["O"] == pytest.approx(-0.7)
    assert summary["mean_abs_difference_between_pairs"]["J-N"] == pytest.approx((0.2 + 0.1 + 0.1) / 3)


def test_the_committed_result_says_what_the_plan_quotes():
    data = json.loads(RESULT.read_text(encoding="utf-8"))
    n, j = "neemp2016_ccd_gen_npa", "jirouskova2009_b3lyp_mk"
    assert data["bluebook_molecules"] == 1108 and data["census_molecules"] == 24
    # C8: the tail of Model N is oxidised sulfur and phosphorus and nothing else above 1.5 e
    over = data["c8"][n]["atoms_over_by_type"]
    assert set(over["1.5"]) == {"S2", "P2"} and set(over["2.0"]) == {"S2", "P2"}
    assert data["c8"][n]["max_abs_charge"] > 2.5 and data["c8"][j]["max_abs_charge"] < 1.1
    assert data["c8"][n]["covered_molecules"] > data["c8"][j]["covered_molecules"]
    # C6: both models, enough molecules, and the largest change stays below 0.1 e
    for model in (n, j):
        assert data["c6"][model]["molecules"] >= 20 and data["c6"][model]["max_all"] < 0.1
    # C9: four models on the same atoms
    assert data["c9"]["molecules"] > 500
    assert set(data["c9"]["mean_charge_by_model_and_element"]) == {"J", "N", "Bultinck", "IonescuE"}
