"""`tools/run_app_gate.sh` plans its chunks correctly and refuses to run against the wrong tree.

The gate itself takes about an hour and is not run here. What IS testable in a second, and was wrong once, is the part that decides
WHAT it runs: a chunk boundary off by one silently drops or repeats a test file, and an interpreter that imports the main checkout's
`openchem` instead of the worktree's tests the wrong code and reports green. Both are plain arithmetic and a path check.

Needs a POSIX `bash`; on Windows that is Git Bash, never the WSL launcher in System32 (which cannot read these paths).
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_app_gate.sh"


def _bash() -> str | None:
    for candidate in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if candidate and Path(candidate).exists() and "system32" not in str(candidate).lower():
            return candidate
    return None


BASH = _bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="needs a POSIX bash (Git Bash on Windows)")


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, str(SCRIPT), *argv], capture_output=True, text=True, cwd=ROOT)


def _shard_size(group: int) -> int:
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "suite_shards.py"), "--splits=2", f"--group={group}"],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    return len(out.split())


@pytest.mark.parametrize("chunk", [25, 7])
def test_the_dry_run_plans_chunks_that_cover_every_shard_file_exactly_once(chunk):
    """The plan's file counts, per chunk, must sum to the shard's own file count (counted independently from the splitter),
    no chunk may exceed the chunk size, and the chunk count must be the ceiling. An off-by-one in the boundary changes one of
    the three. (Mutation: `% CHUNK` -> `% (CHUNK + 1)` in the dry run fails the size and the count.)"""
    result = _run("--tree", ".", "--shards", "1,2", "--chunk", str(chunk), "--dry-run")
    assert result.returncode == 0, result.stderr
    for group in (1, 2):
        header = re.search(rf"shard {group}: (\d+) files, chunks of {chunk} -> (\d+) chunks", result.stdout)
        assert header, result.stdout
        files, chunks = int(header[1]), int(header[2])
        sizes = [int(m[1]) for m in re.finditer(rf"chunk s{group}c\d+: (\d+) files", result.stdout)]
        assert files == _shard_size(group), "the plan counted a different number of files than the splitter"
        assert sum(sizes) == files, (sum(sizes), files)
        assert max(sizes) <= chunk, sizes
        assert len(sizes) == chunks == math.ceil(files / chunk), (len(sizes), chunks)


def test_a_sha_and_a_tree_are_alternatives():
    result = _run("--sha", "HEAD", "--tree", ".", "--dry-run")
    assert result.returncode == 2
    assert "alternatives" in result.stderr


def test_an_unknown_argument_is_refused_not_ignored():
    result = _run("--tree", ".", "--no-such-flag", "--dry-run")
    assert result.returncode == 2
    assert "unknown argument" in result.stderr


@pytest.mark.skipif(shutil.which("java") is None, reason="the preflight needs JAVA_HOME and a bare java, as the gate does")
def test_the_preflight_refuses_a_tree_whose_openchem_is_not_the_one_imported(tmp_path):
    """A detached worktree has no venv, so the main checkout's interpreter runs it with PYTHONPATH at the worktree's `src`. A
    wrong tree (here: a directory that has no `src` at all) must be refused, not tested against the wrong code."""
    import os

    if not os.environ.get("JAVA_HOME"):
        pytest.skip("JAVA_HOME is not set")
    result = _run("--tree", str(tmp_path), "--out", str(tmp_path / "out"), "--preflight")
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "somewhere other than" in result.stderr


def test_the_script_has_no_carriage_returns():
    """Under `core.autocrlf=true` a shell script would be checked out CRLF, and `set -o pipefail` followed by a carriage return is
    an invalid option name: the script still runs, with the option that makes a pipeline's failure visible silently off. The
    `.gitattributes` rule `*.sh text eol=lf` is the fix; this is the check that a working copy honours it."""
    assert b"\r" not in SCRIPT.read_bytes()
    attributes = subprocess.run(
        ["git", "check-attr", "eol", "tools/run_app_gate.sh"], capture_output=True, text=True, cwd=ROOT
    ).stdout
    assert attributes.strip().endswith("lf"), attributes
