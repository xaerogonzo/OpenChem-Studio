"""When a structural edit makes the application recompute.

**DRAWING WAS RECOMPUTING EVERYTHING ON EVERY EDIT**, and the measurement that
motivated this file is in `benchmarks/visual/README.md`: twelve edits of aspirin, a
new structure each time, cost a median 1.1 s each with the event loop blocked for up
to 4 s, and a full descriptor fan-out per edit -- fifty results, twelve times, for
eleven structures nobody wanted. A person building a molecule does not want any of
those answers until they stop.

The policy is one of three behaviours and a delay, never a fourth:

    while drawing      a run per event-loop turn (quiet period 0)
    after I pause      a run once no edit has arrived for the quiet period (default)
    only when I ask    no automatic run; results read stale until asked

The **quiet period runs from the most recent structural edit**, and every edit
restarts it -- a debounce, not a throttle: a slow steady drawing rate must not fire a
recompute every N milliseconds, which is exactly the behaviour being removed.

Pure and Qt-free: the scheduler that acts on it is `services.recalc_scheduler`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class RecalcMode(IntEnum):
    """Stored as its integer under a stable key, never as a label (see `Preference`)."""

    #: Recompute as soon as the event loop is free.
    WHILE_DRAWING = 0
    #: Recompute once drawing pauses. The default.
    AFTER_PAUSE = 1
    #: Never automatically; the person asks.
    ON_REQUEST = 2


#: The default quiet period, in milliseconds: long enough that a bond and the atom
#: bolted onto it are one run, short enough that stopping to look is not a wait.
DEFAULT_QUIET_MS = 800

#: The shortest quiet period. Zero is legal, and is what "while drawing" means.
MIN_QUIET_MS = 0

#: The longest quiet period: above five seconds it stops being a pause and becomes
#: "when I ask".
MAX_QUIET_MS = 5000


@dataclass(frozen=True)
class RecalcPolicy:
    """What the person chose: a mode, and how long a pause counts as stopping."""

    mode: RecalcMode = RecalcMode.AFTER_PAUSE
    quiet_ms: int = DEFAULT_QUIET_MS

    def delay_ms(self) -> int | None:
        """How long after the latest edit the recompute is due, or None for never.

        `while drawing` is a zero delay whatever `quiet_ms` holds: the delay control
        belongs to "after I pause", and a stale value left in it must not slow the
        mode that asks for none.
        """
        if self.mode is RecalcMode.ON_REQUEST:
            return None
        if self.mode is RecalcMode.WHILE_DRAWING:
            return 0
        return max(MIN_QUIET_MS, min(MAX_QUIET_MS, int(self.quiet_ms)))
