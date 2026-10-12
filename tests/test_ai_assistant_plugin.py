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
    # Regression test: the menu action used to only call panel-internal
    # focus/prefill methods, invisible when the panel is hidden behind
    # another tab -- confirmed live as "clicking the menu item does
    # nothing." Must reveal its own panel first.
    assert "AI Assistant" in ui.revealed_panels


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


def _entry(ui, label):
    return next(cb for lbl, cb in ui.menu_actions["ai_assistant"] if lbl == label)


def test_open_entry_reveals_the_panel_on_first_use_and_leaves_the_question_box_alone(tmp_path: Path, qapp):
    """The one entry whose name says "AI Assistant" -- the other two name what they do.
    Nothing has been opened or constructed beyond plugin load, so this is the
    first activation; it must still show the panel."""
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    panel = ui.panels["AI Assistant"]
    panel._input.setPlainText("half a question")
    _entry(ui, "Open AI Assistant")()

    assert "AI Assistant" in ui.revealed_panels
    assert panel._input.toPlainText() == "half a question"


def test_open_entry_is_the_first_one_listed(tmp_path: Path, qapp):
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()

    assert ui.menu_actions["ai_assistant"][0][0] == "Open AI Assistant"


def _panel_with_keychain(tmp_path, qapp, monkeypatch, stored: dict[str, str]):
    import openchem.plugins.context as context_module

    monkeypatch.setattr(context_module.keyring, "get_password", lambda _service, key: stored.get(key))
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    return ui.panels["AI Assistant"]


def test_a_provider_with_no_key_says_what_to_do_instead_of_a_blank_chat(tmp_path: Path, qapp, monkeypatch):
    panel = _panel_with_keychain(tmp_path, qapp, monkeypatch, stored={})
    panel._provider_combo.setCurrentText("anthropic")

    hint = panel.setup_hint()

    assert "anthropic" in hint and "Configure" in hint
    assert not panel._setup_hint.isHidden()
    assert panel._setup_hint.text() == hint


def test_the_hint_goes_away_once_a_key_is_stored(tmp_path: Path, qapp, monkeypatch):
    stored: dict[str, str] = {}
    panel = _panel_with_keychain(tmp_path, qapp, monkeypatch, stored)
    panel._provider_combo.setCurrentText("anthropic")
    assert panel.setup_hint()

    stored["anthropic_api_key"] = "sk-test"
    panel._refresh_setup_hint()

    assert panel.setup_hint() == ""
    assert panel._setup_hint.isHidden()


def test_providers_that_take_no_key_claim_nothing(tmp_path: Path, qapp, monkeypatch):
    """Ollama is a local server and claude_cli signs in through the CLI: neither can
    be checked without a call, and saying "no key" about them would be wrong."""
    panel = _panel_with_keychain(tmp_path, qapp, monkeypatch, stored={})

    for provider_id in ("ollama", "claude_cli"):
        panel._provider_combo.setCurrentText(provider_id)
        assert panel.setup_hint() == "", provider_id
        assert panel._setup_hint.isHidden(), provider_id


def test_an_unusable_keychain_is_treated_as_no_key_not_a_crash(tmp_path: Path, qapp, monkeypatch):
    import openchem.plugins.context as context_module

    def broken(_service, _key):
        raise RuntimeError("no keyring backend")

    monkeypatch.setattr(context_module.keyring, "get_password", broken)
    manager, services, ui = _make_manager(tmp_path)
    manager.load_all()
    panel = ui.panels["AI Assistant"]
    panel._provider_combo.setCurrentText("anthropic")

    assert "No API key" in panel.setup_hint()
