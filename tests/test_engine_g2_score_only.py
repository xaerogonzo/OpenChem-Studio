"""G2 receptor selection and pose splitting (no docking)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"
sys.path.insert(0, str(_PATH))

import engine_core as core  # noqa: E402
import engine_g2_score_only as g2  # noqa: E402
import engine_pilot as pilot  # noqa: E402


def test_g2_receptors_are_the_first_five_of_the_pilot_list():
    names = g2.g2_receptors()
    assert names == tuple(pilot.pilot_receptors()[: core.G2_RECEPTOR_COUNT])
    assert len(names) == 5
    assert len(set(names)) == 5


def test_vina_pose_blocks_split_model_records():
    text = "MODEL 1\nATOM     1  C   UNL     1       0.000   0.000   0.000  0.00  0.00    +0.000 C\nENDMDL\nMODEL 2\nATOM     1  C   UNL     1       1.000   0.000   0.000  0.00  0.00    +0.000 C\nENDMDL\n"
    blocks = g2.vina_pose_blocks(text)
    assert len(blocks) == 2
    assert "1.000" in blocks[1]
