"""An ORCA job the assistant asks for and a person approves, at the host (dispatch, step 2 of `docs/AI_CALCULATION_BRIDGE.md`, section 17).

`CalculationHost` decides nothing about an ORCA job. It prepares a card from the frozen turn, holds it until a person approves, hands the settings to the Quantum Chemistry panel through the one
method the window gave it (`QuantumStarter`), and ends the run when ORCA's own run record arrives. These pin that, with a recording starter in place of the panel so no ORCA is involved: what the
card carries, that nothing starts before Approve, what is handed over, and each way the run ends.
"""

from __future__ import annotations

import dataclasses
import shutil

import pytest
from test_calculation_host import ETHANOL, _World

from openchem.chem.quantum_run_request import TWO_PARTNERS_MESSAGE, RunChoice
from openchem.domain.calculation_bridge import ProblemCode, Route
from openchem.domain.common import CacheState
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.domain.quantum_dispatch import STARTABLE
from openchem.domain.run_lifecycle import RunState
from openchem.events.events import QuantumChemistryJobStateChanged, QuantumChemistryRunCompleted

DIMER = "O.O"


class _Starter:
    """What the window gives the host in place of the Quantum Chemistry panel: records the hand-over and answers as told."""

    def __init__(self, answer: str = "") -> None:
        self.calls: list[tuple[str, RunChoice, str]] = []
        self.answer = answer
        self.during = None

    def start_assistant_run(self, molecule_uuid, choice, input_fingerprint):
        self.calls.append((molecule_uuid, choice, input_fingerprint))
        if self.during is not None:
            self.during()
        return self.answer


@pytest.fixture
def world(qapp, tmp_path, monkeypatch):
    """A world whose host has a starter, whose molecule has a conformer, and whose ORCA is 'set up' (nothing is ever run)."""
    world = _World(qapp)
    world.starter = _Starter()
    world.host.set_quantum_starter(world.starter)
    world.add_conformer(world.molecule)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    fake = tmp_path / "orca.exe"
    fake.write_text("not really")
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", str(fake))
    return world


def prepare(world, calculator_id="orca.sp", parameters=None, turn=None):
    return world.host.prepare(turn or world.host.begin_turn(), calculator_id, parameters or {})


def approve(world, run_id):
    return world.host.approve(run_id)


def completed(world, preparation, *, status=RunStatus.COMPLETED, run_id="orca-run-1", **changes):
    """ORCA's run record for the approved job, as the service publishes it when the job ends."""
    fields = dict(
        run_id=run_id, molecule_uuid=preparation.molecule_uuid, calc_type=STARTABLE[preparation.calculator_id], method_basis=preparation.parameters["method_basis"], charge=0, multiplicity=1,
        calculation_input="geometry", input_fingerprint=preparation.input_fingerprint, input_molblock="", status=status,
    )
    fields.update(changes)
    world.services.event_bus.publish(QuantumChemistryRunCompleted(run=QuantumChemistryRun(**fields)))
    world.qapp.processEvents()


# --- what the card says, and that saying it starts nothing ------------------------------------------------------------------------------------------


def test_with_a_starter_the_single_job_orca_calculators_need_approval_and_the_others_stay_where_they_were(world):
    for calculator_id in STARTABLE:
        assert world.host.describe(calculator_id).route is Route.NEEDS_APPROVAL, calculator_id
    for calculator_id in ("orca.fukui", "docking.vina", "lewis_hsab"):
        assert world.host.describe(calculator_id).route is Route.PREVIEW_ONLY, calculator_id


def test_without_a_starter_nothing_is_offered_that_could_not_be_approved(world):
    world.host.set_quantum_starter(None)
    assert world.host.describe("orca.sp").route is Route.PREVIEW_ONLY
    result = prepare(world)
    assert not result.ok and result.service_preview is not None and [p.code for p in result.problems] == [ProblemCode.SERVICE_RUN]


def test_a_prepared_job_is_a_card_with_every_setting_and_nothing_has_started(world):
    result = prepare(world, "orca.opt", {"charge": 1, "multiplicity": 2, "method_basis": "PBE0 def2-TZVP"})
    assert result.ok
    preparation = result.preparation
    assert preparation.route is Route.NEEDS_APPROVAL and world.host.state_of(preparation.run_id) is RunState.PREVIEWED
    assert dict(preparation.parameters) == {"charge": 1, "multiplicity": 2, "method_basis": "PBE0 def2-TZVP"}
    text = "\n".join(preparation.preview)
    assert "Aspirin" in text and "charge=1" in text and "multiplicity=2" in text and "PBE0 def2-TZVP" in text
    assert "Quantum Chemistry panel's Run button" in text and "where it can be cancelled" in text
    assert preparation.external_tools == ("orca",) and "ORCA runs for minutes to hours" in preparation.decision.reason
    assert world.starter.calls == [] and world.host.pending() == (preparation,)


def test_the_card_is_bound_to_the_conformer_every_calculation_uses(world):
    turn = world.host.begin_turn()
    preparation = prepare(world, turn=turn).preparation
    assert preparation.calculation_input == "geometry" and preparation.input_fingerprint == turn.fingerprints["geometry"] != turn.fingerprints["drawing"]


def test_asking_to_run_the_previewed_job_again_starts_nothing(world):
    """The tool-facing `run` is what a model's repeated request reaches; for a job that needs a person it only reports the preview."""
    turn = world.host.begin_turn()
    preparation = prepare(world, turn=turn).preparation
    thread, box = world.run_in_worker(turn, preparation.run_id, timeout=1.0)
    outcome = world.finish(thread, box, run_pool=False)
    assert outcome.state is RunState.PREVIEWED and "needs a person to approve" in outcome.message
    assert world.starter.calls == [] and world.host.state_of(preparation.run_id) is RunState.PREVIEWED


@pytest.mark.parametrize("parameters, code, parameter", [
    ({"method_basis": "not a method"}, ProblemCode.NOT_A_CHOICE, "method_basis"),
    ({"charge": 99}, ProblemCode.OUT_OF_RANGE, "charge"),
    ({"charge": "one"}, ProblemCode.WRONG_TYPE, "charge"),
    ({"solvent": "water"}, ProblemCode.UNKNOWN_PARAMETER, "solvent"),
])
def test_a_setting_the_calculator_does_not_take_is_refused_before_a_card_exists(world, parameters, code, parameter):
    result = prepare(world, "orca.sp", parameters)
    assert [(p.code, p.parameter) for p in result.problems] == [(code, parameter)] and result.service_preview is None and world.host.pending() == ()


def test_a_molecule_with_no_conformer_is_not_ready_and_says_what_to_do(world):
    ethanol = world.add(ETHANOL, "Ethanol")
    result = prepare(world, "orca.sp")
    assert [p.code for p in result.problems] == [ProblemCode.NOT_READY] and "3D conformer for Ethanol" in result.problems[0].message
    assert "generate conformers" in result.problems[0].message and world.host.pending() == () and ethanol is not None


def test_no_orca_is_not_ready_and_says_where_to_set_it_up(world):
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    result = prepare(world, "orca.sp")
    assert [p.code for p in result.problems] == [ProblemCode.NOT_READY] and "ORCA executable" in result.problems[0].message and "External Tools" in result.problems[0].message


def test_a_blank_molecule_has_no_structure_to_calculate(world):
    world.add(None, "Blank")
    assert [p.code for p in prepare(world).problems] == [ProblemCode.NO_STRUCTURE]


def test_an_interaction_breakdown_of_one_species_is_refused_before_a_card_and_of_two_shows_what_it_costs(world):
    assert [p.code for p in prepare(world, "orca.led").problems] == [ProblemCode.INVALID_STRUCTURE]
    assert prepare(world, "orca.led").problems[0].message == TWO_PARTNERS_MESSAGE
    dimer = world.add(DIMER, "Water dimer")
    world.add_conformer(dimer)
    result = prepare(world, "orca.led")
    assert result.ok
    text = "\n".join(result.preparation.preview)
    assert "What it would cost (approving accepts it)" in text and "basis functions, DLPNO-CCSD(T)" in text


# --- proton affinity: a fixed protocol, run on the drawing ------------------------------------------------------------------------------------


def base(world, smiles="N", name="Ammonia"):
    """A molecule with a structure and NO conformer: the protocol embeds every structure fresh."""
    return world.add(smiles, name)


def test_proton_affinity_needs_no_conformer_and_is_a_card_with_the_cost(world):
    base(world)
    turn = world.host.begin_turn()
    result = prepare(world, "orca.proton_affinity", turn=turn)
    assert result.ok, result.problems
    preparation = result.preparation
    assert preparation.calculation_input == "drawing" and preparation.input_fingerprint == turn.fingerprints["drawing"] and preparation.drawing_fingerprint == ""
    text = "\n".join(preparation.preview)
    assert "embedded fresh" in text and "Proton affinity button" in text and "What it would cost (approving accepts it)" in text
    assert "2 ORCA geometry optimizations" in text and "minutes to hours" in text and "conformer" not in text.replace("no conformer", "")
    assert world.starter.calls == [] and world.host.state_of(preparation.run_id) is RunState.PREVIEWED


def test_a_base_outside_what_was_measured_says_so_on_the_card(world):
    base(world, "CCl", "Chloroethane")
    text = "\n".join(prepare(world, "orca.proton_affinity").preparation.preview)
    assert "outside what the benchmark measured" in text and "Cl:" in text


def test_a_base_the_protocol_cannot_compute_is_refused_before_a_card(world):
    base(world, "C[N+](C)(C)C", "Tetramethylammonium")
    result = prepare(world, "orca.proton_affinity")
    assert [p.code for p in result.problems] == [ProblemCode.INVALID_STRUCTURE] and "does not apply" in result.problems[0].message and world.host.pending() == ()


def test_proton_affinity_without_orca_is_not_ready(world):
    base(world)
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    assert [p.code for p in prepare(world, "orca.proton_affinity").problems] == [ProblemCode.NOT_READY]


def test_approving_proton_affinity_hands_over_the_protocol_and_the_drawings_fingerprint(world):
    ammonia = base(world)
    preparation = prepare(world, "orca.proton_affinity").preparation
    assert approve(world, preparation.run_id) is RunState.RUNNING
    [(molecule_uuid, choice, fingerprint)] = world.starter.calls
    assert molecule_uuid == ammonia.uuid and choice.calc_type == "proton_affinity" and fingerprint == preparation.input_fingerprint
    completed(world, preparation, calc_type="proton_affinity", calculation_input="drawing", status=RunStatus.COMPLETED)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED] and world.host._quantum_inflight == {}


def test_editing_the_drawing_after_a_proton_affinity_card_withdraws_it(world):
    ammonia = base(world)
    preparation = prepare(world, "orca.proton_affinity").preparation
    world.engine.set_structure_from_smiles(ammonia, "CN")
    assert approve(world, preparation.run_id) is RunState.INVALIDATED and world.starter.calls == []


# --- Approve starts it, by the panel's rules, and nothing else does ---------------------------------------------------------------------------------


def test_approving_hands_the_panel_exactly_the_settings_the_card_showed(world):
    preparation = prepare(world, "orca.nmr", {"charge": -1, "multiplicity": 1, "method_basis": "PBE0 def2-TZVP"}).preparation
    assert approve(world, preparation.run_id) is RunState.RUNNING
    [(molecule_uuid, choice, fingerprint)] = world.starter.calls
    assert molecule_uuid == world.molecule.uuid and fingerprint == preparation.input_fingerprint
    assert choice == RunChoice(calc_type="nmr", method_basis="PBE0 def2-TZVP", charge=-1, multiplicity=1)
    assert world.outcomes == [], "handing it over is not the job ending"


def test_an_open_shell_spin_state_is_handed_over_as_chosen(world):
    preparation = prepare(world, "orca.sp", {"charge": 1, "multiplicity": 2}).preparation
    approve(world, preparation.run_id)
    assert (world.starter.calls[0][1].charge, world.starter.calls[0][1].multiplicity) == (1, 2)


def test_each_startable_calculator_hands_over_its_own_calculation_type(world):
    seen = {}
    for calculator_id in ("orca.sp", "orca.opt", "orca.opt_freq", "orca.nmr", "orca.nmr_coupling", "orca.delta_scf"):
        preparation = prepare(world, calculator_id).preparation
        approve(world, preparation.run_id)
        seen[calculator_id] = world.starter.calls[-1][1].calc_type
        completed(world, preparation)
    assert seen == {"orca.sp": "sp", "orca.opt": "opt", "orca.opt_freq": "opt_freq", "orca.nmr": "nmr", "orca.nmr_coupling": "nmr_coupling", "orca.delta_scf": "delta_scf"}


def test_nothing_but_approve_hands_anything_over(world):
    preparation = prepare(world).preparation
    for _ in range(3):
        world.qapp.processEvents()
    assert world.starter.calls == [] and world.host.state_of(preparation.run_id) is RunState.PREVIEWED
    assert world.host.cancel(preparation.run_id) is True
    assert approve(world, preparation.run_id) is RunState.CANCELLED and world.starter.calls == []


def test_the_run_ends_when_orcas_run_record_arrives_and_not_before(world):
    preparation = prepare(world).preparation
    approve(world, preparation.run_id)
    assert world.host.state_of(preparation.run_id) is RunState.RUNNING
    completed(world, preparation)
    [outcome] = world.outcomes
    assert outcome.run_id == preparation.run_id and outcome.state is RunState.COMPLETED and outcome.stored is None and not outcome.has_number
    assert "orca-run-1" in outcome.message and "read_quantum_runs" in outcome.message
    assert world.host.state_of(preparation.run_id) is RunState.COMPLETED
    assert world.host._quantum_inflight == {}, "a finished job is no longer waited for"


@pytest.mark.parametrize("status, state, fragments", [
    (RunStatus.COMPLETED, RunState.COMPLETED, ["ORCA finished the job."]),
    (RunStatus.COMPLETED_WITH_WARNINGS, RunState.COMPLETED, ["reported 2 warning(s)"]),
    (RunStatus.FAILED, RunState.FAILED, ["did not produce a result", "no numbers"]),
    (RunStatus.CANCELLED, RunState.CANCELLED, ["cancelled before it finished", "Quantum Chemistry panel", "no numbers"]),
])
def test_each_way_the_job_can_end_is_told_in_the_applications_words(world, status, state, fragments):
    preparation = prepare(world).preparation
    approve(world, preparation.run_id)
    completed(world, preparation, status=status, warnings=["a", "b"])
    [outcome] = world.outcomes
    assert outcome.state is state and world.host.state_of(preparation.run_id) is state
    for fragment in fragments:
        assert fragment in outcome.message
    assert "read_quantum_runs" in outcome.message


def test_a_run_record_of_something_else_does_not_end_the_approved_job(world):
    other = world.add(ETHANOL, "Ethanol", select=False)
    preparation = prepare(world).preparation
    approve(world, preparation.run_id)
    completed(world, preparation, molecule_uuid=other.uuid)
    completed(world, preparation, calc_type="opt")
    completed(world, preparation, input_fingerprint="another conformer")
    assert world.outcomes == [] and world.host.state_of(preparation.run_id) is RunState.RUNNING
    completed(world, preparation)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED]


def test_a_second_run_record_for_a_finished_job_is_ignored(world):
    preparation = prepare(world).preparation
    approve(world, preparation.run_id)
    completed(world, preparation)
    completed(world, preparation, run_id="orca-run-2", status=RunStatus.FAILED)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED] and world.host.state_of(preparation.run_id) is RunState.COMPLETED


# --- the ways it does not start ---------------------------------------------------------------------------------------------------------------


def test_the_panels_refusal_is_the_runs_outcome_in_its_own_words(world):
    world.starter.answer = "This panel is busy with another calculation. Nothing was started."
    preparation = prepare(world).preparation
    assert approve(world, preparation.run_id) is RunState.REFUSED
    [outcome] = world.outcomes
    assert outcome.state is RunState.REFUSED and outcome.message == world.starter.answer
    # The job is not in flight, so a run record that arrives later for the same molecule is nobody's.
    assert world.host._quantum_inflight == {}
    completed(world, preparation)
    assert len(world.outcomes) == 1


def test_a_failure_the_service_says_while_the_job_is_handed_over_ends_the_run(world):
    def service_says_no():
        world.services.event_bus.publish(QuantumChemistryJobStateChanged(molecule_uuid=world.molecule.uuid, state=CacheState.FAILED, message="No ORCA executable is configured."))
        world.qapp.processEvents()

    world.starter.during = service_says_no
    preparation = prepare(world).preparation
    assert approve(world, preparation.run_id) is RunState.FAILED
    [outcome] = world.outcomes
    assert outcome.state is RunState.FAILED and outcome.message == "No ORCA executable is configured."


def test_a_failed_state_of_a_job_already_going_is_left_to_its_run_record(world):
    preparation = prepare(world).preparation
    approve(world, preparation.run_id)
    world.services.event_bus.publish(QuantumChemistryJobStateChanged(molecule_uuid=world.molecule.uuid, state=CacheState.FAILED, message="ORCA exited with code 1"))
    world.qapp.processEvents()
    assert world.outcomes == [] and world.host.state_of(preparation.run_id) is RunState.RUNNING
    completed(world, preparation, status=RunStatus.FAILED)
    assert [o.state for o in world.outcomes] == [RunState.FAILED]


def test_a_starter_that_raises_is_a_failed_run_and_not_a_crash(world):
    def boom():
        raise RuntimeError("the panel was destroyed")

    world.starter.during = boom
    preparation = prepare(world).preparation
    assert approve(world, preparation.run_id) is RunState.REFUSED
    assert "the panel was destroyed" in world.outcomes[0].message


def test_editing_the_structure_after_the_card_withdraws_it_and_hands_nothing_over(world):
    preparation = prepare(world).preparation
    world.engine.set_structure_from_smiles(world.molecule, ETHANOL)
    assert approve(world, preparation.run_id) is RunState.INVALIDATED
    assert world.starter.calls == [] and "structure was edited" in world.outcomes[0].message


def test_a_drawing_edited_while_the_conformer_is_unchanged_still_withdraws_the_card(world):
    """The conformer keeps its fingerprint when the drawing is edited, which is why the card is bound to both."""
    turn = world.host.begin_turn()
    preparation = prepare(world, turn=turn).preparation
    assert preparation.drawing_fingerprint == turn.fingerprints["drawing"] != ""
    before = world.services.result_store_service.fingerprints_for(world.molecule)["geometry"]
    world.engine.set_structure_from_smiles(world.molecule, ETHANOL)
    assert world.services.result_store_service.fingerprints_for(world.molecule)["geometry"] == before
    assert approve(world, preparation.run_id) is RunState.INVALIDATED


def test_a_conformer_replaced_after_the_card_withdraws_it_as_well(world):
    """The other half of the binding: the drawing is the same, the geometry it was prepared against is not."""
    preparation = prepare(world).preparation
    world.molecule.conformers.clear()
    world.add_conformer(world.molecule)
    world.molecule.conformers[0].molblock = world.molecule.conformers[0].molblock.replace("0.", "1.", 3)
    after = world.services.result_store_service.fingerprints_for(world.molecule)
    assert after["geometry"] != preparation.input_fingerprint and after["drawing"] == preparation.drawing_fingerprint
    assert approve(world, preparation.run_id) is RunState.INVALIDATED and world.starter.calls == []


def test_a_card_for_a_molecule_that_has_left_the_project_hands_nothing_over(world):
    preparation = prepare(world).preparation
    world.project.molecules.remove(world.molecule)
    assert approve(world, preparation.run_id) is RunState.INVALIDATED and world.starter.calls == []


def test_the_prepared_run_is_a_frozen_record(world):
    preparation = prepare(world).preparation
    with pytest.raises(dataclasses.FrozenInstanceError):
        preparation.input_fingerprint = "other"  # type: ignore[misc]


def test_a_calculator_that_says_it_needs_no_conformer_is_not_told_it_does(world):
    """The preview a host without a starter gives lists what a calculator needs; these three say they embed every structure fresh."""
    world.host.set_quantum_starter(None)
    for calculator_id in ("orca.proton_affinity", "orca.bond_dissociation_enthalpy", "orca.tautomer_distribution"):
        preview = prepare(world, calculator_id).service_preview
        assert not any(r.what.startswith("a 3D conformer") for r in preview.requirements), calculator_id
    assert any(r.what.startswith("a 3D conformer") for r in prepare(world, "orca.sp").service_preview.requirements)


# --- bond dissociation: a fixed protocol whose one choice, which bonds, is on the card ----------------------------------------------------------


def test_bond_dissociation_needs_no_conformer_and_the_card_names_the_bonds_and_the_cost(world):
    base(world, "CCO", "Ethanol")
    turn = world.host.begin_turn()
    result = prepare(world, "orca.bond_dissociation_enthalpy", turn=turn)
    assert result.ok, result.problems
    preparation = result.preparation
    assert preparation.calculation_input == "drawing" and preparation.input_fingerprint == turn.fingerprints["drawing"] and preparation.drawing_fingerprint == ""
    text = "\n".join(preparation.preview)
    assert "embedded fresh" in text and "Bond dissociation button" in text and "What it would cost (approving accepts it)" in text
    assert "The bonds it would compute: CH3-H, bonded to C; CH2-H, bonded to C, O; O-H, bonded to C." in text and "5 ORCA jobs" in text and "minutes to hours" in text
    assert "leaves out" not in text and "conformer" not in text.replace("no conformer", "")
    assert world.starter.calls == [] and world.host.state_of(preparation.run_id) is RunState.PREVIEWED


def test_a_molecule_with_more_bond_classes_than_one_run_takes_says_which_are_left_out(world):
    base(world, "CCCCCCO", "Hexanol")
    text = "\n".join(prepare(world, "orca.bond_dissociation_enthalpy").preparation.preview)
    assert "it leaves out: O-H, bonded to C" in text and "the Quantum Chemistry panel's Bond dissociation button, where the bonds are chosen" in text and "22 ORCA jobs" in text


def test_a_molecule_outside_what_was_measured_says_so_on_the_bond_card(world):
    base(world, "CCl", "Chloromethane")
    text = "\n".join(prepare(world, "orca.bond_dissociation_enthalpy").preparation.preview)
    assert "outside what the benchmark measured" in text and "Cl:" in text


@pytest.mark.parametrize(("smiles", "fragment"), [("C[N+](C)(C)C", "charged"), ("O=C=O", "no bond between a heavy atom and a hydrogen")])
def test_a_molecule_the_bond_protocol_cannot_compute_is_refused_before_a_card(world, smiles, fragment):
    base(world, smiles, "Refused")
    result = prepare(world, "orca.bond_dissociation_enthalpy")
    assert [p.code for p in result.problems] == [ProblemCode.INVALID_STRUCTURE] and "does not apply" in result.problems[0].message and fragment in result.problems[0].message
    assert world.host.pending() == ()


def test_bond_dissociation_without_orca_is_not_ready(world):
    base(world, "CCO", "Ethanol")
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    assert [p.code for p in prepare(world, "orca.bond_dissociation_enthalpy").problems] == [ProblemCode.NOT_READY]


def test_approving_bond_dissociation_hands_over_the_protocol_and_the_drawings_fingerprint(world):
    ethanol = base(world, "CCO", "Ethanol")
    preparation = prepare(world, "orca.bond_dissociation_enthalpy").preparation
    assert approve(world, preparation.run_id) is RunState.RUNNING
    [(molecule_uuid, choice, fingerprint)] = world.starter.calls
    assert molecule_uuid == ethanol.uuid and choice.calc_type == "bond_dissociation" and fingerprint == preparation.input_fingerprint
    completed(world, preparation, calc_type="bond_dissociation", calculation_input="drawing", status=RunStatus.COMPLETED)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED] and world.host._quantum_inflight == {}


def test_editing_the_drawing_after_a_bond_dissociation_card_withdraws_it(world):
    ethanol = base(world, "CCO", "Ethanol")
    preparation = prepare(world, "orca.bond_dissociation_enthalpy").preparation
    world.engine.set_structure_from_smiles(ethanol, "CCCO")
    assert approve(world, preparation.run_id) is RunState.INVALIDATED and world.starter.calls == []


# --- tautomer distribution: the three settings, run on the drawing, with the jobs its enumeration gives ----------------------------------------------


def test_a_tautomer_card_needs_no_conformer_and_states_the_settings_and_the_jobs(world):
    base(world, "CC(C)=O", "Acetone")
    turn = world.host.begin_turn()
    result = prepare(world, "orca.tautomer_distribution", turn=turn)
    assert result.ok, result.problems
    preparation = result.preparation
    assert preparation.calculation_input == "drawing" and preparation.input_fingerprint == turn.fingerprints["drawing"] and preparation.drawing_fingerprint == ""
    assert set(preparation.parameters) == {"charge", "multiplicity", "method_basis"}
    text = "\n".join(preparation.preview)
    assert "embedded fresh" in text and "same rules as the Quantum Chemistry panel's Tautomers button" in text and "What it would cost (approving accepts it)" in text
    assert f"method_basis='{preparation.parameters['method_basis']}'" in text and "charge=0" in text and "multiplicity=1" in text
    assert "3 real ORCA geometry optimizations for 2 tautomer(s)" in text and "default conformer search" in text and "Full ORCA conformers box" in text
    assert "conformer" not in text.replace("conformer search", "").replace("Full ORCA conformers box", "").replace("distinct conformers", "").replace("sampled conformer", "")
    assert world.starter.calls == [] and world.host.state_of(preparation.run_id) is RunState.PREVIEWED


def test_the_settings_a_person_gave_are_the_settings_on_the_tautomer_card(world):
    base(world, "CC(C)=O", "Acetone")
    parameters = {"charge": 0, "multiplicity": 1, "method_basis": "PBE0 def2-TZVP"}
    text = "\n".join(prepare(world, "orca.tautomer_distribution", parameters).preparation.preview)
    assert "PBE0 def2-TZVP" in text


def test_tautomers_without_orca_are_not_ready(world):
    base(world, "CC(C)=O", "Acetone")
    world.services.quantum_chemistry_service._settings.set("orca/executable_path", "")
    assert [p.code for p in prepare(world, "orca.tautomer_distribution").problems] == [ProblemCode.NOT_READY]


def test_approving_tautomers_hands_over_the_settings_and_the_drawings_fingerprint(world):
    acetone = base(world, "CC(C)=O", "Acetone")
    preparation = prepare(world, "orca.tautomer_distribution", {"charge": 0, "multiplicity": 1, "method_basis": "PBE0 def2-TZVP"}).preparation
    assert approve(world, preparation.run_id) is RunState.RUNNING
    [(molecule_uuid, choice, fingerprint)] = world.starter.calls
    assert molecule_uuid == acetone.uuid and choice.calc_type == "tautomer_distribution" and fingerprint == preparation.input_fingerprint
    assert (choice.method_basis, choice.charge, choice.multiplicity) == ("PBE0 def2-TZVP", 0, 1)
    # The run record the service really writes for this calculation carries no fingerprint (its input is the whole candidate set), so it is matched by molecule and type.
    completed(world, preparation, calc_type="tautomer_distribution", calculation_input="", input_fingerprint="", status=RunStatus.COMPLETED)
    assert [o.state for o in world.outcomes] == [RunState.COMPLETED] and world.host._quantum_inflight == {}


def test_editing_the_drawing_after_a_tautomer_card_withdraws_it(world):
    acetone = base(world, "CC(C)=O", "Acetone")
    preparation = prepare(world, "orca.tautomer_distribution").preparation
    world.engine.set_structure_from_smiles(acetone, "CCC(C)=O")
    assert approve(world, preparation.run_id) is RunState.INVALIDATED and world.starter.calls == []


def test_a_run_record_with_no_fingerprint_ends_only_a_job_of_its_own_type(world):
    """The tautomer record is written blank; that must not let a blank record of ANOTHER type, or a fingerprint that names another structure, end an approved job."""
    base(world, "CC(C)=O", "Acetone")
    preparation = prepare(world, "orca.tautomer_distribution").preparation
    assert approve(world, preparation.run_id) is RunState.RUNNING
    completed(world, preparation, calc_type="sp", calculation_input="", input_fingerprint="", status=RunStatus.COMPLETED)
    completed(world, preparation, calc_type="tautomer_distribution", calculation_input="drawing", input_fingerprint="another-structure", status=RunStatus.COMPLETED)
    assert world.outcomes == [] and world.host.state_of(preparation.run_id) is RunState.RUNNING
