"""`QuantumChemistryService.request_proton_affinity`: the real sequential-job orchestration with a real subprocess standing in for ORCA (never a mocked QProcess), printing the benchmark's real ORCA outputs.

What it proves is the orchestration, not the chemistry (`test_proton_affinity_calculation.py` holds the chemistry to the benchmark's records): the molecule's single job slot is held for the whole sequence, the preregistered input is what ORCA is
given, the one `Calc_Hess` retry happens, a structure whose output cannot be read costs that structure and not the run, a cancellation or a crash ends the operation with no result, and ONE result and ONE run are published for the operation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem import paths as app_paths
from openchem.app.settings import Settings
from openchem.domain.calculator import DRAWING
from openchem.domain.common import RUN_CALC_TYPE, RUN_CHARGE, RUN_MULTIPLICITY, CacheState
from openchem.domain.quantum_chemistry_run import RunStatus
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryJobStateChanged, QuantumChemistryResultReady, QuantumChemistryRunCompleted, ResultRecorded
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.job_manager import JobManager
from openchem.services.quantum_chemistry_service import QuantumChemistryService

from test_quantum_chemistry_service import FakeQuantumEngineProvider, _wait_until

_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
WATER = (_FIXTURES / "pa_water_optfreq.out").read_text(encoding="utf-8")
HYDRONIUM = (_FIXTURES / "pa_h3o_optfreq.out").read_text(encoding="utf-8")
PLANAR_HYDRONIUM = HYDRONIUM.replace("6:     807.65 cm**-1", "6:    -601.55 cm**-1")
_FAKE_FINGERPRINT = "drawing:fake-water"


class _OrcaStandIn(FakeQuantumEngineProvider):
    """Prints the given ORCA outputs one per launched job (a real subprocess), and keeps the input file each job was given."""

    def __init__(self, outputs: list[str], sleep_seconds: float = 0.0) -> None:
        super().__init__(stdout_text="", sleep_seconds=sleep_seconds)
        self._outputs = outputs
        self.inputs: list[str] = []

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        self.inputs.append(Path(input_path).read_text(encoding="utf-8"))
        text = self._outputs[min(len(self.inputs), len(self._outputs)) - 1]
        script = f"import sys, time; time.sleep({self._sleep_seconds}); sys.stdout.write({text!r})"
        return [executable_path, "-c", script]


@pytest.fixture(autouse=True)
def _scratch_under_tmp_path(tmp_path, monkeypatch):
    root = tmp_path / "data-root"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(root))
    return root


def _make_service(provider: QuantumEngineProvider, job_manager: JobManager | None = None):
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    return QuantumChemistryService(bus, settings, providers={provider.provider_id: provider}, job_manager=job_manager), bus


def _request(service, smiles: str = "O", molecule_uuid: str = "mol-1") -> None:
    service.request_proton_affinity(smiles, molecule_uuid, DRAWING, _FAKE_FINGERPRINT, structure_identity="O", provider_id="fake")


def test_a_water_run_gives_one_result_with_both_outputs_and_the_smoke_runs_proton_affinity(qapp):
    provider = _OrcaStandIn([WATER, HYDRONIUM])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)

    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(results) == 1 and len(provider.inputs) == 2
    by_id = {d.descriptor_id: d for d in results[0].descriptors}
    assert set(by_id) == {"orca.proton_affinity", "orca.gas_basicity"}
    pa, gb = by_id["orca.proton_affinity"], by_id["orca.gas_basicity"]
    assert pa.units == "kJ/mol" and pa.value == pytest.approx(686.8, abs=0.1)  # the preregistration's smoke run: H(water), H(H3O+)
    assert gb.cache_state is CacheState.COMPLETED and gb.value == pytest.approx(655.8, abs=0.2)  # with the symmetry number corrected, as the same note records
    assert results[0].structure_identity == "O"


def test_every_job_is_given_the_preregistered_input_with_the_right_charge(qapp):
    provider = _OrcaStandIn([WATER, HYDRONIUM])
    service, _bus = _make_service(provider)
    _request(service)
    assert _wait_until(qapp, lambda: len(provider.inputs) == 2)

    base, ion = provider.inputs
    for text in (base, ion):
        assert text.startswith("! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq") and "%maxcore 3000" in text and "%pal nprocs" in text and "Calc_Hess" not in text
    assert "* xyz 0 1" in base and "* xyz 1 1" in ion
    assert sum(1 for line in base.splitlines() if line.split()[:1] == ["H"]) == 2 and sum(1 for line in ion.splitlines() if line.split()[:1] == ["H"]) == 3


def test_the_result_says_what_the_number_is_and_how_good_it_was_measured_to_be(qapp):
    provider = _OrcaStandIn([WATER, HYDRONIUM])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)
    assert _wait_until(qapp, lambda: results)

    pa = next(d for d in results[0].descriptors if d.descriptor_id == "orca.proton_affinity")
    parameters = pa.provenance.parameters
    assert parameters["quantity"] == "pa" and parameters["temperature_k"] == 298.15 and parameters["pressure_atm"] == 1.0
    assert parameters["site_atom"] == 0 and parameters["site_element"] == "O" and parameters["sites"][0]["chosen_pa"] is True
    assert "1.55" in parameters["validation"] and "too weakly" in parameters["validation"]
    # stamped with the BASE's charge and multiplicity, not the last job's (the conjugate acid, +1), and with the operation's own type
    assert parameters[RUN_CHARGE] == 0 and parameters[RUN_MULTIPLICITY] == 1 and parameters[RUN_CALC_TYPE] == "proton_affinity"


def test_an_imaginary_mode_is_re_run_once_with_calc_hess_and_the_retry_is_what_counts(qapp):
    provider = _OrcaStandIn([WATER, PLANAR_HYDRONIUM, HYDRONIUM])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(provider.inputs) == 3
    assert "Calc_Hess" not in provider.inputs[1] and "Calc_Hess true" in provider.inputs[2]
    assert "* xyz 1 1" in provider.inputs[2]  # the retry is of the same conjugate acid
    assert next(d for d in results[0].descriptors if d.descriptor_id == "orca.proton_affinity").value == pytest.approx(686.8, abs=0.1)


def test_a_structure_that_keeps_its_imaginary_mode_is_dropped_and_both_outputs_say_why(qapp):
    provider = _OrcaStandIn([WATER, PLANAR_HYDRONIUM, PLANAR_HYDRONIUM])  # the benchmark's own water
    service, bus = _make_service(provider)
    results, runs = [], []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    _request(service)

    assert _wait_until(qapp, lambda: results and runs)
    assert len(provider.inputs) == 3  # one retry and no more
    for descriptor in results[0].descriptors:
        assert descriptor.value is None and descriptor.cache_state is CacheState.FAILED
        assert "mol|ion|lone_pair0|0" in descriptor.error and "-20 cm-1" in descriptor.error
    assert runs[0].status is RunStatus.FAILED


def test_a_structure_whose_output_cannot_be_read_costs_that_structure_and_not_the_sequence(qapp):
    provider = _OrcaStandIn(["ORCA ended with nothing to read", HYDRONIUM])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(provider.inputs) == 2  # the conjugate acid still ran
    assert all(d.value is None for d in results[0].descriptors)
    assert "mol|base|0" in results[0].descriptors[0].error


def test_one_run_and_one_stored_result_per_output_are_recorded_for_the_whole_operation(qapp):
    provider = _OrcaStandIn([WATER, HYDRONIUM])
    service, bus = _make_service(provider)
    runs, stored = [], []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    bus.subscribe(ResultRecorded, stored.append)
    _request(service)

    assert _wait_until(qapp, lambda: runs)
    assert len(runs) == 1  # NOT one per structure
    run = runs[0]
    assert run.calc_type == "proton_affinity" and run.charge == 0 and run.multiplicity == 1 and run.status is RunStatus.COMPLETED
    assert {d.descriptor_id for d in run.results["descriptors"]} == {"orca.proton_affinity", "orca.gas_basicity"}
    assert sorted(s.stored.identity.producer for s in stored) == ["orca", "orca"]
    assert {s.stored.result.descriptor_id for s in stored} == {"orca.proton_affinity", "orca.gas_basicity"}


def test_a_base_outside_what_the_benchmark_measured_is_refused_with_its_reason_and_starts_no_job(qapp):
    provider = _OrcaStandIn([WATER])
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)

    _request(service, smiles="CCl")

    assert states[-1].state is CacheState.FAILED and "Proton affinity does not apply" in states[-1].message and "Cl" in states[-1].message
    assert provider.inputs == [] and not job_manager.is_active("quantum_chemistry", "mol-1")


def test_the_molecule_slot_is_held_for_the_whole_sequence_and_a_second_request_is_refused(qapp):
    provider = _OrcaStandIn([WATER, HYDRONIUM], sleep_seconds=0.3)
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)

    _request(service)
    assert _wait_until(qapp, lambda: len(provider.inputs) >= 1)
    service.request_calculation(mol=Chem.MolFromSmiles("C"), molecule_uuid="mol-1", calc_type="sp", charge=0, multiplicity=1, method_basis="HF STO-3G", provider_id="fake")
    assert any("already running" in s.message for s in states)

    assert _wait_until(qapp, lambda: len(provider.inputs) == 2)
    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))


def test_cancelling_mid_run_publishes_no_result_records_a_cancelled_run_and_releases_the_slot(qapp):
    provider = _OrcaStandIn([WATER, HYDRONIUM], sleep_seconds=5.0)
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)
    results, runs, states = [], [], []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)

    _request(service)
    assert _wait_until(qapp, lambda: service._active_jobs.get("mol-1") is not None)
    service.cancel("mol-1")

    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))
    assert results == [] and any("Cancelled by user" in s.message for s in states)
    assert [r.status for r in runs] == [RunStatus.CANCELLED] and runs[0].calc_type == "proton_affinity"
    assert "mol-1" not in service._proton_runs
