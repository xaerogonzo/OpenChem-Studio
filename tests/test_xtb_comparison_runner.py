"""The runner of the xtb comparison (`benchmarks/xtb_comparison/run_comparison.py`): the fixed lists of `PREREGISTRATION.md`, the conformer rule, the floor variants, and the assembly of records into the judge's input.

Nothing here runs an engine: the runner's engine path is not exercised before the freeze (no job may be run first). The assembly is tested on synthetic records built from the real start geometries.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from rdkit import Chem

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "xtb_comparison"
_spec = importlib.util.spec_from_file_location("xtb_comparison_runner", _DIRECTORY / "run_comparison.py")
runner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = runner
_spec.loader.exec_module(runner)
judge = runner.judge


def test_the_runner_loads_its_own_judge_whatever_another_benchmark_put_in_sys_modules(monkeypatch):
    import types

    monkeypatch.setitem(sys.modules, "judge", types.ModuleType("judge"))
    spec = importlib.util.spec_from_file_location("xtb_comparison_runner_again", _DIRECTORY / "run_comparison.py")
    again = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, again)
    spec.loader.exec_module(again)

    assert again.judge.__name__ == "xtb_comparison_judge" and hasattr(again.judge, "judge_geometry")


# --- the fixed lists --------------------------------------------------------------------------------------------------------


def test_the_sets_are_the_ones_the_preregistration_names():
    assert len(runner.SET_S) == 16 and len(runner.SET_M) == 6 and len(runner.SET_F) == 5
    assert runner.SET_S["acetate"][1:] == (-1, 1) and runner.SET_S["hydroxyl radical"][1:] == (0, 2)
    assert set(runner.REPORTED_ONLY) == {"acetate", "hydroxyl radical"}
    # 14 neutral closed-shell molecules of S + the 6 of M are judged
    assert len(runner.JUDGED) == 20 and not set(runner.REPORTED_ONLY) & set(runner.JUDGED)
    assert all(runner.ALL_STRUCTURES[m][1:] == (0, 1) for m in runner.JUDGED)
    assert {a for pair in runner.PAIRS for a in pair} <= set(runner.SET_S) and len(runner.PAIRS) == 3
    assert set(runner.FLOOR_MOLECULES) <= set(runner.SET_S) and len(runner.FLOOR_MOLECULES) == 6
    assert (runner.SEED, runner.CONFORMER_EMBEDDINGS, runner.CONFORMER_PRUNE_RMSD, runner.CONFORMERS_KEPT) == (7, 300, 0.3, 6)
    assert (runner.PRIMARY, runner.ENERGY_REFERENCE, runner.XTB_METHOD) == ("B3LYP def2-SVP", "B3LYP def2-TZVP D3BJ", "GFN2-xTB")


def test_every_listed_molecule_parses_embeds_and_has_a_valid_electron_count_for_xtb():
    from openchem.chem.xtb_engine import XtbQuantumEngineProvider

    provider = XtbQuantumEngineProvider(threads=lambda: 1)
    for name, (smiles, charge, multiplicity) in runner.ALL_STRUCTURES.items():
        mol = runner.molecule(name)
        assert mol.GetNumConformers() == 1 and Chem.MolFromSmiles(smiles) is not None, name
        provider.build_input(mol, charge, multiplicity, "GFN2-xTB", "opt")  # refuses an impossible electron count


def test_the_molecules_are_the_same_every_time():
    a, b = runner.molecule("aspirin"), runner.molecule("aspirin")
    assert np.allclose(a.GetConformer().GetPositions(), b.GetConformer().GetPositions())


# --- the conformer rule -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(runner.SET_F))
def test_the_conformers_follow_the_rule(name):
    mols = runner.conformer_mols(name)
    assert 1 <= len(mols) <= runner.CONFORMERS_KEPT
    assert all(m.GetNumConformers() == 1 for m in mols)
    again = runner.conformer_mols(name)
    assert all(np.allclose(x.GetConformer().GetPositions(), y.GetConformer().GetPositions()) for x, y in zip(mols, again, strict=True))
    from rdkit.Chem import rdMolAlign

    for i in range(len(mols)):
        for j in range(i):
            assert rdMolAlign.GetBestRMS(Chem.Mol(mols[i]), Chem.Mol(mols[j])) >= runner.CONFORMER_PRUNE_RMSD - 1e-9, "two kept conformers closer than the pruning RMSD"


def test_the_conformer_stage_is_built_from_exactly_those_conformers():
    structures = runner.conformer_structures()
    assert len(structures) == sum(len(runner.conformer_mols(n)) for n in runner.SET_F) and all("#" in s for s in structures)
    assert runner.split_structure("glycine#3") == ("glycine", 3) and runner.split_structure("aspirin") == ("aspirin", None)
    assert runner.charge_spin("glycine#3") == (0, 1) and runner.charge_spin("acetate") == (-1, 1)


# --- the stages -------------------------------------------------------------------------------------------------------------


def test_each_stage_lists_the_jobs_of_its_section_and_keys_are_unique():
    jobs = {name: make() for name, make in runner.STAGES.items()}
    assert len(jobs["floor"]) == 6 * 2 + 6 * 4
    assert len(jobs["geometry"]) == 22 * 2 + 16  # ORCA and xtb on S and M, Psi4 on S only
    assert len(jobs["preopt"]) == 22 and all(j.start == "xtb" and j.engine == "orca" for j in jobs["preopt"])
    assert len(jobs["gfn1"]) == 20 and all(j.method == "GFN1-xTB" for j in jobs["gfn1"])
    n = len(runner.conformer_structures())
    assert len(jobs["conformers"]) == 2 * n and len(jobs["reference"]) == 2 * (len(runner.PAIR_MOLECULES) + n)
    assert all(j.start == "orca" and j.calc_type == "sp" for j in jobs["reference"])
    assert {j.method for j in jobs["reference"] if j.engine == "orca"} == {"B3LYP def2-TZVP D3BJ"}
    for stage_jobs in jobs.values():
        assert len({j.key for j in stage_jobs}) == len(stage_jobs)
    assert not any(j.engine == "psi4" for stage in ("floor", "conformers", "reference", "preopt", "gfn1") for j in jobs[stage])


def test_the_listing_command_runs_nothing(capsys):
    assert runner.main(["list"]) == 0
    printed = capsys.readouterr().out
    assert "geometry" in printed and "preopt" in printed


# --- the variants and the readers -------------------------------------------------------------------------------------------


def test_the_orca_tight_variant_only_adds_tightopt_to_an_optimization():
    text = "! B3LYP def2-SVP Opt\n* xyz 0 1\nH 0 0 0\n*\n"
    assert runner.orca_variant(text, "default", "opt") == text
    assert runner.orca_variant(text, "tight", "opt").split("\n")[0] == "! B3LYP def2-SVP Opt TightOpt"
    with pytest.raises(ValueError):
        runner.orca_variant(text, "tight", "sp")
    with pytest.raises(ValueError):
        runner.orca_variant(text, "bogus", "opt")


def test_the_xtb_variants_change_only_the_optimization_level():
    base = ["xtb.exe", "job.inp", "--gfn", "2", "--chrg", "0", "--uhf", "0", "-P", "4", "--opt", "tight"]
    assert runner.xtb_args(base, "vtight")[-2:] == ["--opt", "vtight"] and runner.xtb_args(base, "vtight")[:-2] == base[:-2]
    for variant in ("default", "one_thread", "repeat"):
        assert runner.xtb_args(base, variant) == base
    assert runner.xtb_args(["x", "--ohess", "tight"], "vtight") == ["x", "--ohess", "vtight"]
    with pytest.raises(ValueError):
        runner.xtb_args(base, "bogus")


def test_optimization_cycles_are_read_from_the_orca_output():
    fixture = Path(__file__).parent / "fixtures" / "orca" / "bde_hcn_parent_optfreq.out"
    text = fixture.read_text(encoding="utf-8", errors="replace")
    expected = max(int(n) for n in __import__("re").findall(r"GEOMETRY OPTIMIZATION CYCLE\s+(\d+)", text))
    assert runner.optimization_cycles(text) == expected >= 2
    assert runner.optimization_cycles("no optimization here") is None


def test_the_rmsd_helpers_ignore_a_rigid_move_and_see_a_real_one():
    mol = runner.molecule("ethanol")
    pos = mol.GetConformer().GetPositions()
    theta = 0.7
    rotation = np.array([[np.cos(theta), -np.sin(theta), 0], [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    moved = pos @ rotation.T + np.array([3.0, -1.0, 2.0])
    assert runner.kabsch_rmsd(pos, moved) == pytest.approx(0.0, abs=1e-9)
    assert runner.heavy_rmsd(mol, pos.tolist(), moved.tolist()) == pytest.approx(0.0, abs=1e-9)
    assert runner.bond_mad(mol, pos.tolist(), moved.tolist()) == pytest.approx(0.0, abs=1e-9)
    stretched = pos.copy()
    stretched[2] += np.array([0.0, 0.0, 0.5])  # move the oxygen
    assert runner.heavy_rmsd(mol, pos.tolist(), stretched.tolist()) > 0.05 and runner.bond_mad(mol, pos.tolist(), stretched.tolist()) > 0.0
    with pytest.raises(ValueError):
        runner.with_coordinates(mol, pos.tolist()[:-1])


# --- assembling records into the judge's input ------------------------------------------------------------------------------


def _write(ctx, stage, engine, rows):
    path = ctx.path(stage, engine)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _record(job, energy, coordinates=None, cycles=None, seconds=10.0, commit="c1", dirty=False):
    record = {"key": job.key, "stage": job.stage, "engine": job.engine, "structure": job.structure, "method": job.method, "calc_type": job.calc_type, "start": job.start,
              "variant": job.variant, "commit": commit, "dirty": dirty, "completed": True, "energy_hartree": energy, "seconds": seconds}
    if coordinates is not None:
        record["coordinates"] = coordinates
    if cycles is not None:
        record["cycles"] = cycles
    return record


@pytest.fixture
def ctx(tmp_path):
    return runner.Context(tmp_path / "out", cores=1, workers=1)


def _coords(name, shift=0.0):
    pos = runner.molecule(name).GetConformer().GetPositions()
    pos = pos.copy()
    pos[0] += shift
    return pos.tolist()


def _fill_geometry(ctx, shift_xtb=0.01, skip: set[str] = frozenset()):
    for job in runner.geometry_jobs():
        if job.structure in skip and job.engine == "orca":
            continue
        shift = shift_xtb if job.engine == "xtb" else 0.0
        _write(ctx, "geometry", job.engine, [_record(job, -100.0 - len(job.structure) / 1000.0, _coords(job.structure, shift), cycles=12, seconds=100.0 if job.engine == "orca" else 5.0)])


def test_geometry_rows_pair_the_xtb_and_orca_structures_of_every_judged_molecule(ctx):
    _fill_geometry(ctx)
    rows = runner.geometry_rows(ctx)
    assert [r["molecule"] for r in rows] == runner.JUDGED and all(r["heavy_rmsd"] is not None and r["heavy_rmsd"] < 0.02 for r in rows)
    assert judge.judge_geometry(rows, judge.Floors(0.01, 0.001)).verdict == judge.PASS


def test_a_missing_reference_structure_is_a_missing_cell_not_a_dropped_molecule(ctx):
    _fill_geometry(ctx, skip={"aspirin"})
    rows = runner.geometry_rows(ctx)
    assert len(rows) == 20 and next(r for r in rows if r["molecule"] == "aspirin")["heavy_rmsd"] is None


def test_preopt_rows_add_the_xtb_seconds_to_the_orca_run_from_the_xtb_start(ctx):
    _fill_geometry(ctx)
    for job in runner.preopt_jobs():
        _write(ctx, "preopt", "orca", [_record(job, -100.0 - len(job.structure) / 1000.0, cycles=6, seconds=40.0)])
    rows = runner.preopt_rows(ctx)
    row = next(r for r in rows if r["molecule"] == "aspirin")
    assert row["cycles_mmff"] == 12 and row["cycles_xtb"] == 6 and row["seconds_mmff"] == 100.0 and row["seconds_xtb_total"] == pytest.approx(45.0)
    assert judge.judge_preoptimizer(rows, judge.Floors(0.01, 0.001)).verdict == judge.PASS


def test_the_floors_come_from_the_default_and_tight_runs(ctx):
    for job in runner.floor_jobs():
        coords = _coords(job.structure, 0.001 if job.variant == "tight" else 0.0)
        _write(ctx, "floor", job.engine, [_record(job, -50.0 + (2e-5 if job.variant == "tight" else 0.0), coords)])
    floors, reported = runner.floors_from(ctx)
    assert floors.orca_opt_energy_meh == pytest.approx(0.02, abs=1e-6) and 0 < floors.orca_opt_rmsd_angstrom < 0.002
    assert reported["xtb_vtight"]["molecules"] == 6 and reported["orca_molecules"] == 6


def test_relative_pairs_use_end_to_end_energies_and_report_conformers_that_moved_to_another_minimum(ctx):
    _fill_geometry(ctx)
    structures = runner.conformer_structures()
    far = structures[0]  # this conformer's xtb structure lands somewhere else
    for job in runner.conformer_jobs():
        shift = 3.0 if (job.engine == "xtb" and job.structure == far) else 0.0
        _write(ctx, "conformers", job.engine, [_record(job, -10.0 - 0.001 * structures.index(job.structure), _coords_conformer(job.structure, shift))])
    for job in runner.reference_jobs():
        _write(ctx, "reference", job.engine, [_record(job, -20.0 - 0.001 * len(job.structure))])
    pairs = runner.relative_pairs(ctx)
    assert pairs["unmapped"] == [far] and len(pairs["isomers"]) == 3
    assert all(p["xtb_kcal"] is not None for p in pairs["isomers"] + pairs["conformers"])
    assert not any(far in p["label"] for p in pairs["conformers"])
    assert pairs["expected_conformer_pairs"] > len(pairs["conformers"])
    # the fixed-geometry decomposition is carried beside the end-to-end difference and never replaces it
    assert all("fixed_geometry" in p for p in pairs["isomers"])


def _coords_conformer(structure, shift):
    name, index = runner.split_structure(structure)
    pos = runner.conformer_mols(name)[index].GetConformer().GetPositions().copy()
    pos[0] += shift
    return pos.tolist()


def test_a_missing_job_leaves_its_pairs_as_missing_cells_rather_than_dropping_them(ctx):
    _fill_geometry(ctx)
    structures = runner.conformer_structures()
    for job in runner.conformer_jobs():
        if job.engine == "xtb" and job.structure == structures[1]:
            continue
        _write(ctx, "conformers", job.engine, [_record(job, -10.0, _coords_conformer(job.structure, 0.0))])
    for job in runner.reference_jobs():
        _write(ctx, "reference", job.engine, [_record(job, -20.0)])
    pairs = runner.relative_pairs(ctx)
    assert pairs["unmapped"] == []
    missing = [p for p in pairs["conformers"] if p["xtb_kcal"] is None]
    assert missing and all(structures[1] in p["label"] for p in missing)


def test_records_from_two_commits_or_a_dirty_tree_are_refused(ctx):
    job = runner.floor_jobs()[0]
    _write(ctx, "floor", "orca", [_record(job, -1.0, _coords("water"), commit="a"), _record(runner.floor_jobs()[1], -1.0, _coords("water"), commit="b")])
    assert "2 different commits" in runner.records_consistent(ctx)
    (ctx.path("floor", "orca")).unlink()
    _write(ctx, "floor", "orca", [_record(job, -1.0, _coords("water"), dirty=True)])
    assert "dirty" in runner.records_consistent(ctx)


def test_the_report_refuses_to_judge_mixed_records_and_says_so(ctx):
    job = runner.floor_jobs()[0]
    _write(ctx, "floor", "orca", [_record(job, -1.0, _coords("water"), commit="a"), _record(runner.floor_jobs()[1], -1.0, _coords("water"), commit="b")])
    assert runner.report(ctx) == 0
    verdict = json.loads((ctx.out / "verdict.json").read_text(encoding="utf-8"))
    assert {v["verdict"] for v in verdict["verdicts"].values()} == {"NOT EVALUABLE"}


def test_the_preregistered_timeout_and_levels_are_not_quietly_changed():
    assert runner.TIMEOUT_SECONDS == 3600 and runner.SAME_MINIMUM_RMSD == 0.3


def test_a_full_set_of_consistent_records_gives_three_separate_verdicts_and_a_readable_report(ctx):
    _fill_geometry(ctx)
    for job in runner.floor_jobs():
        _write(ctx, "floor", job.engine, [_record(job, -50.0, _coords(job.structure, 0.0))])
    structures = runner.conformer_structures()
    for job in runner.conformer_jobs():
        _write(ctx, "conformers", job.engine, [_record(job, -10.0 - 0.001 * structures.index(job.structure), _coords_conformer(job.structure, 0.0))])
    for job in runner.reference_jobs():
        _write(ctx, "reference", job.engine, [_record(job, -20.0 - 0.001 * len(job.structure))])
    for job in runner.preopt_jobs():
        _write(ctx, "preopt", "orca", [_record(job, -100.0 - len(job.structure) / 1000.0, cycles=6, seconds=40.0)])
    for job in runner.gfn1_jobs():
        _write(ctx, "gfn1", "xtb", [_record(job, -99.0, _coords(job.structure, 0.02))])

    assert runner.report(ctx) == 0

    verdicts = json.loads((ctx.out / "verdict.json").read_text(encoding="utf-8"))["verdicts"]
    assert set(verdicts) == {"C1", "C2", "C3"} and verdicts["C1"]["verdict"] == "PASS" and verdicts["C3"]["verdict"] == "PASS"
    assert verdicts["C2"]["verdict"].startswith("TIER")
    text = (ctx.out / "report.txt").read_text(encoding="utf-8")
    assert "reported aside" in text and "ORCA optimizer floor" in text and "overall" not in text.lower()
