"""Ketcher's own controls are answered by this application, not by Ketcher.

The embedded editor ships a periodic table, file open/save, About, Help
and a 3D viewer, and this application has all of them. Two controls that
look alike and behave differently read as one feature that has lost half
its capability depending which you pressed -- which is how the first of
them was reported: "the periodic table reverted to vanilla".

**UNDO IS NOT COSMETIC.** Measured in the running app before this
existed: Ketcher's undo does not unwind this window's `QUndoStack`. It
edits the canvas, which fires `change`, which pushes a NEW
`EditStructureCommand` -- the stack GREW from 3 to 4 on an undo. And
undoing past our own `setMolecule` empties the canvas, with the project
model following it to zero atoms.

The interception itself lives in the bundle and is guarded by
`tests/test_ketcher_bundle_is_current.py`, which derives a test per
bridge name from the JSX. The half that can only be checked in the
running app -- that the application answers AND Ketcher stays quiet --
was verified there: all eight actions arrived and Ketcher opened nothing
(`dialogs: 0, modals: 0`).
"""

from __future__ import annotations

import re

import pytest

from openchem.app.main_window import MainWindow

#: action name -> the `MainWindow` method that must answer it.
#:
#: Named methods rather than behaviour, because every one of these opens
#: a dialog or a file picker that a test has no business driving. What
#: matters is that the action reaches the right handler at all: a
#: swallowed click that answers nothing is worse than the duplicate it
#: replaced.
_ROUTES = {
    "periodic_table": "_show_periodic_table",
    "import": "_import_molecule",
    "export": "_export_molecule",
    "about": "_show_about",
    "help": "_show_help",
    "viewer_3d": "_send_to_3d_viewer",
}


@pytest.fixture(scope="module")
def window(qapp, tmp_path_factory):
    """One real window for the file.

    Retained rather than destroyed: `tests/conftest.py` keeps every
    MainWindow for the session on purpose, because collecting one
    corrupts the heap.
    """
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("overrule")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


@pytest.mark.parametrize("action,method", sorted(_ROUTES.items()))
def test_each_intercepted_control_reaches_its_handler(window, monkeypatch, action, method):
    """**EVERY handler is stubbed, not just the expected one.**

    Patching only the expected one leaves the others real, so a routing
    mistake runs a real handler -- and `_show_about` opens a MODAL, which
    does not fail the test, it deadlocks the whole run. A mutation arm
    that routed `import` to `_show_about` hung for ten minutes rather
    than failing in a second.

    Stubbing all of them also makes the assertion sharper: it can now say
    which handler was reached, instead of only that the expected one was
    not.
    """
    called: list[str] = []
    for name in set(_ROUTES.values()):
        monkeypatch.setattr(
            MainWindow, name, lambda self, *a, _n=name, **k: called.append(_n)
        )

    window._on_editor_action(action)

    assert called == [method], f"{action!r} reached {called or 'nothing'}, expected {method}"


def test_undo_goes_to_the_applications_stack_not_ketchers(window, monkeypatch):
    """THE DEFECT THIS EXISTS FOR.

    Ketcher's undo edits the canvas, which fires `change`, which pushes a
    NEW command -- so pressing it GREW the stack (3 -> 4) rather than
    unwinding it. Routing it here means there is one history.
    """
    undone: list[str] = []
    monkeypatch.setattr(type(window._undo_stack), "undo", lambda self: undone.append("undo"))
    monkeypatch.setattr(type(window._undo_stack), "redo", lambda self: undone.append("redo"))

    window._on_editor_action("undo")
    window._on_editor_action("redo")

    assert undone == ["undo", "redo"]


def test_an_unknown_action_is_logged_rather_than_swallowed(window, caplog):
    """The click has already been eaten by the time this runs, so an
    action with no handler means the button now does NOTHING -- strictly
    worse than the duplicate it replaced. It has to be loud."""
    import logging

    with caplog.at_level(logging.WARNING, logger="openchem.ui"):
        window._on_editor_action("no_such_action")

    # `getMessage()`, not `.message`: the record carries a lazy format
    # string and its args separately, so the unformatted attribute does
    # not contain the action name at all.
    assert any("no_such_action" in record.getMessage() for record in caplog.records), caplog.text


def _routed_actions() -> set[str]:
    """The action names `_on_editor_action` really handles.

    Read out of the PRODUCTION method rather than from `_ROUTES` above.
    `_ROUTES` is this file's own copy, used to say which handler each
    action should reach; checking coverage against it would be checking
    the test against itself, and a mutation proved exactly that -- an
    entry deleted from the real routing table left this green.
    """
    import inspect

    from openchem.app.main_window import MainWindow

    source = inspect.getsource(MainWindow._on_editor_action)
    body = source.split("handlers = {", 1)[1].split("}", 1)[0]
    return set(re.findall(r'"([a-z_0-9]+)":', body))


def test_every_intercepted_name_has_a_route():
    """DERIVED from the JSX, so a control intercepted in the bundle
    without a handler here fails rather than becoming a dead button.

    This is the direction the bundle guard does not cover: it checks that
    every JSX call has a `_Bridge` slot, and a slot can still emit an
    action that nothing routes -- which is worse than the duplicate it
    replaced, because the click has already been swallowed.
    """
    from pathlib import Path

    from openchem.ui.widgets import ketcher_editor_backend as backend

    jsx = (Path(__file__).resolve().parent.parent
           / "tools" / "ketcher-host" / "src" / "main.jsx").read_text(encoding="utf-8")
    intercepted = set(re.findall(r"^\s*'?[^']*'?\s*:\s*'([A-Za-z_][A-Za-z0-9_]*)',\s*$",
                                 jsx, re.MULTILINE))
    intercepted |= set(re.findall(r"bridgeObject\.([A-Za-z_][A-Za-z0-9_]*Requested)\s*\(", jsx))
    assert intercepted, "no interceptions found in main.jsx -- the parser is wrong"

    source = Path(backend.__file__).read_text(encoding="utf-8")
    actions = dict(re.findall(
        # A DIGIT is legal in the middle: `viewer3dRequested`.
        r"def ([A-Za-z_][A-Za-z0-9_]*Requested)\(self\).*?_emit_editor_action\(\"([a-z_0-9]+)\"\)",
        source, re.DOTALL))

    routed = _routed_actions()
    unrouted = sorted(actions[name] for name in intercepted
                      if name in actions and actions[name] not in routed)

    assert not unrouted, f"{unrouted} are intercepted in the bundle but route nowhere"
