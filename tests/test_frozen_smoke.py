"""The frozen smoke test's judge and launcher, and the driver steps it relies on.

The judge is what stands between a release that cannot start and a published
zip, so what is held here is that it never passes by default: every way a run
can be wrong is its own failing case, and the one passing case is the only
combination of everything being right.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load("frozen_smoke")


@pytest.fixture
def script(tmp_path):
    path = tmp_path / "script.json"
    path.write_text("[]", encoding="utf-8")
    return path


def _report(script, **overrides):
    base = {
        "verdict": "PASS",
        "exit_code": 0,
        "run": {"started": datetime.now(timezone.utc).isoformat(), "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest()},
        "steps": {"in_script": 9, "run": 9},
        "assertions": [
            {"step": "help_report", "tag": "", "ok": True, "detail": "ok"},
            {"step": "install_report", "tag": "", "ok": True, "detail": "ok"},
            {"step": "expect_clean", "tag": "", "ok": True, "detail": "ok"},
        ],
        "ledger": {"errors": [], "warnings": [], "driver_failures": [], "dropped": 0},
    }
    base.update(overrides)
    return base


def _judge(tmp_path, script, report=None, *, exit_code=0, timed_out=False, launched_at=None, raw=None):
    path = tmp_path / "report.json"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    elif report is not None:
        path.write_text(json.dumps(report), encoding="utf-8")
    launched_at = launched_at or (datetime.now(timezone.utc) - timedelta(seconds=30))
    return smoke.judge(path, exit_code=exit_code, timed_out=timed_out, launched_at=launched_at, script=script)


def test_the_one_passing_case(tmp_path, script):
    result = _judge(tmp_path, script, _report(script))
    assert result.ok and result.failures == []


def test_a_missing_report_fails_even_with_exit_zero(tmp_path, script):
    result = _judge(tmp_path, script, None)
    assert not result.ok and "no report" in result.failures[0]


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null"])
def test_a_report_that_is_not_an_object_fails(tmp_path, script, raw):
    assert not _judge(tmp_path, script, raw=raw).ok


def test_a_pass_report_with_a_nonzero_exit_status_fails(tmp_path, script):
    assert not _judge(tmp_path, script, _report(script), exit_code=1).ok


def test_a_fail_report_with_exit_zero_fails(tmp_path, script):
    assert not _judge(tmp_path, script, _report(script, verdict="FAIL", exit_code=1)).ok


def test_a_timeout_fails_even_if_a_report_appeared(tmp_path, script):
    result = _judge(tmp_path, script, _report(script), exit_code=None, timed_out=True)
    assert not result.ok and any("in time" in f for f in result.failures)


def test_a_stale_report_is_not_this_runs(tmp_path, script):
    """A report left in a reused folder: its run started before this launch."""
    stale = _report(script)
    stale["run"]["started"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    result = _judge(tmp_path, script, stale, launched_at=datetime.now(timezone.utc))
    assert not result.ok and any("stale" in f for f in result.failures)


def test_a_report_that_does_not_say_when_it_started_fails(tmp_path, script):
    report = _report(script)
    del report["run"]["started"]
    assert not _judge(tmp_path, script, report).ok


def test_a_report_for_a_different_script_fails(tmp_path, script):
    report = _report(script)
    script.write_text('[{"do": "quit"}]', encoding="utf-8")  # the script changed after the report
    assert not _judge(tmp_path, script, report).ok


def test_a_script_that_stopped_early_fails(tmp_path, script):
    assert not _judge(tmp_path, script, _report(script, steps={"in_script": 9, "run": 4})).ok
    assert not _judge(tmp_path, script, _report(script, steps={})).ok


@pytest.mark.parametrize("missing", smoke.REQUIRED_ASSERTIONS)
def test_every_required_assertion_must_have_run(tmp_path, script, missing):
    """A script that quietly lost a step asserts less than it used to."""
    report = _report(script)
    report["assertions"] = [a for a in report["assertions"] if a["step"] != missing]
    result = _judge(tmp_path, script, report)
    assert not result.ok and any(missing in f and "never ran" in f for f in result.failures)


def test_a_failed_assertion_fails_the_run_and_says_which(tmp_path, script):
    report = _report(script)
    report["assertions"][0] = {"step": "help_report", "tag": "", "ok": False, "detail": "help source is 'files'"}
    result = _judge(tmp_path, script, report)
    assert not result.ok and any("help source is 'files'" in f for f in result.failures)


def test_no_assertions_at_all_fails(tmp_path, script):
    assert not _judge(tmp_path, script, _report(script, assertions=[])).ok


def test_a_dropped_ledger_cannot_vouch_for_the_run(tmp_path, script):
    ledger = {"errors": [], "warnings": [], "driver_failures": [], "dropped": 3}
    assert not _judge(tmp_path, script, _report(script, ledger=ledger)).ok
    assert not _judge(tmp_path, script, _report(script, ledger={})).ok


def test_driver_failures_fail_the_run(tmp_path, script):
    ledger = {"errors": [], "warnings": [], "driver_failures": ["step 3 raised"], "dropped": 0}
    assert not _judge(tmp_path, script, _report(script, ledger=ledger)).ok


# --- the launcher, against a stand-in for the exe -----------------------------


def _fake_app(tmp_path, body: str) -> list[str]:
    app = tmp_path / "fake_app.py"
    app.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(app)]


_WRITES_A_PASSING_REPORT = """
import hashlib, json, os, pathlib, sys, datetime
script = pathlib.Path(os.environ["OPENCHEM_DRIVE"])
report = {
    "verdict": "PASS", "exit_code": 0,
    "run": {"started": datetime.datetime.now(datetime.timezone.utc).isoformat(), "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest()},
    "steps": {"in_script": 1, "run": 1},
    "assertions": [{"step": s, "tag": "", "ok": True, "detail": ""} for s in ("help_report", "install_report", "expect_clean")],
    "ledger": {"errors": [], "warnings": [], "driver_failures": [], "dropped": 0},
}
pathlib.Path(os.environ["OPENCHEM_DRIVE_REPORT"]).write_text(json.dumps(report))
assert os.environ["OPENCHEM_DATA_ROOT"] and os.path.isdir(os.environ["OPENCHEM_DATA_ROOT"])
"""


def test_the_launcher_passes_a_run_that_reports_a_pass(tmp_path, script):
    judgement, work = smoke.run_smoke(_fake_app(tmp_path, _WRITES_A_PASSING_REPORT), script, timeout=60, workdir=tmp_path)
    assert judgement.ok, judgement.failures
    assert work.parent == tmp_path  # a fresh folder, so a stale report cannot satisfy it


def test_the_launcher_fails_a_run_that_exits_zero_without_a_report(tmp_path, script):
    judgement, _ = smoke.run_smoke(_fake_app(tmp_path, "pass\n"), script, timeout=60, workdir=tmp_path)
    assert not judgement.ok and any("no report" in f for f in judgement.failures)


def test_the_launcher_times_out_and_kills_only_its_own_process(tmp_path, script):
    command = _fake_app(tmp_path, "import time\ntime.sleep(120)\n")
    judgement, _ = smoke.run_smoke(command, script, timeout=2, workdir=tmp_path)
    assert not judgement.ok and any("in time" in f for f in judgement.failures)


def test_a_failed_run_prints_what_the_app_said(tmp_path, script, capsys):
    command = _fake_app(tmp_path, "import sys\nprint('boom from the app', file=sys.stderr)\nsys.exit(3)\n")
    judgement, _ = smoke.run_smoke(command, script, timeout=60, workdir=tmp_path)
    assert not judgement.ok
    assert "boom from the app" in capsys.readouterr().out


def test_a_missing_executable_is_a_usage_error(tmp_path):
    assert smoke.main(["--exe", str(tmp_path / "nope.exe")]) == 2


# --- the driver steps ----------------------------------------------------------

from openchem.app import drive_release  # noqa: E402


def test_the_help_state_reads_the_running_modules(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    state = drive_release.help_state("Vina")
    assert state["source"] == "files" and state["documents"] == 4
    assert state["topics"] >= 15 and state["unresolved_keys"] == [] and state["search_hits"] >= 1


def test_every_panel_help_key_is_checked():
    keys = drive_release.panel_help_keys()
    assert len(keys) >= 10 and "docking" in keys


def test_a_broken_help_is_reported_not_raised(monkeypatch):
    from openchem import help as help_docs

    def boom():
        raise help_docs.HelpUnavailable("bundle missing")

    monkeypatch.setattr(help_docs, "topics", boom)
    state = drive_release.help_state()
    assert "bundle missing" in state["error"]
    assert drive_release.evaluate_help({"source": "files"}, state)


def test_help_expectations_fail_closed():
    good = {"source": "bundle", "documents": 4, "topics": 20, "unresolved_keys": [], "search_query": "Vina", "search_hits": 3}
    expect = {"source": "bundle", "documents": 4, "topics_at_least": 15, "panel_keys_resolve": True, "search": {"query": "Vina", "hits_at_least": 1}}
    assert drive_release.evaluate_help(expect, good) == []
    assert drive_release.evaluate_help({"source": "bundle", "typo_key": 1}, good)  # an unknown key is a failure
    assert drive_release.evaluate_help(expect, dict(good, source="files"))
    assert drive_release.evaluate_help(expect, dict(good, documents=3))
    assert drive_release.evaluate_help(expect, dict(good, topics=2))
    assert drive_release.evaluate_help(expect, dict(good, unresolved_keys=["docking"]))
    assert drive_release.evaluate_help(expect, dict(good, search_hits=0))
    without = {k: v for k, v in good.items() if k != "unresolved_keys"}
    assert drive_release.evaluate_help(expect, without)  # an unreadable field is a failure


def test_install_expectations_fail_closed():
    verified = {"status": "verified", "checked": 77, "problems": 0, "summary": "verified"}
    assert drive_release.evaluate_install({"status": "verified", "checked_at_least": 50}, verified) == []
    assert drive_release.evaluate_install({"status": "verified"}, dict(verified, status="modified"))
    assert drive_release.evaluate_install({"status": "verified"}, dict(verified, status="check_failed"))
    assert drive_release.evaluate_install({"status": "verified", "checked_at_least": 50}, dict(verified, checked=5))
    assert drive_release.evaluate_install({"status": "verified"}, {"status": "checking"})  # never finished
    assert drive_release.evaluate_install({"status": "verified"}, {"error": "x"})
    assert drive_release.evaluate_install({"status": "verified", "typo": 1}, verified)
    assert drive_release.install_pending({"status": "checking"}) and not drive_release.install_pending(verified)


def test_the_smoke_script_asserts_what_the_judge_requires():
    steps = json.loads((ROOT / "benchmarks" / "visual" / "frozen_smoke.json").read_text(encoding="utf-8"))
    actions = [s["do"] for s in steps]
    for required in smoke.REQUIRED_ASSERTIONS:
        assert required in actions
    help_step = next(s for s in steps if s["do"] == "help_report")
    assert help_step["expect"]["source"] == "bundle" and help_step["expect"]["panel_keys_resolve"] is True
    assert next(s for s in steps if s["do"] == "install_report")["expect"]["status"] == "verified"
    assert actions[-1] == "quit"


def test_the_driver_has_a_handler_for_every_step_the_smoke_script_uses():
    from openchem.app.debug_drive import _Driver as cls

    steps = json.loads((ROOT / "benchmarks" / "visual" / "frozen_smoke.json").read_text(encoding="utf-8"))
    missing = [s["do"] for s in steps if not hasattr(cls, f"_do_{s['do']}")]
    assert not missing, f"the smoke script uses steps the driver does not have: {missing}"


# --- how the build wires it ----------------------------------------------------


def test_the_build_smoke_tests_and_the_release_refuses_a_dirty_tree():
    build = (ROOT / "build.ps1").read_text(encoding="utf-8")
    assert "frozen_smoke.py" in build and "throw \"The built app failed its smoke test" in build
    assert "status --porcelain" in build
    assert "$dirty -and $Release" in build  # a release is never made from a modified tree
    assert "make_release_zip.py" in build
    assert 'dirty = $(if ($dirty)' in build  # the stamp records it


def test_about_says_when_a_build_came_from_a_modified_tree(monkeypatch):
    from openchem import build_info

    monkeypatch.setattr(build_info, "_stamped", lambda name, default: {"commit": "cafe123", "dirty": "True"}.get(name, default))
    assert build_info._commit() == ("cafe123", "baked at build time, MODIFIED TREE")
    monkeypatch.setattr(build_info, "_stamped", lambda name, default: {"commit": "cafe123", "dirty": "False"}.get(name, default))
    assert build_info._commit() == ("cafe123", "baked at build time")
