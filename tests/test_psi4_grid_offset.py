"""The grid-offset experiment (`benchmarks/psi4_agreement/run_grid_offset.py`, `PLAN_GRID_OFFSET.md`): the fixed cell lists and the reading rule, tested on synthetic records. Nothing here runs an engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "psi4_agreement"
sys.path.insert(0, str(_DIRECTORY))
_spec = importlib.util.spec_from_file_location("psi4_grid_offset_runner", _DIRECTORY / "run_grid_offset.py")
go = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = go
_spec.loader.exec_module(go)
ra = go.ra


def _records(offset_default: float, shift_psi4: float, shift_orca: float, hf_move: float = 0.0, skip=()) -> tuple[list[dict], list[dict]]:
    """Synthetic records (Hartree) for every cell: ORCA at -100, Psi4 offset by `offset_default` mEh at the default grids, each program shifted by its own grid shift (mEh) at the finer one."""
    orca, psi4 = [], []
    cells = [(m, f, b) for m in go.MOLECULES for f, b in go.DFT_COMBINATIONS] + go.HF_CONTROLS
    for m, f, b in cells:
        hf = f == "HF"
        for engine, records, levels, base, shift in (
            ("orca", orca, go.LEVELS["orca"], -100.0, hf_move if hf else shift_orca),
            ("psi4", psi4, go.LEVELS["psi4"], -100.0 + (0.0 if hf else offset_default / 1000.0), hf_move if hf else shift_psi4),
        ):
            for variant, extra in ((levels[0], 0.0), (levels[1], shift / 1000.0)):
                if (m, f, b, variant, engine) in skip:
                    continue
                records.append({"molecule": m, "functional": f, "basis": b, "variant": variant, "completed": True, "energy_hartree": base + extra})
    return orca, psi4


def _verdict(**kwargs) -> tuple[str, list[str]]:
    orca, psi4 = _records(**kwargs)
    return go.judge_cells(go.cells_from(orca, psi4))


def test_the_job_lists_are_the_cells_of_the_plan():
    assert go.MOLECULES == ["dimethyl ether", "fluorobenzene", "benzene", "dimethyl sulfoxide", "propanal", "water"]
    for engine in ("orca", "psi4"):
        listed = go.jobs(engine)
        assert len(listed) == (6 * 4 + 2) * 2 == 52
        assert len({j.key for j in listed}) == 52 and all(j.stage == go.STAGE and j.calc_type == "sp" for j in listed)
        assert {j.variant for j in listed} == set(go.LEVELS[engine])
    assert {m for m in go.MOLECULES} <= set(ra.MOLECULES)


def test_the_finer_variants_are_the_ones_the_runner_defines():
    sp = "set scf_type pk\nset e_convergence 1e-8\nenergy('b3lyp5')\n"
    assert "set dft_spherical_points 590" in ra.psi4_variant(sp, "grid", "sp")
    assert "DefGrid3" in ra.orca_variant("! B3LYP def2-SVP\n", "tight", "sp")


def test_an_offset_that_vanishes_on_a_fine_grid_is_the_grid():
    # Psi4's own finer grid removes the whole offset: the offset was Psi4's default grid
    verdict, _ = _verdict(offset_default=0.4, shift_psi4=-0.4, shift_orca=0.0)

    assert verdict == "GRID EXPLAINS"


def test_an_offset_that_vanishes_when_orcas_grid_is_made_finer_is_also_the_grid():
    # ORCA's energy rises by 0.4 mEh on its finer grid and meets Psi4's default: the offset was ORCA's default grid (a mutation that ignored ORCA's own shift survived without this)
    verdict, _ = _verdict(offset_default=0.4, shift_psi4=0.0, shift_orca=0.4)

    assert verdict == "GRID EXPLAINS"


def test_an_offset_that_a_fine_grid_does_not_touch_is_not_the_grid():
    verdict, _ = _verdict(offset_default=0.4, shift_psi4=0.01, shift_orca=0.01)

    assert verdict == "NOT THE GRID"


def test_an_offset_that_is_partly_removed_is_partial():
    # 0.4 -> 0.25: not within T_DFT of zero, and not unchanged (0.25 is below 0.75 x 0.4 = 0.3)
    verdict, _ = _verdict(offset_default=0.4, shift_psi4=-0.15, shift_orca=0.0)

    assert verdict == "PARTIAL"


def test_each_programs_shift_enters_the_offset_with_its_own_sign():
    # ORCA's finer grid moving DOWN by 0.4 mEh raises Psi4 - ORCA by 0.4: the offset doubles, which is not an explanation
    verdict, _ = _verdict(offset_default=0.4, shift_psi4=0.0, shift_orca=-0.4)

    assert verdict == "NOT THE GRID"


def test_a_hartree_fock_control_that_moves_invalidates_the_run():
    verdict, why = _verdict(offset_default=0.4, shift_psi4=-0.4, shift_orca=0.0, hf_move=0.05)

    assert verdict == "NOT VALID" and any("Hartree-Fock control" in line for line in why)


def test_an_offset_that_does_not_reproduce_invalidates_the_run():
    verdict, why = _verdict(offset_default=0.05, shift_psi4=0.0, shift_orca=0.0)

    assert verdict == "NOT VALID" and any("did not reproduce" in line for line in why)


def test_a_few_missing_runs_are_tolerated_and_many_are_not():
    # two cells lacking a run: 22 of 24 remain, the rule still applies
    two = {("dimethyl ether", "M062X", "def2-SVP", "grid", "psi4"), ("benzene", "B3LYP", "def2-TZVP", "tight", "orca")}
    assert _verdict(offset_default=0.4, shift_psi4=-0.4, shift_orca=0.0, skip=two)[0] == "GRID EXPLAINS"
    three = two | {("propanal", "M062X", "def2-TZVP", "grid", "psi4")}
    verdict, why = _verdict(offset_default=0.4, shift_psi4=-0.4, shift_orca=0.0, skip=three)
    assert verdict == "NOT EVALUABLE" and "21 of 24" in why[0]
    # a missing Hartree-Fock control cannot be waived: the pipeline would be unchecked
    assert _verdict(offset_default=0.4, shift_psi4=-0.4, shift_orca=0.0, skip={("water", "HF", "def2-SVP", "grid", "psi4")})[0] == "NOT EVALUABLE"


def test_the_thresholds_are_the_plans():
    assert go.T_DFT_MEH == pytest.approx(0.126) and go.T_CELL_MEH == pytest.approx(0.252) and go.HF_CONTROL_MEH == 0.01
    assert (go.MIN_OFFSET_MEH, go.EXPLAINED_SHARE, go.HALVED, go.UNCHANGED, go.MIN_DFT_CELLS) == (0.1, 0.8, 0.5, 0.75, 22)
