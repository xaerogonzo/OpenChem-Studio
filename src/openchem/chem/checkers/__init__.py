"""The core checkers.

One module per source of opinion, registered together. A plugin adds its
own by calling `registry.register(...)` with its checkers -- it does not
need to be listed here, and it does not need to be appended to an ordering
either, because run order is derived from what each checker declares it
requires.
"""

from __future__ import annotations

from typing import Any

from openchem.chem.checkers import geometry, representation, valence


def register_core_checkers(registry: Any) -> None:
    valence.register(registry)
    representation.register(registry)
    geometry.register(registry)
