"""Removing installed sidecars.

Deleting is irreversible, so the tests that matter most here are the ones
about what must NOT be deleted: software the user installed themselves,
which happens to be reachable from a setting this app reads.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openchem import paths as app_paths
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.services import sidecar_inventory


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(root))
    return root


class _FakeSettings:
    def __init__(self, values=None):
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


def _install(root: Path, name: str, size: int = 2048) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "payload.bin").write_bytes(b"x" * size)
    return directory


# --- What is present ------------------------------------------------------


def test_an_absent_component_is_listed_but_offers_nothing_to_remove(isolated_root):
    component = sidecar_inventory.find("pkasolver")

    assert not component.present
    assert component.size_bytes() == 0


def test_an_installed_component_reports_its_size(isolated_root):
    _install(isolated_root, "pkasolver_env", size=4096)

    component = sidecar_inventory.find("pkasolver")

    assert component.present
    assert component.size_bytes() == 4096


def test_measuring_orders_by_size(isolated_root):
    _install(isolated_root, "pkasolver_env", size=1024)
    _install(isolated_root, "stout_env", size=8192)

    measured = [(c.key, size) for c, size in sidecar_inventory.measure() if size]

    assert [key for key, _size in measured] == ["stout", "pkasolver"]


def test_listing_components_does_not_touch_the_disk(isolated_root, monkeypatch):
    """The regression that made the External Tools dialog take 18.9
    seconds to open: sorting the list by size walked every file in two
    sidecar environments, on every construction. Sizes are measured only
    when asked for, off the GUI thread."""
    _install(isolated_root, "pkasolver_env", size=4096)
    walked = []
    monkeypatch.setattr(
        sidecar_inventory, "_size_of", lambda path: walked.append(path) or 0
    )

    sidecar_inventory.components()

    assert walked == [], "building the inventory must not stat anything"


# --- Removing -------------------------------------------------------------


def test_removing_deletes_the_files_and_clears_the_stored_path(isolated_root):
    """Deleting without clearing leaves the app reporting a configured
    tool that is not there -- the configured-but-broken state a stale
    path already produced once."""
    directory = _install(isolated_root, "pkasolver_env")
    settings = _FakeSettings({PKASOLVER_PYTHON_SETTING: str(directory / "python.exe")})

    freed = sidecar_inventory.uninstall(sidecar_inventory.find("pkasolver", settings), settings)

    assert not directory.exists()
    assert freed == 2048
    assert settings.get(PKASOLVER_PYTHON_SETTING) == ""


def test_the_shift_index_takes_its_wal_and_shm_companions_with_it(isolated_root):
    """Leaving those behind strands megabytes and, worse, lets SQLite
    rebuild a partial database from a stale write-ahead log."""
    from openchem.chem.nmr_database import default_database_path

    database = default_database_path()
    database.write_bytes(b"index")
    Path(f"{database}-wal").write_bytes(b"wal")
    Path(f"{database}-shm").write_bytes(b"shm")

    sidecar_inventory.uninstall(sidecar_inventory.find("nmr_index"))

    assert not database.exists()
    assert not Path(f"{database}-wal").exists()
    assert not Path(f"{database}-shm").exists()


def test_removing_something_absent_is_harmless(isolated_root):
    assert sidecar_inventory.uninstall(sidecar_inventory.find("cache")) == 0


# --- What must NOT be removed --------------------------------------------


def test_a_user_installed_vina_is_not_removable(isolated_root, tmp_path):
    """Someone who pointed the app at their own Vina and clicked Remove
    would otherwise lose their own executable. Confirmed against a real
    configuration doing exactly this."""
    theirs = tmp_path / "Program Files" / "Vina" / "vina.exe"
    theirs.parent.mkdir(parents=True)
    theirs.write_bytes(b"binary")
    settings = _FakeSettings({sidecar_inventory.VINA_SETTING: str(theirs)})

    component = sidecar_inventory.find("vina", settings)

    assert not component.is_managed
    assert "did not install" in component.unmanaged_reason
    with pytest.raises(sidecar_inventory.UninstallError, match="not installed by this app"):
        sidecar_inventory.uninstall(component, settings)
    assert theirs.exists()


def test_a_downloaded_vina_is_removable(isolated_root):
    """The other half: a copy this app fetched into its own tools folder
    is fair game, or the rule above would make it permanently
    unremovable."""
    managed = app_paths.subdirectory("tools") / "vina"
    managed.mkdir(parents=True)
    (managed / "vina.exe").write_bytes(b"binary")
    settings = _FakeSettings({sidecar_inventory.VINA_SETTING: str(managed / "vina.exe")})

    component = sidecar_inventory.find("vina", settings)

    assert component.is_managed
    sidecar_inventory.uninstall(component, settings)
    assert not managed.exists()
    assert settings.get(sidecar_inventory.VINA_SETTING) == ""


def test_a_system_java_is_not_removable(isolated_root, monkeypatch):
    """Deleting a machine's Java because someone wanted space back in an
    application folder would be indefensible."""
    from openchem.services import java_setup

    monkeypatch.setattr(java_setup, "system_java_home", lambda: Path("/usr/lib/jvm/real"))

    component = sidecar_inventory.find("java")

    assert not component.is_managed
    assert "system Java" in component.unmanaged_reason
    with pytest.raises(sidecar_inventory.UninstallError):
        sidecar_inventory.uninstall(component)


def test_a_managed_java_is_removable(isolated_root, monkeypatch):
    from openchem.services import java_setup

    monkeypatch.setattr(java_setup, "system_java_home", lambda: None)
    _install(isolated_root, "jre")

    component = sidecar_inventory.find("java")

    assert component.is_managed
    sidecar_inventory.uninstall(component)
    assert not (isolated_root / "jre").exists()


# --- Reporting ------------------------------------------------------------


def test_every_removable_component_says_how_to_get_it_back(isolated_root):
    """Removal is only comfortable if reinstalling is obvious."""
    for component in sidecar_inventory.components():
        if component.is_managed:
            assert component.reinstall_hint, f"{component.key} has no reinstall hint"


def test_components_follow_a_moved_data_root(isolated_root, tmp_path, monkeypatch):
    """The inventory is built fresh each call for this reason: a cached
    one would offer to delete paths under the old root."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(other))

    component = sidecar_inventory.find("pkasolver")

    assert component.paths[0] == other / "pkasolver_env"
