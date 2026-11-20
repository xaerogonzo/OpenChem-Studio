"""An engine a geometry optimization could be started with, and whether it can be now."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizeChoice:
    """One quantum-chemistry engine offered for optimizing a conformer.

    `available` False carries the reason in `reason` (the sentence a person is shown beside the greyed entry), so a menu can
    offer the engine and say why it cannot be used yet instead of leaving it out.
    """

    provider_id: str
    name: str
    available: bool
    reason: str = ""
