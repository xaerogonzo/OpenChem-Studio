"""The current held-out population is evaluation-only, and that is enforced.

Each naming round spends the previous fresh set as fix targets, which spends
it as evidence of generalisation: round 4 spent `heldout.json`, round 5 spent
the v2 draw, round 7 spent the v3 draw, round 8 spends the v4 draw. The v5 draw
(`heldout5.json`) was drawn and frozen before any round-8 diagnosis to replace
it, and it is only worth anything if nothing during the round looks at it: a row
read while debugging another stage is a row that ends up fixed, and then the
"fresh" number is the regression number again.

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

FROZEN_FILE = "heldout5.json"
FROZEN_KEY = "heldout_v5"
FROZEN_META = "benchmarks/naming/heldout5.meta.json"

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


@pytest.mark.parametrize(
    "key, meta_file, since",
    [
        ("heldout_v3", "heldout3.meta.json", "naming round 7"),
        ("heldout_v4", "heldout4.meta.json", "naming round 8"),
    ],
)
def test_a_spent_fresh_population_is_a_tuning_population_now(key, meta_file, since):
    """A round spends the previous fresh set (its rows may be adjudicated and
    fixed), so a stage run loads it, the registry says tuning, and its meta file
    says it is used -- the same record v1 and v2 got when they were spent."""
    assert key in stage.active_populations()
    assert registry.get(key).status == registry.TUNING
    meta = json.loads((ROOT / "benchmarks/naming" / meta_file).read_text(encoding="utf-8"))
    assert meta["status"] == "USED_FOR_TUNING"
    assert since in meta["status_since"]


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
    assert meta["variant"] == "v5"


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


def test_no_population_shares_a_cid_or_a_row_identity_with_another():
    """Structure overlap (above) is one way a fresh set stops being fresh; the
    other two are the SAME PUBCHEM RECORD and the SAME ROW IDENTITY. The draw
    excludes by structure, and its offsets make the CID sets disjoint by
    construction -- which is a claim, and this is the measurement of it.

    Reads only the `pubchem_cid` and `label` fields, in memory, and the message
    carries COUNTS: never a value, so a failure cannot print an identifier of a
    row from the frozen file.
    """
    cids: dict[str, list] = {}
    labels: dict[str, list] = {}
    for population in registry.registry():
        rows = json.loads((registry.BENCH / population.file).read_text(encoding="utf-8"))
        cids[population.key] = [r["pubchem_cid"] for r in rows if r.get("pubchem_cid") is not None]
        labels[population.key] = [r["label"] for r in rows if r.get("label")]
    within = {k: len(v) - len(set(v)) for k, v in {**cids, **{f"{k}/labels": v for k, v in labels.items()}}.items()}
    assert not any(within.values()), {k: n for k, n in within.items() if n}
    keys = list(cids)
    shared_cids = {
        (a, b): len(set(cids[a]) & set(cids[b])) for i, a in enumerate(keys) for b in keys[i + 1:]
    }
    shared_labels = {
        (a, b): len(set(labels[a]) & set(labels[b])) for i, a in enumerate(keys) for b in keys[i + 1:]
    }
    assert not any(shared_cids.values()), {p: n for p, n in shared_cids.items() if n}
    assert not any(shared_labels.values()), {p: n for p, n in shared_labels.items() if n}


def test_a_committed_artifact_carries_no_row_of_a_frozen_population():
    """"Aggregates only" must hold for what is COMMITTED, not just what is printed.

    Through round 7 the final artifact carried the frozen population's per-row
    `records`, so every name and outcome was in the repository while the console
    showed counts. The split keeps counts and a hash reference in the public
    artifact and moves the rows to a sealed sidecar; the input is untouched
    because `--compare` still reads it in memory."""
    import copy
    import hashlib

    rows = [{"label": "x1", "name": "secret-name", "outcome": "exact"}]
    artifact = {
        "stage": "r8-test",
        "populations": {
            "heldout_v5": {"rows": 1, "outcomes": {"exact": 1}, "records": rows},
            "heldout_v4": {"rows": 1, "outcomes": {"exact": 1}, "records": copy.deepcopy(rows)},
        },
    }
    before = copy.deepcopy(artifact)
    public, sealed = stage.seal_frozen_records(artifact, {"heldout_v5"})

    assert artifact == before, "the in-memory artifact (still read by --compare) was modified"
    frozen = public["populations"]["heldout_v5"]
    assert "records" not in frozen and frozen["outcomes"] == {"exact": 1}
    assert "secret-name" not in json.dumps(public["populations"]["heldout_v5"])
    assert sealed == {"heldout_v5": rows}
    body = json.dumps(rows, indent=1).encode("utf-8")
    assert frozen["records_sealed"] == {
        "file": "sealed/r8-test.heldout_v5.records.json",
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    assert public["populations"]["heldout_v4"]["records"] == rows, "a tuning population keeps its rows"


def test_the_registry_state_is_read_from_the_meta_file_and_never_opens_the_frozen_one(
    spy_on_the_frozen_file,
):
    state = stage.registry_state()
    meta = json.loads((ROOT / FROZEN_META).read_text(encoding="utf-8"))
    assert state[FROZEN_KEY]["status"] == registry.FROZEN
    assert state[FROZEN_KEY]["sha256"] == meta["heldout_sha256"]
    assert state[FROZEN_KEY]["rows"] == meta["rows"]
    assert all(v["status"] == registry.TUNING for k, v in state.items() if k != FROZEN_KEY)
    assert spy_on_the_frozen_file == [], spy_on_the_frozen_file


def test_an_artifact_records_the_identity_of_the_source_it_ran():
    """`src_tree` is the tree hash of src/ at HEAD: two artifacts with the same value were produced by
    byte-identical source, whatever else differs between their commits, which is what makes 'this stage
    changed no src file, so its baseline is the previous commit's engine' a checkable claim."""
    provenance = stage._provenance("r8-test")
    expected = subprocess.run(["git", "rev-parse", "HEAD:src"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert provenance["src_tree"] == expected and len(expected) == 40


def test_no_other_tracked_script_names_the_sealed_directory():
    """The seal is a convention, so the guard is what makes opening it a deliberate act."""
    listed = subprocess.run(
        ["git", "grep", "-l", "sealed", "--", "*.py"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    allowed = {"tools/naming_stage_artifact.py", "tests/test_naming_heldout_lock.py"}
    # `sealed` is an ordinary word; only a script that names the DIRECTORY matters.
    offenders = [
        f for f in listed
        if f not in allowed
        and "stages/sealed" in (ROOT / f).read_text(encoding="utf-8", errors="replace")
    ]
    assert not offenders, offenders


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
        # `known_deviation` (naming round 8): rows whose engine name carries a DECLARED legacy locant, never counted as a preferred match; none here.
        "adjudicated_rows": 2, "engine": 2, "pubchem": 1, "known_deviation": 0,
    }
    assert tool._preferred_scores(named, {})["adjudicated_rows"] == 0
