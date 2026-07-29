from __future__ import annotations

from pathlib import Path

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.events.events import DescriptorComputed, MoleculeSelected, MoleculeSnapshotUpdated
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


def test_ai_assistant_loads_and_registers_everything(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    assert "ai_assistant" in manager.loaded_plugin_ids
    assert "AI Assistant" in ui.panels
    labels = [label for label, _ in ui.menu_actions["ai_assistant"]]
    assert "Explain Selected Molecule" in labels
    assert "Generate Molecule Report" in labels


def test_menu_action_with_no_molecule_selected_shows_placeholder(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    panel = ui.panels["AI Assistant"]
    _, callback = next(
        (label, cb) for label, cb in ui.menu_actions["ai_assistant"] if label == "Explain Selected Molecule"
    )
    callback()

    assert "No molecule" in panel._input.toPlainText()


def test_menu_action_prefills_from_cached_context(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    services.event_bus.publish(MoleculeSelected(molecule_uuid="mol-1"))
    services.event_bus.publish(
        MoleculeSnapshotUpdated(
            molecule_uuid="mol-1",
            display_name="Ibuprofen",
            canonical_smiles="CC(C)Cc1ccc(cc1)C(C)C(=O)O",
            inchi=None,
            inchikey=None,
            conformer_count=0,
            lowest_conformer_energy=None,
        )
    )
    services.event_bus.publish(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="mol_wt",
                name="Molecular Weight",
                units="g/mol",
                category="physicochemical",
                provider="rdkit",
                molecule_uuid="mol-1",
                value=206.28,
                cache_state=CacheState.COMPLETED,
            )
        )
    )

    panel = ui.panels["AI Assistant"]
    _, explain_callback = next(
        (label, cb) for label, cb in ui.menu_actions["ai_assistant"] if label == "Explain Selected Molecule"
    )
    explain_callback()
    assert "Ibuprofen" in panel._input.toPlainText()

    _, report_callback = next(
        (label, cb) for label, cb in ui.menu_actions["ai_assistant"] if label == "Generate Molecule Report"
    )
    report_callback()
    assert "Ibuprofen" in panel._input.toPlainText()
    assert "markdown report" in panel._input.toPlainText()


def test_unload_reverses_panel_and_menu_registration(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    assert "AI Assistant" in ui.panels

    manager.unload("ai_assistant")

    assert "AI Assistant" not in ui.panels
    assert "ai_assistant" not in ui.menu_actions
