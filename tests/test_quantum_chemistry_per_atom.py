"""A finished ORCA job that yields per-atom datasets (the condensed Fukui functions), through the real service.

The process is a stand-in (a real subprocess printing a captured transcript); the PARSE is the real ORCA provider's,
fed the verbatim extracts of a real run (`tests/fixtures/orca/water_fukui.out`), so the datasets are exactly what
ORCA's would be. The harness is the one `test_quantum_chemistry_run_recording.py` already uses for descriptors.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import (
    RUN_CALC_TYPE,
    RUN_CHARGE,
    RUN_ID,
    RUN_METHOD_BASIS,
    RUN_MULTIPLICITY,
    CacheState,
)
from openchem.domain.quantum_chemistry_run import OutputStatus, QuantumChemistryRun, RunStatus
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.events import (
    PerAtomDataComputed,
    QuantumChemistryJobStateChanged,
    QuantumChemistryRunCompleted,
    ResultRecorded,
)

from test_quantum_chemistry_run_recording import (
    _Filed,
    _make_service,
    _OrcaTranscriptProvider,
    _read,
    _scratch_under_tmp_path,  # noqa: F401  (autouse fixture)
)
from test_quantum_chemistry_service import FakeQuantumEngineProvider, _wait_until

FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "water_fukui.out"
TRANSCRIPT = FIXTURE.read_text(encoding="utf-8")

IDS = ["orca.fukui_plus", "orca.fukui_minus", "orca.fukui_zero", "orca.fukui_dual"]


def _water():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


class _Transcript(_OrcaTranscriptProvider):
    """The shared transcript provider forwards only `parse_output` to the real parser; the per-atom hook is
    forwarded here too, so the datasets are the real provider's."""

    def parse_per_atom_output(self, output_text, mol, molecule_uuid, calc_type):
        return self._orca.parse_per_atom_output(output_text, mol, molecule_uuid, calc_type)


class _Landed(_Filed):
    """`_Filed`, plus the per-atom events and a geometry fingerprint on the request."""

    def __init__(self, qapp, provider) -> None:
        super().__init__(qapp, provider)
        self.per_atom: list[PerAtomDataComputed] = []
        self.states: list[QuantumChemistryJobStateChanged] = []
        bus = self.service._event_bus
        bus.subscribe(PerAtomDataComputed, self.per_atom.append)
        bus.subscribe(QuantumChemistryJobStateChanged, self.states.append)

    def run(self, mol, *, calc_type="fukui", method_basis="HF STO-3G", charge=0, multiplicity=1) -> None:
        finished = len(self.runs)
        self.service.request_calculation(
            mol=mol, molecule_uuid="mol-1", calc_type=calc_type, charge=charge, multiplicity=multiplicity,
            method_basis=method_basis, provider_id=self.provider_id,
            input_fingerprint="geom-fp-1", calculation_input=GEOMETRY,
        )
        assert _wait_until(self._qapp, lambda: len(self.runs) > finished)


def test_a_fukui_run_publishes_its_four_datasets_stamped_with_the_geometry_it_ran_on(qapp):
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    assert [event.dataset.property_id for event in landed.per_atom] == IDS
    for event in landed.per_atom:
        # The atom indices mean nothing without the structure they index; the Atom Inspector compares this
        # with the conformer it shows before it lays the values over its atoms.
        assert event.input_fingerprint == "geom-fp-1"
        assert event.calculation_input == GEOMETRY
        assert isinstance(event.dataset, PerAtomDataset)
        assert event.dataset.molecule_uuid == "mol-1"
        assert sorted(event.dataset.values) == [0, 1, 2]


def test_the_datasets_carry_the_job_they_came_from(qapp):
    """Method, basis, charge, multiplicity and the run id, merged beside the provider's own working
    (scheme, vertical, ORCA version, the caveat), so a stored dataset can say what made it however the
    panel's controls have moved since."""
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water(), method_basis="HF STO-3G", charge=0, multiplicity=1)

    for event in landed.per_atom:
        parameters = event.dataset.provenance.parameters
        assert parameters[RUN_CALC_TYPE] == "fukui"
        assert parameters[RUN_METHOD_BASIS] == "HF STO-3G"
        assert (parameters[RUN_CHARGE], parameters[RUN_MULTIPLICITY]) == (0, 1)
        assert parameters[RUN_ID] == landed.runs[0].run_id and parameters[RUN_ID]
        # and the provider's own keys survive the merge
        assert parameters["charge_scheme"] == "hirshfeld" and parameters["states"] == "vertical"
        assert parameters["orca_version"] == "6.1.1"
        assert "ABOVE" in parameters["caveat"]


def test_each_dataset_is_filed_in_the_result_store_under_its_own_id(qapp):
    """Without this the numbers showed live and were gone the moment the molecule was reselected or the
    project reopened (the reason `_record_descriptors` exists)."""
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    filed = {s.identity.result_id: s for s in landed.recorded}
    assert set(IDS) <= set(filed)
    assert "descriptor:orca:orca.scf_energy" in filed
    for property_id in IDS:
        identity = filed[property_id].identity
        assert identity.molecule_uuid == "mol-1"
        assert identity.calculation_input == GEOMETRY
        assert identity.input_fingerprint == "geom-fp-1"
        assert identity.producer == "orca"


def test_the_event_the_store_and_the_run_hold_the_same_datasets(qapp):
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    from_store = {s.identity.result_id: s.result for s in landed.recorded if s.identity.result_id in IDS}
    from_event = {e.dataset.property_id: e.dataset for e in landed.per_atom}
    from_run = {d.property_id: d for d in landed.runs[0].results["per_atom"]}
    assert set(from_store) == set(from_event) == set(from_run) == set(IDS)
    for property_id in IDS:
        assert from_store[property_id] == from_event[property_id] == from_run[property_id]


def test_the_run_keeps_the_datasets_and_says_they_are_available(qapp):
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    run = landed.runs[0]
    assert run.status is RunStatus.COMPLETED
    assert run.output_status["per_atom"] is OutputStatus.AVAILABLE
    assert [d.property_id for d in run.results["per_atom"]] == IDS
    # the descriptors are still there beside them
    assert run.output_status["descriptors"] is OutputStatus.AVAILABLE
    assert run.results["descriptors"][0].descriptor_id == "orca.scf_energy"


def test_a_saved_run_comes_back_with_its_datasets(qapp):
    """A project file keeps the run's results through `result_codec`; a dataset that did not survive the round
    trip would leave a reopened project with a Fukui run and no numbers."""
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    run = landed.runs[0]
    restored = QuantumChemistryRun.from_dict(json.loads(json.dumps(run.to_dict())))
    assert restored is not None
    assert [d.property_id for d in restored.results["per_atom"]] == IDS
    for original, back in zip(run.results["per_atom"], restored.results["per_atom"]):
        assert back.values == pytest.approx(original.values)
        assert back.name == original.name
        assert back.provenance.parameters[RUN_ID] == run.run_id
    assert restored.output_status["per_atom"] is OutputStatus.AVAILABLE


def test_a_model_reading_the_stored_dataset_is_told_the_anion_is_unbound(qapp):
    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    stored = next(s for s in landed.recorded if s.identity.result_id == "orca.fukui_plus")
    envelope = _read(stored)
    assert envelope["kind"] == "per_atom"
    assert envelope["parameters"] == {
        "calc_type": "fukui", "method_basis": "HF STO-3G", "charge": 0, "multiplicity": 1,
    }
    assert any("ABOVE" in caveat and "unbound" in caveat for caveat in envelope["caveats"])


def test_a_model_reading_the_stored_dataset_is_told_it_is_not_validated(qapp):
    """The sentence rides the same provenance caveat as the unbound warning, so it reaches the assistant without a path of its own."""
    from openchem.chem.fukui import NOT_VALIDATED_SENTENCE

    landed = _Landed(qapp, _Transcript(TRANSCRIPT))
    landed.run(_water())

    for stored in (s for s in landed.recorded if s.identity.result_id.startswith("orca.fukui_")):
        envelope = _read(stored)
        assert any(NOT_VALIDATED_SENTENCE in caveat for caveat in envelope["caveats"]), stored.identity.result_id


# --- what does NOT change ---------------------------------------------------------------------------------------------


def test_a_calculation_with_no_per_atom_output_adds_no_key_to_its_run(qapp):
    """The default hook returns nothing. Recording a `NOT_PRODUCED` entry for every such run would change the
    saved record of every ORCA run there already is."""
    landed = _Landed(qapp, FakeQuantumEngineProvider(stdout_text="hello"))
    landed.run(_water(), calc_type="sp")

    run = landed.runs[0]
    assert "per_atom" not in run.output_status and "per_atom" not in run.results
    assert landed.per_atom == []
    assert {s.identity.result_id for s in landed.recorded} == {"descriptor:fake:fake.scf_energy"}


# --- failures ---------------------------------------------------------------------------------------------------------


def test_a_fukui_job_whose_tables_will_not_read_fails_the_run_and_publishes_nothing(qapp):
    """Two states of three: the anion's job died. The run is FAILED with ORCA's reason, no per-atom event goes
    out and nothing is filed, because a difference of the two that did finish would be a number for another
    quantity."""
    truncated = TRANSCRIPT.rsplit("FINAL SINGLE POINT ENERGY", 1)[0].rsplit("Total Charge", 1)[0]
    landed = _Landed(qapp, _Transcript(truncated))
    landed.run(_water())

    run = landed.runs[0]
    assert run.status is RunStatus.FAILED
    assert any("N+1 state of this Fukui calculation did not finish" in warning for warning in run.warnings)
    assert landed.per_atom == []
    assert not [s for s in landed.recorded if s.identity.result_id in IDS]
    assert landed.states[-1].state is CacheState.FAILED


class _RaisingPerAtom(FakeQuantumEngineProvider):
    def parse_per_atom_output(self, output_text, mol, molecule_uuid, calc_type):
        raise ValueError("fake per-atom parse failure")


def test_a_per_atom_parser_that_raises_costs_a_warning_not_the_run(qapp):
    """The enhancement contract the spectrum hooks keep: the descriptors the job did produce are still there."""
    landed = _Landed(qapp, _RaisingPerAtom(stdout_text="ok"))
    landed.run(_water(), calc_type="sp")

    run = landed.runs[0]
    assert run.status is RunStatus.COMPLETED_WITH_WARNINGS
    assert run.output_status["per_atom"] is OutputStatus.FAILED
    assert any("Per-atom output could not be parsed" in warning for warning in run.warnings)
    assert run.output_status["descriptors"] is OutputStatus.AVAILABLE
    assert landed.per_atom == []


# --- the open-shell refusal, through the real service ----------------------------------------------------------------


@pytest.mark.parametrize("multiplicity", [2, 3])
def test_an_open_shell_request_is_refused_before_any_job_starts(qapp, multiplicity):
    service, bus = _make_service(OrcaQuantumEngineProvider())
    states: list[QuantumChemistryJobStateChanged] = []
    runs: list = []
    bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    bus.subscribe(QuantumChemistryRunCompleted, lambda e: runs.append(e.run))

    service.request_calculation(
        mol=_water(), molecule_uuid="mol-1", calc_type="fukui", charge=0, multiplicity=multiplicity,
        method_basis="B3LYP def2-SVP", provider_id="orca", input_fingerprint="geom-fp-1", calculation_input=GEOMETRY,
    )

    assert states[-1].state is CacheState.FAILED
    assert "closed-shell" in states[-1].message and "Failed to build input" in states[-1].message
    assert runs == []
    assert not service._active_jobs
