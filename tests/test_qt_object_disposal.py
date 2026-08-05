"""A test must not leave a deferred delete queued for a later test to drain.

This guards the autouse `flush_deferred_deletes` fixture in `conftest.py`,
because what it prevents is invisible in normal output and goes off much
later: `processEvents()` does not deliver a `DeferredDelete`, so without
the fixture every `deleteLater()` in the suite accumulates in one
process-wide queue until something spins a nested event loop and drains
the whole backlog at once, thousands of allocations away from the code
that queued it.

The check is an ordered pair: one test deliberately abandons an object,
the next asserts it was destroyed in between. pytest runs tests in
definition order within a file, so the pair is deterministic.

There is deliberately no companion check for abandoned WIDGETS. A fixture
that destroyed those was tried and reverted for crashing the suite on
master; `flush_deferred_deletes` documents that at length. The crash this
file's fixture was originally written to fix is still open.
"""

from __future__ import annotations

import weakref

import shiboken6
from PySide6.QtCore import QObject

_deleted_later: list[weakref.ref] = []


def test_a_test_may_call_delete_later_and_not_wait(qapp):
    # A plain QObject rather than a widget: nothing else in the suite
    # disposes of one, so this isolates `flush_deferred_deletes`.
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
