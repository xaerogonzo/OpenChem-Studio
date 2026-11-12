"""Words the salt-composition window shows. No RDKit, no Qt.

A charge-valid result is never phrased as an isolable salt.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Always the first line of the body. The window exists to compute a
#: composition, and this sentence is what stops that being read as a crystal.
DISCLAIMER = (
    "A charge-balanced composition is not an isolable salt, a crystal, or a 3D ion pair."
)

#: Analyze one drawing's disconnected ions as drawn (Mode B).
MODE_ANALYZE = "analyze"
#: Two molecular neutrals, then B + HA → BH+ + A− (Mode A workflow 1).
MODE_NEUTRALS = "neutrals"
#: Two already-charged species used as given (Mode A workflow 2).
MODE_IONS = "ions"
#: Cartesian product of ionization states of one pair (Mode C).
MODE_ENUMERATE = "enumerate"

#: The four window modes, in the combo's order.
MODES = (
    MODE_ANALYZE,
    MODE_NEUTRALS,
    MODE_IONS,
    MODE_ENUMERATE,
)


@dataclass(frozen=True)
class SaltPreview:
    """What the dialog renders. ``charge_valid`` is None when nothing was balanced."""

    headline: str
    body: str
    charge_valid: bool | None
    mode: str
    notes: tuple[str, ...]


def make_preview(
    mode: str,
    headline: str,
    lines: tuple[str, ...] = (),
    *,
    charge_valid: bool | None = None,
    notes: tuple[str, ...] = (),
) -> SaltPreview:
    body = "\n".join((DISCLAIMER, *lines))
    return SaltPreview(headline, body, charge_valid, mode, notes)
