"""The runner of the Psi4 agreement check (`benchmarks/psi4_agreement/run_agreement.py`): the fixed lists of `PLAN.md`, the nuisance variants of its floor, the geometry comparison, and the assembly of
records into the judge's input. Nothing here runs an engine; the runner's engine path is exercised by a smoke run (recorded in the plan's history), not by this suite.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.chem.psi4_engine import PSI4_METHODS, Psi4QuantumEngineProvider

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "psi4_agreement"
sys.path.insert(0, str(_DIRECTORY))
_spec = importlib.util.spec_from_file_location("psi4_agreement_runner", _DIRECTORY / "run_agreement.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)
judge = runner.judge


# --- the fixed lists of the plan ------------------------------------------------------------------------------------------


def test_the_plan_has_sixteen_molecules_with_their_charges_and_spins():
    assert len(runner.MOLECULES) == 16
    assert runner.MOLECULES["acetate"][1:] == (-1, 1)
    assert runner.MOLECULES["hydroxyl radical"][1:] == (0, 2)
    assert all(runner.MOLECULES[m][1:] == (0, 1) for m in runner.MOLECULES if m not in ("acetate", "hydroxyl radical"))
    assert {a for pair in runner.PAIRS for a in pair} <= set(runner.MOLECULES) and len(runner.PAIRS) == 3
    assert set(runner.FLOOR_MOLECULES) <= set(runner.MOLECULES) and len(runner.FLOOR_MOLECULES) == 6


def test_every_molecule_embeds_with_the_atoms_it_should_have():
    counts = {"water": 3, "methane": 5, "hydroxyl radical": 2, "benzene": 12, "acetate": 7}
    for name, expected in counts.items():
        assert runner.molecule(name).GetNumAtoms() == expected, name
    for name in runner.MOLECULES:
        mol = runner.molecule(name)
        assert mol.GetNumConformers() == 1 and mol.GetNumAtoms() >= 2


def test_the_grid_is_fifteen_distinct_combinations_every_engine_can_write():
    assert len(runner.GRID_COMBINATIONS) == 15 and len(set(runner.GRID_COMBINATIONS)) == 15
    water = runner.molecule("water")
    psi4, orca = Psi4QuantumEngineProvider(threads=lambda: 1), OrcaQuantumEngineProvider()
    for functional, basis in runner.GRID_COMBINATIONS:
        assert functional.lower() in PSI4_METHODS
        assert psi4.build_input(water, 0, 1, f"{functional} {basis}", "sp")
        assert orca.build_input(water, 0, 1, f"{functional} {basis}", "sp")


def test_the_job_lists_have_the_sizes_the_plan_states():
    assert len(runner.grid_jobs("orca")) == len(runner.grid_jobs("psi4")) == 240
    assert len(runner.optimize_jobs("orca")) == 16
    assert len(runner.floor_jobs("orca")) == 6 * 3 * 2 + 6 * 2
    assert len(runner.floor_jobs("psi4")) == 6 * 3 * 3 + 6 * 2
    assert len({job.key for job in runner.grid_jobs("psi4")}) == 240, "every job has its own key, so a resume cannot skip the wrong one"


# --- the nuisance variants --------------------------------------------------------------------------------------------------


def _inputs():
    water = runner.molecule("water")
    return (
        OrcaQuantumEngineProvider().build_input(water, 0, 1, "B3LYP def2-SVP", "sp"),
        OrcaQuantumEngineProvider().build_input(water, 0, 1, "B3LYP def2-SVP", "opt"),
        Psi4QuantumEngineProvider(threads=lambda: 1).build_input(water, 0, 1, "B3LYP def2-SVP", "sp"),
        Psi4QuantumEngineProvider(threads=lambda: 1).build_input(water, 0, 1, "B3LYP def2-SVP", "opt"),
    )


def test_orcas_tight_variant_adds_its_keywords_to_the_header_line_and_nothing_else():
    sp, opt, _p, _po = _inputs()

    assert runner.orca_variant(sp, "default", "sp") == sp
    tight = runner.orca_variant(sp, "tight", "sp")
    assert tight.split("\n")[0].endswith("TightSCF DefGrid3") and "TightOpt" not in tight
    assert tight.split("\n")[1:] == sp.split("\n")[1:]
    assert runner.orca_variant(opt, "tight", "opt").split("\n")[0].endswith("TightSCF DefGrid3 TightOpt")
    with pytest.raises(ValueError):
        runner.orca_variant(sp, "nonsense", "sp")


def test_psi4_variants_change_exactly_the_setting_they_name_and_keep_the_call_last():
    _o, _oo, sp, opt = _inputs()

    assert runner.psi4_variant(sp, "default", "sp") == sp and runner.psi4_variant(sp, "one_thread", "sp") == sp
    # PLAN_V2: the engine writes exact integrals, so density fitting is the (attribution-only) variant
    assert "set scf_type pk" in sp
    pk = runner.psi4_variant(sp, "df", "sp")
    assert "set scf_type df" in pk and "set scf_type pk" not in pk and pk.rstrip().endswith("energy('b3lyp5')")
    assert "pk" not in runner.PSI4_VARIANTS and "df" not in runner.PSI4_VARIANTS
    grid = runner.psi4_variant(sp, "grid", "sp")
    assert "set dft_radial_points 99" in grid and "set dft_spherical_points 590" in grid and "set e_convergence 1e-10" in grid and "1e-8" not in grid
    assert grid.rstrip().endswith("energy('b3lyp5')")
    tight = runner.psi4_variant(opt, "tight", "opt")
    assert "set g_convergence gau_tight" in tight and "set geom_maxiter 200" in tight and tight.rstrip().endswith("optimize('b3lyp5')")
    # no variant touches the molecule block
    for variant in (pk, grid, tight):
        assert variant.split("molecule {")[1].split("}")[0] == sp.split("molecule {")[1].split("}")[0]
    with pytest.raises(ValueError):
        runner.psi4_variant(sp, "nonsense", "sp")


# --- the geometry comparison ---------------------------------------------------------------------------------------------------


def _points():
    return np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]])


def test_rmsd_ignores_a_rigid_motion_and_sees_a_displacement():
    a = _points()
    theta = 0.7
    rotation = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    moved = a @ rotation.T + np.array([5.0, -3.0, 2.0])
    assert runner.kabsch_rmsd(a, moved) == pytest.approx(0.0, abs=1e-9)

    bent = a.copy()
    bent[3, 2] += 0.4
    assert 0.05 < runner.kabsch_rmsd(a, bent) < 0.25


def test_a_mirror_image_is_not_the_same_structure():
    a = _points()
    mirror = a * np.array([1.0, 1.0, -1.0])
    assert runner.kabsch_rmsd(a, mirror) > 0.1


# --- the floors and the records -----------------------------------------------------------------------------------------------


def _record(engine: str, job, energy: float, coordinates=None, commit: str = "c" * 40, dirty: bool = False) -> dict:
    record = {"key": job.key, "stage": job.stage, "engine": engine, "molecule": job.molecule, "functional": job.functional, "basis": job.basis, "variant": job.variant,
              "calc_type": job.calc_type, "commit": commit, "dirty": dirty, "completed": True, "energy_hartree": energy}
    if coordinates is not None:
        record["coordinates"] = coordinates
    return record


def _floor_records(shift_pk_hf=1e-6, shift_grid_dft=4e-5, shift_tight_orca=2e-5, opt_shift=3e-5, opt_displacement=0.002):
    base = _points().tolist()
    moved = _points()
    moved[3, 2] += opt_displacement
    orca, psi4 = [], []
    for m in runner.FLOOR_MOLECULES:
        for f, b in runner.FLOOR_COMBINATIONS:
            orca.append(_record("orca", runner.Job("floor", "orca", m, f, b, "default", "sp"), -100.0))
            orca.append(_record("orca", runner.Job("floor", "orca", m, f, b, "tight", "sp"), -100.0 + shift_tight_orca))
            psi4.append(_record("psi4", runner.Job("floor", "psi4", m, f, b, "default", "sp"), -100.0))
            psi4.append(_record("psi4", runner.Job("floor", "psi4", m, f, b, "grid", "sp"), -100.0 + (0.0 if f == "HF" else shift_grid_dft)))
            psi4.append(_record("psi4", runner.Job("floor", "psi4", m, f, b, "one_thread", "sp"), -100.0))
        for engine, records in (("orca", orca), ("psi4", psi4)):
            records.append(_record(engine, runner.Job("floor", engine, m, *runner.OPT_COMBINATION, "default", "opt"), -50.0, base))
            records.append(_record(engine, runner.Job("floor", engine, m, *runner.OPT_COMBINATION, "tight", "opt"), -50.0 + opt_shift, moved.tolist()))
    return orca, psi4


def test_the_floors_are_the_largest_changes_per_class_across_both_engines():
    orca, psi4 = _floor_records()

    floors = runner.floors_from(orca, psi4)

    # DFT: the largest of ORCA's tight (0.02 mEh) and Psi4's finer grid (0.04 mEh); HF: ORCA's tight 0.02 mEh (Psi4's variants move HF by 0)
    assert floors["dft_meh"] == pytest.approx(0.04)
    assert floors["hf_meh"] == pytest.approx(0.02)
    assert floors["opt_energy_meh"] == pytest.approx(0.03)
    assert 0.0005 < floors["rmsd_angstrom"] < 0.002  # a 0.002 A displacement of one atom of four
    # counted: DFT = ORCA tight (6 molecules x 2 DFT combinations) + Psi4 grid and one_thread (2 x 12); HF = 6 + 12; optimizations = 6 per engine
    assert floors["measurements"] == {"hf": 18, "dft": 36, "opt": 12, "expected_sp_per_variant": 18}


def test_a_floor_without_measurements_is_an_error_and_not_zero():
    with pytest.raises(ValueError):
        runner.floors_from([], [])


def test_single_point_and_optimization_records_pair_the_engines_and_mark_what_is_missing():
    orca = [_record("orca", runner.Job("grid", "orca", "water", "HF", "def2-SVP", "default", "sp"), -76.0)]
    psi4 = [_record("psi4", runner.Job("grid", "psi4", "water", "HF", "def2-SVP", "default", "sp"), -76.0001)]

    records = runner.single_point_records(orca, psi4)

    assert len(records) == 240
    water = next(r for r in records if (r["molecule"], r["functional"], r["basis"]) == ("water", "HF", "def2-SVP"))
    assert water["psi4"] - water["orca"] == pytest.approx(-0.0001)
    assert sum(1 for r in records if r["orca"] is None) == 239

    base = _points().tolist()
    opt = runner.optimization_records(
        [_record("orca", runner.Job("optimize", "orca", "water", *runner.OPT_COMBINATION, "default", "opt"), -76.3, base)],
        [_record("psi4", runner.Job("optimize", "psi4", "water", *runner.OPT_COMBINATION, "default", "opt"), -76.3001, base)],
    )
    water_opt = next(r for r in opt if r["molecule"] == "water")
    assert water_opt["rmsd"] == pytest.approx(0.0, abs=1e-9) and water_opt["psi4"] - water_opt["orca"] == pytest.approx(-0.0001)
    assert sum(1 for r in opt if r["rmsd"] is None) == 15


def test_records_from_two_commits_or_a_dirty_tree_are_refused():
    job = runner.Job("grid", "orca", "water", "HF", "def2-SVP", "default", "sp")
    one = [_record("orca", job, -1.0, commit="a" * 40)]
    two = [_record("psi4", job, -1.0, commit="b" * 40)]
    dirty = [_record("psi4", job, -1.0, commit="a" * 40, dirty=True)]

    assert runner.provenance_problem(one, one) is None
    assert "2 commits" in runner.provenance_problem(one, two)
    assert "dirty" in runner.provenance_problem(one, dirty)


def test_a_completed_job_is_never_run_again_and_a_failed_one_is_retried(tmp_path):
    ctx = runner.Context(tmp_path, cores=1, workers=1)
    job = runner.Job("grid", "orca", "water", "HF", "def2-SVP", "default", "sp")

    assert not ctx.done(job)
    ctx.append(job, {"key": job.key, "completed": False, "error": "timeout"})
    assert not ctx.done(job), "a failed attempt is retried"
    ctx.append(job, {"key": job.key, "completed": True, "energy_hartree": -1.0})
    assert ctx.done(job)
    assert [json.loads(line)["completed"] for line in ctx.path("grid", "orca").read_text(encoding="utf-8").splitlines()] == [False, True]


def test_a_perfect_agreement_end_to_end_through_the_judge_passes():
    """Every cell identical in the two engines and the floors synthetic: the whole chain from records to a verdict."""
    orca_floor, psi4_floor = _floor_records()
    tol = runner.tolerances_from(runner.floors_from(orca_floor, psi4_floor))
    grid_o = [_record("orca", j, -100.0 - i * 0.1) for i, j in enumerate(runner.grid_jobs("orca"))]
    grid_p = [_record("psi4", j, -100.0 - i * 0.1) for i, j in enumerate(runner.grid_jobs("psi4"))]
    base = _points().tolist()
    opt_o = [_record("orca", j, -50.0, base) for j in runner.optimize_jobs("orca")]
    opt_p = [_record("psi4", j, -50.0, base) for j in runner.optimize_jobs("psi4")]

    verdict, _why = judge.judge(runner.single_point_records(grid_o, grid_p), runner.optimization_records(opt_o, opt_p), runner.PAIRS, tol)

    assert verdict == judge.PASS
