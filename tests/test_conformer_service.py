from __future__ import annotations

import time

from PySide6.QtCore import QThreadPool

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.plugins.interfaces import ConformerProvider
from openchem.services.conformer_service import ConformerService
from openchem.services.job_manager import JobManager


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def _wait_until(qapp, predicate, timeout_seconds: float = 10) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class _SlowConformerProvider(ConformerProvider):
    """Sleeps between conformers -- gives a test enough real wall-clock
    time to call job_manager.cancel() while generation is genuinely still
    in progress, rather than racing a sub-millisecond real RDKit embed."""

    provider_id = "slow"

    def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
        results = []
        for i in range(num_conformers):
            time.sleep(0.05)
            if on_progress is not None:
                should_continue = on_progress(i + 1, num_conformers)
                if should_continue is False:
                    break
        return results


def test_conformer_job_lifecycle_reaches_completed(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))

    ready_payload = {}
    bus.subscribe(ConformersReady, lambda e: ready_payload.setdefault("conformers", e.conformers))

    service.request_conformers(model, num_conformers=3, optimize=True)
    _drain(qapp)

    assert CacheState.QUEUED in states
    assert CacheState.RUNNING in states
    assert states[-1] == CacheState.COMPLETED

    conformers = ready_payload["conformers"]
    # NOT `== 3`. Duplicate embeddings are pruned, so the count returned is
    # how many DISTINCT shapes the molecule has, capped by how many were
    # asked for. Ethanol has two (the O-H rotamers), so pinning this to the
    # requested number is pinning the bug that made a rigid molecule report
    # ten identical conformers. The exact figure lives in
    # tests/test_conformer_dedup.py; what matters here is the contract.
    assert 1 <= len(conformers) <= 3
    parameters = conformers[0].provenance.parameters
    assert parameters["conformers_embedded"] == 3
    assert parameters["conformers_distinct"] == len(conformers)
    assert all(c.energy is not None for c in conformers)
    assert all(c.molblock for c in conformers)

    # The service must not have mutated the model directly.
    assert model.conformers == []


def test_conformer_job_failure_when_no_structure(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)
    model = MoleculeModel()  # no molblock

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))

    service.request_conformers(model, num_conformers=2, optimize=False)
    _drain(qapp)

    assert states[-1] == CacheState.FAILED


def test_conformer_request_rejected_while_one_already_running(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    job_manager = JobManager()
    service = ConformerService(bus, engine, job_manager=job_manager)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    # Simulate a job already in flight for this molecule without actually
    # scheduling one -- exercises the guard deterministically, no QRunnable
    # timing race needed.
    job_manager.try_start("conformer", model.uuid)

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))

    service.request_conformers(model, num_conformers=3, optimize=True)

    assert states == [CacheState.FAILED]


def test_conformer_results_carry_provenance_and_round_trip(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    ready_payload = {}
    bus.subscribe(ConformersReady, lambda e: ready_payload.setdefault("conformers", e.conformers))

    service.request_conformers(model, num_conformers=2, optimize=True)
    _drain(qapp)

    conformers = ready_payload["conformers"]
    assert conformers
    for conformer in conformers:
        assert conformer.provenance is not None
        assert conformer.provenance.created_by == "core"
        assert conformer.provenance.method == "rdkit"
        # The request is recorded alongside what actually came back, so a
        # result reading "1 conformer" can be told apart from "1 was asked
        # for" -- 1 distinct out of 12 embedded is a statement about the
        # molecule being rigid, and that is worth persisting.
        assert conformer.provenance.parameters["num_conformers"] == 2
        assert conformer.provenance.parameters["optimize"] is True
        assert conformer.provenance.parameters["conformers_embedded"] == 2
        assert conformer.provenance.parameters["conformers_distinct"] == len(conformers)

        round_tripped = type(conformer).from_dict(conformer.to_dict())
        assert round_tripped.provenance == conformer.provenance


def test_cancel_via_job_manager_stops_generation(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    provider = _SlowConformerProvider()
    job_manager = JobManager()
    service = ConformerService(
        bus, engine, providers={provider.provider_id: provider}, job_manager=job_manager
    )
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))
    ready_events = []
    bus.subscribe(ConformersReady, lambda e: ready_events.append(e))

    service.request_conformers(model, num_conformers=100, optimize=False, provider_id="slow")
    assert _wait_until(qapp, lambda: CacheState.RUNNING in states)

    cancelled = job_manager.cancel("conformer", model.uuid)
    assert cancelled is True

    assert _wait_until(qapp, lambda: states and states[-1] == CacheState.FAILED)
    _drain(qapp)

    assert ready_events == []  # partial results must not be reported as a success
    assert not job_manager.is_active("conformer", model.uuid)


# --- truncation: the stage that was happening and was not being recorded -----


#: Two rotatable O-H plus the C-C torsion, so 30 embeddings find far more
#: distinct shapes than a small cap will keep -- and it is fast. The
#: molecule flexible enough to be truncated is the ordinary case, not the
#: exotic one: the shipped dialog defaults to keeping 10, and the
#: de-duplication benchmark finds ~12.8 for a drug-like molecule.
_FLEXIBLE = "OCCO"
_EMBEDDINGS = 30

#: Higher than any distinct count this fixture reaches, so the run is
#: capped by the molecule rather than by the number -- that is what makes
#: it the "full ordering" the truncated arm is compared against.
_NO_CAP = 50


def _generate_with_cap(qapp, keep: int, embeddings: int = _EMBEDDINGS):
    """One seeded run, returning `(conformers, provenance parameters)`.

    SEEDED, so two runs differ only by the cap. Without that this compares
    two random searches and any difference in the retained set reads as
    truncation behaviour.
    """
    from openchem.chem.conformer_providers import RDKitConformerProvider

    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(
        bus, engine, providers={"rdkit": RDKitConformerProvider(random_seed=0)}
    )
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, _FLEXIBLE)

    payload = {}
    bus.subscribe(ConformersReady, lambda e: payload.setdefault("conformers", e.conformers))
    service.request_conformers(
        model, num_conformers=keep, optimize=True, num_embeddings=embeddings
    )
    _drain(qapp)
    conformers = payload["conformers"]
    return conformers, conformers[0].provenance.parameters


def test_truncation_slices_the_production_result_rather_than_regenerating(qapp):
    """The cap keeps the lowest-energy members of the SAME run.

    This is the claim the whole diagnostic rests on -- that `returned` is
    production's own output sliced, not a differently-configured search --
    so it is asserted directly: generate with a cap above the distinct
    count to capture the full ordering, then again with a smaller cap, and
    require the second to be exactly the first N of the first.

    A weaker test that only checked counts would pass against an
    implementation that re-ran generation under the cap and happened to
    return the right number of different structures.
    """
    full, full_parameters = _generate_with_cap(qapp, keep=_NO_CAP)
    distinct = full_parameters["conformers_distinct"]
    # THE CAP IS DERIVED from what production actually found, not written
    # in. A hardcoded number silently stops truncating the day the search
    # or the molecule changes, and the test goes on passing while asserting
    # nothing about truncation at all.
    assert distinct > 1, f"fixture found {distinct} distinct shape(s); it cannot show truncation"
    keep = distinct - 1
    assert full_parameters["conformers_returned"] == len(full) == distinct

    capped, capped_parameters = _generate_with_cap(qapp, keep=keep)
    assert capped_parameters["conformers_distinct"] == distinct
    assert capped_parameters["conformers_returned"] == keep
    assert len(capped) == keep
    # Exactly the first `keep` of the full ordering, geometry and energy.
    assert [c.molblock for c in capped] == [c.molblock for c in full[:keep]]
    assert [c.energy for c in capped] == [c.energy for c in full[:keep]]


def test_without_truncation_returned_equals_distinct(qapp):
    """The other side, and it is not redundant.

    An implementation that simply set `conformers_returned = num_conformers`
    passes the interesting case above and fails here. Both sides are needed
    or the field can be wrong in the direction that reads as reassuring.
    """
    conformers, parameters = _generate_with_cap(qapp, keep=_NO_CAP)
    assert parameters["conformers_returned"] == parameters["conformers_distinct"]
    assert parameters["conformers_returned"] == len(conformers)
    assert parameters["conformers_returned"] < parameters["num_conformers"]


def test_the_omitted_conformers_are_ordinary_production_conformers(qapp):
    """What the cap removes is real, which is why it is worth reporting.

    They are not failures, not near-duplicates and not unconverged -- they
    are distinct conformers that production found, ranked below the cut. So
    raising the cap must expose them rather than compute anything new.
    """
    full, full_parameters = _generate_with_cap(qapp, keep=_NO_CAP)
    assert full_parameters["conformers_distinct"] > 1
    capped, _ = _generate_with_cap(qapp, keep=full_parameters["conformers_distinct"] - 1)

    omitted = full[len(capped):]
    assert omitted, "nothing was omitted, so this asserts nothing"
    assert full_parameters["conformers_returned"] == len(capped) + len(omitted)
    for conformer in omitted:
        assert conformer.molblock
        assert conformer.energy is not None       # it converged
        assert conformer.provenance is not None
    # Ranked below the cut, which is what "the N lowest in energy" means.
    assert max(c.energy for c in capped) <= min(c.energy for c in omitted)


def test_a_cap_of_zero_is_refused_by_the_dialog_and_unguarded_in_the_service(qapp):
    """Recorded as it IS, not as it ought to be.

    The spin box floors at 1, so no user can ask for zero conformers. The
    service applies no validation of its own -- `results[:0]` is empty and
    the job completes -- and adding some would be a behaviour change no
    measurement has asked for. Written down so the boundary is a known
    state rather than an assumption, and so a future validator has a test
    to update instead of a surprise to discover.
    """
    from openchem.ui.dialogs.conformer_options_dialog import ConformerOptionsDialog

    from openchem.chem.conformer_providers import RDKitConformerProvider

    dialog = ConformerOptionsDialog()
    try:
        dialog._keep_spin.setValue(0)
        assert dialog.conformers_to_keep() == 1, "the dialog must not permit a cap of zero"
    finally:
        dialog.setParent(None)
        dialog.deleteLater()

    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(
        bus, engine, providers={"rdkit": RDKitConformerProvider(random_seed=0)}
    )
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, _FLEXIBLE)

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))
    payload = {}
    bus.subscribe(ConformersReady, lambda e: payload.setdefault("conformers", e.conformers))
    service.request_conformers(model, num_conformers=0, optimize=True, num_embeddings=6)
    _drain(qapp)

    # No validation: the slice is empty and the job reports success.
    assert payload["conformers"] == []
    assert states[-1] == CacheState.COMPLETED
    # And `conformers_returned` is unreachable in this case, because
    # provenance is carried BY the conformers -- with none returned there
    # is nothing to hang it on. That is a real limit of storing stage
    # counts on the result rather than on the job, and it is only ever hit
    # where the result is empty.
