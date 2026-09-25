"""The literature manifest is a record, and a record has rules.

`docs/research/literature.toml` says what the survey reads and how each source is held. What these tests
guard is the SHAPE that keeps it honest: `printed` (checkable) apart from `assigned` (a judgement), a closed
vocabulary for access so that "we could not read it" can never be filed as "we rejected it", a DOI only when
the paper prints one, and counts that are generated rather than typed.

The one thing they do not do is read a PDF: identity was established by reading each file's first page, and
`tools/index_literature.py --check` verifies the files are unchanged (skipped here when the library is not on
the machine, which is every machine but the maintainer's).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "index_literature.py"
README = ROOT / "docs" / "research" / "README.md"
#: Where the maintainer's library lives, tried when `OPENCHEM_PDF_LIBRARY` is unset.
DEFAULT_LIBRARY = Path(r"D:\Xaero Stuff\Documents\Sci Downloads")

_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("index_literature", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def entries(tool):
    return tool.load_manifest()


def test_ids_are_unique(entries):
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


def test_the_vocabularies_are_closed(tool, entries):
    """A typo'd state must be an error, never a quiet new category."""
    for entry in entries:
        assert entry["access"] in tool.ACCESS_STATES, (entry["id"], entry["access"])
        assert entry["assigned"]["property"] in tool.PROPERTIES, (entry["id"], entry["assigned"]["property"])
        assert entry["assigned"]["role"] in tool.ROLES, (entry["id"], entry["assigned"]["role"])


def test_there_is_no_rejected_state(tool):
    """An access state is not a verdict. A rejection is a scientific decision with a recorded reason."""
    assert not any("reject" in state for state in tool.ACCESS_STATES)


def test_a_held_file_is_pinned_and_an_unheld_one_names_no_file(tool, entries):
    for entry in entries:
        if entry["access"] in tool.HELD_STATES:
            assert entry.get("file", "").endswith(".pdf"), entry["id"]
            assert _SHA.match(entry.get("sha256", "")), entry["id"]
            assert isinstance(entry.get("pages"), int) and entry["pages"] > 0, entry["id"]
        else:
            assert "file" not in entry and "sha256" not in entry, (
                f"{entry['id']} is {entry['access']} but names a file"
            )


def test_a_doi_is_well_formed_or_absent_and_never_repeated(entries):
    seen: dict[str, str] = {}
    for entry in entries:
        doi = entry["printed"]["doi"]
        if not doi:
            continue
        assert _DOI.match(doi), (entry["id"], doi)
        assert doi == doi.strip() and "\ufb02" not in doi and "\x05" not in doi, (entry["id"], doi)
        assert doi not in seen, f"{doi} is on both {seen[doi]} and {entry['id']}"
        seen[doi] = entry["id"]


def test_every_entry_says_what_the_paper_is_for_in_our_words_and_not_its_own(entries):
    """`printed` and `assigned` stay two tables: the first can be checked against a file, the second is a
    judgement. A title under `assigned`, or a role under `printed`, would blur exactly that."""
    for entry in entries:
        assert set(entry["assigned"]) == {"property", "role"}, entry["id"]
        assert set(entry["printed"]) <= {"doi", "title", "venue"}, entry["id"]


def test_a_request_records_its_date(entries):
    for entry in entries:
        if entry["access"] == "requested":
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", entry.get("requested", "")), entry["id"]


def test_the_two_gharagheizi_2011_files_are_two_different_papers(entries):
    """Two files named alike, two works: the sublimation model and the enthalpy of FUSION."""
    by_id = {e["id"]: e for e in entries}
    a, b = by_id["gharagheizi2011_subl"], by_id["gharagheizi2011_fusion"]
    assert a["printed"]["doi"] != b["printed"]["doi"]
    assert (a["assigned"]["property"], b["assigned"]["property"]) == ("enthalpy_sublimation", "enthalpy_fusion")


def test_a_paper_that_was_only_an_accepted_manuscript_or_a_preproof_says_so(entries):
    by_id = {e["id"]: e for e in entries}
    assert by_id["mathieu2018_iecr"]["access"] == "held_accepted_manuscript"
    assert by_id["keshavarz2021"]["access"] == "held_preproof"
    assert by_id["burkhardt2026"]["access"] == "held_si_only"


def test_the_readme_quotes_no_hand_typed_count_of_papers():
    """Counts come from `--counts`. A typed "36 papers" is what goes stale the day one is added."""
    text = README.read_text(encoding="utf-8")
    assert not re.search(r"\b\d+\s+(papers|sources|entries|files|PDFs)\b", text, re.I)


def test_the_counts_are_generated_from_the_entries(tool, entries):
    generated = tool.counts(entries)
    assert generated["entries"]["total"] == len(entries)
    assert sum(generated["access"].values()) == len(entries)
    assert sum(generated["property"].values()) == len(entries)


def test_a_missing_library_skips_and_says_so(tool, entries, capsys):
    assert tool.check(None, entries) == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_a_held_file_that_changed_is_reported(tool, entries, tmp_path, capsys):
    """The check must be able to FAIL: an empty library says every held file is missing."""
    assert tool.check(tmp_path, entries) == 1
    assert "is not in the library" in capsys.readouterr().out


def test_a_file_with_the_right_name_and_the_wrong_content_is_reported(tool, entries, tmp_path, capsys):
    """The name is a locator, not identity: a different file under the same name must not pass."""
    first = next(e for e in entries if e["access"] in tool.HELD_STATES)
    (tmp_path / first["file"]).write_bytes(b"not the paper")
    assert tool.check(tmp_path, entries) == 1
    assert f"{first['id']}: {first['file']} is not the file that was identified" in capsys.readouterr().out


def test_the_held_files_are_the_ones_that_were_read(tool, entries):
    """Runs only on the machine that has the library."""
    import os

    raw = os.environ.get("OPENCHEM_PDF_LIBRARY")
    library = Path(raw) if raw else DEFAULT_LIBRARY
    if not library.is_dir():
        pytest.skip("no PDF library on this machine")
    assert tool.check(library, entries) == 0
