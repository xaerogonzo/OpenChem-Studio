from __future__ import annotations

from openchem.app.settings import Settings
from openchem.events.base import EventBus
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog


def test_dialog_has_every_tool_tab_and_focuses_the_requested_one(qapp):
    bus = EventBus()
    settings = Settings(bus)

    dialog = ExternalToolsDialog(settings, focus="orca")

    assert [dialog._tabs.tabText(i) for i in range(dialog._tabs.count())] == [
        "AutoDock Vina",
        "ORCA",
        "pkasolver (pKa)",
        "STOUT (naming)",
        # These two OBTAIN a prerequisite rather than configure a tool the
        # user already has: a portable Temurin runtime (STOUT and OPSIN
        # are both dead without one) and the experimental shift index.
        "Java (Temurin)",
        "NMR Database",
        # Not a tool at all -- where the tools' own multi-gigabyte
        # installs are kept, and how to move them off the system drive.
        "Storage",
    ]
    assert dialog._tabs.currentIndex() == 1


def test_dialog_can_focus_the_pkasolver_tab(qapp):
    bus = EventBus()
    settings = Settings(bus)

    dialog = ExternalToolsDialog(settings, focus="pkasolver")

    assert dialog._tabs.currentIndex() == 2


def test_editing_pkasolver_path_saves_immediately_to_settings(qapp):
    from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING

    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings, focus="pkasolver")

    dialog._pkasolver_path_edit.setText(r"C:\some\env\python.exe")
    dialog._on_pkasolver_path_edited()

    assert settings.get(PKASOLVER_PYTHON_SETTING, "") == r"C:\some\env\python.exe"


def test_dialog_defaults_to_vina_tab(qapp):
    bus = EventBus()
    settings = Settings(bus)

    dialog = ExternalToolsDialog(settings)

    assert dialog._tabs.currentIndex() == 0


def test_editing_vina_path_saves_immediately_to_settings(qapp):
    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings)

    dialog._vina_path_edit.setText("C:/fake/vina.exe")
    dialog._vina_path_edit.editingFinished.emit()

    assert settings.get("docking/vina_executable_path") == "C:/fake/vina.exe"


def test_editing_orca_path_saves_immediately_to_settings(qapp):
    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings)

    dialog._orca_path_edit.setText("C:/fake/orca.exe")
    dialog._orca_path_edit.editingFinished.emit()

    assert settings.get("orca/executable_path") == "C:/fake/orca.exe"


def test_dialog_prefills_paths_already_present_in_settings(qapp):
    bus = EventBus()
    settings = Settings(bus)
    settings.set("docking/vina_executable_path", "C:/existing/vina.exe")
    settings.set("orca/executable_path", "C:/existing/orca.exe")

    dialog = ExternalToolsDialog(settings)

    assert dialog._vina_path_edit.text() == "C:/existing/vina.exe"
    assert dialog._orca_path_edit.text() == "C:/existing/orca.exe"


def test_stout_tab_offers_setup_and_saves_its_path(qapp):
    from openchem.chem.stout_providers import STOUT_PYTHON_SETTING

    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings, focus="orca")

    dialog._stout_path_edit.setText(r"C:\some\stout\python.exe")
    dialog._on_stout_path_edited()

    assert settings.get(STOUT_PYTHON_SETTING, "") == r"C:\some\stout\python.exe"
    assert dialog._stout_setup_button.isEnabled()


def test_stout_tab_states_that_names_are_predictions(qapp):
    """A wrong STOUT name looks exactly as authoritative as a right one, so
    the dialog has to say so rather than leaving it to be discovered."""
    from PySide6.QtWidgets import QLabel

    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings, focus="orca")

    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "neural model" in text
    assert "plausible name for ANY input" in text


def test_each_sidecar_tab_can_remove_its_own_tool(qapp):
    """Remove has always worked -- but only from the Storage tab, and
    nobody standing on the STOUT tab, having just read that STOUT cannot
    work, goes hunting under Storage for it. Alex looked and reported
    there was no uninstall.
    """
    dialog = ExternalToolsDialog(Settings(EventBus()))

    for attribute in (
        "_stout_remove_button",
        "_pkasolver_remove_button",
        "_java_remove_button",
        "_nmr_db_remove_button",
    ):
        button = getattr(dialog, attribute, None)
        assert button is not None, f"{attribute} is missing from its tab"
        assert button.text() == "Remove from Disk..."


def test_the_tab_buttons_reuse_the_storage_tabs_removal_path(qapp, monkeypatch):
    """One confirmation, one set of paths, one refresh -- a second
    implementation is how the two would drift apart."""
    dialog = ExternalToolsDialog(Settings(EventBus()))
    removed: list[str] = []
    monkeypatch.setattr(dialog, "_on_remove_component", removed.append)
    # Rebuild the buttons so they close over the patched method.
    dialog._stout_remove_button = dialog._remove_button(dialog, "stout", "STOUT")
    dialog._java_remove_button = dialog._remove_button(dialog, "java", "Java")

    dialog._stout_remove_button.click()
    dialog._java_remove_button.click()

    assert removed == ["stout", "java"]
