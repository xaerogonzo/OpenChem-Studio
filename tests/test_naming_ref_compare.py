"""The ref-compare firewall: its pure comparison, its manifest rules, and one real two-engine run.

`tools/naming_ref_compare.py` names the same structures with a base engine and the working tree and checks the
difference against a manifest. The comparison is a pure function, so its rules are tested without an engine; the last
test runs the real tool against HEAD and the working tree, and checks what must hold whether or not the tree is dirty.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_ref_compare as rc  # noqa: E402

BASE = {"a": "old-a", "b": "old-b", "c": "old-c"}


def _ok(*ids, value=True):
    return {i: value for i in ids}


def test_a_name_that_changes_and_is_not_listed_is_a_violation():
    head = {**BASE, "a": "new-a"}
    changed, violations = rc.evaluate(BASE, head, _ok("a"), _ok("a"), {})
    assert [c["id"] for c in changed] == ["a"]
    assert violations == ["UNEXPECTED_CHANGE a: 'old-a' -> 'new-a'"]


def test_nothing_changing_is_clean():
    assert rc.evaluate(BASE, dict(BASE), {}, {}, {}) == ([], [])


def test_a_listed_must_change_that_does_not_happen_is_a_violation():
    manifest = {"a": {"id": "a", "expect": rc.MUST_CHANGE, "reason_rule_id": "P-44.1.1", "expected_layer": "CANDIDATE_ABSENT"}}
    _, violations = rc.evaluate(BASE, dict(BASE), {}, {}, manifest)
    assert violations and violations[0].startswith("EXPECTED_CHANGE_MISSING a")


def test_a_must_change_to_the_wrong_name_does_not_satisfy_its_entry():
    manifest = {"a": {"id": "a", "expect": rc.MUST_CHANGE, "reason_rule_id": "P-44.1.1",
                      "expected_layer": "CANDIDATE_ABSENT", "expected_name": "right"}}
    _, violations = rc.evaluate(BASE, {**BASE, "a": "wrong"}, _ok("a"), _ok("a"), manifest)
    assert violations == ["WRONG_CHANGE_TARGET a: expected 'right', got 'wrong' (P-44.1.1)"]
    _, clean = rc.evaluate(BASE, {**BASE, "a": "right"}, _ok("a"), _ok("a"), manifest)
    assert clean == []


def test_an_explicit_must_stay_that_moves_is_a_violation():
    manifest = {"b": {"id": "b", "expect": rc.MUST_STAY}}
    _, violations = rc.evaluate(BASE, {**BASE, "b": "moved"}, _ok("b"), _ok("b"), manifest)
    assert any(v.startswith("MUST_STAY_MOVED b") for v in violations)


def test_a_structural_regression_cannot_be_excused_by_any_entry():
    """A name that round-tripped and no longer does is a violation even when the manifest says it may change."""
    for entry in ({"id": "a", "expect": rc.EQUIVALENT},
                  {"id": "a", "expect": rc.MUST_CHANGE, "reason_rule_id": "r", "expected_layer": "l"}):
        _, violations = rc.evaluate(BASE, {**BASE, "a": "new"}, {"a": True}, {"a": False}, {"a": entry})
        assert any(v.startswith("STRUCTURAL_REGRESSION a") for v in violations), entry


def test_structural_equivalence_allows_a_change_only_while_it_round_trips():
    manifest = {"a": {"id": "a", "expect": rc.EQUIVALENT}}
    _, ok = rc.evaluate(BASE, {**BASE, "a": "other"}, _ok("a"), _ok("a"), manifest)
    assert ok == []
    _, lost = rc.evaluate(BASE, {**BASE, "a": "other"}, _ok("a", value=False), _ok("a", value=False), manifest)
    assert any(v.startswith("EQUIVALENCE_LOST a") for v in lost)


def test_a_row_named_by_only_one_side_is_reported_not_ignored():
    _, violations = rc.evaluate(BASE, {"a": "old-a", "b": "old-b"}, {}, {}, {})
    assert violations == ["ROW_SET_DIFFERS c: named by only one side"]


def test_a_change_for_a_different_reason_does_not_satisfy_an_entry_for_another_row():
    """The entry is per row: listing row `a` does not excuse row `b` moving."""
    manifest = {"a": {"id": "a", "expect": rc.MUST_CHANGE, "reason_rule_id": "r", "expected_layer": "l"}}
    _, violations = rc.evaluate(BASE, {**BASE, "a": "x", "b": "y"}, _ok("a", "b"), _ok("a", "b"), manifest)
    assert [v.split()[0] for v in violations] == ["UNEXPECTED_CHANGE"] and "b" in violations[0]


def test_a_must_change_entry_must_say_why_and_where(tmp_path):
    bad = tmp_path / "m.toml"
    bad.write_text('[[expect]]\nid = "a"\nexpect = "MUST_CHANGE"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="reason_rule_id"):
        rc.load_manifest(bad)
    dup = tmp_path / "d.toml"
    dup.write_text('[[expect]]\nid = "a"\nexpect = "MUST_STAY"\n[[expect]]\nid = "a"\nexpect = "MUST_STAY"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        rc.load_manifest(dup)
    unknown = tmp_path / "u.toml"
    unknown.write_text('[[expect]]\nid = "a"\nexpect = "MAYBE"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown expectation"):
        rc.load_manifest(unknown)
    assert rc.load_manifest(None) == {}


def test_the_structure_sets_never_reach_the_frozen_population():
    """`pop:` rows come through the registry's `tuning()`, so the frozen file is not even opened."""
    ids = [i for i, _ in rc.collect({"pop"})]
    assert ids and all(i.startswith("pop:") for i in ids)
    assert not any(i.startswith("pop:heldout_v5:") for i in ids)
    assert any(i.startswith("pop:heldout_v4:") for i in ids), "v4 is a tuning population from round 8"


def test_two_real_engines_are_compared_and_every_unlisted_change_is_a_violation(tmp_path):
    """The one end-to-end run: extract HEAD's src, name a small set with it and with the WORKING TREE, compare.

    Whether anything differs depends on whether the tree is dirty (mid-stage it is, and the tool must then say so), so the
    test asserts what holds either way: two DIFFERENT engine trees were used (a vacuous comparison is refused), every
    change is a violation because no manifest was given, and the exit code follows the violations.
    """
    import json

    out = tmp_path / "report.json"
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools/naming_ref_compare.py"), "--base", "HEAD", "--sets", "mc", "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT,
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["engines"]["base"] != report["engines"]["head"]
    assert len(report["violations"]) >= len(report["changed"]), "an unlisted change is a violation"
    assert (done.returncode == 0) == (not report["violations"])
    if not report["toolchain"]["working_tree_dirty"]:
        assert report["changed"] == [], "a clean tree compared with its own HEAD changes nothing"
    assert report["toolchain"]["rdkit"] and report["toolchain"]["python"]
