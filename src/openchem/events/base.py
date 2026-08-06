from __future__ import annotations

import inspect
import weakref
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TypeVar

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class Event:
    """Base class for all typed events published on the EventBus."""


TEvent = TypeVar("TEvent", bound=Event)
Handler = Callable[[TEvent], None]


class _Subscription:
    """One subscription, holding its handler weakly where it safely can.

    A BOUND METHOD is held weakly. `self._on_molecule_changed` keeps its
    panel alive for as long as the bus does if stored normally, and a bus
    outlives most of what subscribes to it -- so a strong list made the bus
    the owner of every panel ever built. Measured before this change:
    `PropertyPanel` and `DockingPanel` could not be freed by reference
    counting at all, only by the cyclic collector, and the collector runs
    at a moment nobody chooses.

    ANYTHING ELSE IS HELD STRONGLY, and that asymmetry is deliberate rather
    than an oversight. A lambda or a local function usually has no other
    reference: held weakly it would be collected the instant `subscribe`
    returned, and the subscription would silently never fire. A bound
    method is different precisely because its owner is the thing that
    should decide how long it lives.

    Measured across the codebase when this was written: production code
    subscribes 38 bound methods and zero lambdas; the tests subscribe 74
    lambdas. So the weak half covers everything real, and the strong half
    keeps every test honest.
    """

    __slots__ = ("_weak", "_strong", "__weakref__")

    def __init__(self, handler: Handler) -> None:
        self._weak: weakref.WeakMethod | None = None
        self._strong: Handler | None = None
        # `ismethod` is a fast path, not the guard -- `WeakMethod` itself
        # raises TypeError for anything that is not a bound method, so the
        # except below is what actually decides. Mutation testing cannot
        # tell the check from its absence, which is correct.
        if inspect.ismethod(handler):
            try:
                self._weak = weakref.WeakMethod(handler)
                return
            except TypeError:
                # A method of something not weak-referenceable. Rare, and
                # holding it strongly is the safe direction.
                pass
        self._strong = handler

    def handler(self) -> Handler | None:
        """The callable, or None once its owner has been collected."""
        if self._strong is not None:
            return self._strong
        assert self._weak is not None
        return self._weak()

    def matches(self, handler: Handler) -> bool:
        """Whether this subscription is for `handler`.

        `==`, not `is`: a bound method is a fresh object every time it is
        looked up, so `panel._on_x is panel._on_x` is False and an identity
        test would make `unsubscribe` silently do nothing.
        """
        current = self.handler()
        return current is not None and current == handler


class EventBus(QObject):
    """Typed publish/subscribe bus.

    Handlers subscribe by event *type* rather than by string name, so a new
    event type never requires touching this class. Publishing goes through a
    Qt signal so that events raised from a QThreadPool worker (e.g. by
    DescriptorService) are safely queued onto the EventBus's own thread
    (normally the GUI thread) instead of running handlers cross-thread.

    Subscriptions do not keep their subscriber alive -- see `_Subscription`
    for which handlers are held weakly and why the rest are not. A handler
    whose owner has been collected is dropped on the next publish; nothing
    has to unsubscribe on the way out.
    """

    _event_published = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._handlers: dict[type[Event], list[_Subscription]] = defaultdict(list)
        self._event_published.connect(self._dispatch)

    def subscribe(self, event_type: type[TEvent], handler: Handler) -> None:
        self._handlers[event_type].append(_Subscription(handler))

    def unsubscribe(self, event_type: type[TEvent], handler: Handler) -> None:
        """Remove ONE subscription of `handler`, as the strong version did.

        Subscribing the same handler twice and unsubscribing once has
        always left one live, and `PluginContext` records exactly one
        rollback per subscribe, so removing every copy would unhook a
        second plugin's subscription along with the first.
        """
        entries = self._handlers.get(event_type)
        if not entries:
            return
        for index, entry in enumerate(entries):
            if entry.matches(handler):
                del entries[index]
                return

    def publish(self, event: Event) -> None:
        self._event_published.emit(event)

    def _dispatch(self, event: Event) -> None:
        for event_type in list(self._handlers):
            if not isinstance(event, event_type):
                continue
            entries = self._handlers[event_type]
            # Prune first, then call. A handler is free to subscribe or
            # unsubscribe while it runs, so the calls happen against a
            # snapshot rather than against the list being edited.
            live = [entry for entry in entries if entry.handler() is not None]
            if len(live) != len(entries):
                self._handlers[event_type] = live
            for entry in list(live):
                handler = entry.handler()
                if handler is not None:
                    handler(event)
