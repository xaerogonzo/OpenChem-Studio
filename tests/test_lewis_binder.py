"""The binder: from a molecule's stored runs to the Lewis evidence, or to a gap that says why (`RECIPES_DESIGN.md` 3-5).

No Qt, no RDKit, no ORCA. The runs are real `QuantumChemistryRun` objects carrying real `DescriptorValue`s, and the
host's knowledge of the molecule (`MoleculeFacts`) is typed in, so every rule has a case that breaks exactly it.
"""

from __future__ import annotations

import pytest

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.lewis_binder import MoleculeFacts, bind_molecule, where
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.domain.recipe_run import BindingState

M = "B3LYP def2-SVP"
GEOMETRY_FP, DRAWING_FP = "g" * 64, "d" * 64
MOL = "mol-1"

STATES = BindingState


def _descriptor(descriptor_id: str, value, units: str = "eV") -> DescriptorValue:
    return DescriptorValue(
        descriptor_id=descriptor_id, name=descriptor_id, units=units, category="quantum_chemistry", provider="orca",
        molecule_uuid=MOL, value=value, cache_state=CacheState.COMPLETED,
    )


SP_VALUES = {"orca.homo_energy": -10.17, "orca.lumo_energy": 1.5, "orca.hardness": 5.8}
DSCF_VALUES = {"orca.dscf_hardness": 8.40}


def _run(run_id: str, calc: str = "sp", *, values=None, **kw) -> QuantumChemistryRun:
    values = (SP_VALUES if calc == "sp" else DSCF_VALUES) if values is None else values
    base = dict(
        run_id=run_id, molecule_uuid=MOL, calc_type=calc, method_basis=M, charge=0, multiplicity=1,
        calculation_input="geometry", input_fingerprint=GEOMETRY_FP, input_molblock="molblock", solvent="",
        started_at=100.0, completed_at=110.0, status=RunStatus.COMPLETED,
    )
    base.update(kw)
    run = QuantumChemistryRun(**base)
    run.results["descriptors"] = [_descriptor(k, v) for k, v in values.items()]
    return run


def _facts(*runs, describes=None, fingerprints=None, formal_charge=0, picks=None, label="CO") -> MoleculeFacts:
    return MoleculeFacts(
        molecule_uuid=MOL, label=label, runs=tuple(runs),
        fingerprints={"geometry": GEOMETRY_FP, "drawing": DRAWING_FP} if fingerprints is None else fingerprints,
        describes={r.run_id: True for r in runs} if describes is None else describes,
        formal_charge=formal_charge, picks=picks or {},
    )


def _bind(facts, slot="first", method=M, solvent=""):
    evidence, records = bind_molecule(slot, facts, method_basis=method, solvent=solvent)
    return evidence, {r.target.split("_", 1)[1]: r for r in records}


GOOD = (_run("sp-1"), _run("dscf-1", "delta_scf"))


# --- the plain case ------------------------------------------------------------------------------------------


def test_current_runs_at_the_chosen_level_give_all_three_numbers_with_their_provenance():
    evidence, records = _bind(_facts(*GOOD))
    assert (evidence.homo.value, evidence.lumo.value, evidence.hardness.value) == (-10.17, 1.5, 8.40)
    assert all(r.state is STATES.BOUND for r in records.values())
    homo = evidence.homo.evidence
    assert (homo.run_id, homo.descriptor_id, homo.calc_type, homo.method_basis) == ("sp-1", "orca.homo_energy", "sp", M)
    assert (homo.charge, homo.multiplicity, homo.input_fingerprint, homo.solvent, homo.unit, homo.molecule_uuid) == (
        0, 1, GEOMETRY_FP, "", "eV", MOL)
    assert evidence.hardness.evidence.run_id == "dscf-1" and evidence.hardness.evidence.descriptor_id == "orca.dscf_hardness"


def test_the_records_are_for_the_evaluating_steps_inputs_in_a_fixed_order():
    _, first = bind_molecule("first", _facts(*GOOD), method_basis=M)
    _, second = bind_molecule("second", _facts(*GOOD), method_basis=M)
    assert [(r.step_id, r.target) for r in first] == [
        ("pair", "first_homo"), ("pair", "first_lumo"), ("pair", "first_hardness")]
    assert [r.target for r in second] == ["second_homo", "second_lumo", "second_hardness"]


def test_each_number_is_read_by_its_own_descriptor_id():
    """Every number distinct, so reading the LUMO for the HOMO, or the Koopmans hardness for the delta-SCF one,
    gives a different value and not a similar one."""
    sp = _run("sp-1", values={"orca.homo_energy": -1.11, "orca.lumo_energy": -2.22, "orca.hardness": -3.33})
    dscf = _run("dscf-1", "delta_scf", values={"orca.hardness": -4.44, "orca.dscf_hardness": -5.55})
    evidence, _ = _bind(_facts(sp, dscf))
    assert (evidence.homo.value, evidence.lumo.value, evidence.hardness.value) == (-1.11, -2.22, -5.55)


# --- absent, and present-but-wrong are different sentences ----------------------------------------------------


def test_no_runs_at_all_is_missing_and_says_which_calculation_to_run():
    evidence, records = _bind(_facts())
    assert all(r.state is STATES.MISSING for r in records.values())
    assert "no single-point run" in records["homo"].reason and "no delta-SCF run" in records["hardness"].reason
    assert f"at {where(M, '')}" in records["hardness"].reason
    assert evidence.homo.value is None


def test_a_missing_hardness_leaves_the_frontier_energies_bound():
    evidence, records = _bind(_facts(_run("sp-1")))
    assert records["homo"].state is records["lumo"].state is STATES.BOUND
    assert records["hardness"].state is STATES.MISSING and evidence.hardness.value is None


def test_the_koopmans_hardness_in_a_single_point_is_never_the_hardness():
    """`orca.hardness` is right there in the single point's descriptors, and is not used."""
    evidence, records = _bind(_facts(_run("sp-1")))
    assert SP_VALUES["orca.hardness"] == 5.8 and evidence.hardness.value is None
    assert "no delta-SCF run" in records["hardness"].reason


def test_a_delta_scf_run_with_only_the_koopmans_value_is_a_failure_to_give_the_number():
    dscf = _run("dscf-1", "delta_scf", values={"orca.hardness": 5.8})
    evidence, records = _bind(_facts(dscf))
    assert records["hardness"].state is STATES.FAILED and evidence.hardness.value is None
    assert "orca.dscf_hardness" in records["hardness"].reason


def test_runs_only_at_another_method_are_incompatible_and_the_sentence_names_both_levels():
    runs = (_run("sp-1", method_basis="HF STO-3G"), _run("dscf-1", "delta_scf", method_basis="PBE0 def2-TZVP"))
    evidence, records = _bind(_facts(*runs))
    assert records["homo"].state is STATES.INCOMPATIBLE
    reason = records["homo"].reason
    assert "HF STO-3G (gas phase)" in reason and f"not at {where(M, '')}" in reason and "different scales" in reason
    assert "PBE0 def2-TZVP" in records["hardness"].reason
    assert evidence.homo.value is None


def test_a_solvent_is_part_of_the_level():
    runs = (_run("sp-1", solvent="Water"),)
    _, records = _bind(_facts(*runs))
    assert records["homo"].state is STATES.INCOMPATIBLE and "B3LYP def2-SVP in Water" in records["homo"].reason
    evidence, records = _bind(_facts(*runs), solvent="Water")
    assert records["homo"].state is STATES.BOUND and evidence.homo.evidence.solvent == "Water"
    _, records = _bind(_facts(_run("sp-1")), solvent="Water")
    assert records["homo"].state is STATES.INCOMPATIBLE and "(gas phase)" in records["homo"].reason


def test_a_failed_run_is_failed_not_missing_and_keeps_its_reason():
    failed = _run("sp-bad", status=RunStatus.FAILED, warnings=["SCF did not converge"])
    _, records = _bind(_facts(failed))
    assert records["homo"].state is STATES.FAILED
    assert "sp-bad" in records["homo"].reason and "SCF did not converge" in records["homo"].reason
    assert records["homo"].candidates == ("sp-bad",)


def test_a_failed_run_does_not_hide_a_good_one():
    evidence, records = _bind(_facts(_run("sp-bad", status=RunStatus.FAILED, warnings=["x"]), _run("sp-ok")))
    assert records["homo"].state is STATES.BOUND and evidence.homo.evidence.run_id == "sp-ok"


def test_a_cancelled_run_is_a_person_stopping_it_not_a_fault():
    _, records = _bind(_facts(_run("sp-1", status=RunStatus.CANCELLED)))
    assert records["homo"].state is STATES.MISSING and "cancelled" in records["homo"].reason


def test_a_run_with_warnings_still_gives_its_numbers():
    evidence, _ = _bind(_facts(_run("sp-1", status=RunStatus.COMPLETED_WITH_WARNINGS, warnings=["couplings"])))
    assert evidence.homo.value == -10.17


def test_a_run_at_another_charge_is_a_different_species():
    ion = _run("sp-ion", charge=1)
    _, records = _bind(_facts(ion, formal_charge=0))
    assert records["homo"].state is STATES.INCOMPATIBLE and "+0" in records["homo"].reason and "+1" in records["homo"].reason
    evidence, records = _bind(_facts(ion, formal_charge=1))
    assert records["homo"].state is STATES.BOUND and evidence.homo.evidence.charge == 1


def test_a_run_at_the_wrong_charge_beside_a_right_one_is_set_aside_even_when_it_is_newer():
    """The mixed case: only the neutral run is the molecule's number, though the ion's finished last."""
    neutral = _run("sp-neutral", completed_at=100.0)
    ion = _run("sp-ion", charge=1, completed_at=900.0, values={**SP_VALUES, "orca.homo_energy": -3.0})
    evidence, records = _bind(_facts(neutral, ion, formal_charge=0))
    assert evidence.homo.evidence.run_id == "sp-neutral" and evidence.homo.value == -10.17
    assert records["homo"].candidates == (), "the ion was not a repeat of this job; it was a different species"


def test_an_unknown_formal_charge_skips_the_check_rather_than_refusing():
    evidence, _ = _bind(_facts(_run("sp-ion", charge=1), formal_charge=None))
    assert evidence.homo.value == -10.17


@pytest.mark.parametrize(
    ("values", "text"),
    [
        ({"orca.lumo_energy": 1.5}, "no orca.homo_energy"),
        ({"orca.homo_energy": float("nan")}, "not a number"),
        ({"orca.homo_energy": float("inf")}, "not a number"),
        ({"orca.homo_energy": None}, "not a number"),
        ({"orca.homo_energy": "x"}, "not a number"),
    ],
    ids=["absent", "nan", "inf", "none", "text"],
)
def test_a_finished_run_without_a_usable_number_is_a_failure_that_says_so(values, text):
    _, records = _bind(_facts(_run("sp-1", values=values)))
    assert records["homo"].state is STATES.FAILED and text in records["homo"].reason


def test_a_number_in_another_unit_is_refused_not_converted():
    run = _run("sp-1")
    run.results["descriptors"] = [_descriptor("orca.homo_energy", -0.37, units="hartree")]
    _, records = _bind(_facts(run))
    assert records["homo"].state is STATES.FAILED and "hartree" in records["homo"].reason


# --- is the run this molecule, and at the geometry a run would use now ----------------------------------------


def test_a_run_of_another_structure_is_stale_and_not_used():
    evidence, records = _bind(_facts(_run("sp-1"), describes={"sp-1": False}))
    assert records["homo"].state is STATES.STALE and evidence.homo.value is None
    assert "edited" in records["homo"].reason and records["homo"].candidates == ("sp-1",)


@pytest.mark.parametrize(
    "change",
    [
        {"describes": {"sp-1": None}},
        {"describes": {}},
        {"fingerprints": {"drawing": DRAWING_FP}},
    ],
    ids=["host could not tell", "host said nothing", "no fingerprint for the run's input kind"],
)
def test_a_run_that_cannot_be_shown_to_describe_the_molecule_is_unverifiable_never_fresh(change):
    _, records = _bind(_facts(_run("sp-1"), **change))
    assert records["homo"].state is STATES.UNVERIFIABLE


@pytest.mark.parametrize("blank", [{"input_fingerprint": ""}, {"input_molblock": ""}], ids=["no fingerprint", "no molblock"])
def test_a_run_that_kept_no_input_is_unverifiable(blank):
    _, records = _bind(_facts(_run("sp-1", **blank)))
    assert records["homo"].state is STATES.UNVERIFIABLE


def test_a_run_at_an_earlier_geometry_is_not_used_by_default_and_is_ambiguous_with_its_candidates():
    old = _run("sp-old", input_fingerprint="o" * 64, completed_at=50.0)
    older = _run("sp-older", input_fingerprint="p" * 64, completed_at=10.0)
    evidence, records = _bind(_facts(older, old))
    assert records["homo"].state is STATES.AMBIGUOUS and evidence.homo.value is None
    assert records["homo"].candidates == ("sp-old", "sp-older"), "newest first"
    assert "earlier geometry" in records["homo"].reason and "choose one by run id" in records["homo"].reason.lower()


def test_one_earlier_geometry_is_still_not_used_unasked():
    _, records = _bind(_facts(_run("sp-old", input_fingerprint="o" * 64)))
    assert records["homo"].state is STATES.AMBIGUOUS and records["homo"].candidates == ("sp-old",)


def test_a_current_run_is_used_and_an_earlier_one_beside_it_is_not():
    evidence, records = _bind(_facts(_run("sp-old", input_fingerprint="o" * 64, completed_at=500.0), _run("sp-now")))
    assert evidence.homo.evidence.run_id == "sp-now" and records["homo"].state is STATES.BOUND


def test_a_run_of_the_drawing_is_current_against_the_drawings_fingerprint():
    drawing_run = _run("sp-draw", calculation_input="drawing", input_fingerprint=DRAWING_FP)
    evidence, _ = _bind(_facts(drawing_run))
    assert evidence.homo.evidence.run_id == "sp-draw"


def test_the_precedence_is_current_then_earlier_then_unverifiable_then_stale():
    stale = _run("r-stale")
    unverifiable = _run("r-unv")
    historical = _run("r-old", input_fingerprint="o" * 64)
    describes = {"r-stale": False, "r-unv": None, "r-old": True}
    _, records = _bind(_facts(stale, unverifiable, historical, describes=describes))
    assert records["homo"].state is STATES.AMBIGUOUS and records["homo"].candidates == ("r-old",)
    _, records = _bind(_facts(stale, unverifiable, describes=describes))
    assert records["homo"].state is STATES.UNVERIFIABLE
    _, records = _bind(_facts(stale, describes=describes))
    assert records["homo"].state is STATES.STALE


# --- repeats, and several of one kind --------------------------------------------------------------------------


def test_repeats_of_one_job_use_the_newest_name_the_others_and_record_the_spread():
    a = _run("sp-a", values={**SP_VALUES, "orca.homo_energy": -10.1700}, completed_at=100.0)
    b = _run("sp-b", values={**SP_VALUES, "orca.homo_energy": -10.1706}, completed_at=300.0)
    c = _run("sp-c", values={**SP_VALUES, "orca.homo_energy": -10.1703}, completed_at=200.0)
    evidence, records = _bind(_facts(a, b, c))
    assert evidence.homo.evidence.run_id == "sp-b" and evidence.homo.value == -10.1706
    assert records["homo"].candidates == ("sp-c", "sp-a")
    assert "Newest of 3" in records["homo"].reason and "0.0006" in records["homo"].reason


def test_the_newest_is_decided_by_when_it_finished_not_when_it_started():
    slow_start = _run("sp-late", started_at=1.0, completed_at=900.0)
    quick_start = _run("sp-early", started_at=500.0, completed_at=600.0)
    evidence, _ = _bind(_facts(quick_start, slow_start))
    assert evidence.homo.evidence.run_id == "sp-late"


def test_a_single_run_has_no_repeats_to_name():
    _, records = _bind(_facts(_run("sp-1")))
    assert records["homo"].candidates == () and records["homo"].reason == ""


def test_current_runs_at_two_multiplicities_are_ambiguous_not_averaged_or_picked():
    singlet, triplet = _run("sp-s", multiplicity=1, completed_at=100.0), _run("sp-t", multiplicity=3, completed_at=200.0)
    _, records = _bind(_facts(singlet, triplet))
    assert records["homo"].state is STATES.AMBIGUOUS and records["homo"].candidates == ("sp-t", "sp-s")
    assert "multiplicities 1, 3" in records["homo"].reason


# --- choosing by run id -----------------------------------------------------------------------------------------


def test_a_chosen_earlier_geometry_is_used_and_the_choice_is_recorded():
    old = _run("sp-old", input_fingerprint="o" * 64)
    evidence, records = _bind(_facts(old, picks={"sp": "sp-old"}))
    assert evidence.homo.evidence.run_id == "sp-old" and records["homo"].state is STATES.BOUND
    assert "Chosen by run id" in records["homo"].reason and "earlier geometry" in records["homo"].reason


def test_a_choice_overrides_the_newest_current_run():
    chosen = _run("sp-chosen", completed_at=1.0)
    newer = _run("sp-newer", completed_at=999.0)
    evidence, records = _bind(_facts(chosen, newer, picks={"sp": "sp-chosen"}))
    assert evidence.homo.evidence.run_id == "sp-chosen" and records["homo"].reason == "Chosen by run id."


def test_a_choice_settles_an_ambiguity():
    singlet, triplet = _run("sp-s", multiplicity=1), _run("sp-t", multiplicity=3)
    evidence, _ = _bind(_facts(singlet, triplet, picks={"sp": "sp-t"}))
    assert evidence.homo.evidence.multiplicity == 3


def test_a_choice_names_a_calculation_type_and_leaves_the_other_alone():
    evidence, records = _bind(_facts(_run("sp-1"), _run("dscf-1", "delta_scf"), picks={"sp": "sp-1"}))
    assert records["hardness"].state is STATES.BOUND and records["hardness"].reason == ""
    assert evidence.hardness.evidence.run_id == "dscf-1"


def test_a_choice_serves_both_frontier_numbers_because_one_run_supplies_both():
    run = _run("sp-1")
    evidence, _ = _bind(_facts(run, _run("sp-2", completed_at=999.0), picks={"sp": "sp-1"}))
    assert evidence.homo.evidence.run_id == evidence.lumo.evidence.run_id == "sp-1"


@pytest.mark.parametrize(
    ("pick", "describes", "state"),
    [
        ("nope", {"sp-1": True}, STATES.MISSING),
        ("sp-1", {"sp-1": False}, STATES.STALE),
        ("sp-1", {"sp-1": None}, STATES.UNVERIFIABLE),
    ],
    ids=["no such run", "of another structure", "cannot be shown to describe it"],
)
def test_a_choice_cannot_override_what_the_run_is(pick, describes, state):
    _, records = _bind(_facts(_run("sp-1"), describes=describes, picks={"sp": pick}))
    assert records["homo"].state is state and "chosen" in records["homo"].reason


def test_a_choice_of_a_run_at_another_method_is_not_a_run_of_this_level():
    other = _run("sp-hf", method_basis="HF STO-3G")
    _, records = _bind(_facts(_run("sp-1"), other, picks={"sp": "sp-hf"}))
    assert records["homo"].state is STATES.MISSING


# --- one molecule's runs are not another's -----------------------------------------------------------------------


def test_each_molecule_is_bound_from_its_own_facts_only():
    one = _facts(_run("sp-1", values={"orca.homo_energy": -1.0, "orca.lumo_energy": -2.0}), _run("d-1", "delta_scf", values={"orca.dscf_hardness": 3.0}))
    two = _facts(_run("sp-2", values={"orca.homo_energy": -10.0, "orca.lumo_energy": 20.0}), _run("d-2", "delta_scf", values={"orca.dscf_hardness": 30.0}), label="B")
    first, _ = bind_molecule("first", one, method_basis=M)
    second, _ = bind_molecule("second", two, method_basis=M)
    assert (first.homo.value, first.lumo.value, first.hardness.value) == (-1.0, -2.0, 3.0)
    assert (second.homo.value, second.lumo.value, second.hardness.value) == (-10.0, 20.0, 30.0)
    assert first.label == "CO" and second.label == "B"


def test_a_missing_label_names_the_molecule_by_its_slot_in_sentences():
    _, records = bind_molecule("second", _facts(label=""), method_basis=M)
    assert records[0].reason.startswith("second has no single-point run")


def test_where_names_a_level_with_and_without_a_solvent():
    assert where(M, "") == "B3LYP def2-SVP (gas phase)" and where(M, "DMSO") == "B3LYP def2-SVP in DMSO"
