"""tools/vendoring_mark_synced.py: pending → synced without a follow-up PR."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("vendoring_mark_synced", ROOT / "tools" / "vendoring_mark_synced.py")
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)
PENDING = _MOD.PENDING
mark_synced = _MOD.mark_synced


def test_pending_row_flips_to_synced():
    row = (
        "| fork pull request | xaerogonzo/open-iupac-namer#94 — pending sync, "
        "corresponding to this repository's pull request #545 (`branch`, base `abc`): NL-012. |"
    )
    out, n = mark_synced(row, fork=94, synced_on=date(2026, 11, 4), app_squash=None)
    assert n == 1
    assert "synced 2026-11-04" in out
    assert "pending sync" not in out


def test_check_pattern_matches_pending_only():
    assert PENDING.search("| fork pull request | xaerogonzo/open-iupac-namer#1 — pending sync, x")
    assert not PENDING.search("| fork pull request | xaerogonzo/open-iupac-namer#1 — synced 2026-01-01, x")
