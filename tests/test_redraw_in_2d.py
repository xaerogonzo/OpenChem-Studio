"""Redraw in 2D is reachable, and it is not one of Ketcher's own actions.

The way back from "Use in 2D Editor" was reported missing: *"we don't have
an easy way to convert the structure back to a two d form. I tried hitting
the cleanup button. but it did not convert it back to a two d form."*

**BOTH OF KETCHER'S TIDY ACTIONS WERE TRIED FIRST, IN THE RUNNING APP, AND
NEITHER IS THE ANSWER.** On the reported cage, after Use in 2D Editor:

    Clean Up   z 6.8435 -> 0.0   conformers 3   SMILES unchanged
               and the picture keeps the projected x,y -- still the
               overlapping mess, 7 structure warnings
    Layout     z 6.8435 -> 0.0   conformers 3 -> 0
               and [C@@] -> [C@].  A DIFFERENT COMPOUND

The same Layout on a drawing that was never adopted leaves the SMILES
alone, measured as a control in the same run -- so what breaks is re-reading
a drawing whose atoms sit on top of each other, which is a state the adopt
path already warns about on screen.

So this action goes through the engine and reads the STRUCTURE. The
behaviour is in `tests/test_adopt_conformer.py`; what is here is that a
user can reach it, and that it is not quietly wired to the editor bridge
that was measured breaking.
"""

from __future__ import annotations

import pytest


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


def _entry(window, text):
    """The action as the MENU holds it -- walked, not read off an attribute.

    "the attribute exists" and "the entry is in the menu" are different
    claims, and only the second is one a user can act on.
    """
    for action in window._structure_menu.actions():
        if action.text() == text:
            return action
    raise AssertionError(
        f"the Structure menu has no {text!r}: "
        f"{[a.text() for a in window._structure_menu.actions() if a.text()]}"
    )


def test_the_structure_menu_offers_it(window):
    assert _entry(window, "Redraw in 2D") is window._redraw_flat_action


def test_it_sits_with_the_other_drawing_actions(window):
    """Beside Layout and Clean Up, because those are what a user reaches for
    first -- and did. An entry filed anywhere else is one more thing to not
    find."""
    labels = [a.text() for a in window._structure_menu.actions() if a.text()]
    assert abs(labels.index("Redraw in 2D") - labels.index("Clean Up")) == 1


def test_the_right_click_menu_offers_the_SAME_action(window):
    """One object, two menus -- the rule `_cip_action` and `_rotate_action`
    already follow, so the label and the enabled state cannot drift."""
    menu = window.build_atom_context_menu(0)

    assert window._redraw_flat_action in menu.actions(), (
        f"the right-click menu has no Redraw in 2D: "
        f"{[a.text() for a in menu.actions() if a.text()]}"
    )


def test_it_is_NOT_one_of_ketchers_toolbar_actions(window):
    """**THE POINT OF THE WHOLE THING.** `_add_editor_action` builds an
    entry that clicks a Ketcher button by `data-testid` and lets the page
    answer -- which is precisely the route measured turning `[C@@]` into
    `[C@]` on an adopted drawing.

    Asserted on the action's `data`, because that is how those entries
    carry their test id: a Ketcher-backed entry has one, and this must not.
    """
    assert window._redraw_flat_action.data() is None, (
        f"Redraw in 2D carries a Ketcher testid ({window._redraw_flat_action.data()!r}), "
        f"so it goes through the page rather than the engine"
    )


def test_it_carries_a_help_contract(window):
    from openchem.app.menu_help import MENU_HELP

    assert window._redraw_flat_action.toolTip()
    assert "redraw_flat" in MENU_HELP


def test_the_layout_contract_no_longer_claims_the_compound_is_unchanged(window):
    """It said "The compound is unchanged; only its picture moves", and the
    measurement above falsified that for the case a user hits it in. A
    contract that is false in the one situation somebody reads it in is
    worse than none."""
    from openchem.app.menu_help import MENU_HELP

    text = MENU_HELP["layout"].text
    assert "The compound is unchanged" not in text
    assert "Redraw in 2D" in text, "the contract does not name what to use instead"
