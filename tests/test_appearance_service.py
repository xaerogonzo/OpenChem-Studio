"""`AppearanceService`: what it asks of Qt, and how it publishes the look once that has SETTLED.

Two layers, because Qt's `offscreen` platform (the suite's default) IGNORES a forced colour scheme:
`setColorScheme` leaves `colorScheme()` Unknown and the palette untouched there, so a test that forces
Dark and expects a dark window can only pass on a real platform.

* Platform-independent tests record the request made of `QStyleHints`, and stand in for the platform
  by installing a palette -- which is what Windows does when its theme changes, and exactly the event
  the service waits for.
* Real-platform tests force the scheme and read the palette. They skip on `offscreen`; run them with
  `QT_QPA_PLATFORM=windows`. The driven script `benchmarks/visual/appearance.json` covers the same on
  the real window.
"""

from __future__ import annotations

import conftest
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest

from openchem.app.appearance_service import AppearanceService
from openchem.app.settings import APPEARANCE, Settings
from openchem.domain.appearance import Appearance, EffectiveAppearance
from openchem.events.base import EventBus
from openchem.events.events import AppearanceChanged

_SETTLE_WAIT_MS = 120


class _RecordingHints:
    """Stands in for `QStyleHints`: remembers what was asked and does nothing else."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def setColorScheme(self, scheme) -> None:  # noqa: N802 - Qt's own casing
        self.calls.append(f"set:{scheme.name}")

    def unsetColorScheme(self) -> None:  # noqa: N802
        self.calls.append("unset")


def _palette(dark: bool) -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e" if dark else "#f3f3f3"))
    return palette


@pytest.fixture
def service(qapp, cheap_repolish):
    bus = EventBus()
    settings = Settings(bus)
    svc = AppearanceService(qapp, settings, bus)
    svc.bus = bus
    svc.settings = settings
    svc.heard = []
    bus.subscribe(AppearanceChanged, lambda event: svc.heard.append(event.effective))
    original = qapp.palette()
    yield svc
    qapp.styleHints().unsetColorScheme()
    if qapp.palette() != original:
        # Only when a test installed one: every live widget in the process is handed the palette, which
        # costs seconds once earlier tests have left windows behind.
        qapp.setPalette(original)
        _settle(svc)


@pytest.fixture
def fake_look(service):
    """The service reading a look the test sets, so no palette is installed on the whole application.

    `QApplication.setPalette` reaches every live widget, about 4 s a call with the windows a long shard has
    left behind. A test about the settle period and change detection does not need the real palette; the
    ones about the real palette ask for it (`qapp`) and keep their `setPalette`.
    """
    state = {"dark": False}
    service._read_effective = lambda: EffectiveAppearance.DARK if state["dark"] else EffectiveAppearance.LIGHT
    service._effective = service._read_effective()
    service.heard.clear()
    return state


def _look_becomes(svc, state, dark: bool) -> None:
    """The look changing, then the settle period passing: what a palette event leads to."""
    state["dark"] = dark
    svc._schedule()
    _settle(svc)


def _settle(svc) -> None:
    """Let the settle period pass, however long a loaded run takes to deliver the palette event."""
    QTest.qWait(_SETTLE_WAIT_MS)
    waited = 0
    while svc._settle.isActive() and waited < 3000:
        QTest.qWait(20)
        waited += 20


def _platform_sets(qapp, svc, dark: bool) -> None:
    """The platform installing a palette, then the settle period passing."""
    qapp.setPalette(_palette(dark))
    _settle(svc)


# --- what it asks of Qt ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (Appearance.LIGHT, ["set:Light"]),
        (Appearance.DARK, ["set:Dark"]),
        (Appearance.SYSTEM, ["unset"]),
    ],
)
def test_each_choice_makes_the_right_request(service, mode, expected):
    hints = _RecordingHints()
    service._hints = lambda: hints

    service.apply(mode)

    assert hints.calls == expected


def test_system_never_pins_a_scheme(service):
    """Reading Windows once and forcing the answer would stop following it; System removes the override."""
    hints = _RecordingHints()
    service._hints = lambda: hints

    for mode in (Appearance.DARK, Appearance.SYSTEM, Appearance.LIGHT, Appearance.SYSTEM):
        service.apply(mode)

    assert hints.calls == ["set:Dark", "unset", "set:Light", "unset"]


def test_a_change_of_the_stored_choice_is_applied(service):
    hints = _RecordingHints()
    service._hints = lambda: hints

    service.settings.set_preference(APPEARANCE, int(Appearance.DARK))

    assert hints.calls == ["set:Dark"]


def test_an_unrelated_setting_asks_nothing_of_qt(service):
    hints = _RecordingHints()
    service._hints = lambda: hints

    service.settings.set("some/other_key", 1)

    assert hints.calls == []


def test_a_damaged_stored_choice_is_the_system(service):
    hints = _RecordingHints()
    service._hints = lambda: hints
    service.settings.set(APPEARANCE.key, "damaged")  # the write itself is applied too
    hints.calls.clear()

    service.start()

    assert hints.calls == ["unset"]


# --- when it speaks --------------------------------------------------------------------------


def test_a_dark_palette_is_announced_once_after_it_is_installed(qapp, service):
    _platform_sets(qapp, service, dark=False)
    service.heard.clear()

    _platform_sets(qapp, service, dark=True)

    assert service.effective() is EffectiveAppearance.DARK
    assert service.heard == [EffectiveAppearance.DARK]


def test_the_announcement_comes_after_the_palette_not_before(qapp, service):
    """A listener that reads the palette when told must see the NEW one: Qt's scheme signal can come first."""
    _platform_sets(qapp, service, dark=False)
    seen = []
    service.bus.subscribe(
        AppearanceChanged,
        lambda event: seen.append(qapp.palette().color(QPalette.ColorRole.Window).lightnessF() < 0.5),
    )

    _platform_sets(qapp, service, dark=True)

    assert seen == [True]


def test_a_burst_of_palette_changes_settles_on_the_last_one(service, fake_look):
    for dark in (True, False, True, False, True):
        fake_look["dark"] = dark
        service._schedule()
    _settle(service)

    assert service.heard == [EffectiveAppearance.DARK]


def test_a_palette_change_that_keeps_the_look_says_nothing(service, fake_look):
    _look_becomes(service, fake_look, dark=True)
    service.heard.clear()

    _look_becomes(service, fake_look, dark=True)

    assert service.heard == []


def test_dark_light_dark_light_announces_each_real_change(service, fake_look):
    for dark in (True, False, True, False):
        _look_becomes(service, fake_look, dark=dark)

    assert service.heard == [
        EffectiveAppearance.DARK,
        EffectiveAppearance.LIGHT,
        EffectiveAppearance.DARK,
        EffectiveAppearance.LIGHT,
    ]


def test_start_reads_the_look_quietly(qapp, service):
    """Nothing is built when `start` runs, so there is nobody to tell; the look must still be read right."""
    qapp.setPalette(_palette(True))
    service.heard.clear()

    service.start()
    _settle(service)

    assert service.heard == []
    assert service.effective() is EffectiveAppearance.DARK


# --- the real platform -----------------------------------------------------------------------

needs_real_platform = pytest.mark.skipif(
    conftest.grid_platform_is_offscreen(),
    reason="the offscreen platform ignores a forced colour scheme; run these on the windows platform",
)


def _window_is_dark(qapp) -> bool:
    return qapp.palette().color(QPalette.ColorRole.Window).lightnessF() < 0.5


def _apply(svc, mode):
    svc.apply(mode)
    _settle(svc)


@needs_real_platform
def test_forcing_dark_darkens_the_real_palette(qapp, service):
    _apply(service, Appearance.LIGHT)
    service.heard.clear()

    _apply(service, Appearance.DARK)

    assert _window_is_dark(qapp)
    assert service.heard == [EffectiveAppearance.DARK]


@needs_real_platform
def test_light_dark_system_repeatedly_leaves_no_residue(qapp, service):
    """System removes the override, so the palette is the one a fresh process starts with, every time."""
    _apply(service, Appearance.SYSTEM)
    baseline = qapp.palette().color(QPalette.ColorRole.Window).name()

    for _ in range(3):
        for mode in (Appearance.LIGHT, Appearance.DARK, Appearance.SYSTEM):
            _apply(service, mode)
        assert qapp.palette().color(QPalette.ColorRole.Window).name() == baseline


@needs_real_platform
def test_system_hands_the_scheme_back(qapp, service):
    _apply(service, Appearance.DARK)
    assert qapp.styleHints().colorScheme() is Qt.ColorScheme.Dark

    _apply(service, Appearance.SYSTEM)

    assert qapp.styleHints().colorScheme() is not Qt.ColorScheme.Dark or _platform_is_dark()


def _platform_is_dark() -> bool:
    """Whether Windows itself is in dark mode (a developer machine may be)."""
    import winreg

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    )
    return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
