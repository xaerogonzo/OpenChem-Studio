"""The runner of the displaced-restart protocol (`benchmarks/restart_v2/`): the arithmetic (a real ORCA Hessian file, the displacement, the two preregistered rules), the structures it builds, the chain of jobs one structure goes through (with a stand-in for ORCA that returns the
benchmark's real output text), what resumes, and the reports on synthetic records.

No ORCA runs here. The Hessian fixture is a real ORCA 6.1.1 `.hess` of planar H3O+ (M062X/def2-SVP): its most negative mode, -541.6 cm-1, is the umbrella that the first run could not leave.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "restart_v2"
_FIXTURES = Path(__file__).parent / "fixtures" / "orca"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("restart_v2_core_for_tests", "restart_core.py")
run = _load("restart_v2_run_for_tests", "run_restart.py")
HESSIAN = (_FIXTURES / "h3o_planar_def2svp_freq.hess").read_text(encoding="utf-8")
GOOD_H3O = (_FIXTURES / "pa_h3o_optfreq.out").read_text(encoding="utf-8")
PLANAR_H3O = GOOD_H3O.replace("6:     807.65 cm**-1", "6:    -601.55 cm**-1")


# --- reading the Hessian and displacing --------------------------------------------------------------------------------------------


def test_the_real_hessian_file_gives_the_umbrella_mode_scaled_to_one():
    frequency, vector = core.lowest_mode(HESSIAN)
    assert frequency == pytest.approx(-541.61, abs=0.01) and vector.shape == (4, 3)
    assert np.abs(vector).max() == pytest.approx(1.0)
    # the three hydrogens move together out of the plane (z, scaled to 1) and the heavy oxygen against them by less (0.19): the umbrella
    assert np.allclose(np.abs(vector[1:, 2]), 1.0, atol=0.05) and np.sign(vector[1:, 2]).tolist() == [-np.sign(vector[0, 2])] * 3 and 0.1 < abs(vector[0, 2]) < 0.3
    assert np.abs(vector[:, :2]).max() < 0.05


def test_the_frequencies_follow_the_modes_in_order_and_the_first_six_are_zero():
    modes, frequencies = core.read_hessian_modes(HESSIAN)
    assert modes.shape == (12, 12) and len(frequencies) == 12
    assert np.allclose(frequencies[:6], 0.0) and frequencies[6] < 0 < frequencies[7]


def test_displacement_moves_the_largest_component_by_exactly_the_amplitude_in_opposite_directions():
    _f, vector = core.lowest_mode(HESSIAN)
    xyz = np.array([[0.0, 0.0, 0.0], [0.98, 0.0, 0.0], [-0.49, 0.8487, 0.0], [-0.49, -0.8487, 0.0]])
    plus, minus = core.displaced(xyz, vector)
    assert np.abs(plus - xyz).max() == pytest.approx(core.AMPLITUDE) and np.abs(minus - xyz).max() == pytest.approx(core.AMPLITUDE)
    assert np.allclose(plus - xyz, -(minus - xyz))
    # a planar ion displaced along the umbrella is a pyramid, one way up and one way down (mirror images, so the same energy)
    assert abs(plus[0, 2] - plus[1, 2]) > 0.1 and plus[0, 2] * minus[0, 2] < 0


def test_a_hessian_that_is_not_one_is_refused_with_the_reason():
    with pytest.raises(ValueError, match="no \\$normal_modes"):
        core.read_hessian_modes("$hessian\n3\n")
    with pytest.raises(ValueError, match="coordinates against"):
        core.displaced([[0.0, 0.0, 0.0]], np.zeros((2, 3)))


# --- the two rules the preregistration states in numbers ----------------------------------------------------------------------------


def _record(**kwargs) -> dict:
    return dict({"completed": True, "role": "radical", "lowest_frequency": 0.0, "skeleton_kept": True}, **kwargs)


def test_a_structure_is_restarted_only_when_it_finished_imaginary_with_its_skeleton_intact():
    assert core.needs_restart(_record(lowest_frequency=-49.4))
    assert not core.needs_restart(_record(lowest_frequency=-19.9))  # inside the first run's allowance
    assert not core.needs_restart(_record(lowest_frequency=-300.0, skeleton_kept=False))  # a rearranged radical is a failed structure, not a saddle point
    assert not core.needs_restart(_record(lowest_frequency=-300.0, completed=False))
    assert not core.needs_restart(_record(role="atom"))


def test_acceptance_is_the_first_runs():
    assert core.accepted_record(_record()) and not core.accepted_record(_record(lowest_frequency=-20.1))
    assert not core.accepted_record(_record(skeleton_kept=False)) and not core.accepted_record(_record(completed=False))
    assert core.accepted_record({"completed": True, "role": "atom"})


@pytest.mark.parametrize(
    "triggered, rescued, adopt",
    [(0, 0, False), (1, 1, False), (2, 1, True), (2, 0, False), (4, 1, False), (4, 2, True), (5, 5, True)],
)
def test_the_stress_sets_adoption_rule_needs_two_triggers_and_half_rescued(triggered, rescued, adopt):
    assert core.adoption(triggered, rescued)["adopt"] is adopt


def test_the_bias_test_reproduces_when_the_interval_holds_the_first_runs_offset():
    errors = [-1.2, -1.8, -1.4, -2.0, -1.1, -1.7, -1.5, -1.3, -1.9, -1.6]
    result = core.bias_test(errors)
    mean = sum(errors) / len(errors)
    sd = math.sqrt(sum((e - mean) ** 2 for e in errors) / (len(errors) - 1))
    assert result["se"] == pytest.approx(sd / math.sqrt(10)) and result["interval"] == pytest.approx((mean - 2 * result["se"], mean + 2 * result["se"]))
    assert result["reproduced"] is True and result["correction_supported"] is True
    assert result["corrected_mae"] < result["mae"] and result["corrected_mean"] == pytest.approx(mean + 1.53)


def test_the_bias_test_does_not_reproduce_when_the_bias_is_gone_and_a_correction_is_then_not_offered():
    errors = [0.3, -0.4, 0.1, -0.2, 0.5, -0.1, 0.2, -0.3]
    result = core.bias_test(errors)
    assert result["reproduced"] is False and result["correction_supported"] is False
    assert result["corrected_mae"] > result["mae"]  # removing -1.53 from errors centred on zero makes them worse


def test_a_bias_test_needs_three_errors():
    with pytest.raises(ValueError, match="at least three"):
        core.bias_test([-1.0, -2.0])


# --- the structures ----------------------------------------------------------------------------------------------------------------


def _hydrogens(structure: dict) -> int:
    return sum(1 for s in structure["symbols"] if s == "H")


@pytest.fixture(scope="module")
def stress_structures():
    return run.build_stress_structures()


@pytest.fixture(scope="module")
def heldout_structures():
    return run.build_heldout_structures()


def test_the_stress_set_is_eleven_new_species_and_the_four_controls(stress_structures):
    names = {s["name"] for s in stress_structures}
    controls = {s["name"] for s in stress_structures if s["control"]}
    assert len(names) == 15 and controls == {"H3O+", "toluene", "ethoxyl", "methylthiyl"}
    assert len({s["id"] for s in stress_structures}) == len(stress_structures)
    assert {s["class"] for s in stress_structures} == {"tiny base's conjugate acid", "free methyl rotor", "alkoxyl or thiyl radical"}


def test_every_stress_ion_has_one_hydrogen_more_than_its_base_and_every_radical_one_less_than_its_parent(stress_structures):
    for s in stress_structures:
        parent_h = _hydrogens({"symbols": [a.GetSymbol() for a in run.bde.parent_molecule(s["smiles"]).GetAtoms()]})
        if s["role"] == "ion":
            assert s["charge"] == 1 and s["mult"] == 1 and _hydrogens(s) == parent_h + 1
        elif s["role"] == "radical":
            assert s["charge"] == 0 and s["mult"] == 2 and _hydrogens(s) == parent_h - 1
        else:
            assert s["charge"] == 0 and s["mult"] == 1 and _hydrogens(s) == parent_h


def test_the_heldout_structures_cover_every_bond_once_per_conformer_and_the_hydrogen_atom(heldout_structures):
    bonds = run.heldout_bonds()
    assert len(bonds) == 30 and sum(b["excluded"] for b in bonds) == 3
    assert len({s["id"] for s in heldout_structures}) == len(heldout_structures)
    radicals = [s for s in heldout_structures if s["role"] == "radical"]
    assert {s["bond"] for s in radicals} == {b["name"] for b in bonds}
    assert sum(1 for s in heldout_structures if s["role"] == "atom") == 1
    assert {s["smiles"] for s in heldout_structures if s["role"] == "parent"} == {b["smiles"] for b in bonds}
    assert all(s["mult"] == 2 for s in radicals) and all(s["excluded"] for s in radicals if "isocyanic" in s["bond"] or "hydrazoic" in s["bond"] or "ketene" in s["bond"])


def test_the_heldout_references_are_the_atct_values_in_the_judges_shape():
    for bond in run.heldout_bonds():
        assert set(bond) >= {"name", "smiles", "atom", "dh298", "uncertainty"} and bond["uncertainty"] <= 1.0


# --- the jobs ----------------------------------------------------------------------------------------------------------------------


def test_the_hessian_job_is_a_frequency_calculation_without_an_optimization_at_the_structures_own_charge():
    text = run.hessian_input({"charge": 1, "mult": 1, "symbols": ["O", "H"], "coordinates": [[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]]}, 4)
    assert text.startswith("! M062X def2-TZVPD TightSCF DefGrid3 Freq\n") and "Opt" not in text.splitlines()[0] and "* xyz 1 1" in text and "%pal nprocs 4 end" in text and "Calc_Hess" not in text


class _Orca:
    """A stand-in for ORCA that answers each job with the next scripted output and records the input it was given."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.inputs: list[str] = []

    def __call__(self, input_text: str, want_hessian: bool = False):
        self.inputs.append(input_text)
        answer = self.answers.pop(0)
        if answer == "HESSIAN":
            return "", HESSIAN
        if answer == "NO HESSIAN":
            return "", None
        return answer, None


def _h3o_structure(structures: list[dict]) -> dict:
    return next(s for s in structures if s["name"] == "H3O+")


def _process(structure: dict, orca: _Orca) -> list[dict]:
    records: list[dict] = []
    run.process(structure, 4, orca, "abc123", False, records.append)
    return records


def test_a_planar_ion_that_stays_imaginary_is_restarted_and_one_displaced_result_is_accepted(stress_structures):
    structure = _h3o_structure(stress_structures)
    orca = _Orca([PLANAR_H3O, PLANAR_H3O, "HESSIAN", GOOD_H3O, PLANAR_H3O])
    records = _process(structure, orca)

    assert [(r["structure"], r["stage"]) for r in records] == [
        (structure["id"], "opt"), (structure["id"], "retry"), (f"{structure['id']}#hessian", "hessian"),
        (f"{structure['id']}#restart+", "restart+"), (f"{structure['id']}#restart-", "restart-"), (structure["id"], "closed"),
    ]
    assert "Calc_Hess" not in orca.inputs[0] and "Calc_Hess true" in orca.inputs[1]
    assert orca.inputs[2].startswith("! M062X def2-TZVPD TightSCF DefGrid3 Freq") and all("Calc_Hess true" in text for text in orca.inputs[3:])
    assert records[2]["mode_frequency"] == pytest.approx(-541.61, abs=0.01) and records[2]["hessian_ok"] is True and records[2]["completed"] is False and records[-1]["final"] is True
    # the restart geometries are the retry's final geometry displaced by the preregistered amplitude, in opposite directions
    retried = np.array(records[1]["coordinates"])
    plus, minus = (np.array(r["coordinates"]) for r in (records[3], records[4]))  # these are the OPTIMIZED results; the inputs carry the starts
    starts = [np.array([[float(x) for x in line.split()[1:4]] for line in text.split("* xyz")[1].splitlines()[1:-1]]) for text in orca.inputs[3:]]
    assert np.abs(starts[0] - retried).max() == pytest.approx(core.AMPLITUDE, abs=1e-6) and np.allclose(starts[0] - retried, -(starts[1] - retried), atol=1e-6)
    assert plus.shape == minus.shape == retried.shape
    # exactly the good displaced result is accepted among the structures of the chain
    accepted = [r["structure"] for r in run.bde.accepted(records)]
    assert accepted == [f"{structure['id']}#restart+"]


def test_a_structure_accepted_by_its_first_job_has_no_further_jobs(stress_structures):
    structure = _h3o_structure(stress_structures)
    orca = _Orca([GOOD_H3O])
    records = _process(structure, orca)
    assert [r["stage"] for r in records] == ["opt", "closed"] and len(orca.inputs) == 1


def test_a_structure_the_calc_hess_rerun_repairs_is_not_restarted(stress_structures):
    structure = _h3o_structure(stress_structures)
    orca = _Orca([PLANAR_H3O, GOOD_H3O])
    records = _process(structure, orca)
    assert [r["stage"] for r in records] == ["opt", "retry", "closed"] and len(orca.inputs) == 2


def test_a_hessian_that_cannot_be_read_ends_the_restart_and_the_chain_still_closes(stress_structures):
    structure = _h3o_structure(stress_structures)
    orca = _Orca([PLANAR_H3O, PLANAR_H3O, "NO HESSIAN"])
    records = _process(structure, orca)
    assert [r["stage"] for r in records] == ["opt", "retry", "hessian", "closed"] and records[2]["hessian_ok"] is False and "no Hessian" in records[2]["error"]
    assert len(orca.inputs) == 3 and run.bde.accepted(records) == []


def test_a_job_whose_output_cannot_be_read_is_recorded_with_its_reason_and_is_not_retried(stress_structures):
    structure = _h3o_structure(stress_structures)
    orca = _Orca(["ORCA died with nothing to read"])
    records = _process(structure, orca)
    assert [r["stage"] for r in records] == ["opt", "closed"] and records[0]["completed"] is False and "converge" in records[0]["error"]


def test_a_chain_that_was_interrupted_is_redone_and_a_closed_one_is_not(stress_structures):
    structures = stress_structures[:3]
    records = [{"structure": s["id"], "stage": "closed", "final": True} for s in structures[:2]] + [{"structure": structures[2]["id"], "stage": "opt", "completed": True}]
    assert [s["id"] for s in run.pending(structures, records)] == [structures[2]["id"]]


# --- the reports on synthetic records ------------------------------------------------------------------------------------------------


def _heldout_records(errors: dict[str, float | None], commit: str = "abc123") -> tuple[list[dict], list[dict]]:
    """Records whose DH298 minus reference is exactly the given error for each bond (None = no radical accepted), so the report's arithmetic can be read off."""
    bonds = run.heldout_bonds()
    atom_energy = -0.498135898315
    h_atom = run.bde.core.hydrogen_atom_enthalpy(atom_energy)
    records = [{"structure": "atom|H", "role": "atom", "completed": True, "energy": atom_energy, "commit": commit, "dirty": False}]
    for smiles in sorted({b["smiles"] for b in bonds}):
        records.append({"structure": f"parent|{smiles}|0", "role": "parent", "smiles": smiles, "completed": True, "lowest_frequency": 0.0, "skeleton_kept": True, "enthalpy": -100.0, "s2": None,
                        "commit": commit, "dirty": False})
    for bond in bonds:
        error = errors.get(bond["name"], 0.0)
        if error is None:
            continue
        dh_eh = (bond["dh298"] + error) / run.bde.core.HARTREE_TO_KCAL
        records.append({"structure": f"radical|{bond['name']}|0", "role": "radical", "bond": bond["name"], "smiles": bond["smiles"], "completed": True, "lowest_frequency": 0.0, "skeleton_kept": True,
                        "enthalpy": dh_eh - h_atom + -100.0, "s2": 0.76, "commit": commit, "dirty": False})
    return records, bonds


def test_the_heldout_report_judges_the_twenty_seven_and_only_reports_the_excluded_three():
    bonds = run.heldout_bonds()
    errors = {b["name"]: -1.5 for b in bonds}
    errors.update({b["name"]: 9.0 for b in bonds if b["excluded"]})  # wildly wrong, and must not move the verdict
    records, _ = _heldout_records(errors)
    text, verdict = run.heldout_report(records, bonds)
    assert verdict["verdict"] == "PASS" or verdict["verdict"] == "PARTIAL"
    assert verdict["deciding"]["count"] == 27 and verdict["deciding"]["mse"] == pytest.approx(-1.5, abs=1e-6) and verdict["deciding"]["max_abs"] == pytest.approx(1.5, abs=1e-6)
    assert "(excluded)" in text and "excluded (reported only, deciding nothing): n= 3" in text
    assert verdict["bias"]["n"] == 27 and verdict["classes"]["N-H"]["count"] == 6 and verdict["classes"]["O-H"]["count"] == 2 and verdict["classes"]["C-H"]["count"] == 19


def test_a_bias_exactly_at_the_limit_reads_as_the_first_run_did():
    bonds = run.heldout_bonds()
    records, _ = _heldout_records({b["name"]: -1.6 for b in bonds if not b["excluded"]})
    _text, verdict = run.heldout_report(records, bonds)
    assert verdict["verdict"] == "PARTIAL"  # |MSE| 1.6 > 1.5, MAE under 3.5: the first run's own verdict for this pattern
    assert verdict["bias"]["correction_supported"] is False  # no spread at all, so the interval is a point at -1.6, which excludes -1.53


def test_more_than_three_missing_deciding_bonds_is_not_evaluable():
    bonds = run.heldout_bonds()
    deciding = [b["name"] for b in bonds if not b["excluded"]]
    records, _ = _heldout_records({name: None for name in deciding[:4]})
    _text, verdict = run.heldout_report(records, bonds)
    assert verdict["verdict"] == "NOT EVALUABLE" and verdict["deciding"]["missing"] == 4
    records, _ = _heldout_records({name: None for name in deciding[:3]})
    assert run.heldout_report(records, bonds)[1]["verdict"] != "NOT EVALUABLE"


def test_records_from_two_commits_or_a_dirty_src_are_refused():
    bonds = run.heldout_bonds()
    records, _ = _heldout_records({})
    records[1]["commit"] = "def456"
    text, verdict = run.heldout_report(records, bonds)
    assert verdict["verdict"] == "NOT EVALUABLE" and "REFUSED" in text.splitlines()[0]
    records, _ = _heldout_records({})
    records[2]["dirty"] = True
    assert run.heldout_report(records, bonds)[1]["verdict"] == "NOT EVALUABLE"


def test_a_restart_structure_is_chosen_when_it_is_the_lowest_accepted_one_of_its_species():
    bonds = run.heldout_bonds()
    name = next(b["name"] for b in bonds if not b["excluded"])
    records, _ = _heldout_records({name: None})
    first = next(b for b in bonds if b["name"] == name)
    records += [
        {"structure": f"radical|{name}|0", "role": "radical", "bond": name, "smiles": first["smiles"], "completed": True, "lowest_frequency": -50.0, "skeleton_kept": True, "enthalpy": -99.0, "commit": "abc123", "dirty": False},
        {"structure": f"radical|{name}|0#restart+", "parent_structure": f"radical|{name}|0", "role": "radical", "bond": name, "smiles": first["smiles"], "completed": True, "lowest_frequency": 0.0, "skeleton_kept": True,
         "enthalpy": run.bde.core.HARTREE_TO_KCAL and (first["dh298"] / run.bde.core.HARTREE_TO_KCAL - run.bde.core.hydrogen_atom_enthalpy(-0.498135898315) - 100.0), "s2": 0.76, "commit": "abc123", "dirty": False},
    ]
    _text, verdict = run.heldout_report(records, bonds)
    assert verdict["deciding"]["missing"] == 0  # the unrestarted structure (still imaginary) was not accepted, the restarted one was


def _stress_fixture():
    structures = [{"id": f"parent|s{i}|0", "name": f"s{i}", "control": i == 0, "class": "free methyl rotor"} for i in range(5)]
    return structures


def _stress_records(structures: list[dict], plan: dict[str, str]) -> list[dict]:
    """plan: structure name -> 'ok' (accepted at once), 'rescued' (restart accepted), 'stuck' (restart did not help)."""
    records = []
    for s in structures:
        what = plan[s["name"]]
        base = {"role": "parent", "completed": True, "skeleton_kept": True, "commit": "abc123", "dirty": False}
        if what == "ok":
            records += [dict(base, structure=s["id"], stage="opt", lowest_frequency=0.0, enthalpy=-10.0)]
        else:
            records += [dict(base, structure=s["id"], stage="opt", lowest_frequency=-60.0, enthalpy=-10.0), dict(base, structure=s["id"], stage="retry", lowest_frequency=-50.0, enthalpy=-10.0)]
            records += [dict(base, structure=f"{s['id']}#hessian", stage="hessian", parent_structure=s["id"], mode_frequency=-50.0, completed=False, hessian_ok=True)]
            good = what == "rescued"
            records += [dict(base, structure=f"{s['id']}#restart+", stage="restart+", parent_structure=s["id"], lowest_frequency=0.0 if good else -30.0, enthalpy=-10.001),
                        dict(base, structure=f"{s['id']}#restart-", stage="restart-", parent_structure=s["id"], lowest_frequency=-30.0, enthalpy=-10.0)]
        records.append({"structure": s["id"], "stage": "closed", "final": True, "completed": False, "commit": "abc123", "dirty": False})
    return records


def test_the_stress_report_counts_triggers_and_rescues_and_applies_the_adoption_rule_to_the_new_species_only():
    structures = _stress_fixture()
    plan = {"s0": "stuck", "s1": "rescued", "s2": "rescued", "s3": "ok", "s4": "stuck"}  # s0 is a control that did not help: it must not count
    text, verdict = run.stress_report(_stress_records(structures, plan), structures)
    assert verdict["new"]["triggered_the_restart"] == 3 and verdict["new"]["rescued_by_the_restart"] == 2 and verdict["new"]["accepted_by_the_first_runs_stages"] == 1
    assert verdict["controls"]["triggered_the_restart"] == 1 and verdict["controls"]["rescued_by_the_restart"] == 0
    assert verdict["verdict"] == "ADOPT" and "(control)" in text
    assert "-0.63" in text  # 0.001 Eh lower than the structure it replaced: -0.63 kcal/mol


def test_the_restart_is_not_adopted_when_it_rarely_triggers_or_rarely_helps():
    structures = _stress_fixture()
    plan = {"s0": "ok", "s1": "stuck", "s2": "stuck", "s3": "rescued", "s4": "ok"}
    assert run.stress_report(_stress_records(structures, plan), structures)[1]["verdict"] == "DO NOT ADOPT"  # 1 of 3 rescued
    plan = {"s0": "ok", "s1": "rescued", "s2": "ok", "s3": "ok", "s4": "ok"}
    assert run.stress_report(_stress_records(structures, plan), structures)[1]["verdict"] == "DO NOT ADOPT"  # only one trigger


def test_an_unfinished_stress_run_is_not_evaluable():
    structures = _stress_fixture()
    records = [r for r in _stress_records(structures, {s["name"]: "ok" for s in structures}) if not (r["structure"] == structures[2]["id"] and r.get("final"))]
    assert run.stress_report(records, structures)[1]["verdict"] == "NOT EVALUABLE"


def test_the_runner_writes_its_structures_where_the_report_reads_them(tmp_path, monkeypatch):
    out = tmp_path / "artifacts"
    monkeypatch.setattr(sys, "argv", ["run_restart.py", "structures", "--arm", "stress", "--out", str(out)])
    run.main()
    structures = json.loads((out / "stress" / "structures.json").read_text(encoding="utf-8"))
    assert len(structures) == 18 and all("coordinates" in s for s in structures)


def test_the_constants_are_the_preregistered_ones_written_out_so_that_a_change_to_either_side_is_seen():
    assert core.AMPLITUDE == 0.15 and core.IMAGINARY_CM == -20.0 and core.FIRST_RUN_BIAS == -1.53
    assert (core.ADOPT_MIN_TRIGGERS, core.ADOPT_MIN_RESCUED_FRACTION) == (2, 0.5)
    text = (_DIRECTORY / "PREREGISTRATION.md").read_text(encoding="utf-8")
    assert "+0.15 and by -0.15" in text and "-1.53" in text and "**at least two** structures" in text and "at least half" in text
