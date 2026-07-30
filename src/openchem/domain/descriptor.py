from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.domain.common import CacheState, Provenance


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
    # `.provider`/`.timestamp` above predate `Provenance` (Phase 1 vs
    # Phase 6+) and are left as they are -- this is an additive retrofit,
    # not a replacement. `None` for a QUEUED/RUNNING placeholder (no real
    # result to attribute yet) or anything round-tripped from before this
    # field existed.
    provenance: Provenance | None = None
