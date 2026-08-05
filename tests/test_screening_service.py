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
    from PySide6.QtCore import QCoreApplication, QEvent

    built = []
    yield built
    for widget in built:
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


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
