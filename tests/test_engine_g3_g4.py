"""G3 receptor pin and G4 success rule (no docking)."""

from __future__ import annotations

import sys
from pathlib import Path

_PATH = Path(__file__).parents[1] / "benchmarks" / "docking"
sys.path.insert(0, str(_PATH))

import engine_g3_repro as g3  # noqa: E402
import engine_g4_coverage as g4  # noqa: E402
from engine_g2_score_only import g2_receptors  # noqa: E402


def test_g3_receptor_is_in_the_g2_five():
    assert g3.G3_RECEPTOR == "7E2Y"
    assert g3.G3_RECEPTOR in g2_receptors()


def test_g4_dock_ok_rejects_setup_and_empty_poses():
    assert g4.dock_ok({"outcome": "top pose correct", "poses": [{"rmsd": 0.5}]}) is True
    assert g4.dock_ok({"outcome": "setup: ligand", "poses": []}) is False
    assert g4.dock_ok({"outcome": "top pose correct", "poses": []}) is False
