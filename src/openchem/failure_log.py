"""What "the same failure" means for a log record, and not saying it five times.

**THE SAME DEFECT LOGS A DIFFERENT MESSAGE EVERY TIME.** A live session drew a
nitramine and the Console filled with five identical tracebacks in forty
seconds, one per edit -- and the message differed on each ("atoms [1, 2]",
then "[1, 3]", ...). So two records are the same failure when they share
(level, logger, exception type, innermost frame, message with its numbers and
uuids collapsed): WHERE it happened, not what it said. The innermost frame is
what keeps two genuinely different failures that share a first line apart --
they raise from different places.

This one definition serves two consumers and must not be written twice:
`app.drive_ledger` counts distinct failures for a driven run's verdict, and
`CollapseRepeatedFailures` stops one failure filling a log. Two definitions
would be two answers to "is this the same problem?", and a run's verdict could
say "one failure" of a log that printed it forty times.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

#: A molecule or result uuid, which differs in every occurrence of one defect.
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
#: Any run of digits: an atom index, a count, a step number. Collapsed so the
#: same defect at atoms [1, 7] and [1, 3] is one entry.
_NUMBER = re.compile(r"\d+")


def _shorten(path: str) -> str:
    """A path as it should read in a report: from the package down.

    An absolute path names the machine, and the same defect on two machines
    would then be two entries.
    """
    normal = path.replace("\\", "/")
    marker = "/openchem/"
    if marker in normal:
        return "openchem/" + normal.split(marker, 1)[1]
    return normal.rsplit("/", 1)[-1]


def _normalise(text: str) -> str:
    """The message with what varies between two occurrences of one defect removed."""
    return _NUMBER.sub("#", _UUID.sub("<uuid>", text))


@dataclass(frozen=True)
class FailureDescription:
    """A log record reduced to what identifies the problem it reports."""

    exception: str
    origin: str
    #: The first line of the message, joined with the exception's own text when
    #: there is one: the log line is usually the same every time ("Alert
    #: computation failed") and the exception text is what says what was wrong.
    first_line: str

    @property
    def message_key(self) -> str:
        return _normalise(self.first_line)


def describe(record: logging.LogRecord) -> FailureDescription:
    """`record` as a `FailureDescription`."""
    try:
        message = record.getMessage()
    except Exception:  # noqa: BLE001 - a malformed record is still evidence
        message = str(record.msg)
    first_line = message.splitlines()[0] if message else ""
    if record.exc_info and record.exc_info[1] is not None:
        traceback = record.exc_info[2]
        origin = f"{_shorten(record.pathname)}:{record.lineno}"
        while traceback is not None:
            origin = f"{_shorten(traceback.tb_frame.f_code.co_filename)}:{traceback.tb_lineno}"
            traceback = traceback.tb_next
        detail = str(record.exc_info[1]).strip().splitlines()
        if detail:
            first_line = f"{first_line} | {detail[0]}"
        return FailureDescription(type(record.exc_info[1]).__name__, origin, first_line)
    return FailureDescription("", f"{_shorten(record.pathname)}:{record.lineno}", first_line)


def failure_key(record: logging.LogRecord) -> tuple[str, str, str, str, str]:
    """The identity of the problem `record` reports. See the module docstring."""
    description = describe(record)
    return (record.levelname, record.name, description.exception, description.origin, description.message_key)


#: How long a repeated traceback stays collapsed. Long enough to cover a burst
#: of edits, short enough that a failure which is still happening minutes later
#: shows itself again.
COLLAPSE_WINDOW_SECONDS = 30.0
#: Distinct failures remembered. A loop that logs a new failure every pass must
#: not grow this without bound; the oldest is forgotten, which costs at worst
#: one repeated traceback.
_MAX_TRACKED = 200


@dataclass
class _Window:
    started: float
    suppressed: int = 0
    announced: bool = False


class CollapseRepeatedFailures(logging.Filter):
    """Lets one traceback of a repeating failure through per window, and SAYS the rest were collapsed.

    **IT NEVER HIDES SILENTLY.** The first repeat inside a window logs one line
    ("further identical tracebacks are collapsed for 30 s"), and the first
    record of the next window says how many were collapsed in the last. What is
    dropped is the repeated traceback -- a failure cannot fill a log -- and
    never the fact that it repeated.

    **ONE INSTANCE IS SHARED BY EVERY HANDLER** (`collapse_filter()`), and it
    remembers its last decision by record identity. A `LogRecord` is one object
    handed to each handler in turn; per-handler instances would each count it as
    an occurrence (so the console would collapse while the file did not) and
    each announce it (three copies of the announcement, each reaching three
    handlers). Only records with a traceback at ERROR or above are subject to it:
    a failure with no traceback is one line and needs no collapsing.

    It does not mutate the record. Records are shared between handlers, so
    rewriting one for the sake of one handler would rewrite it for all.
    """

    def __init__(
        self,
        window_seconds: float = COLLAPSE_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self._window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple, _Window] = {}
        self._decided: tuple[logging.LogRecord, bool] | None = None

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.ERROR or not record.exc_info or record.exc_info[1] is None:
            return True
        notice: str | None = None
        with self._lock:
            if self._decided is not None and self._decided[0] is record:
                return self._decided[1]
            keep, notice = self._decide(record)
            self._decided = (record, keep)
        if notice:
            # AFTER the lock, and through the normal path: it is an ordinary
            # WARNING without a traceback, so this filter waves it through.
            logging.getLogger("openchem.logging").warning("%s", notice)
        return keep

    def _decide(self, record: logging.LogRecord) -> tuple[bool, str | None]:
        key = failure_key(record)
        now = self._clock()
        window = self._windows.get(key)
        first_line = describe(record).first_line
        if window is None or now - window.started >= self._window:
            previous = window.suppressed if window is not None else 0
            if len(self._windows) >= _MAX_TRACKED and key not in self._windows:
                self._windows.pop(next(iter(self._windows)))
            self._windows[key] = _Window(started=now)
            notice = (
                f"{previous} identical failure(s) were collapsed in the previous "
                f"{self._window:g} s: {first_line}"
            ) if previous else None
            return True, notice
        window.suppressed += 1
        if not window.announced:
            window.announced = True
            return False, (
                f"This failure repeated; further identical tracebacks are collapsed for "
                f"{self._window:g} s: {first_line}"
            )
        return False, None


#: The instance every handler shares (`collapse_filter`).
_SHARED = CollapseRepeatedFailures()


def collapse_filter() -> CollapseRepeatedFailures:
    """The one filter every handler shares. See `CollapseRepeatedFailures`."""
    return _SHARED
