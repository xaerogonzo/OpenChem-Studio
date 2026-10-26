"""The help bundle: a release reads its help from the exe's archive, never from disk.

The bundle replaces loose markdown that the Help window offered to open in an
editor. These tests hold the two promises that make the swap safe: bundle mode
gives the SAME answers as file mode, and a frozen build never falls back to a
file when the bundle is wrong (a fallback would hide a broken release).
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import stat
import sys
import types
import zlib
from pathlib import Path

import pytest

from openchem import help as help_docs

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _fresh_caches():
    """The provider caches by design; every test starts and ends clean."""

    def clear():
        help_docs._document_lines.cache_clear()
        help_docs.topics.cache_clear()
        help_docs._bundle_documents.cache_clear()

    clear()
    yield
    clear()


@pytest.fixture
def documents():
    return help_docs.source_documents()


def _module_for(documents, **overrides):
    schema, digest, payload = help_docs.encode_bundle(documents)
    module = types.SimpleNamespace(SCHEMA=schema, DIGEST=digest, PAYLOAD=payload)
    for key, value in overrides.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def frozen_with(monkeypatch):
    """Pretend to be a frozen build whose bundle module is `module` (or absent)."""

    def install(module):
        monkeypatch.setattr(sys, "frozen", True, raising=False)

        def load():
            if module is None:
                raise ModuleNotFoundError("No module named 'openchem._help_bundle'", name="openchem._help_bundle")
            return module

        monkeypatch.setattr(help_docs, "_load_bundle_module", load)

    return install


def _snapshot():
    return {
        "topics": [(t.key, t.title, t.document, t.level) for t in help_docs.topics()],
        "sections": {t.key: help_docs.topic_markdown(t.key) for t in help_docs.topics()},
        "documents": {d: help_docs.document_markdown(d) for d in help_docs.HELP_DOCUMENTS},
        "search": [(h.topic.key, h.occurrences, h.in_title, h.snippet) for h in help_docs.search("Vina")],
    }


# --- parity -----------------------------------------------------------------


def test_bundle_mode_answers_exactly_as_file_mode(documents, frozen_with):
    from_files = _snapshot()
    assert help_docs.content_source() == "files"
    assert len(from_files["topics"]) >= 15 and from_files["search"]

    help_docs._document_lines.cache_clear()
    help_docs.topics.cache_clear()
    frozen_with(_module_for(documents))
    assert help_docs.content_source() == "bundle"
    assert _snapshot() == from_files


def test_the_generator_writes_a_module_that_decodes_to_the_source(tmp_path, documents):
    spec = importlib.util.spec_from_file_location("build_help_bundle", ROOT / "tools" / "build_help_bundle.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    out = tmp_path / "_help_bundle.py"
    assert tool.main(["--out", str(out)]) == 0

    generated = importlib.util.spec_from_file_location("generated_bundle", out)
    module = importlib.util.module_from_spec(generated)
    generated.loader.exec_module(module)
    assert help_docs.decode_bundle(module.SCHEMA, module.DIGEST, module.PAYLOAD) == documents
    assert not list(tmp_path.glob("*.tmp")), "the atomic write left a temp file behind"


# --- mode selection ---------------------------------------------------------


def test_a_checkout_ignores_a_stray_bundle(monkeypatch, documents):
    """A crashed build can leave the generated module behind; it must not
    shadow edits to the markdown."""
    stale = dict(documents)
    stale["QUICKSTART.md"] = "# Stale\n\nnot the real text\n"
    monkeypatch.setattr(help_docs, "_load_bundle_module", lambda: _module_for(stale))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert help_docs.content_source() == "files"
    assert "not the real text" not in "\n".join(help_docs._document_lines("QUICKSTART.md"))


def test_frozen_without_the_bundle_fails_and_does_not_read_the_disk(frozen_with):
    """The whole point: no quiet fallback to a loose file that happens to exist."""
    frozen_with(None)
    assert (help_docs.docs_directory() / "USER_GUIDE.md").is_file()  # a file IS there to be wrongly used
    with pytest.raises(help_docs.HelpUnavailable, match="no help bundle"):
        help_docs.topics()
    with pytest.raises(help_docs.HelpUnavailable, match="no help bundle"):
        help_docs.topic_markdown("docking")


def test_a_bundle_module_that_is_present_but_broken_is_reported_as_broken(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    def load():
        raise ModuleNotFoundError("No module named 'zlibx'", name="zlibx")

    monkeypatch.setattr(help_docs, "_load_bundle_module", load)
    with pytest.raises(help_docs.HelpUnavailable, match="zlibx"):
        help_docs.topics()


def test_the_open_file_copy_comes_from_the_same_provider(documents, frozen_with):
    frozen_with(_module_for(documents))
    assert help_docs.document_text("QUICKSTART.md") == documents["QUICKSTART.md"].replace("\r\n", "\n").rstrip("\n") + "\n"


# --- corruption: each is named, none falls back -------------------------------


def _mutated(documents):
    schema, digest, payload = help_docs.encode_bundle(documents)
    flipped = payload[:100] + ("A" if payload[100] != "A" else "B") + payload[101:]
    return schema, digest, payload, flipped


def test_every_kind_of_damage_is_rejected_with_a_category(documents):
    schema, digest, payload, flipped = _mutated(documents)
    canonical = help_docs._canonical_bytes(documents)
    reordered = dict(reversed(list(documents.items())))
    cases = {
        "wrong schema": (2, digest, payload),
        "mutated payload": (schema, digest, flipped),
        "mutated digest": (schema, "0" * 64, payload),
        "invalid base85": (schema, digest, "\x00not base85\x00"),
        "invalid zlib": (schema, digest, base64.b85encode(b"not zlib").decode()),
        "digest of other bytes": (schema, digest, base64.b85encode(zlib.compress(canonical + b" ")).decode()),
        "missing digest": (schema, None, payload),
    }
    for label, args in cases.items():
        with pytest.raises(help_docs.HelpUnavailable):
            help_docs.decode_bundle(*args)
        del label

    def bundle_of(obj):
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        import hashlib

        return schema, hashlib.sha256(raw).hexdigest(), base64.b85encode(zlib.compress(raw)).decode()

    not_json = b"{not json"
    import hashlib

    with pytest.raises(help_docs.HelpUnavailable, match="JSON"):
        help_docs.decode_bundle(
            schema, hashlib.sha256(not_json).hexdigest(), base64.b85encode(zlib.compress(not_json)).decode()
        )
    missing = dict(documents)
    missing.pop("QUICKSTART.md")
    extra = dict(documents, **{"EXTRA.md": "x"})
    for label, obj in {
        "missing document": missing,
        "extra document": extra,
        "wrong order": reordered,
        "empty document": dict(documents, **{"QUICKSTART.md": "  "}),
        "not an object": ["a"],
    }.items():
        with pytest.raises(help_docs.HelpUnavailable, match="exactly the help documents"):
            help_docs.decode_bundle(*bundle_of(obj))
        del label


def test_a_mutated_bundle_is_rejected_when_frozen(documents, frozen_with):
    schema, digest, payload, flipped = _mutated(documents)
    frozen_with(types.SimpleNamespace(SCHEMA=schema, DIGEST=digest, PAYLOAD=flipped))
    with pytest.raises(help_docs.HelpUnavailable):
        help_docs.topics()


def test_the_error_messages_never_carry_document_text(documents):
    schema, digest, payload, flipped = _mutated(documents)
    with pytest.raises(help_docs.HelpUnavailable) as caught:
        help_docs.decode_bundle(schema, "0" * 64, payload)
    message = str(caught.value)
    assert all(text[:40] not in message for text in documents.values())


def test_encoding_refuses_anything_but_exactly_the_help_documents(documents):
    with pytest.raises(help_docs.HelpUnavailable):
        help_docs.encode_bundle({"QUICKSTART.md": documents["QUICKSTART.md"]})


# --- the reading copy ("Open file") ------------------------------------------


def test_the_reading_copy_is_outside_the_install_read_only_and_identical(documents):
    path = help_docs.reading_copy("QUICKSTART.md")
    try:
        assert path.parent != help_docs.docs_directory()
        assert ROOT not in path.parents
        assert path.read_text(encoding="utf-8") == help_docs.document_text("QUICKSTART.md")
        assert not os.access(path, os.W_OK)
        assert not (path.stat().st_mode & stat.S_IWRITE)
        assert help_docs.reading_copy("QUICKSTART.md") == path  # reused, not rewritten
        with pytest.raises(PermissionError):
            path.write_text("changed", encoding="utf-8")
        # the real help is unaffected by anything done to the copy
        assert help_docs.document_text("QUICKSTART.md") == help_docs.document_text("QUICKSTART.md")
    finally:
        help_docs._remove_copy_directory()


def test_the_reading_copy_refuses_a_name_that_is_not_a_help_document():
    with pytest.raises(help_docs.HelpUnavailable):
        help_docs.reading_copy("../pyproject.toml")


# --- the dialog's Open file button --------------------------------------------


class TestOpenFileButton:
    @pytest.fixture
    def dialog(self, qapp):
        import conftest
        from openchem.ui.dialogs.help_dialog import HelpDialog

        widget = HelpDialog()
        widget.show_topic("docking")
        yield widget
        widget.close()
        conftest.dispose(widget)
        help_docs._remove_copy_directory()

    def test_it_opens_a_copy_and_not_the_document_on_disk(self, dialog, monkeypatch):
        from openchem.ui.dialogs import help_dialog

        opened = []
        monkeypatch.setattr(help_dialog.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
        dialog._open_document_file()
        assert len(opened) == 1
        path = Path(opened[0])
        assert path.name == dialog._current_document
        assert path != help_docs.docs_directory() / dialog._current_document
        assert path.read_text(encoding="utf-8") == help_docs.document_text(dialog._current_document)

    def test_a_system_with_no_markdown_program_is_said_so_with_the_path(self, dialog, monkeypatch):
        from openchem.ui.dialogs import help_dialog

        monkeypatch.setattr(help_dialog.QDesktopServices, "openUrl", lambda url: False)
        dialog._open_document_file()
        assert "no program" in dialog._status.text()
        assert dialog._current_document in dialog._status.text()

    def test_a_failure_to_write_the_copy_is_reported_not_raised(self, dialog, monkeypatch):
        from openchem.ui.dialogs import help_dialog

        def boom(document):
            raise PermissionError("disk full")

        monkeypatch.setattr(help_dialog.help_docs, "reading_copy", boom)
        dialog._open_document_file()
        assert "Could not prepare a copy" in dialog._status.text()

    def test_the_status_line_does_not_send_a_release_reader_to_a_file_that_is_not_there(self, dialog, monkeypatch):
        monkeypatch.setattr(help_docs, "content_source", lambda: "bundle")
        assert "built into this release" in dialog._source_note()
        assert "edit that file" not in dialog._source_note()
        monkeypatch.setattr(help_docs, "content_source", lambda: "files")
        assert "edit that file" in dialog._source_note()

    def test_the_tooltip_no_longer_promises_the_file_on_disk(self):
        from openchem.ui.dialogs.help_dialog import HelpDialog  # noqa: F401
        import openchem.ui.dialogs.help_dialog as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "read-only copy" in source
        assert "as it is on disk" not in source
