from __future__ import annotations

import threading
from pathlib import Path

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
    """IMMEDIACY is what this asserts. The stored form is now normalised to
    native separators -- see the forward-slash tests at the end of this
    file -- so the expectation goes through `Path` rather than naming a
    separator, which would make this test platform-specific for no reason.
    """
    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings)

    dialog._vina_path_edit.setText("C:/fake/vina.exe")
    dialog._vina_path_edit.editingFinished.emit()

    assert settings.get("docking/vina_executable_path") == str(Path("C:/fake/vina.exe"))


def test_editing_orca_path_saves_immediately_to_settings(qapp):
    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings)

    dialog._orca_path_edit.setText("C:/fake/orca.exe")
    dialog._orca_path_edit.editingFinished.emit()

    assert settings.get("orca/executable_path") == str(Path("C:/fake/orca.exe"))


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


def test_progress_from_a_worker_thread_actually_reaches_the_label(qapp):
    """`progress_reporter` reported nothing at all, for as long as it has
    existed.

    Its docstring claimed `QTimer.singleShot(0, fn)` "hops back to the GUI
    thread via the single-shot-timer idiom Qt sanctions for cross-thread UI
    updates". It does not: the two-argument form creates the timer in the
    CALLING thread, and both callers reach it through `run_async`, i.e. a
    `QThreadPool` worker -- a thread with no event loop, where a timer can
    never fire. Measured:

        QTimer.singleShot(0, fn)         NEVER FIRED
        QTimer.singleShot(0, label, fn)  fired in MainThread

    So the status label sat on "Starting..." for the whole of a tool
    install or a data-root move. Passing the label as the CONTEXT OBJECT
    is the idiom that claim described -- Qt runs the functor in the
    context object's thread.

    **DRIVEN FROM A REAL POOL WORKER, and the test asserts it really was
    one.** Called from the GUI thread the broken form works perfectly, so
    a test that skipped the thread would have passed against the bug.
    """
    import time
    from types import SimpleNamespace

    from PySide6.QtCore import QCoreApplication, QRunnable, QThreadPool
    from PySide6.QtWidgets import QLabel

    from openchem.ui.dialogs.external_tool_tabs import progress_reporter

    label = QLabel()
    report = progress_reporter(label)
    ran_on: list[str] = []

    class Job(QRunnable):
        def run(self) -> None:
            ran_on.append(threading.current_thread().name)
            report(SimpleNamespace(step=2, total=5, message="Fetching"))

    QThreadPool.globalInstance().start(Job())
    assert QThreadPool.globalInstance().waitForDone(10_000), "the worker never finished"
    assert ran_on and ran_on[0] != threading.current_thread().name, (
        "the job ran on the GUI thread, where even the broken form works"
    )

    deadline = time.monotonic() + 5.0
    while not label.text() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert label.text() == "[2/5] Fetching..."


# ---------------------------------------------------------------------------
# A PASTED FORWARD-SLASH PATH IS WHAT KILLS ORCA
#
# ORCA derives its helper binaries' directory (`orca_startup` and friends)
# from the path it was invoked with, so `D:/ORCA/orca.exe` aborts in
# `Startup` where `D:\ORCA\orca.exe` on the identical input terminates
# normally. Browse never had the problem -- it round-trips through `Path`,
# which normalises. This hand-editable field is the way in, and every
# validity check the application makes passes on the bad form, because
# `Path(p).is_file()` accepts forward slashes.
#
# Normalised where the value ENTERS the system so it covers every tool and
# every tool added later. `QuantumChemistryService._resolve_executable_path`
# normalises again on read, which is what repairs a setting saved before
# this existed.
# ---------------------------------------------------------------------------


def test_a_pasted_forward_slash_path_is_stored_in_native_form(qapp, tmp_path):
    import os

    exe = tmp_path / "ORCA" / "orca.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")

    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings, focus="orca")

    assert "/" in exe.as_posix(), "the fixture must actually use forward slashes"
    dialog._orca_path_edit.setText(exe.as_posix())
    dialog._orca_path_edit.editingFinished.emit()

    stored = settings.get("orca/executable_path", "")
    assert stored == str(exe), f"stored {stored!r} rather than the native form"
    # The class docstring promises the field and the setting move together,
    # so the user must not be left looking at a form that was not saved.
    assert dialog._orca_path_edit.text() == stored
    if os.sep == "\\":
        assert "/" not in stored


def test_clearing_the_path_field_stores_an_empty_string_not_a_dot(qapp):
    """The control. `str(Path(""))` is `"."` -- a real, existing directory --
    so a careless normalisation would turn "not configured" into a
    configured path to the working directory, and every "is this tool set
    up" check would start answering yes."""
    bus = EventBus()
    settings = Settings(bus)
    dialog = ExternalToolsDialog(settings, focus="orca")

    dialog._orca_path_edit.setText("")
    dialog._orca_path_edit.editingFinished.emit()

    assert settings.get("orca/executable_path", "") == ""
    assert dialog._orca_path_edit.text() == ""
