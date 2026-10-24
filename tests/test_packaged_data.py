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
    assert "dest.startswith(DROPPED_PREFIXES)" in spec
    assert '"openchem/chem/data/regulatory/sources/"' in spec.split("DROPPED_PREFIXES = (")[1].split(")")[0]


# --- RDKit's Contrib modules are source imported by name, which the freezer cannot see ----------


def test_every_rdkit_contrib_directory_the_code_reads_is_collected_by_the_spec():
    """`Contrib/SA_Score` was caught by a launch (every Physicochemical property failed) and
    `Contrib/NP_Score` was caught the same way later, because the code appends
    `RDConfig.RDContribDir/<name>` to `sys.path` and imports a module by name: PyInstaller's
    analysis never sees it and `collect_data_files` skips `.py` files. This scans the code, so a
    third one cannot be added without the spec."""
    import re

    spec = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    used = set()
    for path in (ROOT / "src" / "openchem").rglob("*.py"):
        if "vendor" in path.parts:
            continue
        used.update(re.findall(r"RDContribDir\}?/([A-Za-z_]+)", path.read_text(encoding="utf-8")))
    assert {"SA_Score", "NP_Score"} <= used, f"the scan found {used}; has the access pattern changed?"
    for name in sorted(used):
        assert f"Contrib/{name}/*.py" in spec, f"the code reads RDKit's Contrib/{name} but the spec does not collect its .py files"
        directory = "Contrib" + chr(92) + name + chr(92)
        assert directory in build, f"build.ps1 does not check that {directory} is in the built tree"


def test_the_natural_product_scorer_works_the_way_the_frozen_app_will_load_it():
    """From a checkout the module is found where RDKit installs it; this is the same call the
    app makes, so a descriptor batch cannot be broken by this import."""
    from openchem.chem import descriptor_providers

    module, model = descriptor_providers._load_npscorer()
    assert hasattr(module, "scoreMol") and model
