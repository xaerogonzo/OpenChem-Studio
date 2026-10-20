"""The synthesis panel (`plugins/synthesis_planner/`): it asks for a plan only through `context.synthesis_requests`, reads the planner's configuration off the GUI thread, shows a plan against the structure it was made for, and says what the planner said and no more.

The plugin is loaded by the real `PluginManager` over a fake host, so the panel is the one the application builds; the real planning service is exercised in `test_synthesis_host.py`."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.chem.reaction_depiction import DepictionError, render_step_svg
from openchem.domain.common import CacheState
from openchem.domain.synthesis_route import (
    STANDARD_LIMITATIONS,
    PlannerIdentity,
    Route,
    RouteMolecule,
    RouteSet,
    RouteStatus,
    RouteStep,
    TargetIdentity,
)
from openchem.events.events import MoleculeSelected, SettingsChanged, SynthesisJobStateChanged, SynthesisRouteReady
from openchem.plugins.manager import PluginManager
from openchem.plugins.synthesis_access import SynthesisTarget
from openchem.services.synthesis_planner_setup import PlannerOptions
from openchem.services.synthesis_planning_service import BoundResult, RequestOutcome
from test_plugin_manager import FakeUIRegistry

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
ANHYDRIDE = "CC(=O)OC(C)=O"
SALICYLIC = "O=C(O)c1ccccc1O"
UUID = "mol-1"

TARGET = SynthesisTarget(molecule_uuid=UUID, display_name="Aspirin", canonical_smiles=ASPIRIN)
OPTIONS = PlannerOptions(
    ok=True, version="4.4.1", expansion=("ring", "uspto"), stock=("mine", "zinc"), filters=("uspto",),
    chosen_expansion="uspto", chosen_stock="zinc", chosen_filter=None,
)


def route_set(status=RouteStatus.FOUND, smiles=ASPIRIN, **kw) -> RouteSet:
    target = TargetIdentity(molecule_uuid=UUID, canonical_smiles=smiles, fingerprint="f")
    planner = PlannerIdentity(planner="AiZynthFinder", version="4.4.1")
    if status is RouteStatus.FOUND:
        first = Route(
            target_smiles=ASPIRIN, rank=1, score=0.9876,
            steps=(RouteStep(product=ASPIRIN, reactants=(ANHYDRIDE, SALICYLIC), policy_probability=0.5, template_id="t1"),),
            starting_materials=(RouteMolecule(smiles=ANHYDRIDE, in_stock=True), RouteMolecule(smiles=SALICYLIC, in_stock=None)),
        )
        two_steps = Route(
            target_smiles=ASPIRIN, rank=2,
            steps=(RouteStep(product=SALICYLIC, reactants=("Oc1ccccc1", "O=C=O")), RouteStep(product=ASPIRIN, reactants=(ANHYDRIDE, SALICYLIC))),
            starting_materials=(RouteMolecule(smiles="Oc1ccccc1", in_stock=True), RouteMolecule(smiles="O=C=O", in_stock=True), RouteMolecule(smiles=ANHYDRIDE, in_stock=True)),
        )
        return RouteSet(status=status, target=target, planner=planner, routes=(first, two_steps), **kw)
    return RouteSet(status=status, target=target, planner=planner, reason=kw.pop("reason", "because"), **kw)


class FakeHost:
    def __init__(self) -> None:
        self.target_value: SynthesisTarget | None = TARGET
        self.results: dict[str, BoundResult] = {}
        self.planning: set[str] = set()
        self.warm = True
        self.options_value = OPTIONS
        self.options_gate: threading.Event | None = None
        self.options_threads: list[int] = []
        self.calls: list[tuple] = []
        self.outcome = RequestOutcome.STARTED
        self.depict_error: Exception | None = None

    def target(self):
        return self.target_value

    def result_for(self, molecule_uuid):
        return self.results.get(molecule_uuid)

    def is_planning(self, molecule_uuid):
        return molecule_uuid in self.planning

    def setup_is_warm(self):
        return self.warm

    def options(self):
        self.options_threads.append(threading.get_ident())
        if self.options_gate is not None:
            self.options_gate.wait(10)
        self.calls.append(("options",))
        self.warm = True
        return self.options_value

    def depict(self, step):
        if self.depict_error is not None:
            raise self.depict_error
        return render_step_svg(step)

    def request_plan(self, molecule_uuid, requested_by):
        self.calls.append(("request_plan", molecule_uuid, requested_by))
        return self.outcome

    def cancel(self, molecule_uuid):
        self.calls.append(("cancel", molecule_uuid))
        return True

    def choose(self, section, name):
        self.calls.append(("choose", section, name))


class Loaded:
    def __init__(self, tmp_path, host: FakeHost) -> None:
        self.services = build_service_container()
        settings = Settings(self.services.event_bus)
        settings.set("plugins/project_directory", str(PLUGINS_DIR))
        settings.set("plugins/user_directory", str(tmp_path / "unused"))
        self.ui = FakeUIRegistry()
        self.manager = PluginManager(self.services, self.ui, settings, None, host)
        self.manager.load_all()
        self.host = host

    @property
    def panel(self):
        return self.ui.panels["Synthesis"]


def pump(predicate, seconds=10.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


@pytest.fixture
def loaded(tmp_path, qapp):
    made = []

    def build(host=None):
        item = Loaded(tmp_path, host or FakeHost())
        made.append(item)
        return item

    yield build
    for item in made:
        for plugin_id in list(item.manager.loaded_plugin_ids):
            item.manager.unload(plugin_id)


def shown(loaded_world: Loaded):
    """The panel, shown, with the configuration read."""
    panel = loaded_world.panel
    panel.show()
    assert pump(lambda: loaded_world.host.calls.count(("options",)) >= 1 and not panel._options_loading)
    return panel


# --- the plugin --------------------------------------------------------------------------------------------------------------------------------


def test_the_plugin_loads_with_a_panel_and_a_menu_entry_that_reveals_it(loaded):
    world = loaded()
    assert "synthesis_planner" in world.manager.loaded_plugin_ids and "Synthesis" in world.ui.panels
    (label, callback), = world.ui.menu_actions["synthesis_planner"]
    assert label == "Plan Synthesis"
    callback()
    assert world.ui.revealed_panels == ["Synthesis"]


def test_the_plugin_loads_without_a_host_and_says_nothing_is_selected(tmp_path, qapp):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(PLUGINS_DIR))
    settings.set("plugins/user_directory", str(tmp_path / "unused"))
    ui = FakeUIRegistry()
    PluginManager(services, ui, settings).load_all()
    panel = ui.panels["Synthesis"]
    assert "Select a molecule" in panel._target_label.text() and not panel._plan_button.isEnabled()


# --- the target and the configuration ----------------------------------------------------------------------------------------------------


def test_nothing_selected_offers_nothing(loaded):
    host = FakeHost()
    host.target_value = None
    panel = loaded(host).panel
    assert "Select a molecule" in panel._target_label.text() and panel._plan_button.isEnabled() is False and panel._cancel_button.isEnabled() is False
    assert panel._status.text() == "" and panel._routes.count() == 0 and panel._limitations.text() == ""


def test_the_target_is_shown_with_its_name_and_structure(loaded):
    panel = loaded().panel
    assert panel._target_label.text() == f"Target: Aspirin\n{ASPIRIN}"
    assert panel._plan_button.isEnabled() and panel._status.text() == "No plan for this molecule yet."


def test_showing_the_panel_reads_the_configuration_off_the_gui_thread_and_fills_the_three_lists(loaded):
    world = loaded()
    panel = shown(world)
    assert world.host.options_threads and all(thread != threading.get_ident() for thread in world.host.options_threads)
    assert [panel._expansion.itemText(i) for i in range(panel._expansion.count())] == ["ring", "uspto"] and panel._expansion.currentText() == "uspto"
    assert [panel._stock.itemText(i) for i in range(panel._stock.count())] == ["mine", "zinc"] and panel._stock.currentText() == "zinc"
    assert [panel._filter.itemText(i) for i in range(panel._filter.count())] == ["No filter", "uspto"] and panel._filter.currentText() == "No filter"
    assert panel._version_label.text() == "AiZynthFinder 4.4.1"


def test_a_chosen_filter_is_the_one_selected_in_its_list(loaded):
    host = FakeHost()
    host.options_value = PlannerOptions(ok=True, expansion=("uspto",), stock=("zinc",), filters=("uspto",), chosen_expansion="uspto", chosen_stock="zinc", chosen_filter="uspto")
    assert shown(loaded(host))._filter.currentText() == "uspto"


def test_choosing_in_a_list_writes_the_choice_and_reads_the_configuration_again(loaded):
    world = loaded()
    panel = shown(world)
    before = world.host.calls.count(("options",))

    panel._expansion.setCurrentText("ring")
    panel._expansion.activated.emit(panel._expansion.currentIndex())
    panel._filter.setCurrentText("uspto")
    panel._filter.activated.emit(panel._filter.currentIndex())
    panel._filter.setCurrentText("No filter")
    panel._filter.activated.emit(panel._filter.currentIndex())

    assert [c for c in world.host.calls if c[0] == "choose"] == [("choose", "expansion", "ring"), ("choose", "filter", "uspto"), ("choose", "filter", None)]
    assert pump(lambda: world.host.calls.count(("options",)) > before)


def test_a_change_to_the_planners_settings_reads_the_configuration_again_only_while_shown(loaded):
    world = loaded()
    panel = shown(world)
    before = world.host.calls.count(("options",))
    world.services.event_bus.publish(SettingsChanged(key="orca/executable_path"))
    QApplication.processEvents()
    time.sleep(0.1)
    QApplication.processEvents()
    assert world.host.calls.count(("options",)) == before  # not the planner's
    world.services.event_bus.publish(SettingsChanged(key="aizynthfinder/stock"))
    assert pump(lambda: world.host.calls.count(("options",)) > before)
    again = world.host.calls.count(("options",))
    panel.hide()
    world.services.event_bus.publish(SettingsChanged(key="aizynthfinder/stock"))
    QApplication.processEvents()
    time.sleep(0.1)
    QApplication.processEvents()
    assert world.host.calls.count(("options",)) == again  # a hidden panel reads it when it is next shown


def test_a_configuration_that_cannot_serve_a_plan_says_why_and_where_to_fix_it(loaded):
    host = FakeHost()
    host.options_value = PlannerOptions(ok=False, problem="Not configured: set the Python of the environment AiZynthFinder is installed in")
    panel = shown(loaded(host))
    assert "Not configured" in panel._status.text() and "Edit > Settings > External tools > AiZynthFinder" in panel._status.text()
    assert panel._expansion.isEnabled() is False
    assert panel._plan_button.isEnabled()  # the service still answers, so the gate has its say first


def test_a_failed_reading_of_the_configuration_is_shown_and_does_not_hang_the_panel(loaded):
    host = FakeHost()

    def raising():
        raise RuntimeError("boom")

    host.options = raising
    world = loaded(host)
    panel = world.panel
    panel.show()
    assert pump(lambda: "could not be read" in panel._status.text())
    assert "boom" in panel._status.text() and panel._options_loading is False


# --- asking --------------------------------------------------------------------------------------------------------------------------------------


def test_plan_asks_through_the_requests_handle_for_the_selected_molecule_in_the_users_name(loaded):
    world = loaded()
    panel = shown(world)
    panel._plan_button.click()
    assert ("request_plan", UUID, "the user") in world.host.calls


def test_plan_pressed_before_the_configuration_was_read_waits_for_it_and_then_asks(loaded):
    host = FakeHost()
    host.warm = False
    host.options_gate = threading.Event()
    world = loaded(host)
    panel = world.panel
    panel._plan_button.click()
    assert panel._plan_button.isEnabled() is False and "Reading the planner's configuration" in panel._status.text()
    QApplication.processEvents()
    assert not any(call[0] == "request_plan" for call in host.calls)  # nothing is asked while the configuration is being read
    host.options_gate.set()
    assert pump(lambda: any(call[0] == "request_plan" for call in host.calls))
    assert host.calls.index(("options",)) < host.calls.index(("request_plan", UUID, "the user"))
    assert panel._plan_after_options is None


def test_a_plan_waiting_for_the_configuration_is_dropped_if_another_molecule_is_selected(loaded):
    host = FakeHost()
    host.warm = False
    host.options_gate = threading.Event()
    world = loaded(host)
    panel = world.panel
    panel._plan_button.click()
    host.target_value = SynthesisTarget(molecule_uuid="other", display_name="Other", canonical_smiles="CCO")
    panel.refresh()
    host.options_gate.set()
    assert pump(lambda: panel._plan_after_options is None)
    QApplication.processEvents()
    assert not any(call[0] == "request_plan" for call in host.calls)


@pytest.mark.parametrize("outcome,text", [(RequestOutcome.ALREADY_RUNNING, "already being planned"), (RequestOutcome.REJECTED, "nothing to plan")])
def test_a_request_that_started_nothing_says_so(loaded, outcome, text):
    host = FakeHost()
    host.outcome = outcome
    panel = shown(loaded(host))
    panel._plan_button.click()
    assert text in panel._status.text()


def test_cancel_is_enabled_only_while_this_molecule_is_being_planned_and_asks_to_stop_it(loaded):
    host = FakeHost()
    world = loaded(host)
    panel = shown(world)
    assert panel._cancel_button.isEnabled() is False and panel._plan_button.isEnabled() is True
    host.planning.add(UUID)
    panel.refresh()
    assert panel._cancel_button.isEnabled() is True and panel._plan_button.isEnabled() is False
    panel._cancel_button.click()
    assert ("cancel", UUID) in host.calls


def test_while_planning_the_status_is_the_jobs_own_message(loaded):
    host = FakeHost()
    world = loaded(host)
    panel = shown(world)
    host.planning.add(UUID)
    world.services.event_bus.publish(SynthesisJobStateChanged(molecule_uuid=UUID, state=CacheState.RUNNING, message="Planning Aspirin (500 iterations)"))
    assert pump(lambda: panel._status.text() == "Planning Aspirin (500 iterations)")
    host.planning.discard(UUID)
    world.services.event_bus.publish(SynthesisJobStateChanged(molecule_uuid=UUID, state=CacheState.COMPLETED, message="done"))
    assert pump(lambda: panel._status.text() != "Planning Aspirin (500 iterations)")
    assert panel._cancel_button.isEnabled() is False


# --- what is shown --------------------------------------------------------------------------------------------------------------------------


def with_result(host: FakeHost, result: RouteSet, current=True, note="") -> None:
    host.results[UUID] = BoundResult(route_set=result, is_current=current, note=note)


def test_routes_are_listed_in_the_planners_order_with_what_the_planner_said(loaded):
    host = FakeHost()
    with_result(host, route_set())
    panel = loaded(host).panel
    titles = [panel._routes.item(i).text() for i in range(panel._routes.count())]
    assert titles == ["Route 1: 1 step, 2 starting materials, planner score 0.988", "Route 2: 2 steps, 3 starting materials"]
    assert panel._status.text() == "2 routes found." and panel._warning.isHidden()
    assert panel._routes.currentRow() == 0 and panel._steps.count() == 1


def test_selecting_a_route_lists_its_steps_in_the_order_they_would_be_run_and_draws_the_first(loaded):
    host = FakeHost()
    with_result(host, route_set())
    panel = loaded(host).panel
    panel._routes.setCurrentRow(1)
    steps = [panel._steps.item(i).text() for i in range(panel._steps.count())]
    assert steps == [f"Step 1: Oc1ccccc1 + O=C=O  >>  {SALICYLIC}", f"Step 2: {ANHYDRIDE} + {SALICYLIC}  >>  {ASPIRIN}"]
    assert panel._steps.currentRow() == 0 and not panel._picture.isHidden() and panel._picture_message.isHidden()


def test_everything_about_routes_is_one_block_shown_only_when_there_are_routes(loaded):
    host = FakeHost()
    world = loaded(host)
    panel = world.panel
    assert panel._route_block.isHidden() and not panel._limitations.isHidden()  # the limitations are never part of the hidden block
    with_result(host, route_set())
    panel.refresh()
    assert not panel._route_block.isHidden()
    with_result(host, route_set(RouteStatus.NO_ROUTE))
    panel.refresh()
    assert panel._route_block.isHidden() and "no route found" in panel._status.text().lower()
    for sentence in STANDARD_LIMITATIONS:
        assert sentence in panel._limitations.text()


def test_a_step_shows_every_field_the_planner_gave_and_says_the_rest_was_not_provided(loaded):
    host = FakeHost()
    with_result(host, route_set())
    panel = loaded(host).panel
    text = panel._details.toPlainText()
    assert "Template: t1" in text and "Policy: not provided" in text and "0.5 (the model's score for this template" in text
    assert "Conditions, reagents and yield: not provided" in text
    assert f"{ANHYDRIDE}   (in stock)" in text and f"{SALICYLIC}   (stock status not provided)" in text
    assert "Internal consistency: not checked." in text
    assert "validated" not in text.lower().replace("not been validated", "")


def test_the_standing_limitations_are_always_beside_the_routes(loaded):
    host = FakeHost()
    with_result(host, route_set())
    panel = loaded(host).panel
    for sentence in STANDARD_LIMITATIONS:
        assert sentence in panel._limitations.text()
    assert "Some routes have not been checked for internal consistency." in panel._limitations.text()


def test_a_result_with_no_routes_shows_its_message_and_the_limitations_and_no_picture(loaded):
    host = FakeHost()
    with_result(host, route_set(RouteStatus.REFUSED, reason="not planned: a match on rule X"))
    panel = loaded(host).panel
    assert panel._status.text() == "Not planned: not planned: a match on rule X"
    assert panel._routes.count() == 0 and panel._steps.count() == 0 and panel._details.toPlainText() == "" and panel._picture.isHidden()
    for sentence in STANDARD_LIMITATIONS:
        assert sentence in panel._limitations.text()


def test_a_plan_for_an_earlier_structure_is_shown_under_a_warning_and_never_as_the_current_plan(loaded):
    host = FakeHost()
    with_result(host, route_set(smiles="CCO"), current=False, note="This plan was made for an earlier version of this structure (CCO). It is not the plan for the structure now drawn.")
    panel = loaded(host).panel
    assert not panel._warning.isHidden() and panel._warning.text().startswith("EARLIER STRUCTURE: This plan was made for an earlier version")
    assert panel._routes.count() == 2  # still readable, but labelled
    host.results[UUID] = BoundResult(route_set=route_set(), is_current=True)
    panel.refresh()
    assert panel._warning.isHidden()


def test_a_step_that_cannot_be_drawn_says_so_in_words_and_not_in_a_picture(loaded):
    host = FakeHost()
    host.depict_error = DepictionError("the molecule 'x' could not be read, so this step cannot be drawn")
    with_result(host, route_set())
    panel = loaded(host).panel
    assert panel._picture.isHidden() and not panel._picture_message.isHidden()
    assert panel._picture_message.text() == "This step cannot be drawn: the molecule 'x' could not be read, so this step cannot be drawn"
    host.depict_error = None
    panel._steps.setCurrentRow(0)
    panel._on_step_changed(0)
    assert not panel._picture.isHidden() and panel._picture_message.isHidden()


# --- events ----------------------------------------------------------------------------------------------------------------------------------


def test_a_finished_plan_appears_without_asking(loaded):
    host = FakeHost()
    world = loaded(host)
    panel = shown(world)
    assert panel._routes.count() == 0
    with_result(host, route_set())
    world.services.event_bus.publish(SynthesisRouteReady(molecule_uuid=UUID, route_set=host.results[UUID].route_set))
    assert pump(lambda: panel._routes.count() == 2)


def test_selecting_another_molecule_shows_that_molecules_plan_or_none(loaded):
    host = FakeHost()
    with_result(host, route_set())
    world = loaded(host)
    panel = shown(world)
    assert panel._routes.count() == 2
    host.target_value = SynthesisTarget(molecule_uuid="other", display_name="Other", canonical_smiles="CCO")
    world.services.event_bus.publish(MoleculeSelected(molecule_uuid="other"))
    assert pump(lambda: panel._routes.count() == 0)
    assert panel._target_label.text() == "Target: Other\nCCO" and panel._status.text() == "No plan for this molecule yet." and panel._limitations.text() == ""
    host.target_value = None
    world.services.event_bus.publish(MoleculeSelected(molecule_uuid=None))
    assert pump(lambda: "Select a molecule" in panel._target_label.text())


def test_the_panel_follows_the_events_after_the_plugin_is_unloaded_without_error(loaded, qapp):
    host = FakeHost()
    world = loaded(host)
    world.manager.unload("synthesis_planner")
    world.services.event_bus.publish(MoleculeSelected(molecule_uuid=UUID))
    QApplication.processEvents()  # the subscriptions were unwound, so nothing reaches the removed panel
    assert "synthesis_planner" not in world.manager.loaded_plugin_ids
