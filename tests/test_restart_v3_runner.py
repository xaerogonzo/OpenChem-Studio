"""Protocol v3's runner (`benchmarks/restart_v3/run_restart_v3.py`, `restart_v3_core.py`): the trigger, the reading of a numerical frequency job (against an excerpt of a real ORCA 6.1.1 job), which records the judge accepts, the reading rules of the three arms,
and the whole chain of one structure with a stand-in for ORCA that answers by the keywords of the input it is given. NOTHING HERE RUNS ORCA.

The stand-in is the only fake: every decision it exercises (which job comes next, what is kept, what the judge sees) is the runner's own code.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
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


# --- the trigger, the size note, the acceptance -----------------------------------------------------------------------------------------------


def _record(**kw) -> dict:
    return {"structure": "radical|x|0", "role": "radical", "completed": True, "lowest_frequency": -300.0, "skeleton_kept": True, "enthalpy": -1.0, **kw}


def test_only_a_radical_that_is_still_imaginary_with_its_skeleton_intact_gets_the_numerical_job():
    assert v3.needs_numerical(_record())
    assert not v3.needs_numerical(_record(role="parent"))            # a closed-shell structure keeps v2's restart
    assert not v3.needs_numerical(_record(role="atom"))
    assert not v3.needs_numerical(_record(lowest_frequency=-19.9))   # accepted by the first run's rule
    assert not v3.needs_numerical(_record(skeleton_kept=False))      # a failed structure, not a saddle point near a minimum
    assert not v3.needs_numerical(_record(completed=False))


def test_the_largest_radical_the_benchmark_covers_has_fourteen_atoms_and_nothing_larger_is_refused():
    assert not v3.beyond_validated(14) and v3.beyond_validated(15)      # a note, not a refusal: see the chain test below


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


def test_a_radical_beyond_the_validated_size_still_gets_the_numerical_job_with_a_note():
    calls, records = [], []
    structure = _radical("CC(C)(C)CS", 5, "neopentyl mercaptan S-H")    # the radical has 17 atoms, more than any arm's
    runner.process(structure, 4, _standin(calls, {"opt": (-300.0, -438.0), "retry": (-300.0, -438.0), "numerical": (550.0, -438.0010)}), "abc", False, records.append)
    assert calls == ["opt", "retry", "numerical"]                      # no refusal for size
    numerical = next(r for r in records if r.get("stage") == "numerical")
    assert numerical["completed"] and numerical["verified"] and numerical["size_note"] == v3.SIZE_NOTE
    assert [r["structure"] for r in v3.accepted(records)] == [numerical["structure"]]
    assert records[-1].get("final") is True


def test_a_radical_at_or_below_the_validated_size_carries_no_size_note():
    calls, records = [], []
    runner.process(_radical(), 4, _standin(calls, {"opt": (-300.0, -438.0), "retry": (-300.0, -438.0), "numerical": (600.0, -438.0010)}), "abc", False, records.append)
    assert next(r for r in records if r.get("stage") == "numerical")["size_note"] is None


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


def test_the_arm_report_flags_a_replaced_enthalpy_and_refuses_a_dirty_or_unstamped_record(monkeypatch):
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
    assert runner.deciding_report("halogen", mixed, [bond], structures)[1]["problem"] is None             # two commits are drift only if a watched file differs between them: that is drift_problem's test, below
    dirty = [dict(r, dirty=True) for r in records]
    refused = runner.deciding_report("halogen", dirty, [bond], structures)[1]
    assert refused["problem"] == "some records were made with a dirty tree" and refused["verdict"] == "NOT EVALUABLE"
    unstamped = [dict(r, commit="") if i == 0 else r for i, r in enumerate(records)]
    assert runner.deciding_report("halogen", unstamped, [bond], structures)[1]["problem"] == "a record carries no commit"
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
    records.append({"structure": "radical|methanethiol S-H|3#numerical", "role": "radical", "stage": "numerical", "completed": False, "error": "ValueError: the numerical job did not terminate normally", "commit": "abc", "dirty": False})
    text, verdict = runner.deciding_report("halogen", records, [bond], None)
    assert "2 numerical job(s) gave no result" in text and "timeout after 14400 s" in text and "did not terminate normally" in text
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


def _git(repo, *args):
    import subprocess
    done = subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, cwd=repo, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture()
def tmp_repo(tmp_path, monkeypatch):
    """A throwaway git repository with a watched file, a note and an artifact, and the runner pointed at it."""
    (tmp_path / "benchmarks" / "restart_v3" / "artifacts").mkdir(parents=True)
    (tmp_path / "benchmarks" / "restart_v3" / "code.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "benchmarks" / "restart_v3" / "notes.md").write_text("notes\n", encoding="utf-8")
    (tmp_path / "benchmarks" / "restart_v3" / "artifacts" / "data.json").write_text("{}", encoding="utf-8")
    (tmp_path / "README.txt").write_text("r\n", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first")
    monkeypatch.setattr(runner, "REPO", tmp_path)
    return tmp_path


def test_a_clean_tree_at_the_records_commit_is_not_drift(tmp_repo):
    head = _git(tmp_repo, "rev-parse", "HEAD")
    assert runner.drift_problem([{"commit": head}]) is None
    assert runner.drift_problem([]) is None


def test_an_UNCOMMITTED_edit_of_a_watched_file_is_drift(tmp_repo):
    head = _git(tmp_repo, "rev-parse", "HEAD")
    (tmp_repo / "benchmarks" / "restart_v3" / "code.py").write_text("x = 2\n", encoding="utf-8")
    assert "files changed since the records' commit" in runner.drift_problem([{"commit": head}])           # `git diff HEAD HEAD` would have said nothing


def test_a_new_untracked_file_in_a_watched_folder_is_drift(tmp_repo):
    head = _git(tmp_repo, "rev-parse", "HEAD")
    (tmp_repo / "benchmarks" / "restart_v3" / "helper.py").write_text("y = 1\n", encoding="utf-8")
    assert "uncommitted changes in the watched folders" in runner.drift_problem([{"commit": head}])


def test_a_later_commit_that_changes_a_watched_file_is_drift_and_one_that_does_not_is_not(tmp_repo):
    first = _git(tmp_repo, "rev-parse", "HEAD")
    (tmp_repo / "README.txt").write_text("changed\n", encoding="utf-8")
    _git(tmp_repo, "commit", "-q", "-am", "readme only")
    second = _git(tmp_repo, "rev-parse", "HEAD")
    assert runner.drift_problem([{"commit": first}, {"commit": second}]) is None                            # two commits, nothing watched between them: an arm that ran across them is fine
    (tmp_repo / "benchmarks" / "restart_v3" / "code.py").write_text("x = 3\n", encoding="utf-8")
    _git(tmp_repo, "commit", "-q", "-am", "code")
    assert runner.drift_problem([{"commit": second}])
    assert "files changed" in runner.drift_problem([{"commit": first}, {"commit": second}])


def test_notes_artifacts_and_results_write_ups_are_not_drift(tmp_repo):
    head = _git(tmp_repo, "rev-parse", "HEAD")
    (tmp_repo / "benchmarks" / "restart_v3" / "notes.md").write_text("more notes\n", encoding="utf-8")
    (tmp_repo / "benchmarks" / "restart_v3" / "RESULT_D.md").write_text("result\n", encoding="utf-8")
    (tmp_repo / "benchmarks" / "restart_v3" / "artifacts" / "data.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_repo / "benchmarks" / "restart_v3" / "artifacts" / "new.jsonl").write_text("{}\n", encoding="utf-8")
    assert runner.drift_problem([{"commit": head}]) is None


def test_an_unstamped_or_unknown_commit_cannot_be_compared(tmp_repo):
    assert "no commit" in runner.drift_problem([{"commit": ""}])
    assert "cannot be compared" in runner.drift_problem([{"commit": "0" * 40}])


def test_git_state_is_an_error_when_git_cannot_answer(tmp_repo, monkeypatch):
    class Failed:
        returncode, stdout, stderr = 128, "", "fatal"

    assert runner.git_state()[1] is False                                                                   # a clean throwaway tree
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Failed())
    with pytest.raises(RuntimeError, match="could not report"):
        runner.git_state()



# --- Arm D-Ph: thiophenol S-H, reported only ----------------------------------------------------------------------------------------------


def test_arm_d_ph_is_one_reported_only_bond_with_every_determination_at_298_kelvin():
    from rdkit import Chem
    (bond,) = v3.thiophenol_bonds()
    assert bond["name"] == "thiophenol S-H" and bond["excluded"] is True                       # nothing decides
    mol = Chem.MolFromSmiles(bond["smiles"])
    assert mol.GetAtomWithIdx(bond["atom"]).GetSymbol() == "S"
    assert Chem.AddHs(mol).GetNumAtoms() - 1 == 12 and not v3.beyond_validated(12)             # 12 atoms: inside what the benchmark covers, no size note
    refs = v3._refs()["thiophenol_context"]
    step = refs["thermal_step_kj"] / 4.184
    pts = bond["points"]
    assert pts["Lim 2007 (0 K value plus the computed step)"] == pytest.approx(76.8 + step)
    assert pts["Borges dos Santos 2002"] == pytest.approx(83.5)                               # a 298 K value as printed
    assert 79.4 in pts.values() and list(pts.values()).count(83.5) == 2                      # Luo's range as printed: its low end, and its high end beside Borges dos Santos's 83.5
    assert bond["upper_limit"] == pytest.approx(28030 * 0.011962656 / 4.184 + step)
    assert bond["upper_limit"] < pts["Borges dos Santos 2002"]                                 # the upper limit lies BELOW the calorimetric value
    assert bond["dh298"] == pytest.approx((min(pts.values()) + max(pts.values())) / 2)        # the table column's middle of the span, nothing is read against it


def test_a_thiophenol_claim_needs_more_than_five_kcal_outside_the_whole_span_on_either_side():
    (bond,) = v3.thiophenol_bonds()
    low, high = min(bond["points"].values()), max(bond["points"].values())
    assert v3.span_reading(None, bond)["claim"] == "no computed value"
    for inside in (low, (low + high) / 2, high):
        assert v3.span_reading(inside, bond)["gross"] is False and v3.span_reading(inside, bond)["outside_span"] == 0.0
    assert v3.span_reading(low - 5.0, bond)["gross"] is False                               # exactly 5.0 outside: not MORE than 5.0
    assert v3.span_reading(low - 5.1, bond)["gross"] is True
    assert v3.span_reading(high + 5.0, bond)["gross"] is False
    assert v3.span_reading(high + 5.1, bond)["gross"] is True
    reading = v3.span_reading(high - 0.5, bond)
    assert reading["above_upper_limit"] == pytest.approx(high - 0.5 - bond["upper_limit"])    # printed, never a claim
    assert reading["gross"] is False and reading["claim"] == "no claim (numbers only)"


def test_the_thiophenol_arm_builds_its_structures_and_is_wired_to_its_own_report(monkeypatch):
    assert "thiophenol" in runner.ARMS and runner.ARMS["thiophenol"].__name__ == "thiophenol_bonds"   # the runner loads its own copy of the core module
    structures = runner.build_structures(v3.thiophenol_bonds())
    radicals = [s for s in structures if s["role"] == "radical"]
    assert radicals and all(len(s["symbols"]) == 12 and s["mult"] == 2 for s in radicals)
    assert sum(1 for s in radicals[0]["symbols"] if s == "S") == 1
    assert any(s["role"] == "atom" for s in structures)


def test_the_thiophenol_report_prints_every_determination_and_the_limit_and_makes_no_claim_when_refused(monkeypatch):
    (bond,) = v3.thiophenol_bonds()
    records = _closed_atom()
    records.append({"structure": "parent|Sc1ccccc1|0", "role": "parent", "smiles": bond["smiles"], "completed": True, "skeleton_kept": True, "enthalpy": -100.0, "lowest_frequency": 50.0, "commit": "abc", "dirty": False})
    records.append({"structure": f"radical|{bond['name']}|0", "role": "radical", "bond": bond["name"], "smiles": bond["smiles"], "completed": True, "skeleton_kept": True, "enthalpy": -99.0, "lowest_frequency": 50.0,
                    "commit": "abc", "dirty": False})
    monkeypatch.setattr(runner, "drift_problem", lambda r: None)
    text, verdict = runner.thiophenol_report(records, [bond], None)                         # invented enthalpies: hundreds of kcal/mol away
    assert verdict["verdict"] is None and verdict["readings"][0]["gross"] is True and "a gross failure" in text
    for label in bond["points"]:
        assert label in text
    assert "UPPER LIMIT" in text and "computed minus limit" in text and "REPORTED ONLY" in text
    monkeypatch.setattr(runner, "drift_problem", lambda r: "files changed since the records' commit")
    text, verdict = runner.thiophenol_report(records, [bond], None)
    assert verdict["readings"][0]["gross"] is False and "no claim: the report is refused" in text and "REFUSED" in text


# --- Arm D: the sensitivity to the shared methanethiol anchor, and where results are written ------------------------------------------------


def test_the_anchor_shifts_are_the_two_upper_bounds_the_preregistration_prints():
    shifts = v3.anchor_shifts_kcal()
    assert shifts["combined"] == pytest.approx(0.317, abs=0.002) and shifts["wilson_alone"] == pytest.approx(0.519, abs=0.002)


def test_the_sensitivity_can_move_a_verdict_and_never_moves_the_one_that_is_read():
    # three bonds each 1.4 below their reference: MSE -1.4 is inside the 1.5 limit, so PASS; raise every reference by 0.32 and MSE is -1.72, so PARTIAL
    rows = [{"dh_kcal": 80.0, "dh_ref": 81.4}] * 3
    base = v3.arm_verdict(v3.judge.stats(rows))
    assert base == "PASS"
    shifted = v3.reference_sensitivity(rows, 0.32)
    assert shifted["verdict"] == "PARTIAL" and shifted["stats"]["mse"] == pytest.approx(-1.72)
    assert v3.reference_sensitivity([{"dh_kcal": None, "dh_ref": 81.4}] * 3, 0.32)["verdict"] == "NOT EVALUABLE"   # missing stays missing


def test_the_arm_d_report_prints_the_sensitivity_beside_the_verdict_and_keeps_the_verdict_on_the_references_as_they_stand(monkeypatch):
    monkeypatch.setattr(runner, "drift_problem", lambda records: None)
    bond, records = _records_with_two_radical_conformers(-99.8)
    text, verdict = runner.deciding_report("sh", records, [dict(bond, excluded=False)], None)
    assert "SENSITIVITY TO THE SHARED METHANETHIOL ANCHOR" in text and "+0.32 kcal/mol" in text and "+0.52 kcal/mol" in text
    assert set(verdict["anchor_sensitivity"]) == {"combined", "wilson_alone"}
    halogen_text, halogen_verdict = runner.deciding_report("halogen", records, [dict(bond, excluded=False)], None)
    assert "SENSITIVITY" not in halogen_text and halogen_verdict["anchor_sensitivity"] is None             # Arm C does not share the anchor


def test_the_watched_list_is_the_benchmark_code_and_not_the_application_or_the_notes():
    assert not any(w.startswith("src") for w in runner.WATCHED)                                              # nothing under benchmarks/ imports openchem
    assert ":(exclude)*.md" in runner.WATCH_SPEC and ":(exclude)benchmarks/restart_v3/artifacts" in runner.WATCH_SPEC
    assert runner._DRIFT_SPEC is runner.WATCH_SPEC                                                           # one list: what is stamped dirty at write time is what is compared at report time


# --- the second independent read's findings ------------------------------------------------------------------------------------------------


def test_a_refused_arm_d_report_states_no_verdict_anywhere(monkeypatch):
    monkeypatch.setattr(runner, "drift_problem", lambda records: None)
    bond, records = _records_with_two_radical_conformers(-99.8)
    text, verdict = runner.deciding_report("sh", records, [dict(bond, excluded=False)], None, extra_problem="structures.json was built for a different bond list than the code now holds")
    assert "REFUSED" in text and verdict["verdict"] == "NOT EVALUABLE"
    assert all(s["verdict"] == "NOT EVALUABLE" for s in verdict["anchor_sensitivity"].values())
    assert "-> PASS" not in text and "-> PARTIAL" not in text and "-> FAIL" not in text


def test_accepting_drift_reads_the_records_and_says_so(monkeypatch):
    monkeypatch.setattr(runner, "drift_problem", lambda records: "files changed since the records' commit abc: run_restart_v3.py")
    bond, records = _records_with_two_radical_conformers(-99.8)
    refused, _ = runner.deciding_report("halogen", records, [dict(bond, excluded=False)], None)
    assert "REFUSED" in refused
    monkeypatch.setattr(runner, "ACCEPT_DRIFT", True)
    accepted, verdict = runner.deciding_report("halogen", records, [dict(bond, excluded=False)], None)
    assert "REFUSED" not in accepted and "DRIFT ACCEPTED" in accepted and "run_restart_v3.py" in accepted and verdict["problem"] is None


def test_the_structures_stamp_follows_the_bond_list(tmp_path):
    bonds = [_sh_bond(), _sh_bond("ethanethiol S-H", "CCS", 2)]
    meta = tmp_path / "structures.meta.json"
    assert "no stamp" in runner.stamp_problem(meta, bonds)
    meta.write_text(json.dumps({"bonds_sha256": runner.bonds_stamp(bonds)}), encoding="utf-8")
    assert runner.stamp_problem(meta, bonds) is None
    assert "different bond list" in runner.stamp_problem(meta, [bonds[0], dict(bonds[1], atom=3)])           # the same name on another atom
    assert "different bond list" in runner.stamp_problem(meta, bonds[:1])
    assert runner.bonds_stamp(bonds) == runner.bonds_stamp([dict(b, dh298=0.0) for b in bonds])             # a reference value is not part of the identity: references are covered by the drift check


def test_a_numerical_failure_that_was_redone_is_not_listed_as_no_result():
    bond, records = _records_with_two_radical_conformers(-99.8)
    failed = {"structure": "radical|methanethiol S-H|0#numerical", "role": "radical", "stage": "numerical", "completed": False, "error": "OSError: no such file", "infrastructure": True, "commit": "abc", "dirty": False}
    row = runner.judge_rows([failed] + records, [bond])[0]                                                   # the completed record of the same structure follows it in `records`
    assert row["numerical_no_result"] == []


def test_the_orca_call_kills_the_whole_tree_on_the_time_limit_and_returns_the_output_otherwise(monkeypatch):
    import sys as _sys
    import time as _time
    monkeypatch.setattr(runner.bde, "ORCA", _sys.executable)             # the "input" is a Python program: Popen([python, "job.inp"])
    monkeypatch.setattr(runner.bde, "JOB_TIMEOUT_SECONDS", 2)
    text, hessian = runner.run_orca_tree("print('ORCA TERMINATED NORMALLY')\nopen('job.hess', 'w').write('H')\n", True)
    assert "ORCA TERMINATED NORMALLY" in text and hessian == "H"
    # a job that spawns a grandchild holding on for a minute and then sleeps itself: the limit fires, the tree dies, and the call returns promptly
    program = "import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\ntime.sleep(60)\n"
    began = _time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        runner.run_orca_tree(program)
    assert _time.time() - began < 30


def test_a_very_large_radical_is_not_refused_but_a_stalled_one_is_a_missing_structure_with_its_reason():
    records = []

    def run(text, want_hessian=False):
        if "NumFreq" in text:
            raise subprocess.TimeoutExpired("orca", 14400)
        return _standin([], {"opt": (-300.0, -438.0), "retry": (-300.0, -438.0)})(text, want_hessian)

    assert runner.process(_radical(), 4, run, "abc", False, records.append) is True                       # the chain closes: a timeout is a result about the structure, not a failure to start
    timed_out = next(r for r in records if r.get("stage") == "numerical")
    assert not timed_out["completed"] and "timeout after" in timed_out["error"]
    assert v3.accepted(records) == []
