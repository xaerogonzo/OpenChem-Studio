"""The appearance choice: what is stored, what a damaged value falls back to, and the pure light/dark decision.

Nothing here touches a window. The service that applies the choice is tested in `test_appearance_service.py`.
"""

from __future__ import annotations

import pytest

from openchem.app.settings import APPEARANCE, PREFERENCES, Settings
from openchem.domain.appearance import (
    Appearance,
    EffectiveAppearance,
    appearance_from_stored,
    effective_from_lightness,
)
from openchem.events.base import EventBus


def test_the_stored_integers_are_a_contract():
    """Changing one would silently flip every saved setting, so the numbers are pinned."""
    assert (int(Appearance.SYSTEM), int(Appearance.LIGHT), int(Appearance.DARK)) == (0, 1, 2)


def test_the_preference_is_registered_and_follows_the_system_by_default():
    assert APPEARANCE in PREFERENCES
    assert APPEARANCE.default == int(Appearance.SYSTEM)
    assert (APPEARANCE.minimum, APPEARANCE.maximum) == (0, 2)


@pytest.mark.parametrize("mode", list(Appearance))
def test_a_stored_choice_reads_back(mode):
    settings = Settings(EventBus())
    settings.set_preference(APPEARANCE, int(mode))
    assert appearance_from_stored(settings.preference(APPEARANCE)) is mode


@pytest.mark.parametrize("damaged", ["", "dark", "3", "-1", "1.5", "True"])
def test_a_damaged_stored_value_falls_back_to_the_system(damaged):
    settings = Settings(EventBus())
    settings.set(APPEARANCE.key, damaged)
    assert appearance_from_stored(settings.preference(APPEARANCE)) is Appearance.SYSTEM


@pytest.mark.parametrize("bare", [None, "", "x", 7, object()])
def test_a_bare_unreadable_value_is_the_system(bare):
    assert appearance_from_stored(bare) is Appearance.SYSTEM


def test_setting_an_out_of_range_choice_raises():
    with pytest.raises(ValueError):
        Settings(EventBus()).set_preference(APPEARANCE, 3)


@pytest.mark.parametrize(
    ("lightness", "expected"),
    [
        (0.0, EffectiveAppearance.DARK),
        (0.12, EffectiveAppearance.DARK),
        (0.49, EffectiveAppearance.DARK),
        (0.5, EffectiveAppearance.LIGHT),
        (0.94, EffectiveAppearance.LIGHT),
        (1.0, EffectiveAppearance.LIGHT),
    ],
)
def test_effective_appearance_from_the_window_colour(lightness, expected):
    assert effective_from_lightness(lightness) is expected
