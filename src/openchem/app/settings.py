from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QStandardPaths

from openchem.domain.calculator_support import Visibility, is_visible
from openchem.domain.recalc_policy import (
    DEFAULT_QUIET_MS,
    MAX_QUIET_MS,
    MIN_QUIET_MS,
    RecalcMode,
    RecalcPolicy,
)
from openchem.domain.result_store import MAX_REVISIONS
from openchem.events.base import EventBus
from openchem.events.events import SettingsChanged

logger = logging.getLogger("openchem.app")

ORG_NAME = "OpenChemStudio"
APP_NAME = "OpenChemStudio"


@dataclass(frozen=True)
class Preference:
    """One setting the Settings window offers: its key, type, default and bounds.

    **THE CONTRACT COMES BEFORE ANY CONTROL.** The window and every consumer
    read a preference through this record (`Settings.preference`), so a
    default shown on screen and the default a consumer falls back to cannot
    be two numbers. What is stored is the plain value under a stable key --
    never a label, which the lesson on a choice parameter storing the
    English on the screen records the cost of.
    """

    key: str
    kind: type
    default: bool | int
    minimum: int | None = None
    maximum: int | None = None


#: Whether choosing a right-hand panel hides the other unplaced panels in its
#: area. On is today's behaviour; off means the rail never hides anything.
RAIL_HIDES_PANELS = Preference("ui/rail_hides_panels", bool, True)

#: Whether recovery copies of an unsaved project are written at all.
RECOVERY_ENABLED = Preference("recovery/enabled", bool, True)

#: How long after the last change a recovery copy is written, in seconds.
RECOVERY_DELAY_SECONDS = Preference("recovery/delay_seconds", int, 5, minimum=1, maximum=600)

#: How many revisions of each molecule keep their results in memory for undo,
#: counted separately per calculation input (`SessionResultStore._touch`).
#: The default is the store's own constant, so the two cannot drift.
MAX_REVISIONS_KEPT = Preference("results/max_revisions", int, MAX_REVISIONS, minimum=1, maximum=64)

#: Whether the launcher offers the calculators that are hidden by default
#: (limited, experimental or specialist ones -- `domain.calculator_support`).
#: Off is the default: a calculator that refuses most of what people draw is
#: not everyday equipment. A per-calculator choice overrides it either way.
SHOW_HIDDEN_CALCULATORS = Preference("calculators/show_hidden", bool, False)

#: When a canvas edit makes the application recompute: a `RecalcMode`, stored as its
#: integer (0 while drawing, 1 after a pause, 2 only when asked) and never as a label.
#: The default is the pause: drawing recomputed everything per edit before this existed.
RECALC_MODE = Preference(
    "compute/recalc_mode", int, int(RecalcMode.AFTER_PAUSE),
    minimum=int(min(RecalcMode)), maximum=int(max(RecalcMode)),
)

#: How long after the latest edit a pause counts, in milliseconds, for the "after I
#: pause" mode. Every edit restarts it. The bounds are the domain's, so the control and
#: the policy cannot disagree about what is legal.
RECALC_QUIET_MS = Preference(
    "compute/recalc_quiet_ms", int, DEFAULT_QUIET_MS, minimum=MIN_QUIET_MS, maximum=MAX_QUIET_MS
)

#: Whether a number key over a hovered bond sets its order (1 single, 2 double, 3 triple).
#: On is the default. Off hands the key back to the editor, which does nothing with it over a
#: bond, so the setting only exists for someone whose own habits use those keys otherwise.
DRAWING_BOND_KEYS = Preference("drawing/bond_order_keys", bool, True)

#: Every preference, in the order the Settings window groups them. Tests
#: iterate this, so a preference added here is covered without a new test.
PREFERENCES = (
    RAIL_HIDES_PANELS, RECOVERY_ENABLED, RECOVERY_DELAY_SECONDS, MAX_REVISIONS_KEPT,
    SHOW_HIDDEN_CALCULATORS, RECALC_MODE, RECALC_QUIET_MS, DRAWING_BOND_KEYS,
)

#: Where one calculator's own visibility choice is stored: a plain
#: `"shown"`/`"hidden"` under `calculators/override/<calculator id>`. An
#: absent key means "follow the default", which is different from either.
_CALCULATOR_OVERRIDE_PREFIX = "calculators/override/"

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

    def remove(self, key: str) -> None:
        """Forget a stored value, so the key reads as absent (its default) again."""
        self._qsettings.remove(key)
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

    def forget_last_directory(self, kind: str) -> None:
        """Drop the remembered directory, so the dialog opens at Documents again."""
        key = _directory_key(kind)
        self._qsettings.remove(key)
        self._event_bus.publish(SettingsChanged(key=key))

    # --- preferences ---------------------------------------------------------

    def preference(self, preference: Preference) -> bool | int:
        """The stored value, or the default when it is absent or unreadable.

        **QSETTINGS HANDS BACK WHATEVER THE BACKEND STORED**: an INI file --
        what the suite's `isolated_settings` uses -- returns a stored bool as
        the string ``"true"`` or ``"false"``, where the registry returns a
        real bool (`main_window._as_bool` records the same). So every value is
        parsed rather than trusted. A value that does not parse, or falls
        outside the bounds, is logged and the default used -- a hand-edited
        or damaged setting must not take a feature down with it.
        """
        raw = self.get(preference.key, None)
        if raw is None:
            return preference.default
        value = _parse(preference, raw)
        if value is None:
            logger.warning(
                "Setting %s holds %r, which is not a valid value; using %r",
                preference.key, raw, preference.default,
            )
            return preference.default
        return value

    # --- calculator visibility ------------------------------------------------

    def calculator_override(self, calculator_id: str) -> Visibility | None:
        """This person's own choice for one calculator, or None to follow the default.

        A stored value that is not one of the two names is logged and treated
        as no choice: a damaged setting must not hide or reveal a calculator.
        """
        raw = self.get(_CALCULATOR_OVERRIDE_PREFIX + calculator_id, None)
        if raw is None or str(raw) == "":
            return None
        try:
            return Visibility(str(raw).strip().lower())
        except ValueError:
            logger.warning(
                "Setting %s holds %r, which is not a visibility; following the default",
                _CALCULATOR_OVERRIDE_PREFIX + calculator_id, raw,
            )
            return None

    def set_calculator_override(self, calculator_id: str, visibility: Visibility | None) -> None:
        """Store the choice, or forget it (`None`) so the calculator follows its default."""
        key = _CALCULATOR_OVERRIDE_PREFIX + calculator_id
        if visibility is None:
            self._qsettings.remove(key)
            self._event_bus.publish(SettingsChanged(key=key))
            return
        self.set(key, visibility.value)

    def calculator_is_visible(self, definition) -> bool:
        """Whether the launcher offers `definition`: its default, the master
        toggle, and this person's own choice, in `domain.calculator_support`'s order."""
        return is_visible(
            definition,
            show_hidden=bool(self.preference(SHOW_HIDDEN_CALCULATORS)),
            override=self.calculator_override(definition.calculator_id),
        )

    def reset_calculator_visibility(self, calculator_ids) -> None:
        """Back to the defaults: the master toggle off and every override forgotten."""
        for calculator_id in calculator_ids:
            if self.calculator_override(calculator_id) is not None:
                self.set_calculator_override(calculator_id, None)
        self.set_preference(SHOW_HIDDEN_CALCULATORS, False)

    def recalc_policy(self) -> RecalcPolicy:
        """What the person chose about recomputing while they draw.

        Read at every edit by the scheduler, so a change applies to the very next
        one. A stored value that does not parse falls back to the default inside
        `preference`, so a damaged setting cannot leave drawing without a policy.
        """
        return RecalcPolicy(
            mode=RecalcMode(int(self.preference(RECALC_MODE))),
            quiet_ms=int(self.preference(RECALC_QUIET_MS)),
        )

    def set_preference(self, preference: Preference, value: bool | int) -> None:
        """Store `value`. An invalid one RAISES: a control can only produce a
        valid value, so an invalid one here is a programming error to see."""
        parsed = _parse(preference, value)
        if parsed is None:
            raise ValueError(f"{value!r} is not a valid value for {preference.key}")
        self.set(preference.key, parsed)


def _parse(preference: Preference, raw: Any) -> bool | int | None:
    if preference.kind is bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        return {"true": True, "false": False, "1": True, "0": False}.get(text)
    if preference.kind is int:
        if isinstance(raw, bool):
            return None
        try:
            value = int(str(raw).strip())
        except ValueError:
            return None
        if preference.minimum is not None and value < preference.minimum:
            return None
        if preference.maximum is not None and value > preference.maximum:
            return None
        return value
    return None


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
