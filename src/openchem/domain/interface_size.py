"""How large the interface's text is: what was chosen, and the number it means.

Stored as the integer under a stable key and never as a label or a percentage, so a later build can
change a step's factor without reinterpreting what an installed copy saved. A value that does not
parse, or names no step, is the default.

Pure and Qt-free: the code that applies the choice is `app.interface_size_service`.
"""

from __future__ import annotations

from enum import IntEnum


class InterfaceSize(IntEnum):
    """Stored as its integer under a stable key, never as a label (see `Preference`)."""

    #: The platform's own default font, untouched. What the program did before this existed.
    DEFAULT = 0
    LARGER = 1
    LARGE = 2


#: The factor each step multiplies the platform default font by. Chosen from the spike (`docs/INTERFACE_SIZE_DESIGN.md`):
#: the real window's minimum size grew only about 4% for a 50% larger font, so the layout is not the limit; legibility
#: at the default dock widths is. A 1.5 step was tried and left out: it elided two controls in the Properties panel
#: ("Run on: this molecu...", the batch status line) at the default width, and 1.3 elides only the status line, which
#: keeps its full text on hover by design.
SCALE: dict[InterfaceSize, float] = {
    InterfaceSize.DEFAULT: 1.0,
    InterfaceSize.LARGER: 1.15,
    InterfaceSize.LARGE: 1.3,
}


def interface_size_from_stored(raw: object) -> InterfaceSize:
    """The step a stored value means; anything unreadable is DEFAULT."""
    try:
        return InterfaceSize(int(str(raw).strip()))
    except (ValueError, TypeError):
        return InterfaceSize.DEFAULT


def scale_of(size: InterfaceSize) -> float:
    return SCALE[size]


def scaled_points(base_points: float, size: InterfaceSize) -> float:
    """A point size scaled for `size`; the default step returns it exactly."""
    return base_points if size is InterfaceSize.DEFAULT else base_points * SCALE[size]
