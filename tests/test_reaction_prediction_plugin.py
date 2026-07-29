from __future__ import annotations

from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.events.events import MoleculeSelected, MoleculeSnapshotUpdated
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


def test_reaction_prediction_loads_and_registers_everything(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    assert "reaction_prediction" in manager.loaded_plugin_ids
    assert "Reaction Prediction" in ui.panels
    labels = [label for label, _ in ui.menu_actions["reaction_prediction"]]
    assert "Predict Reaction Products" in labels


def test_menu_action_prefills_reactant_from_selection(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    services.event_bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
    services.event_bus.publish(
        MoleculeSnapshotUpdated(
            molecule_uuid="mol-1",
            display_name="Ethanol",
            canonical_smiles="CCO",
            inchi=None,
            inchikey=None,
            conformer_count=0,
            lowest_conformer_energy=None,
        )
    )

    panel = ui.panels["Reaction Prediction"]
    _, callback = next(
        (label, cb)
        for label, cb in ui.menu_actions["reaction_prediction"]
        if label == "Predict Reaction Products"
    )
    callback()

    assert panel._reactant1_edit.text() == "CCO"


def test_menu_action_with_no_selection_does_not_crash(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    _, callback = next(
        (label, cb)
        for label, cb in ui.menu_actions["reaction_prediction"]
        if label == "Predict Reaction Products"
    )
    callback()  # must not raise


def test_predict_and_import_end_to_end(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["Reaction Prediction"]

    panel._reactant1_edit.setText("CC(=O)O")
    panel._reactant2_edit.setText("CCO")
    panel._method_combo.setCurrentText("Templates")
    panel._on_predict_clicked()

    for _ in range(50):
        qapp.processEvents()
        if panel._table.rowCount() > 0 or panel._status_label.text().startswith("Error"):
            break

    assert panel._table.rowCount() == 1
    assert panel._table.item(0, 0).text() == "CCOC(C)=O"

    panel._table.selectRow(0)
    panel._on_import_clicked()

    assert len(ui.added_molecules) == 1
    assert ui.added_molecules[0].canonical_smiles == "CCOC(C)=O"


def test_unload_reverses_panel_and_menu_registration(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    assert "Reaction Prediction" in ui.panels

    manager.unload("reaction_prediction")

    assert "Reaction Prediction" not in ui.panels
    assert "reaction_prediction" not in ui.menu_actions
