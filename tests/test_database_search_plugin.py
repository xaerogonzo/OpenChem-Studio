from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.plugins.manager import PluginManager
from test_plugin_manager import FakeUIRegistry

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


def _make_manager(tmp_path: Path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(PLUGINS_DIR))
    settings.set("plugins/user_directory", str(tmp_path / "unused_user_plugins"))
    ui = FakeUIRegistry()
    manager = PluginManager(services, ui, settings)
    return manager, services, ui


def test_database_search_loads_and_registers_everything(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    assert "database_search" in manager.loaded_plugin_ids
    assert "Database Search" in ui.panels
    labels = [label for label, _ in ui.menu_actions["database_search"]]
    assert "Search Chemical Databases" in labels


def test_import_search_result_adds_molecule_via_context(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    panel = ui.panels["Database Search"]
    from database_search.providers import SearchResult

    panel._results = [
        SearchResult(
            source="PubChem",
            external_id="2244",
            name="Aspirin",
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            molecular_formula="C9H8O4",
            molecular_weight=180.16,
        )
    ]
    panel._table.setRowCount(1)
    panel._table.selectRow(0)

    panel._on_import_clicked()

    assert len(ui.added_molecules) == 1
    added = ui.added_molecules[0]
    assert added.display_name == "Aspirin"
    assert added.canonical_smiles is not None
    assert added.molblock is not None


def test_search_task_runs_provider_off_thread(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["Database Search"]

    from database_search.providers import SearchResult

    fake_result = SearchResult(
        source="PubChem",
        external_id="1",
        name="Water",
        smiles="O",
        molecular_formula="H2O",
        molecular_weight=18.02,
    )
    with patch.object(
        panel._providers["PubChem"], "search", return_value=[fake_result]
    ):
        panel._query_edit.setText("water")
        panel._on_search_clicked()
        # QThreadPool tasks run asynchronously; process events until the
        # signal-connected slot has updated the table. A plain processEvents()
        # busy-loop with no sleep can spin faster than the worker thread gets
        # scheduled, especially under load (confirmed flaky) -- the small
        # sleep gives the OS scheduler an actual chance to run it.
        import time as _time

        for _ in range(200):
            qapp.processEvents()
            if panel._table.rowCount() > 0 or panel._status_label.text().startswith("Error"):
                break
            _time.sleep(0.01)

    assert panel._table.rowCount() == 1
    assert panel._table.item(0, 2).text() == "Water"


def test_unload_reverses_panel_and_menu_registration(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    assert "Database Search" in ui.panels

    manager.unload("database_search")

    assert "Database Search" not in ui.panels
    assert "database_search" not in ui.menu_actions
