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
    # The CELL form of `error`. `ScientificResult` carries the same pair
    # for every other result kind; this class predates it and defines its
    # own fields, so the retrofit is written twice by construction rather
    # than by oversight. `describe_failure` is the one reader of both.
    error_summary: str | None = None
    # `.provider`/`.timestamp` above predate `Provenance` (Phase 1 vs
    # Phase 6+) and are left as they are -- this is an additive retrofit,
    # not a replacement. `None` for a QUEUED/RUNNING placeholder (no real
    # result to attribute yet) or anything round-tripped from before this
    # field existed.
    provenance: Provenance | None = None
