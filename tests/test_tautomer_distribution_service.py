"""Service-layer tests for `QuantumChemistryService.request_tautomer_distribution`
-- the real sequential-job orchestration, mirroring
`test_quantum_chemistry_service.py`'s own Boltzmann-run test patterns
(a real subprocess standing in for ORCA, never a mocked QProcess).

No real ORCA here -- that is Phase I's separate, explicitly-flagged live
validation run. This file proves the orchestration: one job per candidate,
a per-candidate parse failure that does NOT abort the sequence, the
molecule-level single-flight slot, cancellation, and that the published
result survives this project's own save/load codec exactly.
"""

from __future__ import annotations

import json
import sys

import pytest
from rdkit import Chem

from openchem import paths as app_paths
from openchem.app.settings import Settings
from openchem.chem.tautomer_distribution import generate_tautomer_candidates
from openchem.domain import result_codec
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.events.base import EventBus
from openchem.events.events import (
    QuantumChemistryJobStateChanged,
    QuantumChemistryRunCompleted,
    TautomerDistributionResultReady,
)
from openchem.plugins.interfaces import QuantumEngineProvider
from openchem.services.job_manager import JobManager
from openchem.services.quantum_chemistry_service import QuantumChemistryService

from test_quantum_chemistry_service import FakeQuantumEngineProvider, _wait_until

CYCLOHEXANONE = "O=C1CCCCC1"


class _PerCandidateProvider(FakeQuantumEngineProvider):
    """Returns a different SCF energy per successive job, like
    `test_quantum_chemistry_service.py`'s own `_PerConformerProvider` --
    plus the ability to make specific calls fail to parse or report no
    usable energy, which a conformer-only fixture never needed to."""

    def __init__(
        self,
        energies: list[float],
        fail_to_parse_at: set[int] | None = None,
        no_energy_at: set[int] | None = None,
    ) -> None:
        super().__init__(stdout_text="fake opt output")
        self._energies = energies
        self._fail_to_parse_at = fail_to_parse_at or set()
        self._no_energy_at = no_energy_at or set()
        self.calls = 0

    def parse_output(self, output_text, mol, molecule_uuid, calc_type):
        index = self.calls
        self.calls += 1
        if index in self._fail_to_parse_at:
            raise RuntimeError(f"fake convergence failure at candidate {index}")
        if index in self._no_energy_at:
            return [], None
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
    service = QuantumChemistryService(
        bus, settings, providers={provider.provider_id: provider}, job_manager=job_manager
    )
    return service, bus


def _two_real_candidates():
    """Cyclohexanone's keto/enol tautomers, deterministically embedded --
    the same real `chem.tautomer_distribution` candidate-generation path
    an actual caller would use, not a hand-built stand-in."""
    candidates, embedding_failures = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE))
    assert embedding_failures == 0
    assert len(candidates) >= 2
    return candidates[:2]


def test_runs_one_job_per_candidate_and_publishes_exactly_one_result(qapp):
    candidates = _two_real_candidates()
    provider = _PerCandidateProvider(energies=[-100.0, -99.999])
    service, bus = _make_service(provider)

    results = []
    bus.subscribe(TautomerDistributionResultReady, lambda e: results.append(e))

    service.request_tautomer_distribution(
        candidates=candidates,
        molecule_uuid="mol-1",
        charge=0,
        multiplicity=1,
        method_basis="HF STO-3G",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: results)
    assert provider.calls == 2
    assert len(results) == 1
    result = results[0].result
    assert len(result.entries) == 2
    assert all(entry.metadata["status"] == "succeeded" for entry in result.entries)
    assert result.provenance.parameters["complete"] is True
    assert result.provenance.parameters["candidate_count_succeeded"] == 2


def test_a_parse_failure_on_one_candidate_does_not_abort_the_sequence(qapp):
    """The key behavioural difference from a Boltzmann run: a per-candidate
    convergence/parse failure continues to the next candidate instead of
    discarding the whole operation."""
    candidates = _two_real_candidates()
    provider = _PerCandidateProvider(energies=[-100.0, -99.999], fail_to_parse_at={0})
    service, bus = _make_service(provider)

    results = []
    bus.subscribe(TautomerDistributionResultReady, lambda e: results.append(e))

    service.request_tautomer_distribution(
        candidates=candidates,
        molecule_uuid="mol-1",
        charge=0,
        multiplicity=1,
        method_basis="HF STO-3G",
        provider_id="fake",
    )

    assert _wait_until(qapp, lambda: results)
    assert provider.calls == 2  # the second candidate still ran
    result = results[0].result
    assert len(result.entries) == 2
    statuses = {e.metadata["status"] for e in result.entries}
    assert statuses == {"succeeded", "failed"}
    # Incomplete -- no score/population on ANY entry, even the survivor.
    assert all(entry.score is None for entry in result.entries)
    assert result.provenance.parameters["complete"] is False
    assert result.provenance.parameters["candidate_count_succeeded"] == 1
    assert result.provenance.parameters["candidate_count_failed"] == 1


def test_a_candidate_with_no_parseable_scf_energy_is_recorded_as_failed(qapp):
    candidates = _two_real_candidates()
    provider = _PerCandidateProvider(energies=[-100.0, -99.999], no_energy_at={1})
    service, bus = _make_service(provider)

    results = []
    bus.subscribe(TautomerDistributionResultReady, lambda e: results.append(e))
    service.request_tautomer_distribution(
        candidates=candidates, molecule_uuid="mol-1", charge=0, multiplicity=1,
        method_basis="HF STO-3G", provider_id="fake",
    )

    assert _wait_until(qapp, lambda: results)
    failed = next(e for e in results[0].result.entries if e.metadata["status"] == "failed")
    assert failed.metadata["failure_reason_code"] == "energy_unparseable"


def test_holds_the_molecule_job_slot_for_the_whole_sequence(qapp):
    candidates = _two_real_candidates()
    provider = _PerCandidateProvider(energies=[-100.0, -99.999])
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)

    events = []
    bus.subscribe(QuantumChemistryJobStateChanged, events.append)

    service.request_tautomer_distribution(
        candidates=candidates, molecule_uuid="mol-1", charge=0, multiplicity=1,
        method_basis="HF STO-3G", provider_id="fake",
    )

    assert _wait_until(qapp, lambda: provider.calls >= 1)
    service.request_calculation(
        mol=Chem.MolFromSmiles("C"), molecule_uuid="mol-1", calc_type="sp",
        charge=0, multiplicity=1, method_basis="HF STO-3G", provider_id="fake",
    )
    assert any("already running" in event.message for event in events)

    assert _wait_until(qapp, lambda: provider.calls == 2)
    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))


def test_cancelling_mid_distribution_publishes_no_result_and_releases_the_slot(qapp):
    candidates = _two_real_candidates() + _two_real_candidates()  # pad so cancel has time to land
    provider = _PerCandidateProvider(energies=[-100.0] * 4)
    job_manager = JobManager()
    service, bus = _make_service(provider, job_manager=job_manager)

    results = []
    bus.subscribe(TautomerDistributionResultReady, lambda e: results.append(e))
    events = []
    bus.subscribe(QuantumChemistryJobStateChanged, events.append)

    service.request_tautomer_distribution(
        candidates=candidates, molecule_uuid="mol-1", charge=0, multiplicity=1,
        method_basis="HF STO-3G", provider_id="fake",
    )
    assert _wait_until(qapp, lambda: service._active_jobs.get("mol-1") is not None)
    service.cancel("mol-1")

    assert _wait_until(qapp, lambda: not job_manager.is_active("quantum_chemistry", "mol-1"))
    assert results == []
    assert any("Cancelled by user" in event.message for event in events)
    assert "mol-1" not in service._tautomer_runs


def test_no_candidates_fails_cleanly(qapp):
    provider = _PerCandidateProvider(energies=[])
    service, bus = _make_service(provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)

    service.request_tautomer_distribution(
        candidates=[], molecule_uuid="mol-1", charge=0, multiplicity=1,
        method_basis="HF STO-3G", provider_id="fake",
    )

    assert states[-1].state == CacheState.FAILED
    assert "No tautomer candidates" in states[-1].message


def test_a_single_quantum_chemistry_run_is_recorded_for_the_whole_operation_not_per_candidate(qapp):
    candidates = _two_real_candidates()
    provider = _PerCandidateProvider(energies=[-100.0, -99.999])
    service, bus = _make_service(provider)

    runs = []
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    service.request_tautomer_distribution(
        candidates=candidates, molecule_uuid="mol-1", charge=0, multiplicity=1,
        method_basis="HF STO-3G", provider_id="fake",
    )

    assert _wait_until(qapp, lambda: runs)
    assert len(runs) == 1  # NOT one per candidate
    run = runs[0]
    assert run.calc_type == "tautomer_distribution"
    assert "tautomer_distribution" in run.results
    assert run.results["tautomer_distribution"].molecule_uuid == "mol-1"


def test_the_published_result_round_trips_through_the_save_codec_exactly(qapp):
    """The scientific-integrity requirement from the plan: reopening a
    project must never turn a known-incomplete run into one that reads as
    complete, and every candidate's identity/status/energy must survive a
    real JSON round trip through this project's own save codec."""
    candidates = _two_real_candidates()
    provider = _PerCandidateProvider(energies=[-100.0, -99.999], fail_to_parse_at={0})
    service, bus = _make_service(provider)

    results = []
    bus.subscribe(TautomerDistributionResultReady, lambda e: results.append(e))
    service.request_tautomer_distribution(
        candidates=candidates, molecule_uuid="mol-1", charge=0, multiplicity=1,
        method_basis="HF STO-3G", provider_id="fake",
    )
    assert _wait_until(qapp, lambda: results)
    original = results[0].result

    encoded = result_codec.encode(original)
    # A REAL json.dumps/loads round trip, not just the in-memory dict --
    # this is what a `.ocsproj` save/load actually does.
    restored = result_codec.decode(json.loads(json.dumps(encoded)))

    assert restored.set_id == original.set_id
    assert len(restored.entries) == len(original.entries) == 2
    for original_entry, restored_entry in zip(original.entries, restored.entries, strict=True):
        assert restored_entry.metadata["status"] == original_entry.metadata["status"]
        assert restored_entry.metadata["fingerprint"] == original_entry.metadata["fingerprint"]
        assert restored_entry.energy == original_entry.energy
        assert restored_entry.score == original_entry.score
    assert restored.provenance.parameters["complete"] is False
    assert restored.provenance.parameters["complete"] == original.provenance.parameters["complete"]
    assert restored.provenance.parameters["candidate_count_failed"] == 1
