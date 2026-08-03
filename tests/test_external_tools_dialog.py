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
        # Grouped with the other out-of-process Python environments rather
        # than with the executables above -- same shape, same problem.
        "ADMET (hERG/CYP)",
        # These two OBTAIN a prerequisite rather than configure a tool the
        # user already has: a portable Temurin runtime (OPSIN is dead
        # without one) and the experimental shift index.
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


def test_each_sidecar_tab_can_remove_its_own_tool(qapp):
    """Remove has always worked -- but only from the Storage tab, and
    nobody standing on a tool's own tab, having just read that the tool is
    missing, goes hunting under Storage for it. Alex looked and reported
    there was no uninstall.
    """
    dialog = ExternalToolsDialog(Settings(EventBus()))

    for attribute in (
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
    dialog._pkasolver_remove_button = dialog._remove_button(dialog, "pkasolver", "pkasolver")
    dialog._java_remove_button = dialog._remove_button(dialog, "java", "Java")

    dialog._pkasolver_remove_button.click()
    dialog._java_remove_button.click()

    assert removed == ["pkasolver", "java"]


def test_the_admet_tab_exists_with_the_full_sidecar_affordance_set(qapp):
    """Every sidecar tab offers the same four things. A tab that can be
    configured but not installed, or installed but not removed, is the
    gap that made the pkasolver and STOUT tabs frustrating before."""
    dialog = ExternalToolsDialog(Settings(EventBus()))

    assert "ADMET (hERG/CYP)" in [
        dialog._tabs.tabText(i) for i in range(dialog._tabs.count())
    ]
    for attribute in (
        "_admet_path_edit",
        "_admet_setup_button",
        "_admet_locate_button",
        "_admet_remove_button",
    ):
        assert getattr(dialog, attribute, None) is not None, f"{attribute} missing"
    assert dialog._admet_remove_button.text() == "Remove from Disk..."


def test_editing_the_admet_path_persists_to_the_setting_the_calculator_reads(qapp):
    """The dialog and the calculator must agree on the key. A mismatch
    would look configured and behave unconfigured."""
    from openchem.chem.admet_providers import ADMET_PYTHON_SETTING

    settings = Settings(EventBus())
    dialog = ExternalToolsDialog(settings)

    dialog._admet_path_edit.setText(r"C:\somewhere\python.exe")
    dialog._on_admet_path_edited()

    assert settings.get(ADMET_PYTHON_SETTING, "") == r"C:\somewhere\python.exe"


def test_the_admet_self_test_uses_a_known_herg_blocker(qapp, monkeypatch):
    """Astemizole, not something inert. A test that passed on a molecule
    with no liability would prove the plumbing runs and nothing else --
    and a model returning 0.05 for astemizole is broken, not cautious."""
    from openchem.chem import admet_providers as ap

    seen = {}

    def fake(mol, interpreter_path):
        from rdkit import Chem

        seen["smiles"] = Chem.MolToSmiles(mol)
        return {"hERG": 0.995}

    monkeypatch.setattr(ap, "compute_admet", fake)
    message = ap.describe_admet_test("anything")

    assert "0.995" in message and "withdrawn" in message
    assert "N" in seen["smiles"] and len(seen["smiles"]) > 30  # the real drug, not a stub


def test_a_low_herg_score_for_astemizole_is_reported_as_suspect(qapp, monkeypatch):
    """The self-test must not print "Working" for a result that is
    chemically wrong."""
    from openchem.chem import admet_providers as ap

    monkeypatch.setattr(ap, "compute_admet", lambda mol, path: {"hERG": 0.05})
    message = ap.describe_admet_test("anything")

    assert "suspect" in message.lower()
    assert "working" not in message.lower()
