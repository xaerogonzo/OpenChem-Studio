from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CacheState(str, Enum):
    """Lifecycle of a computed descriptor value.

    Modeled explicitly (rather than just holding a value) so slow future
    providers (docking, ORCA, AI) share the same async contract as today's
    fast RDKit descriptors.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class DescriptorValue:
    """A single descriptor result, from any provider (built-in or plugin)."""

    descriptor_id: str
    name: str
    units: str
    category: str
    provider: str
    molecule_uuid: str
    value: Any = None
    timestamp: float | None = None
    cache_state: CacheState = CacheState.QUEUED
    error: str | None = None
