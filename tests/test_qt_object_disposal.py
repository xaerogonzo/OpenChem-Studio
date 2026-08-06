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

There is deliberately no companion check that DESTROYS abandoned widgets.
A fixture that did was tried twice and reverted twice for crashing the
suite; `flush_deferred_deletes` documents that at length.

The second half of the problem -- widgets whose C++ destructor ran inside
an unrelated test -- is now solved by the `pytest_runtest_teardown` hook in
`conftest.py`, and the pair of tests at the bottom of this file guard the
mechanism it relies on.
"""

from __future__ import annotations

import weakref

import shiboken6
from PySide6.QtCore import QObject

_deleted_later: list[weakref.ref] = []
_abandoned_subscribers: list[weakref.ref] = []


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


# --- why a panel outlives its test, and what the teardown collect fixes ----


def test_subscribing_to_the_event_bus_makes_a_reference_cycle(qapp):
    """The cause, pinned.

    `EventBus.subscribe` stores the BOUND METHOD, so the bus holds the
    subscriber and the subscriber holds the bus. Reference counting cannot
    break that, so nothing is freed when a test's locals go out of scope --
    it waits for the cyclic collector, which runs whenever it likes,
    including from inside Qt's event dispatch in a completely unrelated
    test. On Windows that is an access violation.

    Measured before the fix: 138 widgets per full run had their C++
    destructor run in a LATER test than the one that built them.
    """
    import gc

    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Subscriber:
        def __init__(self, bus):
            self._bus = bus
            bus.subscribe(MoleculeChanged, self._on_changed)

        def _on_changed(self, event):
            pass

    gc.collect()
    bus = EventBus()
    subscriber = Subscriber(bus)
    ref = weakref.ref(subscriber)
    del bus, subscriber

    assert ref() is not None, "refcounting freed it; the cycle this guards is gone"

    gc.collect()
    assert ref() is None, "the cyclic collector must be able to free it"


def test_a_subscriber_left_behind_is_gone_before_the_next_test(qapp):
    """The first half of an ordered pair, like the deferred-delete one
    above: this abandons a subscriber, and the next test asserts it was
    collected in between -- which is what the teardown hook exists to
    guarantee, and what stops the destructor landing in someone else's
    event dispatch."""
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Abandoned:
        def __init__(self, bus):
            self._bus = bus
            bus.subscribe(MoleculeChanged, self._on_changed)

        def _on_changed(self, event):
            pass

    bus = EventBus()
    _abandoned_subscribers.append(weakref.ref(Abandoned(bus)))
    _abandoned_subscribers.append(weakref.ref(bus))


def test_the_abandoned_subscriber_was_collected_at_the_previous_teardown(qapp):
    assert _abandoned_subscribers, "the previous test did not run; the pair is broken"
    assert all(ref() is None for ref in _abandoned_subscribers), (
        "a subscriber survived into this test -- the teardown gc.collect() in "
        "conftest.py has regressed, and its destructor will now run at an "
        "arbitrary later moment"
    )
