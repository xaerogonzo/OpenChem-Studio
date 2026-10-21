"""`context.synthesis` and its window-side host (`plugins/synthesis_access.py`, `app/synthesis_host.py`): the selected molecule, a plan asked for through the ONE service path (so the regulatory gate has already spoken), the choices written to the settings the planner reads, and a reading handle that cannot start anything."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from test_synthesis_planning_service import ASPIRIN, SARIN, molecule

from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.app.synthesis_host import SynthesisHost
from openchem.bootstrap import build_service_container
from openchem.chem import synthesis_gate as gate_module
from openchem.chem.reaction_depiction import DepictionError
from openchem.domain.project import ProjectModel
from openchem.domain.synthesis_gate import GateDecision, GateOutcome
from openchem.domain.synthesis_route import PlannerIdentity, RouteSet, RouteStatus, RouteStep, SearchTermination
from openchem.plugins.manager import PluginManager
from openchem.plugins.synthesis_access import CHOICES, PluginSynthesis, PluginSynthesisRequests
from openchem.services import synthesis_planner_setup as setup
from openchem.services.synthesis_planner_setup import PlannerOptions
from openchem.services.synthesis_planning_service import RequestOutcome, SynthesisPlanningService
from test_plugin_manager import FakeUIRegistry


@pytest.fixture(autouse=True)
def _fresh_gate():
    gate_module.reset_gate_engine()
    yield
    gate_module.reset_gate_engine()


class World:
    """A real container, a session with a project, real settings, and a host over them."""

    def __init__(self, tmp_path: Path, qapp) -> None:
        self.services = build_service_container()
        self.settings = Settings(self.services.event_bus)
        self.session = SessionManager()
        self.project = ProjectModel()
        self.session.set_project(self.project)
        self.host = SynthesisHost(self.services, self.session, self.settings)

    def add(self, smiles: str, name: str = "target", select: bool = True):
        model = molecule(smiles, name)
        self.project.molecules.append(model)
        if select:
            self.session.select_molecule(model.uuid)
        return model


@pytest.fixture
def world(tmp_path, qapp):
    return World(tmp_path, qapp)


# --- the selected molecule ---------------------------------------------------------------------------------------------------------------------


def test_the_target_is_the_selected_molecule_as_it_is_drawn(world):
    assert world.host.target() is None  # nothing selected
    model = world.add(ASPIRIN, "Aspirin")
    target = world.host.target()
    assert (target.molecule_uuid, target.display_name, target.canonical_smiles) == (model.uuid, "Aspirin", model.canonical_smiles)


def test_there_is_no_target_without_a_project_a_selection_that_exists_or_a_structure(world):
    from openchem.domain.molecule import MoleculeModel

    world.session.select_molecule("not-in-the-project")
    assert world.host.target() is None
    blank = MoleculeModel(display_name="blank")
    world.project.molecules.append(blank)
    world.session.select_molecule(blank.uuid)
    assert world.host.target() is None  # nothing drawn to plan for
    assert world.host.structure_of(blank.uuid) is None and world.host.structure_of("not-in-the-project") is None
    world.session.set_project(None)
    assert world.host.target() is None


# --- asking: the gate has spoken before anything starts, whoever asked -----------------------------------------------------------------------------------


def test_a_plan_asked_for_through_the_host_is_refused_by_the_gate_and_starts_no_process(world, monkeypatch):
    from openchem.chem import aizynth_planner as planner_host

    started = []
    real_popen = planner_host.subprocess.Popen
    monkeypatch.setattr(planner_host.subprocess, "Popen", lambda *a, **k: started.append(a) or real_popen(*a, **k))
    model = world.add(SARIN, "refused target")

    outcome = world.host.request_plan(model.uuid, "the user")

    assert outcome is RequestOutcome.FINISHED and started == []
    bound = world.host.result_for(model.uuid)
    assert bound.is_current and bound.route_set.status is RouteStatus.REFUSED and world.host.is_planning(model.uuid) is False


def test_a_target_the_setup_cannot_serve_is_unavailable_after_the_gate_allowed_it(world):
    model = world.add(ASPIRIN)
    assert world.host.request_plan(model.uuid, "the user") is RequestOutcome.FINISHED  # the real container has no planner set up in this test
    assert world.host.result_for(model.uuid).route_set.status is RouteStatus.UNAVAILABLE


def test_an_unknown_molecule_or_a_container_without_a_service_is_rejected(world):
    assert world.host.request_plan("nobody", "the user") is RequestOutcome.REJECTED
    assert world.host.result_for("nobody") is None
    model = world.add(ASPIRIN)
    world.services.synthesis_planning_service = None
    assert world.host.request_plan(model.uuid, "the user") is RequestOutcome.REJECTED
    assert world.host.result_for(model.uuid) is None and world.host.is_planning(model.uuid) is False and world.host.cancel(model.uuid) is False


def test_the_plan_is_asked_for_in_the_name_of_whoever_the_caller_says(world):
    seen = []
    service = world.services.synthesis_planning_service
    original = service.request_plan
    service.request_plan = lambda molecule, requested_by="x": seen.append(requested_by) or original(molecule, requested_by=requested_by)
    model = world.add(ASPIRIN)
    world.host.request_plan(model.uuid, "the assistant")
    assert seen == ["the assistant"]


def test_a_running_search_is_seen_as_planning_and_a_cancel_stops_it(world):
    released = threading.Event()
    started = threading.Event()

    def blocking_runner(request, target, **kw):
        started.set()
        cancel = kw["cancel"]
        for _ in range(500):
            if cancel.is_set():
                break
            time.sleep(0.01)
        released.set()
        return RouteSet(status=RouteStatus.CANCELLED, target=target, planner=PlannerIdentity(planner="AiZynthFinder", version="4.4.1"), reason="cancelled", termination=SearchTermination.CANCELLED)

    from openchem.chem.aizynth_planner import PlannerSetup

    fake_setup = PlannerSetup(python="p", config={"stock": {"zinc": "z"}}, stock="zinc", expansion="uspto", filter=None, limits=setup.DEFAULT_LIMITS)
    world.services.synthesis_planning_service = SynthesisPlanningService(
        world.services.event_bus, setup_provider=lambda: fake_setup, runner=blocking_runner,
        gate=lambda smiles: GateDecision(outcome=GateOutcome.ALLOWED, ruleset_version="1", ruleset_sha256="x", screened_on="today"),
    )
    model = world.add(ASPIRIN)

    assert world.host.request_plan(model.uuid, "the user") is RequestOutcome.STARTED
    assert started.wait(10) and world.host.is_planning(model.uuid) is True
    assert world.host.request_plan(model.uuid, "the user") is RequestOutcome.ALREADY_RUNNING
    assert world.host.cancel(model.uuid) is True
    assert released.wait(10)
    for _ in range(200):
        qapp_events(world)
        if not world.host.is_planning(model.uuid):
            break
        time.sleep(0.01)
    assert world.host.is_planning(model.uuid) is False
    assert world.host.result_for(model.uuid).route_set.status is RouteStatus.CANCELLED
    world.services.synthesis_planning_service.shutdown()


def qapp_events(world):
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()


# --- what the planner offers, and the choices -------------------------------------------------------------------------------------------------------


def test_options_and_warmth_are_the_providers_and_an_absent_one_says_so(world):
    class Provider:
        def is_warm(self):
            return True

        def options(self):
            return PlannerOptions(ok=True, expansion=("uspto",), chosen_expansion="uspto")

    world.services.synthesis_setup = Provider()
    assert world.host.setup_is_warm() is True and world.host.options().chosen_expansion == "uspto"
    world.services.synthesis_setup = None
    assert world.host.setup_is_warm() is False
    absent = world.host.options()
    assert absent.ok is False and "no synthesis planner" in absent.problem


def test_a_choice_is_written_to_the_setting_the_planner_reads_and_no_filter_is_none(world):
    world.host.choose("expansion", "ring")
    world.host.choose("stock", "mine")
    world.host.choose("filter", "uspto")
    assert (world.settings.get(setup.EXPANSION_KEY), world.settings.get(setup.STOCK_KEY), world.settings.get(setup.FILTER_KEY)) == ("ring", "mine", "uspto")
    world.host.choose("filter", None)
    assert world.settings.get(setup.FILTER_KEY) == setup.NO_FILTER == "none"
    with pytest.raises(ValueError):
        world.host.choose("limits", "10")


def test_a_choice_made_through_the_host_is_what_the_next_setup_uses(world, tmp_path):
    from test_synthesis_planner_setup import files, inspection

    python = tmp_path / "python.exe"
    python.write_text("x", encoding="utf-8")
    config_file = tmp_path / "config.yml"
    config_file.write_text("x", encoding="utf-8")
    _, config = files(tmp_path)
    world.settings.set(setup.PYTHON_KEY, str(python))
    world.settings.set(setup.CONFIG_KEY, str(config_file))
    provider = setup.SetupProvider(world.settings, inspector=lambda p, c: inspection(expansion=("uspto", "ring"), stock=("zinc",), filters=("uspto",), config=config))
    config["expansion"]["ring"] = config["expansion"]["uspto"]
    world.host.choose("expansion", "ring")
    world.host.choose("filter", "uspto")
    chosen = provider()
    assert chosen is not None and (chosen.expansion, chosen.filter) == ("ring", "uspto")


def test_a_step_is_drawn_through_the_host_and_an_unreadable_one_raises(world):
    svg = world.host.depict(RouteStep(product=ASPIRIN, reactants=("CC(=O)OC(C)=O", "O=C(O)c1ccccc1O")))
    assert "<svg" in svg
    with pytest.raises(DepictionError):
        world.host.depict(RouteStep(product="not a smiles(", reactants=("CCO",)))


# --- the handles a plugin gets ----------------------------------------------------------------------------------------------------------------


def test_a_handle_without_a_host_answers_nothing_and_starts_nothing():
    reading, requests = PluginSynthesis(None), PluginSynthesisRequests(None)
    assert reading.available is False and reading.target() is None and reading.result_for("u") is None
    assert reading.is_planning("u") is False and reading.setup_is_warm() is False
    assert reading.options().ok is False and "did not provide" in reading.options().problem
    with pytest.raises(LookupError):
        reading.depict(RouteStep(product="CCO", reactants=("CC",)))
    assert requests.request_plan("u") is RequestOutcome.REJECTED and requests.cancel("u") is False
    requests.choose("expansion", "uspto")  # nothing to write to, and not an error


def test_the_reading_handle_has_no_way_to_start_stop_or_configure_a_plan():
    """The split that keeps a tool from starting a search: what a tool is handed is `synthesis`, and everything that acts is on the other object."""
    reading = {name for name in dir(PluginSynthesis) if not name.startswith("_")}
    acting = {name for name in dir(PluginSynthesisRequests) if not name.startswith("_")}
    assert reading == {"available", "depict", "is_planning", "options", "result_for", "setup_is_warm", "structure_of", "target"}
    assert acting == {"cancel", "choose", "request_plan"}
    assert reading.isdisjoint(acting)


def test_a_choice_must_name_one_of_the_three_selections_and_a_stock_or_policy_must_have_a_name():
    requests = PluginSynthesisRequests(None)
    assert CHOICES == ("expansion", "stock", "filter")
    for section in ("limits", "", "Stock"):
        with pytest.raises(ValueError, match="nothing to choose"):
            requests.choose(section, "x")
    for section in ("expansion", "stock"):
        for blank in (None, ""):
            with pytest.raises(ValueError, match="must be named"):
                requests.choose(section, blank)
    requests.choose("filter", None)  # no filter is a choice


def test_the_manager_gives_every_plugin_both_handles_over_one_host(tmp_path, qapp):
    class Host:
        def target(self):
            return None

        def is_planning(self, molecule_uuid):
            return True

    plugin_dir = tmp_path / "plugins" / "capture"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text("from openchem.plugins.interfaces import Plugin\n\nclass P(Plugin):\n    def activate(self, context):\n        pass\n    def deactivate(self):\n        pass\n\ndef create_plugin():\n    return P()\n", encoding="utf-8")
    (plugin_dir / "manifest.toml").write_text('plugin_id = "capture"\nversion = "0.1.0"\napi_version = 1\ndisplay_name = "Capture"\nauthor = "t"\ndescription = "d"\nhomepage = ""\nlicense = "GPL-3.0-or-later"\ndependencies = []\n', encoding="utf-8")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    manager = PluginManager(services, FakeUIRegistry(), settings, None, Host())
    manager.load_all()
    context = manager._loaded["capture"].context
    assert context.synthesis.available is True and context.synthesis.is_planning("u") is True

    bare = PluginManager(services, FakeUIRegistry(), settings)
    bare.load_all()
    assert bare._loaded["capture"].context.synthesis.available is False
