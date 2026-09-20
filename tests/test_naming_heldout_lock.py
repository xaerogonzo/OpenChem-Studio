"""The current held-out population is evaluation-only, and that is enforced.

Each naming round spends the previous fresh set as fix targets, which spends
it as evidence of generalisation: round 4 spent `heldout.json`, round 5
spends the v2 draw. The v3 draw (`heldout3.json`) was drawn and frozen before
any round-5 diagnosis to replace it, and it is only worth
anything if nothing during the round looks at it: a row read while debugging
another stage is a row that ends up fixed, and then the "fresh" number is the
regression number again.

"Please don't look" is not a control. These tests make it one:

* the stage tool refuses to load it outside `--final-evaluation`, before the
  file is even opened;
* no other tracked script names the file, so no new diagnostic can quietly
  start reading it.

Nothing here reads `heldout3.json`'s rows.
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

FROZEN_FILE = "heldout3.json"
FROZEN_KEY = "heldout_v3"
FROZEN_META = "benchmarks/naming/heldout3.meta.json"

#: The only tracked files allowed to name the frozen file: the script that
#: drew it, the tool that locks it, and this test.
ALLOWED = {
    "benchmarks/naming/build_heldout.py",
    "tools/naming_stage_artifact.py",
    "tests/test_naming_heldout_lock.py",
}


def test_a_stage_run_does_not_include_the_frozen_population():
    assert FROZEN_KEY not in stage.active_populations()


def test_loading_the_frozen_population_is_refused_before_the_file_is_opened(monkeypatch):
    opened: list[Path] = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    with pytest.raises(stage.FrozenPopulation):
        stage.load_population(FROZEN_KEY)
    assert not [p for p in opened if p.name == FROZEN_FILE]


def test_the_final_evaluation_is_the_one_door_in():
    assert FROZEN_KEY in stage.active_populations(final_evaluation=True)


def test_the_previous_fresh_population_is_a_tuning_population_now():
    """Round 5 spends v2 (N1 adjudicates its differing rows), so a stage run
    loads it, and its meta file says it is used -- the same record v1 got
    when round 4 spent it."""
    assert "heldout_v2" in stage.active_populations()
    meta = json.loads(
        (ROOT / "benchmarks/naming/heldout2.meta.json").read_text(encoding="utf-8")
    )
    assert meta["status"] == "USED_FOR_TUNING"


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
        (ROOT / FROZEN_META).read_text(encoding="utf-8")
    )
    raw = (ROOT / "benchmarks/naming" / FROZEN_FILE).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == meta["heldout_sha256"]


def test_the_freeze_record_says_what_the_policy_is():
    """Reads the META file only -- counts, rule and hash, never rows."""
    meta = json.loads((ROOT / FROZEN_META).read_text(encoding="utf-8"))
    assert meta["engine_consulted"] is False
    assert meta["rows"] == 40
    assert "evaluation only" in meta["inspection_policy"]


def test_the_preferred_score_counts_only_rows_with_a_settled_target():
    """Round 4 (A13): the engine and PubChem are each scored against the
    adjudicated preferred name, over the rows that have one. A row with no
    settled target is not in the denominator, so a population nobody
    adjudicated (the evaluation-only one) reports zero rows, not zero right."""
    import naming_stage_artifact as tool

    targets = {"CCO": "ethanol", "C[Si](C)(C)O": "trimethylsilanol"}
    named = [
        {"smiles": "OCC", "name": "ethanol", "pubchem_name": "ethanol"},
        {"smiles": "C[Si](C)(C)O", "name": "trimethylsilanol",
         "pubchem_name": "hydroxy(trimethyl)silane"},
        {"smiles": "CC", "name": "ethane", "pubchem_name": "ethane"},
    ]
    assert tool._preferred_scores(named, targets) == {
        "adjudicated_rows": 2, "engine": 2, "pubchem": 1,
    }
    assert tool._preferred_scores(named, {})["adjudicated_rows"] == 0
