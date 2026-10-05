"""Tautomer NMR (P5, step 2): choosing the structures out of a stored distribution, and running NMR on them.

The ORCA process is a real subprocess standing in for it (never a mocked QProcess); what is checked is the
orchestration: one job per structure, referencing with the cached reference, per-structure failure that does not
end the run, a missing reference that does, cancellation, the slot being released, and that nothing here ever
reaches the molecule's own spectrum.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem import paths as app_paths
from openchem.chem.tautomer_nmr import NmrJob, TautomerNmrTarget, targets_from_distribution
from openchem.domain.scientific_result import NMRSpectrumResult, StructureEntry, StructureSetResult
from openchem.events.events import (
    QuantumChemistryJobStateChanged,
    QuantumChemistryRunCompleted,
    SpectrumComputed,
    TautomerNmrResultReady,
)

sys.path.insert(0, str(Path(__file__).parent))
from test_quantum_chemistry_service import FakeQuantumEngineProvider, _wait_until  # noqa: E402
from test_tautomer_distribution_service import _make_service  # noqa: E402


# --- choosing the structures ---------------------------------------------------------------------------


def _entry(label, tautomer, fingerprint, *, energy=0.0, representative=False, status="succeeded", stereo="s1",
           conformer=0, geometry="GEOM", absolute=-100.0):
    metadata = {
        "tautomer_fingerprint": tautomer, "fingerprint": fingerprint, "status": status,
        "is_lowest_calculated_for_tautomer": representative, "stereo_fingerprint": stereo,
        "conformer_index": conformer,
    }
    if status == "succeeded":
        metadata["absolute_energy_hartree"] = absolute
        if geometry:
            metadata["optimized_molblock"] = f"{geometry}-{fingerprint}"
    return StructureEntry(molblock=f"2D-{fingerprint}", label=label, energy=energy, metadata=metadata)


def _result(entries):
    return StructureSetResult(set_id="orca.tautomer_distribution", name="t", method="orca",
                              molecule_uuid="m", entries=list(entries))


def test_one_structure_per_tautomer_is_its_representative_in_energy_order():
    result = _result([
        _entry("OC=C [conf 2/2]", "T2", "t2b", energy=3.0, conformer=1),
        _entry("OC=C [conf 1/2]", "T2", "t2a", energy=3.0, representative=True, conformer=0),
        _entry("C=O", "T1", "t1a", energy=0.0, representative=True),
    ])
    targets, problems = targets_from_distribution(result)
    assert problems == []
    assert [(t.tautomer_fingerprint, t.label) for t in targets] == [("T1", "C=O"), ("T2", "OC=C")]
    assert [j.candidate_fingerprint for t in targets for j in t.jobs] == ["t1a", "t2a"]
    assert targets[1].jobs[0].optimized_molblock == "GEOM-t2a" and targets[1].display_molblock == "2D-t2a"


def test_per_conformer_takes_every_succeeded_conformer_of_the_representative_stereoisomer_only():
    result = _result([
        _entry("A [1 of 2] [conf 1/2]", "T", "a0", representative=True, stereo="sA", conformer=0, absolute=-100.0),
        _entry("A [1 of 2] [conf 2/2]", "T", "a1", stereo="sA", conformer=1, absolute=-99.99),
        _entry("A [2 of 2]", "T", "b0", stereo="sB", conformer=0),  # a different stereoisomer: never averaged in
        _entry("A [1 of 2] [conf 3/3]", "T", "a2", stereo="sA", conformer=2, status="failed"),
    ])
    (target,), problems = targets_from_distribution(result, per_conformer=True)
    assert problems == [] and [j.candidate_fingerprint for j in target.jobs] == ["a0", "a1"]
    assert [j.absolute_energy_hartree for j in target.jobs] == [-100.0, -99.99]


def test_a_tautomer_with_no_stored_geometry_or_no_success_is_reported_never_substituted():
    result = _result([
        _entry("A", "T1", "a", representative=True, geometry=""),
        _entry("B", "T2", "b", status="failed"),
        _entry("C", "T3", "c", representative=True),
    ])
    targets, problems = targets_from_distribution(result)
    assert [t.tautomer_fingerprint for t in targets] == ["T3"]
    assert len(problems) == 2
    assert any("not stored" in p and p.startswith("A:") for p in problems)
    assert any("no candidate" in p and p.startswith("B:") for p in problems)


def test_one_conformer_missing_its_geometry_fails_the_tautomer_rather_than_averaging_a_subset():
    result = _result([
        _entry("A", "T", "a0", representative=True, stereo="sA"),
        _entry("A", "T", "a1", stereo="sA", conformer=1, geometry=""),
    ])
    targets, problems = targets_from_distribution(result, per_conformer=True)
    assert targets == [] and "1 of 2" in problems[0]


def test_a_succeeded_candidate_with_no_recorded_energy_is_reported_not_raised():
    entry = _entry("A", "T1", "a", representative=True)
    del entry.metadata["absolute_energy_hartree"]
    targets, problems = targets_from_distribution(_result([entry]))
    assert targets == [] and "not stored" in problems[0]


# --- running it ----------------------------------------------------------------------------------------

METHOD = "HF STO-3G"


class _NmrProvider(FakeQuantumEngineProvider):
    """A fake ORCA whose `nmr` job yields a raw shielding per carbon, different per job, and can fail one."""

    def __init__(self, fail_at=(), sleep_seconds=0.0) -> None:
        super().__init__(stdout_text="fake nmr", sleep_seconds=sleep_seconds)
        self.fail_at = set(fail_at)
        self.spectrum_calls = 0

    def parse_spectrum_output(self, output_text, mol, molecule_uuid, calc_type):
        index = self.spectrum_calls
        self.spectrum_calls += 1
        if index in self.fail_at:
            raise RuntimeError("fake nmr parse failure")
        carbons = [a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "C"]
        return NMRSpectrumResult(
            spectrum_type="nmr_raw_shielding", name="NMR Isotropic Shielding",
            units="ppm (isotropic shielding)", method="fake", molecule_uuid=molecule_uuid,
            values={i: 100.0 + i + 10 * index for i in carbons}, elements={i: "C" for i in carbons},
        )


@pytest.fixture(autouse=True)
def _scratch(tmp_path, monkeypatch):
    root = tmp_path / "data-root"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(root))


def _geometry(smiles):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return Chem.MolToMolBlock(mol)


def _target(name, smiles, *energies):
    jobs = tuple(NmrJob(f"{name}-{i}", _geometry(smiles), e) for i, e in enumerate(energies))
    return TautomerNmrTarget(name, name, "2D", jobs)


def _service(provider, *, reference=True):
    service, bus = _make_service(provider)
    if reference:
        service._settings.set(f"orca/nmr_reference/{METHOD}/unknown/C", 180.0)
    return service, bus


def _run(service, targets, **kwargs):
    service.request_tautomer_nmr(
        targets=targets, molecule_uuid="mol-1", charge=0, multiplicity=1, method_basis=METHOD,
        provider_id="fake", parent_run_id="parent-run", **kwargs,
    )


def test_one_nmr_job_per_tautomer_referenced_and_published_once(qapp):
    provider = _NmrProvider()
    service, bus = _service(provider)
    results, shifts, runs = [], [], []
    bus.subscribe(TautomerNmrResultReady, results.append)
    bus.subscribe(SpectrumComputed, shifts.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    _run(service, [_target("keto", "CC(C)=O", -100.0), _target("enol", "C=C(C)O", -99.99)])
    assert _wait_until(qapp, lambda: results and runs)
    assert provider.spectrum_calls == 2 and len(results) == 1
    result = results[0].result
    assert result.complete and result.parent_run_id == "parent-run" and result.per_conformer is False
    keto, enol = result.entries
    assert keto.weights == (1.0,) and keto.spectrum.spectrum_type != "nmr_raw_shielding"
    for index, value in keto.spectrum.values.items():  # 180 - sigma, the cached reference
        assert value == pytest.approx(180.0 - (100.0 + index))
    assert enol.spectrum.values and all(v == pytest.approx(180.0 - (110.0 + i)) for i, v in enol.spectrum.values.items())
    assert shifts == []  # never reaches the molecule's own spectrum: these are the candidates' atom indices
    assert len(runs) == 1 and runs[0].calc_type == "tautomer_nmr" and runs[0].results["tautomer_nmr"] is result


def test_conformers_of_a_tautomer_are_boltzmann_averaged_atom_by_atom(qapp):
    provider = _NmrProvider()
    service, bus = _service(provider)
    results = []
    bus.subscribe(TautomerNmrResultReady, results.append)
    _run(service, [_target("keto", "CC(C)=O", -100.0, -100.0)], per_conformer=True)
    assert _wait_until(qapp, lambda: results)
    (entry,) = results[0].result.entries
    assert provider.spectrum_calls == 2 and results[0].result.per_conformer is True
    assert entry.weights == pytest.approx((0.5, 0.5)) and len(entry.job_fingerprints) == 2
    for index, value in entry.spectrum.values.items():  # mean of 180-(100+i) and 180-(110+i)
        assert value == pytest.approx(180.0 - (105.0 + index))


def test_one_structure_failing_is_recorded_and_the_run_continues(qapp):
    provider = _NmrProvider(fail_at={0})
    service, bus = _service(provider)
    results, runs = [], []
    bus.subscribe(TautomerNmrResultReady, results.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    _run(service, [_target("keto", "CC(C)=O", -100.0), _target("enol", "C=C(C)O", -99.99)])
    assert _wait_until(qapp, lambda: results and runs)
    keto, enol = results[0].result.entries
    assert keto.spectrum is None and "could not be parsed" in keto.failure and enol.spectrum is not None
    assert results[0].result.complete is False  # an incomplete result is shown, never averaged
    assert runs[0].status.value == "completed_with_warnings"


def test_one_failed_conformer_fails_its_tautomer_instead_of_averaging_the_survivors(qapp):
    provider = _NmrProvider(fail_at={1})
    service, bus = _service(provider)
    results = []
    bus.subscribe(TautomerNmrResultReady, results.append)
    _run(service, [_target("keto", "CC(C)=O", -100.0, -100.0)], per_conformer=True)
    assert _wait_until(qapp, lambda: results)
    (entry,) = results[0].result.entries
    assert entry.spectrum is None and entry.weights == ()


def test_without_a_cached_reference_the_run_stops_at_the_first_result_and_publishes_nothing(qapp):
    provider = _NmrProvider()
    service, bus = _service(provider, reference=False)
    results, states, runs = [], [], []
    bus.subscribe(TautomerNmrResultReady, results.append)
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))
    _run(service, [_target("keto", "CC(C)=O", -100.0), _target("enol", "C=C(C)O", -99.99)])
    assert _wait_until(qapp, lambda: any("No NMR reference" in s.message for s in states))
    assert provider.spectrum_calls == 1  # it did not spend the rest of the run on shieldings
    assert results == []
    # The molecule's slot is free again: a new request is accepted, not refused as "already running".
    _run(service, [_target("keto", "CC(C)=O", -100.0)])
    assert _wait_until(qapp, lambda: provider.spectrum_calls == 2)


def test_cancelling_publishes_no_result_and_frees_the_slot(qapp):
    provider = _NmrProvider(sleep_seconds=3)
    service, bus = _service(provider)
    results = []
    bus.subscribe(TautomerNmrResultReady, results.append)
    _run(service, [_target("keto", "CC(C)=O", -100.0), _target("enol", "C=C(C)O", -99.99)])
    service.cancel("mol-1")
    assert not _wait_until(qapp, lambda: results, timeout_seconds=1.5)
    _run(service, [_target("keto", "CC(C)=O", -100.0)])  # slot free again
    assert _wait_until(qapp, lambda: provider.spectrum_calls >= 1, timeout_seconds=15)


def test_an_unreadable_stored_geometry_fails_that_structure_and_still_releases_the_slot(qapp):
    provider = _NmrProvider()
    service, bus = _service(provider)
    results = []
    bus.subscribe(TautomerNmrResultReady, results.append)
    bad = TautomerNmrTarget("bad", "bad", "2D", (NmrJob("bad-0", "not a molblock", -100.0),))
    _run(service, [bad])  # nothing launchable at all: finishes inside the request
    assert _wait_until(qapp, lambda: results)
    assert results[0].result.entries[0].failure == "the stored geometry could not be read"
    assert provider.spectrum_calls == 0
    _run(service, [_target("keto", "CC(C)=O", -100.0)])  # a second request is accepted: the slot was released
    assert _wait_until(qapp, lambda: len(results) == 2)


def test_two_requests_for_one_molecule_are_refused_not_interleaved(qapp):
    provider = _NmrProvider(sleep_seconds=1)
    service, bus = _service(provider)
    states = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    _run(service, [_target("keto", "CC(C)=O", -100.0)])
    _run(service, [_target("enol", "C=C(C)O", -99.99)])
    assert any("already running" in s.message for s in states)


def test_the_result_survives_the_project_codec_exactly():
    """A tautomer-NMR result sits in a stored run, so a saved project carries it."""
    from openchem.domain import result_codec
    from openchem.domain.scientific_result import TautomerNmrEntry, TautomerNmrResult

    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_13c", name="n", units="ppm", method="orca", molecule_uuid="m",
        values={0: 12.5, 3: 130.0}, elements={0: "C", 3: "C"},
    )
    result = TautomerNmrResult(
        molecule_uuid="m", run_id="r", parent_run_id="p", method_basis=METHOD, per_conformer=True,
        entries=(
            TautomerNmrEntry("T1", "CC=O", "2D", ("a", "b"), (0.7, 0.3), spectrum),
            TautomerNmrEntry("T2", "C=CO", "2D", ("c",), (), None, "ORCA produced no shielding data"),
        ),
        skipped=("T3: not stored",),
    )
    decoded = result_codec.decode(result_codec.encode(result))
    assert decoded == result and decoded.complete is False
