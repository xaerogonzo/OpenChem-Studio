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


# --- sending a generated structure to the editor ------------------------------
#
# Tautomers, stereoisomers and resonance forms come back as a
# `StructureSetResult`, and the Calculator Inspector's grid has been able to
# put a chosen one into the project since it was built -- as "Add to Project".
#
# **THE BEHAVIOUR WAS ALREADY RIGHT.** Measured on acetylacetone before any
# change: molecules 2 -> 3, the original untouched, the editor showing the
# picked enol, one undo step. What was missing was any way to know that from
# a label describing the mechanism rather than the destination.


def _tautomer_molblock(window):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles("C=C(O)CC(C)=O")
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def test_a_generated_structure_ADDS_a_molecule_rather_than_replacing_one(window):
    """**A TAUTOMER IS A DIFFERENT COMPOUND**, not a different arrangement of
    the same one -- which is the whole reason this adds where "Use in 2D
    Editor" replaces. Replacing would discard the molecule being worked on
    and everything computed for it."""
    project = window._session.project
    before = list(project.molecules)
    assert before, "no molecule to preserve"

    window._add_generated_structure(_tautomer_molblock(window), "Tautomer 3")

    assert len(project.molecules) == len(before) + 1
    assert project.molecules[: len(before)] == before, "an existing molecule was disturbed"
    assert project.molecules[-1].display_name == "Tautomer 3"


def test_sending_a_generated_structure_REVEALS_the_editor(window):
    """A control labelled "Send to 2D Editor" that leaves you on another tab
    is the navigation-claims-one-thing problem the panel rail exists to
    avoid. `add_molecule` selects the molecule and loads the canvas; it does
    not show it.

    Started from the 3D Viewer deliberately -- the editor is the default
    tab, so a test that does not move first passes without the reveal.
    """
    window._center_tabs.setCurrentWidget(window._viewer3d)
    assert window._center_tabs.currentWidget() is not window._editor

    window._add_generated_structure(_tautomer_molblock(window), "Tautomer 3")

    assert window._center_tabs.currentWidget() is window._editor


def test_a_structure_that_cannot_be_read_adds_nothing(window):
    """Reported, never crashes the dialog that called in -- and never leaves
    a half-built molecule in the project either."""
    project = window._session.project
    before = len(project.molecules)

    window._add_generated_structure("not a molblock", "Broken")

    assert len(project.molecules) == before
