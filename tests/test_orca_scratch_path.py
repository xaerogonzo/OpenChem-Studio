"""ORCA's scratch directory must never contain a space.

ORCA truncates its input path at the first space and aborts with
"Error: Cannot open input file D:\\Random" -- after printing its banner, so
it looks like a calculation that started and then broke rather than a path
problem. Confirmed against a real ORCA 6.1.1: the identical job returned
-74.963358634082 from an unspaced directory and failed from a spaced one.

`quantum_chemistry_service` carried a comment asserting this requirement
long before it held: it avoided the source tree (which lives under
"OpenChem Studio") but derived the scratch dir from `cache_root()`, which
follows the *configurable* data root. Pointing that at a spaced directory
put the space straight back, and every ORCA job failed on a machine whose
setup looked perfectly reasonable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openchem import paths as app_paths


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Point the data root somewhere the test controls, per test."""

    def _set(directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(directory))
        return directory

    return _set


def test_unspaced_cache_root_is_used_unchanged(data_root, tmp_path):
    """The common case must not be redirected anywhere surprising."""
    data_root(tmp_path / "plain")

    assert app_paths.space_free_cache_root() == app_paths.cache_root()


def test_spaced_cache_root_is_replaced_with_a_space_free_path(data_root, tmp_path):
    data_root(tmp_path / "Random Programs" / "OpenChemStudio_Data")

    assert " " in str(app_paths.cache_root()), "precondition: the cache root is spaced"

    scratch = app_paths.space_free_cache_root()

    assert " " not in str(scratch)
    assert scratch != app_paths.cache_root()


def test_the_replacement_stays_on_the_same_drive(data_root, tmp_path):
    """The data root is configurable *because* ORCA writes gigabytes and
    someone moved them off the system disk deliberately. Retreating to a
    temp directory would quietly undo that."""
    spaced = data_root(tmp_path / "Random Programs" / "OpenChemStudio_Data")

    scratch = app_paths.space_free_cache_root()

    assert Path(scratch).anchor == Path(spaced).anchor


def test_a_spaced_anchor_is_left_alone_rather_than_guessed_at(monkeypatch, tmp_path):
    """A UNC share can itself contain a space, and then there is nowhere
    space-free on that volume. Returning the spaced path lets ORCA's own
    error surface, which is truthful; inventing a location the user never
    chose is not."""
    spaced_anchor = Path(r"\\host\My Share\data\cache")
    monkeypatch.setattr(app_paths, "cache_root", lambda: spaced_anchor)

    assert app_paths.space_free_cache_root() == spaced_anchor
