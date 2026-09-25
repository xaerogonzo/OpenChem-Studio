"""Finish now: end a conformer search where it is and KEEP what it found, and a readout that says how the search is going.

A cancel discards the run; this ends it and the shapes so far are the result. It was asked for because a flexible molecule can
sample for minutes and the only way out was to throw all of it away. The readout is the other half: "Sampling shapes 450/1000"
alone said nothing about whether waiting was buying anything.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.conformer_providers import (
    STOP_CANCELLED,
    STOP_USER_FINISHED,
    GenerationOptions,
    SearchArchive,
    SearchProgress,
    search_conformers,
)
from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged, ConformersReady
from openchem.plugins.interfaces import ConformerBatch, ConformerProvider
from openchem.services.conformer_service import ConformerService, format_search_progress
from openchem.services.job_manager import JobManager
from openchem.services.progress import ProgressHandle


def _geometries():
    """Four hexane geometries far enough apart (RMSD >= 0.5) that none merges with another."""
    base = Chem.AddHs(Chem.MolFromSmiles("CCCCCC"))
    AllChem.EmbedMolecule(base, AllChem.ETKDGv3())
    AllChem.MMFFOptimizeMolecule(base)
    start = rdMolTransforms.GetDihedralDeg(base.GetConformer(), 0, 1, 2, 3)

    def at(offset):
        m = Chem.Mol(base)
        rdMolTransforms.SetDihedralDeg(m.GetConformer(), 0, 1, 2, 3, start + offset)
        return m

    return at(0), at(100), at(250)


class _Scripted(ConformerProvider):
    """One prepared batch per call; `short` makes a call come back with fewer attempts than asked (a provider stopping itself)."""

    provider_id = "scripted"

    def __init__(self, batches, short_on=()):
        self._batches = list(batches)
        self._short_on = set(short_on)
        self.calls = 0

    def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
        return []

    def generate_conformer_batch(self, mol, num_conformers, optimize, on_progress=None, options=None):
        results = self._batches[self.calls] if self.calls < len(self._batches) else []
        attempted = num_conformers - 1 if self.calls in self._short_on else num_conformers
        self.calls += 1
        return ConformerBatch(results=list(results), attempted=attempted, embedded=len(results), converged=len(results))


# --- what a batch added ------------------------------------------------------------------------------------------------


def test_a_new_shape_above_the_kept_set_does_not_count_as_entering_it():
    """Keeping 1: a new shape HIGHER in energy than the lowest cannot change what the run hands back."""
    a, b, d = _geometries()
    archive = SearchArchive()

    first = archive.add_batch_detailed([(a, 3.0)], keep=1)
    higher = archive.add_batch_detailed([(b, 3.4)], keep=1)
    lower = archive.add_batch_detailed([(d, 2.0)], keep=1)

    assert (first.unmatched, first.entered_keep_set) == (1, 1), "an archive with fewer than `keep` counts everything"
    assert (higher.unmatched, higher.entered_keep_set) == (1, 0), "a new but higher-energy shape is not in the lowest 1"
    assert (lower.unmatched, lower.entered_keep_set) == (1, 1)


def test_the_bar_is_the_archive_BEFORE_the_batch():
    """One batch must not raise its own bar: two new shapes in the same batch both beat what was there."""
    a, b, d = _geometries()
    archive = SearchArchive()
    archive.add_batch_detailed([(a, 3.0)], keep=1)

    report = archive.add_batch_detailed([(b, 2.5), (d, 2.0)], keep=1)

    assert report.entered_keep_set == 2


def test_add_batch_still_returns_the_unmatched_count():
    """`add_batch` is the plateau signal the search and its older tests read; it must not change meaning."""
    a, b, _d = _geometries()
    archive = SearchArchive()
    assert archive.add_batch([(a, 3.0), (b, 3.4)]) == 2


# --- the search reports its state ---------------------------------------------------------------------------------------


def test_the_search_reports_shapes_and_how_long_the_kept_set_has_been_unchanged():
    a, b, d = _geometries()
    provider = _Scripted([[(a, 3.0)], [(b, 3.4)], [(d, 2.0)]])
    options = GenerationOptions(embedding_batch_size=1, max_embeddings=3, plateau_batches_required=99)
    states: list[SearchProgress] = []

    search_conformers(provider, None, True, options, keep=1, on_state=states.append)

    assert [(s.attempted, s.shapes, s.unchanged_for) for s in states] == [(1, 1, 0), (2, 2, 1), (3, 3, 0)]
    assert all(s.keep == 1 and s.ceiling == 3 for s in states)


def test_nothing_about_a_run_changes_unless_a_finish_is_asked_for():
    """The three new parameters are inert by default: same batches, same stop, same pool."""
    a, b, d = _geometries()
    batches = [[(a, 3.0)], [(b, 3.4)], [(d, 2.0)]]
    options = GenerationOptions(embedding_batch_size=1, max_embeddings=3, plateau_batches_required=99)

    plain = search_conformers(_Scripted(batches), None, True, options)
    instrumented = search_conformers(
        _Scripted(batches), None, True, options, keep=1, on_state=lambda _s: None, finish_requested=lambda: False
    )

    assert (plain.batches, plain.attempted, plain.stop_reason, len(plain.pool)) == (
        instrumented.batches, instrumented.attempted, instrumented.stop_reason, len(instrumented.pool),
    )


# --- finishing ------------------------------------------------------------------------------------------------------


def test_a_finish_after_a_batch_keeps_that_batch():
    a, b, _d = _geometries()
    provider = _Scripted([[(a, 3.0)], [(b, 3.4)]])
    options = GenerationOptions(embedding_batch_size=1, max_embeddings=10, plateau_batches_required=99)

    outcome = search_conformers(
        provider, None, True, options, on_progress=lambda _d, _t: False, finish_requested=lambda: True
    )

    assert outcome.stop_reason == STOP_USER_FINISHED
    assert outcome.batches == 1 and len(outcome.pool) == 1, "the batch that was running is part of the result"


def test_a_batch_cut_short_by_the_request_is_a_finish_not_a_cancel():
    """The provider stops mid-batch when `on_progress` says stop, so the batch comes back short. That is BECAUSE of the
    request and its results are a result."""
    a, _b, _d = _geometries()
    provider = _Scripted([[(a, 3.0)]], short_on={0})
    options = GenerationOptions(embedding_batch_size=2, max_embeddings=10, plateau_batches_required=99)

    outcome = search_conformers(provider, None, True, options, finish_requested=lambda: True)

    assert outcome.stop_reason == STOP_USER_FINISHED
    assert len(outcome.pool) == 1


def test_without_a_finish_a_stop_is_still_a_cancel():
    a, _b, _d = _geometries()
    options = GenerationOptions(embedding_batch_size=1, max_embeddings=10, plateau_batches_required=99)

    for finish in (None, lambda: False):
        outcome = search_conformers(
            _Scripted([[(a, 3.0)]]), None, True, options, on_progress=lambda _d, _t: False, finish_requested=finish
        )
        assert outcome.stop_reason == STOP_CANCELLED


# --- the readout ---------------------------------------------------------------------------------------------------------


def test_the_readout_before_the_first_batch_is_just_the_count():
    assert format_search_progress(30, 1000, None) == "Sampling shapes 30/1000"


def test_the_readout_says_found_and_whether_the_lowest_are_still_changing():
    steady = SearchProgress(attempted=450, ceiling=1000, shapes=31, keep=20, unchanged_for=150)
    moving = SearchProgress(attempted=450, ceiling=1000, shapes=31, keep=20, unchanged_for=0)

    assert format_search_progress(460, 1000, steady) == "Sampling shapes 460/1000 - 31 found so far - lowest 20 unchanged for 150"
    assert format_search_progress(460, 1000, moving) == "Sampling shapes 460/1000 - 31 found so far - lowest 20 still changing"


def test_no_claim_about_the_lowest_set_before_it_is_full():
    """With fewer shapes than the run keeps, "unchanged" would describe a set that is still filling."""
    filling = SearchProgress(attempted=100, ceiling=1000, shapes=8, keep=20, unchanged_for=50)

    text = format_search_progress(110, 1000, filling)

    assert text == "Sampling shapes 110/1000 - 8 found so far"
    assert "conformers" not in text


# --- through the real service ----------------------------------------------------------------------------------------------


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def _wait_until(qapp, predicate, timeout_seconds: float = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_finish_now_keeps_the_shapes_found_and_records_that_it_was_asked(qapp):
    """The real provider, a real job: press Finish once embeddings are flowing, and the run COMPLETES with what it had."""
    from openchem.chem.conformer_providers import RDKitConformerProvider

    bus = EventBus()
    engine = ChemistryEngine()
    jobs = JobManager()
    service = ConformerService(bus, engine, providers={"rdkit": RDKitConformerProvider(random_seed=0)}, job_manager=jobs)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCCCCCCCCC")  # decane: flexible, so the 2000-embedding ceiling is far away

    states, messages, ready = [], [], []
    bus.subscribe(ConformerJobStateChanged, lambda e: (states.append(e.state), messages.append(e.message)))
    bus.subscribe(ConformersReady, ready.append)

    service.request_conformers(model, num_conformers=5, optimize=True, num_embeddings=2000)
    assert _wait_until(qapp, lambda: any("Sampling shapes" in (m or "") and " 10/" in m for m in messages))

    assert service.finish_early(model) is True
    assert _wait_until(qapp, lambda: states and states[-1] in (CacheState.COMPLETED, CacheState.FAILED))
    _drain(qapp)

    assert states[-1] == CacheState.COMPLETED
    assert len(ready) == 1 and ready[0].conformers, "a finish keeps the result; it does not discard it"
    parameters = ready[0].conformers[0].provenance.parameters
    assert parameters["stop_reason"] == STOP_USER_FINISHED
    assert parameters["conformers_attempted"] < 2000
    assert "finished early after" in messages[-1]
    assert not jobs.is_active("conformer", model.uuid)


class _Idle(ConformerProvider):
    """Finds nothing, slowly enough for a test to press Finish while it runs."""

    provider_id = "idle"

    def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
        for i in range(num_conformers):
            time.sleep(0.02)
            if on_progress is not None and on_progress(i + 1, num_conformers) is False:
                break
        return []


def test_finish_now_with_nothing_found_publishes_no_empty_result(qapp):
    """An empty set would REPLACE whatever the molecule already had with nothing."""
    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine, providers={"idle": _Idle()}, job_manager=JobManager())
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    states, messages, ready = [], [], []
    bus.subscribe(ConformerJobStateChanged, lambda e: (states.append(e.state), messages.append(e.message)))
    bus.subscribe(ConformersReady, ready.append)

    service.request_conformers(model, num_conformers=100, optimize=False, provider_id="idle")
    assert _wait_until(qapp, lambda: CacheState.RUNNING in states)
    assert service.finish_early(model) is True
    assert _wait_until(qapp, lambda: states and states[-1] == CacheState.FAILED)
    _drain(qapp)

    assert ready == []
    assert messages[-1] == "Stopped before any conformer had been found"


def test_a_cancel_outranks_a_finish():
    """Both asked: the run is discarded, so the search must not report the stop as a finish."""
    from openchem.services.conformer_service import _ConformerGenerationTask

    task = _ConformerGenerationTask.__new__(_ConformerGenerationTask)
    task._progress = ProgressHandle()
    task._progress.finish_early()
    assert task._finish_requested() is True

    task._progress.cancel()
    assert task._finish_requested() is False


def test_finish_early_on_a_molecule_with_no_job_is_a_no_op(qapp):
    service = ConformerService(EventBus(), ChemistryEngine(), job_manager=JobManager())
    assert service.finish_early(MoleculeModel()) is False


@pytest.mark.parametrize("reason", [STOP_USER_FINISHED])
def test_the_details_dialog_has_words_for_a_run_you_ended(qapp, reason):
    from openchem.ui.dialogs.conformer_details_dialog import ConformerDetailsDialog

    note = ConformerDetailsDialog._stop_note({"stop_reason": reason})

    assert note.startswith("Finished early by you")
    assert "Finish now" in note


# --- the experimental kept-set stop rule (Settings > Conformers) ---------------------------------------------------------


def _higher_energy_arrivals():
    """Three batches, each a NEW shape: the first lowest, the next two HIGHER in energy, then nothing."""
    a, b, d = _geometries()
    return [[(a, 3.0)], [(b, 3.4)], [(d, 3.6)], [], [], []]


def _rule_options(rule):
    from openchem.chem.conformer_providers import GenerationOptions

    return GenerationOptions(embedding_batch_size=1, max_embeddings=6, plateau_batches_required=2, stop_rule=rule)


def test_the_kept_set_rule_stops_where_the_default_keeps_going():
    """Shapes that arrive but would not rank among the kept ones are the whole difference between the two rules."""
    from openchem.chem.conformer_providers import (
        STOP_KEPT_SET_STEADY,
        STOP_PLATEAU,
        STOP_RULE_ANY_NEW,
        STOP_RULE_KEPT_SET,
    )

    default = search_conformers(_Scripted(_higher_energy_arrivals()), None, True, _rule_options(STOP_RULE_ANY_NEW), keep=1)
    kept = search_conformers(_Scripted(_higher_energy_arrivals()), None, True, _rule_options(STOP_RULE_KEPT_SET), keep=1)

    assert (default.stop_reason, default.batches) == (STOP_PLATEAU, 5), "each higher-energy shape is still 'something new'"
    assert (kept.stop_reason, kept.batches) == (STOP_KEPT_SET_STEADY, 3)
    assert kept.batches_without_new_candidates == 2
    assert kept.batches <= default.batches


def test_the_kept_set_rule_needs_a_kept_set_to_watch():
    """A caller that gives no `keep` has no set to watch, so the experimental rule is the default one."""
    from openchem.chem.conformer_providers import STOP_PLATEAU, STOP_RULE_KEPT_SET

    outcome = search_conformers(_Scripted(_higher_energy_arrivals()), None, True, _rule_options(STOP_RULE_KEPT_SET), keep=0)

    assert (outcome.stop_reason, outcome.batches) == (STOP_PLATEAU, 5)


def test_a_new_shape_that_would_be_kept_still_keeps_the_kept_set_rule_searching():
    """The rule ignores shapes above the kept set, never one that belongs in it."""
    from openchem.chem.conformer_providers import STOP_RULE_KEPT_SET

    a, b, d = _geometries()
    lower_last = [[(a, 3.0)], [(b, 3.4)], [(d, 2.0)], [], [], []]

    outcome = search_conformers(_Scripted(lower_last), None, True, _rule_options(STOP_RULE_KEPT_SET), keep=1)

    assert outcome.batches == 5, "the batch that found a lower shape reset the quiet count"


def test_the_record_says_which_stop_rule_ran(qapp):
    from openchem.chem.conformer_providers import RDKitConformerProvider, STOP_RULE_KEPT_SET

    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine, providers={"rdkit": RDKitConformerProvider(random_seed=0)})
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "OCCO")
    ready = []
    bus.subscribe(ConformersReady, ready.append)

    service.request_conformers(
        model, num_conformers=5, optimize=True, num_embeddings=30, options=GenerationOptions(stop_rule=STOP_RULE_KEPT_SET)
    )
    _drain(qapp)

    assert ready[0].conformers[0].provenance.parameters["stop_rule"] == STOP_RULE_KEPT_SET


def test_the_default_record_says_the_default_rule(qapp):
    from openchem.chem.conformer_providers import RDKitConformerProvider, STOP_RULE_ANY_NEW

    bus = EventBus()
    engine = ChemistryEngine()
    service = ConformerService(bus, engine, providers={"rdkit": RDKitConformerProvider(random_seed=0)})
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "OCCO")
    ready = []
    bus.subscribe(ConformersReady, ready.append)

    service.request_conformers(model, num_conformers=5, optimize=True, num_embeddings=30)
    _drain(qapp)

    assert ready[0].conformers[0].provenance.parameters["stop_rule"] == STOP_RULE_ANY_NEW


def test_the_details_dialog_says_the_experimental_rule_ended_the_run(qapp):
    from openchem.ui.dialogs.conformer_details_dialog import ConformerDetailsDialog

    note = ConformerDetailsDialog._stop_note({"stop_reason": "kept_set_steady", "batches_without_new_candidates": 2})

    assert note.startswith("Lowest conformers stopped changing (experimental) -- no change in the last 2 batches")
    assert "Settings > Conformers" in note


def test_the_options_dialog_carries_the_stop_rule_it_was_built_with(qapp):
    """The layering rule puts this in the dialog: the viewer widget may not import `chem`, the dialog may."""
    from openchem.chem.conformer_providers import STOP_RULE_ANY_NEW, STOP_RULE_KEPT_SET
    from openchem.ui.dialogs.conformer_options_dialog import ConformerOptionsDialog

    assert ConformerOptionsDialog().options().stop_rule == STOP_RULE_ANY_NEW
    assert ConformerOptionsDialog(early_stop=False).options().stop_rule == STOP_RULE_ANY_NEW
    assert ConformerOptionsDialog(early_stop=True).options().stop_rule == STOP_RULE_KEPT_SET


def test_the_viewer_widget_builds_its_dialog_from_settings(qapp):
    """The REAL dialog, not a fake: what Settings says is what the options carry."""
    from openchem.app.settings import CONFORMER_EARLY_STOP, CONFORMER_MAX_EMBEDDINGS, Settings
    from openchem.chem.conformer_providers import STOP_RULE_KEPT_SET
    from openchem.services.measurement_service import MeasurementService
    from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget
    from tests.test_molecule_viewer3d_widget import FakeViewerBackend

    settings = Settings(EventBus())
    settings.set_preference(CONFORMER_EARLY_STOP, True)
    settings.set_preference(CONFORMER_MAX_EMBEDDINGS, 500)
    engine = ChemistryEngine()
    widget = MoleculeViewer3DWidget(
        ConformerService(EventBus(), engine), MeasurementService(engine), EventBus(),
        backend=FakeViewerBackend(), settings=settings,
    )
    try:
        options = widget.options_dialog().options()
        assert options.stop_rule == STOP_RULE_KEPT_SET
        assert options.max_embeddings == 500
    finally:
        widget.deleteLater()
