"""The library index: pure pieces, and the whole cycle with a stand-in for the PDF reader.

`tools/library_index.py` needs pymupdf only to read a PDF, and pymupdf is not a project dependency, so every
test here replaces `extract_pages` and runs on dummy `.pdf` files -- except one that builds a real PDF and is
skipped where pymupdf is absent. What is pinned is the behaviour that makes an index trustworthy: a scanned file
is LISTED rather than silently unsearchable, a search expression cannot be turned into an operator by what is
typed, and an unchanged file is not read again.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "library_index.py"
#: Assembled, never written whole: a DOI-shaped literal is a citation as far as `test_sources_are_current` is concerned.
D = "10."


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("library_index", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- pure pieces ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Journal of X. https://doi.org/" + D + "1021/acs.jced.5c00573.", D + "1021/acs.jced.5c00573"),
        ("doi:" + D + "1002/prep.70064)", D + "1002/prep.70064"),
        ("no identifier here", ""),
        ("", ""),
        ("see " + D + "1038/s42004-025-01544-9, and also", D + "1038/s42004-025-01544-9"),
    ],
)
def test_find_doi_trims_the_sentence_around_it(tool, text, expected):
    assert tool.find_doi(text) == expected


def test_a_file_with_almost_no_text_is_scanned(tool):
    assert tool.is_scanned(chars=40, pages=200)
    assert not tool.is_scanned(chars=900_000, pages=200)
    assert not tool.is_scanned(chars=0, pages=0), "an unreadable file is an error, not a scan"


@pytest.mark.parametrize(
    "typed",
    ['2,4-DNT', 'NEAR(a b)', 'a" OR "b', "x AND y", "-negated", "col:umn", "(paren"],
)
def test_nothing_typed_becomes_a_search_operator(tool, typed):
    """The whole expression is one quoted phrase, so punctuation and keywords are searched, not parsed."""
    expression = tool.fts_query(typed)
    assert expression.startswith('"') and expression.endswith('"')
    assert expression.count('"') - 2 * typed.count('"') == 2


def test_a_trailing_star_is_a_prefix_and_nothing_else_is_an_operator(tool):
    assert tool.fts_query("PETN", near=["solub*"]) == 'NEAR("PETN" "solub"*, 30)'
    assert tool.fts_query("a*b") == '"a*b"', "a star inside a term is searched, not interpreted"


def test_a_prefix_finds_the_longer_word_and_a_bare_stem_does_not(tool, library):
    root, connection, _reads, _contents = library
    tool.update(root, connection, say=_quiet)
    stem = tool.fts_query("propylene glycol dinitrate", near=["solub"])
    prefix = tool.fts_query("propylene glycol dinitrate", near=["solub*"])
    assert not tool.search(connection, stem)
    assert [h["path"] for h in tool.search(connection, prefix)] == ["handbook.pdf"]


def test_alternatives_and_proximity_are_the_only_structure(tool):
    assert tool.fts_query("PGDN | propylene glycol dinitrate") == '"PGDN" OR "propylene glycol dinitrate"'
    assert tool.fts_query("PETN", near=["solubility"], within=40) == 'NEAR("PETN" "solubility", 40)'
    assert tool.fts_query("RDX", also=["water"]) == '("RDX") AND "water"'
    with pytest.raises(ValueError):
        tool.fts_query(" | ")


def test_a_literature_key_is_a_clean_slug(tool):
    assert tool.slug("Aqueous Solubility Methods of Estimation for Organic Compound.pdf") == (
        "aqueous_solubility_methods_of_estimation_for_organic_compound"
    )
    assert tool.slug("....pdf") == "paper"


# --- the cycle, with the PDF reader replaced ------------------------------------------------------------------------


@pytest.fixture
def library(tool, tmp_path, monkeypatch):
    """A folder of dummy PDFs and a stand-in `extract_pages` that serves text from a dict, counting reads."""
    root = tmp_path / "Sci Downloads"
    (root / "sub").mkdir(parents=True)
    contents = {
        "handbook.pdf": ["front matter", "1,2-Propylene glycol dinitrate  solubility 1.6 g/L at 20 C", "tail"],
        "paper.pdf": ["Title page doi:" + D + "1000/xyz123.", "RDX is sparingly soluble in water"],
        "sub/scan.pdf": ["", "3"],
        "sub/broken.pdf": None,
    }
    for name in contents:
        (root / name).write_bytes(b"%PDF-dummy " + name.encode())
    reads: list[str] = []

    def fake_extract(path: Path):
        name = path.relative_to(root).as_posix()
        reads.append(name)
        pages = contents[name]
        if pages is None:
            raise RuntimeError("damaged")
        yield from pages

    monkeypatch.setattr(tool, "extract_pages", fake_extract)
    connection = tool.connect(tmp_path / "index.sqlite")
    yield root, connection, reads, contents
    connection.close()


def _quiet(_message):
    return None


def test_update_indexes_searches_and_lists_what_it_could_not_read(tool, library):
    root, connection, reads, _contents = library
    counts = tool.update(root, connection, say=_quiet)
    assert counts == {"indexed": 4, "unchanged": 0, "errors": 1, "removed": 0}

    hits = tool.search(connection, tool.fts_query("propylene glycol dinitrate | PGDN", near=["solubility"]))
    assert [(h["path"], h["page"]) for h in hits] == [("handbook.pdf", 2)]
    assert "[[" in hits[0]["snippet"], "the matched words are marked"
    assert tool.search(connection, tool.fts_query("RDX"), file_filter="paper")

    report = tool.stats(connection)
    assert "sub/scan.pdf" in report, "a scan is LISTED, because it can never match"
    assert "sub/broken.pdf: RuntimeError: damaged" in report

    paper = connection.execute("SELECT doi, pages, sha256 FROM files WHERE path = 'paper.pdf'").fetchone()
    assert paper["doi"] == D + "1000/xyz123" and paper["pages"] == 2 and len(paper["sha256"]) == 64


def test_an_unchanged_file_is_not_read_again_and_a_changed_one_is(tool, library):
    root, connection, reads, contents = library
    tool.update(root, connection, say=_quiet)
    reads.clear()
    counts = tool.update(root, connection, say=_quiet)
    assert reads == [] or reads == ["sub/broken.pdf"], "only the file that failed may be retried"
    assert counts["unchanged"] >= 3

    changed = root / "paper.pdf"
    changed.write_bytes(changed.read_bytes() + b" more")
    contents["paper.pdf"] = ["Title page", "HMX is poorly soluble in water"]
    reads.clear()
    tool.update(root, connection, say=_quiet)
    assert "paper.pdf" in reads
    assert tool.search(connection, tool.fts_query("HMX"))
    assert not tool.search(connection, tool.fts_query("RDX")), "the old pages are gone, not left to match"


def test_a_removed_file_is_forgotten(tool, library):
    root, connection, _reads, _contents = library
    tool.update(root, connection, say=_quiet)
    (root / "paper.pdf").unlink()
    counts = tool.update(root, connection, say=_quiet)
    assert counts["removed"] == 1
    assert not tool.search(connection, tool.fts_query("sparingly"))


def test_the_index_is_a_sibling_of_the_library_so_a_walk_never_meets_it(tool, tmp_path):
    root = tmp_path / "Sci Downloads"
    root.mkdir()
    assert tool.index_path(root) == tmp_path / "Sci Downloads.index.sqlite"
    assert root not in tool.index_path(root).parents


def test_a_page_can_be_read_back_by_a_unique_fragment_of_its_name(tool, library):
    root, connection, _reads, _contents = library
    tool.update(root, connection, say=_quiet)
    assert "sparingly" in tool.page_text(connection, "paper", 2)
    with pytest.raises(SystemExit):
        tool.page_text(connection, "s", 1)  # matches several files: refuse rather than guess


def test_the_draft_entry_is_valid_toml_and_fills_only_what_a_machine_can_know(tool, library):
    root, connection, _reads, _contents = library
    tool.update(root, connection, say=_quiet)
    entry = tomllib.loads(tool.stub(connection, "paper.pdf"))["source"][0]
    assert entry["id"] == "paper" and entry["pages"] == 2 and entry["access"] == "held"
    assert entry["printed"]["doi"] == D + "1000/xyz123"
    assert entry["printed"]["title"] == "" and entry["assigned"]["property"] == "", "a person writes these"
    assert len(entry["sha256"]) == 64


def test_a_real_pdf_round_trips(tool, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    root = tmp_path / "lib"
    root.mkdir()
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Nitroglycerin solubility 1.25 g/L doi:" + D + "1000/real.1")
    document.save(root / "real.pdf")
    document.close()
    connection = tool.connect(tmp_path / "index.sqlite")
    tool.update(root, connection, say=_quiet)
    assert tool.search(connection, tool.fts_query("nitroglycerin", near=["solubility"]))
    assert connection.execute("SELECT doi FROM files").fetchone()["doi"] == D + "1000/real.1"
    connection.close()
