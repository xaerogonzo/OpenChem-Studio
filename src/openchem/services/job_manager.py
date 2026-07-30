from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class JobHandle:
    """A single active job's tracked state -- what a Jobs panel (Phase 13)
    lists and cancels through. `message` reuses the same free-text progress
    string every `*JobStateChanged` event already carries (live ORCA
    stdout lines, "3/9 conformers") rather than a second, parallel
    progress-reporting channel.
    """

    kind: str
    key: str
    cancel_callback: Callable[[], None] | None = None
    message: str = ""


class JobManager:
    """Shared registry of in-flight async jobs, keyed by (kind, key).

    Not a scheduling engine -- ConformerService/DockingService/
    QuantumChemistryService each keep their own QRunnable/QProcess
    mechanics untouched. This only answers "is a job with this key already
    running" (the single-flight guard QuantumChemistryService's own
    `_active_jobs` dict almost provided but didn't actually check before
    overwriting, see its request_calculation) and, since Phase 13, tracks
    enough per-job state (a cancel callback, a progress message) for a
    Jobs panel to list and cancel any job type uniformly. `kind` namespaces
    per service ("conformer", "docking", "quantum_chemistry") so two
    services can never collide on the same key by accident.
    """

    def __init__(self) -> None:
        self._active: dict[tuple[str, str], JobHandle] = {}

    def try_start(
        self, kind: str, key: str, cancel_callback: Callable[[], None] | None = None
    ) -> bool:
        """Registers (kind, key) as active and returns True, unless it's
        already active, in which case this is a no-op and returns False.
        `cancel_callback`, if given, is what `cancel()` below invokes --
        omit it for a job type that can't actually be cancelled (nothing
        stops it from still being registered and listed, just not
        cancellable)."""
        job_key = (kind, key)
        if job_key in self._active:
            return False
        self._active[job_key] = JobHandle(kind=kind, key=key, cancel_callback=cancel_callback)
        return True

    def finish(self, kind: str, key: str) -> None:
        self._active.pop((kind, key), None)

    def is_active(self, kind: str, key: str) -> bool:
        return (kind, key) in self._active

    def update_message(self, kind: str, key: str, message: str) -> None:
        handle = self._active.get((kind, key))
        if handle is not None:
            handle.message = message

    def active_jobs(self) -> list[JobHandle]:
        return list(self._active.values())

    def cancel(self, kind: str, key: str) -> bool:
        """Invokes the job's registered cancel callback, if it has one.
        Returns False (a no-op) if the job isn't active or was registered
        without a `cancel_callback` -- callers can't assume every job type
        is actually cancellable."""
        handle = self._active.get((kind, key))
        if handle is None or handle.cancel_callback is None:
            return False
        handle.cancel_callback()
        return True
