"""The held-out size panel of the proton-affinity benchmark (`benchmarks/proton_affinity/PREREGISTRATION_HELDOUT.md`). Nothing here runs ORCA: the set, the freeze and the stricter missing rule are tested before any job exists."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from rdkit import Chem

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "proton_affinity"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(_DIRECTORY))
try:
    heldout = _load("proton_affinity_heldout", "heldout.py")
    freeze = _load("proton_affinity_freeze_heldout", "freeze_heldout.py")
    judge = _load("proton_affinity_judge", "judge.py")
    run = _load("proton_affinity_run", "run_pa.py")
finally:
    sys.path.remove(str(_DIRECTORY))

BASES = heldout.bases()
FIRST = json.loads((_DIRECTORY / "nist_values.json").read_text(encoding="utf-8"))["bases"]


def test_the_panel_is_six_named_bases_of_eleven_to_twenty_heavy_atoms():
    assert [row["name"] for row in BASES] == [
        "guanine",
        "camphor",
        "benzoquinuclidine",
        "acridine",
        "anthracene",
        "phenanthrene",
    ]
    assert heldout.MISSING_ALLOWED == 1
    for row in BASES:
        mol = Chem.AddHs(Chem.MolFromSmiles(row["smiles"]))
        heavy = sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() > 1)
        assert heavy == row["heavy_atoms"]
        assert heldout.MIN_HEAVY <= heavy <= heldout.MAX_HEAVY
        assert {atom.GetSymbol() for atom in mol.GetAtoms()} <= heldout.SUPPORTED_ELEMENTS
        assert row["pa_kj"] > judge.LOW_BASICITY_KJ and row["gb_kj"] < row["pa_kj"]


def test_none_of_the_held_out_bases_is_one_the_first_run_measured():
    assert {row["name"] for row in BASES}.isdisjoint(heldout.first_run_names())
    assert {row["cas"] for row in BASES}.isdisjoint({row["cas"] for row in FIRST})
    assert len({row["cas"] for row in BASES}) == 6


def test_the_original_runner_still_has_only_the_twenty_eight():
    assert set(run.BASES) == {row["name"] for row in FIRST}
    assert len(run.BASES) == 28


def test_every_held_out_base_has_at_least_one_protonation_site_under_the_original_rule():
    previous = dict(run.BASES)
    run.BASES = heldout.smiles()
    try:
        for name in run.BASES:
            assert run.candidate_sites(run.base_molecule(name)), name
    finally:
        run.BASES = previous


def test_one_missing_deciding_base_is_still_evaluable_and_two_are_not():
    records = [
        {
            "name": row["name"],
            "pa_ref_kj": row["pa_kj"],
            "gb_ref_kj": row["gb_kj"],
            "pa_kcal": row["pa_kj"] / 4.184,
            "gb_kcal": row["gb_kj"] / 4.184,
        }
        for row in BASES
    ]
    records[0]["pa_kcal"] = None
    assert judge.judge(records, "primary", missing_allowed=heldout.MISSING_ALLOWED)["pa"]["verdict"] == judge.PASS
    records[1]["pa_kcal"] = None
    assert judge.judge(records, "primary", missing_allowed=heldout.MISSING_ALLOWED)["pa"]["verdict"] == judge.NOT_EVALUABLE
    assert judge.judge(records, "primary")["pa"]["verdict"] == judge.PASS, "the original allowance of two is unchanged"


def test_the_heldout_freeze_matches_the_hashed_files():
    frozen = json.loads((_DIRECTORY / "freeze_heldout.json").read_text(encoding="utf-8"))
    assert freeze.problems(frozen) == []
