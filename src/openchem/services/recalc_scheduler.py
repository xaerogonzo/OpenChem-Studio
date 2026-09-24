"""Decides WHEN a canvas edit's recomputation runs, and says so with `RecalculationDue`.

**ONE PLACE, BECAUSE THREE THINGS RECOMPUTED PER EDIT AND EACH WOULD OTHERWISE NEED ITS
OWN TIMER.** The window re-requested the descriptor fan-out, the Properties panel
re-ran the substance perception, and the structure version bumped for a result nobody
had asked for. They now subscribe to one event, and this class is the only thing that
knows how long to wait.

A canvas edit publishes `MoleculeChanged(during_edit=True)`. That event still reaches
everything that only has to KNOW the structure moved -- the version bumps, so results
read STALE at once, which is the honest state of a result for a structure that is gone
-- but the consumers that COMPUTE wait for `RecalculationDue`, which this publishes
once the policy says so:

    while drawing      a zero-delay timer: edits within one event-loop turn coalesce
    after I pause      a single-shot timer restarted by EVERY edit (a debounce)
    only when I ask    no timer; `recalculate_now()` is the person asking

Anything that is not a canvas edit (undo, redo, import, rename, a conformer command)
publishes `during_edit=False`, is recomputed by its consumers at once, and CANCELS a
pending run for its molecule: the run would only repeat what has just been done.
Selecting a molecule cancels everything pending, because selection itself recomputes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from openchem.domain.recalc_policy import RecalcPolicy
from openchem.events.base import EventBus
from openchem.events.events import MoleculeChanged, MoleculeSelected, RecalculationDue

logger = logging.getLogger("openchem.services")


class RecalcScheduler(QObject):
    """See the module docstring."""

    #: Whether anything is waiting to be recalculated. For the "Recalculate Now" action
    #: and the status text: with results only on request, this is what tells a person
    #: their results are out of date.
    pending_changed = Signal(bool)

    def __init__(
        self,
        event_bus: EventBus,
        policy_source: Callable[[], RecalcPolicy],
        parent: QObject | None = None,
    ) -> None:
        """`policy_source` is read at every edit, never cached, so a change in Settings
        applies to the very next edit -- and to an edit already waiting."""
        super().__init__(parent)
        self._event_bus = event_bus
        self._policy_source = policy_source
        #: Molecules edited since the last run, in the order first edited.
        self._pending: dict[str, None] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        event_bus.subscribe(MoleculeChanged, self._on_molecule_changed)
        event_bus.subscribe(MoleculeSelected, self._on_molecule_selected)

    # --- what the scheduler is told ------------------------------------------------

    def _on_molecule_changed(self, event: MoleculeChanged) -> None:
        if not event.during_edit:
            self.cancel(event.molecule_uuid)
            return
        was_pending = bool(self._pending)
        self._pending[event.molecule_uuid] = None
        if not was_pending:
            self.pending_changed.emit(True)
        delay = self._policy_source().delay_ms()
        if delay is None:
            # Only when asked: no timer, and one already running (the mode was changed
            # while an edit waited) is stopped rather than left to fire.
            self._timer.stop()
            return
        # `start` on a running single-shot timer RESTARTS it: the debounce.
        self._timer.start(delay)

    def _on_molecule_selected(self, _event: MoleculeSelected) -> None:
        self.cancel_all()

    # --- what a person or a caller can do --------------------------------------------

    def has_pending(self) -> bool:
        return bool(self._pending)

    def pending_molecules(self) -> tuple[str, ...]:
        return tuple(self._pending)

    def cancel(self, molecule_uuid: str) -> None:
        """Forget a pending run for one molecule, because something recomputed it."""
        if molecule_uuid not in self._pending:
            return
        del self._pending[molecule_uuid]
        if not self._pending:
            self._timer.stop()
            self.pending_changed.emit(False)

    def cancel_all(self) -> None:
        if not self._pending:
            return
        self._pending.clear()
        self._timer.stop()
        self.pending_changed.emit(False)

    def recalculate_now(self) -> bool:
        """Run what is waiting immediately -- the person asking, in any mode.

        Returns whether there was anything to run, so a caller can say "nothing to
        recalculate" instead of appearing to have done something.
        """
        if not self._pending:
            return False
        self._timer.stop()
        self._fire()
        return True

    # --- firing ------------------------------------------------------------------------

    def _fire(self) -> None:
        due = list(self._pending)
        self._pending.clear()
        if due:
            self.pending_changed.emit(False)
        for molecule_uuid in due:
            self._event_bus.publish(RecalculationDue(molecule_uuid=molecule_uuid))
