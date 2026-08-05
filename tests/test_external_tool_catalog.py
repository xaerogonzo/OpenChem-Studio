"""The wiring between a tool tab and the service behind it.

Four of the External Tools tabs are now built from descriptors rather than
hand-written, which trades 34 methods for a table of callables. That trade
moves the failure mode: nothing here can fail by forgetting a method, but
everything here can fail by naming the WRONG service in a lambda, or the
wrong exception class, and every one of those mistakes is invisible until
someone clicks a button that downloads a gigabyte.

None of that is reachable from the tests that open the dialog, because
opening it only exercises the read path. These tests exercise the wiring
itself, with the installers mocked -- the parts that cost money, minutes
or data to run for real.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from openchem.app.settings import Settings
from openchem.events.base import EventBus
from openchem.ui.dialogs import external_tool_catalog as catalog
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog

ALL_DESCRIPTORS = ("java", "nmr_database", "pkasolver", "admet")
SIDECARS = ("pkasolver", "admet")


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """Every message box answers itself.

    A QMessageBox in a test is a hang, not a failure -- it waits for a
    click that never comes.
    """
    recorded: list[tuple[str, str]] = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, name, lambda *a, _n=name, **k: recorded.append((_n, a[1])) or 0
        )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    return recorded


def _descriptor(name: str):
    return getattr(catalog, name)()


# --- The catalog agrees with the services it names -------------------------


@pytest.mark.parametrize("name", ALL_DESCRIPTORS)
def test_every_descriptor_key_names_a_real_removable_component(name, qapp):
    """A typo in `key` would only surface as a crash on Remove.

    The tab builds its Remove button from this string and
    `sidecar_inventory.find` raises UninstallError on an unknown one, so a
    wrong key is a button that looks fine and fails when pressed.
    """
    from openchem.services import sidecar_inventory

    settings = Settings(EventBus())
    keys = {component.key for component in sidecar_inventory.components(settings)}

    assert _descriptor(name).key in keys


@pytest.mark.parametrize(
    "name, module_path, expected",
    [
        ("java", "openchem.services.java_setup", "JavaSetupError"),
        ("nmr_database", "openchem.services.nmr_database_setup", "NmrDatabaseSetupError"),
        ("pkasolver", "openchem.services.pkasolver_setup", "PkasolverSetupError"),
        ("admet", "openchem.services.admet_setup", "AdmetSetupError"),
    ],
)
def test_each_descriptor_catches_the_error_its_own_service_raises(name, module_path, expected):
    """`errors` is what run_async treats as an expected failure.

    Name the wrong one and a genuine setup failure is reported as
    "Unexpected error: ..." instead of the service's own message -- which
    is the difference between a diagnosable failure and a mystery.
    """
    import importlib

    module = importlib.import_module(module_path)

    assert _descriptor(name).errors is getattr(module, expected)


@pytest.mark.parametrize(
    "name, module_path, function",
    [
        ("java", "openchem.services.java_setup", "install"),
        ("nmr_database", "openchem.services.nmr_database_setup", "build"),
        ("pkasolver", "openchem.services.pkasolver_setup", "install"),
        ("admet", "openchem.services.admet_setup", "install"),
    ],
)
def test_run_invokes_that_services_own_installer(name, module_path, function, monkeypatch):
    """The one mistake this table makes easy: pkasolver's tab calling
    ADMET's installer. Both take (root, on_progress) and both would run."""
    import importlib

    module = importlib.import_module(module_path)
    seen = {}

    def fake(*args, on_progress=None, **kwargs):
        seen["called"] = True
        seen["on_progress"] = on_progress
        return "result"

    monkeypatch.setattr(module, function, fake)
    sentinel = object()

    assert _descriptor(name).run(sentinel) == "result"
    assert seen["called"]
    # The progress callback must reach the service, or the status label
    # sits on "Starting..." for the whole install.
    assert seen["on_progress"] is sentinel


# --- Preconditions ---------------------------------------------------------


def test_java_refuses_to_install_when_the_machine_already_has_java(monkeypatch):
    """Good news, not a failure -- so it must be an information box."""
    import openchem.services.java_setup as java_setup

    monkeypatch.setattr(java_setup, "system_java_home", lambda: "C:/java")
    blocked = catalog.java().blocked()

    assert blocked is not None
    assert blocked.severity == "information"
    assert "C:/java" in blocked.message


def test_java_installs_when_no_system_java_is_present(monkeypatch):
    import openchem.services.java_setup as java_setup

    monkeypatch.setattr(java_setup, "system_java_home", lambda: None)

    assert catalog.java().blocked() is None


@pytest.mark.parametrize("name, module_path", [
    ("pkasolver", "openchem.services.pkasolver_setup"),
    ("admet", "openchem.services.admet_setup"),
])
def test_a_sidecar_refuses_without_uv_or_a_fallback_python(name, module_path, monkeypatch):
    """Without an interpreter to build from there is nothing to do, and
    starting anyway would fail several minutes in."""
    import importlib

    module = importlib.import_module(module_path)
    monkeypatch.setattr(module, "find_uv", lambda: None)
    monkeypatch.setattr(module, "find_fallback_python", lambda: None)

    blocked = _descriptor(name).blocked()

    assert blocked is not None
    assert blocked.severity == "warning"


@pytest.mark.parametrize("name, module_path", [
    ("pkasolver", "openchem.services.pkasolver_setup"),
    ("admet", "openchem.services.admet_setup"),
])
def test_a_sidecar_proceeds_when_uv_is_available(name, module_path, monkeypatch):
    import importlib

    module = importlib.import_module(module_path)
    monkeypatch.setattr(module, "find_uv", lambda: "uv")

    assert _descriptor(name).blocked() is None


def test_a_blocked_precondition_never_starts_the_install(qapp, monkeypatch):
    """The button must stay usable -- a refused start is not a failure."""
    import openchem.services.java_setup as java_setup

    monkeypatch.setattr(java_setup, "system_java_home", lambda: "C:/java")
    dialog = ExternalToolsDialog(Settings(EventBus()))
    tab = dialog._tab_for("java")

    started = []
    monkeypatch.setattr(java_setup, "install", lambda *a, **k: started.append(True))
    tab.setup_button.click()

    assert started == []
    assert tab.setup_button.isEnabled()


# --- Failure leaves a usable tab ------------------------------------------


@pytest.mark.parametrize("key", ["java", "nmr_index", "pkasolver"])
def test_a_failed_install_re_enables_its_button(key, qapp):
    """`_on_setup_clicked` disables the button so it cannot be pressed
    twice. If the failure path forgets to restore it, the only way to
    retry is to close and reopen the dialog."""
    dialog = ExternalToolsDialog(Settings(EventBus()))
    tab = dialog._tab_for(key)
    tab.setup_button.setEnabled(False)

    tab._failed("network unreachable")

    assert tab.setup_button.isEnabled()
    assert "network unreachable" in tab.status_label.text()


def test_admet_keeps_an_environment_that_built_but_failed_its_check(qapp, tmp_path, monkeypatch):
    """ADMET's one documented departure from the shared path.

    The expensive part is ~1 GB of PyTorch and the check is seconds on
    top, so a failed verification must not discard a usable environment.
    """
    from openchem.services import admet_setup

    interpreter = tmp_path / "python.exe"
    interpreter.write_text("", encoding="utf-8")
    monkeypatch.setattr(admet_setup, "default_install_root", lambda: tmp_path)
    monkeypatch.setattr(admet_setup, "interpreter_for", lambda root: interpreter)

    dialog = ExternalToolsDialog(Settings(EventBus()))
    tab = dialog._tab_for("admet")
    tab._failed("model load timed out")

    assert tab.path_row.text() == str(interpreter)
    assert "press Test to retry" in tab.status_label.text()


def test_admet_reports_a_plain_failure_when_nothing_was_built(qapp, tmp_path, monkeypatch):
    """The recovery above must not swallow a real failure."""
    from openchem.services import admet_setup

    monkeypatch.setattr(admet_setup, "default_install_root", lambda: tmp_path)
    monkeypatch.setattr(admet_setup, "interpreter_for", lambda root: tmp_path / "absent.exe")

    dialog = ExternalToolsDialog(Settings(EventBus()))
    tab = dialog._tab_for("admet")
    tab._failed("no network")

    assert tab.status_label.text() == "Setup failed: no network"


# --- Removal refreshes every tab, not most of them ------------------------


def test_removing_a_component_refreshes_every_tool_tab(qapp, monkeypatch):
    """Regression: the hand-written `_refresh_tool_tabs` listed pkasolver,
    Java, NMR and Vina and silently omitted ADMET, so removing the ADMET
    environment left its own tab showing the interpreter path that had
    just been deleted and cleared from settings -- exactly the
    configured-but-broken state that method exists to prevent.
    """
    dialog = ExternalToolsDialog(Settings(EventBus()))
    refreshed: list[str] = []
    for tab in dialog._tool_tabs:
        monkeypatch.setattr(
            tab, "refresh", lambda _key=tab.descriptor.key: refreshed.append(_key)
        )

    dialog._refresh_tool_tabs()

    assert set(refreshed) == {"java", "nmr_index", "pkasolver", "admet"}


@pytest.mark.parametrize("key", ["pkasolver", "admet"])
def test_every_sidecar_tab_offers_the_full_affordance_set(key, qapp):
    """Generalises the ADMET-only version of this check. A tab that can be
    configured but not installed, or installed but not removed, is the gap
    that made the pkasolver and STOUT tabs frustrating."""
    dialog = ExternalToolsDialog(Settings(EventBus()))
    tab = dialog._tab_for(key)

    assert tab.path_row is not None
    assert tab.setup_button is not None
    assert tab.locate_button is not None
    assert tab.test_button is not None
    assert tab.remove_button.text() == "Remove from Disk..."


@pytest.mark.parametrize("name", SIDECARS)
def test_a_sidecar_writes_its_path_to_the_setting_its_calculator_reads(name, qapp):
    """A mismatch here looks configured and behaves unconfigured."""
    settings = Settings(EventBus())
    dialog = ExternalToolsDialog(settings)
    descriptor = _descriptor(name)
    tab = dialog._tab_for(descriptor.key)

    tab.path_row.set_path(r"C:\somewhere\python.exe")

    assert settings.get(descriptor.setting_key, "") == r"C:\somewhere\python.exe"
