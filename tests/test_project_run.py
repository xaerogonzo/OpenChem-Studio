"""Running the ticked calculators on more than one molecule, from Properties.

The claim under test is PARITY: the project table that "Run selected" on several
molecules produces is the table the Batch panel produces for the same molecules,
calculators and settings -- cell for cell -- because both go through the one
`BatchService`. Everything else here is the wiring around that claim: the scope,
the immutable plan, the cost question, and what the Results dock does with the
table.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

import conftest
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.panels import property_panel as property_panel_module
from openchem.ui.panels.batch_panel import BatchPanel
from openchem.ui.panels.property_panel import (
    _SCOPE_ALL,
    _SCOPE_CHOSEN,
    _SCOPE_THIS,
    PropertyPanel,
)
from openchem.ui.widgets.results_workspace import ResultsWorkspace

_DRUGS = [
    ("aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("paracetamol", "CC(=O)Nc1ccc(O)cc1"),
]
_CALCULATORS = ["topology_analysis", "polar_surface_area"]


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def project(services):
    project = ProjectModel(name="test")
    for name, smiles in _DRUGS:
        molecule = MoleculeModel(display_name=name)
        services.chemistry_engine.set_structure_from_smiles(molecule, smiles)
        project.molecules.append(molecule)
    return project


@pytest.fixture
def built():
    widgets = []
    yield widgets
    for widget in widgets:
        conftest.dispose(widget)


def _properties(services, project, built, **kwargs) -> PropertyPanel:
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        services.chemistry_engine,
        structure_version_of=services.structure_check_service.current_version,
        batch_service=services.batch_service,
        **kwargs,
    )
    panel.set_project(project)
    built.append(panel)
    return panel


def _workspace(services, project, built) -> ResultsWorkspace:
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


def _wait() -> None:
    QThreadPool.globalInstance().waitForDone(120000)
    QApplication.instance().processEvents()


def _cells(table) -> dict:
    """What a cell SAYS, without its timestamps: value, text, kind and whether it failed."""
    return {
        key: (cell.value, cell.text, cell.kind, cell.failed)
        for key, cell in table.cells.items()
    }


def _run_from_properties(panel, workspace, ids, scope=_SCOPE_ALL, descriptors=False):
    panel.project_run_started.connect(workspace.begin_project_run)
    for calculator_id in ids:
        panel._calculator_ticks[calculator_id].setChecked(True)
    panel.set_scope(scope)
    panel._scope_descriptors.setChecked(descriptors)
    panel._on_run_selected()
    _wait()
    return workspace.table_view.table()


# --- parity -----------------------------------------------------------------------


def test_the_project_table_is_the_table_the_batch_panel_makes(services, project, built):
    batch = BatchPanel(
        services.batch_service,
        services.calculator_registry,
        services.table_export_service,
        services.event_bus,
        services.chemistry_engine,
    )
    batch.set_project(project)
    built.append(batch)
    for calculator_id in _CALCULATORS:
        batch.check(calculator_id)
    batch._run()
    _wait()
    expected = batch.table()
    assert expected is not None and expected.columns, "the baseline run produced nothing"

    panel = _properties(services, project, built)
    workspace = _workspace(services, project, built)
    actual = _run_from_properties(panel, workspace, _CALCULATORS)

    assert actual is not None
    assert actual.row_uuids == expected.row_uuids
    # The same columns and the same cells. ORDER is not part of the claim: the
    # Batch panel orders by its picker tree, Properties by the launcher's browse
    # order, and `test_the_columns_follow_the_launchers_order` pins the latter.
    assert {c.column_id for c in actual.columns} == {c.column_id for c in expected.columns}
    assert _cells(actual) == _cells(expected)


def test_the_columns_follow_the_launchers_order(services, project, built):
    from openchem.domain.calculator_taxonomy import calculator_browse_sort_key

    panel = _properties(services, project, built)
    workspace = _workspace(services, project, built)
    table = _run_from_properties(panel, workspace, ["topology_analysis", "polar_surface_area", "elemental_analysis"])
    sources = []
    for column in table.columns:
        if column.source_id not in sources:
            sources.append(column.source_id)
    expected = sorted(sources, key=lambda cid: calculator_browse_sort_key(services.calculator_registry.get(cid)))
    assert sources == expected


def test_with_the_always_on_properties_the_descriptor_columns_match_too(services, project, built):
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider

    batch = BatchPanel(
        services.batch_service,
        services.calculator_registry,
        services.table_export_service,
        services.event_bus,
        services.chemistry_engine,
    )
    batch.set_project(project)
    built.append(batch)
    for descriptor_id in RDKitDescriptorProvider().descriptor_ids():
        batch.check(descriptor_id)
    batch._run()
    _wait()
    expected = batch.table()

    panel = _properties(services, project, built)
    workspace = _workspace(services, project, built)
    actual = _run_from_properties(panel, workspace, ["topology_analysis"], descriptors=True)

    descriptor_columns = [c.column_id for c in expected.columns if c.source == "descriptor"]
    assert descriptor_columns, "the baseline has no descriptor columns"
    for column_id in descriptor_columns:
        for molecule_uuid in expected.row_uuids:
            a, b = actual.cell(molecule_uuid, column_id), expected.cell(molecule_uuid, column_id)
            assert (a.value, a.text, a.failed) == (b.value, b.text, b.failed), column_id


# --- the scope ----------------------------------------------------------------------


def test_this_molecule_is_still_the_default_and_runs_the_old_way(services, project, built):
    panel = _properties(services, project, built)
    assert panel._scope_mode == _SCOPE_THIS
    assert panel._scope_combo.currentData() == _SCOPE_THIS
    assert panel._scope_descriptors.isHidden()


def test_the_scope_names_molecules_in_project_order(services, project, built):
    panel = _properties(services, project, built)
    panel.set_scope(_SCOPE_ALL)
    assert [m.display_name for m in panel.scope_molecules()] == ["aspirin", "caffeine", "paracetamol"]
    chosen = {project.molecules[2].uuid, project.molecules[0].uuid}
    panel.set_scope(_SCOPE_CHOSEN, chosen)
    assert [m.display_name for m in panel.scope_molecules()] == ["aspirin", "paracetamol"]
    assert "(2)" in panel._scope_combo.itemText(2)


def test_a_chosen_set_forgets_a_molecule_the_project_no_longer_has(services, project, built):
    panel = _properties(services, project, built)
    panel.set_scope(_SCOPE_CHOSEN, {project.molecules[0].uuid, "gone"})
    other = ProjectModel(name="other")
    panel.set_project(other)
    assert panel._scope_chosen == set()


def test_a_panel_with_no_batch_service_is_unchanged(services, project, built):
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        services.chemistry_engine,
    )
    built.append(panel)
    assert panel._scope_combo.isHidden()


def test_only_the_chosen_molecules_get_rows(services, project, built):
    panel = _properties(services, project, built)
    workspace = _workspace(services, project, built)
    chosen = {project.molecules[0].uuid, project.molecules[1].uuid}
    panel.set_scope(_SCOPE_CHOSEN, chosen)
    table = _run_from_properties(panel, workspace, ["topology_analysis"], scope=_SCOPE_CHOSEN)
    assert set(table.row_uuids) == chosen


# --- the plan is immutable, the cost is stated ---------------------------------------


def test_a_run_is_what_it_was_when_it_was_submitted(services, project, built):
    panel = _properties(services, project, built)
    plans = []
    panel.project_run_started.connect(plans.append)
    panel._calculator_ticks["topology_analysis"].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    panel._scope_descriptors.setChecked(False)
    panel._on_run_selected()
    # Everything changes after the press...
    panel._calculator_ticks["polar_surface_area"].setChecked(True)
    panel.set_scope(_SCOPE_THIS)
    _wait()
    plan = plans[0]
    assert plan.calculator_ids == ("topology_analysis",)
    assert plan.molecule_count == 3


def test_a_large_run_states_its_size_and_cancel_computes_nothing(services, project, built, monkeypatch):
    panel = _properties(services, project, built)
    monkeypatch.setattr(property_panel_module, "_CONFIRM_PROJECT_RUN_ABOVE", 1)
    asked = []

    def _no(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_no))
    started = []
    panel.project_run_started.connect(started.append)
    panel._calculator_ticks["topology_analysis"].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    panel._on_run_selected()
    assert asked and "3 molecules" in asked[0] and "calculations" in asked[0]
    assert started == []
    assert "nothing was computed" in panel._batch_status.text()


def test_a_calculator_with_no_usable_default_is_left_out_and_named(services, project, built):
    panel = _properties(services, project, built)
    definition = next(
        d for d in services.calculator_registry._definitions.values()
        if any(p.required for p in d.parameters) and d.calculator_id in panel._calculator_ticks
    )
    panel._calculator_ticks[definition.calculator_id].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    panel._on_run_selected()
    assert "Nothing to run" in panel._batch_status.text()
    assert definition.display_name in panel._batch_status.text()


# --- the Results dock ---------------------------------------------------------------


def test_the_table_page_appears_only_once_a_project_run_makes_one(services, project, built):
    workspace = _workspace(services, project, built)
    assert workspace._switch.isHidden()
    assert not workspace.has_project_table()
    panel = _properties(services, project, built)
    _run_from_properties(panel, workspace, ["topology_analysis"])
    assert not workspace._switch.isHidden()
    assert workspace.showing_project_table()
    workspace.show_molecule_reader()
    assert not workspace.showing_project_table()
    assert workspace.has_project_table(), "going back to a molecule must not lose the table"


def test_a_run_nobody_told_the_workspace_about_does_not_replace_its_table(services, project, built):
    """A one-molecule details run from the Batch panel publishes the same event."""
    from openchem.domain.batch import BatchRequest

    panel = _properties(services, project, built)
    workspace = _workspace(services, project, built)
    table = _run_from_properties(panel, workspace, ["topology_analysis"])
    rows_before = list(table.row_uuids)
    services.batch_service.request_batch(
        BatchRequest(
            molecule_uuids=[project.molecules[0].uuid],
            calculator_ids=["polar_surface_area"],
        ),
        [project.molecules[0]],
    )
    _wait()
    assert workspace.table_view.table() is table
    assert list(workspace.table_view.table().row_uuids) == rows_before
    assert [c.column_id for c in workspace.table_view.table().columns] == [c.column_id for c in table.columns]


# --- presets ------------------------------------------------------------------------


def _with_settings(services, project, built, **stored):
    from openchem.app.settings import Settings

    settings = Settings(services.event_bus)
    for key, value in stored.items():
        settings.set(key.replace("__", "/"), value)
    return _properties(services, project, built, settings=settings), settings


def test_a_preset_ticks_exactly_its_calculators_and_replaces_the_current_ticks(services, project, built):
    panel, _settings = _with_settings(services, project, built)
    panel._calculator_ticks["elemental_analysis"].setChecked(True)
    panel._calculator_ticks["topology_analysis"].setChecked(True)
    panel._calculator_ticks["polar_surface_area"].setChecked(True)
    assert panel._presets.save("quick", ["topology_analysis", "polar_surface_area"])
    panel._calculator_ticks["elemental_analysis"].setChecked(True)
    panel._calculator_ticks["polar_surface_area"].setChecked(False)
    assert panel.apply_preset("quick") == 2
    assert sorted(panel._selected_calculator_ids()) == ["polar_surface_area", "topology_analysis"]


def test_the_presets_menu_lists_presets_a_to_z_and_offers_delete(services, project, built):
    panel, _settings = _with_settings(services, project, built)
    panel._presets.save("zeta", ["topology_analysis"])
    panel._presets.save("Alpha", ["polar_surface_area"])
    menu, actions = panel.build_presets_menu()
    # By text, not `a.menu()`: asking an action for its sub-menu hands back a
    # wrapper whose collection takes the sub-menu (and its actions) with it.
    labels = [a.text() for a in menu.actions() if a.text() and a.text() != "Delete preset"]
    assert labels == ["Save ticked as preset...", "Alpha", "zeta"]
    assert not actions["save"].isEnabled(), "nothing is ticked, so there is nothing to save"
    actions["delete:zeta"].trigger()
    assert panel._presets.names() == ["Alpha"]
    menu.deleteLater()


def test_the_batch_panels_selection_is_copied_in_as_a_preset_and_left_alone(services, project, built):
    from openchem.domain.selection_presets import IMPORTED_NAME, LEGACY_BATCH_KEY

    panel, settings = _with_settings(
        services, project, built, **{"batch__selected_property_ids": ["mol_wt", "topology_analysis", "retired_thing"]}
    )
    assert panel._presets.names() == [IMPORTED_NAME]
    assert panel.apply_preset(IMPORTED_NAME) == 1
    assert panel._selected_calculator_ids() == ["topology_analysis"]
    assert list(settings.get(LEGACY_BATCH_KEY)) == ["mol_wt", "topology_analysis", "retired_thing"]


def test_a_preset_never_ticks_what_the_launcher_is_not_offering(services, project, built):
    panel, _settings = _with_settings(services, project, built)
    hidden = next(iter(panel._hidden_calculator_ids), None)
    if hidden is None:
        pytest.skip("this build offers every calculator")
    panel._presets.save("with-hidden", [hidden, "topology_analysis"])
    assert panel.apply_preset("with-hidden") == 1
    assert hidden not in panel._selected_calculator_ids()


# --- what the Batch panel offered that a project run now carries -----------------------


def _capture(services, monkeypatch):
    seen = []
    monkeypatch.setattr(services.batch_service, "request_batch", lambda request, molecules: seen.append((request, molecules)))
    return seen


def test_the_per_atom_aggregate_reaches_the_request(services, project, built, monkeypatch):
    seen = _capture(services, monkeypatch)
    panel = _properties(services, project, built)
    panel._calculator_ticks["crippen_logp_contrib"].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    panel._scope_aggregate.setCurrentIndex(panel._scope_aggregate.findData("sum"))
    panel._on_run_selected()
    assert seen[0][0].per_atom_aggregate == "sum"


def test_the_default_aggregate_is_the_one_the_batch_panel_defaults_to(services, project, built, monkeypatch):
    seen = _capture(services, monkeypatch)
    panel = _properties(services, project, built)
    panel._calculator_ticks["topology_analysis"].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    panel._on_run_selected()
    from openchem.chem.result_reduction import PER_ATOM_AGGREGATES

    assert seen[0][0].per_atom_aggregate == PER_ATOM_AGGREGATES[0] == "mean"


def test_alerts_are_off_by_default_and_requested_when_asked_for(services, project, built, monkeypatch):
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider

    seen = _capture(services, monkeypatch)
    panel = _properties(services, project, built)
    panel._calculator_ticks["topology_analysis"].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    panel._scope_descriptors.setChecked(False)
    panel._on_run_selected()
    assert seen[-1][0].descriptor_ids == []
    panel._scope_alerts.setChecked(True)
    panel._on_run_selected()
    assert set(seen[-1][0].descriptor_ids) == set(RDKitDescriptorProvider().alert_ids())


def test_settings_chosen_for_project_runs_go_to_the_service_and_only_those(services, project, built, monkeypatch):
    seen = _capture(services, monkeypatch)
    panel = _properties(services, project, built)
    panel._calculator_ticks["topology_analysis"].setChecked(True)
    panel._calculator_ticks["polar_surface_area"].setChecked(True)
    panel.set_scope(_SCOPE_ALL)
    definition = services.calculator_registry.get("polar_surface_area")
    chosen = {p.name: p.default for p in definition.parameters}
    panel._project_parameters["polar_surface_area"] = chosen
    panel._on_run_selected()
    request = seen[-1][0]
    assert request.parameters == {"polar_surface_area": chosen}, "an untouched calculator must run on the service's defaults"


def test_the_settings_entry_is_offered_only_where_a_project_run_exists(services, project, built):
    with_service = _properties(services, project, built)
    menu = with_service._about_menu_for("polar_surface_area")
    assert "Settings for project runs..." in [a.text() for a in menu.actions()]
    menu.deleteLater()
    alone = PropertyPanel(
        services.event_bus, services.calculator_registry, services.descriptor_service, services.chemistry_engine
    )
    built.append(alone)
    menu = alone._about_menu_for("polar_surface_area")
    assert [a.text() for a in menu.actions()] == ["About this calculator"]
    menu.deleteLater()


def test_the_extra_project_controls_appear_with_a_project_scope_only(services, project, built):
    panel = _properties(services, project, built)
    controls = (panel._scope_descriptors, panel._scope_alerts, panel._scope_aggregate)
    assert all(c.isHidden() for c in controls)
    panel.set_scope(_SCOPE_ALL)
    assert not any(c.isHidden() for c in controls)
    panel.set_scope(_SCOPE_THIS)
    assert all(c.isHidden() for c in controls)


# --- cancelling ------------------------------------------------------------------------


def test_the_results_page_has_its_own_cancel_and_the_batch_panels_view_does_not(services, project, built):
    workspace = _workspace(services, project, built)
    assert workspace.table_view._show_cancel is True
    batch = BatchPanel(
        services.batch_service, services.calculator_registry, services.table_export_service,
        services.event_bus, services.chemistry_engine,
    )
    built.append(batch)
    assert batch._view._show_cancel is False


def test_cancel_on_the_results_page_asks_the_service_to_stop(services, project, built, monkeypatch):
    workspace = ResultsWorkspace(
        QWidget(), services.calculator_registry, services.table_export_service, services.event_bus,
        services.chemistry_engine, batch_service=services.batch_service,
    )
    built.append(workspace)
    cancelled = []
    monkeypatch.setattr(services.batch_service, "cancel", lambda: cancelled.append(True) or True)
    workspace.table_view._cancel_button.click()
    assert cancelled == [True]
