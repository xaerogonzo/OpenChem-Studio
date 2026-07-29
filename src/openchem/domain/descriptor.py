from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.domain.common import CacheState


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
