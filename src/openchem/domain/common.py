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
    first used on Phase 6+ domain models (starting with `DockingResultModel`)
    so every generated result can answer "what produced this," later
    retrofitted (Phase 9.5) onto `ConformerModel`/`DescriptorValue` as an
    additive optional field alongside their own pre-existing `.method`/
    `.timestamp`/`.provider` fields, not a replacement for them.
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


@dataclass(frozen=True, kw_only=True)
class ScientificResult:
    """Shared shape for a computed scientific output that isn't a bare
    scalar. `DescriptorValue` (one number per descriptor) predates this and
    keeps its own directly-defined `provenance`/`timestamp`/`cache_state`
    fields rather than being retrofitted to compose this — no behavior
    change for existing callers, it's simply the same shape by convention.
    New result kinds that don't fit a single scalar (per-atom datasets,
    categorical alerts, spectra — see `PerAtomDataset`, `AlertResult`,
    `SpectrumResult`) build on this instead of each inventing their own
    provenance/timestamp/status shape independently.

    `kw_only=True` so subclasses can add their own required fields (a
    dataclass can't otherwise mix required subclass fields after
    already-defaulted base fields — every field here has a default so
    plain positional inheritance would force subclasses to default
    everything too, including fields that should stay required).
    """

    provenance: Provenance | None = None
    timestamp: float = field(default_factory=time.time)
    cache_state: CacheState = CacheState.COMPLETED
