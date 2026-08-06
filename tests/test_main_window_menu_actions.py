from __future__ import annotations

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel


def test_add_menu_action_callback_receives_no_arguments(qapp, tmp_path):
    """Regression test: QAction.triggered emits `triggered(checked: bool)`.
    Connecting it directly to a plugin-supplied callback would silently pass
    that bool through as a positional argument, clobbering a lambda default
    like `lambda aid=action_id: ...` instead of raising. `add_menu_action`
    must shield callers from this so `UIRegistry`'s zero-arg `callback`
    contract genuinely holds when a real QAction fires.
    """
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    window = MainWindow(services, settings, session)

    received: list[object] = []

    # Shaped exactly like the real callback plugins get from
    # `_MenuRegistrar.register` (context.py): a callable with one
    # *optional* positional parameter carrying the real payload as its
    # default. Qt's signal/slot introspection calls a connected callable
    # with min(signal_arg_count, slot_arity) arguments -- for a genuinely
    # zero-arg callable it correctly passes nothing, but for a one-optional-
    # arg callable like this it fills that slot with the emitted
    # `triggered(bool)`, clobbering the default unless add_menu_action
    # shields it.
    def callback(action_id: str = "expected_action_id") -> None:
        received.append(action_id)

    window.add_menu_action("test_plugin", "Do Thing", callback)
    action = next(a for a in window._plugins_menu.actions() if a.text() == "Do Thing")
    action.trigger()

    assert received == ["expected_action_id"]

    window.remove_menu_actions("test_plugin")
    assert not any(a.text() == "Do Thing" for a in window._plugins_menu.actions())


def _build_window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    return MainWindow(services, settings, session)


def _structure_display_menu(window):
    return next(
        m for m in window._view_menu.findChildren(type(window._view_menu)) if m.title() == "2D Structure Display"
    )


def test_structure_display_submenu_toggles_proxy_to_the_editor(qapp, tmp_path):
    """Regression/coverage test for Phase 17b: the View menu's "2D Structure
    Display" toggles must reach KetcherEditorBackend's confirmed-live
    `set_render_option`, not just exist as inert menu chrome."""
    window = _build_window(tmp_path)
    calls: list[tuple[str, object]] = []
    window._editor.set_render_option = lambda name, value: calls.append((name, value))

    carbon_action = next(a for a in _structure_display_menu(window).actions() if a.text() == "Show Carbon Labels")

    carbon_action.trigger()
    assert calls == [("carbonExplicitly", True)]

    carbon_action.trigger()
    assert calls == [("carbonExplicitly", True), ("carbonExplicitly", False)]


def test_structure_display_submenu_actions_proxy_to_the_real_ketcher_buttons(qapp, tmp_path):
    """Regression test for the Phase 17 audit correction: "Toggle Explicit
    Hydrogens" and "Open 3D Viewer (Miew)..." must reach Ketcher's own
    real toolbar buttons via `trigger_toolbar_action`, not the ineffective
    `showHydrogenLabels` render option this replaced."""
    window = _build_window(tmp_path)
    calls: list[str] = []
    window._editor.trigger_toolbar_action = lambda action_id: calls.append(action_id)

    menu = _structure_display_menu(window)
    hydrogens_action = next(a for a in menu.actions() if a.text() == "Toggle Explicit Hydrogens")
    miew_action = next(a for a in menu.actions() if a.text() == "Open 3D Viewer (Miew)...")

    hydrogens_action.trigger()
    miew_action.trigger()

    assert calls == ["Add/Remove explicit hydrogens button", "3D Viewer button"]


def test_edit_menu_structure_actions_proxy_to_the_real_ketcher_buttons(qapp, tmp_path):
    """Regression test for the follow-up bridges: Aromatize/Dearomatize/
    Layout/Clean Up/Calculate CIP/Check Structure all go through the same
    confirmed-live `trigger_toolbar_action` mechanism as the explicit-
    hydrogens/3D-viewer actions, not a reimplementation."""
    window = _build_window(tmp_path)
    calls: list[str] = []
    window._editor.trigger_toolbar_action = lambda action_id: calls.append(action_id)

    edit_menu = next(m for m in window.menuBar().findChildren(type(window._view_menu)) if m.title() == "&Edit")
    expected = {
        "Aromatize": "Aromatize button",
        "Dearomatize": "Dearomatize button",
        "Layout (Recalculate Coordinates)": "Layout button",
        "Clean Up": "Clean Up button",
        "Calculate CIP (Stereo Descriptors)": "Calculate CIP button",
        "Check Structure in the Editor (Indigo)...": "Check Structure button",
    }
    for label, test_id in expected.items():
        action = next(a for a in edit_menu.actions() if a.text() == label)
        action.trigger()
        assert calls[-1] == test_id


def test_the_two_structure_checkers_are_distinct_menu_entries(qapp, tmp_path):
    """There are two opinions about a structure and they disagree on purpose.

    Ketcher's is Indigo's, and it is the one the CANVAS draws in red -- so
    it stays reachable. Ours is the panel, which accepts iron oxides and
    hypervalent iodine that Indigo flags. Sharing one menu label would make
    the disagreement look like a bug in whichever one you opened.
    """
    window = _build_window(tmp_path)
    molecule = MoleculeModel(display_name="Aspirin")
    window._services.chemistry_engine.set_structure_from_smiles(molecule, "CC(=O)Oc1ccccc1C(=O)O")
    window.add_molecule(molecule)
    calls: list[str] = []
    window._editor.trigger_toolbar_action = lambda action_id: calls.append(action_id)

    edit_menu = next(m for m in window.menuBar().findChildren(type(window._view_menu)) if m.title() == "&Edit")
    ours = next(a for a in edit_menu.actions() if a.text() == "Check Structure...")
    ours.trigger()

    assert calls == [], "the app's own checker must not proxy to Ketcher's"
    # It ran a check of its own. `isVisible()` would prove nothing here --
    # the test window is never shown, so every dock in it reports False.
    assert window._structure_check_panel._molblock == molecule.molblock


def test_send_to_3d_viewer_switches_the_center_tab(qapp, tmp_path):
    window = _build_window(tmp_path)
    molecule = MoleculeModel(display_name="Aspirin")
    window._services.chemistry_engine.set_structure_from_smiles(molecule, "CC(=O)Oc1ccccc1C(=O)O")
    window.add_molecule(molecule)

    generate_calls = []
    window._services.conformer_service.request_conformers = (
        lambda model, count, optimize: generate_calls.append((model.uuid, count, optimize))
    )

    window._send_to_3d_viewer()

    assert window._center_tabs.currentWidget() is window._viewer3d
    assert generate_calls == [(molecule.uuid, 10, True)]  # no conformer yet -- one gets requested


def test_send_to_3d_viewer_does_not_regenerate_when_a_conformer_already_exists(qapp, tmp_path):
    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.domain.conformer import ConformerModel

    window = _build_window(tmp_path)
    molecule = MoleculeModel(display_name="Ethanol")
    window._services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    conf_mol, energy = RDKitConformerProvider().generate_conformers(
        window._services.chemistry_engine.mol_from_model(molecule), num_conformers=1, optimize=False
    )[0]
    molecule.conformers = [
        ConformerModel(molblock=window._services.chemistry_engine.mol_to_molblock(conf_mol), energy=energy)
    ]
    window.add_molecule(molecule)

    generate_calls = []
    window._services.conformer_service.request_conformers = (
        lambda model, count, optimize: generate_calls.append((model.uuid, count, optimize))
    )

    window._send_to_3d_viewer()

    assert window._center_tabs.currentWidget() is window._viewer3d
    assert generate_calls == []
