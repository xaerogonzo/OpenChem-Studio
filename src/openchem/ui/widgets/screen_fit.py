"""How large a window may open, given the screen it opens on.

Lifted out of `ui/dialogs/periodic_table_dialog.py`, which was its only
consumer until `PopOutHost` needed the same answer. It moved rather than
being reimplemented because the reason it exists is not specific to any
one window -- a dialog whose minimum exceeds the screen cannot be rescued
by resizing, since `resize()` is clamped to the minimum, which is exactly
how the periodic table's action row ended up unreachable below the bottom
of a 1366x768 laptop.

Nothing here knows about the periodic table, and nothing here knows about
Qt: four integers in, two out. That is what makes it testable at all --
see `fit_within` for why a call site that reads the real screen cannot be
told apart from its own deletion under the suite's platform.
"""

from __future__ import annotations

#: How much of the screen a window may claim when it opens. Not the whole
#: of it: a window flush against every edge is hard to move, and the
#: height leaves room for a title bar the geometry does not include.
#:
#: The justification is about windows in general rather than about any
#: particular one, which is what made this safe to move here along with
#: the function that reads it.
_SCREEN_FRACTION = (0.95, 0.92)


def fit_within(
    width: int, height: int, available_width: int, available_height: int
) -> tuple[int, int]:
    """An opening size that fits the screen, as a pure function.

    Pure so it can be tested at all: the suite's `offscreen` platform
    reports an 800x800 screen, where a large dialog's own minimum is
    larger still, so nothing observable distinguishes calling it from not.
    Deleting the CALL is therefore the one mutation no test through a
    window can catch, and that is written into the guards rather than
    papered over.
    """
    return (
        min(width, int(available_width * _SCREEN_FRACTION[0])),
        min(height, int(available_height * _SCREEN_FRACTION[1])),
    )
