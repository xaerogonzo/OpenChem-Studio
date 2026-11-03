"""The freeze of the restart-v3 preregistration (`benchmarks/restart_v3/PREREGISTRATION.md` section 11, `freeze.py`, `freeze.json`).

A failure here means a frozen file changed. That is allowed only as an AMENDMENT: an appended `## Amendment N` section, the change, and `python benchmarks/restart_v3/freeze.py write --amend "what changed"` in the same commit.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).parent.parent / "benchmarks" / "restart_v3"
_spec = importlib.util.spec_from_file_location("restart_v3_freeze_under_test", _BENCH / "freeze.py")
fz = importlib.util.module_from_spec(_spec)
sys.modules["restart_v3_freeze_under_test"] = fz
_spec.loader.exec_module(fz)
FROZEN = json.loads((_BENCH / "freeze.json").read_text(encoding="utf-8"))


def test_nothing_that_was_frozen_has_changed_except_by_an_amendment():
    assert fz.problems(FROZEN) == [], "a frozen file changed: write an Amendment (see freeze.py)"


def test_the_preregistration_says_it_is_frozen_and_names_the_date():
    text = (_BENCH / "PREREGISTRATION.md").read_text(encoding="utf-8")
    assert "**Status: FROZEN 2026-10-28" in text and FROZEN["frozen"] == "2026-10-28"
    assert "\n## 11. The freeze (2026-10-28)" in text.replace("\r\n", "\n")


def test_every_file_that_decides_an_arm_is_hashed():
    listed = set(FROZEN["files"])
    for rel in ("benchmarks/restart_v3/restart_v3_core.py", "benchmarks/restart_v3/run_restart_v3.py", "benchmarks/restart_v3/references.json", "benchmarks/restart_v3/thermal_step.py",
                "benchmarks/bde/judge.py", "benchmarks/bde/run_bde.py", "benchmarks/restart_v2/run_restart.py", "benchmarks/bde_heldout/candidates_halogen.json", "benchmarks/restart_v3/freeze.py"):
        assert rel in listed, rel


def test_the_check_notices_each_kind_of_change(tmp_path, monkeypatch):
    """The guard is worth something only if it fails when it should: a changed file, a changed frozen sentence, an appended amendment that freeze.json does not list, and a hashed file that is gone."""
    root = tmp_path / "repo"
    (root / "benchmarks" / "restart_v3").mkdir(parents=True)
    files = ["a.py", "b.json"]
    for name in files:
        (root / name).write_text("one\r\n", encoding="utf-8", newline="")
    prereg = root / "benchmarks" / "restart_v3" / "PREREGISTRATION.md"
    prereg.write_text("# frozen text\n", encoding="utf-8", newline="")
    monkeypatch.setattr(fz, "REPO", root)
    monkeypatch.setattr(fz, "FILES", files)
    frozen = {"files": {n: fz.sha256(fz.normalised(root / n)) for n in files}, "preregistration": {"bytes": len(fz.normalised(prereg)), "sha256": fz.sha256(fz.normalised(prereg))}, "amendments": []}
    assert fz.problems(frozen) == []
    (root / "a.py").write_text("one\n", encoding="utf-8", newline="")                            # CRLF to LF: the same file as far as the freeze is concerned
    assert fz.problems(frozen) == []
    (root / "a.py").write_text("two\n", encoding="utf-8", newline="")
    assert fz.problems(frozen) == ["a.py differs from the freeze"]
    (root / "a.py").write_text("one\n", encoding="utf-8", newline="")
    prereg.write_text("# frozen text\n\n## Amendment 1\n", encoding="utf-8", newline="")          # appended, but freeze.json does not list it
    assert "1 Amendment section(s) and freeze.json lists 0" in fz.problems(frozen)[0]
    frozen["amendments"] = [{"date": "x", "what": "y"}]
    assert fz.problems(frozen) == []
    prereg.write_text("# frozen texT\n\n## Amendment 1\n", encoding="utf-8", newline="")          # the frozen sentence itself edited
    assert "no longer the start of the file" in fz.problems(frozen)[0]
    (root / "b.json").unlink()
    assert any("b.json is missing" in p for p in fz.problems(frozen))
