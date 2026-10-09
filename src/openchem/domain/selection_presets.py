"""Named sets of ticked calculators, and the one-time copy from the Batch panel.

**A PRESET IS A LIST OF CALCULATOR IDS AND NOTHING ELSE.** Ids, never tree
positions or check states, for the reason the batch panel stored ids: the
launcher's order moves when a calculator is added, and a saved position would
then restore somebody else's property. An id that no longer names a calculator
is DROPPED on load rather than reported, because a calculator removed between
launches is not the person's problem.

**THE MIGRATION COPIES, AND NEVER DELETES.** The Batch panel keeps its own
selection under `batch/selected_property_ids`. This reads it once, files the
calculators in it as a preset, and leaves the original key exactly as it was --
so the old panel still works while it exists, and going back to an earlier
build loses nothing. A marker key makes it happen once: without it a person who
then deleted the imported preset would find it back on the next launch, which
is the migration overwriting a choice the person made.

Pure: it takes anything with `get(key, default)` and `set(key, value)` (the
application's `Settings`, or a dict wrapper in a test) and imports no Qt.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Iterable
from typing import Any, Protocol

logger = logging.getLogger("openchem.domain")

#: Where the user's presets live: one JSON object, name -> list of ids.
PRESETS_KEY = "presets/calculator_ticks"
#: Set once the Batch panel's selection has been copied in, whatever it held.
MIGRATED_KEY = "presets/batch_selection_migrated"
#: The key the Batch panel stores its ticked ids under (calculators AND
#: descriptors in one flat list).
LEGACY_BATCH_KEY = "batch/selected_property_ids"
#: What the copied selection is called.
IMPORTED_NAME = "From the Batch panel"


class SettingsLike(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...


def clean_ids(stored: Iterable[Any], known: Collection[str]) -> list[str]:
    """`stored` as a list of unique strings that still name something, in order."""
    seen: set[str] = set()
    kept: list[str] = []
    if isinstance(stored, (str, bytes)) or not hasattr(stored, "__iter__"):
        stored = [stored] if isinstance(stored, str) else []
    for item in stored or ():
        identifier = str(item)
        if identifier in known and identifier not in seen:
            seen.add(identifier)
            kept.append(identifier)
    return kept


class PresetStore:
    """User presets over a settings object. Reads are tolerant, writes are whole."""

    def __init__(self, settings: SettingsLike | None) -> None:
        self._settings = settings

    # -- reading ---------------------------------------------------------------

    def _load(self) -> dict[str, list[str]]:
        if self._settings is None:
            return {}
        try:
            raw = self._settings.get(PRESETS_KEY, "") or ""
            data = json.loads(raw) if isinstance(raw, str) and raw else {}
        except Exception:  # noqa: BLE001 - a damaged preference must not take a feature down
            logger.warning("Could not read the saved calculator presets; starting with none")
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(name): [str(i) for i in ids]
            for name, ids in data.items()
            if isinstance(ids, list)
        }

    def names(self) -> list[str]:
        """Preset names, A to Z (case-folded), so a menu does not reshuffle."""
        return sorted(self._load(), key=lambda name: (name.casefold(), name))

    def ids(self, name: str, known: Collection[str]) -> list[str]:
        """What `name` ticks, with anything that no longer exists dropped."""
        return clean_ids(self._load().get(name, []), known)

    # -- writing ---------------------------------------------------------------

    def _store(self, data: dict[str, list[str]]) -> None:
        if self._settings is None:
            return
        try:
            self._settings.set(PRESETS_KEY, json.dumps(data, sort_keys=True))
        except Exception:  # noqa: BLE001 - a preference is never worth a crash
            logger.debug("Could not save the calculator presets")

    def save(self, name: str, calculator_ids: Iterable[str]) -> bool:
        """Save or replace a preset. False for a blank name or an empty selection."""
        name = (name or "").strip()
        ids = list(dict.fromkeys(str(i) for i in calculator_ids))
        if not name or not ids or self._settings is None:
            return False
        data = self._load()
        data[name] = ids
        self._store(data)
        return True

    def delete(self, name: str) -> bool:
        data = self._load()
        if name not in data:
            return False
        del data[name]
        self._store(data)
        return True

    # -- the one-time copy from the Batch panel ------------------------------------

    def migrate_batch_selection(self, known_calculators: Collection[str]) -> int:
        """Copy the Batch panel's calculators in as a preset, once. Returns how many.

        Descriptor and alert ids in that list have no tick box in Properties
        (the always-on properties are one switch), so they are not carried; the
        count of what WAS carried is what a caller can say. Nothing is deleted
        or rewritten: see the module docstring.
        """
        if self._settings is None:
            return 0
        try:
            if str(self._settings.get(MIGRATED_KEY, "") or "").lower() in ("1", "true"):
                return 0
            legacy = self._settings.get(LEGACY_BATCH_KEY, []) or []
        except Exception:  # noqa: BLE001
            return 0
        if isinstance(legacy, str):
            legacy = [legacy]
        carried = clean_ids(legacy, known_calculators)
        if carried and IMPORTED_NAME not in self._load():
            self.save(IMPORTED_NAME, carried)
        try:
            # Marked even when there was nothing to copy: "nothing" was this
            # launch's answer, and a selection made in the Batch panel LATER
            # must not appear as a surprise preset.
            self._settings.set(MIGRATED_KEY, "1")
        except Exception:  # noqa: BLE001
            logger.debug("Could not record that the batch selection was migrated")
        return len(carried)
