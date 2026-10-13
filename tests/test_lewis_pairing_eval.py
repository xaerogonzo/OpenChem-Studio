"""The Lewis pairing evaluated over stored runs (`docs/RECIPES_DESIGN.md` sections 4, 8 and 10).

Real RDKit molecules (borane, boron trifluoride, carbon monoxide), real `QuantumChemistryRun` objects carrying the
documented B3LYP/def2-SVP numbers, and the real result codec for the file round trip. No ORCA: the gate that runs
these on real ORCA output is a later slice, and this is what it will be run through.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest
from rdkit import Chem

from openchem.chem.lewis_pairing_eval import RESULT_NAME, PairMember, evaluate_lewis_pairing
from openchem.chem.recipe_host import constitution_key
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.lewis_binder import MoleculeFacts
from openchem.domain.lewis_pairing import LEWIS_PAIRING
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.domain.recipe_run import BindingState, RecipeRunStatus, RecipeRunStore, StepState

M = "B3LYP def2-SVP"
GEOMETRY_FP, DRAWING_FP = "g" * 64, "d" * 64
GAP, HSAB = "Frontier orbital gap", "HSAB hardness match"

# The documented numbers (tests/test_lewis_adduct.py, RECIPES_DESIGN section 10), B3LYP/def2-SVP on real ORCA 6.1.1.
CO = dict(homo=-10.17, lumo=99.0, hardness=8.40)
BH3 = dict(homo=-99.0, lumo=-2.04, hardness=6.77)
BF3 = dict(homo=-98.0, lumo=0.73, hardness=9.29)


def _descriptor(molecule: str, descriptor_id: str, value) -> DescriptorValue:
    return DescriptorValue(
        descriptor_id=descriptor_id, name=descriptor_id, units="eV", category="quantum_chemistry", provider="orca",
        molecule_uuid=molecule, value=value, cache_state=CacheState.COMPLETED,
    )


def _run(molecule: str, run_id: str, calc: str, values: dict, **kw) -> QuantumChemistryRun:
    base = dict(
        run_id=run_id, molecule_uuid=molecule, calc_type=calc, method_basis=M, charge=0, multiplicity=1,
        calculation_input="geometry", input_fingerprint=GEOMETRY_FP, input_molblock="molblock",
        started_at=1.0, completed_at=2.0, status=RunStatus.COMPLETED,
    )
    base.update(kw)
    run = QuantumChemistryRun(**base)
    run.results["descriptors"] = [_descriptor(molecule, k, v) for k, v in values.items()]
    return run


def _runs(molecule: str, numbers: dict, *, hardness: bool = True, **kw) -> list[QuantumChemistryRun]:
    runs = [_run(molecule, f"{molecule}-sp", "sp", {
        "orca.homo_energy": numbers["homo"], "orca.lumo_energy": numbers["lumo"], "orca.hardness": 5.5}, **kw)]
    if hardness:
        runs.append(_run(molecule, f"{molecule}-dscf", "delta_scf", {"orca.dscf_hardness": numbers["hardness"]}, **kw))
    return runs


def _member(smiles: str, uuid: str, label: str, runs, *, charge: int = 0, describes=None) -> PairMember:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return PairMember(
        facts=MoleculeFacts(
            molecule_uuid=uuid, label=label, runs=tuple(runs), fingerprints={"geometry": GEOMETRY_FP, "drawing": DRAWING_FP},
            describes={r.run_id: True for r in runs} if describes is None else describes, formal_charge=charge,
        ),
        mol=mol,
        constitution_key=constitution_key(mol),
    )


def _co(**kw) -> PairMember:
    return _member("[C-]#[O+]", "co", "CO", _runs("co", CO, **{k: v for k, v in kw.items() if k == "hardness"}))


def _bh3() -> PairMember:
    return _member("B", "bh3", "BH3", _runs("bh3", BH3))


def _bf3() -> PairMember:
    return _member("FB(F)F", "bf3", "BF3", _runs("bf3", BF3))


def _lines(run, label: str) -> list[float | None]:
    found = []
    for text in run.result.matched:
        match = re.match(rf"\s*{re.escape(label)}: (?:(-?\d+\.\d+) eV|not available)", text)
        if match:
            found.append(float(match.group(1)) if match.group(1) else None)
    return found


# --- the documented pair -----------------------------------------------------------------------------------------


def test_the_documented_pair_reproduces_through_stored_runs():
    """Frontier gap 8.13 / 10.90 eV and |d eta| 1.63 / 0.89 eV, from numbers read out of runs and not typed into
    the report. The borane and boron trifluoride are the acid, as the gate (section 10) sets it: boron
    trifluoride's fluorine lone pairs make it structurally admissible as a base too, so left to `auto` it reports
    both ways round, which is the calculator being right and not what is being reproduced here."""
    bh3 = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M, role="acid")
    bf3 = evaluate_lewis_pairing(_bf3(), _co(), method_basis=M, role="acid")
    assert _lines(bh3, GAP) == [pytest.approx(8.13)] and _lines(bf3, GAP) == [pytest.approx(10.90)]
    assert _lines(bh3, HSAB) == [pytest.approx(1.63)] and _lines(bf3, HSAB) == [pytest.approx(0.89)]


def test_the_two_orbital_lines_still_disagree_on_carbon_monoxide():
    """The headline: the frontier gap prefers borane and the HSAB match prefers boron trifluoride. A recipe that
    'fixes' this has altered the chemistry."""
    bh3 = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M, role="acid")
    bf3 = evaluate_lewis_pairing(_bf3(), _co(), method_basis=M, role="acid")
    assert _lines(bh3, GAP)[0] < _lines(bf3, GAP)[0]
    assert _lines(bf3, HSAB)[0] < _lines(bh3, HSAB)[0]


def test_a_complete_pairing_is_completed_with_every_step_and_binding_accounted_for():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    assert run.status is RecipeRunStatus.COMPLETED
    assert all(s.state is StepState.COMPLETED for s in run.steps)
    assert len(run.bindings) == 6 and all(b.state is BindingState.BOUND for b in run.bindings)
    assert isinstance(run.result.matched, list)


def test_the_steps_are_the_recipes_steps_in_the_recipes_order():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    assert [s.step_id for s in run.steps] == [s.step_id for s in LEWIS_PAIRING.steps]
    assert run.recipe_id == LEWIS_PAIRING.recipe_id and run.recipe_version == LEWIS_PAIRING.version


def test_the_bindings_are_the_evaluating_steps_six_optional_inputs():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    pair = next(s for s in LEWIS_PAIRING.steps if s.step_id == "pair")
    optional = [b.target for b in pair.bindings if b.optional]
    assert [b.target for b in run.bindings] == optional
    assert {b.step_id for b in run.bindings} == {"pair"}


def test_the_numbers_are_copied_into_the_run_with_their_provenance():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    by_target = {b.target: b.evidence for b in run.bindings}
    assert by_target["first_lumo"].value == -2.04 and by_target["first_lumo"].run_id == "bh3-sp"
    assert by_target["second_homo"].value == -10.17 and by_target["second_homo"].molecule_uuid == "co"
    assert by_target["second_hardness"].descriptor_id == "orca.dscf_hardness" and by_target["second_hardness"].calc_type == "delta_scf"
    assert all(e.method_basis == M and e.unit == "eV" for e in by_target.values())


def test_the_koopmans_hardness_in_the_single_point_is_present_and_never_read():
    """Every sp run here carries `orca.hardness` = 5.5; no line may use it."""
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    assert _lines(run, HSAB) == [pytest.approx(1.63)]
    assert all(b.evidence.value != 5.5 for b in run.bindings)


# --- order, and who is the acid ---------------------------------------------------------------------------------


def test_slot_order_is_not_part_of_the_answer():
    one = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    other = evaluate_lewis_pairing(_co(), _bh3(), method_basis=M)
    assert _lines(one, GAP) == _lines(other, GAP) and _lines(one, HSAB) == _lines(other, HSAB)


def test_the_role_is_the_role_of_the_first_molecule():
    explicit = evaluate_lewis_pairing(_co(), _bh3(), method_basis=M, role="base")
    assert _lines(explicit, GAP) == [pytest.approx(8.13)]
    assert dict(explicit.parameters)["role"] == "base"
    refused = evaluate_lewis_pairing(_co(), _bh3(), method_basis=M, role="acid")
    assert refused.result is None, "carbon monoxide has nothing to accept"


def test_the_inputs_name_both_molecules_with_their_constitution_and_drawing_fingerprint():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    first, second = run.inputs
    assert (first.slot, first.molecule_uuid, second.slot, second.molecule_uuid) == ("first", "bh3", "second", "co")
    assert first.constitution_key == constitution_key(Chem.MolFromSmiles("B")) and first.drawing_fingerprint == DRAWING_FP


def test_the_parameters_are_recorded_so_the_answer_can_be_reproduced():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M, solvent="", role="acid")
    assert dict(run.parameters) == {"method_basis": M, "solvent": "", "role": "acid"}


# --- the report --------------------------------------------------------------------------------------------------


def test_the_result_is_filed_as_the_recipes_not_the_calculators():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    assert run.result.report_id == "lewis_pairing" and run.result.name == RESULT_NAME
    assert run.result.report_id != "lewis_adduct"


def test_the_result_says_where_it_came_from():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    provenance = run.result.provenance
    assert provenance.method == "recipe:lewis_pairing:1"
    assert provenance.parameters["recipe_run_id"] == run.run_id and provenance.parameters["method_basis"] == M
    assert provenance.parameters["orientation_basis"] == "site_admissibility", "the calculator's own record is kept"


def test_renaming_the_report_does_not_put_its_old_name_in_front_of_every_plain_line():
    run = evaluate_lewis_pairing(_bh3(), _co(hardness=False), method_basis=M)
    assert not [line for line in run.result.matched if line.startswith("Lewis Adduct")]
    assert any(line.startswith("Role:") for line in run.result.matched)
    assert any("HSAB hardness match: not available" in line for line in run.result.matched)


def test_the_report_carries_the_evidence_block_and_no_combined_score():
    run = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    labels = [f.label for f in run.result.facts]
    assert "BH3: E(LUMO)" in labels and "CO: E(HOMO)" in labels and "CO: Chemical hardness (delta-SCF)" in labels
    for word in ("score", "combined", "overall"):
        assert not any(word in label.lower() for label in labels)


# --- gaps --------------------------------------------------------------------------------------------------------


def test_a_missing_hardness_makes_the_pairing_partial_and_keeps_the_frontier_line():
    run = evaluate_lewis_pairing(_bh3(), _co(hardness=False), method_basis=M)
    assert run.status is RecipeRunStatus.PARTIAL
    assert _lines(run, GAP) == [pytest.approx(8.13)] and _lines(run, HSAB) == [None]
    assert run.result is not None
    blocked = [s for s in run.steps if s.state is StepState.BLOCKED]
    assert [s.step_id for s in blocked] == ["dscf_second"]
    assert "CO has no delta-SCF run" in blocked[0].reason
    assert {b.target: b.state for b in run.bindings}["second_hardness"] is BindingState.MISSING


def test_a_job_that_gave_one_of_its_two_numbers_is_blocked_not_satisfied():
    """The single point supplies BOTH frontier energies; a run with the HOMO and no LUMO leaves the job unsatisfied."""
    half = _run("co", "co-sp", "sp", {"orca.homo_energy": CO["homo"]})
    dscf = _run("co", "co-dscf", "delta_scf", {"orca.dscf_hardness": CO["hardness"]})
    run = evaluate_lewis_pairing(_bh3(), _member("[C-]#[O+]", "co", "CO", [half, dscf]), method_basis=M, role="acid")
    states = {b.target: b.state for b in run.bindings}
    assert states["second_homo"] is BindingState.BOUND and states["second_lumo"] is BindingState.FAILED
    assert {s.step_id: s.state for s in run.steps}["sp_second"] is StepState.BLOCKED
    assert run.status is RecipeRunStatus.PARTIAL


def test_the_gap_list_is_in_the_run_as_sentences():
    run = evaluate_lewis_pairing(_bh3(), _co(hardness=False), method_basis=M)
    gaps = [b.reason for b in run.bindings if b.state is not BindingState.BOUND]
    assert gaps == ["CO has no delta-SCF run. Run one in the Quantum Chemistry panel at B3LYP def2-SVP (gas phase)."]


def test_runs_at_another_method_are_reported_as_such_not_as_missing():
    other = _member("[C-]#[O+]", "co", "CO", _runs("co", CO, method_basis="HF STO-3G"))
    run = evaluate_lewis_pairing(_bh3(), other, method_basis=M)
    states = {b.target: b.state for b in run.bindings}
    assert states["second_homo"] is states["second_hardness"] is BindingState.INCOMPATIBLE
    # BH3's own numbers exist, but CO supplies none, so no line can be evaluated: a gap list, not a report.
    assert run.result is None and run.status is RecipeRunStatus.PARTIAL


def test_a_pair_with_no_evidence_and_no_tabulated_enthalpy_is_blocked_not_a_report_of_nothing():
    run = evaluate_lewis_pairing(
        _member("B", "bh3", "BH3", []), _member("[C-]#[O+]", "co", "CO", []), method_basis=M
    )
    assert run.status is RecipeRunStatus.BLOCKED and run.result is None
    pair = run.steps[-1]
    assert pair.state is StepState.BLOCKED and "No line of evidence could be evaluated" in pair.reason
    assert all(s.state is StepState.BLOCKED for s in run.steps)


def test_a_pair_that_cannot_form_an_adduct_is_refused_with_the_reason_and_a_limit_kind():
    methane = _member("C", "ch4", "methane", _runs("ch4", dict(homo=-1.0, lumo=1.0, hardness=3.0)))
    ethane = _member("CC", "c2h6", "ethane", _runs("c2h6", dict(homo=-2.0, lumo=2.0, hardness=4.0)))
    run = evaluate_lewis_pairing(methane, ethane, method_basis=M)
    pair = run.steps[-1]
    assert pair.state is StepState.REFUSED and pair.refusal_kind == "limit"
    assert "accept an electron pair" in pair.reason
    assert run.result is None and run.status is RecipeRunStatus.PARTIAL, "the four jobs were satisfied; the answer is a refusal"


def test_an_edited_molecule_loses_its_evidence_and_the_sentence_says_so():
    runs = _runs("co", CO)
    edited = _member("[C-]#[O+]", "co", "CO", runs, describes={r.run_id: False for r in runs})
    run = evaluate_lewis_pairing(_bh3(), edited, method_basis=M)
    assert {b.target: b.state for b in run.bindings}["second_homo"] is BindingState.STALE
    assert run.result is None, "the stale number is not used, so no line could be evaluated"
    assert "edited" in next(b for b in run.bindings if b.target == "second_homo").reason


def test_the_evidence_of_one_molecule_is_never_used_for_the_other():
    """Distinct sentinel for every number, in both slots."""
    first = _member("B", "m1", "First", _runs("m1", dict(homo=-1.1, lumo=-2.2, hardness=3.3)))
    second = _member("[C-]#[O+]", "m2", "Second", _runs("m2", dict(homo=-10.4, lumo=20.5, hardness=30.6)))
    run = evaluate_lewis_pairing(first, second, method_basis=M)
    assert _lines(run, GAP) == [pytest.approx(8.2)]  # -2.2 - (-10.4)
    assert _lines(run, HSAB) == [pytest.approx(27.3)]  # |3.3 - 30.6|


# --- the arguments ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "text"),
    [
        (dict(method_basis="HF STO-3G"), "not one of the presets"),
        (dict(method_basis=M, solvent="Ethanol"), "solvent"),
        (dict(method_basis=M, role="stronger"), "role"),
    ],
    ids=["method not a preset", "solvent not offered", "role not a code"],
)
def test_an_argument_that_is_not_one_of_the_recipes_choices_is_a_caller_error(kwargs, text):
    with pytest.raises(ValueError, match=text):
        evaluate_lewis_pairing(_bh3(), _co(), **kwargs)


def test_every_evaluation_is_a_new_run():
    one = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    two = evaluate_lewis_pairing(_bh3(), _co(), method_basis=M)
    assert one.run_id != two.run_id and _lines(one, GAP) == _lines(two, GAP)


# --- through a file ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("which", ["complete", "partial", "blocked", "refused"])
def test_every_kind_of_run_this_produces_survives_a_project_file(which):
    runs = {
        "complete": lambda: evaluate_lewis_pairing(_bh3(), _co(), method_basis=M),
        "partial": lambda: evaluate_lewis_pairing(_bh3(), _co(hardness=False), method_basis=M),
        "blocked": lambda: evaluate_lewis_pairing(
            _member("B", "bh3", "BH3", []), _member("[C-]#[O+]", "co", "CO", []), method_basis=M),
        "refused": lambda: evaluate_lewis_pairing(
            _member("C", "a", "methane", []), _member("CC", "b", "ethane", []), method_basis=M),
    }
    run = runs[which]()
    store = RecipeRunStore("project")
    store.record(run)
    [loaded] = RecipeRunStore.from_dict(json.loads(json.dumps(store.to_dict())), "project").all_runs()
    assert loaded.status is run.status and loaded.steps == run.steps and loaded.bindings == run.bindings
    assert loaded.inputs == run.inputs and loaded.parameters == run.parameters
    assert (loaded.result is None) == (run.result is None)
    if run.result is not None:
        assert loaded.result.matched == run.result.matched and loaded.result.provenance.method == run.result.provenance.method


def test_a_run_with_an_ambiguous_binding_keeps_its_candidates_through_a_file():
    runs = [
        _run("co", "co-sp-old", "sp", {"orca.homo_energy": -10.0, "orca.lumo_energy": 1.0}, input_fingerprint="o" * 64, completed_at=5.0),
        _run("co", "co-sp-older", "sp", {"orca.homo_energy": -11.0, "orca.lumo_energy": 2.0}, input_fingerprint="p" * 64, completed_at=3.0),
    ]
    run = evaluate_lewis_pairing(_bh3(), _member("[C-]#[O+]", "co", "CO", runs), method_basis=M)
    store = RecipeRunStore("project")
    store.record(run)
    [loaded] = RecipeRunStore.from_dict(json.loads(json.dumps(store.to_dict())), "project").all_runs()
    homo = next(b for b in loaded.bindings if b.target == "second_homo")
    assert homo.state is BindingState.AMBIGUOUS and homo.candidates == ("co-sp-old", "co-sp-older")
