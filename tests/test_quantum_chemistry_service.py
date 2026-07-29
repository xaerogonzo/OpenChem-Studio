from __future__ import annotations

import sys
import time
from pathlib import Path

from rdkit import Chem

from openchem.app.settings import Settings
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.events.base import EventBus
from openchem.events.events import QuantumChemistryJobStateChanged, QuantumChemistryResultReady
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.quantum_chemistry_service import QuantumChemistryService


class FakeQuantumEngineProvider(QuantumEngineProvider):
    """Runs a REAL subprocess (the current Python interpreter, running a
    tiny inline script) rather than mocking QProcess itself -- this
    exercises the service's actual QProcess lifecycle (spawn, stream
    stdout, finish, cleanup) genuinely, the same way test_docking_providers.py
    exercises real Open Babel conversion instead of mocking it away.
    """

    provider_id = "fake"

    def __init__(self, stdout_text: str = "ok", exit_code: int = 0, sleep_seconds: float = 0.0) -> None:
        self._stdout_text = stdout_text
        self._exit_code = exit_code
        self._sleep_seconds = sleep_seconds
        self.parse_calls: list[str] = []

    def build_input(self, mol, charge, multiplicity, method_basis, calc_type) -> str:
        return "fake input text"

    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        script = (
            f"import sys, time; time.sleep({self._sleep_seconds}); "
            f"sys.stdout.write({self._stdout_text!r}); sys.exit({self._exit_code})"
        )
        return [executable_path, "-c", script]

    def parse_output(self, output_text: str, mol, molecule_uuid: str, calc_type: str):
        self.parse_calls.append(output_text)
        if "FAIL_PARSE" in output_text:
            raise RuntimeError("fake parse failure")
        descriptor = DescriptorValue(
            descriptor_id="fake.energy",
            name="Fake Energy",
            units="Hartree",
            category="quantum_chemistry",
            provider="fake",
            molecule_uuid=molecule_uuid,
            value=-1.0,
            cache_state=CacheState.COMPLETED,
        )
        conformer = None if calc_type == "sp" else ConformerModel(molblock="fake molblock", method="fake_opt")
        return [descriptor], conformer


def _wait_until(qapp, predicate, timeout_seconds: float = 15) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _make_service(tmp_path, provider) -> tuple[QuantumChemistryService, EventBus]:
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(bus, settings, providers={provider.provider_id: provider})
    return service, bus


def test_quantum_chemistry_job_lifecycle_reaches_completed(qapp, tmp_path):
    provider = FakeQuantumEngineProvider(stdout_text="hello from fake orca")
    service, bus = _make_service(tmp_path, provider)

    states: list[CacheState] = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))
    results = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: results.append(e))

    mol = Chem.MolFromSmiles("CCO")
    service.request_calculation(
        mol=mol,
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert CacheState.QUEUED in states
    assert CacheState.RUNNING in states
    assert states[-1] == CacheState.COMPLETED
    assert len(results) == 1
    assert results[0].molecule_uuid == "mol-1"
    assert results[0].descriptors[0].value == -1.0
    assert results[0].conformer is None  # calc_type == "sp"
    assert "hello from fake orca" in provider.parse_calls[0]
    assert not service._active_jobs  # job popped once finished


def test_quantum_chemistry_opt_returns_conformer(qapp, tmp_path):
    provider = FakeQuantumEngineProvider()
    service, bus = _make_service(tmp_path, provider)
    results = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: results.append(e))
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="opt",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert len(results) == 1
    assert results[0].conformer is not None
    assert results[0].conformer.method == "fake_opt"


def test_quantum_chemistry_scratch_dir_is_cleaned_up_on_success(qapp, tmp_path):
    provider = FakeQuantumEngineProvider()
    service, bus = _make_service(tmp_path, provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    # Capture the scratch dir while the job is still active.
    job = service._active_jobs.get("mol-1")
    scratch_dir = job.scratch_dir if job is not None else None

    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert scratch_dir is not None, "expected to capture the scratch dir while job was active"
    assert not scratch_dir.exists(), "scratch dir must be cleaned up after the job finishes"


def test_quantum_chemistry_parse_failure_still_cleans_up_scratch(qapp, tmp_path):
    provider = FakeQuantumEngineProvider(stdout_text="FAIL_PARSE this output")
    service, bus = _make_service(tmp_path, provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))
    results = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: results.append(e))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    job = service._active_jobs.get("mol-1")
    scratch_dir = job.scratch_dir if job is not None else None

    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert states[-1] == CacheState.FAILED
    assert results == []
    assert scratch_dir is not None and not scratch_dir.exists()


def test_quantum_chemistry_cancel_kills_process_and_cleans_up(qapp, tmp_path):
    provider = FakeQuantumEngineProvider(sleep_seconds=5.0)
    service, bus = _make_service(tmp_path, provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))
    results = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: results.append(e))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: CacheState.RUNNING in states, timeout_seconds=5)

    job = service._active_jobs.get("mol-1")
    scratch_dir = job.scratch_dir if job is not None else None
    messages = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: messages.append(e.message))
    service.cancel("mol-1")

    assert _wait_until(qapp, lambda: states and states[-1] == CacheState.FAILED, timeout_seconds=10)
    assert any("Cancelled" in m for m in messages)
    assert results == []
    assert scratch_dir is not None and not scratch_dir.exists()


def test_quantum_chemistry_no_executable_configured_fails_immediately(qapp, tmp_path):
    provider = FakeQuantumEngineProvider()
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", str(tmp_path / "does_not_exist.exe"))
    service = QuantumChemistryService(bus, settings, providers={provider.provider_id: provider})

    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )

    assert states == [CacheState.FAILED]
    assert not service._active_jobs


class _LargeFinalBurstProvider(FakeQuantumEngineProvider):
    """Generates its large payload AT RUNTIME inside the subprocess rather
    than embedding it in the `-c` script argument itself -- a literal
    ~200KB string baked into the command line blows past Windows' argument-
    length limits and the process never starts. The marker is what matters:
    it must survive to `parse_output` intact."""

    MARKER = "END_MARKER_" + "x" * 100

    def command_args(self, executable_path, input_path):
        script = f"import sys; sys.stdout.write('y' * 200_000 + {self.MARKER!r}); sys.exit(0)"
        return [executable_path, "-c", script]


def test_quantum_chemistry_captures_full_output_for_a_large_final_burst(qapp, tmp_path):
    """Regression test: confirmed live against a real ORCA install that
    QProcess's `finished` signal can fire before Qt has delivered the LAST
    `readyReadStandardOutput` chunk for data the process wrote right as it
    exited -- a short job's output always arrived in time, but a longer
    job's final "FINAL SINGLE POINT ENERGY"/"OPTIMIZATION RUN DONE" block
    was sporadically missing from the captured text, even though the
    identical input completed fine when run directly. `_on_finished` now
    drains any remaining buffered bytes before parsing -- this pumps a
    large (~200KB), single burst of output right before exit to exercise
    that path.
    """
    provider = _LargeFinalBurstProvider()
    service, bus = _make_service(tmp_path, provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert states[-1] == CacheState.COMPLETED
    assert _LargeFinalBurstProvider.MARKER in provider.parse_calls[0]


def test_quantum_chemistry_unknown_provider_fails_immediately(qapp, tmp_path):
    bus = EventBus()
    settings = Settings(bus)
    service = QuantumChemistryService(bus, settings, providers={})

    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="does_not_exist",
    )

    assert states == [CacheState.FAILED]
