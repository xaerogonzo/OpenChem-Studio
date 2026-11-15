"""Local CIP Validation Suite inventory (`benchmarks/naming/CIP_VALIDATION_SUITE.md`).

Runs only when ``compounds.smi`` is present (default path on disk or ``OPENCHEM_CIP_SUITE``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "naming_cip_suite_probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("naming_cip_suite_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["naming_cip_suite_probe"] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()
_suite_path = probe.suite_smi_path()
_suite_missing = not _suite_path.is_file()


@pytest.mark.skipif(_suite_missing, reason=f"CIP suite SMILES not at {_suite_path}")
def test_cip_suite_entry_count_is_stable():
    rows = probe.load_rows(_suite_path)
    assert len(rows) == 288


@pytest.mark.skipif(_suite_missing, reason=f"CIP suite SMILES not at {_suite_path}")
def test_cip_suite_pins_vs207_vs214_vs279_vs231_present():
    rows = probe.load_rows(_suite_path)
    ids = {r.suite_id for r in rows}
    assert ids >= {"VS207", "VS214", "VS279", "VS231"}


@pytest.mark.skipif(_suite_missing, reason=f"CIP suite SMILES not at {_suite_path}")
def test_cip_suite_has_no_bicyclo_3_3_1_bridgehead_row_nl002():
    """Measured 2026-11-15: no norbornane / bicyclo[3.3.1] entry for NL-002."""
    rows = probe.load_rows(_suite_path)
    hits = [r for r in rows if probe.BRIDGEHEAD_GREP.search(r.smiles)]
    bicyclo_331 = [
        r
        for r in rows
        if "bicyclo[3.3.1]" in r.smiles.lower() or "bicyclo[3.3.1]" in r.labels.lower()
    ]
    assert not bicyclo_331
    assert not hits  # measured 2026-11-15: no bicyclo/norborn bridgehead SMILES in the suite