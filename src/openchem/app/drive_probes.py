"""In-process probes for the resource census (`tools/perf_census.py`).

**WHAT THIS IS FOR.** The census samples the process from OUTSIDE (CPU, memory,
handles, child processes). That says THAT something grows or burns CPU; it cannot
say WHICH widget, timer or cache. These probes answer that, and only when a drive
script names one -- nothing here runs in a normal launch, and `debug_drive` imports
this module lazily, from inside the step that needs it.

**NONE OF THESE IS FREE, and that is a rule of the census, not a footnote.**
`gc.get_objects()`, `allWidgets()`, `tracemalloc` and a heartbeat timer each
perturb what they measure. The census therefore runs them as separate arms, never
together for a baseline number, and measures their overhead (scenario S0). Every
function here takes a snapshot at a checkpoint; none starts anything that keeps
running except `HeartbeatProbe`, which exists to run and is stopped by its caller.

**WHAT EACH ONE CAN AND CANNOT SEE** -- worded exactly, because a census that
claims more coverage than it has reads "zero growth" for an object it never saw:

* `object_census` counts the Python-visible `QObject`/`QWidget`/`QTimer` wrappers
  the garbage collector tracks, plus `QApplication.allWidgets()`. It is NOT a
  census of every C++ object: a C++ child with no Python wrapper is invisible to
  the first, and a non-widget one to the second.
* Timers are "active Python-visible `QTimer`s". A `startTimer` id or a timer a C++
  class owns internally does not appear.
* `tracemalloc` sees Python allocations only. Qt, RDKit, Chromium and ORCA memory
  is invisible to it.
"""

from __future__ import annotations

import gc
import statistics
import sys
import threading
import time
import tracemalloc
from collections import Counter
from typing import Any

#: Stall thresholds in milliseconds. 16.7 is one frame at 60 Hz; the others are the
#: steps at which "slow" becomes "frozen" for a person at the canvas.
STALL_THRESHOLDS_MS = (16.7, 50.0, 100.0, 250.0)


def _valid(obj: Any) -> bool:
    """False for a wrapper whose C++ object is gone -- calling anything on one raises."""
    try:
        import shiboken6

        return bool(shiboken6.isValid(obj))
    except Exception:  # noqa: BLE001 - a probe must not stop the run
        return False


def _label(obj: Any) -> str:
    return f"{type(obj).__module__.split('.')[0]}.{type(obj).__name__}"


def _parent_class(obj: Any) -> str:
    try:
        parent = obj.parent()
    except Exception:  # noqa: BLE001
        return "?"
    return type(parent).__name__ if parent is not None else "<none>"


def object_census(top_timers: int = 40, collect: bool = True) -> dict[str, Any]:
    """What is alive now, by class. Take it AT CHECKPOINTS, never once a second.

    `collect` runs `gc.collect()` first so what remains is retained, not merely
    awaiting collection. That is the diagnostic's one deliberate side effect and the
    report records that it ran.
    """
    from PySide6.QtCore import QObject, QThread, QThreadPool, QTimer
    from PySide6.QtWidgets import QApplication

    started = time.perf_counter()
    if collect:
        gc.collect()

    widgets = Counter()
    visible = Counter()
    for widget in QApplication.allWidgets():
        if not _valid(widget):
            continue
        name = type(widget).__name__
        widgets[name] += 1
        try:
            if widget.isVisible():
                visible[name] += 1
        except RuntimeError:
            pass

    qobjects = Counter()
    timers_total = 0
    active_timers: list[dict[str, Any]] = []
    pools: list[dict[str, Any]] = []
    qthreads: list[dict[str, Any]] = []
    for obj in gc.get_objects():
        try:
            if not isinstance(obj, QObject) or not _valid(obj):
                continue
        except Exception:  # noqa: BLE001 - some tracked objects raise on isinstance
            continue
        qobjects[type(obj).__name__] += 1
        if isinstance(obj, QTimer):
            timers_total += 1
            try:
                if obj.isActive():
                    active_timers.append({
                        "interval_ms": obj.interval(),
                        "single_shot": obj.isSingleShot(),
                        "remaining_ms": obj.remainingTime(),
                        "parent": _parent_class(obj),
                        "object_name": obj.objectName(),
                        "visible_owner": _owner_visible(obj),
                    })
            except RuntimeError:
                pass
        elif isinstance(obj, QThreadPool):
            pools.append({
                "active": obj.activeThreadCount(), "max": obj.maxThreadCount(),
                "global": obj is QThreadPool.globalInstance(),
                "object_name": obj.objectName(),
            })
        elif isinstance(obj, QThread):
            qthreads.append({
                "running": obj.isRunning(), "object_name": obj.objectName(),
                "parent": _parent_class(obj),
            })

    # Repeating timers first, fastest first: those are what an idle CPU number
    # can be made of.
    active_timers.sort(key=lambda t: (t["single_shot"], t["interval_ms"]))
    python_threads = [
        {"name": t.name, "daemon": t.daemon, "alive": t.is_alive()} for t in threading.enumerate()
    ]
    return {
        "widget_total": sum(widgets.values()),
        "widgets": dict(widgets.most_common()),
        "widgets_visible": dict(visible.most_common()),
        "qobject_wrappers_total": sum(qobjects.values()),
        "qobject_wrappers": dict(qobjects.most_common()),
        "timers_python_visible": timers_total,
        "timers_active": len(active_timers),
        "timers_active_detail": active_timers[:top_timers],
        "thread_pools_observed": pools,
        "qthreads_observed": qthreads,
        "python_threads": python_threads,
        "gc_forced": bool(collect),
        "scan_ms": round((time.perf_counter() - started) * 1000.0, 1),
    }


def _owner_visible(timer: Any) -> bool | None:
    """Whether the widget a timer hangs off is on screen: a repeating timer under a
    hidden panel is the polling-while-hidden case."""
    parent = timer.parent()
    while parent is not None:
        if hasattr(parent, "isVisible"):
            try:
                return bool(parent.isVisible())
            except RuntimeError:
                return None
        parent = parent.parent()
    return None


class HeartbeatProbe:
    """The event loop's own heartbeat, started and stopped by the caller.

    A QTimer whose gaps say how long the loop was blocked: a blocked edit is one
    long gap, which is what "the canvas froze" is. **It is itself a repeating
    timer**, so it adds idle wakeups; the census never runs it in an idle-CPU arm.
    """

    def __init__(self, interval_ms: int = 10) -> None:
        from PySide6.QtCore import QTimer

        self.interval_ms = interval_ms
        self._gaps: list[float] = []
        self._last = time.perf_counter()
        self._timer = QTimer()
        self._timer.setInterval(interval_ms)
        # A bound method, never a lambda capturing self (PySide6 holds a plain
        # callable strongly -- tests/test_qt_object_disposal.py).
        self._timer.timeout.connect(self._beat)

    def _beat(self) -> None:
        now = time.perf_counter()
        self._gaps.append((now - self._last) * 1000.0)
        self._last = now

    def start(self) -> None:
        self._gaps.clear()
        self._last = time.perf_counter()
        self._timer.start()

    def stop(self) -> dict[str, Any]:
        self._timer.stop()
        # A stall is the gap beyond the interval the timer asked for.
        stalls = sorted(max(0.0, gap - self.interval_ms) for gap in self._gaps)

        def percentile(fraction: float) -> float:
            return stalls[min(len(stalls) - 1, int(fraction * len(stalls)))] if stalls else 0.0

        return {
            "interval_ms": self.interval_ms,
            "beats": len(self._gaps),
            "stall_ms": {
                "p50": round(percentile(0.50), 1), "p95": round(percentile(0.95), 1),
                "p99": round(percentile(0.99), 1),
                "max": round(stalls[-1], 1) if stalls else 0.0,
                "mean": round(statistics.fmean(stalls), 2) if stalls else 0.0,
            },
            "stalls_over_ms": {
                str(limit): sum(1 for s in stalls if s > limit) for limit in STALL_THRESHOLDS_MS
            },
        }


class AllocationProbe:
    """`tracemalloc`, filtered to this project. Python allocations only."""

    def __init__(self) -> None:
        self._baseline: tracemalloc.Snapshot | None = None

    @property
    def running(self) -> bool:
        return tracemalloc.is_tracing()

    def start(self, frames: int = 8) -> None:
        if not tracemalloc.is_tracing():
            tracemalloc.start(frames)
        gc.collect()
        self._baseline = tracemalloc.take_snapshot()

    def diff(self, limit: int = 20) -> dict[str, Any]:
        if self._baseline is None or not tracemalloc.is_tracing():
            return {"error": "tracemalloc is not running"}
        gc.collect()
        now = tracemalloc.take_snapshot()
        keep = [tracemalloc.Filter(True, "*openchem*")]
        stats = now.filter_traces(keep).compare_to(self._baseline.filter_traces(keep), "lineno")
        current, peak = tracemalloc.get_traced_memory()

        def row(stat: Any) -> dict[str, Any]:
            frame = stat.traceback[0]
            path = frame.filename.replace(chr(92), "/").split("openchem/")[-1]
            return {
                "where": f"{path}:{frame.lineno}",
                "size_diff_kib": round(stat.size_diff / 1024.0, 1),
                "count_diff": stat.count_diff,
            }

        by_size = sorted(stats, key=lambda s: s.size_diff, reverse=True)[:limit]
        by_count = sorted(stats, key=lambda s: s.count_diff, reverse=True)[:limit]
        return {
            "traced_current_kib": round(current / 1024.0, 1),
            "traced_peak_kib": round(peak / 1024.0, 1),
            "top_by_size": [row(s) for s in by_size],
            "top_by_count": [row(s) for s in by_count],
            "limitation": "Python allocations only; native Qt/RDKit/WebEngine memory is not traced",
        }

    def stop(self) -> None:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        self._baseline = None


def resolve_attribute_path(root: Any, path: str) -> Any:
    """`"_services.recalc_scheduler._queue"` from `root`. Attributes only -- a probe
    that evaluated expressions would be an interpreter in the app."""
    value = root
    for part in path.split("."):
        value = getattr(value, part)
    return value


def cache_size(value: Any) -> dict[str, Any]:
    """The size of one named container, shallow. Only for caches the static survey
    flagged; this is not a generic object inspector."""
    out: dict[str, Any] = {"type": type(value).__name__}
    try:
        out["len"] = len(value)
    except TypeError:
        out["len"] = None
    out["shallow_bytes"] = sys.getsizeof(value)
    return out
