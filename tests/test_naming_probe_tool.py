"""tools/naming_probe.py: the round-8 instrument for naming ordinary molecules, kept working (naming round 8, round end)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_probe as probe  # noqa: E402


def test_the_probe_names_a_molecule_and_reports_no_failed_plan_for_a_clean_one():
    name, failures = probe._name_with_failures("CC(=O)C(C)=O")
    assert name == "butane-2,3-dione"
    assert failures == []


def test_the_probe_shows_a_plan_that_failed_to_execute_and_the_engine_silently_left():
    """D-088b (open): the carbamate plan for a carbazate is TRIED, fails ('leaves heavy atoms unclaimed'), and the engine names the next plan. The probe is how that was seen. If the
    carbazate is fixed this test's molecule must change, not be deleted: the point is that a failed top plan is visible."""
    name, failures = probe._name_with_failures("CCOC(=O)NN")
    assert name
    assert any("unclaimed" in f or "owned by no node" in f for f in failures), failures


def test_the_probe_restores_the_engine_after_it_wraps_it():
    from openchem.vendor.iupac_namer import engine

    before = engine.SubstitutivePath.execute
    probe._name_with_failures("CC")
    assert engine.SubstitutivePath.execute is before


# --- naming round 9 (R0): plan counters, and a refusal to name a frozen structure ------------------------------------------------------

import hashlib  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402

import naming_populations as populations  # noqa: E402


def test_a_clean_name_reports_its_plan_counters():
    record = probe.probe_structure("CC(=O)C(C)=O")
    assert record["name"] == "butane-2,3-dione"
    assert record["status"] == "clean" and record["errored"] == 0 and record["attempted"] >= 1


def test_a_top_plan_that_died_and_still_produced_a_name_is_a_fallback():
    """D-088b (open): the carbamate plan for a carbazate is tried, fails, and the engine names the next plan. That silent fall-back is the
    number round 8 found most of its defects in, so it has its own status and not a place under 'clean'."""
    record = probe.probe_structure("CCOC(=O)NN")
    assert record["status"] == "fallback", record
    assert record["errored"] >= 1 and record["name"] and not str(record["name"]).startswith("NAMING ERROR")


class _ErrorTree:
    message = "atoms [0] unclaimed"


_ErrorTree.__name__ = "ErrorTree"  # the spy recognises an error tree by its class NAME, as the engine's own type is not importable here


def test_no_plan_and_all_plans_failed_are_different_defects(monkeypatch):
    """`no_plan`: nothing was ever generated to execute (a CANDIDATE failure). `all_plans_failed`: plans were generated and each died in
    the builder (an EXECUTION failure). They are fixed in different places, so the probe must not merge them."""
    import openchem.vendor.iupac_namer as namer
    from openchem.vendor.iupac_namer import engine

    monkeypatch.setattr(namer, "name_smiles", lambda smiles: "NAMING ERROR: No valid naming plan found")
    none = probe.probe_structure("CC")
    assert none["status"] == "no_plan" and none["attempted"] == 0

    class Plan:
        pcg_type = "x"

        class named_parent:  # noqa: N801
            name = "methane"

    monkeypatch.setattr(engine.SubstitutivePath, "execute", lambda self, plan, *a, **k: _ErrorTree())
    monkeypatch.setattr(namer, "name_smiles", lambda smiles: (engine.SubstitutivePath.execute(None, Plan()), "NAMING ERROR: x")[1])
    dead = probe.probe_structure("CC")
    assert dead["status"] == "all_plans_failed" and dead["attempted"] == 1 and dead["errored"] == 1


def test_the_probe_summary_counts_by_status():
    records = [
        {"status": "clean", "attempted": 3, "errored": 0},
        {"status": "fallback", "attempted": 4, "errored": 1},
        {"status": "no_plan", "attempted": 0, "errored": 0},
    ]
    line = probe.summarise(records)
    assert "3 structures" in line and "clean 1" in line and "fallback 1" in line and "no_plan 1" in line and "all_plans_failed 0" in line
    assert "plans executed 7" in line and "error trees 1" in line


def _fake_membership(monkeypatch, smiles: str, key: str = "heldout_x"):
    salt = "test-salt"
    digest = hashlib.sha256((salt + smiles).encode("utf-8")).hexdigest()
    monkeypatch.setattr(populations, "frozen_membership", lambda: {key: (salt, frozenset({digest}))})


def test_a_frozen_structure_is_recognised_by_hash_and_only_that_one(monkeypatch):
    _fake_membership(monkeypatch, "CCO")
    assert populations.frozen_key_of("CCO") == "heldout_x"
    assert populations.frozen_key_of("CCC") is None


def test_the_probe_refuses_a_frozen_structure_and_says_which_population_without_naming_it(monkeypatch, capsys):
    _fake_membership(monkeypatch, "CCO")
    monkeypatch.setattr(sys, "argv", ["naming_probe.py", "--no-readback", "OCC", "CC(=O)C(C)=O"])
    code = probe.main()
    out = capsys.readouterr().out
    assert code == 3, "a refusal must not exit 0: a battery script would read it as a clean run"
    assert "FROZEN" in out and "heldout_x" in out
    assert "ethanol" not in out, "a refused structure is not named"
    assert "butane-2,3-dione" in out, "the other structures on the line are still named"


def test_the_probe_writes_its_records_as_json(monkeypatch, tmp_path, capsys):
    target = tmp_path / "probe.json"
    monkeypatch.setattr(populations, "frozen_membership", lambda: {})
    monkeypatch.setattr(sys, "argv", ["naming_probe.py", "--no-readback", "--json", str(target), "CC(=O)C(C)=O"])
    assert probe.main() == 0
    records = json.loads(target.read_text(encoding="utf-8"))
    assert [r["name"] for r in records] == ["butane-2,3-dione"]
    assert records[0]["status"] == "clean"
    assert "1 structures" in capsys.readouterr().out


def test_a_frozen_population_without_membership_hashes_is_an_error_not_an_empty_set(tmp_path, monkeypatch):
    """An empty set would read as 'nothing is frozen' to the one tool that uses it to refuse a structure: the unsafe default."""
    (tmp_path / "populations.toml").write_text('[[population]]\nkey="f"\nshort="f"\nfile="f.json"\nstatus="frozen"\n', encoding="utf-8")
    (tmp_path / "f.meta.json").write_text(json.dumps({"rows": 1}), encoding="utf-8")
    monkeypatch.setattr(populations, "REGISTRY", tmp_path / "populations.toml")
    monkeypatch.setattr(populations, "BENCH", tmp_path)
    with pytest.raises(ValueError, match="no membership hashes"):
        populations.frozen_membership()


def test_the_real_frozen_populations_carry_membership_hashes_made_with_the_shared_salt():
    membership = populations.frozen_membership()
    assert membership, "the registry has at least one frozen population"
    for key, (salt, hashes) in membership.items():
        assert hashes and all(len(h) == 64 for h in hashes), key
        assert salt == populations.MEMBERSHIP_SALT, f"{key}: the meta was hashed with a salt the probe does not use"


def test_membership_hashes_are_sorted_salted_and_row_order_independent():
    rows = [{"smiles": "CCO"}, {"smiles": "CCC"}]
    forward = populations.membership_hashes(rows)
    assert forward == populations.membership_hashes(list(reversed(rows))) == sorted(forward)
    assert populations.membership_hash("CCO") in forward
    assert populations.membership_hash("CCO", "another-salt") != populations.membership_hash("CCO")
