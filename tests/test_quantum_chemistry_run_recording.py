"""QuantumChemistryService -> QuantumChemistryRunCompleted -- the wiring
that gives every finished ORCA job a durable, run-scoped history record
(Phase 1 of the QC run identity/persistence work).

Reuses `FakeQuantumEngineProvider` (a real subprocess, not a mock of
QProcess) exactly the way `test_quantum_chemistry_service.py` already does,
so the service's actual QProcess lifecycle is exercised, not bypassed.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from rdkit import Chem

from openchem import paths as app_paths
from openchem.app.settings import Settings
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.quantum_chemistry_run import OutputStatus, RunStatus
from openchem.domain.scientific_result import NMRSpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import (
    NmrReferenceCalibrated,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    QuantumChemistryRunCompleted,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.quantum_chemistry_service import QuantumChemistryService

from test_quantum_chemistry_service import FakeQuantumEngineProvider, _wait_until


@pytest.fixture(autouse=True)
def _scratch_under_tmp_path(tmp_path, monkeypatch):
    """Same isolation `test_quantum_chemistry_service.py` requires -- keep
    every job's scratch directory out of the developer's real cache."""
    root = tmp_path / "data-root"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(root))
    return root


def _make_service(provider: QuantumEngineProvider) -> tuple[QuantumChemistryService, EventBus]:
    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(bus, settings, providers={provider.provider_id: provider})
    return service, bus


class _NmrProvider(FakeQuantumEngineProvider):
    """An NMR calc_type that also reports spin-spin coupling, with a
    trigger (a fixed marker in the stdout the fake subprocess writes) to
    make the coupling parse fail without touching the real ORCA parser."""

    def __init__(self, *, fail_coupling: bool = False) -> None:
        super().__init__(stdout_text="fake nmr output")
        self._fail_coupling = fail_coupling

    def parse_spectrum_output(self, output_text, mol, molecule_uuid: str, calc_type: str):
        return NMRSpectrumResult(
            spectrum_type="nmr_raw_shielding",
            name="NMR Isotropic Shielding",
            units="ppm (isotropic shielding)",
            method="fake",
            molecule_uuid=molecule_uuid,
            values={0: 30.0},
            elements={0: "H"},
        )

    def parse_spin_spin_coupling(self, output_text: str, calc_type: str):
        if self._fail_coupling:
            raise ValueError("fake coupling parse failure")
        return {(0, 1): 12.3}


def test_a_completed_run_publishes_a_completed_qc_run(qapp, tmp_path):
    provider = FakeQuantumEngineProvider(stdout_text="hello from fake orca")
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: runs)
    run = runs[0]
    assert run.molecule_uuid == "mol-1"
    assert run.status is RunStatus.COMPLETED
    assert run.run_id  # minted, non-empty
    assert run.output_status["descriptors"] is OutputStatus.AVAILABLE
    assert run.results["descriptors"][0].value == -1.0
    assert run.completed_at is not None


def test_an_optimized_conformer_is_recorded_on_the_run(qapp, tmp_path):
    """`output_conformer_id` must be THIS run's optimized geometry -- not
    "whatever the molecule's latest conformer happens to be" -- so a later
    historical run's IR/Surfaces view can resolve the right one."""
    provider = FakeQuantumEngineProvider()  # calc_type != "sp" -> returns a conformer
    service, bus = _make_service(provider)
    ready: list = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: ready.append(e))
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid="mol-1",
        calc_type="opt",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: runs)
    assert ready[0].conformer is not None
    assert runs[0].output_conformer_id == ready[0].conformer.conformer_id


def test_a_core_parse_failure_still_produces_a_failed_run(qapp, tmp_path):
    """The `run_id` is minted at SUBMISSION, not at a successful finish --
    a job that never parses is still a historical execution, not a run
    that silently never existed."""
    provider = FakeQuantumEngineProvider(stdout_text="FAIL_PARSE")
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    states: list = []
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

    assert _wait_until(qapp, lambda: runs)
    assert states[-1] == CacheState.FAILED
    assert runs[0].status is RunStatus.FAILED
    assert runs[0].warnings


def test_a_coupling_parse_failure_makes_the_run_completed_with_warnings(qapp, tmp_path):
    """The base spectrum survives (an existing, correct contract -- see
    quantum_chemistry_service._finish_calculation_job); the RUN must say
    so was degraded rather than reading as a clean success."""
    provider = _NmrProvider(fail_coupling=True)
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CO"),
        molecule_uuid="mol-1",
        calc_type="nmr_coupling",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP pcSseg-1",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: runs)
    run = runs[0]
    assert run.status is RunStatus.COMPLETED_WITH_WARNINGS
    assert run.output_status["spectrum"] is OutputStatus.AVAILABLE
    assert run.results["spectrum"].coupling_error
    assert any("coupling" in w.lower() for w in run.warnings)


def test_a_clean_coupling_run_is_completed_not_completed_with_warnings(qapp, tmp_path):
    provider = _NmrProvider(fail_coupling=False)
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    service.request_calculation(
        mol=Chem.MolFromSmiles("CO"),
        molecule_uuid="mol-1",
        calc_type="nmr_coupling",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP pcSseg-1",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: runs)
    assert runs[0].status is RunStatus.COMPLETED
    assert runs[0].results["spectrum"].couplings == {(0, 1): 12.3}


def test_a_cancelled_job_produces_a_cancelled_run_not_a_failed_one(qapp, tmp_path):
    provider = FakeQuantumEngineProvider(sleep_seconds=5.0)
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    states: list = []
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
    assert _wait_until(qapp, lambda: CacheState.RUNNING in states, timeout_seconds=5)

    service.cancel("mol-1")

    assert _wait_until(qapp, lambda: runs, timeout_seconds=10)
    assert runs[0].status is RunStatus.CANCELLED


def test_reference_calibration_never_produces_a_qc_run(qapp, tmp_path):
    """TMS calibration is not a run on the user's molecule -- see
    quantum_chemistry_run.py's module docstring."""
    provider = FakeQuantumEngineProvider(stdout_text="fake nmr output")
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    calibrated: list = []
    bus.subscribe(NmrReferenceCalibrated, lambda e: calibrated.append(e))

    service.request_reference_calibration("B3LYP def2-SVP", provider_id="fake")

    assert _wait_until(qapp, lambda: calibrated)
    assert runs == []


def test_two_identical_submissions_mint_two_different_run_ids(qapp, tmp_path):
    """parameters/structure alone cannot distinguish two EXECUTIONS of the
    identical calculation -- run_id must, and it must differ every time."""
    provider = FakeQuantumEngineProvider(stdout_text="hello from fake orca")
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    for _ in range(2):
        service.request_calculation(
            mol=Chem.MolFromSmiles("CCO"),
            molecule_uuid="mol-1",
            calc_type="sp",
            charge=0,
            multiplicity=1,
            method_basis="B3LYP def2-SVP",
            provider_id="fake",
        )
        assert _wait_until(qapp, lambda: len(runs) == _ + 1)

    assert len(runs) == 2
    assert runs[0].run_id != runs[1].run_id


class _PerConformerProvider(FakeQuantumEngineProvider):
    def __init__(self, energies: list[float], shifts: list[float]) -> None:
        super().__init__(stdout_text="fake nmr output")
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


def test_a_boltzmann_run_publishes_exactly_one_qc_run_not_one_per_conformer(qapp, tmp_path):
    provider = _PerConformerProvider(energies=[-100.0, -100.0, -100.0], shifts=[30.0, 20.0, 10.0])
    service, bus = _make_service(provider)
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    mol = Chem.MolFromSmiles("CCO")
    service.request_boltzmann_nmr(
        mols=[mol, mol, mol],
        molecule_uuid="mol-1",
        calc_type="nmr",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP pcSseg-1",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: provider.calls == 3)
    assert _wait_until(qapp, lambda: runs)
    assert len(runs) == 1
    assert runs[0].status is RunStatus.COMPLETED
    assert runs[0].calculation_input == ""  # no ensemble identity was passed in this test
