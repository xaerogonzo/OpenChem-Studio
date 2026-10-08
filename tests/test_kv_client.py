"""`tools/kv_client.py`: every way Knowledge Vista can fail is "unavailable", and what it is asked is only a hash.

The mock KV (`tests/fake_kv.py`) stands in for the real program, so CI never needs a library. Each test names one failure mode from the
list the integration plan required: success, ambiguous, missing, malformed JSON, an unsupported protocol version, a timeout, an
executable that is not there, and a non-zero exit.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("fake_kv.py")
SHA = "ab" * 32


@pytest.fixture
def client(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("kv_client_under_test", ROOT / "tools" / "kv_client.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["kv_client_under_test"] = module
    spec.loader.exec_module(module)
    monkeypatch.setenv("OPENCHEM_KV", str(FAKE))
    monkeypatch.delenv("OPENCHEM_KV_CATALOG", raising=False)
    monkeypatch.setenv("FAKE_KV_LOG", str(tmp_path / "kv.log"))
    monkeypatch.setenv("FAKE_KV_PATH", str(tmp_path / "paper.pdf"))
    module.forget()
    yield module
    module.forget()


def asked(tmp_path) -> list[list[str]]:
    log = tmp_path / "kv.log"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def test_a_found_artifact_reports_where_it_is_and_what_kv_called_it(client, tmp_path):
    located = client.locate_sha256(SHA)
    assert located.artifact_id == SHA and located.status == "available" and located.document_id == "d" * 32
    assert located.paths == (str(tmp_path / "paper.pdf"),) and located.reachable is True and located.uri == "knowledgevista://document/" + "d" * 32


def test_only_the_hash_is_sent_and_always_as_json(client, tmp_path):
    client.locate_sha256(SHA)
    calls = asked(tmp_path)
    assert [c for c in calls if "locate" in c] == [["--json", "locate", SHA]] and [c for c in calls if "capabilities" in c] == [["--json", "capabilities"]]


def test_the_catalog_setting_is_passed_through(client, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCHEM_KV_CATALOG", str(tmp_path / "other.sqlite"))
    client.forget()
    client.locate_sha256(SHA)
    assert all(["--catalog", str(tmp_path / "other.sqlite")] == c[1:3] for c in asked(tmp_path))


def test_an_artifact_kv_has_never_seen_is_none_not_an_error(client, monkeypatch):
    monkeypatch.setenv("FAKE_KV_LOCATE", "unknown")
    assert client.locate_sha256(SHA) is None


def test_a_known_artifact_with_no_reachable_copy_has_no_paths(client, monkeypatch):
    for mode in ("missing", "root_offline"):
        monkeypatch.setenv("FAKE_KV_LOCATE", mode)
        located = client.locate_sha256(SHA)
        assert located is not None and located.paths == () and located.reachable is False and located.status in ("missing", "root_offline")


def test_several_paths_are_all_returned_for_the_caller_to_verify(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_KV_PATH", f"{tmp_path / 'a.pdf'}|{tmp_path / 'b.pdf'}")
    assert [Path(p).name for p in client.locate_sha256(SHA).paths] == ["a.pdf", "b.pdf"]


@pytest.mark.parametrize("mode", ["ambiguous", "malformed", "notenvelope", "wrongbytes", "crash"])
def test_every_way_of_answering_badly_is_unavailable(client, monkeypatch, mode):
    monkeypatch.setenv("FAKE_KV_LOCATE", mode)
    with pytest.raises(client.KvUnavailable) as caught:
        client.locate_sha256(SHA)
    assert str(caught.value)


def test_an_unsupported_protocol_version_is_unavailable_and_says_which(client, monkeypatch):
    monkeypatch.setenv("FAKE_KV_PROTOCOL", "7")
    with pytest.raises(client.KvUnavailable, match="protocol 7"):
        client.locate_sha256(SHA)


def test_a_capabilities_call_that_fails_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("FAKE_KV_LOCATE", "nocapabilities")
    with pytest.raises(client.KvUnavailable):
        client.locate_sha256(SHA)


def test_a_timeout_is_unavailable(client, monkeypatch):
    monkeypatch.setenv("FAKE_KV_LOCATE", "hang")
    with pytest.raises(client.KvUnavailable, match="did not answer"):
        client.locate_sha256(SHA, timeout=1.0)


def test_a_missing_executable_is_unavailable(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCHEM_KV", str(tmp_path / "no-such-kv"))
    assert client.command() is None
    with pytest.raises(client.KvUnavailable, match="not found"):
        client.locate_sha256(SHA)


def test_with_no_setting_and_no_kv_on_the_path_there_is_nothing_to_run(client, monkeypatch):
    monkeypatch.delenv("OPENCHEM_KV")
    monkeypatch.setattr(client.shutil, "which", lambda name: None)
    assert client.command() is None and client.configured() is False
    monkeypatch.setattr(client.shutil, "which", lambda name: "/usr/bin/kv")
    assert client.command() == ["/usr/bin/kv"]


def test_the_protocol_is_checked_once_per_command_not_once_per_question(client, tmp_path):
    client.locate_sha256(SHA)
    client.locate_sha256(SHA)
    assert len([c for c in asked(tmp_path) if "capabilities" in c]) == 1
    client.forget()
    client.locate_sha256(SHA)
    assert len([c for c in asked(tmp_path) if "capabilities" in c]) == 2


def test_a_hash_that_is_not_a_full_lowercase_sha256_is_refused_before_anything_runs(client, tmp_path):
    for bad in ("", "abc", SHA.upper(), SHA[:-1], "z" * 64):
        with pytest.raises(ValueError):
            client.locate_sha256(bad)
    assert asked(tmp_path) == []


def test_only_active_online_paths_not_known_to_be_absent_are_offered(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_KV_LOCATE", "missing")  # on_disk False
    assert client.locate_sha256(SHA).paths == ()
    monkeypatch.setenv("FAKE_KV_LOCATE", "found")
    assert len(client.locate_sha256(SHA).paths) == 1


def test_a_python_script_is_run_with_this_interpreter(client, monkeypatch):
    monkeypatch.setenv("OPENCHEM_KV", str(FAKE))
    assert client.command() == [sys.executable, str(FAKE)]
