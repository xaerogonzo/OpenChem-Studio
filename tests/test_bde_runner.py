"""The primary-arm runner of the bond-dissociation benchmark (`benchmarks/bde/run_bde.py`): the structures it builds, the ORCA output it reads (real, trimmed: the CN radical and the hydrogen atom) and the selection and report it makes on synthetic records. Nothing here runs ORCA."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "bde"
_FIXTURES = Path(__file__).parent / "fixtures" / "orca"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = _load("bde_run_bde_under_test", _BENCH / "run_bde.py")
core, judge, pa = run.core, run.judge, run.pa
BONDS = run.reference_bonds()
CN = (_FIXTURES / "bde_cn_radical_optfreq.out").read_text(encoding="utf-8")
ATOM = (_FIXTURES / "bde_h_atom.out").read_text(encoding="utf-8")


# --- loading must not disturb the other benchmark ---------------------------------------------------------------------------


def test_loading_the_runner_leaves_this_benchmarks_judge_its_own():
    assert judge.MAE_PASS["primary"] == 2.5 and judge.MISSING_ALLOWED == 3 and hasattr(judge, "UNCERTAINTY_LIMIT")
    assert pa.judge.MISSING_ALLOWED == 2  # run_pa kept the proton-affinity judge it imported


# --- structures -------------------------------------------------------------------------------------------------------------


def test_every_bond_has_a_parent_and_a_radical_start_and_the_atom_is_there_once():
    structures = run.build_structures()
    ids = [s["id"] for s in structures]

    assert len(set(ids)) == len(ids) and ids.count(run.ATOM_ID) == 1
    for bond in BONDS:
        parents = [s for s in structures if s["role"] == "parent" and s["smiles"] == bond["smiles"]]
        radicals = [s for s in structures if s["role"] == "radical" and s["bond"] == bond["name"]]
        assert 1 <= len(parents) <= pa.KEEP
        assert len(radicals) == len(parents)  # one radical start per kept parent conformer
        for parent, radical in zip(parents, radicals, strict=True):
            assert radical["symbols"].count("H") == parent["symbols"].count("H") - 1
            assert len(radical["symbols"]) == len(parent["symbols"]) - 1 and radical["mult"] == 2 and parent["mult"] == 1


def test_a_parent_shared_by_two_bonds_is_built_once():
    structures = run.build_structures()
    methanol = [s for s in structures if s["role"] == "parent" and s["smiles"] == "CO"]
    radicals = {s["bond"] for s in structures if s["role"] == "radical" and s["smiles"] == "CO"}

    assert len(methanol) == 1 and radicals == {"methanol C-H", "methanol O-H"}


def test_a_radical_start_keeps_every_other_atoms_place_and_the_list_is_reproducible():
    first, second = run.build_structures(), run.build_structures()
    structures = {s["id"]: s for s in first}
    parent, radical = structures["parent|CC|0"], structures["radical|ethane C-H|0"]
    mol = run.parent_molecule("CC")
    dropped = min(n.GetIdx() for n in mol.GetAtomWithIdx(0).GetNeighbors() if n.GetSymbol() == "H")

    assert np.allclose(radical["coordinates"], np.delete(np.array(parent["coordinates"]), dropped, axis=0))
    assert [s["id"] for s in first] == [s["id"] for s in second]
    assert all(np.allclose(a["coordinates"], b["coordinates"]) for a, b in zip(first, second, strict=True))  # the seed is pinned


# --- the ORCA input ---------------------------------------------------------------------------------------------------------


def test_a_radical_is_a_doublet_a_parent_a_singlet_and_the_atom_a_single_point():
    structures = {s["id"]: s for s in run.build_structures()}
    parent = run.orca_input(structures["parent|CC|0"], 4)
    radical = run.orca_input(structures["radical|ethane C-H|0"], 4)
    retried = run.orca_input(structures["radical|ethane C-H|0"], 4, retry=True)
    atom = run.orca_input(structures[run.ATOM_ID], 4)

    assert parent.startswith("! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq\n%pal nprocs 4 end\n%maxcore 3000\n") and "* xyz 0 1\n" in parent
    assert "* xyz 0 2\n" in radical and "Calc_Hess" not in radical
    assert "%geom\n  Calc_Hess true\nend" in retried
    assert atom.startswith("! M062X def2-TZVPD TightSCF DefGrid3\n") and "Opt" not in atom and "Freq" not in atom and "* xyz 0 2\nH " in atom


# --- reading ORCA's output --------------------------------------------------------------------------------------------------


def test_the_spin_taken_is_the_last_scf_not_the_first():
    assert run.parse_s2(CN) == 0.764932  # the fixture prints an earlier SCF's 0.765870 first
    assert run.parse_s2("no spin here") is None


def test_the_cn_radical_is_read_as_printed():
    r = run.parse_species(CN)

    assert (r["enthalpy"], r["gibbs"], r["energy"]) == (-92.70350529, -92.72646713, -92.711931882203)
    assert r["s2"] == 0.764932 and r["symbols"] == ["C", "N"] and r["frequencies"][5] == 2248.18
    assert r["lowest_frequency"] == 0.0  # a linear molecule's five zero modes are not imaginary


def test_the_hydrogen_atom_is_read_and_its_enthalpy_is_the_energy_plus_five_halves_kt():
    atom = run.parse_atom(ATOM)

    assert atom["energy"] == -0.498135898315 and atom["s2"] == 0.75 and atom["orca_version"] == "6.1.1"
    assert core.hydrogen_atom_enthalpy(atom["energy"]) == pytest.approx(-0.498135898315 + 0.0023604, abs=1e-6)  # 1.4812 kcal/mol in Hartree


def test_an_atom_job_that_did_not_finish_is_refused():
    with pytest.raises(ValueError, match="normally"):
        run.parse_atom(ATOM.replace("ORCA TERMINATED NORMALLY", "ABORTED"))
    with pytest.raises(ValueError, match="no energy"):
        run.parse_atom(ATOM.replace("FINAL SINGLE POINT ENERGY", "ENERGY"))


# --- is it still the species it was meant to be ------------------------------------------------------------------------------


def _methanol_radical_result(shift_h=False):
    """A methanol C-H radical geometry (CH2-OH) built by hand, optionally with a hydrogen moved from carbon to oxygen (the rearrangement to CH3O.)."""
    symbols = ["C", "O", "H", "H", "H"]  # C, O, two C-H, the O-H
    xyz = [[0.0, 0.0, 0.0], [1.36, 0.0, 0.0], [-0.55, 0.93, 0.0], [-0.55, -0.93, 0.0], [1.75, 0.88, 0.0]]
    if shift_h:
        xyz[3] = [1.75, -0.88, 0.0]  # the second carbon hydrogen now sits on the oxygen: O has two H, C has one
    return {"symbols": symbols, "coordinates": xyz}


def test_a_radical_with_the_parents_skeleton_minus_one_hydrogen_is_kept():
    structure = {"role": "radical", "smiles": "CO", "atom": 0}
    assert run.same_skeleton(structure, _methanol_radical_result()) is True


@pytest.mark.parametrize("break_it", ["moved_hydrogen", "lost_hydrogen", "wrong_atom_lost"])
def test_a_rearranged_or_wrong_radical_is_not_kept(break_it):
    structure = {"role": "radical", "smiles": "CO", "atom": 0}
    result = _methanol_radical_result()
    if break_it == "moved_hydrogen":
        result = _methanol_radical_result(shift_h=True)
    elif break_it == "lost_hydrogen":
        result["coordinates"][3] = [9.0, 9.0, 9.0]  # a hydrogen far away: the bond is gone
    else:
        structure = {"role": "radical", "smiles": "CO", "atom": 1}  # the hydrogen came off the carbon, but the bond asked about is the O-H
    assert run.same_skeleton(structure, result) is False


def test_a_parent_is_checked_against_its_own_skeleton():
    water = {"role": "parent", "smiles": "O"}
    good = {"symbols": ["O", "H", "H"], "coordinates": [[0, 0, 0], [0.96, 0, 0], [-0.24, 0.93, 0]]}
    bad = {"symbols": ["O", "H", "H"], "coordinates": [[0, 0, 0], [0.96, 0, 0], [5.0, 5.0, 5.0]]}

    assert run.same_skeleton(water, good) is True and run.same_skeleton(water, bad) is False


# --- which records count, and the report ------------------------------------------------------------------------------------


def _species(structure, role, enthalpy, lowest=0.0, kept=True, completed=True, retry=False, commit="abc", dirty=False, s2=0.76, **extra):
    r = {"structure": structure, "role": role, "retry": retry, "commit": commit, "dirty": dirty, "completed": completed, "enthalpy": enthalpy, "lowest_frequency": lowest, "skeleton_kept": kept, "s2": s2}
    r.update(extra)
    return r


def _atom(commit="abc", dirty=False, energy=-0.5):
    return {"structure": run.ATOM_ID, "role": "atom", "retry": False, "commit": commit, "dirty": dirty, "completed": True, "energy": energy, "s2": 0.75}


def _ids(records):
    return sorted(r["structure"] for r in run.accepted(records))


def test_accepted_drops_imaginary_and_rearranged_structures_and_a_retry_replaces_its_first_try():
    first = _species("p0", "parent", -1.0, lowest=-60.0, smiles="C")
    retried = _species("p0", "parent", -1.1, lowest=10.0, retry=True, smiles="C")
    rearranged = _species("r0", "radical", -1.0, kept=False, bond="x")
    failed = _species("r1", "radical", 0.0, completed=False, bond="x")

    assert _ids([first, rearranged, failed, _atom()]) == [run.ATOM_ID]
    assert _ids([first, retried, rearranged, failed, _atom()]) == [run.ATOM_ID, "p0"]
    assert _ids([retried, first]) == []  # the later record is the structure's current state


def test_the_lowest_enthalpy_parent_and_radical_are_chosen_independently_and_the_atoms_enthalpy_is_used():
    bond = {"name": "b", "smiles": "C"}
    records = [_species("p0", "parent", -40.0, smiles="C"), _species("p1", "parent", -40.5, smiles="C"), _species("r0", "radical", -39.7, bond="b", s2=0.80),
               _species("r1", "radical", -39.6, bond="b", s2=0.9), _atom(energy=-0.4981)]
    h_atom = core.hydrogen_atom_enthalpy(-0.4981)

    picked = run.select(records, bond)

    assert picked["value_eh"] == pytest.approx(-39.7 + h_atom + 40.5)
    assert picked["s2"] == 0.80 and picked["structures"] == 4


@pytest.mark.parametrize("drop", ["parent", "radical", "atom"])
def test_a_bond_missing_a_species_or_the_atom_has_no_value(drop):
    bond = {"name": "b", "smiles": "C"}
    records = [_species("p0", "parent", -40.0, smiles="C"), _species("r0", "radical", -39.7, bond="b"), _atom()]
    assert run.select([r for r in records if r["role"] != drop], bond) is None


def _all_records(commit="abc", dirty=False, error=0.0, skip=()):
    """A record set whose every bond comes out at the reference plus `error` kcal/mol, built by inverting the arithmetic."""
    h_atom = core.hydrogen_atom_enthalpy(-0.5)
    records = [_atom(commit=commit, dirty=dirty, energy=-0.5)]
    seen = set()
    for bond in BONDS:
        if bond["name"] in skip:
            continue
        dh_eh = (bond["dh298"] + error) / core.HARTREE_TO_KCAL
        if bond["smiles"] not in seen:
            seen.add(bond["smiles"])
            records.append(_species(f"parent|{bond['smiles']}", "parent", -100.0, commit=commit, dirty=dirty, smiles=bond["smiles"]))
        records.append(_species(f"radical|{bond['name']}", "radical", -100.0 + dh_eh - h_atom, commit=commit, dirty=dirty, bond=bond["name"], smiles=bond["smiles"]))
    return records


def test_a_set_that_reproduces_the_reference_passes_and_one_off_by_six_fails():
    text, verdict = run.report_text(_all_records(), BONDS)
    assert verdict["verdict"] == judge.PASS and "VERDICT PASS" in text and verdict["problem"] is None

    _, off = run.report_text(_all_records(error=6.0), BONDS)
    assert off["verdict"] == judge.FAIL


def test_more_than_three_missing_deciding_bonds_is_not_evaluable_and_three_is_not():
    deciding = [b["name"] for b in BONDS if not judge.is_low(b)]
    assert run.report_text(_all_records(skip=deciding[:3]), BONDS)[1]["verdict"] == judge.PASS
    assert run.report_text(_all_records(skip=deciding[:4]), BONDS)[1]["verdict"] == judge.NOT_EVALUABLE


def test_a_missing_loose_bond_does_not_count_against_the_verdict():
    loose = [b["name"] for b in BONDS if judge.is_low(b)]
    assert run.report_text(_all_records(skip=loose), BONDS)[1]["verdict"] == judge.PASS


@pytest.mark.parametrize("case", ["two_commits", "dirty"])
def test_records_from_two_commits_or_a_dirty_tree_are_refused_even_when_perfect(case):
    records = _all_records()
    if case == "two_commits":
        records[1] = dict(records[1], commit="def")
    else:
        records = _all_records(dirty=True)

    text, verdict = run.report_text(records, BONDS)

    assert verdict["verdict"] == judge.NOT_EVALUABLE and verdict["problem"] and "REFUSED" in text


def test_the_report_lists_contaminated_radicals_and_reports_by_class():
    records = _all_records()
    for r in records:
        if r.get("bond") == "methane C-H":
            r["s2"] = 0.95
    text, _ = run.report_text(records, BONDS)

    assert "spin-contaminated radicals: 1 (methane C-H)" in text
    assert "  peroxide O-H" in text and "  Si-H" in text and "  S-H" in text
    assert run.bond_class("hydrogen peroxide O-H") == "peroxide O-H" and run.bond_class("ethanol O-H") == "O-H"
    assert run.bond_class("benzene C-H") == "C-H"
