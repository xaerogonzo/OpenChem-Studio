"""The current held-out population is evaluation-only, and that is enforced.

Each naming round spends the previous fresh set as fix targets, which spends
it as evidence of generalisation: round 4 spent `heldout.json`, round 5 spent
the v2 draw, round 7 spends the v3 draw. The v4 draw (`heldout4.json`) was drawn
and frozen before any round-7 diagnosis to replace it, and it is only worth
anything if nothing during the round looks at it: a row read while debugging
another stage is a row that ends up fixed, and then the "fresh" number is the
regression number again.

"Please don't look" is not a control. These tests make it one, and since round 7
the control is ONE registry rather than one list per tool:

* `benchmarks/naming/populations.toml` says which populations are `tuning` and
  which is `frozen`; `tools/naming_populations.py` is the only door, and it
  refuses a frozen one BEFORE the file is touched;
* every tool that enumerates populations (the stage tool, the registry audit,
  the Ertl cross-check) is asserted to take its list from that registry;
* no other tracked script names the frozen file, and none builds a population
  path with a glob, so no new diagnostic can quietly start reading it.

The one test that looks at rows (the overlap check) compares canonical SMILES
in memory and its failure message carries COUNTS only, never a structure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_populations as registry  # noqa: E402
import naming_stage_artifact as stage  # noqa: E402

FROZEN_FILE = "heldout4.json"
FROZEN_KEY = "heldout_v4"
FROZEN_META = "benchmarks/naming/heldout4.meta.json"

#: The only tracked scripts allowed to name the frozen file: the one that drew
#: it and this test. The stage tool used to be here; it reads the registry now.
ALLOWED = {
    "benchmarks/naming/build_heldout.py",
    "tests/test_naming_heldout_lock.py",
}


@pytest.fixture
def spy_on_the_frozen_file(monkeypatch):
    """Record every way a Path can be used to look at the frozen file."""
    touched: list[str] = []
    for name in ("read_text", "read_bytes", "open", "exists", "stat", "is_file"):
        original = getattr(Path, name)

        def spy(self, *args, _original=original, _name=name, **kwargs):
            if self.name == FROZEN_FILE:
                touched.append(_name)
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(Path, name, spy)
    return touched


def test_exactly_one_population_is_frozen_and_it_is_the_current_draw():
    frozen = [p.key for p in registry.registry() if p.frozen]
    assert frozen == [FROZEN_KEY], frozen


def test_a_stage_run_does_not_include_the_frozen_population():
    assert FROZEN_KEY not in stage.active_populations()


def test_loading_the_frozen_population_is_refused_before_the_file_is_touched(
    spy_on_the_frozen_file,
):
    """Every door: the registry's `path` and `load`, and the stage tool's."""
    with pytest.raises(registry.FrozenPopulation):
        registry.path(FROZEN_KEY)
    with pytest.raises(registry.FrozenPopulation):
        registry.load(FROZEN_KEY)
    with pytest.raises(stage.FrozenPopulation):
        stage.load_population(FROZEN_KEY)
    # `keys()` enumerates without opening, and must not so much as stat it.
    assert FROZEN_KEY not in registry.keys()
    assert spy_on_the_frozen_file == [], spy_on_the_frozen_file


def test_the_final_evaluation_is_the_one_door_in():
    assert FROZEN_KEY in stage.active_populations(final_evaluation=True)
    assert registry.path(FROZEN_KEY, final_evaluation=True).name == FROZEN_FILE


def test_the_previous_fresh_population_is_a_tuning_population_now():
    """Round 7 spends v3 (its rows may be adjudicated and fixed), so a stage
    run loads it, the registry says tuning, and its meta file says it is used --
    the same record v1 and v2 got when they were spent."""
    assert "heldout_v3" in stage.active_populations()
    assert registry.get("heldout_v3").status == registry.TUNING
    meta = json.loads(
        (ROOT / "benchmarks/naming/heldout3.meta.json").read_text(encoding="utf-8")
    )
    assert meta["status"] == "USED_FOR_TUNING"
    assert "naming round 7" in meta["status_since"]


def test_every_enumerating_tool_takes_its_populations_from_the_registry():
    """The hazard: one tool keeps a private list, and the list is where a frozen
    file gets added. Each tool is asserted to agree with the registry, and none
    may hold the frozen file."""
    import ertl_crosscheck
    import retained_name_audit

    tuning_files = [p.file for p in registry.tuning()]
    audit_files = [f for _short, f in retained_name_audit.TUNING_POPULATIONS]
    assert audit_files == tuning_files
    assert FROZEN_FILE not in audit_files

    ertl_files = [c.name for c in ertl_crosscheck.CORPORA]
    assert set(ertl_files) <= set(tuning_files), ertl_files
    assert FROZEN_FILE not in ertl_files

    stage_files = [f for _k, f, frozen in stage.POPULATIONS if not frozen]
    assert stage_files == tuning_files


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


def test_no_tracked_script_builds_a_population_path_with_a_glob():
    """`glob("heldout*.json")` would pull the frozen file in without naming it.

    The pattern is assembled from pieces and this file is excluded from the
    search, so the test does not match its own prose.
    """
    pattern = r"glob\(.*(held|corpus)|(held|corpus).*\.glob\(|iterdir\(\).*held"
    hits = subprocess.run(
        ["git", "grep", "-nE", pattern, "--", "*.py", ":!tests/test_naming_heldout_lock.py"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    assert not hits, hits


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
    assert meta["variant"] == "v4"


def test_no_structure_is_in_two_populations():
    """A held-out set is independent only if it shares no STRUCTURE with the
    populations that were tuned on, and two PubChem CIDs can be one structure.

    The builder excludes by the stored strings at draw time; this re-checks
    after canonicalising every row of all five. It reads the frozen file's
    structures in memory, which the policy allows for an aggregate check, and
    the assertion carries COUNTS only so a failure cannot print a row.
    """
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    canonical: dict[str, set[str]] = {}
    for population in registry.registry():
        rows = json.loads(
            (registry.BENCH / population.file).read_text(encoding="utf-8")
        )
        canonical[population.key] = {
            Chem.MolToSmiles(mol)
            for row in rows
            if (mol := Chem.MolFromSmiles(row["smiles"])) is not None
        }
    keys = list(canonical)
    shared = {
        (a, b): len(canonical[a] & canonical[b])
        for i, a in enumerate(keys)
        for b in keys[i + 1:]
    }
    assert not any(shared.values()), {pair: n for pair, n in shared.items() if n}


def test_the_registry_rejects_a_status_that_would_read_as_not_frozen(tmp_path, monkeypatch):
    """A typo in `status` must not silently mean 'tuning'."""
    bad = tmp_path / "populations.toml"
    bad.write_text(
        '[[population]]\nkey="a"\nshort="a"\nfile="a.json"\nstatus="froxen"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "REGISTRY", bad)
    with pytest.raises(ValueError, match="neither"):
        registry.registry()


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
