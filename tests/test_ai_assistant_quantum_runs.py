"""`read_quantum_runs`: the assistant reading the ORCA jobs a person ran, through the real host, the real assistant plugin and its real tool loop.

What `test_quantum_run_snapshot.py` pins on values is asserted here on the path a reply takes: a run is frozen when Send is pressed and not before or after, a run for another molecule is
never read, an edit of the structure turns a run historical, the tool starts nothing and cannot, and a long history still fits the reply budget with every header.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
import test_quantum_run_snapshot as shared
from ai_assistant.bridge import REPLY_BUDGET
from ai_assistant.calculation_tools import CALCULATION_HANDLERS, CALCULATION_TOOLS, READ_QUANTUM_RUNS
from ai_assistant.panel import SYSTEM_PROMPT_PREFIX
from ai_assistant.tools import validate_arguments
from test_ai_assistant_bridge import _bridge, _call, _Rig, _tool_message, _two_step
from test_calculation_host import ETHANOL

from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus
from openchem.domain.scientific_result import VibrationalMode
from openchem.domain.turn_snapshot import Freshness


@pytest.fixture
def rig(qapp, tmp_path):
    return _Rig(qapp, tmp_path, held=True)


def record(rig, molecule=None, *, run_id, status=RunStatus.COMPLETED, started=1000.0, descriptors=True, vibrational=None, warnings=()) -> QuantumChemistryRun:
    """A run in the project's own store, on the molecule's drawing as it stands now, as the service records one when a job ends."""
    service = rig.world.services.result_store_service
    molecule = molecule or rig.world.molecule
    run = QuantumChemistryRun(
        run_id=run_id, molecule_uuid=molecule.uuid, calc_type="opt_freq" if vibrational is not None else "sp", method_basis="B3LYP def2-SVP", charge=0, multiplicity=1,
        calculation_input="drawing", input_fingerprint=service.fingerprints_for(molecule)["drawing"], input_molblock=shared.SECRET_MOLBLOCK, started_at=started,
        completed_at=started + 5.0, status=status, surface_cache_key=shared.SECRET_CACHE_KEY, warnings=list(warnings),
    )
    if descriptors and status in (RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_WARNINGS):
        run.results["descriptors"] = shared.real_descriptors()
        run.output_status["descriptors"] = OutputStatus.AVAILABLE
    if vibrational is not None:
        run.results["vibrational_spectrum"] = vibrational
        run.output_status["vibrational_spectrum"] = OutputStatus.AVAILABLE
    service.record_quantum_chemistry_run(run)
    assert service.qc_runs.get(run_id) is run
    return run


def read(rig, **arguments) -> dict:
    bridge = rig.bridge()
    return json.loads(bridge.read_quantum_runs(arguments.get("run_ids"), arguments.get("include_not_current", False)))


# --- the turn ------------------------------------------------------------------------------------------------------------------------------


def test_a_turn_freezes_the_runs_stored_when_send_was_pressed(rig):
    record(rig, run_id="first", started=100.0)
    turn = rig.world.host.begin_turn()
    record(rig, run_id="second", started=200.0)
    assert [e.run_id for e in turn.runs] == ["first"], "a job that ended while the reply streams must not change what it is told"
    later = rig.world.host.begin_turn()
    assert [e.run_id for e in later.runs] == ["second", "first"]


def test_only_the_selected_molecules_runs_are_read(rig):
    other = rig.world.add(ETHANOL, "Ethanol", select=False)
    record(rig, other, run_id="ethanol-run")
    record(rig, run_id="aspirin-run")
    assert [r["run_id"] for r in read(rig)["runs"]] == ["aspirin-run"]
    # Not only the default list: another molecule's run reads as historical against this one's fingerprints, so the default hides it. The turn itself must never hold it.
    assert [e.run_id for e in rig.world.host.begin_turn().runs] == ["aspirin-run"]
    assert [r["run_id"] for r in read(rig, include_not_current=True)["runs"]] == ["aspirin-run"]


def test_a_run_survives_the_structure_being_drawn_again_as_a_historical_one(rig):
    record(rig, run_id="before-the-edit")
    rig.world.engine.set_structure_from_smiles(rig.world.molecule, ETHANOL)
    turn = rig.world.host.begin_turn()
    [entry] = turn.runs
    assert entry.freshness is Freshness.HISTORICAL
    listed = read(rig)
    assert listed["runs"] == [] and listed["not_current_left_out"] == 1
    everything = read(rig, include_not_current=True)
    assert [(r["run_id"], r["freshness"]) for r in everything["runs"]] == [("before-the-edit", "historical")]
    assert "earlier structure" in everything["runs"][0]["freshness_note"]


def test_a_molecule_with_nothing_drawn_still_says_what_became_of_its_runs(rig):
    blank = rig.world.add(None, "Blank")
    assert rig.world.host.begin_turn().runs == ()
    assert rig.world.session.selected_molecule_uuid == blank.uuid


# --- the tool, through the real loop -----------------------------------------------------------------------------------------------------------


def test_the_tool_is_offered_with_a_handler_a_schema_and_a_sentence_in_the_system_prompt():
    assert READ_QUANTUM_RUNS in CALCULATION_TOOLS and "read_quantum_runs" in CALCULATION_HANDLERS
    assert validate_arguments(READ_QUANTUM_RUNS.input_schema, {}) == []
    assert validate_arguments(READ_QUANTUM_RUNS.input_schema, {"run_ids": ["a"], "include_not_current": True}) == []
    assert validate_arguments(READ_QUANTUM_RUNS.input_schema, {"run_ids": "a"}) != []
    assert "read_quantum_runs" in SYSTEM_PROMPT_PREFIX and "cannot start, stop or approve" in SYSTEM_PROMPT_PREFIX
    description = READ_QUANTUM_RUNS.description
    assert "never be reported as the answer" in description and "never treat it as zero" in description and "cannot start, stop or approve" in description


def test_a_bridge_with_no_molecule_says_unavailable():
    data = json.loads(_bridge().read_quantum_runs())
    assert data["ok"] is False and data["problem"] == "unavailable"


def test_the_model_lists_the_runs_and_then_reads_one_in_full(rig):
    record(rig, run_id="run-a", started=100.0)
    list_provider = _two_step([_call("read_quantum_runs")])
    thread, _ = rig.loop(list_provider, rig.bridge())
    rig.settle(thread)
    listed = json.loads(_tool_message(list_provider)[0].content)
    [header] = listed["runs"]
    assert header["run_id"] == "run-a" and header["outputs"]["descriptors"]["names"] == ["SCF Energy"] and "154.98" not in json.dumps(listed)

    detail_provider = _two_step([_call("read_quantum_runs", run_ids=["run-a", "ghost"])])
    thread, _ = rig.loop(detail_provider, rig.bridge())
    rig.settle(thread)
    detail = json.loads(_tool_message(detail_provider)[0].content)
    assert detail["not_found"] == ["ghost"]
    [value] = detail["runs"][0]["outputs"]["descriptors"]["results"]
    assert value["data"]["value"] == -154.988 and value["data"]["units"] == "Hartree"


def test_a_failed_job_is_told_as_a_failure_with_its_warnings_and_no_number(rig):
    record(rig, run_id="broken", status=RunStatus.FAILED, warnings=["ORCA ended before the SCF converged"])
    data = read(rig, run_ids=["broken"])
    [run] = data["runs"]
    assert run["outcome"] == "failed" and run["warnings"] == ["ORCA ended before the SCF converged"]
    assert run["outputs"] == {} and "154.98" not in json.dumps(data)


def test_the_tool_starts_nothing_and_touches_no_service(rig, monkeypatch):
    record(rig, run_id="run-a")
    qc = rig.world.services.quantum_chemistry_service

    def boom(*args, **kwargs):
        raise AssertionError("reading a run must not start or stop a job")

    for name in ("request_calculation", "request_boltzmann_nmr", "request_proton_affinity", "request_bond_dissociation", "request_tautomer_distribution", "cancel"):
        monkeypatch.setattr(qc, name, boom)
    thread, _ = rig.loop(_two_step([_call("read_quantum_runs", run_ids=["run-a"])]), rig.bridge())
    rig.settle(thread)
    assert rig.world.pool.tasks == [] and rig.world.host.pending() == ()


def test_the_structure_sent_to_orca_never_reaches_the_model(rig):
    record(rig, run_id="run-a")
    for arguments in ({}, {"run_ids": ["run-a"]}, {"include_not_current": True}):
        text = rig.bridge().read_quantum_runs(arguments.get("run_ids"), arguments.get("include_not_current", False))
        assert shared.SECRET_MOLBLOCK not in text and shared.SECRET_CACHE_KEY not in text


def test_an_infrared_analysis_is_read_as_its_modes(rig):
    record(rig, run_id="freq", vibrational=shared.real_vibrational())
    spectrum = read(rig, run_ids=["freq"])["runs"][0]["outputs"]["vibrational_spectrum"]["results"][0]["data"]
    assert spectrum["count"] == 3 and "peaks" not in spectrum and spectrum["imaginary_modes"] == 0


def test_a_reply_that_is_too_big_at_full_detail_is_shortened_and_says_so(rig):
    """Forty caveated results in one run are far past the budget at full detail; the reply steps down and keeps the run's header."""
    from openchem.domain.common import CacheState, Provenance
    from openchem.domain.descriptor import DescriptorValue

    many = [
        DescriptorValue(
            descriptor_id=f"orca.value_{i}", name=f"Value {i}", units="eV", category="quantum_chemistry", provider="orca", molecule_uuid="m", value=float(i), cache_state=CacheState.COMPLETED,
            provenance=Provenance(created_by="core", method="orca", parameters={"caveat": "a limitation worth reading " * 20}),
        )
        for i in range(40)
    ]
    run = record(rig, run_id="wide", descriptors=False)
    run.results["descriptors"] = many
    run.output_status["descriptors"] = OutputStatus.AVAILABLE
    text = rig.bridge().read_quantum_runs(["wide"])
    data = json.loads(text)
    assert len(text) <= REPLY_BUDGET and data["shortened_for_length"] is True
    assert data["runs"][0]["run_id"] == "wide" and data["runs"][0]["calculation"]["method_basis"] == "B3LYP def2-SVP"


def long_history(rig, count=10):
    big = dataclasses.replace(shared.real_vibrational(), modes=tuple(VibrationalMode(wavenumber_cm1=100.0 + i, ir_intensity_km_mol=1.5) for i in range(400)))
    ids = [f"run-{i:02d}" for i in range(count)]
    for i, run_id in enumerate(ids):
        record(rig, run_id=run_id, started=100.0 + i, vibrational=big)
    return ids


def test_a_long_history_listed_as_headers_fits_the_reply_budget_with_every_run(rig):
    ids = long_history(rig)
    text = rig.bridge().read_quantum_runs()
    data = json.loads(text)
    assert len(text) <= REPLY_BUDGET and "shortened_for_length" not in data
    assert [r["run_id"] for r in data["runs"]] == list(reversed(ids))


def test_runs_read_in_full_are_three_at_a_time_and_the_reply_says_how_many_it_left_out(rig):
    ids = long_history(rig)
    text = rig.bridge().read_quantum_runs(ids)
    data = json.loads(text)
    assert len(text) <= REPLY_BUDGET, "ten long analyses came to 14,193 characters before the cap"
    assert [r["run_id"] for r in data["runs"]] == ids[:3] and data["left_out_for_length"] == 7
    for run in data["runs"]:
        assert run["calculation"]["method_basis"] == "B3LYP def2-SVP" and run["freshness"] == "current"
        assert run["outputs"]["vibrational_spectrum"]["results"][0]["data"]["count"] == 400
