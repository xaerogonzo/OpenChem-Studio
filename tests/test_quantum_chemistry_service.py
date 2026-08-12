from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.app.settings import Settings
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.events.base import EventBus
from openchem.domain.scientific_result import NMRSpectrumResult, SpectrumResult
from openchem.events.events import (
    NmrReferenceCalibrated,
    NmrScalingCalibrated,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    SpectrumComputed,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.job_manager import JobManager
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
            # `<provider_id>.scf_energy` is the convention the service uses
            # to find a conformer's weighting energy for Boltzmann averaging.
            descriptor_id="fake.scf_energy",
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


def test_quantum_chemistry_request_rejected_while_one_already_running(qapp, tmp_path):
    """Regression test for the real bug this guard fixes: request_calculation
    used to write `self._active_jobs[molecule_uuid] = job` with no check
    first, so a second call before the first finished silently overwrote
    the dict entry, orphaning the first QProcess. Exercised deterministically
    via the JobManager guard directly, no real subprocess timing race needed.
    """
    provider = FakeQuantumEngineProvider()
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    job_manager = JobManager()
    service = QuantumChemistryService(
        bus, settings, providers={provider.provider_id: provider}, job_manager=job_manager
    )

    job_manager.try_start("quantum_chemistry", "mol-1")

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


class _NmrSpectrumProvider(FakeQuantumEngineProvider):
    """Overrides only parse_spectrum_output -- exercises
    QuantumChemistryService's own wiring of that optional method, not the
    real ORCA parser (already covered directly in test_orca_engine.py)."""

    def parse_spectrum_output(self, output_text, mol, molecule_uuid: str, calc_type: str):
        if calc_type != "nmr":
            return None
        return SpectrumResult(
            spectrum_type="nmr_raw_shielding",
            name="Fake NMR",
            units="ppm",
            method=self.provider_id,
            molecule_uuid=molecule_uuid,
            values={0: 365.694},
            elements={0: "O"},
        )


def test_quantum_chemistry_publishes_spectrum_computed_for_nmr(qapp, tmp_path):
    provider = _NmrSpectrumProvider()
    service, bus = _make_service(tmp_path, provider)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    service.request_calculation(
        mol=Chem.MolFromSmiles("O"),
        molecule_uuid="mol-1",
        calc_type="nmr",
        charge=0,
        multiplicity=1,
        method_basis="HF STO-3G",
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert states[-1] == CacheState.COMPLETED
    assert len(spectra) == 1
    assert spectra[0].values == {0: 365.694}


def test_quantum_chemistry_does_not_publish_spectrum_for_non_nmr_calc_types(qapp, tmp_path):
    provider = _NmrSpectrumProvider()
    service, bus = _make_service(tmp_path, provider)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
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

    assert spectra == []


class _TmsLikeProvider(FakeQuantumEngineProvider):
    """Returns synthetic but internally-consistent TMS-shaped shielding
    (uniform per element, like TMS's real chemical equivalence) for
    reference-calibration tests, and molecule-specific shielding for a
    real molecule request keyed by molecule_uuid."""

    def parse_spectrum_output(self, output_text, mol, molecule_uuid: str, calc_type: str):
        if calc_type != "nmr":
            return None
        if molecule_uuid == "mol-1":
            return SpectrumResult(
                spectrum_type="nmr_raw_shielding", name="raw", units="ppm", method=self.provider_id,
                molecule_uuid=molecule_uuid, values={0: 100.0, 1: 25.0}, elements={0: "C", 1: "H"},
            )
        # TMS reference job -- 4 equivalent C, 12 equivalent H.
        values = {i: 190.0 for i in range(4)} | {i: 30.0 for i in range(4, 16)}
        elements = {i: "C" for i in range(4)} | {i: "H" for i in range(4, 16)}
        return SpectrumResult(
            spectrum_type="nmr_raw_shielding", name="raw", units="ppm", method=self.provider_id,
            molecule_uuid=molecule_uuid, values=values, elements=elements,
        )


def test_request_reference_calibration_caches_and_publishes(qapp, tmp_path):
    provider = _TmsLikeProvider()
    service, bus = _make_service(tmp_path, provider)

    calibrated = []
    bus.subscribe(NmrReferenceCalibrated, lambda e: calibrated.append(e))

    service.request_reference_calibration("B3LYP def2-SVP", provider_id="fake")

    assert _wait_until(qapp, lambda: calibrated)
    event = calibrated[0]
    assert event.error is None
    assert event.method_basis == "B3LYP def2-SVP"
    assert event.values == {"C": 190.0, "H": 30.0}
    assert not service._active_jobs


def test_request_reference_calibration_with_no_executable_publishes_error(qapp, tmp_path):
    provider = _TmsLikeProvider()
    bus = EventBus()
    settings = Settings(bus)  # no orca/executable_path set
    service = QuantumChemistryService(bus, settings, providers={"fake": provider})

    calibrated = []
    bus.subscribe(NmrReferenceCalibrated, lambda e: calibrated.append(e))

    service.request_reference_calibration("B3LYP def2-SVP", provider_id="fake")

    assert len(calibrated) == 1
    assert calibrated[0].error is not None
    assert calibrated[0].values == {}


def test_calibration_is_applied_to_a_subsequent_real_molecule_result(qapp, tmp_path):
    provider = _TmsLikeProvider()
    service, bus = _make_service(tmp_path, provider)

    calibrated = []
    bus.subscribe(NmrReferenceCalibrated, lambda e: calibrated.append(e))
    service.request_reference_calibration("B3LYP def2-SVP", provider_id="fake")
    assert _wait_until(qapp, lambda: calibrated)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    service.request_calculation(
        mol=Chem.MolFromSmiles("CO"),
        molecule_uuid="mol-1",
        calc_type="nmr",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: spectra)

    spectrum = spectra[0]
    assert spectrum.spectrum_type == "nmr_calibrated"
    # delta = reference - raw: C = 190-100=90, H = 30-25=5.
    assert spectrum.values == {0: 90.0, 1: 5.0}


def test_calibration_does_not_apply_for_a_different_uncalibrated_method_basis(qapp, tmp_path):
    provider = _TmsLikeProvider()
    service, bus = _make_service(tmp_path, provider)

    calibrated = []
    bus.subscribe(NmrReferenceCalibrated, lambda e: calibrated.append(e))
    service.request_reference_calibration("B3LYP def2-SVP", provider_id="fake")
    assert _wait_until(qapp, lambda: calibrated)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    service.request_calculation(
        mol=Chem.MolFromSmiles("CO"),
        molecule_uuid="mol-1",
        calc_type="nmr",
        charge=0,
        multiplicity=1,
        method_basis="PBE0 def2-TZVP",  # different method_basis, no cached reference
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: spectra)

    assert spectra[0].spectrum_type == "nmr_raw_shielding"  # unchanged, no reference for this method_basis


def test_reference_job_and_real_molecule_job_use_separate_job_manager_kinds(qapp, tmp_path):
    """A reference calibration and a real molecule's calculation must not
    collide on JobManager keys even if run concurrently."""
    provider = _TmsLikeProvider()
    job_manager = JobManager()
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(bus, settings, providers={"fake": provider}, job_manager=job_manager)

    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))
    calibrated = []
    bus.subscribe(NmrReferenceCalibrated, lambda e: calibrated.append(e))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CO"), molecule_uuid="mol-1", calc_type="nmr",
        charge=0, multiplicity=1, method_basis="B3LYP def2-SVP", provider_id="fake",
    )
    service.request_reference_calibration("B3LYP def2-SVP", provider_id="fake")

    assert _wait_until(qapp, lambda: calibrated and states and states[-1] == CacheState.COMPLETED)
    assert calibrated[0].error is None
    assert states[-1] == CacheState.COMPLETED


class _PerConformerProvider(FakeQuantumEngineProvider):
    """Returns a different SCF energy and a different shielding on each
    successive job, so a Boltzmann run over N conformers produces N
    genuinely distinct spectra to average -- the same subprocess runs every
    time, so without this every "conformer" would be identical and the
    averaging would be untestable.
    """

    def __init__(self, energies: list[float], shifts: list[float], sleep_seconds: float = 0.0) -> None:
        super().__init__(stdout_text="fake nmr output", sleep_seconds=sleep_seconds)
        self._energies = energies
        self._shifts = shifts
        self.calls = 0

    def parse_output(self, output_text: str, mol, molecule_uuid: str, calc_type: str):
        index = self.calls
        self.calls += 1
        descriptor = DescriptorValue(
            descriptor_id="fake.scf_energy",
            name="Fake SCF Energy",
            units="Hartree",
            category="quantum_chemistry",
            provider="fake",
            molecule_uuid=molecule_uuid,
            value=self._energies[index],
            cache_state=CacheState.COMPLETED,
        )
        return [descriptor], None

    def parse_spectrum_output(self, output_text: str, mol, molecule_uuid: str, calc_type: str):
        # parse_output ran first for this same job and already advanced the
        # counter, so the current conformer is calls - 1.
        index = self.calls - 1
        return NMRSpectrumResult(
            spectrum_type="nmr_raw_shielding",
            name="NMR Isotropic Shielding",
            units="ppm (isotropic shielding)",
            method="fake",
            molecule_uuid=molecule_uuid,
            values={0: self._shifts[index]},
            elements={0: "H"},
        )


def test_boltzmann_run_executes_one_job_per_conformer_and_publishes_one_spectrum(qapp, tmp_path):
    provider = _PerConformerProvider(energies=[-100.0, -100.0], shifts=[30.0, 10.0])
    service, bus = _make_service(tmp_path, provider)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    states: list[CacheState] = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e.state))

    mol = Chem.MolFromSmiles("CCO")
    service.request_boltzmann_nmr(
        mols=[mol, mol],
        molecule_uuid="mol-1",
        calc_type="nmr",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP pcSseg-1",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))

    assert states[-1] == CacheState.COMPLETED
    assert provider.calls == 2  # both conformers really ran
    # One event, not one per conformer -- the per-conformer shifts are an
    # intermediate, not something the NMR view should flicker through.
    assert len(spectra) == 1
    assert spectra[0].values[0] == pytest.approx(20.0)  # equal energies -> mean


def test_boltzmann_run_weights_by_the_scf_energy_of_each_run(qapp, tmp_path):
    """A 3 kcal/mol gap leaves the higher conformer effectively unpopulated,
    so the average must sit on the lower one -- proving the energies are
    really coming from each job rather than being ignored."""
    three_kcal = 3.0 / 627.5094740631
    provider = _PerConformerProvider(energies=[-100.0, -100.0 + three_kcal], shifts=[30.0, 10.0])
    service, bus = _make_service(tmp_path, provider)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))

    mol = Chem.MolFromSmiles("CCO")
    service.request_boltzmann_nmr(
        mols=[mol, mol], molecule_uuid="mol-1", calc_type="nmr",
        charge=0, multiplicity=1, method_basis="B3LYP pcSseg-1", provider_id="fake",
    )

    assert _wait_until(qapp, lambda: spectra)
    assert spectra[0].values[0] == pytest.approx(30.0, abs=0.2)


def test_boltzmann_run_holds_the_molecule_job_slot_for_the_whole_sequence(qapp, tmp_path):
    """Releasing the slot between conformers would let a second request
    start alongside the rest of the run and make Cancel unreachable."""
    provider = _PerConformerProvider(energies=[-100.0] * 3, shifts=[30.0, 20.0, 10.0])
    job_manager = JobManager()
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(bus, settings, providers={"fake": provider}, job_manager=job_manager)

    events = []
    bus.subscribe(QuantumChemistryJobStateChanged, events.append)

    mol = Chem.MolFromSmiles("CCO")
    service.request_boltzmann_nmr(
        mols=[mol, mol, mol], molecule_uuid="mol-1", calc_type="nmr",
        charge=0, multiplicity=1, method_basis="B3LYP pcSseg-1", provider_id="fake",
    )

    # Mid-run: the second request must be refused, not run concurrently.
    assert _wait_until(qapp, lambda: provider.calls >= 1)
    service.request_calculation(
        mol=mol, molecule_uuid="mol-1", calc_type="sp",
        charge=0, multiplicity=1, method_basis="HF STO-3G", provider_id="fake",
    )
    assert any("already running" in event.message for event in events)

    # Waits on the run's own progress, not on the last state event: the
    # refusal above publishes FAILED for this same molecule_uuid, so a
    # "last state is terminal" condition would return immediately while the
    # run is still going.
    assert _wait_until(qapp, lambda: provider.calls == 3)
    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))


def test_boltzmann_run_of_one_conformer_still_publishes_a_spectrum(qapp, tmp_path):
    provider = _PerConformerProvider(energies=[-100.0], shifts=[42.0])
    service, bus = _make_service(tmp_path, provider)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))

    service.request_boltzmann_nmr(
        mols=[Chem.MolFromSmiles("CCO")], molecule_uuid="mol-1", calc_type="nmr",
        charge=0, multiplicity=1, method_basis="B3LYP pcSseg-1", provider_id="fake",
    )

    assert _wait_until(qapp, lambda: spectra)
    assert spectra[0].values[0] == pytest.approx(42.0)


def test_boltzmann_run_with_no_conformers_fails_cleanly(qapp, tmp_path):
    provider = _PerConformerProvider(energies=[], shifts=[])
    service, bus = _make_service(tmp_path, provider)

    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, lambda e: states.append(e))

    service.request_boltzmann_nmr(
        mols=[], molecule_uuid="mol-1", calc_type="nmr",
        charge=0, multiplicity=1, method_basis="B3LYP pcSseg-1", provider_id="fake",
    )

    assert states[-1].state == CacheState.FAILED
    assert "No conformers" in states[-1].message


def test_cancelling_mid_run_stops_the_sequence_and_releases_the_slot(qapp, tmp_path):
    """Cancel must end the whole run, not just the conformer in flight --
    otherwise the next one would start immediately after the kill."""
    provider = _PerConformerProvider(
        energies=[-100.0] * 4, shifts=[30.0, 20.0, 10.0, 5.0], sleep_seconds=0.5
    )
    job_manager = JobManager()
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(bus, settings, providers={"fake": provider}, job_manager=job_manager)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    events = []
    bus.subscribe(QuantumChemistryJobStateChanged, events.append)

    mol = Chem.MolFromSmiles("CCO")
    service.request_boltzmann_nmr(
        mols=[mol] * 4, molecule_uuid="mol-1", calc_type="nmr",
        charge=0, multiplicity=1, method_basis="B3LYP pcSseg-1", provider_id="fake",
    )
    assert _wait_until(qapp, lambda: service._active_jobs.get("mol-1") is not None)
    service.cancel("mol-1")

    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))
    assert spectra == []  # no partial average published
    assert any("Cancelled by user" in event.message for event in events)
    assert "mol-1" not in service._boltzmann_runs

    # And nothing kept running: the remaining conformers were abandoned.
    calls_at_cancel = provider.calls
    qapp.processEvents()
    time.sleep(0.6)
    qapp.processEvents()
    assert provider.calls == calls_at_cancel


# --- Empirical scaling calibration ---------------------------------------

_TRUE_SLOPE = {"C": -1.05, "H": -0.98}
_TRUE_INTERCEPT = {"C": 186.0, "H": 31.4}


class ScalingCalibrationProvider(FakeQuantumEngineProvider):
    """Emits shieldings that lie EXACTLY on a known line for each element.

    So the calibration must recover `_TRUE_SLOPE`/`_TRUE_INTERCEPT` to
    within floating point -- a far sharper check than "the numbers look
    plausible", and it needs no ORCA. The real ORCA behaviour is pinned
    separately by the measured shieldings in `test_nmr_scaling.py`.
    """

    def __init__(self, skip: set[str] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._skip = skip or set()
        self.seen: list[str] = []

    def parse_spectrum_output(self, output_text, mol, molecule_uuid, calc_type):
        from rdkit import Chem

        from openchem.chem.nmr_scaling import REFERENCE_COMPOUNDS

        smiles = Chem.MolToSmiles(Chem.RemoveHs(mol))
        compound = next(
            (
                c
                for c in REFERENCE_COMPOUNDS
                if Chem.MolToSmiles(Chem.MolFromSmiles(c.smiles)) == smiles
            ),
            None,
        )
        if compound is None or compound.name in self._skip:
            return None
        self.seen.append(compound.name)

        values, elements = {}, {}
        for atom in mol.GetAtoms():
            element = atom.GetSymbol()
            shift = compound.shifts.get(element)
            if shift is None or element not in _TRUE_SLOPE:
                continue
            # Invert the line, so fitting it back recovers the line.
            values[atom.GetIdx()] = (shift - _TRUE_INTERCEPT[element]) / _TRUE_SLOPE[element]
            elements[atom.GetIdx()] = element
        if not values:
            return None
        return NMRSpectrumResult(
            spectrum_type="nmr_raw_shielding",
            name="Fake shielding",
            units="ppm",
            method="fake",
            molecule_uuid=molecule_uuid,
            values=values,
            elements=elements,
        )


def test_scaling_calibration_recovers_the_line_and_caches_it(qapp, tmp_path):
    provider = ScalingCalibrationProvider()
    service, bus = _make_service(tmp_path, provider)
    events = []
    bus.subscribe(NmrScalingCalibrated, events.append)

    service.request_scaling_calibration("B3LYP def2-SVP", provider_id="fake")

    assert _wait_until(qapp, lambda: events, timeout_seconds=60)
    event = events[0]
    assert event.error is None
    for element in ("C", "H"):
        assert event.factors[element].slope == pytest.approx(_TRUE_SLOPE[element])
        assert event.factors[element].intercept == pytest.approx(_TRUE_INTERCEPT[element])
        assert event.factors[element].r_squared == pytest.approx(1.0)
    # Every standard really ran, one ORCA job each.
    assert len(provider.seen) == 11
    assert not service._scaling_runs
    assert not service._active_jobs


def test_scaled_factors_are_used_in_preference_to_tms_subtraction(qapp, tmp_path):
    """Subtraction is scaling with the slope forced to -1, and that forced
    slope is most of the residual error -- so where both are cached, the
    fitted line has to win."""
    provider = ScalingCalibrationProvider()
    service, bus = _make_service(tmp_path, provider)
    calibrations = []
    bus.subscribe(NmrScalingCalibrated, calibrations.append)
    service.request_scaling_calibration("B3LYP def2-SVP", provider_id="fake")
    assert _wait_until(qapp, lambda: calibrations, timeout_seconds=60)

    # A stale TMS reference for the same method/basis, which must lose.
    service._settings.set("orca/nmr_reference/B3LYP def2-SVP/unknown/C", 999.0)

    spectra = []
    bus.subscribe(SpectrumComputed, lambda e: spectra.append(e.spectrum))
    service.request_calculation(
        mol=Chem.MolFromSmiles("c1ccccc1"),
        molecule_uuid="mol-1",
        calc_type="nmr",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )
    assert _wait_until(qapp, lambda: spectra, timeout_seconds=30)

    spectrum = spectra[0]
    assert spectrum.provenance.parameters["referencing"] == "empirical_linear_scaling"
    # Benzene's literature 13C shift, recovered through the fitted line
    # rather than the bogus 999.0 reference.
    assert all(value == pytest.approx(128.4) for value in spectrum.values.values())


def test_one_failed_standard_costs_a_point_not_the_calibration(qapp, tmp_path):
    """The fit needs four points, not eleven."""
    provider = ScalingCalibrationProvider(skip={"Benzene", "Acetylene"})
    service, bus = _make_service(tmp_path, provider)
    events = []
    bus.subscribe(NmrScalingCalibrated, events.append)

    service.request_scaling_calibration("B3LYP def2-SVP", provider_id="fake")

    assert _wait_until(qapp, lambda: events, timeout_seconds=60)
    assert events[0].error is None
    assert events[0].factors["C"].slope == pytest.approx(_TRUE_SLOPE["C"])
    # Two fewer standards contributed than the full set would have.
    assert events[0].factors["H"].sample_count < 9


def test_a_second_calibration_for_the_same_method_is_refused(qapp, tmp_path):
    provider = ScalingCalibrationProvider(sleep_seconds=0.5)
    service, bus = _make_service(tmp_path, provider)
    events = []
    bus.subscribe(NmrScalingCalibrated, events.append)

    service.request_scaling_calibration("B3LYP def2-SVP", provider_id="fake")
    service.request_scaling_calibration("B3LYP def2-SVP", provider_id="fake")

    assert events, "the second request should have been refused immediately"
    assert "already running" in events[0].error
    assert _wait_until(qapp, lambda: len(events) > 1, timeout_seconds=90)


def test_cancelling_a_calibration_reports_it_and_releases_the_slot(qapp, tmp_path):
    provider = ScalingCalibrationProvider(sleep_seconds=0.5)
    job_manager = JobManager()
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(
        bus, settings, providers={"fake": provider}, job_manager=job_manager
    )
    events = []
    bus.subscribe(NmrScalingCalibrated, events.append)

    service.request_scaling_calibration("B3LYP def2-SVP", provider_id="fake")
    key = "__nmr_scaling__::B3LYP def2-SVP"
    assert _wait_until(qapp, lambda: key in service._active_jobs)
    job_manager.cancel("quantum_chemistry_scaling", key)

    assert _wait_until(qapp, lambda: events, timeout_seconds=30)
    assert events[0].error == "Cancelled by user"
    assert not service._scaling_runs
    assert not job_manager.is_active("quantum_chemistry_scaling", key)


# ---------------------------------------------------------------------------
# ORCA ABORTS AT STARTUP ON A FORWARD-SLASH PATH
#
# ORCA derives the directory of its own helper binaries (`orca_startup` and
# friends) from the path it was invoked with, so `D:/ORCA/orca.exe` dies in
# `Startup` where `D:\ORCA\orca.exe` on the identical input terminates
# normally. Same mechanism as the already-known spaces-in-path failure, and
# it reads like a broken input file rather than a broken invocation.
#
# The exposure is the hand-editable path field in External Tools: a pasted
# forward-slash path is stored verbatim, `Path(p).is_file()` accepts it, so
# every check passes and the raw string reaches QProcess.
# ---------------------------------------------------------------------------


def test_a_configured_orca_path_is_resolved_in_native_separator_form(tmp_path):
    """The read-time half, which is what repairs an already-saved setting."""
    exe = tmp_path / "ORCA" / "orca.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")

    bus = EventBus()
    settings = Settings(bus)
    # What a paste into the External Tools field leaves behind.
    settings.set("orca/executable_path", exe.as_posix())
    assert "/" in exe.as_posix(), "the fixture must actually use forward slashes"

    service = QuantumChemistryService(bus, settings, providers={})
    resolved = service._resolve_executable_path()

    assert resolved == str(exe), (
        "the configured path reached the caller unnormalised; ORCA aborts in "
        "Startup on a forward-slash path"
    )
    # Asserting the SEPARATOR, not just equality -- on a POSIX machine both
    # forms are identical and this test would be vacuous, so say so.
    if os.sep == "\\":
        assert "/" not in resolved


def test_resolving_orca_does_not_invent_a_path_when_nothing_is_configured():
    """The control for the test above: normalising must not turn an empty
    setting into something. `str(Path(""))` is `"."`, which is a real
    directory and would make every 'is ORCA configured' check say yes."""
    bus = EventBus()
    settings = Settings(bus)  # nothing configured

    resolved = QuantumChemistryService(bus, settings, providers={})._resolve_executable_path()

    assert resolved != ".", "an empty setting was normalised into the current directory"
    # Either None, or whatever a real `orca` on PATH resolves to.
    assert resolved is None or Path(resolved).is_file()
