"""Named tick sets, and the one-time, non-destructive copy from the Batch panel."""

from __future__ import annotations

import pytest

from openchem.domain.selection_presets import (
    IMPORTED_NAME,
    LEGACY_BATCH_KEY,
    MIGRATED_KEY,
    MIGRATED_PROPERTIES_KEY,
    PRESETS_KEY,
    PresetStore,
    clean_ids,
)

KNOWN = {"a", "b", "c"}
#: Always-on property and alert-catalog ids, which a preset can now hold too.
PROPS = {"mol_wt", "pains"}


class _Settings:
    def __init__(self, **values):
        self.values = dict(values)
        self.writes: list[str] = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.writes.append(key)
        self.values[key] = value


def test_ids_are_cleaned_to_unique_known_strings_in_order():
    assert clean_ids(["b", "gone", "a", "b", 7], KNOWN) == ["b", "a"]
    assert clean_ids(None, KNOWN) == []


def test_a_saved_preset_round_trips_and_names_sort_case_insensitively():
    store = PresetStore(_Settings())
    assert store.save("zeta", ["a", "b"]) and store.save("Alpha", ["c"])
    assert store.names() == ["Alpha", "zeta"]
    assert store.ids("zeta", KNOWN) == ["a", "b"]


def test_a_preset_drops_what_no_longer_exists_on_load_but_keeps_it_stored():
    settings = _Settings()
    PresetStore(settings).save("old", ["a", "retired"])
    assert PresetStore(settings).ids("old", KNOWN) == ["a"]
    assert "retired" in settings.values[PRESETS_KEY], "loading must not rewrite the stored preset"


@pytest.mark.parametrize("name,ids", [("", ["a"]), ("  ", ["a"]), ("x", [])])
def test_a_blank_name_or_an_empty_selection_is_not_a_preset(name, ids):
    settings = _Settings()
    assert PresetStore(settings).save(name, ids) is False
    assert settings.writes == []


def test_delete_removes_one_and_reports_a_missing_one():
    store = PresetStore(_Settings())
    store.save("x", ["a"])
    assert store.delete("x") is True and store.delete("x") is False
    assert store.names() == []


def test_a_damaged_stored_value_means_no_presets_not_a_crash():
    for bad in ("{not json", "[1, 2]", 5, None):
        store = PresetStore(_Settings(**{PRESETS_KEY: bad}))
        assert store.names() == []


def test_no_settings_at_all_is_an_empty_store():
    store = PresetStore(None)
    assert store.names() == [] and store.save("x", ["a"]) is False
    assert store.migrate_batch_selection(KNOWN) == 0


# --- the migration ------------------------------------------------------------------


def test_the_batch_selection_is_copied_in_once_and_left_exactly_as_it_was():
    legacy = ["mol_wt", "a", "c", "gone"]  # a descriptor, two calculators, one retired
    settings = _Settings(**{LEGACY_BATCH_KEY: list(legacy)})
    store = PresetStore(settings)
    assert store.migrate_batch_selection(KNOWN) == 2
    assert store.ids(IMPORTED_NAME, KNOWN) == ["a", "c"]
    assert settings.values[LEGACY_BATCH_KEY] == legacy, "the old key must not be touched"
    assert LEGACY_BATCH_KEY not in settings.writes


def test_the_migration_is_idempotent_and_does_not_undo_a_deletion():
    settings = _Settings(**{LEGACY_BATCH_KEY: ["a"]})
    store = PresetStore(settings)
    store.migrate_batch_selection(KNOWN)
    store.delete(IMPORTED_NAME)
    assert store.migrate_batch_selection(KNOWN) == 0
    assert store.names() == [], "a deleted import came back"


def test_an_empty_legacy_selection_still_marks_the_migration_done():
    settings = _Settings()
    PresetStore(settings).migrate_batch_selection(KNOWN)
    assert settings.values[MIGRATED_KEY] == "1"
    # ...so a selection made in the Batch panel LATER is not a surprise preset.
    settings.values[LEGACY_BATCH_KEY] = ["a"]
    assert PresetStore(settings).migrate_batch_selection(KNOWN) == 0


@pytest.mark.parametrize("legacy", ["a", ["a", "a", "a"], "not-an-id", 3, ["", None]])
def test_malformed_legacy_values_are_tolerated(legacy):
    settings = _Settings(**{LEGACY_BATCH_KEY: legacy})
    PresetStore(settings).migrate_batch_selection(KNOWN)  # must not raise
    assert settings.values[MIGRATED_KEY] == "1"


def test_an_existing_preset_with_the_imported_name_is_not_overwritten():
    settings = _Settings(**{LEGACY_BATCH_KEY: ["a"]})
    store = PresetStore(settings)
    store.save(IMPORTED_NAME, ["b", "c"])
    store.migrate_batch_selection(KNOWN)
    assert store.ids(IMPORTED_NAME, KNOWN) == ["b", "c"]


# --- the properties the first copy dropped ------------------------------------------------


def test_the_copy_carries_property_and_alert_ids_when_properties_can_hold_them():
    legacy = ["mol_wt", "a", "pains", "c", "gone"]
    settings = _Settings(**{LEGACY_BATCH_KEY: list(legacy)})
    store = PresetStore(settings)

    assert store.migrate_batch_selection(KNOWN, PROPS) == 4

    assert store.ids(IMPORTED_NAME, KNOWN | PROPS) == ["mol_wt", "a", "pains", "c"]
    assert settings.values[LEGACY_BATCH_KEY] == legacy
    assert settings.values[MIGRATED_PROPERTIES_KEY] == "1"


def test_a_first_copy_made_before_properties_existed_is_upgraded_if_untouched():
    legacy = ["mol_wt", "a", "pains"]
    settings = _Settings(**{LEGACY_BATCH_KEY: legacy})
    store = PresetStore(settings)
    store.migrate_batch_selection(KNOWN)  # the old behaviour: calculators only
    assert store.ids(IMPORTED_NAME, KNOWN | PROPS) == ["a"]

    assert store.migrate_batch_selection(KNOWN, PROPS) == 3

    assert store.ids(IMPORTED_NAME, KNOWN | PROPS) == ["mol_wt", "a", "pains"]


def test_an_imported_preset_the_person_changed_is_not_upgraded():
    settings = _Settings(**{LEGACY_BATCH_KEY: ["mol_wt", "a", "b"]})
    store = PresetStore(settings)
    store.migrate_batch_selection(KNOWN)
    store.save(IMPORTED_NAME, ["c"])

    assert store.migrate_batch_selection(KNOWN, PROPS) == 0

    assert store.ids(IMPORTED_NAME, KNOWN | PROPS) == ["c"]


def test_a_deleted_imported_preset_does_not_come_back_with_the_upgrade():
    settings = _Settings(**{LEGACY_BATCH_KEY: ["mol_wt", "a"]})
    store = PresetStore(settings)
    store.migrate_batch_selection(KNOWN)
    store.delete(IMPORTED_NAME)

    store.migrate_batch_selection(KNOWN, PROPS)

    assert store.names() == []


def test_the_upgrade_happens_once():
    settings = _Settings(**{LEGACY_BATCH_KEY: ["mol_wt", "a"]})
    store = PresetStore(settings)
    store.migrate_batch_selection(KNOWN)
    store.migrate_batch_selection(KNOWN, PROPS)
    store.save(IMPORTED_NAME, ["a"])  # the person narrows it again afterwards

    assert store.migrate_batch_selection(KNOWN, PROPS) == 0
    assert store.ids(IMPORTED_NAME, KNOWN | PROPS) == ["a"]


def test_calling_without_properties_never_uses_up_the_upgrade():
    settings = _Settings(**{LEGACY_BATCH_KEY: ["mol_wt", "a"]})
    store = PresetStore(settings)

    store.migrate_batch_selection(KNOWN)

    assert MIGRATED_PROPERTIES_KEY not in settings.values


def test_the_module_imports_no_qt():
    import inspect

    from openchem.domain import selection_presets

    assert "PySide6" not in inspect.getsource(selection_presets)
