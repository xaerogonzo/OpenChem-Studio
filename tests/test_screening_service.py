"""Docking N ligands into one receptor, in order.

The queue is the only genuinely new thing virtual screening adds over
`DockingService`, and it is the part that can wedge: advance on the wrong
event and the screen stops forever on the first ligand Vina refuses. So
these drive a FAKE docking provider through the real `DockingService`,
which exercises the real events and the real single-flight guard while
running no Vina.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.domain.macromolecule import MacromoleculeModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.services.docking_service import DockingService
from openchem.services.job_manager import JobManager
from openchem.services.screening_service import ScreeningEntry, ScreeningProgress, ScreeningService, rank

import conftest


class _FakeVina:
    """Returns a fixed score per ligand, or raises for named ones.

    Ligands are identified by ATOM COUNT, not by name: `dock()` receives a
    bare `Chem.Mol` built by `ChemistryEngine.mol_from_model`, which does
    not carry the model's display name. An earlier version of this fake
    read `_Name` and silently scored every ligand the same, which made the
    ranking test pass on tie order alone.
    """

    provider_id = "vina"
    engine_id = "vina"

    def __init__(self, scores: dict[int, float], failing: set[int] | None = None) -> None:
        self._scores = scores
        self._failing = failing or set()
        self.calls: list[int] = []

    def engine_version(self) -> str:
        return "fake"

    def dock(self, _receptor_text, _receptor_format, ligand_mol, _box, num_poses, _progress, _options):
        atoms = ligand_mol.GetNumAtoms()
        self.calls.append(atoms)
        if atoms in self._failing:
            raise RuntimeError(f"no {atoms}-atom ligands for you")
        score = self._scores[atoms]
        return [
            DockingPoseModel(
                pose_molblock="", binding_affinity_kcal_mol=score + index, rmsd_lb=0.0, rmsd_ub=0.0
            )
            for index in range(min(num_poses, 2))
        ]


@pytest.fixture
def harness(qapp):
    """A real DockingService and ScreeningService over a fake provider."""
    engine = ChemistryEngine()
    event_bus = EventBus()
    job_manager = JobManager()
    provider = _FakeVina(_SCORES)
    docking = DockingService(event_bus, _settings(), providers={"vina": provider}, job_manager=job_manager)
    screening = ScreeningService(event_bus, docking, engine, job_manager=job_manager)
    events: list[ScreeningProgress] = []
    event_bus.subscribe(ScreeningProgress, events.append)
    return engine, event_bus, provider, screening, events


def _settings():
    from openchem.app.settings import Settings

    return Settings(EventBus())


def _ligands(engine, names_and_smiles):
    molecules = []
    for name, smiles in names_and_smiles:
        molecule = MoleculeModel(display_name=name)
        engine.set_structure_from_smiles(molecule, smiles)
        molecules.append(molecule)
    return molecules


#: A single-atom PDB rather than an empty string. `DockingService` runs
#: pose-interaction analysis on the receptor after every job; it catches
#: its own failure, but an unparseable receptor makes it log a traceback
#: per ligand, which buries any real failure in this file.
_RECEPTOR_PDB = (
    "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\nEND\n"
)


def _receptor():
    return MacromoleculeModel(
        display_name="receptor", structure_text=_RECEPTOR_PDB, source_format="pdb"
    )


def _box():
    return DockingBox(center=(0.0, 0.0, 0.0), size=(20.0, 20.0, 20.0))


def _drain(timeout_ms=30000):
    """Let the queue run to completion.

    Each ligand's terminal event has to be delivered on the GUI thread
    before the next is submitted, so this alternates draining the pool with
    draining the event queue rather than waiting once.
    """
    for _ in range(60):
        QThreadPool.globalInstance().waitForDone(timeout_ms)
        QApplication.instance().processEvents()


#: Three ligands with distinct heavy-atom counts, so the fake can tell
#: them apart: aspirin 13, caffeine 14, ethanol 3.
_THREE = [
    ("strong", "CC(=O)Oc1ccccc1C(=O)O"),
    ("middling", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("weak", "CCO"),
]
_SCORES = {13: -11.2, 14: -8.0, 3: -5.5}


def test_ligands_are_docked_one_at_a_time(harness):
    """Submitting all of them at once would start N Vina processes
    simultaneously."""
    engine, _bus, provider, screening, _events = harness
    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
    _drain()
    assert len(provider.calls) == 3


def test_the_best_binder_ranks_first(harness):
    """Vina scores are negative and more negative is better, so the correct
    ranking sorts ASCENDING -- which reads as backwards."""
    engine, _bus, _provider, screening, events = harness
    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
    _drain()
    final = events[-1]
    assert final.state is CacheState.COMPLETED
    assert [entry.display_name for entry in final.entries] == ["strong", "middling", "weak"]
    assert final.entries[0].best_affinity_kcal_mol == pytest.approx(-11.2)


def test_a_ligand_that_fails_keeps_its_row_and_does_not_wedge_the_queue(harness):
    """Advancing only on the result event would leave the screen stopped
    forever on the first refusal."""
    engine, bus, _provider, _screening, events = harness
    failing = _FakeVina(_SCORES, failing={14})  # caffeine
    job_manager = JobManager()
    docking = DockingService(bus, _settings(), providers={"vina": failing}, job_manager=job_manager)
    screening = ScreeningService(bus, docking, engine, job_manager=job_manager)
    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
    _drain()
    final = events[-1]
    assert len(failing.calls) == 3  # it got past the failure
    names = [entry.display_name for entry in final.entries]
    assert names[-1] == "middling"  # failures rank last
    assert final.entries[-1].failed


def test_a_ligand_with_no_structure_is_reported_without_reaching_vina(harness):
    engine, _bus, provider, screening, events = harness
    ligands = _ligands(engine, _THREE)
    ligands.insert(0, MoleculeModel(display_name="not drawn"))
    screening.request_screen(ligands, _receptor(), _box())
    _drain()
    entry = next(e for e in events[-1].entries if e.display_name == "not drawn")
    assert entry.failed and "no structure" in entry.error
    assert "not drawn" not in provider.calls


def test_progress_counts_up_as_ligands_finish(harness):
    engine, _bus, _provider, screening, events = harness
    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
    _drain()
    assert [event.completed for event in events][-1] == 3
    assert events[-1].total == 3


def test_an_empty_ligand_list_is_refused_with_a_reason(harness):
    _engine, _bus, _provider, screening, events = harness
    screening.request_screen([], _receptor(), _box())
    assert "No ligands" in events[-1].error


def test_a_second_screen_is_refused_while_one_runs(harness):
    from openchem.services.screening_service import SCREENING_JOB_KEY, SCREENING_JOB_KIND

    engine, _bus, _provider, screening, events = harness
    screening._job_manager.try_start(SCREENING_JOB_KIND, SCREENING_JOB_KEY)
    try:
        screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
        assert "already in progress" in events[-1].error
    finally:
        screening._job_manager.finish(SCREENING_JOB_KIND, SCREENING_JOB_KEY)


def test_cancelling_stops_submitting_further_ligands(harness):
    engine, _bus, provider, screening, events = harness
    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
    screening.cancel()
    _drain()
    assert len(provider.calls) <= 1
    assert events[-1].state is CacheState.FAILED
    assert "Cancelled" in events[-1].message


def test_a_screen_releases_its_job_when_it_finishes(harness):
    engine, _bus, _provider, screening, _events = harness
    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box())
    _drain()
    assert not screening.is_running()


def test_an_unrelated_docking_does_not_advance_the_screen(harness):
    """`DockingService` is shared -- a user can run a one-off docking from
    the Docking panel mid-screen, and recording it here would skip a
    ligand."""
    engine, bus, _provider, screening, _events = harness
    from openchem.events.events import DockingJobStateChanged

    before = len(screening._entries)
    bus.publish(
        DockingJobStateChanged(
            ligand_molecule_uuid="someone-elses-ligand",
            receptor_macromolecule_uuid="r",
            state=CacheState.COMPLETED,
        )
    )
    QApplication.instance().processEvents()
    assert len(screening._entries) == before


def test_ranking_puts_failures_last_in_attempt_order():
    entries = [
        ScreeningEntry(molecule_uuid="a", display_name="a", error="boom"),
        ScreeningEntry(molecule_uuid="b", display_name="b", best_affinity_kcal_mol=-4.0),
        ScreeningEntry(molecule_uuid="c", display_name="c", error="also boom"),
        ScreeningEntry(molecule_uuid="d", display_name="d", best_affinity_kcal_mol=-9.0),
    ]
    assert [entry.display_name for entry in rank(entries)] == ["d", "b", "a", "c"]


# --- the dialog ---------------------------------------------------------


@pytest.fixture
def widgets():
    """Destroyed deterministically -- see the same fixture in
    `tests/test_batch_panel.py` for why leaving it to the collector caused
    an access violation inside `processEvents`."""

    built = []
    yield built
    for widget in built:
        conftest.dispose(widget)


def _dialog(widgets, harness, project):
    from openchem.ui.dialogs.virtual_screening_dialog import VirtualScreeningDialog

    _engine, bus, _provider, screening, _events = harness
    dialog = VirtualScreeningDialog(screening, bus, project)
    widgets.append(dialog)
    return dialog


def _project(engine, with_receptor=True):
    from openchem.domain.project import ProjectModel

    project = ProjectModel(name="screen")
    project.molecules.extend(_ligands(engine, _THREE))
    if with_receptor:
        project.macromolecules.append(_receptor())
    return project


def test_the_dialog_refuses_to_run_without_a_receptor(harness, widgets):
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine, with_receptor=False))
    assert not dialog._run.isEnabled()
    assert "Receptor Library" in dialog._ligand_note.text()


def test_the_dialog_counts_the_ligands_it_would_dock(harness, widgets):
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))
    assert "3 ligands" in dialog._ligand_note.text()


def test_a_receptor_with_no_placeable_site_is_reported_not_crashed(harness, widgets):
    """The single-atom receptor here names no ligand, so no box can be
    derived. Docking into a box centred on the origin would return poses
    that look like results."""
    engine, _bus, provider, _screening, _events = harness
    dialog = _dialog(widgets, harness, _project(engine))
    dialog._start()
    assert "Could not place a search box" in dialog._status.text()
    assert provider.calls == []


def test_the_ranked_table_leaves_a_failure_unranked(harness, widgets):
    """Numbering a ligand that never produced a score puts it in an
    ordering it is not part of."""
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))
    dialog._render(
        rank(
            [
                ScreeningEntry(molecule_uuid="a", display_name="good", best_affinity_kcal_mol=-9.0),
                ScreeningEntry(molecule_uuid="b", display_name="bad", error="Vina refused it"),
            ]
        )
    )
    assert dialog._results.item(0, 0).text() == "1"
    assert dialog._results.item(1, 0).text() == ""
    assert dialog._results.item(1, 2).text() == "Vina refused it"


# --- replicates, and the ranking they license -------------------------------


def _entry(name, *affinities, uuid=None):
    """A screened ligand whose replicate runs produced `affinities`.

    `best_affinity_kcal_mol` is the MEDIAN of them, because that is what the
    service records: the poses it receives are the median replicate's, so the
    ligand's headline score is the median run's best. Setting it to the
    minimum here would build a fixture the service can never produce.
    """
    from openchem.domain.docking import DockingReplicate

    median = sorted(affinities)[len(affinities) // 2]
    return ScreeningEntry(
        molecule_uuid=uuid or name,
        display_name=name,
        best_affinity_kcal_mol=median,
        pose_count=9,
        replicates=tuple(
            DockingReplicate(seed=1000 + index, best_affinity_kcal_mol=value)
            for index, value in enumerate(affinities)
        ),
    )


# A overlaps B, B overlaps C, and A is DISJOINT from C -- the fixture that
# separates a dominance rank from a tie-grouping. Four runs each, which is the
# smallest count that can support a separation at all.
_A = (-9.0, -8.8, -8.6, -8.5)
_B = (-8.6, -8.2, -7.5, -7.0)
_C = (-7.2, -7.0, -6.5, -6.0)


def test_overlapping_ligands_share_a_rank_and_a_transitively_separated_one_does_not():
    """The fixture that kills the tie-grouping this design first reached for.

    "Not separated" is NOT an equivalence relation: A overlaps B and B overlaps
    C while A and C are disjoint. A transitive closure over overlapping pairs
    renders 1, 1, 1 and destroys a genuine separation that the data supports.

    The dominance rank -- 1 + however many entries are separated below it --
    renders 1, 1, 2, which is the honest reading: A and B are
    indistinguishable, and C is behind at least one of them.
    """
    from openchem.services.screening_service import dominance_ranks

    entries = [_entry("A", *_A), _entry("B", *_B), _entry("C", *_C)]

    assert dominance_ranks(entries) == [1, 1, 2]


def test_the_separation_that_makes_that_fixture_work_really_is_disjoint():
    """Asserting the setup, so the guard above cannot go vacuous.

    If A and C ever stopped being disjoint the test would still render
    1, 1, 1 -- and would pass against a tie-grouping implementation while
    reading as though it had ruled one out.
    """
    from openchem.domain.affinity_range import ranges_separate

    a, b, c = (_entry("x", *values).spread for values in (_A, _B, _C))

    assert not ranges_separate(a, b)
    assert not ranges_separate(b, c)
    assert ranges_separate(a, c)


def test_a_screen_at_one_replicate_ranks_nothing():
    """The DEFAULT path, and it is the one almost everyone will see.

    Three ligands nearly a kcal/mol apart, docked once each. Every pair is
    NOT_ASSESSED, so every rank is 1 -- correct behaviour that looks exactly
    like a broken rank column, which is why `ranking_is_assessed` exists for
    the dialog to say so.
    """
    from openchem.services.screening_service import dominance_ranks, ranking_is_assessed

    entries = [_entry("A", -9.0), _entry("B", -8.0), _entry("C", -7.0)]

    assert dominance_ranks(entries) == [1, 1, 1]
    assert ranking_is_assessed(entries) is False


def test_the_ranking_is_assessed_over_PAIRS_and_never_from_a_count():
    """`min(n_a, n_b) >= 4` gets both of these wrong.

    The gate is `2/comb(n_a+n_b, n_a)`, which behaves non-obviously with
    unequal counts: 2 runs against 8 clears 0.05 at 0.044, while 2 against 5
    does not at 0.095. A count-based shortcut refuses the first and would have
    to be told about the second.
    """
    from openchem.services.screening_service import ranking_is_assessed

    two_and_eight = [_entry("A", -9.0, -8.9), _entry("B", *[-7.0 - i / 10 for i in range(8)])]
    two_and_five = [_entry("A", -9.0, -8.9), _entry("B", *[-7.0 - i / 10 for i in range(5)])]

    assert ranking_is_assessed(two_and_eight) is True
    assert ranking_is_assessed(two_and_five) is False


def test_a_ligand_that_never_scored_gets_no_rank():
    """Numbering a failure puts it in an ordering it is not part of."""
    from openchem.services.screening_service import dominance_ranks

    entries = [_entry("good", -9.0), ScreeningEntry(molecule_uuid="b", display_name="bad", error="no")]

    assert dominance_ranks(entries) == [1, None]


def test_a_ligand_docked_once_has_a_range_of_one_run():
    """One score IS a range of one, and saying so is not synthesising a record.

    `DockingResultModel.from_dict` refuses to manufacture a replicate SET for a
    legacy result, because that would be a stored claim about how the run was
    performed. This is a transient statement about how many scores are in hand,
    and it is what makes every pair involving the ligand come back
    NOT_ASSESSED rather than crashing on a missing range.
    """
    spread = _entry("A", -9.0).spread

    assert spread is not None
    assert spread.n == 1
    assert spread.width is None


def test_a_ligand_that_failed_has_no_range_at_all():
    """None, not an empty range -- "every run failed" and "not measured" have
    to stay distinguishable, which is why `AffinityRange` refuses to be empty.
    """
    assert ScreeningEntry(molecule_uuid="b", display_name="bad", error="no").spread is None


# --- what the screen actually runs ------------------------------------------


def test_the_screen_runs_every_ligand_the_requested_number_of_times(harness):
    """End to end through the real `DockingService`, counting provider calls.

    The mutation is the screen dropping the count on the floor -- which would
    leave every entry at one run, every pair NOT_ASSESSED, and the table
    permanently unable to rank anything however high the spin box was set.
    """
    engine, _bus, provider, screening, _events = harness
    project_ligands = _ligands(engine, _THREE)

    screening.request_screen(project_ligands, _receptor(), _box(), replicates=3)
    _drain()

    assert len(provider.calls) == 3 * len(project_ligands)


def test_a_screen_records_every_replicate_behind_each_ligand(harness):
    """The raw runs reach `ScreeningEntry`, so the dialog can show a range
    rather than a bare number it would have to trust."""
    engine, _bus, _provider, screening, events = harness

    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box(), replicates=3)
    _drain()

    scored = [entry for entry in events[-1].entries if not entry.failed]
    assert scored, "setup: at least one ligand scored"
    assert all(len(entry.replicates) == 3 for entry in scored)
    assert all(entry.spread.n == 3 for entry in scored)


def test_a_screen_at_the_default_replicate_count_is_unchanged(harness):
    """One call per ligand, exactly as before replicates existed."""
    engine, _bus, provider, screening, _events = harness
    project_ligands = _ligands(engine, _THREE)

    screening.request_screen(project_ligands, _receptor(), _box())
    _drain()

    assert len(provider.calls) == len(project_ligands)


# --- the dialog -------------------------------------------------------------


def test_the_dialog_sends_the_replicate_count_it_displays(harness, widgets, monkeypatch):
    """One accessor, so the dialog cannot show one count and screen another.

    Driven through the real `_start`, which means the box derivation has to
    succeed -- the shared receptor fixture names no ligand code, deliberately,
    because another test asserts that case is REPORTED rather than crashed. So
    the site is stubbed at `openchem.chem.binding_site.box_from_ligand`, which
    is where `_start` imports it from at call time.
    """
    from types import SimpleNamespace

    import openchem.chem.binding_site as binding_site

    engine, _bus, _provider, screening, _events = harness
    dialog = _dialog(widgets, harness, _project(engine))
    dialog._replicates.setValue(4)

    monkeypatch.setattr(
        binding_site,
        "box_from_ligand",
        lambda *a, **k: SimpleNamespace(box=_box(), describe=lambda: "a stubbed site"),
    )
    sent: dict = {}
    monkeypatch.setattr(screening, "request_screen", lambda *a, **k: sent.update(k))
    dialog._start()

    assert sent, "setup: _start really reached request_screen"
    assert sent["replicates"] == 4
    assert sent["num_poses"] == dialog._poses.value()


def test_the_ligand_note_states_the_multiplied_run_count(harness, widgets):
    """DERIVED, AND WITH NO WALL-CLOCK ESTIMATE.

    N multiplies the whole screen, so the cost has to be chosen rather than
    inherited -- and the honest way to state it is the run COUNT, which a
    reader can check, not a seconds-per-run constant fitted to one machine.
    """
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))
    dialog._replicates.setValue(5)

    note = dialog._ligand_note.text()
    assert "3 ligands x 5 replicates = 15 Vina runs" in note


def test_the_ligand_note_says_nothing_about_replicates_at_the_default(harness, widgets):
    """The narrow half. "3 ligands x 1 replicates = 3 Vina runs" is noise on
    the path almost everyone takes, and the default has to read as it did
    before replicates existed.
    """
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))

    assert dialog._ligand_note.text() == "3 ligands will be docked, in project order."


def test_an_unreplicated_table_ranks_everything_one_and_says_why(harness, widgets):
    """THE DEFAULT PATH, and it is correct behaviour that looks like a bug.

    Three ligands with clearly different scores all read rank 1. Without the
    note a reader concludes the rank column is broken; with it they know to
    raise Replicates. The note is checked for the ACTIONABLE half -- the
    control's name and the minimum count -- rather than for its exact prose.
    """
    from openchem.domain.affinity_range import MIN_REPLICATES_FOR_SEPARATION

    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))

    dialog._render(rank([_entry("A", -9.0), _entry("B", -8.0), _entry("C", -7.0)]))

    assert [dialog._results.item(row, 0).text() for row in range(3)] == ["1", "1", "1"]
    assert not dialog._ranking_note.isHidden()
    note = dialog._ranking_note.text()
    assert "Replicates" in note
    assert str(MIN_REPLICATES_FOR_SEPARATION) in note


def test_a_replicated_table_marks_a_shared_rank_and_leaves_a_separated_one_plain(
    harness, widgets
):
    """The A/B/C fixture through the real render.

    A and B share rank 1 and are marked; C is alone at rank 2 and is not. The
    mutation is `str(row + 1)`, which prints 1, 2, 3 -- a strict ordering
    whatever the evidence says.
    """
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))

    dialog._render(rank([_entry("A", *_A), _entry("B", *_B), _entry("C", *_C)]))

    assert [dialog._results.item(row, 0).text() for row in range(3)] == ["1=", "1=", "2"]
    assert "per-pair" in dialog._ranking_note.text()


def test_the_range_column_says_one_run_rather_than_a_zero(harness, widgets):
    """A single run measured NO spread; five agreeing runs measure a width of
    zero. Rendering both as 0.00 would be `n/a is not 0` in the one column
    whose whole job is to say how much the runs disagreed.
    """
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))

    dialog._render(rank([_entry("once", -9.0), _entry("agreeing", *([-8.0] * 5))]))

    cells = [dialog._results.item(row, 4).text() for row in range(2)]
    assert cells[0] == "1 run"
    assert cells[1] == "-8.00 to -8.00 (5 runs)"


def test_the_ranking_note_is_hidden_when_there_is_nothing_to_rank(harness, widgets):
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))

    dialog._render([])

    assert dialog._ranking_note.isHidden()


def test_every_result_column_has_an_explicit_resize_mode(harness, widgets):
    """A fifth column left unconfigured reproduces this table's own recorded
    defect: it would inherit Qt's default width and clip its header, and
    nothing in the suite would notice.

    Asserted over `_RESULT_COLUMNS` rather than over four hand-listed indices,
    so a sixth column is covered without anybody remembering to add it.
    """
    from PySide6.QtWidgets import QHeaderView

    from openchem.ui.dialogs.virtual_screening_dialog import (
        _RESULT_COLUMNS,
        _STRETCHED_COLUMN,
    )

    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))
    header = dialog._results.horizontalHeader()

    modes = {
        name: header.sectionResizeMode(column)
        for column, name in enumerate(_RESULT_COLUMNS)
    }
    assert dialog._results.columnCount() == len(_RESULT_COLUMNS)
    assert modes.pop(_STRETCHED_COLUMN) == QHeaderView.ResizeMode.Stretch
    assert set(modes.values()) == {QHeaderView.ResizeMode.ResizeToContents}



def test_no_row_numbers_sit_beside_the_rank_column(harness, widgets):
    """Qt's vertical header asserts the ordering the Rank column refuses.

    The table is SORTED BY SCORE, so a row index reads as a rank. It sat
    immediately left of a Rank column reading 1, 1, 1 above a note saying the
    ranking could not be assessed -- so the refusal was contradicted by the
    widget beside it, and a reader would believe the numbers over the prose.

    `isHidden`, not `isVisible`: every child of an unshown dialog reports
    `isVisible() == False`, so that assertion would pass against a header that
    is permanently shown.
    """
    engine = harness[0]
    dialog = _dialog(widgets, harness, _project(engine))

    assert dialog._results.verticalHeader().isHidden()


class _VaryingVina(_FakeVina):
    """Scores each replicate of a ligand differently, so median and minimum
    over the set are DIFFERENT numbers.

    `_FakeVina` returns the same score for a ligand on every call, so a screen
    at N replicates gives N identical values -- and a service taking the
    best-of-N instead of the median run produces byte-identical output. The
    shared fake cannot see that mutation at all, which is why this one exists.
    """

    def __init__(self, scores, step: float = 0.5) -> None:
        super().__init__(scores)
        self._step = step
        self._seen: dict[int, int] = {}

    def dock(self, receptor_text, receptor_format, ligand_mol, box, num_poses, progress, options):
        atoms = ligand_mol.GetNumAtoms()
        run = self._seen.get(atoms, 0)
        self._seen[atoms] = run + 1
        poses = super().dock(
            receptor_text, receptor_format, ligand_mol, box, num_poses, progress, options
        )
        return [
            DockingPoseModel(
                pose_molblock=pose.pose_molblock,
                binding_affinity_kcal_mol=pose.binding_affinity_kcal_mol + run * self._step,
                rmsd_lb=pose.rmsd_lb,
                rmsd_ub=pose.rmsd_ub,
            )
            for pose in poses
        ]


def test_the_screened_score_is_the_median_run_and_not_the_best_of_n(qapp):
    """The ranking must not improve with the replicate count.

    Three runs of the strongest ligand score -11.2, -10.7 and -10.2, so the
    median is -10.7 and the best-of-N is -11.2. Taking the minimum over the
    set would make every ligand's headline score drift more negative purely as
    Replicates rose -- the exact harm the median representative exists to
    prevent, reintroduced one layer up in the table that ranks them.
    """
    from openchem.app.settings import Settings

    engine = ChemistryEngine()
    bus = EventBus()
    jobs = JobManager()
    provider = _VaryingVina(_SCORES)
    docking = DockingService(bus, Settings(EventBus()), providers={"vina": provider}, job_manager=jobs)
    screening = ScreeningService(bus, docking, engine, job_manager=jobs)
    events: list[ScreeningProgress] = []
    bus.subscribe(ScreeningProgress, events.append)

    screening.request_screen(_ligands(engine, _THREE), _receptor(), _box(), replicates=3)
    _drain()

    best = {entry.display_name: entry.best_affinity_kcal_mol for entry in events[-1].entries}
    spread = {entry.display_name: entry.spread for entry in events[-1].entries}

    assert spread["strong"].n == 3
    assert spread["strong"].low == pytest.approx(-11.2)
    assert best["strong"] == pytest.approx(-10.7), "the MEDIAN run, not the best of three"
    assert best["strong"] != pytest.approx(spread["strong"].low)
