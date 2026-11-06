"""The committed result of `eem_boron_probe.py` against the rule registered in section 14 of the plan, so the stated verdict cannot drift from the numbers."""

from __future__ import annotations

import json
import pathlib

RESULT = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "charges" / "models" / "eem_second_models_results" / "boron_probe.json"


def test_the_probe_fails_the_registered_rule_on_the_worst_boron_atom_only():
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    mean_ok = result["leave_one_out_mean_heavy_error"] <= 0.20
    worst_ok = result["leave_one_out_worst_boron_error"] <= 0.5
    spread_ok = all(result["parameter_spread_over_loo"][k] <= 0.10 * abs(v) for k, v in zip("AB", result["fit_all"], strict=True))
    assert (mean_ok, worst_ok, spread_ok) == (True, False, True)


def test_boron_is_still_refused_by_both_models():
    from openchem.chem import typed_eem as te

    for model in te.MODELS:
        assert "B1" not in te.parameters()[model]["types"], model
