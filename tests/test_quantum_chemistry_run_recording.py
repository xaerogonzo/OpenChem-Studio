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
from openchem.chem.calculation_input import input_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.quantum_chemistry_run import OutputStatus, RunStatus
from openchem.domain.scientific_result import NMRSpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import (
    DescriptorComputed,
    NmrReferenceCalibrated,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    QuantumChemistryRunCompleted,
    ResultRecorded,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.services.result_store_service import ResultStoreService

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


def test_a_boltzmann_run_publishes_the_lowest_energy_conformers_descriptors(qapp, tmp_path):
    """A Boltzmann run has no averaging convention for a scalar like SCF
    energy the way it does for a spectrum's per-atom shifts (see
    `_BoltzmannRun.descriptors`'s docstring), so `_finish_conformer_job`
    publishes the LOWEST-energy conformer's own descriptors -- the same
    "current/latest value" wiring `_finish_calculation_job` uses for a
    single job (Phase 3), now reaching Results for a Boltzmann run too.

    Energies are deliberately NOT monotonic (middle one lowest) so this
    fails if the code picked the first or the last conformer instead of
    genuinely finding the minimum. The gaps are small (a fraction of a
    kcal/mol, comparable to kT at room temperature) rather than the 3
    kcal/mol `test_boltzmann_run_weights_by_the_scf_energy_of_each_run`
    uses to prove weighting works at all -- a 3 kcal/mol gap leaves the
    higher conformer's Boltzmann weight numerically indistinguishable
    from zero, which would make the weighted-average skeleton below
    collapse onto the lowest energy and prove nothing about the average.
    """
    kcal_per_hartree = 1.0 / 627.5094740631
    lowest_energy = -100.0 - 3 * kcal_per_hartree
    middle_energy = -100.0 - 2.7 * kcal_per_hartree
    provider = _PerConformerProvider(
        energies=[-100.0, lowest_energy, middle_energy], shifts=[30.0, 20.0, 10.0]
    )
    service, bus = _make_service(provider)
    ready: list = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: ready.append(e))
    recorded: list = []
    bus.subscribe(ResultRecorded, lambda e: recorded.append(e.stored))
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

    assert _wait_until(qapp, lambda: runs)

    # Exactly one QuantumChemistryResultReady for the whole sequence, not
    # one per conformer -- same contract as the averaged spectrum.
    assert len(ready) == 1
    assert [d.value for d in ready[0].descriptors] == [pytest.approx(lowest_energy)]

    # It also reached the generic revision-cache store, the same way
    # `_finish_calculation_job` does for a single job -- otherwise a
    # Boltzmann run's numbers would still vanish from Results on reselect.
    assert len(recorded) == 1
    assert recorded[0].result.value == pytest.approx(lowest_energy)

    qc_run = runs[0]
    assert [d.value for d in qc_run.results["descriptors"]] == [pytest.approx(lowest_energy)]
    # Skeleton weighted-average energy (docs/ROADMAP.md): not a descriptor,
    # just present in run history. The 0.3 kcal/mol gap to the middle
    # conformer is small enough that both meaningfully contribute, so the
    # weighted mean must land strictly above the lowest-energy pick above
    # (never collapse onto it) and strictly below the middle conformer.
    weighted = qc_run.results["boltzmann_average_scf_energy_hartree"]
    assert lowest_energy < weighted < middle_energy


def test_a_qc_descriptor_survives_replay_after_no_recompute(qapp, tmp_path):
    """Phase 3: PropertyPanel's 'current/latest value' display for every
    OTHER calculator already survives a molecule reselection/project
    reload through `ResultStoreService.replay()`, which republishes
    whatever the generic `store` holds as ordinary `DescriptorComputed`
    events. QC's headline numbers (SCF energy, HOMO/LUMO, ...) never
    reached that store at all before this -- they were live-only even for
    Results, not just for this panel. This is the mechanism-level proof:
    submit once, then replay with NO live job involved, and the same
    descriptor value comes back through the same event PropertyPanel
    already listens to.
    """
    provider = FakeQuantumEngineProvider(stdout_text="hello from fake orca")
    bus = EventBus()
    engine = ChemistryEngine()
    settings = Settings(bus)
    settings.set("orca/executable_path", sys.executable)
    service = QuantumChemistryService(bus, settings, providers={"fake": provider})
    store_service = ResultStoreService(bus, engine, settings)

    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    project = ProjectModel(name="Test")
    project.molecules.append(molecule)
    store_service.set_project(project)

    fingerprint = input_fingerprint(engine, molecule, DRAWING)
    service.request_calculation(
        mol=Chem.MolFromSmiles("CCO"),
        molecule_uuid=molecule.uuid,
        calc_type="sp",
        charge=0,
        multiplicity=1,
        method_basis="B3LYP def2-SVP",
        provider_id="fake",
        input_fingerprint=fingerprint,
        calculation_input=DRAWING,
    )
    assert _wait_until(qapp, lambda: store_service.store.molecule_uuids() == [molecule.uuid])

    # Simulate a completely fresh session: a new store built only from the
    # first one's saved/serialized form, no live job anywhere.
    from openchem.domain.result_store import SessionResultStore

    reloaded_store = SessionResultStore.from_dict(store_service.store.to_dict(), project.uuid)
    reloaded_service = ResultStoreService(EventBus(), engine, settings)
    reloaded_service.set_project(project, reloaded_store)

    received = []
    reloaded_service._event_bus.subscribe(DescriptorComputed, lambda e: received.append(e.descriptor))

    sent = reloaded_service.replay(molecule)

    assert any(d.descriptor_id == "fake.scf_energy" and d.value == -1.0 for d in received)
    assert sent
