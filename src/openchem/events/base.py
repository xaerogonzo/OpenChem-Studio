from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TypeVar

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class Event:
    """Base class for all typed events published on the EventBus."""


TEvent = TypeVar("TEvent", bound=Event)
Handler = Callable[[TEvent], None]


class EventBus(QObject):
    """Typed publish/subscribe bus.

    Handlers subscribe by event *type* rather than by string name, so a new
    event type never requires touching this class. Publishing goes through a
    Qt signal so that events raised from a QThreadPool worker (e.g. by
    DescriptorService) are safely queued onto the EventBus's own thread
    (normally the GUI thread) instead of running handlers cross-thread.
    """

    _event_published = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._handlers: dict[type[Event], list[Handler]] = defaultdict(list)
        self._event_published.connect(self._dispatch)

    def subscribe(self, event_type: type[TEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[TEvent], handler: Handler) -> None:
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def publish(self, event: Event) -> None:
        self._event_published.emit(event)

    def _dispatch(self, event: Event) -> None:
        for event_type, handlers in list(self._handlers.items()):
            if isinstance(event, event_type):
                for handler in list(handlers):
                    handler(event)
