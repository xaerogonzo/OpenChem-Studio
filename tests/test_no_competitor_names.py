"""Other companies' products are not named in this repository.

The project does not describe itself in terms of commercial products it resembles or compares
itself to. Where a number was checked against one, the documents say that it was checked against
"the reference editor" (or "the vendor"), defined once in `docs/README.md`, and say what was read
and where. This keeps it true: a name that creeps back into a comment, a document, a test name
or a user-visible string fails here.

The names are built from fragments below so that this file does not contain them either. They
live in the maintainer's private notes, outside the repository.

NOT SCANNED: the third-party bundles in `src/openchem/resources/ketcher/dist/` and
`src/openchem/resources/molstar/`, which are other projects' minified code. A file-format
identifier such as the `Mrv` header tag in a molfile fixture contains none of these names and
is data, not prose.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Assembled from pieces; see the module docstring.
_NAMES = (
    "mar" + "vin",
    "chem" + "axon",
    "cx" + "calc",
    "amsterdam " + "modeling",
    "scm" + ".com",
)
_PATTERN = re.compile("|".join(re.escape(name) for name in _NAMES), re.IGNORECASE)

_NOT_SCANNED_PREFIXES = (
    "src/openchem/resources/ketcher/dist/",
    "src/openchem/resources/molstar/",
)
_NOT_SCANNED_FILES = {"uv.lock"}


def _tracked_text_files() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    return [f for f in tracked if f and f not in _NOT_SCANNED_FILES and not f.startswith(_NOT_SCANNED_PREFIXES)]


def _offences() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for rel in _tracked_text_files():
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary, or not ours to read
        lines = [i + 1 for i, line in enumerate(text.splitlines()) if _PATTERN.search(line)]
        # A file NAME counts too: a renamed document must not keep the name in its path.
        if _PATTERN.search(rel):
            lines.insert(0, 0)
        if lines:
            found[rel] = lines
    return found


def test_the_scan_reads_a_real_number_of_files():
    """A scan that read nothing would pass for any repository."""
    assert len(_tracked_text_files()) > 1000


def test_no_other_products_name_is_in_the_repository():
    offences = _offences()
    assert not offences, (
        "Other companies' product names are not used in this repository. Say 'the reference editor' "
        "(a commercial structure editor) or 'the vendor' (its maker), defined in docs/README.md, and say "
        "what was checked and where it was read. Found in: "
        + "; ".join(f"{path} (lines {', '.join(map(str, lines[:5]))})" for path, lines in sorted(offences.items())[:15])
    )


def test_the_guard_can_fail():
    """Proof that the pattern matches what it is meant to, on text made of the same fragments."""
    assert _PATTERN.search("matches " + _NAMES[0].capitalize() + "'s own output")
    assert _PATTERN.search(_NAMES[1].upper() + "-style options")
    assert _PATTERN.search("see https://www." + _NAMES[4])
    assert not _PATTERN.search("the reference editor's own output")
    assert not _PATTERN.search("  Mrv2014 molfile header")


def test_the_two_terms_the_documents_use_are_defined_once_in_the_docs_index():
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "**The reference editor**" in index and "**The vendor**" in index
