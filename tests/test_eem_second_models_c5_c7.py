"""The judge of `benchmarks/charges/models/eem_second_models_c5_c7.py` (checks C5 and C7) and the committed result. The ORCA runs themselves are not repeated here."""

from __future__ import annotations

import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIR = ROOT / "benchmarks" / "charges" / "models"


def _runner():
    spec = importlib.util.spec_from_file_location("eem_second_models_c5_c7_under_test", DIR / "eem_second_models_c5_c7.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unit_needs_a_clear_winner_else_stays_angstrom():
    r = _runner()
    assert r.judge_unit(0.30, 0.10)["unit"] == "bohr" and r.judge_unit(0.30, 0.10)["discriminated"]
    assert r.judge_unit(0.10, 0.30)["unit"] == "angstrom" and r.judge_unit(0.10, 0.30)["discriminated"]
    close = r.judge_unit(0.20, 0.22)
    assert close["unit"] == "angstrom" and not close["discriminated"]
    assert r.judge_unit(0.15, 0.10)["discriminated"] is False  # ratio 1.5 minus a hair is not enough


def test_oxidised_rule_counts_molecules_over_the_threshold():
    r = _runner()
    assert r.judge_oxidised([0.6, -0.7, 0.8], threshold=0.5, needed=3)["rule_says_refuse"]
    assert not r.judge_oxidised([0.6, -0.7, 0.4], threshold=0.5, needed=3)["rule_says_refuse"]
    assert r.judge_oxidised([0.5], threshold=0.5, needed=1)["over_threshold"] == 0  # not strictly over


def test_committed_result_says_what_the_plan_quotes():
    d = json.loads((DIR / "eem_second_models_results" / "c5_c7.json").read_text(encoding="utf-8"))
    assert d["c5"]["J"]["verdict"]["unit"] == "angstrom" and d["c5"]["J"]["verdict"]["discriminated"]
    assert not d["c5"]["N"]["verdict"]["discriminated"]
    assert d["c7"]["S2"]["vs_chelpg"]["over_threshold"] == 9 and d["c7"]["P2"]["vs_chelpg"]["over_threshold"] == 4
    assert d["c7"]["S2"]["vs_chelpg"]["rule_says_refuse"] and d["c7"]["P2"]["vs_loewdin"]["rule_says_refuse"]
