"""Protocol v3's runner (`benchmarks/restart_v3/run_restart_v3.py`, `restart_v3_core.py`): the trigger, the reading of a numerical frequency job (against an excerpt of a real ORCA 6.1.1 job), which records the judge accepts, the reading rules of the three arms,
and the whole chain of one structure with a stand-in for ORCA that answers by the keywords of the input it is given. NOTHING HERE RUNS ORCA.

The stand-in is the only fake: every decision it exercises (which job comes next, what is kept, what the judge sees) is the runner's own code.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent
_BENCH = _HERE.parent / "benchmarks" / "restart_v3"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v3 = _load("restart_v3_core_under_test", _BENCH / "restart_v3_core.py")
runner = _load("run_restart_v3_under_test", _BENCH / "run_restart_v3.py")

NUMFREQ = (_HERE / "fixtures" / "orca" / "methylthiyl_numfreq_excerpt.out").read_text(encoding="utf-8")


# --- the reading of a numerical job, against a real one ---------------------------------------------------------------------------------


def test_a_real_numerical_job_is_read():
    out = v3.parse_numerical(NUMFREQ)
    assert out["energy"] == pytest.approx(-438.041431474243)
    assert out["enthalpy"] == pytest.approx(-438.00155118)
    assert out["s2"] == pytest.approx(0.753892)
    assert out["symbols"] == ["C", "S", "H", "H", "H"] and len(out["coordinates"]) == 5
    assert len(out["frequencies"]) == 15 and out["lowest_frequency"] == pytest.approx(0.0)  # the six translations and rotations are printed as zero
    assert out["orca_version"] == "6.1.1"


def test_an_unfinished_or_wrong_condition_job_is_never_a_number():
    with pytest.raises(ValueError, match="terminate normally"):
        v3.parse_numerical(NUMFREQ.replace("ORCA TERMINATED NORMALLY", ""))
    with pytest.raises(ValueError, match="298.15 K"):
        v3.parse_numerical(NUMFREQ.replace("298.15 K", "310.00 K"))
    with pytest.raises(ValueError, match="no enthalpy"):
        v3.parse_numerical(NUMFREQ.replace("Total enthalpy", "Total nothing"))


# --- the trigger, the cap, the acceptance -----------------------------------------------------------------------------------------------


def _record(**kw) -> dict:
    return {"structure": "radical|x|0", "role": "radical", "completed": True, "lowest_frequency": -300.0, "skeleton_kept": True, "enthalpy": -1.0, **kw}


def test_only_a_radical_that_is_still_imaginary_with_its_skeleton_intact_gets_the_numerical_job():
    assert v3.needs_numerical(_record())
    assert not v3.needs_numerical(_record(role="parent"))            # a closed-shell structure keeps v2's restart
    assert not v3.needs_numerical(_record(role="atom"))
    assert not v3.needs_numerical(_record(lowest_frequency=-19.9))   # accepted by the first run's rule
    assert not v3.needs_numerical(_record(skeleton_kept=False))      # a failed structure, not a saddle point near a minimum
    assert not v3.needs_numerical(_record(completed=False))


def test_the_cap_is_twelve_atoms():
    assert v3.within_cap(12) and not v3.within_cap(13)


def test_a_numerical_record_is_accepted_at_any_frequency_and_an_analytic_one_is_not():
    numerical = _record(structure="radical|x|0#numerical", numerical=True, lowest_frequency=-95.2)
    analytic = _record(structure="radical|y|0", lowest_frequency=-95.2)
    assert v3.accepted([numerical]) == [numerical]
    assert v3.accepted([analytic]) == []
    assert v3.accepted([_record(structure="radical|z|0#numerical", numerical=True, skeleton_kept=False)]) == []   # the skeleton test still applies


def test_the_label_and_the_shift_say_what_the_replacement_did():
    retry = _record(enthalpy=-100.000, lowest_frequency=-1328.0)
    verified = v3.numerical_fields(retry, {"lowest_frequency": 601.0})
    assert verified["verified"] and verified["label"] is None and verified["analytic_enthalpy"] == -100.0
    soft = v3.numerical_fields(retry, {"lowest_frequency": -30.0})
    assert not soft["verified"] and soft["label"] == v3.NOT_VERIFIED
    record = _record(structure="radical|x|0#numerical", parent_structure="radical|x|0", numerical=True, enthalpy=-100.001, verified=False, lowest_frequency=-30.0, analytic_enthalpy=-100.0, analytic_lowest_frequency=-1328.0)
    shift = v3.numerical_labels([record])["radical|x|0"]["shift_kcal"]
    assert shift == pytest.approx(-0.001 * 627.5094740631)


# --- the reading rules ----------------------------------------------------------------------------------------------------------------------


def _stats(errors, missing=0):
    return v3.judge.Stats(len(errors), missing, sum(abs(e) for e in errors) / len(errors), sum(errors) / len(errors), max(abs(e) for e in errors)) if errors else v3.judge.Stats(0, missing, None, None, None)


def test_arm_verdict_uses_the_first_runs_limits_and_its_own_missing_rule():
    assert v3.arm_verdict(_stats([1.0, -1.0, 2.0, 1.5, 0.5, -0.5])) == "PASS"
    assert v3.arm_verdict(_stats([3.0, 3.0, 3.0, 3.0, 3.0, 3.0])) == "PARTIAL"            # MAE 3.0, MSE 3.0 over the signed limit
    assert v3.arm_verdict(_stats([4.0, 4.0, 4.0, 4.0, 4.0, 4.0])) == "FAIL"
    assert v3.arm_verdict(_stats([1.0, 1.0, 1.0, 1.0, 1.0], missing=1)) == "PASS"         # one of six missing is allowed
    assert v3.arm_verdict(_stats([1.0, 1.0, 1.0, 1.0], missing=2)) == "NOT EVALUABLE"    # two is not (the 27-bond arm's allowance of three is NOT used)
    assert v3.arm_verdict(_stats([1.0, 1.0], missing=1)) == "PASS"                        # Arm D: two of three computed
    assert v3.arm_verdict(_stats([1.0], missing=2)) == "NOT EVALUABLE"
    assert v3.arm_verdict(_stats([])) == "NOT EVALUABLE"


def test_a_single_error_over_five_stops_a_pass():
    assert v3.arm_verdict(_stats([0.0, 0.0, 0.0, 0.0, 0.0, 5.1])) == "PARTIAL"


def test_the_standard_error_and_the_limits_too_close_to_call():
    assert v3.standard_error([1.0]) is None
    assert v3.standard_error([0.0, 2.0]) == pytest.approx(1.0)       # sd sqrt(2), over sqrt(2)
    near = v3.near_limits(_stats([2.3, 2.5, 2.4]), 0.5)
    assert any("mean absolute error 2.40" in n for n in near)
    assert v3.near_limits(_stats([0.1, 0.0, -0.1]), 0.5) == []


def _bond(**kw):
    return {"name": "b", "dh298": 100.0, "uncertainty": 0.6, "others": [98.0, 99.0], "calculated": [97.0], **kw}


def test_a_bromine_claim_needs_both_the_kinetics_value_and_the_calculation_to_be_over_five_away():
    assert v3.bromine_reading(None, _bond())["claim"] == "no computed value"
    assert v3.bromine_reading(100.0 - 5.5, _bond())["gross"] is False       # 5.5 from the kinetics value but only 2.5 from the calculation
    assert v3.bromine_reading(90.0, _bond())["gross"] is True                # 10 from the kinetics, 7 from the calculation
    no_calc = _bond(calculated=[])
    assert v3.bromine_reading(92.0, no_calc)["gross"] is True                # bromoethane: 6 below the lowest other determination (98.0) and 8 from the kinetics value
    assert v3.bromine_reading(93.0, no_calc)["gross"] is False               # exactly 5 outside the range: not MORE than 5
    assert v3.bromine_reading(106.0, no_calc)["gross"] is True               # 7 above the highest (99.0), 6 from the kinetics value
    assert v3.bromine_reading(104.5, no_calc)["gross"] is False              # 5.5 above the highest, but only 4.5 from the kinetics value
    wide = _bond(dh298=105.0, others=[95.0, 99.0], calculated=[])
    assert v3.bromine_reading(91.0, wide)["gross"] is False                  # 8 from the highest, but only 4 below the LOWEST: the old rule called this gross
    assert v3.bromine_reading(97.0, wide)["gross"] is False                  # inside the range of the others
    two_calcs = _bond(calculated=[97.0, 90.0])
    assert v3.bromine_reading(91.0, two_calcs)["gross"] is False             # within 5 of one of the two calculated values: no claim


# --- the references of the three arms -----------------------------------------------------------------------------------------------------


def test_arm_c_is_the_six_atct_bonds_and_arm_cbr_the_four_kinetics_bonds_in_kcal():
    halogen = v3.halogen_bonds()
    assert len(halogen) == 6 and not any(b["excluded"] for b in halogen)
    bromine = v3.bromine_bonds()
    assert [b["name"] for b in bromine] == ["bromomethane C-H", "dibromomethane C-H", "bromochloromethane C-H", "bromoethane alpha C-H"]
    assert all(b["excluded"] for b in bromine)                                                  # reported only: nothing decides
    assert bromine[0]["dh298"] == pytest.approx(427.2 / 4.184) and bromine[3]["calculated"] == []
    assert bromine[0]["calculated"] == pytest.approx([420.5 / 4.184, 420.8 / 4.184])


def test_each_bromine_parent_loses_the_hydrogen_the_name_says():
    from rdkit import Chem
    for b in v3.bromine_bonds():
        mol = Chem.MolFromSmiles(b["smiles"])
        atom = mol.GetAtomWithIdx(b["atom"])
        assert atom.GetSymbol() == "C" and atom.GetTotalNumHs() >= 1, b["name"]
    alpha = next(b for b in v3.bromine_bonds() if "alpha" in b["name"])
    assert [n.GetSymbol() for n in Chem.MolFromSmiles(alpha["smiles"]).GetAtomWithIdx(alpha["atom"]).GetNeighbors()] == ["C", "Br"]


# --- the chain of one structure, with a stand-in for ORCA ---------------------------------------------------------------------------------


def _output(symbols, coordinates, lowest, enthalpy, optimized=True, numerical=False):
    """A minimal output with exactly the lines the readers use. A real output has thousands more; the readers are tested against real ones elsewhere (the excerpt above, `tests/test_proton_affinity_*`)."""
    lines = ["Program Version 6.1.1 - RELEASE -"]
    if optimized:
        lines.append("*** THE OPTIMIZATION HAS CONVERGED ***")
    lines += ["CARTESIAN COORDINATES (ANGSTROEM)", "---------------------------------"]
    lines += [f"  {s:<3}{x:>12.6f}{y:>12.6f}{z:>12.6f}" for s, (x, y, z) in zip(symbols, coordinates)]
    lines += ["", "Expectation value of <S**2>     :     0.753892", "FINAL SINGLE POINT ENERGY      -438.000000000000", "VIBRATIONAL FREQUENCIES", "-----------------------", "",
              f"     0:       0.00 cm**-1", f"     1:    {lowest:>8.2f} cm**-1", "", "Temperature         ...   298.15 K", "Pressure            ...     1.00 atm", "Point Group:  C1, Symmetry Number:   1",
              f"Total enthalpy                    ...   {enthalpy:.8f} Eh", "Final Gibbs free energy         ...  -438.020000 Eh", "                             ****ORCA TERMINATED NORMALLY****"]
    return "\n".join(lines)


def _standin(calls, results):
    """An ORCA that answers by the keywords of the input: `results` maps 'opt' / 'retry' / 'numerical' to the lowest frequency and enthalpy it reports; the geometry is the one in the input."""
    def run(text, want_hessian=False):
        kind = "numerical" if "NumFreq" in text else "retry" if "Calc_Hess" in text else "hessian" if " Freq" in text.splitlines()[0] and "Opt" not in text.splitlines()[0] else "opt"
        calls.append(kind)
        block = text.split("* xyz")[1].strip().splitlines()[1:-1]
        symbols = [row.split()[0] for row in block]
        coordinates = [[float(v) for v in row.split()[1:4]] for row in block]
        lowest, enthalpy = results[kind]
        return _output(symbols, coordinates, lowest, enthalpy, optimized=kind != "numerical"), None
    return run


def _radical(smiles="CS", atom=1, name="methanethiol S-H"):
    bond = {"name": name, "smiles": smiles, "atom": atom, "dh298": 87.35, "uncertainty": 0.58, "element": "S", "excluded": False}
    return next(s for s in runner.build_structures([bond]) if s["role"] == "radical")


def test_a_radical_that_stays_imaginary_gets_one_numerical_job_and_no_displaced_restart():
    calls, records = [], []
    structure = _radical()
    done = runner.process(structure, 4, _standin(calls, {"opt": (-1328.0, -438.0), "retry": (-1328.0, -438.0), "numerical": (601.0, -438.0010)}), "abc", False, records.append)
    assert done is True
    assert calls == ["opt", "retry", "numerical"]                        # one numerical job; no Hessian job, no displaced optimizations
    numerical = next(r for r in records if r.get("stage") == "numerical")
    assert numerical["structure"] == f"{structure['id']}#numerical" and numerical["completed"] and numerical["verified"] and numerical["numerical"]
    assert numerical["analytic_enthalpy"] == -438.0 and numerical["enthalpy"] == -438.0010
    assert numerical["parent_structure"] == structure["id"] and numerical["skeleton_kept"]
    assert records[-1].get("final") is True
    # the judge sees the numerical enthalpy and not the analytic one
    kept = v3.accepted(records)
    assert [r["structure"] for r in kept] == [f"{structure['id']}#numerical"]


def test_a_numerical_result_below_minus_twenty_is_kept_and_labelled():
    calls, records = [], []
    structure = _radical()
    runner.process(structure, 4, _standin(calls, {"opt": (-300.0, -438.0), "retry": (-300.0, -438.0), "numerical": (-95.0, -438.0010)}), "abc", False, records.append)
    assert calls == ["opt", "retry", "numerical"]                        # no displaced restart afterwards
    numerical = next(r for r in records if r.get("stage") == "numerical")
    assert numerical["completed"] and not numerical["verified"] and numerical["label"] == v3.NOT_VERIFIED
    assert [r["structure"] for r in v3.accepted(records)] == [numerical["structure"]]
    assert list(v3.numerical_labels(records).values())[0]["verified"] is False


def test_a_radical_the_first_stage_accepts_never_gets_the_numerical_job():
    calls, records = [], []
    runner.process(_radical(), 4, _standin(calls, {"opt": (150.0, -438.0)}), "abc", False, records.append)
    assert calls == ["opt"]
    assert not any(r.get("stage") == "numerical" for r in records)


def test_a_radical_over_the_cap_gets_no_job_and_a_record_saying_why():
    calls, records = [], []
    structure = _radical("CC(C)(C)S", 4, "tert-butanethiol S-H")      # the radical has 14 atoms
    runner.process(structure, 4, _standin(calls, {"opt": (-300.0, -438.0), "retry": (-300.0, -438.0)}), "abc", False, records.append)
    assert calls == ["opt", "retry"]
    capped = next(r for r in records if r.get("stage") == "numerical")
    assert capped["capped"] and capped["label"] == v3.OVER_CAP and not capped["completed"]
    assert v3.accepted(records) == []                                  # it is a missing bond, as the first run's rule makes it
    assert records[-1].get("final") is True


def test_a_failed_numerical_job_is_a_missing_structure_with_its_reason():
    records = []
    structure = _radical()

    def run(text, want_hessian=False):
        if "NumFreq" in text:
            return "ORCA crashed", None
        return _standin([], {"opt": (-300.0, -438.0), "retry": (-300.0, -438.0)})(text, want_hessian)

    runner.process(structure, 4, run, "abc", False, records.append)
    failed = next(r for r in records if r.get("stage") == "numerical")
    assert not failed["completed"] and "terminate normally" in failed["error"]
    assert v3.accepted(records) == []


def test_a_job_that_cannot_be_started_leaves_the_chain_open():
    records = []

    def run(text, want_hessian=False):
        raise OSError("no such executable")

    assert runner.process(_radical(), 4, run, "abc", False, records.append) is False
    assert not any(r.get("final") for r in records)


def test_the_input_of_the_numerical_job_is_the_preregistered_one():
    structure = dict(_radical(), charge=0, mult=2)
    text = runner.numerical_input(structure, 4).splitlines()
    assert text[0] == "! M062X def2-TZVPD TightSCF DefGrid3 NumFreq"
    assert text[1:4] == ["%pal nprocs 4 end", "%maxcore 3000", "* xyz 0 2"]
    assert "Opt" not in text[0] and "Freq" in text[0]


def test_the_arm_report_flags_a_replaced_enthalpy_and_refuses_mixed_commits(monkeypatch):
    monkeypatch.setattr(runner, "drift_problem", lambda records: None)   # the commit "abc" of these stand-in records is not a real one; the drift check has its own tests below
    bond = {"name": "methanethiol S-H", "smiles": "CS", "atom": 1, "dh298": 87.35, "uncertainty": 0.58, "element": "S", "excluded": False}
    structures = runner.build_structures([bond])
    records = []
    for s in structures:
        if s["role"] == "atom":
            records.append({"structure": s["id"], "role": "atom", "completed": True, "energy": -0.5, "commit": "abc", "dirty": False})
            records.append({"structure": s["id"], "role": "atom", "stage": "closed", "completed": False, "final": True, "commit": "abc", "dirty": False})
        else:
            runner.process(s, 4, _standin([], {"opt": (150.0, -438.0), "retry": (150.0, -438.0)}), "abc", False, records.append)
    text, verdict = runner.deciding_report("halogen", records, [bond], structures)
    assert "ARM C" in text and verdict["problem"] is None
    mixed = [dict(r, commit="other") if i == 0 else r for i, r in enumerate(records)]
    _, refused = runner.deciding_report("halogen", mixed, [bond], structures)
    assert refused["problem"] and "commits" in refused["problem"] and refused["verdict"] == "NOT EVALUABLE"
    dirty = [dict(r, dirty=True) for r in records]
    assert runner.deciding_report("halogen", dirty, [bond], structures)[1]["problem"] == "some records were made with a dirty src/"
    assert json.dumps(verdict["rows"], default=str)


# --- what the report says about WHICH structures decided a bond ------------------------------------------------------------------------


def _sh_bond(name="methanethiol S-H", smiles="CS", atom=1, ref=87.35):
    return {"name": name, "smiles": smiles, "atom": atom, "dh298": ref, "uncertainty": 0.58, "element": "S", "excluded": False}


def _closed_atom():
    return [{"structure": runner.bde.ATOM_ID, "role": "atom", "completed": True, "energy": -0.5, "commit": "abc", "dirty": False},
            {"structure": runner.bde.ATOM_ID, "role": "atom", "stage": "closed", "completed": False, "final": True, "commit": "abc", "dirty": False}]


def _records_with_two_radical_conformers(numerical_enthalpy, kept_verified=True):
    """Two parent/radical conformers of one bond. Conformer 0's radical needs the numerical job; conformer 1's is accepted analytically. Which of them is LOWER decides which one the bond's value comes from."""
    bond = _sh_bond()
    base = {"commit": "abc", "dirty": False, "completed": True, "skeleton_kept": True}
    records = _closed_atom()
    records.append(dict(base, structure="parent|CS|0", role="parent", smiles="CS", enthalpy=-100.0, lowest_frequency=50.0, stage="opt"))
    records.append(dict(base, structure="radical|methanethiol S-H|0", role="radical", bond=bond["name"], smiles="CS", enthalpy=-99.0, lowest_frequency=-1300.0, stage="retry"))
    records.append(dict(base, structure="radical|methanethiol S-H|0#numerical", parent_structure="radical|methanethiol S-H|0", role="radical", bond=bond["name"], smiles="CS", stage="numerical",
                        numerical=True, verified=kept_verified, enthalpy=numerical_enthalpy, analytic_enthalpy=-99.0, analytic_lowest_frequency=-1300.0, lowest_frequency=600.0 if kept_verified else -40.0))
    records.append(dict(base, structure="radical|methanethiol S-H|1", role="radical", bond=bond["name"], smiles="CS", enthalpy=-99.5, lowest_frequency=100.0, stage="opt"))
    return bond, records


def test_the_flag_follows_the_conformer_the_value_came_from_not_the_other_ones():
    # the numerical conformer is HIGHER (-99.3) than the analytic one (-99.5): the bond's radical is the analytic conformer and nothing should say 'numerical'
    bond, records = _records_with_two_radical_conformers(-99.3, kept_verified=False)
    row = runner.judge_rows(records, [bond])[0]
    assert row["selected"]["radical"]["method"] == "analytic"
    text = runner._flags(row)
    assert "NUMERICAL" not in text and "NOT VERIFIED" not in text and "radical analytic" in text


def test_a_bond_whose_value_is_an_unverified_numerical_enthalpy_says_so():
    # now the numerical conformer is the lowest (-99.8) and its own mode is still below -20
    bond, records = _records_with_two_radical_conformers(-99.8, kept_verified=False)
    row = runner.judge_rows(records, [bond])[0]
    assert row["selected"]["radical"]["method"] == "numerical" and row["selected"]["radical"]["verified"] is False
    assert "NUMERICAL" in runner._flags(row) and "FREQUENCIES NOT VERIFIED" in runner._flags(row)
    assert row["selected"]["radical"]["shift_kcal"] == pytest.approx((-99.8 + 99.0) * 627.5094740631)
    assert "lowest frequency parent 50, radical -40 cm-1" in runner._flags(row)


def test_a_numerical_job_with_no_result_is_named_in_the_report(monkeypatch):
    monkeypatch.setattr(runner, "drift_problem", lambda records: None)
    bond, records = _records_with_two_radical_conformers(-99.3)
    records.append({"structure": "radical|methanethiol S-H|2#numerical", "role": "radical", "stage": "numerical", "completed": False, "error": "timeout after 14400 s", "commit": "abc", "dirty": False})
    records.append({"structure": "radical|methanethiol S-H|3#numerical", "role": "radical", "stage": "numerical", "completed": False, "capped": True, "label": v3.OVER_CAP, "commit": "abc", "dirty": False})
    text, verdict = runner.deciding_report("halogen", records, [bond], None)
    assert "2 numerical job(s) gave no result" in text and "timeout after 14400 s" in text and "over the 12-atom cap" in text
    assert [n["structure"] for n in verdict["rows"][0]["numerical_no_result"]] == ["radical|methanethiol S-H|2#numerical", "radical|methanethiol S-H|3#numerical"]


def test_one_missing_deciding_bond_is_stated(monkeypatch):
    monkeypatch.setattr(runner, "drift_problem", lambda records: None)
    bond, records = _records_with_two_radical_conformers(-99.8)
    absent = _sh_bond("ethanethiol S-H", "CCS", 2, 87.16)
    text, _ = runner.deciding_report("sh", records, [bond, absent], None)
    assert "ONE of the 2 deciding bonds has no computed value: the verdict rests on the other 1." in text
    assert "DERIVED here" in text and "PUBLISHED" in text    # Arm D says which references are published and which are derived


def test_a_refused_bromine_report_makes_no_claim(monkeypatch):
    bromine = v3.bromine_bonds()[0]
    records = _closed_atom()
    records.append({"structure": "parent|CBr|0", "role": "parent", "smiles": "CBr", "completed": True, "skeleton_kept": True, "enthalpy": -100.0, "lowest_frequency": 50.0, "commit": "abc", "dirty": False})
    records.append({"structure": f"radical|{bromine['name']}|0", "role": "radical", "bond": bromine["name"], "smiles": "CBr", "completed": True, "skeleton_kept": True, "enthalpy": -99.0, "lowest_frequency": 50.0,
                    "commit": "abc", "dirty": False})
    monkeypatch.setattr(runner, "drift_problem", lambda r: None)
    # the invented enthalpies make the computed value hundreds of kcal/mol from every reference
    text, verdict = runner.bromine_report(records, [bromine], None)
    assert verdict["readings"][0]["gross"] is True and "a gross failure" in text
    monkeypatch.setattr(runner, "drift_problem", lambda r: "files changed since the records' commit")
    text, verdict = runner.bromine_report(records, [bromine], None)
    assert verdict["readings"][0]["gross"] is False and "no claim: the report is refused" in text and "REFUSED" in text
    assert "(error" in text and "calculated" in text      # the errors against the range and the calculated values are printed, not only held in the JSON


# --- provenance --------------------------------------------------------------------------------------------------------------------------


def test_every_record_is_stamped_with_the_tree_as_it_is_when_it_is_written(tmp_path, monkeypatch):
    structures = [s for s in runner.build_structures([_sh_bond()]) if s["role"] == "atom"]
    (tmp_path / "sh").mkdir()
    (tmp_path / "sh" / "structures.json").write_text(json.dumps(structures), encoding="utf-8")
    states = iter([("c0", False)] + [("c1", False)] + [("c1", True)] * 20)   # the first call is the run's start; the tree is edited before the next record
    monkeypatch.setattr(runner, "git_state", lambda: next(states))

    def run(text, want_hessian=False):
        return "FINAL SINGLE POINT ENERGY      -0.500000000000\nORCA TERMINATED NORMALLY", None

    runner.run_stage("sh", tmp_path, 4, 1, run)
    records = [json.loads(line) for line in (tmp_path / "sh" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["commit"], r["dirty"]) for r in records] == [("c1", False), ("c1", True)]    # the later record carries the edit; one stamp for the whole run would hide it


def test_a_report_is_refused_when_what_the_records_depend_on_changed_since_their_commit():
    import subprocess
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=runner.REPO, check=False).stdout.strip()
    assert head, "this test needs a git checkout"
    assert runner.drift_problem([{"commit": head}]) is None                         # nothing changed since HEAD
    assert "no commit" in runner.drift_problem([{"commit": ""}])                    # an unstamped record
    assert runner.drift_problem([{"commit": "0" * 40}])                             # a commit git does not know cannot be compared
    assert runner.drift_problem([]) is None


def test_the_report_prints_the_lowest_vibration_not_the_zeros_of_translation_and_rotation():
    real = v3.parse_numerical(NUMFREQ)["frequencies"]          # a real NumFreq job: six zeros, then 600.75 ...
    assert v3.lowest_vibration(real) == pytest.approx(600.75)
    assert v3.lowest_vibration([0.0] * 6 + [-1328.21, 742.5]) == pytest.approx(-1328.21)   # an imaginary mode is kept
    assert v3.lowest_vibration([0.0, 0.0]) is None
    bond, records = _records_with_two_radical_conformers(-99.8)
    for r in records:
        if r.get("role") != "atom":
            r["frequencies"] = [0.0] * 6 + [r["lowest_frequency"], 900.0]
    row = runner.judge_rows(records, [bond])[0]
    assert "lowest frequency parent 50, radical 600 cm-1" in runner._flags(row)             # the stand-in records' own lowest modes, not 0
