"""The second held-out population is evaluation-only, and that is enforced.

Naming round 4 uses the first held-out set (`heldout.json`) as fix targets,
which spends it as evidence of generalisation. `heldout2.json` was drawn and
frozen before any round-4 diagnosis to replace it, and it is only worth
anything if nothing during the round looks at it: a row read while debugging
another stage is a row that ends up fixed, and then the "fresh" number is the
regression number again.

"Please don't look" is not a control. These tests make it one:

* the stage tool refuses to load it outside `--final-evaluation`, before the
  file is even opened;
* no other tracked script names the file, so no new diagnostic can quietly
  start reading it.

Nothing here reads `heldout2.json`'s rows.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_stage_artifact as stage  # noqa: E402

FROZEN_FILE = "heldout2.json"

#: The only tracked files allowed to name the frozen file: the script that
#: drew it, the tool that locks it, and this test.
ALLOWED = {
    "benchmarks/naming/build_heldout.py",
    "tools/naming_stage_artifact.py",
    "tests/test_naming_heldout_lock.py",
}


def test_a_stage_run_does_not_include_the_frozen_population():
    assert "heldout_v2" not in stage.active_populations()


def test_loading_the_frozen_population_is_refused_before_the_file_is_opened(monkeypatch):
    opened: list[Path] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    with pytest.raises(stage.FrozenPopulation):
        stage.load_population("heldout_v2")
    assert not [p for p in opened if p.name == FROZEN_FILE]


def test_the_final_evaluation_is_the_one_door_in():
    assert "heldout_v2" in stage.active_populations(final_evaluation=True)


def test_no_other_tracked_file_names_the_frozen_population():
    """The structural guard. Breaking it: add `heldout2.json` to any script.

    Mutation-tested 2026-09-18: dropping `build_heldout.py` from ALLOWED
    fails this test.
    """
    listed = subprocess.run(
        ["git", "grep", "-l", FROZEN_FILE, "--", "*.py"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    assert set(listed) <= ALLOWED, set(listed) - ALLOWED


def test_the_frozen_file_still_matches_its_recorded_hash():
    """Integrity without inspection: bytes are hashed, never parsed.

    Over LF text, because that is what the freeze hashed and what git stores
    (`i/lf`); the Windows working copy is CRLF under autocrlf, and hashing it
    raw reads as tampering when it is only a checkout setting.
    """
    import hashlib

    meta = json.loads(
        (ROOT / "benchmarks/naming/heldout2.meta.json").read_text(encoding="utf-8")
    )
    raw = (ROOT / "benchmarks/naming" / FROZEN_FILE).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == meta["heldout_sha256"]


def test_the_freeze_record_says_what_the_policy_is():
    """Reads the META file only -- counts, rule and hash, never rows."""
    meta = json.loads(
        (ROOT / "benchmarks/naming/heldout2.meta.json").read_text(encoding="utf-8")
    )
    assert meta["engine_consulted"] is False
    assert meta["rows"] == 40
    assert "evaluation only" in meta["inspection_policy"]
