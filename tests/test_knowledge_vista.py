"""The Knowledge Vista tab and the service behind it: optional, defensive, and never a reason for anything else to fail.

A mock `kv` (`tests/fake_kv.py`, wrapped so it can be executed as a file) stands in for the real program, so CI needs neither it nor a
library. Each way a configured program can disappoint is one test.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

import conftest
from openchem.app.settings import Settings
from openchem.events.base import EventBus
from openchem.services import knowledge_vista as kv
from openchem.services import tool_download_service as tools
from openchem.ui.dialogs.external_tool_catalog import knowledge_vista as descriptor
from openchem.ui.dialogs.external_tools_pages import ExternalToolsPages

FAKE = Path(__file__).with_name("fake_kv.py")


@pytest.fixture
def program(tmp_path, monkeypatch):
    """A file named `kv` that runs the mock, plus a log of what it was asked."""
    log = tmp_path / "kv.log"
    monkeypatch.setenv("FAKE_KV_LOG", str(log))
    monkeypatch.delenv("FAKE_KV_MODE", raising=False)
    monkeypatch.delenv("FAKE_KV_PROTOCOL", raising=False)
    if os.name == "nt":
        path = tmp_path / "kv.cmd"
        path.write_text(f'@"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
    else:
        path = tmp_path / "kv"
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def asked(tmp_path) -> list[list[str]]:
    log = tmp_path / "kv.log"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


# --- the service -------------------------------------------------------------------------------------------------


def test_a_working_program_is_verified_by_asking_it_what_it_is(program, tmp_path):
    message = kv.verify(str(program))
    assert message == "Works: Knowledge Vista 0.0.1 (integration protocol 1, 2 read-only commands)."
    assert asked(tmp_path) == [["--json", "capabilities"]]  # one question, nothing else, no path or text sent


@pytest.mark.parametrize(("mode", "fragment"), [
    ("other_app", "is not Knowledge Vista"), ("malformed", "without a JSON answer"), ("notenvelope", "Knowledge Vista's format"),
    ("crash", "exited 3 without a JSON answer"), ("nocapabilities", "is not Knowledge Vista"),
])
def test_every_way_the_program_can_be_wrong_is_one_readable_failure(program, monkeypatch, mode, fragment):
    monkeypatch.setenv("FAKE_KV_MODE", mode)
    with pytest.raises(kv.KnowledgeVistaUnavailable) as caught:
        kv.verify(str(program))
    assert fragment in str(caught.value)


def test_a_protocol_this_build_was_not_taught_is_said_plainly(program, monkeypatch):
    monkeypatch.setenv("FAKE_KV_PROTOCOL", "4")
    with pytest.raises(kv.KnowledgeVistaUnavailable, match="protocol 4; this OpenChem Studio understands 1"):
        kv.verify(str(program))


def test_a_program_that_does_not_answer_in_time_is_unavailable_not_a_frozen_window(program, monkeypatch):
    monkeypatch.setenv("FAKE_KV_MODE", "hang")
    with pytest.raises(kv.KnowledgeVistaUnavailable, match="did not answer within 1 s"):
        kv.check_protocol(str(program), timeout=1.0)


def test_nothing_configured_and_nothing_on_the_path_is_the_normal_case_and_says_how_to_fix_it(monkeypatch):
    monkeypatch.setattr(kv.shutil, "which", lambda name: None)
    assert kv.executable("") is None and kv.executable(None) is None
    with pytest.raises(kv.KnowledgeVistaUnavailable, match="Settings > External Tools > Knowledge Vista"):
        kv.verify("")


def test_a_configured_path_that_is_not_a_file_is_not_silently_replaced_by_the_path_search(tmp_path, monkeypatch):
    monkeypatch.setattr(kv.shutil, "which", lambda name: "/somewhere/else/kv")
    assert kv.executable(str(tmp_path / "gone")) is None  # the user said which one: do not run a different program
    assert kv.executable("") == ["/somewhere/else/kv"]


def test_the_status_line_reads_the_path_and_runs_nothing(program, tmp_path, monkeypatch):
    monkeypatch.setattr(kv.shutil, "which", lambda name: None)
    assert kv.describe_status("") == "Not configured (optional: OpenChem Studio works without it)"
    assert "no file at" in kv.describe_status(str(tmp_path / "absent"))
    assert kv.describe_status(str(program)).startswith("Configured: ")
    monkeypatch.setattr(kv.shutil, "which", lambda name: "/usr/bin/kv")
    assert kv.describe_status("") == "Found on PATH: /usr/bin/kv"
    assert asked(tmp_path) == []  # a status line is read on every visit to the tab: it must not start a program


def test_locating_accepts_only_what_answers_as_knowledge_vista(program, monkeypatch, tmp_path):
    assert kv.responds_as_knowledge_vista(program) is True
    monkeypatch.setenv("FAKE_KV_MODE", "other_app")
    assert kv.responds_as_knowledge_vista(program) is False
    assert kv.responds_as_knowledge_vista(tmp_path / "does-not-exist") is False
    found = tools.locate_executable(("kv",), validate=kv.responds_as_knowledge_vista, search_roots=(program.parent,))
    assert found is None  # the impostor is skipped, not returned
    monkeypatch.setenv("FAKE_KV_MODE", "ok")


# --- the tab -----------------------------------------------------------------------------------------------------


@pytest.fixture
def dialog(qapp):
    widget = ExternalToolsPages(Settings(EventBus()))
    yield widget
    conftest.dispose(widget)


def test_the_descriptor_says_what_this_tool_is_and_is_not():
    d = descriptor()
    assert d.key == "knowledge_vista" and d.title == "Knowledge Vista" and d.setting_key == "knowledgevista/executable_path"
    assert d.obtainable is False and d.removable is False  # the app does not install it, so it neither fetches nor deletes it
    assert [url for _label, url in d.vendor_links] == ["https://github.com/xaerogonzo/knowledgevista"]
    assert d.describe_test is kv.verify and d.test_errors is kv.KnowledgeVistaUnavailable


def test_the_tab_is_registered_after_the_tools_something_needs_and_before_storage(dialog):
    labels = [dialog._tabs.tabText(i) for i in range(dialog._tabs.count())]
    assert labels.index("Knowledge Vista") == labels.index("NMR Database") + 1 == labels.index("Storage") - 1
    assert "knowledge_vista" in [tab.descriptor.key for tab in dialog._tool_tabs]


def test_the_tab_shows_a_test_and_a_locate_but_no_set_up_and_no_remove(dialog):
    tab = dialog._tab_for("knowledge_vista")
    assert not tab.setup_button.isVisibleTo(tab) and not tab.remove_button.isVisibleTo(tab)
    assert tab.locate_button is not None and tab.test_button is not None and tab.status_label.text()
    assert dialog._knowledge_vista_path_edit is tab.path_row.edit and dialog._knowledge_vista_status_label is tab.status_label


def test_the_tab_says_nothing_depends_on_it(dialog):
    from PySide6.QtWidgets import QLabel

    text = " ".join(label.text() for label in dialog._tab_for("knowledge_vista").findChildren(QLabel))
    assert "nothing in OpenChem Studio depends on it" in text
