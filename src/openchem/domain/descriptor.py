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
    # WHY IT FAILED, in the only sense a view can act on: is this a fault
    # or a limit of the method?
    #
    # `False` (the default) means a FAULT -- something broke, or the input
    # is invalid, and the user may be able to do something about it.
    # "Needs a 3D conformer" is a fault in this sense: it names an action.
    #
    # `True` means the METHOD DOES NOT COVER THIS MOLECULE, which is a
    # correct and permanent statement rather than something going wrong.
    # Joback has no group for a ring tertiary amine; Kamlet-Jacobs needs a
    # measured loading density that no structure can supply. Painting
    # those the same red as a crash is what made two working calculators
    # read as broken.
    #
    # DECLARED BY THE PRODUCER, never sniffed from the message. `if "no
    # group for" in error` as application logic is exactly what
    # `joback.refusal_text` exists to prevent. Optional and defaulting to
    # today's behaviour, for the same reason `error_summary` is: every
    # producer that declines to declare one is completely unmoved.
    inapplicable: bool = False
    # `.provider`/`.timestamp` above predate `Provenance` (Phase 1 vs
    # Phase 6+) and are left as they are -- this is an additive retrofit,
    # not a replacement. `None` for a QUEUED/RUNNING placeholder (no real
    # result to attribute yet) or anything round-tripped from before this
    # field existed.
    provenance: Provenance | None = None
