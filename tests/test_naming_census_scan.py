"""The census scan tool (naming round 13's prelude): classification, refusal to scan a different sample, and the report.

The namer and OPSIN are replaced, so this runs with no JRE; one test names three real structures with the real
engine and skips the read-back.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_census_scan as scan  # noqa: E402

ETHANOL = "CCO"


def test_an_identical_read_back_is_exact():
    assert scan.classify(ETHANOL, "ethanol", "CCO") == "exact"


def test_stereo_only_difference_is_same_connectivity():
    assert scan.classify("C[C@H](N)C(=O)O", "alanine", "CC(N)C(=O)O") == "same_connectivity"


def test_a_different_formula_is_a_wrong_molecule_class():
    """The oxadiazolyl `-3-yl` shape: the read-back carries two more hydrogens."""
    assert scan.classify("Cc1nnc(C)o1", "x", "CC1=NN(C)CO1") == "mismatch_formula"


def test_the_same_formula_with_another_structure_is_its_own_class():
    assert scan.classify("Cc1ccccc1C", "x", "Cc1cccc(C)c1") == "mismatch_same_formula"


def test_an_empty_read_back_is_unparsable():
    assert scan.classify(ETHANOL, "gibberish", "") == "unparsable"


def test_an_embedded_error_and_a_refusal_are_classified_before_any_read_back():
    assert scan.classify(ETHANOL, "x-({[NAMING ERROR: No valid naming plan found for C]}oxy)y", None) == "naming_error"
    assert scan.classify(ETHANOL, "RAISED: ValueError: charge perception claimed", None) == "refused"


def test_the_summary_counts_every_class_and_clusters_error_stems():
    recs = {
        "a": {"smiles": "C", "name": "methane", "cls": "exact"},
        "b": {"smiles": "CC", "name": "[NAMING ERROR: atom ownership under parent 'ethane': atom 3]", "cls": "naming_error"},
        "c": {"smiles": "CCC", "name": "x", "cls": "mismatch_formula"},
    }
    text = "\n".join(scan.summarise(recs))
    assert "3 rows" in text and "naming_error" in text and "mismatch_formula" in text
    assert "atom ownership under parent" in text
    assert "candidate wrong structures: 1" in text and "visible failures: 1" in text


def test_compare_lists_rows_that_changed_class_and_only_counts_a_rename():
    old = {"a": {"name": "n1", "cls": "mismatch_formula"}, "b": {"name": "m1", "cls": "exact"}}
    new = {"a": {"name": "n2", "cls": "exact"}, "b": {"name": "m2", "cls": "exact"}}
    text = "\n".join(scan.compare(old, new))
    assert "1 rows changed class; 2 rows changed name" in text
    assert "a: mismatch_formula -> exact" in text and "b:" not in text


def test_a_sample_that_does_not_match_its_meta_is_refused(tmp_path, monkeypatch):
    sample = tmp_path / "s.json"
    sample.write_text(json.dumps([{"label": "x", "smiles": "C"}]), encoding="utf-8")
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"census_sha256": "0" * 64}), encoding="utf-8")
    monkeypatch.setattr(scan, "CENSUS", sample)
    monkeypatch.setattr(scan, "META", meta)
    with pytest.raises(SystemExit):
        scan.load_sample()


def test_the_real_sample_matches_its_meta():
    assert len(scan.load_sample()) == 2000


def test_names_only_names_real_structures_without_a_jre(monkeypatch):
    rows = [{"label": "r1", "smiles": "CCO"}, {"label": "r2", "smiles": "c1ccccc1"}]
    records = scan.scan(rows, names_only=True)
    assert records["r1"]["name"] == "ethanol" and records["r2"]["name"] == "benzene"
    assert all(r["cls"] == "exact" and r["back"] is None for r in records.values())


def test_the_command_refuses_without_java_unless_names_only(monkeypatch, capsys):
    monkeypatch.setattr(scan.shutil, "which", lambda _name: None)
    assert scan.main([]) == 2
    assert "java" in capsys.readouterr().err
