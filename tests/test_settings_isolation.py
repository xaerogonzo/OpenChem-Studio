"""The test suite must never write to the machine's real settings store.

This guards the autouse `isolated_settings` fixture in `conftest.py` rather
than any application behaviour. It exists because the previous isolation
looked correct and silently half-worked: it kept the real "OpenChemStudio"
key clean while depositing one junk registry key per test under
HKCU\\Software, which nothing in the suite's output would ever reveal. Read
that fixture's docstring before changing anything here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container


def test_settings_are_backed_by_a_file_under_tmp_path(tmp_path):
    """The backing store is a real file in this test's own directory."""
    settings = Settings(build_service_container().event_bus)

    backing = Path(settings._qsettings.fileName())

    assert backing.parent == tmp_path, (
        f"settings should live under this test's tmp_path, got {backing}"
    )


def test_settings_writes_never_reach_the_native_store(tmp_path):
    """A write lands in the INI file and not in the registry.

    `fileName()` is the check that actually distinguishes the two: a
    NativeFormat QSettings on Windows reports a `\\HKEY_CURRENT_USER\\...`
    pseudo-path here, which is exactly what the old fixture produced while
    appearing to have set IniFormat.
    """
    settings = Settings(build_service_container().event_bus)
    settings.set("plugins/project_directory", "sentinel-value")
    settings._qsettings.sync()

    file_name = settings._qsettings.fileName()
    assert settings._qsettings.format() == QSettings.Format.IniFormat
    assert "HKEY" not in file_name.upper()
    assert "sentinel-value" in Path(file_name).read_text(encoding="utf-8")


def test_separate_settings_instances_share_one_store(tmp_path):
    """Two `Settings` in the same test see each other's writes.

    Several tests construct a `Settings`, hand it to `MainWindow`, and then
    assert on values the window wrote. That only works while every instance
    resolves to the same backing file, so it is pinned here rather than left
    as an emergent property of the fixture.
    """
    bus = build_service_container().event_bus
    writer = Settings(bus)
    writer.set("plugins/user_directory", "shared-store")
    writer._qsettings.sync()

    assert Settings(bus).get("plugins/user_directory") == "shared-store"
