"""Rotate 3D is reachable from the menu bar and from F7.

**IT WAS REACHABLE ONLY FROM ONE BUTTON**, on the editor's own bar, so it
existed only while the 2D Editor tab was showing and was discoverable only
by noticing it. `docs/USER_GUIDE.md` described it; the Structure menu did
not offer it and no key pressed it. F7 is the key Marvin binds to the same
gesture.

**WHAT IS ASSERTED HERE IS AN INVARIANT, NOT A STATE.** Entering the mode
for real needs the editor's page to be live -- `start_rotation()` answers
False while it is loading, deliberately, so that a control never claims a
mode nothing is in. So these do not assert "the mode turned on"; they assert
that the menu entry's tick always equals the BUTTON's, whatever the button
decided, which is the property that stops two controls disagreeing. The
live half is `benchmarks/visual/rotate_3d_reach.json`.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QKeySequence


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _bare_editor(qapp):
    """The editor alone, with no window and no molecule.

    Deliberately not the `window` fixture: what is under test is the
    widget's own signal ORDER, and asserting it through a consumer would
    pass for a consumer that happened to resync afterwards -- which is
    exactly how the first version of this looked correct.
    """
    from PySide6.QtGui import QUndoStack

    from openchem.bootstrap import build_service_container
    from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget

    services = build_service_container()
    return MoleculeEditorWidget(
        services.chemistry_engine, services.event_bus, QUndoStack()
    )


def _rotate_entry(window):
    """The action as the MENU holds it, not the attribute.

    Found by walking the real `QMenu`, because "the attribute exists" and
    "the entry is in the menu" are different claims and only the second one
    is what a user can reach -- the same reason the panel guards walk the
    live menu bar rather than the window's fields.
    """
    for action in window._structure_menu.actions():
        if action.text() == "Rotate 3D":
            return action
    raise AssertionError(
        f"the Structure menu has no Rotate 3D entry: "
        f"{[a.text() for a in window._structure_menu.actions() if a.text()]}"
    )


def test_the_structure_menu_offers_rotate_3d(window):
    assert _rotate_entry(window) is window._rotate_action


def test_it_is_on_F7(window):
    entry = _rotate_entry(window)

    assert entry.shortcut() == QKeySequence("F7"), entry.shortcut().toString()


def test_it_is_checkable_because_the_mode_is_a_state(window):
    """An entry that could not show whether the mode is on would be worse
    than none: the whole point of the mode is that dragging means something
    different while it is on."""
    assert _rotate_entry(window).isCheckable()


def test_it_carries_the_SAME_contract_as_the_button(window):
    """**ONE CONCEPT, ONE `help_id`.** `menu_help` registers the button's
    own `ROTATE_HELP` object rather than a second copy of its words, so the
    two cannot drift into saying different things about one gesture --
    which is what `test_one_help_id_means_exactly_one_thing` and
    `test_one_concept_is_not_split_across_many_help_ids` between them
    require of any control added here."""
    from openchem.app.menu_help import MENU_HELP
    from openchem.ui.widgets.molecule_editor_widget import ROTATE_HELP

    assert MENU_HELP["rotate_in_3d"] is ROTATE_HELP


def test_the_menu_entry_presses_the_editors_own_button(window):
    """**THE BUTTON, NOT THE HANDLER BEHIND IT.** `_on_rotate_toggled` is
    where the refusals live, and a menu entry that called it directly would
    leave the button showing the opposite of what happened -- the
    `jobs_cancel` rule, which exists because a control that reports a state
    nothing is in is this project's most repeated defect."""
    pressed: list[bool] = []
    window._editor._rotate_button.clicked.connect(lambda: pressed.append(True))

    _rotate_entry(window).trigger()

    assert pressed == [True], "the menu entry did not press the real button"


def test_the_entrys_tick_always_equals_the_button(window):
    """**THE INVARIANT, AND THE ONLY ONE WORTH ASSERTING HERE.**

    Two controls for one mode is the drift this file keeps refusing, so the
    button decides and the entry follows -- through a REFUSAL too, which is
    the case that broke two earlier designs. With no molecule loaded the
    button is set straight back, and the entry has to come back off with it
    whether the trip in was a menu trigger or a press of the button itself.
    Both routes are walked here for that reason.
    """
    entry = _rotate_entry(window)
    button = window._editor._rotate_button

    for step in ("initial", "trigger", "trigger again", "press the button"):
        if step == "trigger" or step == "trigger again":
            entry.trigger()
        elif step == "press the button":
            button.click()
        assert entry.isChecked() == button.isChecked(), (
            f"after {step}: menu entry {entry.isChecked()}, "
            f"button {button.isChecked()}"
        )


def test_the_action_does_not_decide_the_state_itself(window):
    """Qt flips a checkable action's own state BEFORE `triggered` arrives,
    so a handler that acted on that argument would make the action the
    authority. It is not. Setting the tick by hand and triggering must still
    leave it agreeing with the button rather than with itself."""
    entry = _rotate_entry(window)
    button = window._editor._rotate_button
    entry.setChecked(True)

    entry.trigger()

    assert entry.isChecked() == button.isChecked(), (
        f"the action kept its own state: entry {entry.isChecked()}, "
        f"button {button.isChecked()}"
    )


def test_the_signal_reports_where_the_mode_ENDED_not_what_was_asked(qapp):
    """**THE NESTED-EMISSION TRAP, AND TWO DESIGNS FELL INTO IT.**

    `_on_rotate_toggled` refuses by calling `setChecked(False)` on the
    button that is mid-emission, and Qt runs that nested emission to
    completion before the outer one reaches its remaining slots. A listener
    connected straight to `toggled` therefore sees `[False, True]` -- the
    refusal first, the request last -- and ends believing the mode is on.

    Measured before this was fixed: the Structure menu's tick read checked
    over an unchecked button. Asserted at the widget, with no window, so
    what is pinned is the ORDER rather than one consumer's luck.
    """
    widget = _bare_editor(qapp)
    reported: list[bool] = []
    widget.rotation_mode_changed.connect(reported.append)

    # No molecule, so entering is refused on the first branch.
    widget._rotate_button.click()

    assert widget._rotate_button.isChecked() is False, "the refusal did not happen"
    assert reported and reported[-1] is False, (
        f"the last thing reported was {reported}, so a mirror would be left "
        f"claiming a mode nothing is in"
    )


def test_the_canvas_right_click_offers_the_SAME_action(window):
    """**A THIRD DOOR, AND THE SAME OBJECT BEHIND IT.**

    "we definitely need ... a possible menu item or a context right click
    or something ... because how would a user ever figure that out?" -- a
    button on one tab and an undocumented key were the only ways in.

    The same `QAction` as the Structure menu's, so the tick cannot say one
    thing in the menu bar and another under the cursor. A second action
    with the same label is what this asserts against, and it is the exact
    drift `_cip_action` is shared to avoid.
    """
    menu = window.build_atom_context_menu(0)

    assert window._rotate_action in menu.actions(), (
        f"the right-click menu has no Rotate 3D: "
        f"{[a.text() for a in menu.actions() if a.text()]}"
    )
