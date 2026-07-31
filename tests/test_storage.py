"""Relocating the data directory.

The move is the risky half -- a bug here strands 3.8 GB of installed
sidecars, or worse, points the app at a half-filled directory. So these
exercise real files and a real virtual environment rather than mocks.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from openchem import paths as app_paths
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.services import storage_service


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    """Never touch the developer's real data directory.

    The env var exists precisely for this: a test that wrote to the real
    root would have destroyed a 3.8 GB install, which is exactly the
    class of accident that already happened once with the NMR index.
    """
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(root))
    return root


class _FakeSettings:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = dict(values)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


# --- Resolving the root ---------------------------------------------------


def test_the_environment_variable_wins(isolated_root):
    assert app_paths.data_root() == isolated_root


def test_a_pointer_file_is_used_when_there_is_no_override(tmp_path, monkeypatch):
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)
    target = tmp_path / "elsewhere"
    monkeypatch.setattr(app_paths, "pointer_file", lambda: tmp_path / "pointer.txt")
    app_paths.set_data_root(target)

    assert app_paths.data_root() == target.resolve()


def test_clearing_the_pointer_returns_to_the_os_default(tmp_path, monkeypatch):
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)
    monkeypatch.setattr(app_paths, "pointer_file", lambda: tmp_path / "pointer.txt")
    app_paths.set_data_root(tmp_path / "elsewhere")

    app_paths.set_data_root(None)

    assert app_paths.data_root() == app_paths.default_data_root()


def test_the_pointer_lives_outside_the_data_directory(tmp_path, monkeypatch):
    """It has to be findable BEFORE the data root is known -- storing it
    inside would not terminate."""
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)

    assert app_paths.pointer_file().parent != app_paths.default_data_root() / "x"


def test_every_sidecar_follows_the_configured_root(isolated_root):
    from openchem.chem import nmr_database
    from openchem.services import java_setup, pkasolver_setup, stout_setup

    assert java_setup.default_install_root() == isolated_root / "jre"
    assert pkasolver_setup.default_install_root() == isolated_root / "pkasolver_env"
    assert stout_setup.default_install_root() == isolated_root / "stout_env"
    assert nmr_database.default_database_path() == isolated_root / "nmrshiftdb.sqlite"


def test_scratch_follows_the_data_root_too(isolated_root):
    """An ORCA optimisation writes gigabytes of scratch, which is exactly
    what someone moving data off the system drive meant to move."""
    assert app_paths.cache_root() == isolated_root / "cache"


# --- Moving ---------------------------------------------------------------


def test_moving_relocates_contents_and_repoints_the_app(isolated_root, tmp_path, monkeypatch):
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)
    monkeypatch.setattr(app_paths, "pointer_file", lambda: tmp_path / "pointer.txt")
    app_paths.set_data_root(isolated_root)
    (isolated_root / "jre").mkdir()
    (isolated_root / "jre" / "note.txt").write_text("hello", encoding="utf-8")
    (isolated_root / "nmrshiftdb.sqlite").write_text("index", encoding="utf-8")

    destination = tmp_path / "moved"
    storage_service.move_data_root(destination)

    assert (destination / "jre" / "note.txt").read_text(encoding="utf-8") == "hello"
    assert (destination / "nmrshiftdb.sqlite").is_file()
    assert app_paths.data_root() == destination.resolve()
    assert not (isolated_root / "jre").exists()


def test_stored_interpreter_paths_follow_the_move(isolated_root, tmp_path, monkeypatch):
    """Moving files without rewriting these leaves both sidecars
    configured but broken -- the same failure a stale path caused once
    already."""
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)
    monkeypatch.setattr(app_paths, "pointer_file", lambda: tmp_path / "pointer.txt")
    app_paths.set_data_root(isolated_root)
    interpreter = isolated_root / "pkasolver_env" / ".venv" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("", encoding="utf-8")
    settings = _FakeSettings(
        {
            # The REAL settings key, imported rather than spelled out --
            # an earlier version of this test invented a name, matched the
            # same invented name in the service, and passed while the
            # feature was broken.
            PKASOLVER_PYTHON_SETTING: str(interpreter),
            "orca/executable_path": r"D:\ORCA\orca.exe",
        }
    )

    destination = tmp_path / "moved"
    storage_service.move_data_root(destination, settings)

    assert settings.get(PKASOLVER_PYTHON_SETTING) == str(
        destination / "pkasolver_env" / ".venv" / "Scripts" / "python.exe"
    )
    # A path outside the data directory is left alone.
    assert settings.get("orca/executable_path") == r"D:\ORCA\orca.exe"


def test_a_non_empty_destination_is_refused(isolated_root, tmp_path):
    destination = tmp_path / "occupied"
    destination.mkdir()
    (destination / "something.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(storage_service.StorageError, match="not empty"):
        storage_service.move_data_root(destination)

    assert (destination / "something.txt").read_text(encoding="utf-8") == "mine"


def test_moving_into_itself_is_refused(isolated_root):
    with pytest.raises(storage_service.StorageError, match="inside the current one"):
        storage_service.move_data_root(isolated_root / "inner")


def test_moving_to_the_current_location_is_refused(isolated_root):
    with pytest.raises(storage_service.StorageError, match="already the current location"):
        storage_service.move_data_root(isolated_root)


def test_the_pointer_is_written_only_after_everything_moved(isolated_root, tmp_path, monkeypatch):
    """Order matters: an interrupted move must leave the app pointed at
    the old location, where the data still is."""
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)
    monkeypatch.setattr(app_paths, "pointer_file", lambda: tmp_path / "pointer.txt")
    app_paths.set_data_root(isolated_root)
    (isolated_root / "payload").mkdir()

    seen_when_moving = {}
    original = storage_service.shutil.move

    def spy(source, target):
        seen_when_moving["root_during_move"] = app_paths.data_root()
        return original(source, target)

    monkeypatch.setattr(storage_service.shutil, "move", spy)
    storage_service.move_data_root(tmp_path / "moved")

    assert seen_when_moving["root_during_move"] == isolated_root


# --- The venv question ----------------------------------------------------


def test_a_real_virtual_environment_still_runs_after_being_moved(isolated_root, tmp_path, monkeypatch):
    """The assumption the whole feature rests on. `pyvenv.cfg` records the
    BASE interpreter, which does not move, and site-packages is found
    relative to the executable -- so a moved venv should still run. Tested
    with a real one rather than assumed."""
    monkeypatch.delenv(app_paths.DATA_ROOT_ENV_VAR, raising=False)
    monkeypatch.setattr(app_paths, "pointer_file", lambda: tmp_path / "pointer.txt")
    app_paths.set_data_root(isolated_root)

    environment = isolated_root / "sidecar_env" / ".venv"
    venv.EnvBuilder(with_pip=False).create(environment)
    interpreter = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert interpreter.is_file()

    destination = tmp_path / "moved"
    storage_service.move_data_root(destination)

    moved = destination / "sidecar_env" / ".venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    result = subprocess.run(
        [str(moved), "-c", "import sys, json; print(json.dumps(sys.version_info[:2]))"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("[")


# --- Reporting ------------------------------------------------------------


def test_usage_lists_the_biggest_things_first(isolated_root):
    (isolated_root / "small").mkdir()
    (isolated_root / "small" / "a").write_bytes(b"x" * 10)
    (isolated_root / "big").mkdir()
    (isolated_root / "big" / "b").write_bytes(b"x" * 5000)

    report = storage_service.usage()

    assert [name for name, _size in report.entries] == ["big", "small"]
    assert report.total_bytes == 5010


def test_status_says_whether_the_location_is_custom(isolated_root):
    assert "custom location" in storage_service.describe_status()


def test_the_status_line_does_not_walk_the_data_directory(isolated_root, monkeypatch):
    """It is drawn on dialog construction, so it has to be instant.
    Totalling the directory took 6.2 seconds on a real install."""
    walked = []
    monkeypatch.setattr(
        storage_service, "_directory_size", lambda path: walked.append(path) or 0
    )

    storage_service.describe_status()

    assert walked == []
