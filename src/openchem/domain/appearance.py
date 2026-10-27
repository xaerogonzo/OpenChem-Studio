"""Which colour scheme the person chose, and which one is actually showing.

Two different things, kept apart on purpose:

    Appearance            what was CHOSEN and stored: follow Windows, always light, always dark
    EffectiveAppearance   what is ON SCREEN: light or dark, never "system"

"System" is a choice, not a look. With System chosen the window can be either, and changes
while the program runs when Windows does, so nothing that paints may be keyed on the choice.

Pure and Qt-free: the code that applies the choice is `app.appearance_service`.
"""

from __future__ import annotations

from enum import IntEnum


class Appearance(IntEnum):
    """Stored as its integer under a stable key, never as a label (see `Preference`)."""

    #: Follow the operating system, and keep following it. The default.
    SYSTEM = 0
    LIGHT = 1
    DARK = 2


class EffectiveAppearance(IntEnum):
    """The look the window actually has right now."""

    LIGHT = 1
    DARK = 2


#: A window background whose lightness (0 black .. 1 white) falls below this reads as dark.
#: The palettes in play sit far from it either way (Windows light is about 0.94, dark about 0.12).
_DARK_BELOW_LIGHTNESS = 0.5


def appearance_from_stored(raw: object) -> Appearance:
    """The choice a stored value means; anything unreadable is SYSTEM.

    `Settings.preference` already falls back to the default for a value that does not parse
    or is out of range; this is the same rule for a caller that holds a bare value, so a
    damaged setting can never leave the window without a scheme.
    """
    try:
        return Appearance(int(str(raw).strip()))
    except (ValueError, TypeError):
        return Appearance.SYSTEM


def effective_from_lightness(window_lightness: float) -> EffectiveAppearance:
    """Light or dark from the lightness (0..1) of the application's window colour."""
    if window_lightness < _DARK_BELOW_LIGHTNESS:
        return EffectiveAppearance.DARK
    return EffectiveAppearance.LIGHT
