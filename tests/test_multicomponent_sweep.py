"""The multicomponent sweep's writer (round 5, S1).

Skipped unless `OPENCHEM_WRITE_SWEEP` names an output file: it runs every
calculator over the whole panel, which is a measurement, not a check.
The guard that holds the result is written in S2, once the matrix exists.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.multicomponent_sweep import classify, load_panel, run_sweep


@pytest.mark.skipif(not os.environ.get("OPENCHEM_WRITE_SWEEP"), reason="a measurement; set OPENCHEM_WRITE_SWEEP")
def test_write_the_sweep_matrix(qapp):
    rows = load_panel()
    only = os.environ.get("OPENCHEM_SWEEP_ONLY")
    if only:
        rows = [r for r in rows if r.id in only.split(",")]
    # The sidecar calculators read an interpreter path from Settings, which
    # the suite isolates -- so without this they report "not configured" on
    # every row, controls included, and say nothing about salts. The paths
    # are handed in by the caller and written to the ISOLATED store only.
    sidecars = os.environ.get("OPENCHEM_SWEEP_SIDECARS")
    if sidecars:
        # THROUGH `openchem.app.settings.QSettings`, the name the suite's
        # isolation fixture patches -- NOT `PySide6.QtCore.QSettings`, which
        # it does not, and which is the developer's real registry key. The
        # first version of this block imported the latter.
        import openchem.app.settings as settings_module

        store = settings_module.QSettings(settings_module.ORG_NAME, settings_module.APP_NAME)
        for pair in sidecars.split(";"):
            key, _, value = pair.partition("=")
            store.setValue(key, value)
        store.sync()
    calculators = os.environ.get("OPENCHEM_SWEEP_CALCULATORS")
    sweep = run_sweep(qapp, rows, calculator_ids=calculators.split(",") if calculators else None)
    sweep["classified"] = classify(sweep, rows)
    Path(os.environ["OPENCHEM_WRITE_SWEEP"]).write_text(json.dumps(sweep, indent=1), encoding="utf-8")
