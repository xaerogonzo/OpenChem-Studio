from __future__ import annotations

from enum import Enum


class CacheState(str, Enum):
    """Lifecycle of an asynchronously computed value (a descriptor, a batch
    of conformers, or any future long-running provider result).

    Modeled explicitly, rather than just holding a value, so slow providers
    (docking, ORCA, AI, conformer search) share one async contract instead
    of each inventing its own.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
