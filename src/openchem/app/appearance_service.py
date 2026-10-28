"""Applies the Light / Dark / System choice and says when the look has settled.

**ONE OWNER.** Settings, the View menu and every painting widget go through here: the choice is
written to `Settings` by whichever control the person used, this service reacts to that write,
and everything that must repaint hears one `AppearanceChanged` with the look that is ON SCREEN.
No widget works out for itself what "System" means.

**QT SAYS "THE SCHEME CHANGED" BEFORE THE PALETTE HAS.** `QStyleHints.colorSchemeChanged` can
arrive while the old palette is still installed, so a colour resolved from it is the previous
look's. The service therefore waits for `ApplicationPaletteChange` (and `StyleChange`), lets the
event loop settle on one tick, and reads the effective look from the palette's window colour.
The scheme signal is only a reason to look again.

**SYSTEM IS REMOVING THE OVERRIDE**, not reading Windows once: `unsetColorScheme()` hands the
decision back to Qt, which then keeps following the operating system.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from openchem.app.settings import APPEARANCE, Settings
from openchem.domain.appearance import (
    Appearance,
    EffectiveAppearance,
    appearance_from_stored,
    effective_from_lightness,
)
from openchem.events.base import EventBus
from openchem.events.events import AppearanceChanged, SettingsChanged
from openchem.ui import theme

logger = logging.getLogger("openchem.app")

#: What a forced choice asks Qt for. SYSTEM is absent on purpose: it is `unsetColorScheme()`.
_FORCED = {Appearance.LIGHT: Qt.ColorScheme.Light, Appearance.DARK: Qt.ColorScheme.Dark}

#: How long the palette is left to finish changing before the look is read. One event-loop tick is
#: enough for Qt's own sequence (scheme, then palette, then style); a few milliseconds also folds the
#: burst a style change sends into one notification.
_SETTLE_MS = 20


class AppearanceService(QObject):
    """See the module docstring."""

    #: The look that is on screen, once it has settled. Also published on the bus as `AppearanceChanged`.
    effective_changed = Signal(object)

    def __init__(self, app: QApplication, settings: Settings, event_bus: EventBus) -> None:
        super().__init__(app)
        self._app = app
        self._settings = settings
        self._event_bus = event_bus
        self._effective = self._read_effective()
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_SETTLE_MS)
        self._settle.timeout.connect(self._publish_if_changed)

        app.installEventFilter(self)
        app.styleHints().colorSchemeChanged.connect(self._schedule)
        event_bus.subscribe(SettingsChanged, self._on_setting_changed)

    # --- what the person chose ---------------------------------------------------------------

    def start(self) -> None:
        """Apply the stored choice. Called once, before the window shows."""
        self.apply(self.choice())
        # Nothing is listening yet and no window is built: take the look as it now is silently, so the
        # first widgets read the real one rather than the look before the choice was applied.
        self._settle.stop()
        self._effective = self._read_effective()
        theme.set_effective(self._effective)

    def choice(self) -> Appearance:
        """The stored choice (System, Light or Dark), which is not the same as the look."""
        return appearance_from_stored(self._settings.preference(APPEARANCE))

    def apply(self, mode: Appearance) -> None:
        """Make Qt use `mode`. System removes the override and keeps following the system."""
        hints = self._hints()
        forced = _FORCED.get(mode)
        if forced is None:
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(forced)
        # A change that leaves the palette as it was sends no palette event, so look again anyway.
        self._schedule()

    def _hints(self):
        """Qt's style hints, behind one name so a test can record what was asked of them: the
        offscreen platform ignores a forced scheme, so the request itself is the thing to check there."""
        return self._app.styleHints()

    def _on_setting_changed(self, event: SettingsChanged) -> None:
        if event.key == APPEARANCE.key:
            self.apply(self.choice())

    # --- what is on screen -------------------------------------------------------------------

    def effective(self) -> EffectiveAppearance:
        """The settled look. A widget built after a switch reads this on construction."""
        return self._effective

    def _read_effective(self) -> EffectiveAppearance:
        window = self._app.palette().color(QPalette.ColorRole.Window)
        return effective_from_lightness(window.lightnessF())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt's own casing
        if watched is self._app and event.type() in (
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._schedule()
        return False

    def _schedule(self, *_ignored) -> None:
        self._settle.start()

    def _publish_if_changed(self) -> None:
        now = self._read_effective()
        if now is self._effective:
            return
        self._effective = now
        logger.info("Appearance settled on %s", now.name.lower())
        # First, so every stylesheet is already rewritten when a listener reacts to the notification.
        theme.set_effective(now)
        self.effective_changed.emit(now)
        self._event_bus.publish(AppearanceChanged(effective=now))
