"""Frozen decision rules of the CNNaffinity ranking-power test."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_DIR = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pose = _load("gnina_core", "gnina_core.py")
core = _load("cnn_affinity_core", "cnn_affinity_core.py")


def test_ranking_twelve_split_on_the_same_crossdocked_index():
    assert sum(core.SERIES_PER_PDB.values()) == 77
    assert core.n_series(sorted(core.RANKING_PDBS)) == 77
    deciding = core.deciding_pdbs()
    overlap = core.overlap_pdbs()
    assert set(deciding) | set(overlap) == core.RANKING_PDBS
    assert set(deciding) & set(overlap) == set()
    assert deciding == ("1ERE", "3HS4", "5I6X", "5TGZ", "6WGT")
    assert core.n_series(deciding) == 35
    assert core.n_series(overlap) == 42
    assert core.TRAINING_OVERLAP == pose.TRAINING_OVERLAP


def test_representative_is_a_real_replicate_not_an_average():
    runs = [(1, -8.2), (2, -8.0), (3, -7.8), (4, -7.4), (5, -7.1), (6, -6.9)]
    assert core.representative_value([s for _, s in runs]) == -7.4
    assert core.representative_replicate(runs) == 4


def test_tied_representative_picks_the_lowest_replicate_index():
    runs = [(0, -8.2), (1, -8.0), (2, -7.8), (3, -7.4), (4, -7.4), (5, -6.9)]
    assert core.representative_value([s for _, s in runs]) == -7.4
    assert core.representative_replicate(runs) == 3


def test_delta_rho_uses_the_same_ligands_on_both_sides():
    vina = [-8.0, -7.0, -6.0, -5.0, -4.0, -3.0]
    cnn = [8.0, 7.0, 6.0, 5.0, 4.0, None]
    pchembl = [9.0, 8.0, 7.0, 6.0, 5.0, 4.0]
    paired = core.paired_delta_rho(vina, cnn, pchembl)
    assert len([c for c in cnn if c is not None]) == 5
    assert len(vina) == 6
    assert paired is not None


def test_below_min_series_after_pairing_is_dropped():
    vina = [-8.0, -7.0, -6.0, -5.0]
    cnn = [8.0, 7.0, None, None]
    pchembl = [9.0, 8.0, 7.0, 6.0]
    assert core.paired_delta_rho(vina, cnn, pchembl) is None


def test_cnn_affinity_is_not_negated():
    vina = [-1.0, -2.0, -3.0, -4.0, -5.0]
    cnn = [5.0, 4.0, 3.0, 2.0, 1.0]
    pchembl = [5.0, 4.0, 3.0, 2.0, 1.0]
    delta = core.paired_delta_rho(vina, cnn, pchembl)
    assert delta is not None and delta > 0
    assert core.CNN_AFFINITY_HIGHER_IS_BETTER is True
    assert core.cnn_sign_is_predeclared(True) is True
    assert core.cnn_sign_is_predeclared(False) is False


def test_verdict_and_integration_gate():
    assert core.verdict((0.01, 0.20), dropped=0, n_deciding=35) == "PASS"
    assert core.verdict((-0.05, 0.05), dropped=0, n_deciding=35) == "NULL"
    assert core.verdict((-0.20, -0.01), dropped=0, n_deciding=35) == "HARMFUL"
    assert core.verdict((0.01, 0.20), dropped=6, n_deciding=35) == "NULL"
    assert core.integration_eligible("PASS", (0.01, 0.2)) is True
    assert core.integration_eligible("PASS", (-0.01, 0.2)) is False
    assert core.integration_eligible("NULL", (0.01, 0.2)) is False


def test_help_must_name_the_frozen_ensemble():
    text = "default cnn: dense_1_3 dense_1_3_PT_KD_3 crossdock_default2018_KD_4"
    assert core.help_names_default_ensemble(text) is True
    assert core.help_names_default_ensemble("dense_1_3 only") is False
    assert core.SCORE_ONLY is True
    assert core.CNN_ENSEMBLE == (
        "dense_1_3",
        "dense_1_3_PT_KD_3",
        "crossdock_default2018_KD_4",
    )
