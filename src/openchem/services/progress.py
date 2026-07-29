from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProgressHandle:
    """Passed into long-running service calls so they can report progress and
    be cancelled, even when today's operation (e.g. computing 12 descriptors)
    finishes instantly. Later, slow operations (conformer generation, docking,
    PubChem search) plug into the same contract with no new API.
    """

    on_progress: Callable[[float, str], None] | None = None
    _cancelled: bool = field(default=False, init=False)

    def report(self, fraction: float, message: str = "") -> None:
        if self.on_progress is not None:
            self.on_progress(fraction, message)

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled
