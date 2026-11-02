"""Applies the stored interface size: the application font scaled from the platform's own, and the pixel sizes in stylesheets.

`QApplication.setFont` reaches windows that are already open (measured on the real window in `docs/INTERFACE_SIZE_DESIGN.md`),
so a change needs no restart. The font is always scaled from the platform default captured when the service is built, never
from the current font, so choosing a step twice, or going back to the default, cannot drift. The program has no
application-level style sheet and its per-widget sheets set no font family or point size, which is what makes a plain
`setFont` safe here; the pixel sizes that do exist go through `ui.theme` (`set_scale`).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from openchem.app.settings import INTERFACE_SIZE, Settings
from openchem.domain.interface_size import InterfaceSize, interface_size_from_stored, scale_of
from openchem.events.base import EventBus
from openchem.events.events import SettingsChanged
from openchem.ui import theme

logger = logging.getLogger("openchem.app")


class InterfaceSizeService:
    """See the module docstring."""

    def __init__(self, app: QApplication, settings: Settings, event_bus: EventBus) -> None:
        self._app = app
        self._settings = settings
        self._base = app.font()
        self._applied: InterfaceSize | None = None
        event_bus.subscribe(SettingsChanged, self._on_setting_changed)

    def choice(self) -> InterfaceSize:
        """The stored step; an unreadable value is the default."""
        return interface_size_from_stored(self._settings.preference(INTERFACE_SIZE))

    def start(self) -> None:
        """Apply the stored choice. Called once, before the window is built."""
        self.apply(self.choice())

    def apply(self, size: InterfaceSize) -> None:
        if size is self._applied:
            return
        self._applied = size
        factor = scale_of(size)
        font = self._app.font()
        font.setFamilies(self._base.families())
        if self._base.pointSizeF() > 0:
            font.setPointSizeF(self._base.pointSizeF() * factor)
        elif self._base.pixelSize() > 0:
            font.setPixelSize(max(1, round(self._base.pixelSize() * factor)))
        self._app.setFont(font)
        theme.set_scale(factor)
        # A widget that carries a stylesheet keeps the font it was polished with, so a section header with
        # `QToolButton { font-weight: bold; }` stayed at the old size after a live change (the same trap as
        # the palette's, `theme.repolish_styled_widgets`). Qt hands the new font to widgets from the event loop,
        # so the sheets are set again after it has.
        QTimer.singleShot(0, self._app, theme.repolish_styled_widgets)
        logger.info("Interface size %s (x%.2f)", size.name.lower(), factor)

    def _on_setting_changed(self, event: SettingsChanged) -> None:
        if event.key == INTERFACE_SIZE.key:
            self.apply(self.choice())
