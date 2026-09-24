"""The Settings window, and every setting changing exactly what it names.

Four layers, each tested where it lives:

* the CONTRACT (`app/settings.Preference`): defaults are today's behaviour,
  values survive the INI backend the suite uses, damage reads as the default;
* the CONSUMERS: the result store, its service, the rail and recovery;
* the WINDOW: every control reads and writes through the contract, and the
  one destructive change asks first;
* the ROUTES: Edit > Settings, Tools > External Tools and both Configure
  buttons open it where they should.

Settings go through the autouse `isolated_settings` fixture, never the
registry.
"""

from __future__ import annotations

import logging

import pytest
from PySide6.QtWidgets import QMessageBox

import conftest
from openchem.app.settings import (
    DIRECTORY_KINDS,
    MAX_REVISIONS_KEPT,
    PREFERENCES,
    RAIL_HIDES_PANELS,
    RECALC_MODE,
    RECALC_QUIET_MS,
    RECOVERY_DELAY_SECONDS,
    RECOVERY_ENABLED,
    Settings,
)
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import CacheState
from openchem.domain.project import ProjectModel
from openchem.domain.recalc_policy import RecalcMode
from openchem.domain.result_store import (
    MAX_REVISIONS,
    BundlePart,
    BundleState,
    ResultIdentity,
    SessionResultStore,
    StoredResult,
)
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.events.events import SettingsChanged
from openchem.ui.dialogs.settings_dialog import (
    DIRECTORY_LABELS,
    EXTERNAL_TOOLS,
    FILE_DIALOGS,
    PANELS,
    RESULTS,
    SECTIONS,
    SettingsDialog,
)


def _stored(result_id, calculation_input, fingerprint, molecule_uuid="m") -> StoredResult:
    return StoredResult(
        identity=ResultIdentity(molecule_uuid, result_id, calculation_input, fingerprint, "producer"),
        result=PerAtomDataset(
            property_id=result_id, name=result_id, units="", method="", molecule_uuid=molecule_uuid,
            values={0: 1.0}, cache_state=CacheState.COMPLETED,
        ),
    )


def _drawing_revisions(store, count, molecule_uuid="m") -> None:
    for index in range(count):
        store.put(_stored("a", DRAWING, f"d{index}", molecule_uuid))


# --- the contract -------------------------------------------------------------


def test_every_default_is_todays_behaviour():
    """The window must change nothing until somebody uses it.

    Each number is the behaviour that shipped before the setting existed:
    the rail hid panels, recovery was on, `enable_recovery`'s delay was
    5000 ms, and the store kept `MAX_REVISIONS`.
    """
    assert RAIL_HIDES_PANELS.default is True
    assert RECOVERY_ENABLED.default is True
    assert RECOVERY_DELAY_SECONDS.default == 5
    assert MAX_REVISIONS_KEPT.default == MAX_REVISIONS == 8
    # Recalculation is the one setting whose default CHANGES behaviour: drawing used to
    # recompute on every edit. It is a pause of 800 ms, the plan's stated default.
    assert RECALC_MODE.default == int(RecalcMode.AFTER_PAUSE)
    assert RECALC_QUIET_MS.default == 800


def test_the_stored_keys_are_stable_names():
    """A key is what an installed copy has already stored. Renaming one
    silently resets that setting for everybody, so the names are pinned."""
    assert {p.key for p in PREFERENCES} == {
        "ui/rail_hides_panels",
        "recovery/enabled",
        "recovery/delay_seconds",
        "results/max_revisions",
        "calculators/show_hidden",
        "compute/recalc_mode",
        "compute/recalc_quiet_ms",
        "drawing/bond_order_keys",
    }


@pytest.mark.parametrize("preference", PREFERENCES, ids=lambda p: p.key)
def test_an_absent_setting_reads_as_its_default(qapp, preference):
    assert Settings(EventBus()).preference(preference) == preference.default


@pytest.mark.parametrize("preference", PREFERENCES, ids=lambda p: p.key)
def test_a_value_survives_the_ini_backend_with_its_type(qapp, preference):
    """The suite's INI file hands every value back as a STRING -- a stored
    False comes back "false", which `bool()` reads as True. A fresh
    `Settings` reads the file, not the first one's memory."""
    value = (not preference.default) if preference.kind is bool else preference.maximum
    Settings(EventBus()).set_preference(preference, value)

    read = Settings(EventBus()).preference(preference)

    assert read == value and type(read) is preference.kind


@pytest.mark.parametrize(
    ("preference", "damaged"),
    [
        (RAIL_HIDES_PANELS, "sometimes"),
        (RECOVERY_ENABLED, "2"),
        (RECOVERY_DELAY_SECONDS, "0"),
        (RECOVERY_DELAY_SECONDS, "601"),
        (MAX_REVISIONS_KEPT, "eight"),
        (MAX_REVISIONS_KEPT, "65"),
    ],
)
def test_a_damaged_value_reads_as_the_default_and_says_so(qapp, caplog, preference, damaged):
    settings = Settings(EventBus())
    settings.set(preference.key, damaged)

    with caplog.at_level(logging.WARNING, logger="openchem.app"):
        assert settings.preference(preference) == preference.default
    assert preference.key in caplog.text


def test_an_invalid_value_is_refused_rather_than_stored(qapp):
    settings = Settings(EventBus())
    with pytest.raises(ValueError):
        settings.set_preference(MAX_REVISIONS_KEPT, 0)
    with pytest.raises(ValueError):
        settings.set_preference(RAIL_HIDES_PANELS, "yes please")
    assert settings.get(MAX_REVISIONS_KEPT.key) is None


def test_forgetting_a_directory_removes_it_and_announces_it(qapp):
    bus = EventBus()
    settings = Settings(bus)
    settings.set_last_directory("project", "C:/somewhere")
    heard = []
    bus.subscribe(SettingsChanged, heard.append)

    settings.forget_last_directory("project")

    assert settings.last_directory("project") == ""
    assert [event.key for event in heard] == ["paths/last_project_directory"]


# --- the store ------------------------------------------------------------------


def test_a_conformer_search_never_evicts_the_drawing_still_on_screen():
    """THE DEFECT A LOWER LIMIT WOULD HAVE MADE COMMON.

    Every conformer change reruns the descriptors on GEOMETRY, so each search
    is a new geometry fingerprint while the drawing's stays put. With one
    revision list for both, measured before the fix: the drawing's results
    were gone after 8 searches at the default, and after ONE at a limit of 1.
    """
    for limit in (1, MAX_REVISIONS):
        store = SessionResultStore("project")
        store.set_max_revisions(limit)
        store.put(_stored("hand_run", DRAWING, "drawing"))
        store.record_part("m", BundlePart("provider", "drawing", ("hand_run",)))
        for search in range(MAX_REVISIONS + 3):
            store.put(_stored("shape", GEOMETRY, f"conformer{search}"))

        assert store.fresh_results("m", {DRAWING: "drawing"}), f"evicted at limit {limit}"
        assert store.bundle_state("m", "drawing", {"provider"})[0] is BundleState.COMPLETE


def test_lowering_the_limit_trims_at_once_and_keeps_the_newest():
    store = SessionResultStore("project")
    _drawing_revisions(store, 6)

    store.set_max_revisions(2)

    assert [f"d{i}" for i in range(6) if store.fresh_results("m", {DRAWING: f"d{i}"})] == ["d4", "d5"]


def test_a_trimmed_drawing_revision_takes_its_part_and_a_geometry_one_does_not():
    store = SessionResultStore("project")
    for fingerprint in ("old", "new"):
        store.put(_stored("a", DRAWING, fingerprint))
        store.record_part("m", BundlePart("provider", fingerprint, ("a",)))
    store.put(_stored("shape", GEOMETRY, "g-old"))
    store.put(_stored("shape", GEOMETRY, "g-new"))

    store.set_max_revisions(1)

    assert store.bundle_state("m", "old", {"provider"})[0] is not BundleState.COMPLETE
    assert store.bundle_state("m", "new", {"provider"})[0] is BundleState.COMPLETE
    assert store.fresh_results("m", {GEOMETRY: "g-old"}) == []
    assert store.fresh_results("m", {GEOMETRY: "g-new"})


def test_a_geometry_run_on_the_drawing_is_evicted_without_taking_the_drawings_results():
    """ONE FINGERPRINT, TWO INPUTS. A GEOMETRY run with no usable conformer
    falls back to the drawing and is recorded under the drawing's own
    fingerprint. When conformer searches push that out of GEOMETRY's count,
    only the GEOMETRY entry may go: the same string under DRAWING is still
    the structure on screen, and so is its part."""
    store = SessionResultStore("project")
    store.set_max_revisions(1)
    store.put(_stored("hand_run", DRAWING, "drawing"))
    store.record_part("m", BundlePart("provider", "drawing", ("hand_run",)))
    store.put(_stored("shape", GEOMETRY, "drawing"))  # the fallback
    store.put(_stored("shape", GEOMETRY, "conformer"))

    assert store.fresh_results("m", {GEOMETRY: "drawing"}) == []
    assert [s.identity.result_id for s in store.fresh_results("m", {DRAWING: "drawing"})] == ["hand_run"]
    assert store.bundle_state("m", "drawing", {"provider"})[0] is BundleState.COMPLETE


def test_the_eviction_count_is_what_trimming_then_removes():
    store = SessionResultStore("project")
    _drawing_revisions(store, 5, "m1")
    _drawing_revisions(store, 2, "m2")
    for search in range(4):
        store.put(_stored("shape", GEOMETRY, f"g{search}", "m2"))

    assert store.revisions_beyond(3) == (2 + 1, 2)  # m1: 2 drawing; m2: 1 geometry
    assert store.revisions_beyond(8) == (0, 0)


def test_raising_the_limit_brings_nothing_back():
    store = SessionResultStore("project")
    _drawing_revisions(store, 4)
    store.set_max_revisions(1)
    store.set_max_revisions(8)
    assert store.fresh_results("m", {DRAWING: "d0"}) == []


def test_a_limit_below_one_is_refused():
    with pytest.raises(ValueError):
        SessionResultStore("project").set_max_revisions(0)


def test_a_saved_file_holds_only_each_inputs_current_revision():
    """WHY "SAVE WITH 8, REOPEN WITH 3" CANNOT OVERFLOW. Every save passes the
    current fingerprints, so no file carries more than one revision of each
    input -- which any limit of at least 1 keeps."""
    store = SessionResultStore("project")
    _drawing_revisions(store, 6)
    store.put(_stored("shape", GEOMETRY, "g1"))
    store.put(_stored("shape", GEOMETRY, "g2"))

    written = store.to_dict({"m": {DRAWING: "d5", GEOMETRY: "g2"}})

    fingerprints = {entry["input_fingerprint"] for entry in written["molecules"]["m"]["results"]}
    assert fingerprints == {"d5", "g2"}


# --- the service ----------------------------------------------------------------


def _service(qapp, limit=None):
    from openchem.chem.engine import ChemistryEngine
    from openchem.services.result_store_service import ResultStoreService

    bus = EventBus()
    settings = Settings(bus)
    if limit is not None:
        settings.set_preference(MAX_REVISIONS_KEPT, limit)
    service = ResultStoreService(bus, ChemistryEngine(), settings)
    return service, settings


def test_the_service_starts_its_store_at_the_setting(qapp):
    service, _settings = _service(qapp, limit=3)
    assert service.store.max_revisions == 3


def test_a_store_loaded_from_a_file_gets_the_setting_not_the_default(qapp):
    """`from_dict` builds its store at `MAX_REVISIONS`. Opening a project must
    not quietly keep 8 while the setting says 3."""
    service, _settings = _service(qapp, limit=3)
    project = ProjectModel(name="saved")
    loaded = SessionResultStore.from_dict(None, project.uuid)
    assert loaded.max_revisions == MAX_REVISIONS

    service.set_project(project, loaded)

    assert service.store is loaded and loaded.max_revisions == 3


def test_changing_the_setting_trims_the_open_store_at_once(qapp):
    service, settings = _service(qapp)
    service.set_project(ProjectModel(name="p"))
    _drawing_revisions(service.store, 6)

    settings.set("some/other_key", 1)
    assert service.store.revisions_beyond(0)[0] == 6

    settings.set_preference(MAX_REVISIONS_KEPT, 2)
    assert service.store.max_revisions == 2
    assert service.store.revisions_beyond(0)[0] == 2


def test_the_container_hands_the_service_its_settings(qapp):
    """THROUGH `build_service_container`, because a service constructed with
    settings in a test proves nothing about the one the app builds."""
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    Settings(services.event_bus).set_preference(MAX_REVISIONS_KEPT, 4)

    assert services.result_store_service.store.max_revisions == 4


# --- the window's consumers ---------------------------------------------------


def _build_window(qapp, tmp_path, **preferences):
    """A real MainWindow, with `preferences` stored BEFORE it is built."""
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    for preference, value in preferences.items():
        settings.set_preference(PREFERENCE_BY_NAME[preference], value)
    window = MainWindow(services, settings, SessionManager())
    window.resize(1600, 900)
    window.show()
    _settle(qapp)
    return window


PREFERENCE_BY_NAME = {
    "rail_hides_panels": RAIL_HIDES_PANELS,
    "recovery_enabled": RECOVERY_ENABLED,
    "recovery_delay_seconds": RECOVERY_DELAY_SECONDS,
}


def _close(window) -> None:
    """Close without the unsaved-changes question.

    `closeEvent` asks only a window that is visible, and these are shown so
    docks have real geometry -- so one a test made dirty would stop the run
    on a modal nobody can answer. Measured: it hung this file.
    """
    window.hide()
    window.close()


def _settle(qapp) -> None:
    for _ in range(10):
        qapp.processEvents()


def _shown_right_docks(window) -> list[str]:
    return [dock.objectName() for dock in window._right_docks if not dock.isHidden()]


def test_the_rail_hides_the_other_panels_by_default(qapp, tmp_path):
    window = _build_window(qapp, tmp_path)
    window._on_panel_chosen("Results")
    _settle(qapp)
    assert _shown_right_docks(window) == ["Results"]
    _close(window)


def test_with_the_setting_off_choosing_a_panel_keeps_the_first(qapp, tmp_path):
    window = _build_window(qapp, tmp_path)
    window._settings.set_preference(RAIL_HIDES_PANELS, False)

    window._on_panel_chosen("Results")
    _settle(qapp)

    assert _shown_right_docks(window) == ["Properties", "Results"]
    assert window.dock_layout_report()["overlaps"] == []
    _close(window)


def test_with_the_setting_off_the_window_still_opens_and_resets_on_one_panel(qapp, tmp_path):
    """The window's OWN arranging is not the rail. Without the exemption the
    setting would open eleven panels at launch and on every reset."""
    window = _build_window(qapp, tmp_path, rail_hides_panels=False)
    assert _shown_right_docks(window) == ["Properties"]

    window._on_panel_chosen("Jobs")
    window.reset_panel_layout()
    _settle(qapp)

    assert _shown_right_docks(window) == ["Properties"]
    _close(window)


def _recovery(window, tmp_path, **kwargs):
    from openchem.services.recovery_service import RecoveryService

    service = RecoveryService(window._services.project_service, tmp_path / "recovery")
    window.enable_recovery(service, **kwargs)
    return service


def test_recovery_off_writes_nothing_and_stops_a_queued_write(qapp, tmp_path):
    window = _build_window(qapp, tmp_path)
    service = _recovery(window, tmp_path, delay_ms=60_000)
    window._session.mark_dirty()
    window._schedule_recovery()
    assert window._recovery_timer.isActive()

    window._settings.set_preference(RECOVERY_ENABLED, False)
    window._write_recovery()  # the queued write, firing after the change
    window._schedule_recovery()

    assert service.candidates() == []
    assert not window._recovery_timer.isActive()
    _close(window)


def test_recovery_on_still_writes(qapp, tmp_path):
    """The other half of the pair, so the test above cannot pass because
    nothing here writes at all."""
    window = _build_window(qapp, tmp_path)
    service = _recovery(window, tmp_path, delay_ms=0)
    window._session.mark_dirty()
    window._schedule_recovery()
    _settle(qapp)

    assert len(service.candidates()) == 1
    _close(window)


def test_the_delay_follows_the_setting_from_the_next_change(qapp, tmp_path):
    window = _build_window(qapp, tmp_path, recovery_delay_seconds=7)
    _recovery(window, tmp_path)
    assert window._recovery_timer.interval() == 7000

    window._settings.set_preference(RECOVERY_DELAY_SECONDS, 30)
    window._session.mark_dirty()
    window._schedule_recovery()

    assert window._recovery_timer.interval() == 30_000
    window._recovery_timer.stop()
    _close(window)


# --- the window -----------------------------------------------------------------


@pytest.fixture
def dialogs():
    built = []
    yield built
    for dialog in built:
        conftest.dispose(dialog)


def _dialog(dialogs, settings, **kwargs) -> SettingsDialog:
    dialog = SettingsDialog(settings, **kwargs)
    dialogs.append(dialog)
    return dialog


def test_the_sections_are_listed_in_order_and_open_by_id(qapp, dialogs):
    dialog = _dialog(dialogs, Settings(EventBus()), section=RESULTS)
    assert [dialog._sections.item(i).text() for i in range(dialog._sections.count())] == [
        label for _id, label in SECTIONS
    ]
    assert dialog.current_section() == RESULTS
    assert dialog._pages.currentIndex() == [s for s, _l in SECTIONS].index(RESULTS)

    with pytest.raises(ValueError):
        dialog.show_section("reuslts")


def test_the_controls_show_what_is_stored(qapp, dialogs):
    settings = Settings(EventBus())
    settings.set_preference(RAIL_HIDES_PANELS, False)
    settings.set_preference(RECOVERY_ENABLED, False)
    settings.set_preference(RECOVERY_DELAY_SECONDS, 42)
    settings.set_preference(MAX_REVISIONS_KEPT, 12)

    dialog = _dialog(dialogs, settings)

    assert not dialog._rail_hides_panels.isChecked()
    assert not dialog._recovery_enabled.isChecked()
    assert dialog._recovery_delay.value() == 42 and not dialog._recovery_delay.isEnabled()
    assert dialog._max_revisions.value() == 12
    assert (dialog._recovery_delay.minimum(), dialog._recovery_delay.maximum()) == (1, 600)
    assert (dialog._max_revisions.minimum(), dialog._max_revisions.maximum()) == (1, 64)


def test_each_control_stores_what_it_names(qapp, dialogs):
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings)

    dialog._rail_hides_panels.setChecked(False)
    dialog._recovery_enabled.setChecked(False)
    assert not dialog._recovery_delay.isEnabled()
    dialog._recovery_enabled.setChecked(True)
    dialog._recovery_delay.setValue(90)

    assert settings.preference(RAIL_HIDES_PANELS) is False
    assert settings.preference(RECOVERY_ENABLED) is True
    assert settings.preference(RECOVERY_DELAY_SECONDS) == 90


def test_the_recalculation_controls_show_and_store_what_they_name(qapp, dialogs):
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings, section="recalculation")
    assert dialog._recalc_mode.currentData() == int(RecalcMode.AFTER_PAUSE)
    assert dialog._recalc_delay.value() == 800 and dialog._recalc_delay.isEnabled()
    assert (dialog._recalc_delay.minimum(), dialog._recalc_delay.maximum()) == (0, 5000)

    dialog._recalc_delay.setValue(1500)
    assert settings.preference(RECALC_QUIET_MS) == 1500

    dialog._recalc_mode.setCurrentIndex(dialog._recalc_mode.findData(int(RecalcMode.ON_REQUEST)))
    assert settings.preference(RECALC_MODE) == int(RecalcMode.ON_REQUEST)
    assert not dialog._recalc_delay.isEnabled(), "the delay belongs to After I pause only"
    assert settings.recalc_policy().delay_ms() is None


def test_the_recalculation_page_shows_a_stored_choice(qapp, dialogs):
    settings = Settings(EventBus())
    settings.set_preference(RECALC_MODE, int(RecalcMode.WHILE_DRAWING))
    settings.set_preference(RECALC_QUIET_MS, 300)
    dialog = _dialog(dialogs, settings)
    assert dialog._recalc_mode.currentData() == int(RecalcMode.WHILE_DRAWING)
    assert dialog._recalc_delay.value() == 300 and not dialog._recalc_delay.isEnabled()


def _asked(monkeypatch, answer=QMessageBox.StandardButton.Yes, during=None):
    """Answer every question with `answer`, recording the text asked."""
    asked: list[str] = []

    def question(_parent, _title, text, *_args, **_kwargs):
        asked.append(text)
        if during is not None and len(asked) == 1:
            during()
        return answer

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def _commit(dialog, value) -> None:
    dialog._max_revisions.setValue(value)
    dialog._max_revisions.editingFinished.emit()


def test_raising_the_limit_stores_without_asking(qapp, dialogs, monkeypatch):
    """WITHOUT a store, deliberately. With one, a raise would count nothing
    to remove and skip the question anyway, so asking on a raise could only
    ever show where there is no store to count."""
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings)
    asked = _asked(monkeypatch)

    _commit(dialog, 20)

    assert asked == [] and settings.preference(MAX_REVISIONS_KEPT) == 20


def test_lowering_says_what_goes_and_trims_only_on_yes(qapp, dialogs, monkeypatch):
    service, settings = _service(qapp)
    service.set_project(ProjectModel(name="p"))
    _drawing_revisions(service.store, 6, "m1")
    _drawing_revisions(service.store, 4, "m2")
    dialog = _dialog(dialogs, settings, result_store_service=service)

    asked = _asked(monkeypatch, QMessageBox.StandardButton.No)
    _commit(dialog, 3)
    assert len(asked) == 1 and "4 older result sets for 2 molecules" in asked[0]
    assert settings.preference(MAX_REVISIONS_KEPT) == MAX_REVISIONS
    assert dialog._max_revisions.value() == MAX_REVISIONS
    assert service.store.revisions_beyond(3) == (4, 2), "declining removed something"

    _asked(monkeypatch, QMessageBox.StandardButton.Yes)
    _commit(dialog, 3)
    assert settings.preference(MAX_REVISIONS_KEPT) == 3
    assert service.store.revisions_beyond(3) == (0, 0)


def test_lowering_with_nothing_to_remove_asks_nothing(qapp, dialogs, monkeypatch):
    service, settings = _service(qapp)
    service.set_project(ProjectModel(name="p"))
    _drawing_revisions(service.store, 2)
    dialog = _dialog(dialogs, settings, result_store_service=service)
    asked = _asked(monkeypatch, QMessageBox.StandardButton.No)

    _commit(dialog, 2)

    assert asked == [] and settings.preference(MAX_REVISIONS_KEPT) == 2


def test_without_a_store_lowering_always_asks(qapp, dialogs, monkeypatch):
    """The Configure buttons open the window with no store to count, so a
    lowering there must still be declinable."""
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings)
    asked = _asked(monkeypatch, QMessageBox.StandardButton.No)

    _commit(dialog, 5)

    assert len(asked) == 1 and settings.preference(MAX_REVISIONS_KEPT) == MAX_REVISIONS


def test_the_question_moving_the_focus_does_not_ask_twice(qapp, dialogs, monkeypatch):
    """Enter finishes the edit, and the question taking the focus finishes it
    again while the first is still open."""
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings)
    asked = _asked(monkeypatch, during=dialog._max_revisions.editingFinished.emit)

    _commit(dialog, 4)

    assert len(asked) == 1 and settings.preference(MAX_REVISIONS_KEPT) == 4


def test_closing_commits_a_value_that_was_never_committed(qapp, dialogs, monkeypatch):
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings)
    asked = _asked(monkeypatch)
    dialog._max_revisions.setValue(6)  # no Enter, no focus change

    dialog.reject()

    assert len(asked) == 1 and settings.preference(MAX_REVISIONS_KEPT) == 6


def test_enter_never_presses_a_forget_button(qapp, dialogs, tmp_path):
    """FOUND IN THE MAGNIFIED SHOT, not by any test: the first Forget button
    was drawn as the dialog's default.

    A dialog shown with no default makes the first auto-default button in its
    focus chain the default, and Enter that the focused control passes on
    presses it -- if it is on screen. The section list passes Enter on, so
    choosing File dialogs with the keyboard and pressing Enter forgot the
    projects folder. (Enter in the revisions box on the Results page did not:
    the Forget button is not visible there, and Qt skips a hidden default.)
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    settings = Settings(EventBus())
    settings.set_last_directory("project", str(tmp_path))
    dialog = _dialog(dialogs, settings, section=FILE_DIALOGS)
    dialog.show()
    _settle(qapp)
    dialog._sections.setFocus()

    from PySide6.QtWidgets import QPushButton

    assert [b.objectName() or b.text() for b in dialog.findChildren(QPushButton) if b.isDefault()] == []

    QTest.keyClick(dialog._sections, Qt.Key.Key_Return)
    _settle(qapp)

    assert settings.last_directory("project") == str(tmp_path)
    dialog.hide()


def test_every_remembered_folder_kind_has_a_row():
    assert set(DIRECTORY_LABELS) == DIRECTORY_KINDS


def test_forget_clears_one_kind_and_says_where_it_now_opens(qapp, dialogs, tmp_path):
    settings = Settings(EventBus())
    settings.set_last_directory("project", str(tmp_path / "projects"))
    settings.set_last_directory("molecule", str(tmp_path / "molecules"))
    dialog = _dialog(dialogs, settings, section=FILE_DIALOGS)
    where, forget = dialog._directory_rows["molecule"]
    assert not dialog._directory_rows["macromolecule"][1].isEnabled()

    forget.click()

    # The row that was NOT clicked is the one that proves which was forgotten.
    assert settings.last_directory("molecule") == ""
    assert settings.last_directory("project") == str(tmp_path / "projects")
    assert "Documents" in where.text() and not forget.isEnabled()


def test_every_preference_control_carries_a_help_contract(qapp, dialogs):
    """The inventory's fixture needs settings, so the bare-context guard in
    `test_dialog_help_contracts` never builds this window. This walks it.

    SCOPED TO THE PREFERENCE SECTIONS. The External Tools pages were never
    walked either -- their dialog needed settings too -- and carry no
    contracts; documenting their controls is its own piece of work, recorded
    in ARCHITECTURE's Known TODOs, not a condition of moving them.
    """
    from openchem.ui.widgets.help_tooltip import placeholder_reason
    from openchem.ui.widgets.tooltip_inventory import iter_documentable_controls

    dialog = _dialog(dialogs, Settings(EventBus()))
    controls = [
        c for c in iter_documentable_controls(dialog, path="SettingsDialog")
        if "/ExternalToolsPages/" not in c.instance_path
    ]

    assert len(controls) >= 7, [c.instance_path for c in controls]
    assert [c.instance_path for c in controls if c.status != "tooltip"] == []
    assert all(placeholder_reason(c.help_tooltip) is None for c in controls)


# --- the routes -------------------------------------------------------------------


@pytest.fixture
def opened(monkeypatch):
    """Every SettingsDialog shown, captured instead of run modally."""
    shown: list[SettingsDialog] = []

    def exec_(self):
        shown.append(self)
        return 0

    monkeypatch.setattr(SettingsDialog, "exec", exec_)
    return shown


def _menu_action(window, text):
    """The window's one action labelled `text`.

    Found with `findChildren`, NOT through `QAction.menu()`. The first version
    looped over `menu_action.menu().actions()` without keeping the menu
    wrapper, and the Settings action it returned was already deleted by the
    time the test used it ("Internal C++ object already deleted"). Why was
    not chased; this lookup does not depend on that wrapper.
    """
    from PySide6.QtGui import QAction

    (action,) = [a for a in window.findChildren(QAction) if a.text() == text]
    return action


def test_edit_settings_opens_the_window_with_the_store_to_count(qapp, tmp_path, opened):
    window = _build_window(qapp, tmp_path)
    action = _menu_action(window, "Settings...")
    assert action.shortcut().toString() == "Ctrl+,"

    action.trigger()

    (dialog,) = opened
    assert dialog.current_section() == PANELS
    assert dialog._result_store_service is window._services.result_store_service
    _close(window)


def test_tools_external_tools_opens_settings_at_the_tools(qapp, tmp_path, opened):
    window = _build_window(qapp, tmp_path)

    _menu_action(window, "External Tools...").trigger()

    (dialog,) = opened
    assert dialog.current_section() == EXTERNAL_TOOLS
    _close(window)


@pytest.mark.parametrize(("panel", "tool"), [("_docking_panel", "vina"), ("_quantum_chemistry_panel", "orca")])
def test_a_panels_configure_button_opens_its_own_tool(qapp, tmp_path, opened, panel, tool):
    window = _build_window(qapp, tmp_path)

    getattr(window, panel)._configure_button.click()

    (dialog,) = opened
    assert dialog.current_section() == EXTERNAL_TOOLS
    assert dialog.external_tools.current_tool() == tool
    _close(window)


def test_the_tools_pages_open_at_any_tool_by_key(qapp, dialogs):
    for key in ("vina", "orca", "pkasolver", "admet", "java", "nmr_index"):
        dialog = _dialog(dialogs, Settings(EventBus()), section=EXTERNAL_TOOLS, tool=key)
        assert dialog.external_tools.current_tool() == key
