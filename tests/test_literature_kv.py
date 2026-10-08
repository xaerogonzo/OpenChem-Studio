"""`tools/index_literature.py --check` with Knowledge Vista: a renamed paper is not a changed paper, and nothing KV says is believed unhashed.

The rule these tests hold (docs/research/README.md): KV answers from a catalog that may be stale, so a path it names counts only if the
bytes at that path hash to the recorded sha256; and KV being absent, slow or wrong changes nothing about what is checked.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("fake_kv.py")
DOC = "c" * 32


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def tool():
    spec = importlib.util.spec_from_file_location("index_literature_kv", ROOT / "tools" / "index_literature.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def kv(tool):
    module = tool._load_sibling("kv_client")
    module.forget()
    yield module
    module.forget()


@pytest.fixture
def library(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    return lib


def entry(name="paper.pdf", data=b"the paper", **extra):
    return {"id": name.removesuffix(".pdf"), "file": name, "sha256": sha(data), "access": "held", **extra}


def locator(kv, *, paths=(), document_id=DOC, status="available", calls=None, raises=None, never_seen=False):
    def locate(digest):
        if calls is not None:
            calls.append(digest)
        if raises:
            raise raises
        return None if never_seen else kv.Located(digest, document_id, status, f"knowledgevista://document/{document_id}", tuple(str(p) for p in paths))
    return locate


def run(tool, library, entries, locate, capsys):
    code = tool.check(library, entries, locate)
    return code, capsys.readouterr().out


def test_a_file_where_it_was_recorded_needs_no_one_to_vouch_for_it(tool, kv, library, capsys):
    (library / "paper.pdf").write_bytes(b"the paper")
    calls = []
    code, out = run(tool, library, [entry()], locator(kv, calls=calls), capsys)
    assert code == 0 and calls == [] and out.strip() == "checked 1 held files: 0 problem(s)"


def test_a_renamed_file_is_found_through_kv_and_verified_by_hashing_it_here(tool, kv, library, capsys):
    moved = library / "renamed.pdf"
    moved.write_bytes(b"the paper")
    calls = []
    code, out = run(tool, library, [entry()], locator(kv, paths=[moved], calls=calls), capsys)
    assert code == 0 and calls == [sha(b"the paper")]
    assert f"MOVED: paper: paper.pdf is not in the library; the identified file is now {moved}" in out
    assert "0 problem(s), 1 found elsewhere by Knowledge Vista" in out and "MISMATCH" not in out


def test_a_path_kv_names_is_not_believed_unless_its_bytes_hash_to_the_record(tool, kv, library, capsys):
    stale = library / "elsewhere.pdf"
    stale.write_bytes(b"a different paper that happens to sit where the old catalog said")
    code, out = run(tool, library, [entry()], locator(kv, paths=[stale]), capsys)
    assert code == 1 and "MOVED" not in out
    assert "MISMATCH: paper: paper.pdf is not in the library; Knowledge Vista names a path, but it does not hold these bytes" in out


def test_a_path_kv_names_that_does_not_exist_is_not_a_find(tool, kv, library, capsys):
    code, out = run(tool, library, [entry()], locator(kv, paths=[library / "ghost.pdf"]), capsys)
    assert code == 1 and "MOVED" not in out and "does not hold these bytes" in out


def test_kv_knowing_the_bytes_but_not_where_they_are_is_still_a_problem(tool, kv, library, capsys):
    code, out = run(tool, library, [entry()], locator(kv, status="missing"), capsys)
    assert code == 1 and "knows these bytes (missing) but no copy is reachable" in out


def test_kv_never_having_seen_the_bytes_is_a_problem_and_says_so(tool, kv, library, capsys):
    code, out = run(tool, library, [entry()], locator(kv, never_seen=True), capsys)
    assert code == 1 and "MISMATCH: paper: paper.pdf is not in the library; Knowledge Vista has never seen these bytes" in out


def test_a_replaced_file_is_a_mismatch_unless_the_identified_bytes_still_exist_elsewhere(tool, kv, library, capsys):
    (library / "paper.pdf").write_bytes(b"someone saved a different paper over it")
    code, out = run(tool, library, [entry()], locator(kv, never_seen=True), capsys)
    assert code == 1 and "is not the file that was identified (sha256 differs); Knowledge Vista has never seen these bytes" in out
    original = library / "kept-original.pdf"
    original.write_bytes(b"the paper")
    code, out = run(tool, library, [entry()], locator(kv, paths=[original]), capsys)
    assert code == 0 and f"MOVED: paper: paper.pdf is not the file that was identified (sha256 differs); the identified file is now {original}" in out


def test_without_kv_the_messages_are_exactly_what_they_always_were(tool, kv, library, capsys):
    code, out = run(tool, library, [entry()], None, capsys)
    assert code == 1 and out.splitlines() == ["MISMATCH: paper: paper.pdf is not in the library", "checked 1 held files: 1 problem(s)"]


def test_kv_unreachable_is_reported_once_when_it_was_asked_for_and_never_when_it_was_not(tool, kv, library, capsys, monkeypatch):
    broken = locator(kv, raises=kv.KvUnavailable("`kv locate` did not answer within 20 s"))
    entries = [entry("a.pdf", b"a"), entry("b.pdf", b"b")]
    monkeypatch.setenv("OPENCHEM_KV", str(FAKE))
    code, out = run(tool, library, entries, broken, capsys)
    assert code == 1 and out.count("NOTE: Knowledge Vista could not be asked") == 1  # once, not once per paper
    assert out.count("MISMATCH") == 2 and "could not be asked (`kv locate` did not answer within 20 s)" in out
    monkeypatch.delenv("OPENCHEM_KV")
    code, out = run(tool, library, entries, broken, capsys)
    assert code == 1 and "NOTE" not in out and out.count("MISMATCH") == 2  # an unset KV is the normal case: silence


def test_kv_is_not_asked_when_there_is_no_library_to_check(tool, kv, capsys):
    calls = []
    code, out = run(tool, None, [entry()], locator(kv, calls=calls), capsys)
    assert code == 0 and calls == [] and out.startswith("SKIPPED")


def test_only_held_entries_are_checked_at_all(tool, kv, library, capsys):
    calls = []
    entries = [{"id": "x", "access": "not_held"}, {"id": "y", "access": "requested"}]
    code, out = run(tool, library, entries, locator(kv, calls=calls), capsys)
    assert code == 0 and calls == [] and "checked 0 held files" in out


# ------------------------------------------------------------------------------------------------ main(), end to end with a mock kv


@pytest.fixture
def renamed(tool, library, tmp_path, monkeypatch):
    moved = library / "renamed.pdf"
    moved.write_bytes(b"the paper")
    monkeypatch.setenv("OPENCHEM_PDF_LIBRARY", str(library))
    monkeypatch.setattr(tool, "load_manifest", lambda *a, **k: [entry()])
    monkeypatch.setenv("FAKE_KV_PATH", str(moved))
    monkeypatch.setenv("FAKE_KV_LOG", str(tmp_path / "kv.log"))
    monkeypatch.delenv("OPENCHEM_KV_CATALOG", raising=False)
    return moved


def test_check_through_a_mock_kv_passes_a_renamed_paper(tool, kv, renamed, capsys, monkeypatch):
    monkeypatch.setenv("OPENCHEM_KV", str(FAKE))
    assert tool.main(["--check"]) == 0
    out = capsys.readouterr().out
    assert f"the identified file is now {renamed}" in out and "1 found elsewhere by Knowledge Vista" in out


def test_no_kv_flag_and_no_kv_installed_both_give_the_old_answer(tool, kv, renamed, capsys, monkeypatch):
    monkeypatch.setenv("OPENCHEM_KV", str(FAKE))
    assert tool.main(["--check", "--no-kv"]) == 1
    assert "MISMATCH: paper: paper.pdf is not in the library\n" in capsys.readouterr().out
    monkeypatch.delenv("OPENCHEM_KV")
    monkeypatch.setattr(kv.shutil, "which", lambda name: None)
    assert tool.main(["--check"]) == 1
    assert "NOTE" not in capsys.readouterr().out


def test_check_with_a_misbehaving_kv_still_fails_the_missing_file_and_does_not_crash(tool, kv, renamed, capsys, monkeypatch):
    monkeypatch.setenv("OPENCHEM_KV", str(FAKE))
    for mode in ("malformed", "crash", "unknown", "ambiguous", "wrongbytes"):
        kv.forget()
        monkeypatch.setenv("FAKE_KV_LOCATE", mode)
        assert tool.main(["--check"]) == 1, mode
        assert "MISMATCH: paper:" in capsys.readouterr().out
    kv.forget()
    monkeypatch.setenv("FAKE_KV_LOCATE", "found")
    monkeypatch.setenv("FAKE_KV_PROTOCOL", "9")
    assert tool.main(["--check"]) == 1
    assert "protocol 9" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------ --link-kv


MANIFEST_TEXT = '''# a hand-written manifest

[[source]]
id = "first"
file = "first.pdf"
sha256 = "{a}"
pages = 3
access = "held"
printed.doi = ""

[[source]]
id = "second"
file = "second.pdf"
sha256 = "{b}"
pages = 4
access = "held"
note = """sha256 = "not a field: this is prose"
kept as it was"""

[[source]]
id = "third"
access = "not_held"
'''


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "literature.toml"
    path.write_bytes(MANIFEST_TEXT.format(a=sha(b"first"), b=sha(b"second")).encode())
    return path


def entries_of(tool, path):
    return tool.load_manifest(path)


def test_link_kv_proposes_without_writing_unless_asked(tool, kv, manifest, library, capsys):
    (library / "first.pdf").write_bytes(b"first")
    before = manifest.read_bytes()
    code = tool.link_kv(entries_of(tool, manifest), locator(kv, paths=[library / "first.pdf"]), write=False, manifest=manifest)
    out = capsys.readouterr().out
    assert code == 0 and manifest.read_bytes() == before
    assert 'LINK: first  kv_document_id = "' + DOC + '"' in out and "(dry run: add --write to record them)" in out


def test_link_kv_writes_one_line_after_the_right_sha256_and_changes_nothing_else(tool, kv, manifest, library, capsys):
    (library / "first.pdf").write_bytes(b"first")
    before = manifest.read_text(encoding="utf-8")
    tool.link_kv(entries_of(tool, manifest), locator(kv, paths=[library / "first.pdf"]), write=True, manifest=manifest)
    after = manifest.read_text(encoding="utf-8")
    inserted = f'kv_document_id = "{DOC}"\n'
    assert after.count(inserted) == 1
    lines = after.splitlines(keepends=True)
    index = lines.index(inserted)
    assert lines[index - 1] == f'sha256 = "{sha(b"first")}"\n'  # right after the first entry's sha256, not the prose one in second's note
    assert after.replace(inserted, "", 1) == before
    again = tool.load_manifest(manifest)
    assert next(e for e in again if e["id"] == "first")["kv_document_id"] == DOC


def test_linking_is_idempotent_and_skips_entries_that_already_have_an_id(tool, kv, manifest, library, capsys):
    (library / "first.pdf").write_bytes(b"first")
    for _ in range(2):
        capsys.readouterr()
        tool.link_kv(entries_of(tool, manifest), locator(kv, paths=[library / "first.pdf"]), write=True, manifest=manifest)
    assert manifest.read_text(encoding="utf-8").count("kv_document_id") == 1
    assert capsys.readouterr().out.splitlines()[0] == "0 entries can be linked; 1 not (Knowledge Vista does not have the verified bytes)"


def test_an_entry_is_linked_only_when_kv_has_its_verified_bytes(tool, kv, manifest, library, capsys):
    (library / "first.pdf").write_bytes(b"NOT the first paper")
    code = tool.link_kv(entries_of(tool, manifest), locator(kv, paths=[library / "first.pdf"]), write=True, manifest=manifest)
    out = capsys.readouterr().out
    assert code == 0 and "kv_document_id" not in manifest.read_text(encoding="utf-8") and "0 entries can be linked; 2 not" in out


def test_linking_stops_and_changes_nothing_when_kv_cannot_be_asked(tool, kv, manifest, capsys):
    before = manifest.read_bytes()
    code = tool.link_kv(entries_of(tool, manifest), locator(kv, raises=kv.KvUnavailable("no answer")), write=True, manifest=manifest)
    assert code == 1 and manifest.read_bytes() == before and "STOPPED" in capsys.readouterr().out


def test_linking_keeps_the_manifests_own_line_endings(tool, kv, manifest, library):
    (library / "first.pdf").write_bytes(b"first")
    manifest.write_bytes(manifest.read_bytes().replace(b"\n", b"\r\n"))
    tool.link_kv(entries_of(tool, manifest), locator(kv, paths=[library / "first.pdf"]), write=True, manifest=manifest)
    data = manifest.read_bytes()
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
