from __future__ import annotations

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.molecule import MoleculeModel


_WINDOWS: list = []


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


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
    window = _track(MainWindow(services, settings, session))

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
    return _track(MainWindow(services, settings, session))


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


def test_structure_menu_actions_proxy_to_the_real_ketcher_buttons(qapp, tmp_path):
    """Regression test for the bridges: Aromatize/Dearomatize/Layout/Clean
    Up/explicit hydrogens/Check Structure all go through the same
    confirmed-live `trigger_toolbar_action` mechanism, not a
    reimplementation.

    They moved out of Edit into their own Structure menu, following
    Marvin -- Edit is for the document (undo, clipboard, which molecule),
    Structure is for operating on the structure.

    **Calculate CIP was in this list and left it.** It is calculated
    annotation state rather than a structural edit, so it no longer goes
    through a toolbar button at all -- see the table below and
    `test_the_cip_toggle_is_display_state_not_a_toolbar_action`.
    """
    window = _build_window(tmp_path)
    calls: list[str] = []
    window._editor.trigger_toolbar_action = lambda action_id: calls.append(action_id)

    edit_menu = window._structure_menu
    expected = {
        "Aromatize": "Aromatize button",
        "Dearomatize": "Dearomatize button",
        "Layout (Recalculate Coordinates)": "Layout button",
        "Clean Up": "Clean Up button",
        "Add/Remove Explicit Hydrogens": "Add/Remove explicit hydrogens button",
        "Check Structure in the Editor (Indigo)...": "Check Structure button",
    }
    # **CIP IS DELIBERATELY ABSENT from this table**, and used to be in it.
    # It is calculated annotation state rather than a structural edit, so it
    # no longer proxies to a toolbar button at all -- Ketcher's fires an
    # asynchronous `change` and grows its own undo history, which is what
    # made the labels impossible to keep fresh. See
    # `test_the_cip_toggle_is_display_state_not_a_toolbar_action`.
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

    ours = next(a for a in window._structure_menu.actions() if a.text() == "Check Structure...")
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


def test_stereo_descriptors_are_the_SAME_action_in_both_menus(qapp, tmp_path):
    """"I also think we may have lost the ability to view lone pairs, or it
    was lost for me in the menus. It should at least be on the dropdown
    view tab" -- the same complaint applies to R/S and E/Z, which existed
    only under Structure.

    **ONE QAction, offered twice**, not two entries that call the same
    thing. Two would drift: a label change, a shortcut or an enable rule
    added to one and not the other. Asserted on identity, because two
    actions with equal text would pass any weaker check.

    Found by TEXT rather than by `data()`, because the action no longer
    carries a Ketcher `data-testid`: it is a checkable display toggle now,
    not a proxy for a toolbar button. See
    `test_the_cip_toggle_is_display_state_not_a_toolbar_action`.
    """
    window = _build_window(tmp_path)

    def cip(menu):
        return next(a for a in menu.actions() if "R/S" in a.text())

    from_structure = cip(window._structure_menu)
    from_view = cip(_structure_display_menu(window))

    assert from_structure is from_view
    assert "R/S" in from_structure.text() and "E/Z" in from_structure.text()


def test_the_cip_toggle_is_display_state_not_a_toolbar_action(qapp, tmp_path):
    """The reported bug, at the level where its CAUSE lives.

    "Noticed a bug with at least the R/S label. If a molecule is changed
    while the label is turned on, it won't update. It will only update once
    the R/S option is clicked again."

    It did not update because it was not state: the menu item clicked
    Ketcher's own "Calculate CIP" toolbar button, a one-shot calculation
    whose result Ketcher stores on `atom.cip` and never invalidates. A
    checkable action that reaches `set_cip_labels` is what makes it
    recomputable at all -- everything downstream of that (recompute on
    edit, clear on the way off) hangs off the editor holding the state.

    Both halves are asserted, because either alone would pass against the
    bug: a checkable action still wired to `trigger_toolbar_action` would
    look right in the menu and behave exactly as before.
    """
    window = _build_window(tmp_path)
    toggled: list[bool] = []
    toolbar: list[str] = []
    window._editor.set_cip_labels = toggled.append
    window._editor.trigger_toolbar_action = toolbar.append

    action = next(a for a in window._structure_menu.actions() if "R/S" in a.text())
    assert action.isCheckable(), "a one-shot action cannot be kept up to date"

    action.trigger()
    action.trigger()

    assert toggled == [True, False], toggled
    assert toolbar == [], "the CIP display must not go through Ketcher's toolbar button"


def test_the_stereo_group_label_styles_are_exclusive_and_start_at_ketchers_default(
    qapp, tmp_path
):
    """Four styles, one at a time, and the menu opens agreeing with the
    canvas.

    Ketcher's settings schema declares `stereoLabelStyle` defaults to
    "Iupac" (read from the bundle). A menu that opened with a different
    one checked would claim a setting nobody applied -- and since these
    are fire-and-forget render options with no read-back, nothing else
    would ever correct it.
    """
    window = _build_window(tmp_path)
    sent: list[tuple[str, object]] = []
    window._editor.set_render_option = lambda name, value: sent.append((name, value))

    style_menu = next(
        m
        for m in _structure_display_menu(window).findChildren(type(window._view_menu))
        if m.title().startswith("Stereo Group Labels")
    )
    actions = style_menu.actions()

    assert [a.data() for a in actions] == ["Iupac", "Classic", "On", "Off"]
    assert [a.isChecked() for a in actions] == [True, False, False, False]
    assert all(a.actionGroup() is actions[0].actionGroup() for a in actions)

    actions[3].trigger()
    assert sent == [("stereoLabelStyle", "Off")]
    assert [a.isChecked() for a in actions] == [False, False, False, True]


def test_the_stereo_flag_toggle_drives_the_option_ketcher_really_has(qapp, tmp_path):
    """`showStereoFlags` is a real Ketcher render option (its own settings
    dialog calls it "Show the Stereo flags", default true) and it toggles
    the molecule-level ABS / AND Enantiomer / Mixed caption.

    **It does NOT show R/S**, which is what the plan for this work
    assumed and what the probe disproved -- hence the label naming the
    flags rather than the descriptors.
    """
    window = _build_window(tmp_path)
    sent: list[tuple[str, object]] = []
    window._editor.set_render_option = lambda name, value: sent.append((name, value))

    action = next(
        a
        for a in _structure_display_menu(window).actions()
        if a.text().startswith("Show Stereo Flags")
    )
    assert action.isCheckable()
    assert "R/S" not in action.text() and "E/Z" not in action.text()

    action.setChecked(True)
    action.setChecked(False)
    assert sent == [("showStereoFlags", True), ("showStereoFlags", False)]


def _electron_menu(window):
    display = _structure_display_menu(window)
    return next(
        m
        for m in display.findChildren(type(window._view_menu))
        if m.title() == "Electron Display"
    )


def test_the_electron_display_modes_are_exclusive_and_start_off(qapp, tmp_path):
    """Off by default: an annotation nobody asked for is one more thing on
    an already crowded canvas."""
    window = _build_window(tmp_path)
    chosen: list[str] = []
    window._editor.set_electron_mode = lambda mode: chosen.append(mode)

    actions = _electron_menu(window).actions()

    assert [a.data() for a in actions] == ["off", "pairs"]
    assert [a.isChecked() for a in actions] == [True, False]

    actions[1].trigger()
    assert chosen == ["pairs"]

    # **EXCLUSIVITY ASSERTED BY BEHAVIOUR, not by membership.** Checking
    # that they share a QActionGroup passes just as happily when that
    # group has `setExclusive(False)` -- measured, a mutation that flipped
    # it survived the whole file. Two modes checked at once would leave
    # the menu claiming the canvas is in two states.
    assert [a.isChecked() for a in actions] == [False, True]
    actions[0].setChecked(True)
    assert [a.isChecked() for a in actions] == [True, False]


def test_full_lewis_is_NOT_a_mode_of_the_canvas_overlay(qapp, tmp_path):
    """It shipped as a disabled third radio item and has left that group.

    **The two are different KINDS of control**, which is the whole reason
    for the restructure: Off and Lone pairs set the canvas overlay and
    stay checked; Full Lewis opens a window and has nothing to stay
    checked about. A radio item that opens a dialog would have to
    un-check itself immediately, which is a control lying about what it
    is.

    Asserted on the SIBLING relationship rather than on the label alone,
    because "an action called Full Lewis exists somewhere" would stay
    true if it were put straight back into the radio group.
    """
    window = _build_window(tmp_path)

    modes = _electron_menu(window).actions()
    assert not any(a.isCheckable() and "Lewis" in a.text() for a in modes)

    display = _structure_display_menu(window)
    lewis = next(a for a in display.actions() if "Lewis" in a.text())

    assert lewis.isEnabled()
    assert not lewis.isCheckable()
    assert lewis.text().endswith("..."), lewis.text()


def test_full_lewis_opens_a_snapshot_of_the_SELECTED_molecule(qapp, tmp_path, monkeypatch):
    """The dialog is a snapshot, so what it is opened WITH is the whole
    contract -- and the two ways to get that wrong are opening it on the
    wrong molecule and opening it on a stale molblock.

    The revision travels with it for the same reason: the details panel
    quotes it, which is what makes a window somebody left open an hour ago
    diagnosable rather than merely wrong.
    """
    from openchem.ui.dialogs.lewis_diagram_dialog import LewisDiagramDialog

    window = _build_window(tmp_path)
    molecule = MoleculeModel(display_name="Acetate")
    window._services.chemistry_engine.set_structure_from_smiles(molecule, "CC(=O)[O-]")
    window.add_molecule(molecule)
    opened: list[LewisDiagramDialog] = []
    monkeypatch.setattr(LewisDiagramDialog, "exec", lambda self: opened.append(self))

    lewis = next(a for a in _structure_display_menu(window).actions() if "Lewis" in a.text())
    lewis.trigger()

    assert len(opened) == 1
    dialog = opened[0]
    assert "Acetate" in dialog._header.text()
    assert dialog.diagram.drawable
    # The molblock it was handed, not one it went and fetched.
    assert dialog.diagram.provenance.molblock_sha
    assert dialog.diagram.provenance.structure_revision == (
        window._services.structure_check_service.current_version(molecule.uuid)
    )


def test_full_lewis_with_nothing_selected_says_so_rather_than_opening_empty(
    qapp, tmp_path, monkeypatch
):
    """An empty diagram window is indistinguishable from a broken one."""
    from openchem.ui.dialogs.lewis_diagram_dialog import LewisDiagramDialog
    from PySide6.QtWidgets import QMessageBox

    window = _build_window(tmp_path)
    window._session.select_molecule(None)
    opened: list[object] = []
    monkeypatch.setattr(LewisDiagramDialog, "exec", lambda self: opened.append(self))
    told: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[2]))
    )

    lewis = next(a for a in _structure_display_menu(window).actions() if "Lewis" in a.text())
    lewis.trigger()

    assert opened == []
    assert told and "Select a molecule" in told[0]


def test_there_is_no_formal_charge_entry_because_ketcher_draws_it(qapp, tmp_path):
    """Measured: `C[NH3+]` renders `C H 3 N H 3 +` on Ketcher's own canvas
    (tests/test_ketcher_viewport_transform.py). A second charge beside its
    own would be the "two of everything" failure this project keeps
    removing."""
    window = _build_window(tmp_path)

    labels = [a.text().lower() for a in _electron_menu(window).actions()]

    assert not any("charge" in label for label in labels), labels


def test_the_electron_status_reaches_the_status_bar(qapp, tmp_path):
    """The two states that draw NOTHING and mean different things: "no
    lone pairs" is an answer, "analysis unavailable" is not."""
    window = _build_window(tmp_path)

    window._editor.electron_status.emit("Lone-pair analysis unavailable: a metal.")

    assert "unavailable" in window.statusBar().currentMessage()


def test_nothing_is_said_when_there_are_dots_to_look_at(qapp, tmp_path):
    """Prose repeating what is already on screen is noise."""
    window = _build_window(tmp_path)
    window.statusBar().showMessage("something earlier")

    window._editor.electron_status.emit("")

    assert window.statusBar().currentMessage() == "something earlier"
