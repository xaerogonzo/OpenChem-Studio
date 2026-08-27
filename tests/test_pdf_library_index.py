"""Guards for `tools/index_pdf_library.py`.

**EVERY TEST HERE BUILDS ITS OWN BYTES.** The real library is one folder on
one machine and is not in the repo, so a test that needed it would skip
everywhere that matters -- which is the failure mode the tool itself is
written against. `searchable()` scans bytes and inflates streams rather
than parsing PDF structure, so a handful of literal bytes with a
`FlateDecode` stream in the middle exercises exactly the code path a real
file does.

The load-bearing pair is `test_a_file_carrying_only_a_foreign_doi_is_flagged`
against `test_a_file_with_no_evidence_is_unresolved_and_that_is_not_a_failure`.
Together they pin the line the whole design turns on: **the tool must be
able to say NO, and must not say NO merely because it could not tell.**
Collapsing either into the other is the mutation that matters -- one makes
it cry wolf on three scans and two reference books, the other makes it
incapable of reporting a genuinely wrong file.
"""

from __future__ import annotations

import importlib.util
import json
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "index_pdf_library.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("index_pdf_library", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


index_pdf_library = _load_tool()


def _pdf(visible: str = "", compressed: str = "") -> bytes:
    """Bytes shaped like a PDF: some plain text, some inside a Flate stream."""
    body = b"%PDF-1.4\n" + visible.encode("latin-1")
    if compressed:
        body += b"\nstream\n" + zlib.compress(compressed.encode("latin-1")) + b"\nendstream\n"
    return body + b"\n%%EOF\n"


def _entry(key, identifier_type="doi", identifier="10.1000/aaa", citation="", local="x.pdf"):
    return {
        "key": key,
        "identifier_type": identifier_type,
        "identifier": identifier,
        "citation": citation,
        "local": local,
    }


# ---------------------------------------------------------------------------
# The library gate: skipping is not passing
# ---------------------------------------------------------------------------


def test_no_library_is_none_rather_than_an_error(monkeypatch, tmp_path):
    monkeypatch.delenv(index_pdf_library.LIBRARY_ENV, raising=False)
    assert index_pdf_library.library_path() is None
    # A path that is set but does not exist is also "no library here",
    # not a crash -- a stale env var must not take the suite down.
    assert index_pdf_library.library_path(str(tmp_path / "nope")) is None
    assert index_pdf_library.library_path(str(tmp_path)) == tmp_path


def test_check_without_a_library_says_so_instead_of_passing_quietly(monkeypatch, capsys):
    """A gate is worth what its ability to admit it did not run is worth."""
    monkeypatch.delenv(index_pdf_library.LIBRARY_ENV, raising=False)
    assert index_pdf_library.check(None, []) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "not a pass" in out


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------


def test_a_doi_inside_a_compressed_stream_is_found(monkeypatch):
    """The zlib half. A raw-byte scan alone misses 8 of the 44 real entries."""
    blob = index_pdf_library.searchable(_pdf(compressed="see doi:10.1107/S0108767394013292 here"))
    assert b"10.1107/S0108767394013292" in blob


def test_an_uninflatable_stream_is_skipped_rather_than_fatal():
    """Not every stream is FlateDecode; one we cannot read is not evidence."""
    raw = b"%PDF-1.4\nstream\nnot-actually-compressed\nendstream\n"
    assert index_pdf_library.searchable(raw).startswith(b"%PDF")


def test_the_key_supplies_the_author_and_year():
    assert index_pdf_library.key_surname_and_year("gasteiger1980") == ("gasteiger", "1980")
    assert index_pdf_library.key_surname_and_year("vogel_drago1996") == ("vogel", "1996")
    # Keys that are not <surname><year> yield nothing, which is correct for
    # them rather than a gap -- `crc_handbook` has no author-year shape.
    assert index_pdf_library.key_surname_and_year("crc_handbook") is None
    assert index_pdf_library.key_surname_and_year("orca") is None
    # Too short to be a surname: `ran2002` would match far too much.
    assert index_pdf_library.key_surname_and_year("abc1999") is None


def test_the_title_words_come_from_the_quoted_part_of_a_citation():
    citation = "S. L. Mayo et al., 'DREIDING: A Generic Force Field', J. Phys. Chem. 1990."
    assert index_pdf_library.title_words(citation) == ["DREIDING", "Generic", "Force"]
    assert index_pdf_library.title_words("no quoted title here") == []


# ---------------------------------------------------------------------------
# Classification: the four confidences
# ---------------------------------------------------------------------------


def test_a_declared_doi_present_in_the_file_is_doi_exact():
    entry = _entry("smith1990", identifier="10.1000/xyz")
    record = index_pdf_library.classify(entry, _pdf("10.1000/xyz"), [])
    assert record["confidence"] == index_pdf_library.DOI_EXACT
    assert "doi" in record["evidence"]


def test_a_missing_doi_falls_back_to_author_and_year_rather_than_failing():
    """THE ARM WITHOUT WHICH THE TOOL SILENTLY BECOMES DOI-ONLY.

    Measured on the real registry: the declared DOI is absent from 20 of
    44 DOI-bearing PDFs, because it was assigned retroactively and never
    printed. Demanding it would fail 45% of them, every failure false.
    """
    entry = _entry("gasteiger1980", identifier="10.1016/0040-4020(80)80168-2")
    record = index_pdf_library.classify(entry, _pdf("Gasteiger, Tetrahedron 1980"), [])
    assert record["confidence"] == index_pdf_library.BIBLIOGRAPHIC
    assert record["evidence"] == ["surname_year"]


def test_a_file_carrying_only_a_foreign_doi_is_flagged():
    """The narrow half: the tool's whole ability to say NO.

    A file that carries some OTHER registry entry's DOI and no evidence of
    its own is the one shape that means "this is the wrong paper". Over
    the shipped registry it fires zero times, which is what makes it a
    signal rather than noise -- 3 of 44 files contain a foreign DOI and
    all three also carry their own.
    """
    entry = _entry("smith1990", identifier="10.1000/mine")
    record = index_pdf_library.classify(
        entry, _pdf("10.1000/yours"), [("jones1985", "10.1000/yours")]
    )
    assert record["confidence"] == index_pdf_library.AMBIGUOUS
    assert record["foreign_dois"] == ["jones1985"]


def test_a_foreign_doi_alongside_its_own_is_just_a_reference_list():
    """The control for the arm above, and the reason it is not noise.

    Every paper's bibliography carries other people's DOIs. Only the
    ABSENCE of its own makes a foreign one meaningful.
    """
    entry = _entry("smith1990", identifier="10.1000/mine")
    record = index_pdf_library.classify(
        entry, _pdf("10.1000/mine and also 10.1000/yours"), [("jones1985", "10.1000/yours")]
    )
    assert record["confidence"] == index_pdf_library.DOI_EXACT


def test_a_file_with_no_evidence_is_unresolved_and_that_is_not_a_failure(tmp_path, capsys):
    """The wide half: "I could not tell" must not render as "this is wrong".

    Five real entries land here -- three scans with no text layer and two
    reference books whose identity is on a cover page -- and every one of
    them is exactly the file it should be.
    """
    entry = _entry("nothing1999", identifier="10.1000/absent", local="blank.pdf")
    record = index_pdf_library.classify(entry, _pdf("unrelated bytes"), [])
    assert record["confidence"] == index_pdf_library.UNRESOLVED

    (tmp_path / "blank.pdf").write_bytes(_pdf("unrelated bytes"))
    assert index_pdf_library.check(tmp_path, [entry]) == 0
    assert "unresolved" in capsys.readouterr().out


def test_a_named_file_that_is_absent_IS_a_failure(tmp_path, capsys):
    """Distinct from unresolved: the registry points at nothing."""
    entry = _entry("gone1999", local="not-here.pdf")
    assert index_pdf_library.check(tmp_path, [entry]) == 1
    assert "MISSING" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def test_byte_identical_files_under_two_names_are_reported(tmp_path):
    """The practical payoff: identity comes from the file, not the name."""
    payload = _pdf("10.1000/same")
    (tmp_path / "mayo1990.pdf").write_bytes(payload)
    (tmp_path / "DREIDING A Generic Force Field.pdf").write_bytes(payload)
    (tmp_path / "different.pdf").write_bytes(_pdf("something else"))

    report = index_pdf_library.duplicates(tmp_path, [])
    assert len(report["identical_bytes"]) == 1
    names = sorted(next(iter(report["identical_bytes"].values())))
    assert names == ["DREIDING A Generic Force Field.pdf", "mayo1990.pdf"]


# ---------------------------------------------------------------------------
# The manifest, and what it is allowed to claim
# ---------------------------------------------------------------------------


def test_the_manifest_records_HOW_identity_was_established(tmp_path):
    """Not just what was found. The index proves ARTIFACT identity only."""
    (tmp_path / "x.pdf").write_bytes(_pdf("10.1000/aaa"))
    index = index_pdf_library.build_index(tmp_path, [_entry("smith1990")])
    record = index["records"][0]
    assert record["confidence"] == index_pdf_library.DOI_EXACT
    assert record["evidence"] == ["doi"]
    assert len(record["sha256"]) == 64
    assert json.dumps(index)  # the manifest must be serialisable


def test_the_tool_hardcodes_nobodys_library_path():
    """It is one person's folder on one machine."""
    source = TOOL.read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]  # skip the module docstring
    assert "Sci Downloads" not in body
    assert "Xaero" not in body


def test_the_index_never_claims_to_verify_a_CLAIM():
    """`verification` in sources.toml is about the SOURCE, not the file.

    The tool's vocabulary must stay disjoint from the registry's three
    values, or a reader will eventually take `doi_exact` for
    `citation_and_claim` -- "this file is that paper" promoted to "that
    paper supports this number".
    """
    registry_words = {"unverified", "citation", "citation_and_claim"}
    ours = {
        index_pdf_library.DOI_EXACT,
        index_pdf_library.BIBLIOGRAPHIC,
        index_pdf_library.AMBIGUOUS,
        index_pdf_library.UNRESOLVED,
    }
    assert not (ours & registry_words)


# ---------------------------------------------------------------------------
# The opt-in guard over the REAL library
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    index_pdf_library.library_path() is None,
    reason=f"no PDF library here; set {index_pdf_library.LIBRARY_ENV} to check `local`",
)
def test_every_local_claim_in_the_registry_holds():
    """`sources.toml`'s `local` field, checked for the first time.

    That field has been documented in the registry itself as "NOT checked
    by any guard -- that folder is not in the repo". This is the guard,
    and it is opt-in rather than absent: it runs where the library exists
    and skips, naming the missing prerequisite, everywhere else.

    It fails on a file that is ABSENT or that carries another work's
    identity. It does NOT fail on `unresolved` -- see the pair of tests
    above for why those are different answers.
    """
    library = index_pdf_library.library_path()
    entries = index_pdf_library.load_entries()
    assert index_pdf_library.check(library, entries) == 0
