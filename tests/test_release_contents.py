"""`docs/RELEASE_CONTENTS.md` says what a release holds; this keeps it true.

A map nobody checks drifts. What can be checked mechanically is checked: every
tracked top-level entry has a row, nothing the page calls "not shipped" is
named as release data by the spec or the build script, and the loose files the
build refuses are all written down. The sizes in the page are a snapshot and are
not asserted.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "docs" / "RELEASE_CONTENTS.md").read_text(encoding="utf-8")

#: Entries the page says DO reach a release. Everything else tracked at the top is "No".
SHIPS = {
    "src", "plugins", "docs",
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "CITATION.cff", "LICENSE",
}


def _tracked_top_level() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return {path.split("/")[0] for path in result.stdout.split("\0") if path}


def _top_level_section() -> str:
    return PAGE.split("## The repository's top level", 1)[1].split("\n## ", 1)[0]


def _rows() -> dict[str, str]:
    """Top-level table: every backticked name in the first cell -> that row's 'In the release?' cell."""
    rows: dict[str, str] = {}
    for line in _top_level_section().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", " "} or cells[0] == "Entry":
            continue
        for name in re.findall(r"`([^`]+)`", cells[0]):
            rows[name] = cells[1]
    return rows


def test_the_page_found_its_table():
    assert len(_rows()) > 20, "the table was not parsed; has its format changed?"


@pytest.mark.parametrize("entry", sorted(_tracked_top_level()))
def test_every_tracked_top_level_entry_has_a_row(entry):
    assert entry in _rows(), (
        f"`{entry}` is tracked at the repository root but docs/RELEASE_CONTENTS.md does not say "
        "whether it reaches a release. Add a row to the top-level table."
    )


def test_exactly_the_shipping_entries_are_marked_as_shipping():
    rows = _rows()
    marked_yes = {name for name, cell in rows.items() if cell.lower().startswith("yes")}
    assert marked_yes == SHIPS, f"the page and the test disagree about what ships: {marked_yes ^ SHIPS}"
    for name, cell in rows.items():
        if name not in SHIPS:
            assert "No" in cell, f"{name}: {cell!r}"


def test_nothing_marked_not_shipped_is_named_as_release_data_by_the_build():
    """A 'No' row that the spec or build script copies would make the page a lie."""
    spec = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    # A `datas` entry is a (source, destination) pair, so a ROOT path followed by a
    # destination string is data; the launcher script handed to Analysis is not.
    data_roots = set(re.findall(r'str\(ROOT / "([^"]+)"[^)]*\)\s*,\s*"', spec))
    for name, cell in _rows().items():
        if name in SHIPS or not (ROOT / name).is_dir():
            continue
        assert name not in data_roots, f"the spec ships `{name}` as data, which the page says does not ship"
        assert not re.search(rf'Copy-Item\s+"\$ROOT\\{re.escape(name)}\b', build), (
            f"build.ps1 copies `{name}` into the release, which the page says does not ship"
        )


def test_the_staged_documents_match_the_page():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    staged = set(re.findall(r'"(README\.md|LICENSE|CHANGELOG\.md|CONTRIBUTING\.md|CODE_OF_CONDUCT\.md|CITATION\.cff)"', build))
    assert staged == {"README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "CITATION.cff"}
    assert 'Copy-Item "$ROOT\\docs"' in build and 'Copy-Item "$ROOT\\plugins"' in build


def test_every_file_the_build_refuses_to_ship_loose_is_written_down():
    spec = importlib.util.spec_from_file_location("make_release_zip", ROOT / "tools" / "make_release_zip.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_release_zip"] = module
    spec.loader.exec_module(module)
    for forbidden in module.FORBIDDEN_PATHS:
        leaf = forbidden.rstrip("/").split("/")[-1]
        assert leaf in PAGE, f"the release refuses {forbidden} but docs/RELEASE_CONTENTS.md does not mention {leaf}"
    for part in module.FORBIDDEN_PARTS:
        assert part in PAGE
    for required in module.REQUIRED:
        assert required.split("/")[-1] in PAGE.replace("`", ""), f"{required} must be in the release but is not on the page"


def test_the_page_names_the_four_help_documents_the_app_reads():
    sys.path.insert(0, str(ROOT / "src"))
    from openchem import help as help_docs

    for document in help_docs.HELP_DOCUMENTS:
        assert document.removesuffix(".md") in PAGE, f"{document} is a help document but the page does not name it"
