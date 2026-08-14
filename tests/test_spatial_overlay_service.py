"""The overlay's async contract: latest wins, and nothing stale is drawn.

The producers cannot be interrupted -- they are plain functions with no
progress handle -- so correctness here is entirely about what is ACCEPTED
on arrival, not about stopping work. These guards therefore drive the
token machinery directly rather than through a viewer, where a real
QThreadPool's timing would decide what got tested.
"""

from __future__ import annotations

import json

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.calculation_input import INPUT_PREFIX
from openchem.chem.dipole import compute_dipole_moment
from openchem.chem.steric import compute_steric_analysis
from openchem.domain.common import Provenance
from openchem.domain.report import ReportResult
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.spatial_overlay_service import (
    SpatialOverlayService,
    resolvable_annotations,
)

PARAMETERS_KEY = f"{INPUT_PREFIX}parameters"


class _RecordingPool:
    """Stands in for QThreadPool so a test decides when work 'runs'."""

    def __init__(self) -> None:
        self.started: list = []

    def start(self, runnable) -> None:
        self.started.append(runnable)


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    def publish(self, event) -> None:
        self.published.append(event)


def _registry() -> CalculatorRegistry:
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        registry.register(definition)
    return registry


def _report(report_id: str, spatial, parameters: dict | None = None) -> ReportResult:
    recorded = {} if parameters is None else {PARAMETERS_KEY: parameters}
    return ReportResult(
        report_id=report_id,
        name=report_id,
        molecule_uuid="u",
        spatial=spatial,
        provenance=Provenance(created_by="core", method="test", parameters=recorded),
    )


def _molecule(smiles: str = "CO") -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = 4
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _service(pool=None) -> tuple[SpatialOverlayService, _Bus, _RecordingPool]:
    bus, recording = _Bus(), pool or _RecordingPool()
    return SpatialOverlayService(bus, _registry(), pool=recording), bus, recording


def _request(service, cell=0, conformer=0, molblock="", reports=None) -> int:
    return service.request(
        cell_index=cell,
        molecule_uuid="u",
        structure_key="key-1",
        conformer_index=conformer,
        molblock=molblock,
        reports=reports if reports is not None else [],
    )


# --- what may be recomputed -------------------------------------------------


def test_only_results_that_actually_carry_geometry_are_recomputed():
    """A molecule whose results are all scalar starts no work at all --
    conformer stepping must not become a tax on everybody."""
    arrow = compute_dipole_moment(_molecule(), "u").spatial
    recomputable, skipped = resolvable_annotations(
        [
            _report("topology_analysis", (), {}),
            _report("dipole_moment", arrow, {"decimals": 4}),
        ],
        _registry(),
    )
    assert [item.calculator_id for item in recomputable] == ["dipole_moment"]
    assert skipped == []


def test_an_unresolvable_origin_is_skipped_with_a_reason():
    """Never inferred, never approximated: a calculator that cannot be
    resolved produces a diagnostic, not a guess."""
    arrow = compute_dipole_moment(_molecule(), "u").spatial
    recomputable, skipped = resolvable_annotations(
        [_report("no_such_calculator", arrow, {})], _registry()
    )
    assert recomputable == []
    assert "not in the calculator registry" in skipped[0]


def test_a_result_with_no_recorded_parameters_is_refused_not_defaulted():
    """The whole reason parameters are recorded. Replaying at today's
    defaults would be a different calculation wearing the original's
    label, so the honest answer is to draw nothing and say why."""
    arrow = compute_dipole_moment(_molecule(), "u").spatial
    recomputable, skipped = resolvable_annotations(
        [_report("dipole_moment", arrow, parameters=None)], _registry()
    )
    assert recomputable == []
    assert "no recorded parameters" in skipped[0]


def test_the_recorded_parameters_are_what_get_replayed():
    arrow = compute_dipole_moment(_molecule(), "u").spatial
    recomputable, _ = resolvable_annotations(
        [_report("dipole_moment", arrow, {"decimals": 2})], _registry()
    )
    assert recomputable[0].parameters == {"decimals": 2}
    # And they survive the trip a saved project would make.
    assert json.loads(json.dumps(recomputable[0].parameters)) == {"decimals": 2}


# --- latest-wins ------------------------------------------------------------


def test_a_second_request_while_one_runs_does_not_start_a_second_job():
    service, _bus, pool = _service()
    _request(service, conformer=0)
    assert len(pool.started) == 1
    _request(service, conformer=1)
    assert len(pool.started) == 1, "a request made while one was running started a second job"


def test_the_pending_request_is_replaced_not_queued():
    """A running -> B pending -> C requested must run C and DISCARD B,
    not run both. Asserting only that some stale result is rejected would
    pass against a queue that eventually drains."""
    service, _bus, pool = _service()
    token_a = _request(service, conformer=0)
    _request(service, conformer=1)  # B, pending
    token_c = _request(service, conformer=2)  # C, replaces B

    assert service.requests_superseded == 1
    service.finished(0, token_a)
    assert len(pool.started) == 2, "the pending request did not start when the running one ended"
    started_tokens = [task._token for task in pool.started]
    assert started_tokens[1] == token_c, "B ran instead of C, so the collapse kept the wrong one"
    assert service.jobs_started == 2, "a third job accumulated"


def test_only_the_newest_token_is_accepted():
    service, _bus, _pool = _service()
    stale = _request(service, conformer=0)
    fresh = _request(service, conformer=1)
    assert not service.accepts(0, stale)
    assert service.accepts(0, fresh)


# --- lifecycle and isolation ------------------------------------------------


def test_switching_the_overlay_off_rejects_a_result_still_in_flight():
    service, _bus, _pool = _service()
    token = _request(service, conformer=0)
    assert service.accepts(0, token)
    service.invalidate(0)
    assert not service.accepts(0, token), "a result arriving after the overlay was switched off"


def test_a_result_for_the_previous_molecule_can_never_reach_the_new_one():
    """The most obvious lifecycle hole, closed explicitly: molecule A's
    answer must not mutate molecule B's viewer."""
    service, _bus, _pool = _service()
    token_a = service.request(
        cell_index=0,
        molecule_uuid="molecule-a",
        structure_key="key-a",
        conformer_index=0,
        molblock="",
        reports=[],
    )
    service.invalidate_all()  # the molecule changed
    service.request(
        cell_index=0,
        molecule_uuid="molecule-b",
        structure_key="key-b",
        conformer_index=0,
        molblock="",
        reports=[],
    )
    assert not service.accepts(0, token_a)


def test_one_cell_never_invalidates_another():
    """Gallery cells own their own tokens. A shared counter would make
    updating cell 2 silently discard cell 1's perfectly valid result."""
    service, _bus, _pool = _service()
    token_cell_1 = _request(service, cell=1, conformer=0)
    _request(service, cell=2, conformer=0)
    _request(service, cell=2, conformer=1)
    assert service.accepts(1, token_cell_1), "updating cell 2 invalidated cell 1"


def test_invalidating_one_cell_leaves_the_others_alone():
    service, _bus, _pool = _service()
    token_cell_1 = _request(service, cell=1)
    token_cell_2 = _request(service, cell=2)
    service.invalidate(2)
    assert service.accepts(1, token_cell_1)
    assert not service.accepts(2, token_cell_2)


# --- the payload ------------------------------------------------------------


def _run_one(reports, molblock) -> object:
    service, bus, pool = _service()
    _request(service, molblock=molblock, reports=reports)
    pool.started[0].run()
    return bus.published[0]


def test_one_job_returns_every_annotation_as_one_payload():
    """Atomic: independent jobs would let a slow cone land on a fast
    dipole and show a half-updated overlay."""
    mol = _molecule("CO")
    molblock = Chem.MolToMolBlock(mol)
    reports = [
        _report("dipole_moment", compute_dipole_moment(mol, "u").spatial, {}),
        _report("geometry_analysis", ("placeholder",), {}),
    ]
    # geometry_analysis really produces axes for this molecule; the
    # placeholder above only has to be non-empty to mark it as spatial.
    event = _run_one(reports, molblock)
    kinds = {type(annotation).__name__ for annotation in event.annotations}
    assert kinds == {"ArrowAnnotation", "AxesAnnotation"}, kinds
    assert event.cell_index == 0 and event.conformer_index == 0


def test_one_calculator_failing_does_not_take_the_others_with_it():
    """A strange cone must not make a valid dipole disappear -- and the
    failure is reported rather than silently absent."""
    mol = _molecule("CO")  # methanol: no donor, so steric raises
    reports = [
        _report("dipole_moment", compute_dipole_moment(mol, "u").spatial, {}),
        _report("steric_analysis", ("placeholder",), {}),
    ]
    event = _run_one(reports, Chem.MolToMolBlock(mol))
    assert [type(a).__name__ for a in event.annotations] == ["ArrowAnnotation"]
    assert any("steric_analysis" in reason for reason in event.diagnostics)


def test_an_unparseable_conformer_publishes_a_reason_rather_than_nothing():
    """A cell that never hears back waits forever; every job publishes."""
    event = _run_one([_report("dipole_moment", ("placeholder",), {})], "not a molblock")
    assert event.annotations == ()
    assert any("could not be parsed" in reason for reason in event.diagnostics)


def test_the_payload_is_computed_for_the_conformer_it_was_asked_about():
    """The point of the whole service: the annotation describes the
    molblock handed in, not some canonical geometry elsewhere."""
    mol = _molecule("CO")
    molblock = Chem.MolToMolBlock(mol)
    event = _run_one([_report("dipole_moment", compute_dipole_moment(mol, "u").spatial, {})], molblock)
    direct = compute_dipole_moment(Chem.MolFromMolBlock(molblock, removeHs=False), "u").spatial[0]
    assert event.annotations[0].vector == pytest.approx(direct.vector)
    assert event.annotations[0].anchor == pytest.approx(direct.anchor)
