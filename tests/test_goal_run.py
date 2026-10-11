"""Running a goal from Properties and from the window.

`PropertyPanel.run_goal` is what both the heading buttons and the wizard call. What is guarded:

* **it touches nothing the person set**: no tick, no preset, no scope control;
* **it resolves "this molecule" when it runs**, not when the wizard was opened;
* **it takes the same routes as "Run selected"**: the same plan, the same one-molecule path,
  the same project table;
* **each task group's heading has a "Run recommended" button** (and the fallback group has
  none), which runs that goal's recommended set on the scope Properties has;
* **there is one wizard**, raised when asked for again.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

import conftest
from openchem.bootstrap import build_service_container
from openchem.domain.calculator import CalculationRequest
from openchem.domain.calculator_goals import (
    GOALS,
    SCOPE_ALL,
    SCOPE_CHOSEN,
    SCOPE_THIS,
    GoalRun,
    goal_of,
)
from openchem.domain.calculator_taxonomy import FALLBACK_TASK_GROUP
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.events import MoleculeSelected
from openchem.ui.panels.property_panel import PropertyPanel
from openchem.ui.widgets.results_workspace import ResultsWorkspace


class _RecordingService:
    """Takes `run_calculator` calls and does nothing, so the test reads what was asked."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, CalculationRequest]] = []

    def run_calculator(self, model, request: CalculationRequest) -> None:
        self.calls.append((model.uuid, request))

    def preflight(self, _model, _calculator_id: str) -> str:
        return ""

    def ids(self) -> list[str]:
        return [request.calculator_id for _uuid, request in self.calls]


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _molecules(services, *names_and_smiles):
    molecules = []
    for name, smiles in names_and_smiles:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        molecules.append(molecule)
    return molecules


def _panel(services, built, molecules, *, with_batch=True):
    recorder = _RecordingService()
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        recorder,
        services.chemistry_engine,
        structure_version_of=services.structure_check_service.current_version,
        batch_service=services.batch_service if with_batch else None,
        settings=None,
    )
    panel.set_project(ProjectModel(name="p", molecules=molecules))
    if molecules:
        services.event_bus.publish(MoleculeSelected(molecule_uuid=molecules[0].uuid))
    # Selecting a molecule starts the always-on calculators through the same service; what the
    # tests read is what the GOAL asked for, so the selection's own runs are set aside.
    recorder.calls.clear()
    panel._running_calculator_ids.clear()
    built.append(panel)
    return panel, recorder


def _run(goal_id, *, ids=None, scope=SCOPE_THIS, uuids=(), parameters=None):
    goal = goal_of(goal_id)
    return GoalRun(
        goal_id=goal_id,
        calculator_ids=ids if ids is not None else goal.recommended_ids(),
        parameters=parameters or {},
        scope_mode=scope,
        scope_uuids=uuids,
    )


def _wait() -> None:
    QThreadPool.globalInstance().waitForDone(120000)
    QApplication.instance().processEvents()


# --- one molecule -------------------------------------------------------------------------------


def test_a_goal_runs_its_calculators_on_the_selected_molecule(services, built):
    molecules = _molecules(services, ("A", "CCO"))
    panel, recorder = _panel(services, built, molecules)

    text = panel.run_goal(_run("identity"))

    assert recorder.ids() == list(goal_of("identity").recommended_ids())
    assert {uuid for uuid, _r in recorder.calls} == {molecules[0].uuid}
    assert "Identity and naming" in text and text.startswith("Running")
    assert panel._batch_status.text() == text


def test_a_goal_run_uses_registered_defaults_unless_the_run_says_otherwise(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")))
    definition = services.calculator_registry.get("gasteiger_charge_at_ph")

    panel.run_goal(_run("charge", ids=("gasteiger_charge_at_ph", "dipole_moment")))
    first = {r.calculator_id: dict(r.parameters) for _u, r in recorder.calls}
    assert first["gasteiger_charge_at_ph"] == {p.name: p.default for p in definition.parameters}

    recorder.calls.clear()
    panel._running_calculator_ids.clear()
    panel.run_goal(
        _run("charge", ids=("gasteiger_charge_at_ph",), parameters={"gasteiger_charge_at_ph": {"pH": 6.5}})
    )
    assert dict(recorder.calls[0][1].parameters) == {"pH": 6.5}


def test_a_goal_run_changes_no_tick_no_preset_and_not_the_scope_control(services, built):
    panel, _recorder = _panel(services, built, _molecules(services, ("A", "CCO")))
    ticks_before = {cid: tick.isChecked() for cid, tick in panel._calculator_ticks.items()}
    presets_before = list(panel._presets.names())
    scope_before = panel.current_scope()

    panel.run_goal(_run("identity"))
    panel.run_goal(_run("solubility", scope=SCOPE_ALL))

    assert {cid: tick.isChecked() for cid, tick in panel._calculator_ticks.items()} == ticks_before
    assert list(panel._presets.names()) == presets_before
    assert panel.current_scope() == scope_before


def test_this_molecule_is_read_when_the_run_happens(services, built):
    """A run built while A was selected runs on B once B is selected: the wizard never resolved it."""
    molecules = _molecules(services, ("A", "CCO"), ("B", "CCN"))
    panel, recorder = _panel(services, built, molecules)
    run = _run("identity", ids=("elemental_analysis",))

    services.event_bus.publish(MoleculeSelected(molecule_uuid=molecules[1].uuid))
    panel.run_goal(run)

    assert {uuid for uuid, _r in recorder.calls} == {molecules[1].uuid}


def test_a_calculator_already_running_is_not_started_twice(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")))
    run = _run("identity", ids=("elemental_analysis",))

    panel.run_goal(run)
    text = panel.run_goal(run)

    assert recorder.ids() == ["elemental_analysis"]
    assert "already running" in text


def test_nothing_selected_is_said_not_run(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")))
    panel._selected_molecule_uuid = None

    text = panel.run_goal(_run("identity"))

    assert text == "Select a molecule first." and recorder.calls == []


def test_no_project_is_said_not_run(services, built):
    panel, recorder = _panel(services, built, [])
    panel._project = None

    assert panel.run_goal(_run("identity")) == "Open or create a project first."
    assert recorder.calls == []


def test_a_molecule_with_no_structure_is_said_not_run(services, built):
    empty = MoleculeModel(display_name="New molecule")
    panel, recorder = _panel(services, built, [empty])

    text = panel.run_goal(_run("identity"))

    assert "no structure yet" in text and recorder.calls == []


def test_a_goal_with_only_unrunnable_calculators_says_so(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")))

    text = panel.run_goal(_run("identity", ids=("orca.sp", "no_such_id")))

    assert text.startswith("Nothing to run.") and recorder.calls == []


def test_a_calculator_that_needs_input_is_left_out_and_named(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")))

    text = panel.run_goal(_run("identity", ids=("elemental_analysis", "lewis_adduct")))

    assert recorder.ids() == ["elemental_analysis"]
    assert "Lewis Adduct" in text and "needs" in text


# --- several molecules ------------------------------------------------------------------------------


def _workspace(services, built, project):
    workspace = ResultsWorkspace(
        QWidget(),
        services.calculator_registry,
        services.table_export_service,
        services.event_bus,
        services.chemistry_engine,
        project_of=lambda: project,
        structure_version_of=services.structure_check_service.current_version,
    )
    built.append(workspace)
    return workspace


def test_a_goal_over_several_molecules_fills_the_project_table(services, built):
    molecules = _molecules(services, ("A", "CCO"), ("B", "CCN"))
    panel, _recorder = _panel(services, built, molecules)
    workspace = _workspace(services, built, panel._project)
    panel.project_run_started.connect(workspace.begin_project_run)

    text = panel.run_goal(_run("identity", ids=("elemental_analysis",), scope=SCOPE_ALL))
    _wait()

    assert "'Identity and naming'" in text and "2 molecule(s)" in text
    table = workspace.table_view.table()
    assert table is not None and len(table.row_uuids) == 2 and table.columns


def test_a_chosen_scope_runs_only_the_chosen_and_drops_a_molecule_that_is_gone(services, built):
    molecules = _molecules(services, ("A", "CCO"), ("B", "CCN"), ("C", "CCC"))
    panel, _recorder = _panel(services, built, molecules)
    plans = []
    panel.project_run_started.connect(plans.append)

    panel.run_goal(
        _run("identity", ids=("elemental_analysis",), scope=SCOPE_CHOSEN, uuids=(molecules[2].uuid, "gone"))
    )
    _wait()

    assert plans[0].molecule_uuids == (molecules[2].uuid,)


def test_a_project_run_is_refused_while_another_is_going(services, built):
    molecules = _molecules(services, ("A", "CCO"))
    panel, _recorder = _panel(services, built, molecules)
    panel._batch_service.is_running = lambda: True

    text = panel.run_goal(_run("identity", ids=("elemental_analysis",), scope=SCOPE_ALL))

    assert "already going" in text


def test_several_molecules_without_a_batch_service_is_said_not_attempted(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")), with_batch=False)

    text = panel.run_goal(_run("identity", ids=("elemental_analysis",), scope=SCOPE_ALL))

    assert "not available" in text and recorder.calls == []


# --- the headings ----------------------------------------------------------------------------------------


def _heading_button(panel, group):
    header = panel._group_headers.get(group)
    return header.findChild(QPushButton) if header is not None else None


def test_every_group_with_a_goal_has_a_run_recommended_button_and_the_fallback_has_none(services, built):
    panel, _recorder = _panel(services, built, _molecules(services, ("A", "CCO")))

    for goal in GOALS:
        assert _heading_button(panel, goal.goal_id) is not None, goal.goal_id
    # The fallback heading may not exist for this registry, so ask the method itself.
    from PySide6.QtWidgets import QLabel

    header = QLabel("Other calculators")
    built.append(header)
    panel._add_run_recommended(header, FALLBACK_TASK_GROUP)
    assert header.findChild(QPushButton) is None


def test_a_heading_button_runs_that_goals_recommended_set(services, built):
    panel, recorder = _panel(services, built, _molecules(services, ("A", "CCO")))

    _heading_button(panel, "druglike").click()

    # The plan orders by the registry, not by the goal's list, so compare what ran.
    assert sorted(recorder.ids()) == sorted(goal_of("druglike").recommended_ids())


def test_a_heading_button_uses_the_scope_properties_has(services, built):
    molecules = _molecules(services, ("A", "CCO"), ("B", "CCN"))
    panel, recorder = _panel(services, built, molecules)
    plans = []
    panel.project_run_started.connect(plans.append)
    panel.set_scope(SCOPE_ALL)

    _heading_button(panel, "identity").click()
    _wait()

    assert recorder.calls == [], "a project run does not go down the one-molecule path"
    assert plans and plans[0].molecule_count == 2


def test_a_heading_button_is_as_tall_as_its_text_needs(services, built):
    """Measured at 3x: a layout margin on top of the label's own cut the bottom off every letter."""
    panel, _recorder = _panel(services, built, _molecules(services, ("A", "CCO")))
    panel.resize(420, 900)
    panel.show()
    QApplication.instance().processEvents()

    button = _heading_button(panel, "identity")
    assert button.height() >= button.sizeHint().height(), (button.height(), button.sizeHint())
    assert button.height() >= button.fontMetrics().height()


def test_a_heading_buttons_tooltip_names_what_it_will_run(services, built):
    panel, _recorder = _panel(services, built, _molecules(services, ("A", "CCO")))

    tip = _heading_button(panel, "solubility").toolTip()

    for calculator_id in goal_of("solubility").recommended_ids():
        assert services.calculator_registry.get(calculator_id).display_name in tip


def test_the_heading_button_is_hidden_with_its_heading(services, built):
    panel, _recorder = _panel(services, built, _molecules(services, ("A", "CCO")))

    panel._find_box.setText("zzz-nothing-matches")
    try:
        assert panel._group_headers["identity"].isHidden()
    finally:
        panel._find_box.setText("")


def test_the_run_by_goal_button_asks_for_the_wizard(services, built):
    panel, _recorder = _panel(services, built, _molecules(services, ("A", "CCO")))
    asked = []
    panel.goal_wizard_requested.connect(lambda: asked.append(1))

    panel._goals_button.click()

    assert asked == [1]


# --- the window ----------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings

    directory = tmp_path_factory.mktemp("goal_wizard")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


def test_there_is_one_wizard_and_asking_again_raises_it(main_window):
    first = main_window.show_goal_wizard()
    second = main_window.show_goal_wizard()

    assert first is second
    assert not first.isHidden()


def test_asking_for_a_goal_selects_it_without_resetting_an_open_wizard(main_window):
    wizard = main_window.show_goal_wizard("charge")
    assert wizard.goal.goal_id == "charge"

    again = main_window.show_goal_wizard("druglike")

    assert again is wizard and wizard.goal.goal_id == "druglike"


def test_the_tools_menu_and_the_properties_button_open_the_same_wizard(main_window):
    wizard = main_window.show_goal_wizard()
    wizard.hide()

    main_window._property_panel._goals_button.click()
    assert main_window._goal_wizard is wizard and not wizard.isHidden()

    wizard.hide()
    action = next(
        a for menu in main_window.menuBar().findChildren(type(main_window.menuBar().addMenu("x"))) for a in menu.actions()
        if a.text() == "Run Calculators by Goal..."
    )
    action.trigger()
    assert main_window._goal_wizard is wizard and not wizard.isHidden()


def test_a_run_asked_for_in_the_wizard_runs_in_properties_and_the_wizard_says_so(main_window):
    recorder = _RecordingService()
    panel = main_window._property_panel
    panel._descriptor_service = recorder
    project = main_window._session.project
    molecule = MoleculeModel(display_name="Ethanol")
    main_window._services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    project.molecules.append(molecule)
    main_window._services.event_bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    recorder.calls.clear()
    panel._running_calculator_ids.clear()
    wizard = main_window.show_goal_wizard("identity")
    wizard.set_scope(SCOPE_THIS)

    wizard._run_recommended_button.click()

    assert sorted(recorder.ids()) == sorted(goal_of("identity").recommended_ids())
    assert wizard._status.text() == panel._batch_status.text() != ""
    assert not any(tick.isChecked() for tick in panel._calculator_ticks.values())


def test_the_wizard_starts_from_the_scope_properties_has(main_window):
    main_window._goal_wizard = None
    main_window._property_panel.set_scope(SCOPE_ALL)
    try:
        wizard = main_window.show_goal_wizard()
        assert wizard._scope_mode == SCOPE_ALL
    finally:
        main_window._property_panel.set_scope(SCOPE_THIS)
