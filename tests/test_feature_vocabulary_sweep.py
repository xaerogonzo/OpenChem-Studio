"""Every feature pattern against every structure this project already holds.

`fg:hydrazine` matched a nitramine's N-N bond, `detect_features` raised
`UndeclaredChargeState`, and one nitramine took every functional-group alert for
its molecule with it. The pattern was fixed; nothing had asked whether the OTHER
patterns do the same on structures nobody happened to draw. This asks, on 2,187
of them (the census panel, the naming corpus and the 2,000-structure naming
census sample), in a few seconds -- and the answer was eight more, in five
features. They are listed in `known_vocabulary_defects.toml` and that list only
shrinks: a new one fails here, and a fixed one must be deleted from it.

Two things this does NOT do: it does not judge whether a feature's labels are
right (`test_structural_features` and the coverage matrix own that), and it does
not fix the eight -- fixing one means deciding what the vocabulary says about a
charge state, which is a decision, not a patch.
"""

from __future__ import annotations

import collections
import json
import tomllib
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import structural_features as sf

_ROOT = Path(__file__).resolve().parent.parent
_KNOWN = _ROOT / "tests" / "fixtures" / "structural_features" / "known_vocabulary_defects.toml"


def _populations() -> dict[str, list[tuple[str, str]]]:
    panel = tomllib.loads((_ROOT / "tests" / "fixtures" / "census_panel.toml").read_text(encoding="utf-8"))
    return {
        "census_panel": [(r["id"], r["smiles"]) for r in panel["row"]],
        "naming_corpus": [
            (r["label"], r["smiles"])
            for r in json.loads((_ROOT / "benchmarks" / "naming" / "corpus.json").read_text(encoding="utf-8"))
        ],
        "naming_census": [
            (r["label"], r["smiles"])
            for r in json.loads((_ROOT / "benchmarks" / "naming" / "census_sample.json").read_text(encoding="utf-8"))
        ],
    }


@pytest.fixture(scope="module")
def sweep() -> dict[str, dict]:
    """Per population and label: the features skipped, and every feature counted."""
    out: dict[str, dict] = {}
    for population, rows in _populations().items():
        for label, smiles in rows:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                continue
            detection = sf.detect_features_tolerant(mol)
            out[f"{population}/{label}"] = {
                "skipped": sorted({item.feature_id for item in detection.skipped}),
                "counts": dict(collections.Counter(f.feature_id for f in detection.features)),
            }
    return out


def _known() -> set[str]:
    data = tomllib.loads(_KNOWN.read_text(encoding="utf-8"))
    return {f"{d['population']}/{d['label']}|{d['feature']}" for d in data["defect"]}


def test_the_sweep_really_covers_the_populations(sweep):
    """The control for every test below: a sweep over nothing finds nothing."""
    assert len(sweep) >= 2100, len(sweep)
    assert any(key.startswith("census_panel/") for key in sweep)
    assert any(key.startswith("naming_corpus/") for key in sweep)
    assert any(key.startswith("naming_census/") for key in sweep)


def test_no_pattern_matches_a_charge_state_it_does_not_declare_on_a_new_structure(sweep):
    found = {f"{key}|{feature}" for key, cell in sweep.items() for feature in cell["skipped"]}
    new = sorted(found - _known())
    assert not new, (
        "a feature pattern matched a group in a charge state its definition does not declare "
        "(the fg:hydrazine class). Decide what the vocabulary says about that state and fix the "
        f"pattern or declare the label; do not just add it to the known list:\n  " + "\n  ".join(new)
    )


def test_every_known_defect_still_occurs(sweep):
    """The ratchet's other half: a defect that was fixed must be deleted, so the
    list cannot rot into a record of things that no longer happen."""
    found = {f"{key}|{feature}" for key, cell in sweep.items() for feature in cell["skipped"]}
    stale = sorted(_known() - found)
    assert not stale, "these no longer occur -- delete them from known_vocabulary_defects.toml:\n  " + "\n  ".join(stale)


def test_the_known_defects_are_listed_once_each_and_with_their_smiles():
    data = tomllib.loads(_KNOWN.read_text(encoding="utf-8"))["defect"]
    keys = [f"{d['population']}/{d['label']}|{d['feature']}" for d in data]
    assert len(keys) == len(set(keys))
    populations = _populations()
    for d in data:
        assert (d["label"], d["smiles"]) in populations[d["population"]], (
            f"{d['label']}: the listed SMILES is not the population's"
        )


# --- expected instances: what must STILL be found, and what must not be -----------------

#: Exact counts for a handful of the panel's structures, chosen because a pattern change
#: that fixes one crash can quietly remove an instance elsewhere. "absent" names features
#: that must NOT be found: a nitramine's N-N is not a hydrazine, and a genuine hydrazine is.
_EXPECTED = {
    "dinitrodiazetidine": {"fg:nitro": 2, "fg:aminal": 2, "absent": ["fg:hydrazine"]},
    "rdx": {"fg:nitro": 3, "fg:aminal": 3, "absent": ["fg:hydrazine"]},
    "hmx": {"fg:nitro": 4, "absent": ["fg:hydrazine"]},
    "tetryl": {"fg:nitro": 4, "absent": ["fg:hydrazine"]},
    "ndma": {"fg:nitroso": 1, "absent": ["fg:hydrazine"]},
    "tnt": {"fg:nitro": 3},
    "petn": {"fg:nitro": 4},
    "methylhydrazine": {"fg:hydrazine": 1},
    "phenylhydrazine": {"fg:hydrazine": 1},
    "nitroguanidine": {"fg:nitro": 1, "fg:guanidine": 1, "absent": ["fg:hydrazine"]},
    "aspirin": {"fg:carboxylic_acid": 1, "fg:carboxylic_ester": 1},
    "haloperidol": {"fg:tertiary_amine": 1, "fg:ketone": 1, "fg:alcohol": 1},
    "imipramine": {"fg:tertiary_amine": 2},
}


@pytest.mark.parametrize("label", sorted(_EXPECTED))
def test_the_expected_instances_are_still_found(sweep, label):
    cell = sweep[f"census_panel/{label}"]
    assert cell["skipped"] == [], "the census panel must not need the tolerant path"
    expected = dict(_EXPECTED[label])
    absent = expected.pop("absent", [])
    for feature, count in expected.items():
        assert cell["counts"].get(feature, 0) == count, (label, feature, cell["counts"])
    for feature in absent:
        assert feature not in cell["counts"], (label, feature)


def test_the_sweep_can_fail(monkeypatch):
    """**A GUARD THAT NEVER FAILED IS UNPROVEN.** The pre-fix `fg:hydrazine` pattern is put
    back, and the strict detector must raise on the panel's nitramine -- which is exactly the
    signal this sweep turns into a failing test."""
    pre_fix = "[NX3;!a;!$([#7][#6]=[O,S,#7]):1]-[NX3;!a;!$([#7][#6]=[O,S,#7]):1]"
    monkeypatch.setitem(sf.SPECS, "fg:hydrazine", sf.FeatureSpec("fg:hydrazine", (pre_fix,)))
    nitramine = Chem.MolFromSmiles("O=[N+]([O-])N1CN([N+](=O)[O-])C1")
    with pytest.raises(sf.UndeclaredChargeState):
        sf.detect_features(nitramine)
    skipped = sf.detect_features_tolerant(nitramine).skipped
    assert {item.feature_id for item in skipped} == {"fg:hydrazine"}
