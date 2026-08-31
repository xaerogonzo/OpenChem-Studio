from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QStandardPaths

from openchem.events.base import EventBus
from openchem.events.events import SettingsChanged

ORG_NAME = "OpenChemStudio"
APP_NAME = "OpenChemStudio"

#: What a remembered file-dialog directory can be ABOUT.
#:
#: Separate memories rather than one, because a project library and a
#: structure folder are different places: importing a PDB must not move the
#: Open Project dialog to wherever that PDB lived.
#:
#: **CLOSED, AND ENFORCED AT RUNTIME.** The failure of an open vocabulary
#: here is silent -- a typo'd kind gets its own private settings key, so the
#: dialog quietly stops remembering anything and no test anywhere goes red.
#: Same fail-closed rule as the `**OPNE**` marker in the DEFERRALS parse: a
#: typo must be an error, never "nothing matched".
DIRECTORY_KINDS = frozenset({"project", "molecule", "macromolecule"})

#: Characters Windows refuses in a filename. A project may legitimately be
#: called "5-HT2A / 6WGT", and a suggested save name built from it has to
#: survive that rather than producing a path the dialog cannot open.
_UNSAFE_IN_A_FILENAME = '<>:"/\\|?*'


def _directory_key(kind: str) -> str:
    if kind not in DIRECTORY_KINDS:
        raise ValueError(
            f"unknown directory kind {kind!r}; expected one of "
            f"{sorted(DIRECTORY_KINDS)}"
        )
    return f"paths/last_{kind}_directory"


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

    def last_directory(self, kind: str) -> str:
        """Where a dialog of this `kind` last landed, or "" if never."""
        return str(self.get(_directory_key(kind), "") or "")

    def set_last_directory(self, kind: str, path: str) -> None:
        self.set(_directory_key(kind), path)


# --- where a file dialog should open -------------------------------------
#
# PURE FUNCTIONS OVER A `Settings`, deliberately, and not methods on the
# window. The decision is the part worth testing and a `QFileDialog` is the
# part that cannot be, so the logic lives where a test can reach it without
# one -- the same two-level split `ui/visual_check.py` uses for its
# predicates and its extraction.


def dialog_start_directory(settings: Settings, kind: str) -> str:
    """The directory a `kind` dialog should open at.

    Falls back to Documents rather than to Qt's own default, which is the
    process working directory -- the repository root when the app is
    launched from a checkout, and never where anybody keeps their files.
    That was the whole complaint.

    A remembered directory that NO LONGER EXISTS is discarded rather than
    handed to Qt: a folder that has since been moved or deleted sends the
    dialog somewhere arbitrary, which is worse than the default it replaced.
    """
    stored = settings.last_directory(kind)
    if stored and Path(stored).is_dir():
        return stored
    return QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )


def remember_chosen_path(settings: Settings, kind: str, chosen: str) -> None:
    """Record the DIRECTORY holding a file the user just chose.

    The parent, never the file itself -- a stored file path would be handed
    back to the next dialog as its starting directory, which Qt cannot open.

    An empty `chosen` means the dialog was CANCELLED and records nothing.
    Without that, backing out of Save would move the remembered directory as
    surely as completing it.
    """
    if not chosen:
        return
    settings.set_last_directory(kind, str(Path(chosen).parent))


def suggested_save_path(settings: Settings, kind: str, name: str, suffix: str) -> str:
    """A starting path for a Save dialog: the remembered directory, and a
    filename built from `name`.

    Qt takes a full path here and pre-fills the name box from it, so this is
    one value rather than two arguments.
    """
    directory = dialog_start_directory(settings, kind)
    stem = "".join("_" if c in _UNSAFE_IN_A_FILENAME else c for c in name).strip()
    if not stem:
        return directory
    return str(Path(directory) / f"{stem}{suffix}")
