"""The reader is a widget, and the window is a shell around it.

**WHY THESE EXIST AT ALL, GIVEN 149 TESTS ALREADY PASS UNCHANGED.** That is
the acceptance test for the EXTRACTION -- it says the move was
behaviour-neutral. It says nothing about the move STAYING a move: a later
edit that reimplements a little reader logic in the window, or rebuilds a
widget instead of pointing at the view's, passes every one of them while
quietly recreating the two-implementations problem this split exists to
remove. These are the guards for that, and for the one property the dock
depends on -- that the reader stands up with no window and no molecule.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from openchem.domain.reader_state import NO_MOLECULE
from openchem.ui.dialogs.merged_results_dialog import (
    EMPTY_MESSAGES,
    MergedResultsDialog,
)
from openchem.ui.widgets.fact_view import FactView
from openchem.ui.widgets.results_view import ResultsView
from tests.conftest import dispose

SHELL = pathlib.Path("src/openchem/ui/dialogs/merged_results_dialog.py")


def test_the_window_shows_the_view_it_aliases(qapp):
    """One reader in the window, and the names callers use point AT it.

    The mutation this is written from is the plausible one: build the
    widgets in the shell as before and hand the view its own, which leaves
    `window._view` a real `FactView` that renders nothing anybody sees.
    Identity is what tells an alias from a copy, and the count is what
    catches a second reader being built beside the first.
    """
    window = MergedResultsDialog("mol-1")
    view = window.results_view()

    assert window._view is view._view
    assert window._focus_box is view._focus_box
    assert window._selector_search is view._selector_search
    assert window._open_button is view._open_button
    assert window._visuals is view._visuals
    assert window._visuals_layout is view._visuals_layout
    assert window._empty is view._empty

    # ONE reader, not two. An alias check alone passes against a window that
    # aliases the first view and displays a second.
    assert len(window.findChildren(ResultsView)) == 1
    assert len(window.findChildren(FactView)) == 1
    dispose(window)


def test_the_reader_stands_up_with_no_window_and_no_molecule(qapp):
    """What a dock needs and a dialog never did.

    `MergedResultsDialog` is opened FOR a molecule, so "no molecule is
    selected" had no route through the application at all -- `reader_state`
    named the state and nothing could reach it. A reader that FOLLOWS the
    selection starts there, before anything is chosen, which is why the
    molecule uuid is defaulted rather than required.
    """
    view = ResultsView()
    assert view.molecule_uuid() == ""
    assert not view._empty.isHidden()
    # The NO_MOLECULE message, not the nothing-computed one: they send a
    # reader to two different places.
    assert view._empty.text() == EMPTY_MESSAGES[NO_MOLECULE]
    assert view._view.isHidden()
    dispose(view)


def _public_methods(tree: ast.Module, class_name: str) -> list[ast.FunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
            ]
    raise AssertionError(f"{class_name} is not in {SHELL}")


def test_every_public_method_of_the_window_forwards_to_the_view():
    """The shell holds no reader logic, asserted where it can be seen.

    **NOT A TEXT SCAN.** This file's own docstring names the reader and the
    view; a search for those words would match the explanation of the rule
    rather than a breach of it, which is the failure this repository has
    recorded seven times. The AST asks the only question that matters: is
    the body one statement, and is it a call on `self._results`?

    The narrow half is the setup assertion -- a walk that quietly returned
    nothing would satisfy an `all()` over it vacuously, and this guard's
    whole value is the population it covers.
    """
    tree = ast.parse(SHELL.read_text(encoding="utf-8"))
    methods = _public_methods(tree, "MergedResultsDialog")
    assert len(methods) >= 9, (
        f"only {len(methods)} public methods found in {SHELL}; the walk has "
        "collapsed and this guard is checking nothing"
    )

    offenders = []
    for method in methods:
        body = [
            node
            for node in method.body
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        ]
        if len(body) != 1:
            offenders.append(f"{method.name}: {len(body)} statements, not one")
            continue
        statement = body[0]
        value = statement.value if isinstance(statement, (ast.Return, ast.Expr)) else None
        if value is None:
            offenders.append(f"{method.name}: neither a return nor a call")
            continue
        # `return self._results` is a forward too -- results_view() is one.
        reached = ast.unparse(value.func if isinstance(value, ast.Call) else value)
        if not reached.startswith("self._results"):
            offenders.append(f"{method.name}: reaches {reached}, not self._results")

    assert not offenders, (
        "the window is doing reader work rather than forwarding it:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize(
    "name",
    [
        "set_structure_resolver",
        "molecule_uuid",
        "set_reader_memory",
        "view",
        "apply_view",
        "set_reports",
        "merged",
        "focus",
        "set_focus",
    ],
)
def test_the_reader_owns_the_surface_the_window_forwards(name):
    """Derived rather than hand-kept: the shell may only forward what the
    view really has, so a method renamed on one side and not the other is a
    failure here rather than an `AttributeError` in front of a user."""
    assert hasattr(ResultsView, name), f"ResultsView has no {name}"
    assert hasattr(MergedResultsDialog, name), f"the window no longer forwards {name}"
