from __future__ import annotations

from typing import Callable, TypeVar

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

T = TypeVar("T")

# A bare tuple of exception types, or a single type -- matches the second
# argument shape `except` itself accepts.
ExpectedErrors = type[Exception] | tuple[type[Exception], ...]


class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class PluginAsyncTask(QRunnable):
    """Runs `func()` off the GUI thread and reports the result back via Qt
    signals, which queue safely onto whichever thread connected to them
    (the same cross-thread-safe marshaling `EventBus` itself relies on).

    Extracted after three bundled plugins (`ai_assistant`, `database_search`,
    `reaction_prediction`) each independently reimplemented this exact
    shape for their network/provider calls -- only the specific "expected"
    exception type differed. `expected_errors` is that type (or a tuple of
    types): caught and reported as `str(exc)`; anything else is still
    caught (a `QRunnable` must never let an exception escape the pool) but
    reported with an "Unexpected error: " prefix so it's visibly distinct
    from a provider's own documented failure mode.
    """

    def __init__(self, func: Callable[[], T], expected_errors: ExpectedErrors) -> None:
        super().__init__()
        self._func = func
        self._expected_errors = expected_errors
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            result = self._func()
        except self._expected_errors as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - a QRunnable must never let an exception escape the pool
            self.signals.failed.emit(f"Unexpected error: {exc}")
        else:
            self.signals.finished.emit(result)


# Every caller of `run_async` in this codebase is fire-and-forget — it
# doesn't keep the returned task around (see ai_assistant/database_search/
# reaction_prediction panels' _on_*_clicked methods). `QThreadPool.start()`
# takes C++-side ownership of the QRunnable for auto-delete purposes, but
# that doesn't reliably keep its Python wrapper (and the plain `QObject`
# held in `task.signals`, which has no C++ parent of its own) alive against
# CPython's own refcounting — confirmed directly: a fire-and-forget
# `run_async()` call would non-deterministically never fire its callback,
# because the task (and its signals object) could get garbage collected
# before the worker thread finishes. Keeping a strong reference here for
# the task's actual lifetime, independent of what any caller does with the
# return value, is what makes the fire-and-forget calling convention safe.
_IN_FLIGHT_TASKS: set[PluginAsyncTask] = set()


def run_async(
    func: Callable[[], T],
    expected_errors: ExpectedErrors,
    on_finished: Callable[[T], None],
    on_failed: Callable[[str], None],
) -> PluginAsyncTask:
    """Builds a `PluginAsyncTask`, wires its signals, and starts it on the
    global `QThreadPool`. Safe to call without keeping the returned task —
    see `_IN_FLIGHT_TASKS` above. Still returns the task in case a caller
    has a reason to keep its own reference too.
    """
    task = PluginAsyncTask(func, expected_errors)
    _IN_FLIGHT_TASKS.add(task)

    def _cleanup(_arg: object = None) -> None:
        _IN_FLIGHT_TASKS.discard(task)

    task.signals.finished.connect(on_finished)
    task.signals.finished.connect(_cleanup)
    task.signals.failed.connect(on_failed)
    task.signals.failed.connect(_cleanup)
    QThreadPool.globalInstance().start(task)
    return task
