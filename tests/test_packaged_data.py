"""Every data file the application reads must be in the frozen build.

Measured 2026-10-21 on a fresh build of master: seventeen files under
`chem/data/` were not in `packaging/openchem.spec`, and the frozen app died at
import on `abraham_solvents.json` before any window appeared. Each file was
listed by hand, so each new one was a chance to forget, and every one of them
works from a checkout, which is where the tests run. This is the guard the
per-file tests (`test_element_reference` and friends) were individually trying
to be.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import conftest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "openchem" / "chem" / "data"


def _data_files() -> list[str]:
    return sorted(
        path.relative_to(ROOT / "src" / "openchem").as_posix()
        for path in DATA.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def test_there_are_data_files_to_check():
    assert len(_data_files()) > 20, "the sweep found almost nothing; the path is wrong"


@pytest.mark.parametrize("relative", _data_files())
def test_every_chem_data_file_ships_unless_it_is_a_ruleset_source(relative):
    if relative.startswith("chem/data/regulatory/sources/"):
        assert not conftest.spec_ships(relative), "the hand-edited ruleset inputs must not ship"
    else:
        assert conftest.spec_ships(relative), f"{relative} works from a checkout and is missing from the frozen build"


def test_the_guard_fails_on_a_spec_without_the_entry():
    """A guard that cannot fail is not one: the same check on a spec with the
    old per-file list minus one file, and on one with no `chem/data` entry."""
    old_style = 'datas += [(str(PKG / "chem" / "data" / "elements.json"), "openchem/chem/data")]'
    assert conftest.spec_ships("chem/data/elements.json", old_style)
    assert not conftest.spec_ships("chem/data/abraham_solvents.json", old_style)
    assert not conftest.spec_ships("chem/data/elements.json", "# datas += [(str(PKG / 'chem' / 'data'), 'x')]")
    assert conftest.spec_ships("chem/data/elements.json", 'datas += [(str(PKG / "chem" / "data"), "d")]')


def test_the_spec_drops_the_ruleset_sources_from_the_directory_entry():
    spec = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    assert 'dest.startswith("openchem/chem/data/regulatory/sources/")' in spec
