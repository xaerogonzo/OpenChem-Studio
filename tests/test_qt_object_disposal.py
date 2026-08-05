"""A test must not leave Qt objects behind for a later test to trip over.

This guards the two autouse fixtures in `conftest.py` --
`dispose_app_widgets` and `flush_deferred_deletes` -- because what they
prevent is invisible in normal output and lethal much later: a Windows
access violation inside an unrelated test's event pumping, at ~30% of a
full run, on some runs and not others. See their docstrings and CLAUDE.md
for the measurements.

Both checks are ordered pairs: one test deliberately abandons an object,
the next asserts it was destroyed in between. pytest runs tests in
definition order within a file, so the pair is deterministic -- unlike the
crash it protects against, which depended on when Python's collector
happened to run.
"""

from __future__ import annotations

import weakref

import shiboken6
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget


class _AbandonedPanel(QWidget):
    """Stands in for any of the app's panels: a top-level widget that a
    test constructs, never parents to anything, and walks away from.

    THE REFERENCE CYCLE IS THE POINT, and this test was worthless without
    it. A widget with no cycle is freed the instant the test's last name
    for it goes out of scope, by plain refcounting, so it never reaches
    the collector and never demonstrates anything -- the check passed
    against a deliberately disabled fixture. Real panels are in cycles
    like the one below, which is exactly why 112 of them survived a full
    run and got destroyed at arbitrary later moments instead.
    """

    def __init__(self) -> None:
        super().__init__()
        # self -> list -> lambda -> closure cell -> self. The app's panels
        # are full of this exact shape (`button.clicked.connect(lambda:
        # self._do_thing())`). `destroyed.connect(self._on_destroyed)` was
        # tried first and is NOT enough -- PySide holds that connection on
        # the C++ side, no Python cycle forms, and the widget is still
        # refcount-freed the moment the test returns.
        self._callbacks = [lambda: self._noop()]

    def _noop(self) -> None:
        pass


_abandoned_widget: list[weakref.ref] = []
_deleted_later: list[weakref.ref] = []


def test_a_test_may_walk_away_from_a_top_level_widget(qapp):
    _abandoned_widget.append(weakref.ref(_AbandonedPanel()))


def test_that_widget_was_destroyed_before_this_test_started(qapp):
    assert _abandoned_widget, "the test above must run first -- this pair is ordered"
    widget = _abandoned_widget[0]()
    assert widget is None or not shiboken6.isValid(widget), (
        "a top-level widget outlived the test that built it. Python will now "
        "destroy it at an arbitrary later moment, from inside some unrelated "
        "test's event dispatch. See dispose_app_widgets in conftest.py."
    )


def test_a_test_may_call_delete_later_and_not_wait(qapp):
    # A plain QObject, deliberately not a widget: `dispose_app_widgets`
    # does not cover it, so this isolates `flush_deferred_deletes`.
    obj = QObject()
    obj.deleteLater()
    _deleted_later.append(weakref.ref(obj))


def test_that_deferred_delete_was_flushed_before_this_test_started(qapp):
    assert _deleted_later, "the test above must run first -- this pair is ordered"
    obj = _deleted_later[0]()
    assert obj is None or not shiboken6.isValid(obj), (
        "a deleteLater() was still queued after its test ended. processEvents() "
        "does not deliver DeferredDelete, so it would sit in the process-wide "
        "queue until some later test caused a nested event loop to drain the "
        "whole backlog at once. See flush_deferred_deletes in conftest.py."
    )
