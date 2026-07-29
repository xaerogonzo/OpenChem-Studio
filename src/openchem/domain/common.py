from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


@dataclass(frozen=True)
class Provenance:
    """What produced a scientific result, with what parameters, when —
    used on new Phase 6+ domain models (starting with `DockingResultModel`)
    so every generated result can answer "what produced this." Not a
    retrofit of Phase 1-5 fields (`ConformerModel.method`/`.timestamp`,
    `DescriptorValue.provider`/`.timestamp` already exist and are left as
    they are — this is for new models going forward, not existing ones.
    """

    created_by: str  # plugin_id, or "core"
    method: str  # e.g. "vina-python", "vina-executable"
    parameters: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_by": self.created_by,
            "method": self.method,
            "parameters": self.parameters,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        return cls(
            created_by=data["created_by"],
            method=data["method"],
            parameters=dict(data.get("parameters", {})),
            timestamp=data.get("timestamp", 0.0),
        )
