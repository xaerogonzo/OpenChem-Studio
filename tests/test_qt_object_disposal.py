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


def test_subscribing_does_not_keep_the_subscriber_alive(qapp):
    """The contract `EventBus` now holds itself to.

    It used to store the BOUND METHOD, so the bus held the subscriber and
    the subscriber held the bus: nothing could be freed by reference
    counting, and the pair waited for the cyclic collector, which runs at a
    moment nobody chooses -- including inside Qt's event dispatch during an
    unrelated test. Bound methods are held weakly now, so a subscriber dies
    with its last real reference.
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
    ref = weakref.ref(Subscriber(bus))

    assert ref() is None, "refcounting alone must free a subscriber"


def test_a_lambda_handler_is_still_held_strongly(qapp):
    """The deliberate asymmetry, and the reason it is not a bug.

    A lambda usually has no other reference. Held weakly it would be
    collected the instant `subscribe` returned and the subscription would
    silently never fire -- which is far worse than a leak, because nothing
    would look wrong. Only bound methods are weak, because only they have
    an owner whose lifetime is the right answer.
    """
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    bus = EventBus()
    seen = []
    bus.subscribe(MoleculeChanged, lambda event: seen.append(event))

    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    assert len(seen) == 1


def test_a_dead_subscriber_is_dropped_rather_than_raising(qapp):
    """Nothing has to unsubscribe on the way out."""
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Subscriber:
        def __init__(self, bus, seen):
            self._seen = seen
            bus.subscribe(MoleculeChanged, self._on_changed)

        def _on_changed(self, event):
            self._seen.append(event)

    bus = EventBus()
    seen = []
    kept = Subscriber(bus, seen)
    Subscriber(bus, seen)  # dropped immediately

    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    assert len(seen) == 1, "the collected subscriber must not have been called"
    assert kept is not None
    # And the dead entry is REMOVED, not merely skipped. Skipping is
    # invisible to a behavioural test and would let `_handlers` grow for
    # the life of the process.
    assert len(bus._handlers[MoleculeChanged]) == 1


def test_unsubscribe_still_removes_exactly_one_subscription(qapp):
    """A bound method is a fresh object each time it is looked up, so
    `unsubscribe` has to compare by equality; an identity test would
    silently do nothing. One occurrence, matching the old behaviour --
    `PluginContext` records one rollback per subscribe."""
    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    class Subscriber:
        def __init__(self, seen):
            self._seen = seen

        def on_changed(self, event):
            self._seen.append(event)

    bus = EventBus()
    seen = []
    subscriber = Subscriber(seen)
    for _ in range(3):
        bus.subscribe(MoleculeChanged, subscriber.on_changed)

    bus.unsubscribe(MoleculeChanged, subscriber.on_changed)
    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    # THREE subscriptions, not two: with only two, a loop that deleted
    # every match still ended up removing one (it mutates the list it is
    # enumerating and falls off the end), so the test passed either way.
    assert len(seen) == 2


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


# --- the leak a self-capturing lambda creates -------------------------------


def _survives_collection(factory) -> bool:
    """True if the object is still alive after the cyclic collector has run.

    Built inside this helper so the caller keeps no local: an object the
    test itself still references is trivially alive, which is how two
    earlier attempts at this measurement fooled themselves.
    """
    import gc

    gc.collect()
    gc.collect()
    ref = weakref.ref(factory())
    for _ in range(3):
        gc.collect()
    return ref() is not None


def test_connecting_a_self_capturing_lambda_leaks_its_widget(qapp):
    """The mechanism, pinned so the fixes below have something to point at.

    PySide6 holds a connected plain callable STRONGLY and a QObject's bound
    method weakly. So a `lambda: self._handler(x)` connected to a signal
    roots its widget for the life of the process -- past refcounting and
    past the cyclic collector, which cannot see through the map the
    callable is kept in.

    This asserts the leak deliberately. If a future PySide6 stops leaking
    here, this test fails and the workarounds it justifies can go.
    """
    from PySide6.QtWidgets import QPushButton, QWidget

    class SelfCapturing(QWidget):
        def __init__(self):
            super().__init__()
            button = QPushButton(self)
            button.clicked.connect(lambda _checked=False: self._go())

        def _go(self):
            pass

    class BoundMethod(QWidget):
        def __init__(self):
            super().__init__()
            button = QPushButton(self)
            button.clicked.connect(self._go)

        def _go(self, _checked=False):
            pass

    assert _survives_collection(SelfCapturing), "PySide6 no longer leaks here"
    assert not _survives_collection(BoundMethod)


def test_the_property_panel_does_not_leak(qapp):
    """Measured before the fix: it survived refcounting AND three cycles of
    the collector, because `_section_for` connected one self-capturing
    lambda per registered calculator -- 22 of them on a default registry.
    Every panel ever built stayed in memory for the session."""
    from openchem.bootstrap import build_service_container
    from openchem.ui.panels.property_panel import PropertyPanel

    def build():
        services = build_service_container()
        return PropertyPanel(
            services.event_bus,
            services.calculator_registry,
            services.descriptor_service,
            services.chemistry_engine,
        )

    assert not _survives_collection(build)


def test_the_periodic_table_dialog_does_not_leak(qapp):
    """118 cells, each of which was connecting a self-capturing lambda."""
    from openchem.ui.dialogs.periodic_table_dialog import PeriodicTableDialog

    assert not _survives_collection(PeriodicTableDialog)


def test_a_subscriber_collected_during_dispatch_is_not_called(qapp):
    """The narrow race the None check in `_dispatch` exists for.

    Pruning happens before any handler runs, so an entry can be alive at
    prune time and dead by the time the loop reaches it -- which is exactly
    what happens when one handler drops the last reference to another
    subscriber. Without the guard that is a call through a dead weakref.

    Written after mutation testing: removing the check failed nothing,
    because every other test prunes and dispatches with a stable set.
    """
    import gc

    from openchem.events.base import EventBus
    from openchem.events.events import MoleculeChanged

    bus = EventBus()
    seen = []
    holder = {}

    class Victim:
        def on_changed(self, event):
            seen.append("victim")

    class Killer:
        def on_changed(self, event):
            seen.append("killer")
            holder.clear()  # drops the only reference to the victim
            gc.collect()

    killer = Killer()
    victim = Victim()
    holder["victim"] = victim
    bus.subscribe(MoleculeChanged, killer.on_changed)
    bus.subscribe(MoleculeChanged, victim.on_changed)
    del victim

    bus._dispatch(MoleculeChanged(molecule_uuid="u"))

    assert seen == ["killer"], "the victim was collected mid-dispatch and must not be called"


def test_closing_a_main_window_empties_its_undo_stack(qapp, tmp_path):
    """Not tidiness -- destruction safety.

    A MainWindow whose stack still holds commands faults when it is
    destroyed. Measured against the real window: suppress `_new_molecule`
    so nothing is ever pushed and it destroys cleanly 3/3; clear the stack
    first and it destroys cleanly 5/5; drop it as-is and it segfaults 5/5.
    `close()` alone is not enough, so `closeEvent` does the clearing.

    The mechanism is not understood. A synthetic QUndoCommand on a
    QUndoStack destroys fine, and so does the real `AddMoleculeCommand` in
    a minimal harness -- it takes the whole window. Recorded in CLAUDE.md.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user"))
    window = MainWindow(services, settings, SessionManager())
    # The auto-created molecule puts one command on the stack.
    assert window._undo_stack.count() > 0

    window.close()

    assert window._undo_stack.count() == 0
