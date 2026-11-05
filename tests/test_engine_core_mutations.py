"""In-process mutations of `engine_core.py` gate rules.

Each arm copies the source, asserts the needle is unique, loads the mutant, and
checks that a fixture the unmutated module judges one way is judged the other.
A missing or non-unique needle is a failure, not a silent skip. No live file
is rewritten.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking" / "engine_core.py"
_SOURCE = _PATH.read_text(encoding="utf-8").replace("\r\n", "\n")

_spec = importlib.util.spec_from_file_location("engine_core_baseline", _PATH)
baseline = importlib.util.module_from_spec(_spec)
sys.modules["engine_core_baseline"] = baseline
_spec.loader.exec_module(baseline)


def _load(text: str, name: str):
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(text, name, "exec"), module.__dict__)
    return module


def _mutant(needle: str, replacement: str, name: str):
    count = _SOURCE.count(needle)
    assert count == 1, f"{name}: needle count {count} (need 1): {needle!r}"
    return _load(_SOURCE.replace(needle, replacement, 1), name)


def test_unmutated_gate_boundaries_are_alive():
    """The mutant probes are meaningless if the baseline already agrees with them."""
    g1_edge = baseline.gate_g1_reproduces_survey(
        [("7B6W", 1.41)], [("7B6W", 1.46)]
    )
    g1_over = baseline.gate_g1_reproduces_survey(
        [("7B6W", 1.41)], [("7B6W", 1.47)]
    )
    assert g1_edge.passed is True
    assert g1_over.passed is False
    assert baseline.gate_g2_same_function([0.01]).passed is True
    assert baseline.gate_g2_same_function([0.011]).passed is False
    assert baseline.gate_g4_coverage({"vina": 43}).passed is False
    assert baseline.gate_g4_coverage({"vina": 44}).passed is True
    assert baseline.gate_g4_paired_drops(4).passed is False
    assert baseline.gate_g5_for_arm("vina", 15 / 17).passed is False
    assert baseline.crystal_score_favorable(0.0) is False
    assert baseline.gate_g3_reproducible(["differ"]).passed is False
    assert (
        baseline.overall_verdict(
            [baseline.GateResult("G1", False, "bad")],
            {"smina-vinardo": "PASS"},
        )
        == "INCONCLUSIVE"
    )
    assert baseline.candidate_verdict(baseline.Tally(10, 5, 0, 5)) == "NULL"
    assert baseline.arm_correct((True, False, False)) is False


def _g1_over(mod):
    return mod.gate_g1_reproduces_survey([("7B6W", 1.41)], [("7B6W", 1.47)])


def _g1_edge(mod):
    return mod.gate_g1_reproduces_survey([("7B6W", 1.41)], [("7B6W", 1.46)])


@pytest.mark.parametrize(
    "name, needle, replacement, killed",
    [
        (
            "g1_tol_loose",
            "G1_DISTANCE_TOL = 0.05",
            "G1_DISTANCE_TOL = 0.10",
            lambda m: _g1_over(m).passed is True,
        ),
        (
            "g1_inclusive_compare",
            "delta_centia(rec[pdb], meas) > limit_centia",
            "delta_centia(rec[pdb], meas) >= limit_centia",
            lambda m: _g1_edge(m).passed is False,
        ),
        (
            "g2_tol_loose",
            "G2_SCORE_TOL = 0.01",
            "G2_SCORE_TOL = 0.02",
            lambda m: m.gate_g2_same_function([0.011]).passed is True,
        ),
        (
            "g2_exclusive_compare",
            "        worst <= tol,\n",
            "        worst < tol,\n",
            lambda m: m.gate_g2_same_function([0.01]).passed is False,
        ),
        (
            "g3_always_pass",
            'return GateResult("G3", not failures,',
            'return GateResult("G3", True,',
            lambda m: m.gate_g3_reproducible(["differ"]).passed is True,
        ),
        (
            "g4_min_low",
            "G4_MIN_DOCKED = 44",
            "G4_MIN_DOCKED = 43",
            lambda m: m.gate_g4_coverage({"vina": 43}).passed is True,
        ),
        (
            "g4_drops_high",
            "G4_MAX_DROPPED = 3",
            "G4_MAX_DROPPED = 4",
            lambda m: m.gate_g4_paired_drops(4).passed is True,
        ),
        (
            "g5_vina_low",
            '"vina": 16 / 17,',
            '"vina": 15 / 17,',
            lambda m: m.gate_g5_for_arm("vina", 15 / 17).passed is True,
        ),
        (
            "g5_zero_counts",
            "return math.isfinite(score) and score < 0.0",
            "return math.isfinite(score) and score <= 0.0",
            lambda m: m.crystal_score_favorable(0.0) is True,
        ),
        (
            "g5_exclusive_fraction",
            "ok = favorable_fraction >= min_fraction",
            "ok = favorable_fraction > min_fraction",
            lambda m: m.gate_g5_for_arm("vina", 16 / 17).passed is False,
        ),
        (
            "overall_skips_failed_gate",
            "if first_failed_gate(gates):",
            "if False:",
            lambda m: m.overall_verdict(
                [m.GateResult("G1", False, "bad")],
                {"smina-vinardo": "PASS"},
            )
            == "PASS",
        ),
        (
            "alpha_unbonferroni",
            "ALPHA = 0.05 / len(CANDIDATE_ARMS)",
            "ALPHA = 0.05",
            lambda m: m.candidate_verdict(m.Tally(10, 5, 0, 5)) == "PASS",
        ),
        (
            "majority_one_seed",
            "SEEDS_REQUIRED = 2",
            "SEEDS_REQUIRED = 1",
            lambda m: m.arm_correct((True, False, False)) is True,
        ),
    ],
)
def test_gate_rule_mutation_is_killed(name, needle, replacement, killed):
    mutant = _mutant(needle, replacement, f"engine_core_{name}")
    assert killed(mutant), f"survivor: {name}"
