"""Drawing no longer recomputes fifty results per edit: WHEN it does is a policy.

The measurement that motivated this (`benchmarks/visual/README.md`): twelve edits of
aspirin, a new structure each time, cost a median 1.1 s each with the event loop blocked
for up to 4 s, because every edit fanned `MoleculeChanged` out to every descriptor
provider. Now a canvas edit publishes `MoleculeChanged(during_edit=True)`, everything that
merely has to KNOW acts at once (results read stale), and everything that COMPUTES waits
for `RecalculationDue`, which `RecalcScheduler` publishes when the policy says so.

These tests pin each half, and the two latent races the change would otherwise have widened:
an alert or descriptor computed for structure A read as current for B whenever an edit landed
mid-run.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QUndoStack

from openchem.app.settings import RECALC_MODE, RECALC_QUIET_MS, Settings
from openchem.chem.engine import ChemistryEngine
from openchem.commands.molecule_commands import EditStructureCommand
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.recalc_policy import (
    DEFAULT_QUIET_MS,
    MAX_QUIET_MS,
    RecalcMode,
    RecalcPolicy,
)
from openchem.domain.scientific_result import AlertResult
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID
from openchem.events.base import EventBus
from openchem.events.events import (
    AlertComputed,
    DescriptorComputed,
    MoleculeChanged,
    MoleculeSelected,
    RecalculationDue,
)
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.recalc_scheduler import RecalcScheduler
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose
from tests.test_property_panel import _FakeDescriptorService


# --- the policy ------------------------------------------------------------------------


def test_after_a_pause_uses_the_delay_and_is_the_default():
    policy = RecalcPolicy()
    assert policy.mode is RecalcMode.AFTER_PAUSE
    assert policy.delay_ms() == DEFAULT_QUIET_MS == 800


def test_while_drawing_is_a_zero_delay_whatever_a_stale_delay_holds():
    """The delay control belongs to "after I pause"; a value left in it must not slow
    the mode that asks for none."""
    assert RecalcPolicy(RecalcMode.WHILE_DRAWING, quiet_ms=3000).delay_ms() == 0


def test_only_when_asked_has_no_delay_at_all():
    assert RecalcPolicy(RecalcMode.ON_REQUEST, quiet_ms=800).delay_ms() is None


def test_the_delay_is_clamped_to_its_range():
    assert RecalcPolicy(RecalcMode.AFTER_PAUSE, quiet_ms=10**6).delay_ms() == MAX_QUIET_MS
    assert RecalcPolicy(RecalcMode.AFTER_PAUSE, quiet_ms=-5).delay_ms() == 0


def test_the_settings_default_is_a_pause_of_800_ms(qapp):
    policy = Settings(EventBus()).recalc_policy()
    assert policy == RecalcPolicy(RecalcMode.AFTER_PAUSE, 800)


def test_a_stored_choice_is_read_at_the_next_call(qapp):
    settings = Settings(EventBus())
    settings.set_preference(RECALC_MODE, int(RecalcMode.ON_REQUEST))
    settings.set_preference(RECALC_QUIET_MS, 1500)
    assert settings.recalc_policy() == RecalcPolicy(RecalcMode.ON_REQUEST, 1500)


def test_a_damaged_stored_mode_falls_back_to_the_default(qapp):
    settings = Settings(EventBus())
    settings.set(RECALC_MODE.key, "banana")
    assert settings.recalc_policy().mode is RecalcMode.AFTER_PAUSE


# --- the scheduler ---------------------------------------------------------------------


class _Rig:
    """A scheduler on a bus, a mutable policy, and every RecalculationDue it published."""

    def __init__(self) -> None:
        self.bus = EventBus()
        self.policy = RecalcPolicy(RecalcMode.AFTER_PAUSE, 800)
        self.scheduler = RecalcScheduler(self.bus, lambda: self.policy)
        self.due: list[str] = []
        self.pending: list[bool] = []
        self.bus.subscribe(RecalculationDue, lambda e: self.due.append(e.molecule_uuid))
        self.scheduler.pending_changed.connect(self.pending.append)

    def edit(self, uuid="m1") -> None:
        self.bus.publish(MoleculeChanged(molecule_uuid=uuid, during_edit=True))

    def fire(self) -> None:
        """The quiet period elapsing, without waiting for it."""
        self.scheduler._timer.timeout.emit()


@pytest.fixture
def rig(qapp):
    rig = _Rig()
    yield rig
    dispose(rig.scheduler)


def test_a_burst_of_edits_is_one_recalculation(rig):
    for _ in range(12):
        rig.edit()
    assert rig.due == [], "nothing recomputes while the edits keep coming"
    rig.fire()
    assert rig.due == ["m1"], "twelve edits, one run"


def test_every_edit_restarts_the_quiet_period(rig):
    """A debounce, not a throttle: a slow steady drawing rate must not fire every N ms."""
    rig.edit()
    assert rig.scheduler._timer.isActive()
    assert rig.scheduler._timer.interval() == 800
    rig.policy = RecalcPolicy(RecalcMode.AFTER_PAUSE, 1200)
    rig.edit()
    assert rig.scheduler._timer.interval() == 1200, "the policy is read at every edit, not cached"


def test_while_drawing_fires_on_the_next_turn_of_the_event_loop(rig):
    rig.policy = RecalcPolicy(RecalcMode.WHILE_DRAWING)
    rig.edit()
    rig.edit()
    assert rig.scheduler._timer.interval() == 0
    QCoreApplication.processEvents()
    assert rig.due == ["m1"], "edits within one turn coalesce into one run"


def test_only_when_asked_never_fires_by_itself(rig):
    rig.policy = RecalcPolicy(RecalcMode.ON_REQUEST)
    rig.edit()
    assert not rig.scheduler._timer.isActive()
    assert rig.scheduler.has_pending()
    QCoreApplication.processEvents()
    assert rig.due == []


def test_asking_runs_what_is_waiting_in_any_mode_and_says_when_there_was_nothing(rig):
    rig.policy = RecalcPolicy(RecalcMode.ON_REQUEST)
    assert rig.scheduler.recalculate_now() is False, "nothing waiting is said, not faked"
    rig.edit()
    assert rig.scheduler.recalculate_now() is True
    assert rig.due == ["m1"]
    assert not rig.scheduler.has_pending()


def test_switching_to_only_when_asked_stops_a_run_already_waiting(rig):
    rig.edit()
    assert rig.scheduler._timer.isActive()
    rig.policy = RecalcPolicy(RecalcMode.ON_REQUEST)
    rig.edit()
    assert not rig.scheduler._timer.isActive()


def test_a_deliberate_change_cancels_the_pending_run_for_that_molecule(rig):
    """Undo, redo, import and the rest recompute at once through their own consumers, so
    the pending run would only repeat what has just been done."""
    rig.edit("m1")
    rig.bus.publish(MoleculeChanged(molecule_uuid="m1", during_edit=False))
    assert not rig.scheduler.has_pending()
    assert not rig.scheduler._timer.isActive()
    rig.fire()
    assert rig.due == []


def test_a_change_to_another_molecule_leaves_this_ones_run_pending(rig):
    rig.edit("m1")
    rig.bus.publish(MoleculeChanged(molecule_uuid="m2", during_edit=False))
    assert rig.scheduler.pending_molecules() == ("m1",)


def test_selecting_a_molecule_cancels_everything_pending(rig):
    """Selection recomputes for the newly selected one, and a run for the one left behind
    would only be dropped by its consumers."""
    rig.edit("m1")
    rig.edit("m2")
    rig.bus.publish(MoleculeSelected(molecule_uuid="m3"))
    assert not rig.scheduler.has_pending()
    rig.fire()
    assert rig.due == []


def test_pending_changed_says_when_something_starts_and_stops_waiting(rig):
    rig.edit()
    rig.edit()
    rig.fire()
    assert rig.pending == [True, False], "once when it began waiting, once when it was done"


# --- the command -----------------------------------------------------------------------


def _molecule(engine, smiles="CCO") -> MoleculeModel:
    molecule = MoleculeModel(display_name="m")
    engine.set_structure_from_smiles(molecule, smiles)
    return molecule


def test_only_the_first_application_of_a_canvas_edit_is_during_edit():
    """An undo, or a redo of it, is a deliberate single action and recomputes at once."""
    engine = ChemistryEngine()
    bus = EventBus()
    seen: list[bool] = []
    bus.subscribe(MoleculeChanged, lambda e: seen.append(e.during_edit))
    molecule = _molecule(engine, "CCO")
    stack = QUndoStack()
    other = _molecule(engine, "CCCO")

    stack.push(EditStructureCommand(engine, molecule, other.molblock, bus, during_edit=True))
    stack.undo()
    stack.redo()

    assert seen == [True, False, False]


def test_an_edit_command_is_not_during_edit_unless_told():
    """Every other caller (quick fixes, adopting a conformer, a rotation) is one action."""
    engine = ChemistryEngine()
    bus = EventBus()
    seen: list[bool] = []
    bus.subscribe(MoleculeChanged, lambda e: seen.append(e.during_edit))
    molecule = _molecule(engine, "CCO")
    QUndoStack().push(EditStructureCommand(engine, molecule, _molecule(engine, "CCCO").molblock, bus))
    assert seen == [False]


def test_the_editor_marks_a_canvas_edit_during_edit(qapp):
    from tests.test_molecule_editor_widget import _edit_the_canvas, _molblock_for, _widget_with_electrons

    widget, backend, _molecule_ = _widget_with_electrons(qapp, "CO")
    seen: list[bool] = []
    widget._event_bus.subscribe(MoleculeChanged, lambda e: seen.append(e.during_edit))

    _edit_the_canvas(widget, backend, _molblock_for("CCO"))

    assert seen == [True]


# --- the consumers ---------------------------------------------------------------------


class _Versions:
    def __init__(self) -> None:
        self.version = 0

    def __call__(self, _uuid: str) -> int:
        return self.version


def _substance_definition() -> CalculatorDefinition:
    return CalculatorDefinition(
        calculator_id="substance_analysis",
        display_name="Substance analysis",
        category="identity",
        description="Fixture.",
        execution=RegistryExecution(compute=lambda _m, _u, _p: None),
    )


@pytest.fixture
def panel_rig(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(_substance_definition())
    service = _FakeDescriptorService()
    versions = _Versions()
    panel = PropertyPanel(bus, registry, service, engine, structure_version_of=versions)
    molecule = _molecule(engine)
    panel.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    service.calls.clear()
    yield panel, bus, molecule, service, versions
    dispose(panel)


def test_a_canvas_edit_does_not_rerun_the_substance_perception(panel_rig):
    panel, bus, molecule, service, _versions = panel_rig
    bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    assert service.calls == [], "the panel waits for RecalculationDue"


def test_the_recalculation_that_follows_perceives_the_substance_once(panel_rig):
    panel, bus, molecule, service, _versions = panel_rig
    bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    bus.publish(RecalculationDue(molecule_uuid=molecule.uuid))
    assert [c[1].calculator_id for c in service.calls] == ["substance_analysis"]


def test_a_deliberate_change_still_perceives_at_once(panel_rig):
    """Undo, import, rename: nothing waits."""
    panel, bus, molecule, service, _versions = panel_rig
    bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=False))
    assert [c[1].calculator_id for c in service.calls] == ["substance_analysis"]


def test_a_recalculation_for_another_molecule_is_ignored(panel_rig):
    panel, bus, _molecule_, service, _versions = panel_rig
    bus.publish(RecalculationDue(molecule_uuid="somebody-else"))
    assert service.calls == []


def _alert(molecule_uuid: str, alert_id="pains") -> AlertResult:
    return AlertResult(
        timestamp=0.0, alert_id=alert_id, name="PAINS", molecule_uuid=molecule_uuid, matched=[],
    )


def test_an_alert_is_stamped_with_the_version_it_was_dispatched_against(panel_rig):
    """The latent race the debounce widens: the run finishes AFTER the next edit, and
    stamping arrival time made it read current for a structure it was not computed on."""
    panel, bus, molecule, _service, versions = panel_rig
    versions.version = 7  # an edit landed while the run was in flight

    bus.publish(AlertComputed(alert=_alert(molecule.uuid), structure_version=5))

    held = panel._reports["pains"]
    assert held.structure_version == 5, "not the 7 it arrived under"


def test_an_alert_with_no_stated_version_falls_back_to_arrival(panel_rig):
    panel, bus, molecule, _service, versions = panel_rig
    versions.version = 7
    bus.publish(AlertComputed(alert=_alert(molecule.uuid)))
    assert panel._reports["pains"].structure_version == 7


def test_an_older_alert_finishing_late_does_not_replace_a_newer_one(panel_rig):
    """Runs on a thread pool finish in any order, and there is one slot per alert."""
    panel, bus, molecule, _service, versions = panel_rig
    versions.version = 9
    bus.publish(AlertComputed(alert=_alert(molecule.uuid), structure_version=8))
    bus.publish(AlertComputed(alert=_alert(molecule.uuid), structure_version=6))
    assert panel._reports["pains"].structure_version == 8


def _descriptor(molecule_uuid: str, descriptor_id="mol_wt") -> DescriptorValue:
    return DescriptorValue(
        descriptor_id=descriptor_id, name="Molecular Weight", units="g/mol", category="physicochemical",
        provider="rdkit", molecule_uuid=molecule_uuid, value=46.07, cache_state=CacheState.COMPLETED,
    )


def test_held_descriptors_read_stale_the_moment_the_structure_moves_on(panel_rig):
    """Before the pause there is nothing new to replace them, so the set must not claim the
    structure it was not computed on."""
    panel, bus, molecule, _service, versions = panel_rig
    versions.version = 3
    bus.publish(DescriptorComputed(descriptor=_descriptor(molecule.uuid), structure_version=3))
    entries, version = panel._reader_entries()
    aggregate = next(e for e in entries if getattr(e, "report_id", "") == DESCRIPTOR_AGGREGATE_ID)
    assert aggregate.structure_version == version == 3

    versions.version = 4  # the edit, whose recomputation is still waiting for the pause
    bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    entries, version = panel._reader_entries()
    aggregate = next(e for e in entries if getattr(e, "report_id", "") == DESCRIPTOR_AGGREGATE_ID)

    assert version == 4
    assert aggregate.structure_version == 3, "still the old structure's numbers, and it says so"


def test_an_older_descriptor_finishing_late_does_not_replace_a_newer_one(panel_rig):
    panel, bus, molecule, _service, versions = panel_rig
    versions.version = 6
    newer = _descriptor(molecule.uuid)
    older = replace(newer, value=1.0)
    bus.publish(DescriptorComputed(descriptor=newer, structure_version=6))
    bus.publish(DescriptorComputed(descriptor=older, structure_version=4))
    assert panel._descriptor_values[("rdkit", "mol_wt")].value == 46.07


# --- the window ------------------------------------------------------------------------


@pytest.fixture
def window_rig(qapp, tmp_path):
    """A real MainWindow with one molecule selected, and `_restore_or_compute` counted.

    Counting that call is the point: it IS the descriptor fan-out, the 1.1 s an edit cost.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    session = SessionManager()
    window = MainWindow(services, settings, session)
    molecule = _molecule(services.chemistry_engine)
    session.set_project(ProjectModel(molecules=[molecule]))
    session.select_molecule(molecule.uuid)
    calls: list[str] = []
    window._restore_or_compute = lambda m: calls.append(m.uuid)
    yield window, services, molecule, calls, settings
    services.recalc_scheduler.cancel_all()


def test_the_window_waits_for_the_recalculation_after_a_canvas_edit(window_rig):
    window, services, molecule, calls, _settings = window_rig
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    assert calls == [], "a canvas edit must not run the descriptor fan-out"

    services.recalc_scheduler.recalculate_now()

    assert calls == [molecule.uuid], "and the recalculation it earned runs once"


def test_a_deliberate_change_recomputes_at_once(window_rig):
    """Undo, redo, import: the descriptors are replayed or recomputed immediately, and a
    pending run is cancelled because it would repeat that."""
    window, services, molecule, calls, _settings = window_rig
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=False))
    assert calls == [molecule.uuid]
    assert not services.recalc_scheduler.has_pending()


def test_a_run_that_fires_after_selecting_something_else_recomputes_nothing_stale(window_rig):
    window, services, molecule, calls, _settings = window_rig
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    window._session.select_molecule(None)
    services.event_bus.publish(RecalculationDue(molecule_uuid=molecule.uuid))
    assert calls == []


def test_recalculate_now_is_disabled_until_an_edit_waits(window_rig):
    window, services, molecule, _calls, _settings = window_rig
    assert not window._recalculate_action.isEnabled()
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    assert window._recalculate_action.isEnabled()
    services.recalc_scheduler.recalculate_now()
    assert not window._recalculate_action.isEnabled()


def test_only_when_asked_says_so_in_the_status_bar_and_clears_only_its_own_message(window_rig):
    window, services, molecule, _calls, settings = window_rig
    settings.set_preference(RECALC_MODE, int(RecalcMode.ON_REQUEST))
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    assert "out of date" in window.statusBar().currentMessage()
    services.recalc_scheduler.recalculate_now()
    assert window.statusBar().currentMessage() == ""


def test_the_pause_modes_do_not_wipe_an_unrelated_status_message(window_rig):
    window, services, molecule, _calls, _settings = window_rig
    window.statusBar().showMessage("something else the person should read", 0)
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    services.recalc_scheduler.recalculate_now()
    assert window.statusBar().currentMessage() == "something else the person should read"


def test_the_menu_action_asks_the_scheduler(window_rig):
    window, services, molecule, calls, _settings = window_rig
    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    window._recalculate_action.trigger()
    assert calls == [molecule.uuid]


def test_asking_with_nothing_waiting_says_the_results_are_current(window_rig):
    window, _services, _molecule_, calls, _settings = window_rig
    window._on_recalculate_now()
    assert "current" in window.statusBar().currentMessage()
    assert calls == []


# --- what an edit still cost once the fan-out waited ----------------------------------------
#
# Profiled after the debounce (`edit_burst` with "profile": true), the burst that remained was
# two things: the Results reader rebuilt once per descriptor EVENT (144 rebuilds of about 60 rows,
# 1.4 s), and the Atom Inspector's atom table rebuilt on every undo-stack index change with IUPAC
# locants (12 of the 12 edits, ~90 ms each, about 80% of an edit's synchronous cost).


def test_a_flood_of_descriptor_events_rebuilds_the_reader_once(panel_rig):
    panel, bus, molecule, _service, versions = panel_rig
    rebuilds: list[int] = []
    original = panel._refresh_reader
    panel._refresh_reader = lambda: (rebuilds.append(1), original())[1]

    for index in range(41):
        bus.publish(DescriptorComputed(descriptor=_descriptor(molecule.uuid, f"d{index}")))
    assert rebuilds == [], "nothing rebuilds while the events are still arriving"

    QCoreApplication.processEvents()

    assert rebuilds == [1], "forty-one events, one rebuild"


def test_a_single_report_still_refreshes_the_reader_at_once(panel_rig):
    """Only the descriptor flood is coalesced: code that reads the reader straight after a
    calculator's result must find it current."""
    from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
    from openchem.events.events import ReportComputed

    panel, bus, molecule, _service, _versions = panel_rig
    rebuilds: list[int] = []
    original = panel._refresh_reader
    panel._refresh_reader = lambda: (rebuilds.append(1), original())[1]

    bus.publish(ReportComputed(report=ReportResult(
        molecule_uuid=molecule.uuid, report_id="x", name="x", category="topology",
        facts=(Fact(category=FactCategory.TOPOLOGY, label="x", value=1, display_value="1",
                    source="t", basis=Basis.DETERMINISTIC),),
    )))

    assert rebuilds == [1]


def test_a_canvas_edit_leaves_the_atom_table_for_the_pause(window_rig):
    window, services, molecule, _calls, _settings = window_rig
    rebuilt: list[int] = []
    window._atom_inspector_panel.set_project = lambda project: rebuilt.append(1)

    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    window._on_undo_index_changed(1)
    assert rebuilt == [], "the atom table names every atom with IUPAC locants: not per edit"

    services.recalc_scheduler.recalculate_now()
    assert rebuilt == [1], "it catches up when the recomputation the pause waited for runs"


def test_undo_still_rebuilds_the_atom_table_at_once(window_rig):
    window, services, molecule, _calls, _settings = window_rig
    rebuilt: list[int] = []
    window._atom_inspector_panel.set_project = lambda project: rebuilt.append(1)

    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=False))
    window._on_undo_index_changed(0)

    assert rebuilt == [1]


def test_the_edit_flag_does_not_outlive_its_push(window_rig):
    """One canvas edit defers ONE rebuild. A later index change that published no
    MoleculeChanged at all -- undoing an imported macromolecule is one -- must not inherit it."""
    window, services, molecule, _calls, _settings = window_rig
    rebuilt: list[int] = []
    window._atom_inspector_panel.set_project = lambda project: rebuilt.append(1)

    services.event_bus.publish(MoleculeChanged(molecule_uuid=molecule.uuid, during_edit=True))
    window._on_undo_index_changed(1)
    assert rebuilt == []
    window._on_undo_index_changed(0)  # no event this time

    assert rebuilt == [1], "the second change is not a canvas edit"
