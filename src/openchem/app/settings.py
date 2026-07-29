from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings

from openchem.events.base import EventBus
from openchem.events.events import SettingsChanged

ORG_NAME = "OpenChemStudio"
APP_NAME = "OpenChemStudio"


class Settings:
    """Typed wrapper over QSettings. Publishes SettingsChanged on every write."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._qsettings = QSettings(ORG_NAME, APP_NAME)

    def get(self, key: str, default: Any = None) -> Any:
        return self._qsettings.value(key, default)

    def set(self, key: str, value: Any) -> None:
        self._qsettings.setValue(key, value)
        self._event_bus.publish(SettingsChanged(key=key))

    @property
    def recent_projects(self) -> list[str]:
        value = self.get("recent_projects", [])
        return list(value) if value else []

    def add_recent_project(self, path: str) -> None:
        recents = [p for p in self.recent_projects if p != path]
        recents.insert(0, path)
        self.set("recent_projects", recents[:10])

    def window_geometry(self) -> bytes | None:
        return self.get("window/geometry", None)

    def set_window_geometry(self, geometry: bytes) -> None:
        self.set("window/geometry", geometry)

    def window_state(self) -> bytes | None:
        return self.get("window/state", None)

    def set_window_state(self, state: bytes) -> None:
        self.set("window/state", state)
