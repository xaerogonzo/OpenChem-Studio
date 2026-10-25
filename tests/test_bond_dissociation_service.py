"""`QuantumChemistryService.request_bond_dissociation`: the real sequential-job orchestration with a real subprocess standing in for ORCA (never a mocked QProcess), printing real ORCA outputs.

What it proves is the orchestration, not the chemistry (`test_bond_dissociation_calculation.py` holds the chemistry to the benchmarks' records): the molecule's single job slot is held for the whole sequence, the hydrogen atom runs first with its own single-point input,
the radical is run as a doublet, the one `Calc_Hess` retry happens, a structure whose output cannot be read costs that structure and not the run (a hydrogen atom that fails ends it), a cancellation or a crash ends the operation with no result,
and ONE result and ONE run are published for the operation. The molecule is hydrogen cyanide: its three jobs are real outputs (the atom, the parent, the CN radical).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from rdkit import Chem
from test_quantum_chemistry_service import FakeQuantumEngineProvider, _wait_until

from openchem import paths as app_paths
from openchem.app.settings import Settings
from openchem.domain.calculator import DRAWING
from openchem.domain.common import (
    RUN_CALC_TYPE,
    RUN_CHARGE,
    RUN_MULTIPLICITY,
    CacheState,
)
from openchem.domain.quantum_chemistry_run import RunStatus
from openchem.events.base import EventBus
from openchem.events.events import (
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    QuantumChemistryRunCompleted,
    ResultRecorded,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.job_manager import JobManager
from openchem.services.quantum_chemistry_service import QuantumChemistryService

_FIXTURES = Path(__file__).parent / "fixtures" / "orca"
H_ATOM = (_FIXTURES / "bde_h_atom.out").read_text(encoding="utf-8")
HCN = (_FIXTURES / "bde_hcn_parent_optfreq.out").read_text(encoding="utf-8")
CN_RADICAL = (_FIXTURES / "bde_cn_radical_optfreq.out").read_text(encoding="utf-8")
IMAGINARY_RADICAL = re.sub(r"(\n\s*5:\s+)(\d+\.\d+)( cm\*\*-1)", r"\g<1>-30.00\g<3>", CN_RADICAL, count=1)
_FAKE_FINGERPRINT = "drawing:fake-hcn"
#: the first run's judged DH298 of HCN's C-H, kcal/mol (126.30 + 2.53), times 4.184
_HCN_KJ = 128.83 * 4.184


class _OrcaStandIn(FakeQuantumEngineProvider):
    """Prints the given ORCA outputs one per launched job (a real subprocess), and keeps the input file each job was given."""

    def __init__(self, outputs: list[str], sleep_seconds: float = 0.0) -> None:
        super().__init__(stdout_text="", sleep_seconds=sleep_seconds)
        self._outputs = outputs
        self.inputs: list[str] = []

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        self.inputs.append(Path(input_path).read_text(encoding="utf-8"))
        text = self._outputs[min(len(self.inputs), len(self._outputs)) - 1]
        # a real ORCA output is hundreds of kilobytes, far past Windows' command-line limit, so the stand-in reads it from a file beside the input
        output_path = Path(input_path).with_name(f"stand_in_{len(self.inputs)}.out")
        output_path.write_text(text, encoding="utf-8")
        script = f"import sys, time; time.sleep({self._sleep_seconds}); sys.stdout.write(open({str(output_path)!r}, encoding='utf-8').read())"
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


def _request(service, smiles: str = "C#N", atoms: list[int] | None = None, molecule_uuid: str = "mol-1") -> None:
    service.request_bond_dissociation(smiles, atoms, molecule_uuid, DRAWING, _FAKE_FINGERPRINT, structure_identity="C#N", provider_id="fake")


def test_a_hydrogen_cyanide_run_gives_one_result_with_the_first_runs_bond_enthalpy(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)

    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(results) == 1 and len(provider.inputs) == 3
    (descriptor,) = results[0].descriptors
    assert descriptor.descriptor_id == "orca.bond_dissociation_enthalpy" and descriptor.units == "kJ/mol" and descriptor.cache_state is CacheState.COMPLETED
    assert descriptor.value == pytest.approx(_HCN_KJ, abs=0.3)
    assert results[0].structure_identity == "C#N"


def test_every_job_is_given_its_own_input_the_atom_first_and_the_radical_as_a_doublet(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL])
    service, _bus = _make_service(provider)
    _request(service)
    assert _wait_until(qapp, lambda: len(provider.inputs) == 3)

    atom, parent, radical = provider.inputs
    assert atom.startswith("! M062X def2-TZVPD TightSCF DefGrid3\n") and "Opt" not in atom and "%pal" not in atom and "* xyz 0 2" in atom and sum(1 for line in atom.splitlines() if line.split()[:1] == ["H"]) == 1
    for text in (parent, radical):
        assert text.startswith("! M062X def2-TZVPD TightSCF TightOpt DefGrid3 Opt Freq") and "%maxcore 3000" in text and "%pal nprocs" in text and "Calc_Hess" not in text
    assert "* xyz 0 1" in parent and "* xyz 0 2" in radical
    assert sum(1 for line in parent.splitlines() if line.split()[:1] == ["H"]) == 1 and sum(1 for line in radical.splitlines() if line.split()[:1] == ["H"]) == 0  # the radical lost its hydrogen


def test_the_result_says_what_the_number_is_and_how_good_it_was_measured_to_be(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)
    assert _wait_until(qapp, lambda: results)

    parameters = results[0].descriptors[0].provenance.parameters
    assert parameters["quantity"] == "bond_dissociation_enthalpy" and parameters["temperature_k"] == 298.15 and parameters["bonds"][0]["weakest"] is True
    assert "49 X-H bonds" in parameters["validation"] and "run LOW" in parameters["validation"]
    # stamped with the PARENT's charge and multiplicity, not the last job's (the radical, a doublet), and with the operation's own type
    assert parameters[RUN_CHARGE] == 0 and parameters[RUN_MULTIPLICITY] == 1 and parameters[RUN_CALC_TYPE] == "bond_dissociation"


def test_an_imaginary_mode_is_re_run_once_with_calc_hess_and_the_retry_is_what_counts(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, IMAGINARY_RADICAL, CN_RADICAL])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(provider.inputs) == 4
    assert "Calc_Hess" not in provider.inputs[2] and "Calc_Hess true" in provider.inputs[3] and "* xyz 0 2" in provider.inputs[3]  # the retry is of the same radical
    assert results[0].descriptors[0].value == pytest.approx(_HCN_KJ, abs=0.3)


def test_a_radical_that_keeps_its_imaginary_mode_is_dropped_and_the_output_says_why(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, IMAGINARY_RADICAL, IMAGINARY_RADICAL])
    service, bus = _make_service(provider)
    results, runs = [], []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    _request(service)

    assert _wait_until(qapp, lambda: results and runs)
    assert len(provider.inputs) == 4  # one retry and no more
    descriptor = results[0].descriptors[0]
    assert descriptor.value is None and descriptor.cache_state is CacheState.FAILED
    assert "mol|radical|0|0" in descriptor.error and "-30 cm-1" in descriptor.error
    assert runs[0].status is RunStatus.FAILED


def test_a_failed_hydrogen_atom_ends_the_run_after_one_job_with_its_reason(qapp):
    provider = _OrcaStandIn(["ORCA ended with nothing to read", HCN, CN_RADICAL])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(provider.inputs) == 1  # hours of ORCA are not spent on a run that cannot have a value
    assert results[0].descriptors[0].value is None and "hydrogen atom's single point failed" in results[0].descriptors[0].error


def test_a_structure_whose_output_cannot_be_read_costs_that_structure_and_not_the_sequence(qapp):
    provider = _OrcaStandIn([H_ATOM, "ORCA ended with nothing to read", CN_RADICAL])
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, results.append)
    _request(service)

    assert _wait_until(qapp, lambda: results)
    assert len(provider.inputs) == 3  # the radical still ran
    assert results[0].descriptors[0].value is None and "no accepted parent structure" in results[0].descriptors[0].error


def test_one_run_and_one_stored_result_are_recorded_for_the_whole_operation(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL])
    service, bus = _make_service(provider)
    runs, stored = [], []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    bus.subscribe(ResultRecorded, stored.append)
    _request(service)

    assert _wait_until(qapp, lambda: runs)
    assert len(runs) == 1  # NOT one per structure
    run = runs[0]
    assert run.calc_type == "bond_dissociation" and run.charge == 0 and run.multiplicity == 1 and run.status is RunStatus.COMPLETED
    assert [d.descriptor_id for d in run.results["descriptors"]] == ["orca.bond_dissociation_enthalpy"]
    assert [s.stored.identity.producer for s in stored] == ["orca"] and stored[0].stored.result.descriptor_id == "orca.bond_dissociation_enthalpy"


def test_a_molecule_the_protocol_cannot_compute_is_refused_with_its_reason_and_starts_no_job(qapp):
    provider = _OrcaStandIn([H_ATOM])
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)

    _request(service, smiles="C[N+](C)(C)C")

    assert states[-1].state is CacheState.FAILED and "Bond dissociation does not apply" in states[-1].message and "charged" in states[-1].message
    assert provider.inputs == [] and not job_manager.is_active("quantum_chemistry", "mol-1")


def test_a_choice_of_bonds_that_is_not_valid_is_refused_before_any_job(qapp):
    provider = _OrcaStandIn([H_ATOM])
    service, bus = _make_service(provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    _request(service, atoms=[0, 0])
    assert "twice" in states[-1].message and provider.inputs == []
    _request(service, atoms=[7])
    assert "could not start" in states[-1].message and "not the representative" in states[-1].message and provider.inputs == []


def test_the_molecule_slot_is_held_for_the_whole_sequence_and_a_second_request_is_refused(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL], sleep_seconds=0.3)
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)

    _request(service)
    assert _wait_until(qapp, lambda: len(provider.inputs) >= 1)
    service.request_calculation(mol=Chem.MolFromSmiles("C"), molecule_uuid="mol-1", calc_type="sp", charge=0, multiplicity=1, method_basis="HF STO-3G", provider_id="fake")
    assert any("already running" in s.message for s in states)

    assert _wait_until(qapp, lambda: len(provider.inputs) == 3)
    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))


def test_the_progress_line_names_the_structure_and_its_role(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL])
    service, bus = _make_service(provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    _request(service)
    assert _wait_until(qapp, lambda: len(provider.inputs) == 3)
    messages = [s.message for s in states if s.state is CacheState.RUNNING]
    assert any("structure 1/3 (hydrogen atom)" in m for m in messages) and any("(parent)" in m for m in messages) and any("(radical)" in m for m in messages)


def test_cancelling_mid_run_publishes_no_result_records_a_cancelled_run_and_releases_the_slot(qapp):
    provider = _OrcaStandIn([H_ATOM, HCN, CN_RADICAL], sleep_seconds=5.0)
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
    assert [r.status for r in runs] == [RunStatus.CANCELLED] and runs[0].calc_type == "bond_dissociation"
    assert "mol-1" not in service._bond_runs
