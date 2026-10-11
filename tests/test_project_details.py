"""Details in the Results project table computes what a molecule is missing.

The Batch panel's Details opened a molecule's results and, if the ticked properties had not been
computed for it, computed them first. The project table's Details only said nothing was
retained. What is guarded:

* what is missing is judged against the TABLE's own properties, at the molecule's CURRENT
  structure version, so an edited molecule's old results do not count;
* the one-molecule run uses the settings the table used, and never replaces the table;
* nothing runs when nothing is missing, or while another run is in progress.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QWidget

import conftest
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.ui.dialogs.batch_detail_dialog import BatchDetailDialog
from openchem.ui.panels.property_panel import _SCOPE_CHOSEN, PropertyPanel
from openchem.ui.widgets.results_workspace import ResultsWorkspace


@pytest.fixture
def services(qapp):
    return build_service_container()


@pytest.fixture
def project(services):
    project = ProjectModel(name="test")
    for name, smiles in (("aspirin", "CC(=O)Oc1ccccc1C(=O)O"), ("caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C")):
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


@pytest.fixture
def versions():
    """Per-molecule structure versions, movable by a test: staleness must be MOVED to be tested."""
    return {}


def _wait() -> None:
    QThreadPool.globalInstance().waitForDone(120000)
    QApplication.instance().processEvents()
    QApplication.instance().processEvents()


def _build(services, project, built, versions):
    panel = PropertyPanel(
        services.event_bus,
        services.calculator_registry,
        services.descriptor_service,
        services.chemistry_engine,
        structure_version_of=lambda uuid: versions.get(uuid, 0),
        batch_service=services.batch_service,
    )
    panel.set_project(project)
    workspace = ResultsWorkspace(
        QWidget(),
        services.calculator_registry,
        services.table_export_service,
        services.event_bus,
        services.chemistry_engine,
        project_of=lambda: project,
        structure_version_of=lambda uuid: versions.get(uuid, 0),
        batch_service=services.batch_service,
    )
    panel.project_run_started.connect(workspace.begin_project_run)
    built.extend([panel, workspace])
    return panel, workspace


def _run_on_first(panel, project, ids=("polar_surface_area",), parameters=None):
    for calculator_id in ids:
        panel._calculator_ticks[calculator_id].setChecked(True)
    panel._project_parameters.update(parameters or {})
    panel.set_scope(_SCOPE_CHOSEN, {project.molecules[0].uuid})
    panel._scope_descriptors.setChecked(False)
    panel._on_run_selected()
    _wait()


@pytest.fixture
def shown(monkeypatch):
    """The molecules whose Details dialog was opened, with the dialog itself never run."""
    opened = []

    def fake_exec(self):
        opened.append(self._molecule.uuid if hasattr(self, "_molecule") else None)
        return 0

    monkeypatch.setattr(BatchDetailDialog, "exec", fake_exec)
    return opened


def _held(services, workspace, molecule, versions):
    store = workspace.table_view._store
    return set(store.for_molecule(molecule.uuid, versions.get(molecule.uuid, 0))) if store else set()


def test_details_computes_what_the_table_has_for_every_other_molecule(services, project, built, versions, shown):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    other = project.molecules[1]
    assert "polar_surface_area" not in _held(services, workspace, other, versions)

    workspace._on_details_requested(other.uuid)
    _wait()

    assert "polar_surface_area" in _held(services, workspace, other, versions)
    assert len(shown) == 1


def test_the_one_molecule_run_does_not_replace_the_table(services, project, built, versions, shown):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    before = list(workspace.table_view.table().row_uuids)

    workspace._on_details_requested(project.molecules[1].uuid)
    _wait()

    assert workspace.table_view.table().row_uuids == before == [project.molecules[0].uuid]


def test_details_opens_only_after_the_computation_lands(services, project, built, versions, shown):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)

    workspace._on_details_requested(project.molecules[1].uuid)

    assert shown == [], "the dialog must wait for the numbers it is about to show"
    _wait()
    assert len(shown) == 1


def test_the_dialog_is_not_opened_inside_the_event_dispatch(services, project, built, versions, shown):
    """A modal opened inside a bus handler starves every LATER subscriber of the same event."""
    from openchem.domain.batch import CacheState
    from openchem.services.batch_service import BatchProgress

    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    seen_open_at_completion = []

    def later_subscriber(event):
        if event.state is CacheState.COMPLETED:
            seen_open_at_completion.append(len(shown))

    services.event_bus.subscribe(BatchProgress, later_subscriber)
    workspace._on_details_requested(project.molecules[1].uuid)
    _wait()

    assert seen_open_at_completion == [0], "the dialog was already open when a later subscriber ran"
    assert len(shown) == 1


def test_nothing_runs_when_nothing_is_missing(services, project, built, versions, shown, monkeypatch):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    asked = []
    monkeypatch.setattr(services.batch_service, "request_batch", lambda *a, **k: asked.append(a))

    workspace._on_details_requested(project.molecules[0].uuid)

    assert asked == [] and len(shown) == 1


def test_an_edited_molecules_old_results_do_not_count_as_computed(services, project, built, versions):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    first = project.molecules[0].uuid
    assert workspace._missing_for(first) == []

    versions[first] = 1

    assert workspace._missing_for(first) == ["polar_surface_area"]


def test_the_one_molecule_run_uses_the_settings_the_table_used(services, project, built, versions, shown, monkeypatch):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(
        panel, project, ids=("gasteiger_charge_at_ph",), parameters={"gasteiger_charge_at_ph": {"pH": 6.5}}
    )
    requests = []
    real = services.batch_service.request_batch
    monkeypatch.setattr(
        services.batch_service, "request_batch", lambda request, molecules: (requests.append(request), real(request, molecules))
    )

    workspace._on_details_requested(project.molecules[1].uuid)
    _wait()

    assert requests[0].parameters == {"gasteiger_charge_at_ph": {"pH": 6.5}}
    assert requests[0].molecule_uuids == [project.molecules[1].uuid]
    assert requests[0].calculator_ids == ["gasteiger_charge_at_ph"]


def test_it_computes_only_what_is_missing(services, project, built, versions, shown, monkeypatch):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project, ids=("polar_surface_area", "topology_analysis"))
    first = project.molecules[0].uuid
    workspace._table_view._store.results.pop(
        next(key for key in workspace._table_view._store.results if key.molecule_uuid == first and key.calculator_id == "topology_analysis")
    )
    requests = []
    monkeypatch.setattr(services.batch_service, "request_batch", lambda request, molecules: requests.append(request))

    workspace._on_details_requested(first)

    assert requests[0].calculator_ids == ["topology_analysis"]


def test_details_is_refused_while_another_run_is_in_progress(services, project, built, versions, shown, monkeypatch):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    asked = []
    monkeypatch.setattr(services.batch_service, "is_running", lambda: True)
    monkeypatch.setattr(services.batch_service, "request_batch", lambda *a, **k: asked.append(a))

    workspace._on_details_requested(project.molecules[1].uuid)

    assert asked == [] and shown == []
    assert "already in progress" in workspace.table_view._status.text()


def test_a_molecule_with_no_structure_just_opens(services, project, built, versions, shown, monkeypatch):
    panel, workspace = _build(services, project, built, versions)
    _run_on_first(panel, project)
    empty = MoleculeModel(display_name="empty")
    project.molecules.append(empty)
    asked = []
    monkeypatch.setattr(services.batch_service, "request_batch", lambda *a, **k: asked.append(a))

    workspace._on_details_requested(empty.uuid)

    assert asked == [] and len(shown) == 1


def test_without_a_service_details_never_tries_to_compute(services, project, built, versions, shown):
    panel, _ = _build(services, project, built, versions)
    workspace = ResultsWorkspace(
        QWidget(),
        services.calculator_registry,
        services.table_export_service,
        services.event_bus,
        services.chemistry_engine,
        project_of=lambda: project,
    )
    built.append(workspace)
    panel.project_run_started.connect(workspace.begin_project_run)
    _run_on_first(panel, project)

    workspace._on_details_requested(project.molecules[1].uuid)

    assert len(shown) == 1


def test_properties_and_catalogs_are_never_what_makes_details_run(services, project, built, versions, shown, monkeypatch):
    """The store holds calculator results only, so asking it about them would always say missing."""
    panel, workspace = _build(services, project, built, versions)
    for calculator_id in ("polar_surface_area",):
        panel._calculator_ticks[calculator_id].setChecked(True)
    panel.set_scope(_SCOPE_CHOSEN, {project.molecules[0].uuid})
    panel.set_descriptor_choice({"mol_wt"})
    panel.set_alert_choice({"pains"})
    panel._on_run_selected()
    _wait()
    asked = []
    monkeypatch.setattr(services.batch_service, "request_batch", lambda *a, **k: asked.append(a))

    workspace._on_details_requested(project.molecules[0].uuid)

    assert asked == [] and len(shown) == 1
