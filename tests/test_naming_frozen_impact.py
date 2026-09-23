"""The blind frozen-impact check (naming round 12), on FAKE rows only.

`naming_ref_compare.py` reaches the tuning populations, so it cannot say whether a change moved a
frozen row. `naming_stage_artifact.frozen_impact` can, and the property that matters is that it does so
WITHOUT un-blinding the set: it returns counts and nothing else. These tests never open a real frozen
population: every registry door, the namer and the sidecar directory are replaced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_stage_artifact as stage  # noqa: E402

_ROWS = [{"label": "row-alpha", "smiles": "C"}, {"label": "row-beta", "smiles": "CC"}]


@pytest.fixture
def fake_frozen(tmp_path, monkeypatch):
    """One fake frozen population `fz` with a sealed sidecar; the namer echoes what the test sets."""
    monkeypatch.setattr(stage, "SEALED", tmp_path)
    monkeypatch.setattr(stage, "POPULATIONS", (("fz", "fz.json", True), ("tune", "tune.json", False)))
    monkeypatch.setattr(stage, "active_populations", lambda *, final_evaluation=False: ["tune", "fz"])
    monkeypatch.setattr(stage, "load_population", lambda key, *, final_evaluation=False: ("fz.json", list(_ROWS)))
    (tmp_path / "r0.fz.records.json").write_text(
        json.dumps([{"label": "row-alpha", "name": "methane"}, {"label": "row-beta", "name": "ethane"}]),
        encoding="utf-8",
    )
    names = {"row-alpha": "methane", "row-beta": "ethane"}
    monkeypatch.setattr(
        stage, "_name_rows", lambda rows: [{"label": r["label"], "name": names[r["label"]]} for r in rows]
    )
    return names


def test_nothing_moved_reports_zero(fake_frozen):
    assert stage.frozen_impact("r0") == {"fz": (2, 0)}


def test_a_moved_row_is_counted_and_only_counted(fake_frozen):
    fake_frozen["row-beta"] = "bicarbon"
    assert stage.frozen_impact("r0") == {"fz": (2, 1)}


def test_a_row_missing_from_the_sidecar_counts_as_changed(fake_frozen, tmp_path):
    (tmp_path / "r0.fz.records.json").write_text(
        json.dumps([{"label": "row-alpha", "name": "methane"}]), encoding="utf-8"
    )
    assert stage.frozen_impact("r0") == {"fz": (2, 1)}


def test_a_stage_with_no_sealed_record_is_refused_not_treated_as_unchanged(fake_frozen):
    with pytest.raises(SystemExit):
        stage.frozen_impact("no-such-stage")


def test_the_tuning_population_is_never_consulted(fake_frozen, monkeypatch):
    """Only populations the registry marks frozen are compared; a tuning key must not need a sidecar."""
    seen = []
    monkeypatch.setattr(stage, "load_population", lambda key, *, final_evaluation=False: (seen.append(key), ("fz.json", list(_ROWS)))[1])
    stage.frozen_impact("r0")
    assert seen == ["fz"]


def test_the_command_prints_counts_and_never_a_label_or_a_name(fake_frozen, capsys, monkeypatch):
    fake_frozen["row-beta"] = "SECRET-NAME"
    monkeypatch.setattr(sys, "argv", ["naming_stage_artifact.py", "--frozen-impact", "r0"])
    with pytest.raises(SystemExit) as exit_info:
        stage.main()
    out = capsys.readouterr().out
    assert exit_info.value.code == 3
    assert "changed_count=1 of 2" in out
    for leaked in ("row-alpha", "row-beta", "SECRET-NAME", "methane", "ethane"):
        assert leaked not in out


def test_the_command_exits_zero_when_nothing_moved(fake_frozen, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["naming_stage_artifact.py", "--frozen-impact", "r0"])
    with pytest.raises(SystemExit) as exit_info:
        stage.main()
    assert exit_info.value.code == 0
    assert "unchanged" in capsys.readouterr().out
