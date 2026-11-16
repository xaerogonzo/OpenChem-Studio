"""NL-066 (WS3): retained-name registry backlog is recorded, not eliminated.

Round 5 typed the entries the gate still emits; 171 rows stay ``UNKNOWN``. Full contract checks
live in ``tests/test_retained_registry_contract.py``; ``tools/retained_name_audit.py`` reports
the backlog for humans.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import retained_name_audit as audit  # noqa: E402

# Measured 2026-11-16 via ``tools/retained_name_audit.py``.
REGISTRY_TOTAL = 293
RULE_CITED = 31
PIN_STATUS = {"PIN": 53, "RETAINED_NOT_PIN": 69, "UNKNOWN": 171}


@pytest.fixture(scope="module")
def registry() -> dict:
    return audit.registry()


def test_nl066_registry_passes_audit_validate(registry):
    assert audit.validate(registry) == []


def test_nl066_backlog_counts_measured_2026_11_16(registry):
    assert len(registry) == REGISTRY_TOTAL
    counts = {status: 0 for status in PIN_STATUS}
    for entry in registry.values():
        key = entry.get("pin_status") or "UNKNOWN"
        counts[key] += 1
    assert counts == PIN_STATUS
    cited = sum(
        1
        for e in registry.values()
        if str(e.get("rule", "")).strip().lower() not in ("various", "", "none")
    )
    assert cited == RULE_CITED