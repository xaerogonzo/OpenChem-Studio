"""QuantumChemistryService -> QuantumChemistryRunCompleted -- the wiring
that gives every finished ORCA job a durable, run-scoped history record
(Phase 1 of the QC run identity/persistence work).

Reuses `FakeQuantumEngineProvider` (a real subprocess, not a mock of
QProcess) exactly the way `test_quantum_chemistry_service.py` already does,
so the service's actual QProcess lifecycle is exercised, not bypassed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from rdkit import Chem

from openchem import paths as app_paths
from openchem.app.settings import Settings
from openchem.chem.calculation_input import input_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.calculator import DRAWING
from openchem.domain.common import (
    RUN_CALC_TYPE,
    RUN_CHARGE,
    RUN_ID,
    RUN_METHOD_BASIS,
    RUN_MULTIPLICITY,
    RUN_PROVIDER,
    CacheState,
)
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.quantum_chemistry_run import OutputStatus, RunStatus
from openchem.domain.result_envelope import envelope_of
from openchem.domain.result_store import SessionResultStore, StoredResult
from openchem.domain.scientific_result import NMRSpectrumResult
from openchem.domain.turn_snapshot import Freshness, Outcome, ResultEntry
from openchem.events.base import EventBus
from openchem.events.events import (
    DescriptorComputed,
    NmrReferenceCalibrated,
    QuantumChemistryJobStateChanged,
    QuantumChemistryResultReady,
    QuantumChemistryRunCompleted,
    ResultRecorded,
    SpectrumComputed,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.services.result_cache import parameters_key
from openchem.services.result_identity import make_identity
from openchem.services.result_store_service import ResultStoreService

from test_orca_engine import REAL_DELTA_SCF_OUTPUT, SP_FIXTURE_OUTPUT, _delta_scf_mol
from test_quantum_chemistry_service import FakeQuantumEngineProvider, _NmrSpectrumProvider, _wait_until


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
    # The lowest conformer's descriptors, PLUS the one decided exception: the SCF
    # energy also averaged over the conformers, as its own labelled descriptor.
    lowest_d, averaged_d = ready[0].descriptors
    assert lowest_d.value == pytest.approx(lowest_energy)
    assert averaged_d.descriptor_id.endswith(".boltzmann_average_scf_energy")
    assert averaged_d.name == "SCF Energy (Boltzmann-averaged)"
    assert averaged_d.units == lowest_d.units
    assert lowest_energy < averaged_d.value < middle_energy
    assert averaged_d.provenance.parameters["averaged_over_conformers"] == 3

    # It also reached the generic revision-cache store, the same way
    # `_finish_calculation_job` does for a single job -- otherwise a
    # Boltzmann run's numbers would still vanish from Results on reselect.
    assert [r.result.value for r in recorded] == [pytest.approx(lowest_energy), pytest.approx(averaged_d.value)]

    qc_run = runs[0]
    assert [d.value for d in qc_run.results["descriptors"]] == [
        pytest.approx(lowest_energy), pytest.approx(averaged_d.value)
    ]
    # The same number also sits in run history as a plain value. The 0.3 kcal/mol gap to the middle
    # conformer is small enough that both meaningfully contribute, so the
    # weighted mean must land strictly above the lowest-energy pick above
    # (never collapse onto it) and strictly below the middle conformer.
    weighted = qc_run.results["boltzmann_average_scf_energy_hartree"]
    assert lowest_energy < weighted < middle_energy
    assert weighted == pytest.approx(averaged_d.value)


def test_a_single_conformer_run_adds_no_averaged_companion(qapp):
    """One conformer's average IS its own energy: a second row saying the same number
    twice would read as two results."""
    provider = _PerConformerProvider(energies=[-100.0], shifts=[30.0])
    service, bus = _make_service(provider)
    ready: list = []
    bus.subscribe(QuantumChemistryResultReady, lambda e: ready.append(e))
    runs: list = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    mol = Chem.MolFromSmiles("CCO")
    service.request_boltzmann_nmr(
        mols=[mol], molecule_uuid="mol-1", calc_type="nmr", charge=0, multiplicity=1,
        method_basis="B3LYP pcSseg-1", provider_id="fake",
    )
    assert _wait_until(qapp, lambda: runs)
    assert len(ready[0].descriptors) == 1


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


# ---------------------------------------------------------------------------
# What a stored QC number says it was run with.
#
# The provider parses an output TEXT and is never handed the method, basis or
# charge, so before the service stamped them a stored `orca.scf_energy` from
# B3LYP/def2-SVP and one from HF/STO-3G were indistinguishable -- to the
# reader, and to the assistant, which is promised every number's method and
# settings. These run the REAL `OrcaQuantumEngineProvider` over a captured
# transcript (streamed through a real subprocess and the service's real
# QProcess lifecycle) and read the result back through the REAL envelope.
# ---------------------------------------------------------------------------


class _OrcaTranscriptProvider(FakeQuantumEngineProvider):
    """A real subprocess that prints a captured ORCA transcript, which the real ORCA provider parses.

    Only the process is a stand-in (there is no ORCA on a CI runner); `build_input` and `command_args`
    are the fake's, `parse_output` is the real one's, so the descriptors are exactly what ORCA's would be.
    """

    provider_id = "orca"

    def __init__(self, transcript: str) -> None:
        super().__init__(stdout_text=transcript)
        self._orca = OrcaQuantumEngineProvider()

    def parse_output(self, output_text, mol, molecule_uuid: str, calc_type: str):
        self.parse_calls.append(output_text)
        return self._orca.parse_output(output_text, mol, molecule_uuid, calc_type)


class _Filed:
    """Everything one service publishes about its finished jobs, captured as it happens."""

    def __init__(self, qapp, provider: QuantumEngineProvider) -> None:
        self._qapp = qapp
        self.service, bus = _make_service(provider)
        self.provider_id = provider.provider_id
        self.recorded: list[StoredResult] = []
        self.ready: list[QuantumChemistryResultReady] = []
        self.runs: list = []
        self.spectra: list[SpectrumComputed] = []
        bus.subscribe(ResultRecorded, lambda e: self.recorded.append(e.stored))
        bus.subscribe(QuantumChemistryResultReady, self.ready.append)
        bus.subscribe(QuantumChemistryRunCompleted, lambda e: self.runs.append(e.run))
        bus.subscribe(SpectrumComputed, self.spectra.append)

    def calculate(self, mol, *, calc_type, method_basis, charge=0, multiplicity=1, fingerprint="fp-1") -> None:
        finished = len(self.runs)
        self.service.request_calculation(
            mol=mol, molecule_uuid="mol-1", calc_type=calc_type, charge=charge, multiplicity=multiplicity,
            method_basis=method_basis, provider_id=self.provider_id,
            input_fingerprint=fingerprint, calculation_input=DRAWING,
        )
        assert _wait_until(self._qapp, lambda: len(self.runs) > finished)
        assert self.runs[-1].status is RunStatus.COMPLETED


def _read(stored: StoredResult) -> dict:
    """The envelope the assistant is sent for `stored`, checked to be strict JSON."""
    envelope = envelope_of(ResultEntry(stored, Freshness.CURRENT, "ready", Outcome.COMPUTED))
    json.dumps(envelope, allow_nan=False)
    return envelope


def _as_the_service_files_it(descriptor) -> StoredResult:
    """The wrapping `_record_descriptors` does, for a descriptor that did not come through the service."""
    return StoredResult(
        identity=make_identity(
            molecule_uuid="mol-1", result=descriptor, calculation_input=DRAWING,
            input_fingerprint="fp-1", producer=descriptor.provider,
        ),
        result=descriptor,
        application_version="9.9",
    )


def test_a_single_point_filed_by_the_service_reads_with_its_method_and_basis(qapp):
    filed = _Filed(qapp, _OrcaTranscriptProvider(SP_FIXTURE_OUTPUT))
    # NON-DEFAULT on purpose (charge 0 / multiplicity 1 would also be the answer of a stamp that
    # invented its values): an anion doublet is the only reading that proves the job's own were used.
    filed.calculate(Chem.MolFromSmiles("CCO"), calc_type="sp", method_basis="B3LYP def2-SVP",
                    charge=-1, multiplicity=2)

    (stored,) = filed.recorded
    envelope = _read(stored)
    assert envelope["parameters"] == {
        "calc_type": "sp", "method_basis": "B3LYP def2-SVP", "charge": -1, "multiplicity": 2,
    }
    assert envelope["method"]["name"] == "orca"
    assert envelope["data"]["descriptor_id"] == "orca.scf_energy"

    # What the provider recorded survives beside it, and the run it came from is named.
    recorded = stored.result.provenance.parameters
    assert "orca_version" in recorded
    assert recorded[RUN_PROVIDER] == "orca"
    assert recorded[RUN_ID] == filed.runs[0].run_id and recorded[RUN_ID]

    # Not shown to a model as a setting: an address into the run history is not one, and the provider
    # is already the result's `calculator`. Nor is the producer's working.
    assert not {"orca_version", "id", "provider", "caveat"} & set(envelope["parameters"])
    assert not [name for name in envelope["parameters"] if name.startswith("run_")]


def test_the_control_without_the_stamp_is_the_defect(qapp):
    """What was filed before this: the provider's descriptor, straight. It reads as a bare 'orca'."""
    descriptors, _ = OrcaQuantumEngineProvider().parse_output(
        SP_FIXTURE_OUTPUT, Chem.MolFromSmiles("CCO"), "mol-1", "sp"
    )
    envelope = _read(_as_the_service_files_it(descriptors[0]))
    assert envelope["method"]["name"] == "orca" and envelope["parameters"] == {}


def test_the_event_the_store_and_the_run_hold_the_same_descriptors(qapp):
    filed = _Filed(qapp, _OrcaTranscriptProvider(SP_FIXTURE_OUTPUT))
    filed.calculate(Chem.MolFromSmiles("CCO"), calc_type="sp", method_basis="HF STO-3G")

    (stored,) = filed.recorded
    (event_descriptor,) = filed.ready[0].descriptors
    (run_descriptor,) = filed.runs[0].results["descriptors"]
    assert (
        event_descriptor.provenance.parameters
        == stored.result.provenance.parameters
        == run_descriptor.provenance.parameters
    )
    assert event_descriptor.provenance.parameters[RUN_METHOD_BASIS] == "HF STO-3G"


def test_a_delta_scf_result_reads_with_its_method_and_keeps_its_caveat(qapp):
    raw, _ = OrcaQuantumEngineProvider().parse_output(
        REAL_DELTA_SCF_OUTPUT, _delta_scf_mol(), "mol-1", "delta_scf"
    )
    caveats = {d.descriptor_id: d.provenance.parameters.get("caveat") for d in raw}
    assert any(caveats.values())  # the control: the provider does attach one, so keeping it means something

    filed = _Filed(qapp, _OrcaTranscriptProvider(REAL_DELTA_SCF_OUTPUT))
    filed.calculate(_delta_scf_mol(), calc_type="delta_scf", method_basis="B3LYP def2-SVP")

    assert {s.result.descriptor_id for s in filed.recorded} == set(caveats)
    for stored in filed.recorded:
        descriptor = stored.result
        envelope = _read(stored)
        assert envelope["parameters"] == {
            "calc_type": "delta_scf", "method_basis": "B3LYP def2-SVP", "charge": 0, "multiplicity": 1,
        }, descriptor.descriptor_id
        assert descriptor.provenance.parameters.get("caveat") == caveats[descriptor.descriptor_id]
        assert descriptor.provenance.parameters["orca_version"] == "6.1.1"
    hardness = next(s for s in filed.recorded if s.result.descriptor_id == "orca.dscf_hardness")
    assert hardness.result.value == pytest.approx(7.209887, abs=1e-6)
    assert _read(hardness)["data"]["value"] == 7.20989  # the envelope's six significant figures


def test_two_levels_of_theory_read_differently_but_are_filed_under_one_identity(qapp):
    """The store key must NOT move: a `parameters_key` built from the method would strand every saved
    project, and the store holds one current value per calculator by design. The label is what moves."""
    filed = _Filed(qapp, _OrcaTranscriptProvider(SP_FIXTURE_OUTPUT))
    mol = Chem.MolFromSmiles("CCO")
    filed.calculate(mol, calc_type="sp", method_basis="B3LYP def2-SVP")
    filed.calculate(mol, calc_type="sp", method_basis="HF STO-3G")

    first, second = filed.recorded
    assert first.identity == second.identity
    assert second.identity.parameters_key == parameters_key(None)

    # And it is the identity the unstamped descriptor would have had.
    raw, _ = OrcaQuantumEngineProvider().parse_output(SP_FIXTURE_OUTPUT, mol, "mol-1", "sp")
    assert _as_the_service_files_it(raw[0]).identity == first.identity

    read = [_read(first), _read(second)]
    assert read[0]["parameters"]["method_basis"] == "B3LYP def2-SVP"
    assert read[1]["parameters"]["method_basis"] == "HF STO-3G"
    assert read[0] != read[1]

    # The one value the store keeps is the second run's, and it says so.
    store = SessionResultStore("project-1")
    for stored in filed.recorded:
        store.put(stored)
    (held,) = store.all_results("mol-1")
    assert _read(held)["parameters"]["method_basis"] == "HF STO-3G"


def test_a_boltzmann_run_stamps_the_lowest_conformer_and_its_averaged_companion(qapp):
    from openchem.domain.calculator import ENSEMBLE

    provider = _PerConformerProvider(energies=[-100.0, -100.5], shifts=[30.0, 10.0])
    filed = _Filed(qapp, provider)
    mol = Chem.MolFromSmiles("CCO")
    filed.service.request_boltzmann_nmr(
        mols=[mol, mol], molecule_uuid="mol-1", calc_type="nmr", charge=1, multiplicity=2,
        method_basis="B3LYP pcSseg-1", provider_id="fake",
        input_fingerprint="fp-set", calculation_input=ENSEMBLE,
    )
    assert _wait_until(qapp, lambda: filed.runs)

    assert {s.result.descriptor_id for s in filed.recorded} == {
        "fake.scf_energy", "fake.boltzmann_average_scf_energy",
    }
    for stored in filed.recorded:
        assert _read(stored)["parameters"] == {
            "calc_type": "nmr", "method_basis": "B3LYP pcSseg-1", "charge": 1, "multiplicity": 2,
        }, stored.result.descriptor_id
        assert stored.result.provenance.parameters[RUN_ID] == filed.runs[0].run_id
    average = next(s for s in filed.recorded if s.result.descriptor_id.endswith("boltzmann_average_scf_energy"))
    assert average.result.provenance.parameters["averaged_over_conformers"] == 2


def test_a_jobs_spectra_and_descriptors_describe_it_in_the_same_words(qapp):
    """One builder behind both, so they cannot drift: a spectrum and a number from the same job."""
    filed = _Filed(qapp, _NmrSpectrumProvider())
    filed.calculate(Chem.MolFromSmiles("O"), calc_type="nmr", method_basis="HF STO-3G",
                    charge=-1, multiplicity=2)

    spectrum = filed.spectra[0].spectrum.provenance.parameters
    descriptor = filed.recorded[0].result.provenance.parameters
    keys = (RUN_CALC_TYPE, RUN_METHOD_BASIS, RUN_CHARGE, RUN_MULTIPLICITY, RUN_PROVIDER)
    assert {k: spectrum[k] for k in keys} == {k: descriptor[k] for k in keys}
    assert descriptor[RUN_CHARGE] == -1


def test_a_descriptor_saved_before_the_settings_were_recorded_still_loads_and_reads(qapp):
    """A project saved by the previous version holds the provider's descriptor with no `run_*` keys."""
    raw, _ = OrcaQuantumEngineProvider().parse_output(
        SP_FIXTURE_OUTPUT, Chem.MolFromSmiles("CCO"), "mol-1", "sp"
    )
    assert not [k for k in raw[0].provenance.parameters if k.startswith("run_")]
    old = SessionResultStore("project-1")
    old.put(_as_the_service_files_it(raw[0]))

    reloaded = SessionResultStore.from_dict(json.loads(json.dumps(old.to_dict())), "project-1")
    (stored,) = reloaded.all_results("mol-1")
    assert not reloaded.load_problems
    envelope = _read(stored)
    assert stored.result.value == pytest.approx(-154.987654123)
    assert envelope["parameters"] == {} and envelope["data"]["value"] == -154.988


def test_the_settings_survive_a_save_and_reload(qapp):
    filed = _Filed(qapp, _OrcaTranscriptProvider(SP_FIXTURE_OUTPUT))
    filed.calculate(Chem.MolFromSmiles("CCO"), calc_type="sp", method_basis="B3LYP def2-SVP",
                    charge=-1, multiplicity=2)
    saved = SessionResultStore("project-1")
    saved.put(filed.recorded[0])

    reloaded = SessionResultStore.from_dict(json.loads(json.dumps(saved.to_dict())), "project-1")
    (stored,) = reloaded.all_results("mol-1")
    assert not reloaded.load_problems
    assert stored.identity == filed.recorded[0].identity
    assert _read(stored)["parameters"] == {
        "calc_type": "sp", "method_basis": "B3LYP def2-SVP", "charge": -1, "multiplicity": 2,
    }
