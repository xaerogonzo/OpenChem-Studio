"""One router for every `FactLink`, and no silent no-op.

A fact can carry a `FactLink` -- "where did this come from" -- and `FactView`
renders it as a `>` button beside the row. Following one used to be an
`if/elif` chain inside `MainWindow._on_atom_fact_link` that handled three
targets and **fell off the end for everything else**.

**FOUR EMITTED LINKS DID NOTHING WHEN PRESSED.** Measured over the shipped
producers, seven `FactLink`s are constructed and four name a target the chain
never matched:

    atom_report.py:259    "Open {dataset.name}"   calculator_inspector
    atom_report.py:286    "Open {spectrum.name}"  nmr_view
    bond_report.py:115    "Inspect C7"            atom_report
    molecule_report.py:202 "Open in Properties"   calculator_inspector

Every one renders a button with a label promising an action. A button that
silently does nothing is indistinguishable from a broken one, which is the
same complaint this project already answered for the "Open..." calculator
rows -- and the fix there was the same: say something.

**THREE OUTCOMES, BECAUSE TWO CANNOT SAY WHAT HAPPENED.** "It did not open"
covers a viewer that is genuinely unavailable right now and a target nobody
ever wired, and those want different answers -- the first is a fact about
this molecule's state, the second is a defect. Both are visible; only one is
worth a warning in the log.

**THE HANDLER MAP IS THE VOCABULARY.** There is deliberately no closed enum of
targets: `FactLink.target`'s own docstring keeps it open "so a new destination
does not change this class", and a second closed list here would contradict
that and rot the first time a plugin declared one. A target with no handler is
UNKNOWN by construction rather than by comparison against a list.

The router holds no widgets. It is constructed with bound methods by whoever
owns them, so it is testable without a window -- which is the same reason the
routing was in the window rather than the panel to begin with.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("openchem.ui")


class LinkOutcome(str, Enum):
    """What following a link did."""

    #: The viewer opened.
    OPENED = "opened"
    #: The target is known and could not open right now -- usually because the
    #: result it names is not loaded. A statement about state, not a defect.
    UNAVAILABLE = "unavailable"
    #: No handler is registered for this target at all. A defect: something
    #: emitted a link nothing can follow.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LinkResult:
    outcome: LinkOutcome
    #: Reader-facing, and empty only when the viewer opened. The host shows
    #: this -- a router that logged and returned would be the silent no-op
    #: wearing a different coat.
    message: str = ""

    @property
    def opened(self) -> bool:
        return self.outcome is LinkOutcome.OPENED


#: A handler takes the link's `params` and returns whether it opened
#: something. Returning False is how a handler says "I know this target and
#: the thing it names is not here", which is the UNAVAILABLE case -- so a
#: handler never has to raise to decline.
LinkHandler = Callable[[dict], bool]


class FactLinkRouter:
    """Follow a `FactLink` to whatever owns the answer."""

    def __init__(self, handlers: dict[str, LinkHandler]) -> None:
        self._handlers = dict(handlers)

    def targets(self) -> frozenset[str]:
        """What this router can follow. Exposed so a guard can compare it
        against what the producers emit, rather than against a list somebody
        maintains."""
        return frozenset(self._handlers)

    def follow(self, link) -> LinkResult:
        target = getattr(link, "target", "") or ""
        params = getattr(link, "params", None) or {}
        label = getattr(link, "label", "") or "that view"

        handler = self._handlers.get(target)
        if handler is None:
            # LOUD. Something built a link nothing can follow, and the reader
            # pressed a button that promised an action.
            logger.warning("No handler for fact link target %r", target)
            return LinkResult(
                LinkOutcome.UNKNOWN,
                f"Nothing here knows how to open {label!r} "
                f"(unrecognised link target {target!r}).",
            )

        try:
            opened = handler(params)
        except Exception:
            # A handler that raises must not take the click path with it. The
            # reader gets a sentence rather than a traceback, and the log gets
            # the traceback rather than a shrug.
            logger.exception("Fact link handler for %r raised", target)
            return LinkResult(
                LinkOutcome.UNAVAILABLE, f"Could not open {label!r}."
            )

        if opened:
            return LinkResult(LinkOutcome.OPENED)
        return LinkResult(
            LinkOutcome.UNAVAILABLE,
            f"Could not open {label!r} -- that result is not loaded for this "
            "molecule. Run it first, then follow the link again.",
        )
