"""The ring-locant sweep tool (naming round 13): its attachable-site predicate, the cases it builds, the frozen
population and the report. The namer and OPSIN are replaced where a test is about wiring; one test names real
structures with the real engine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_ring_locant_sweep as sweep  # noqa: E402


def _ring(smiles: str, **extra) -> dict:
    return {**sweep.describe_ring(smiles, {"name": smiles, **extra}), "smiles": smiles}


def test_only_a_free_hydrogen_carbon_that_is_not_a_fusion_atom_is_attachable():
    thiophene = _ring("c1ccsc1")
    assert len(thiophene["sites"]) == 4 and thiophene["skipped"] == {"heteroatom": [3]}
    naphthalene = _ring("c1ccc2ccccc2c1")
    assert len(naphthalene["sites"]) == 8 and sorted(naphthalene["skipped"]) == ["fusion_atom"]


def test_a_skipped_atom_is_recorded_with_its_reason_and_never_dropped():
    pyrrole = _ring("c1cc[nH]c1")
    assert pyrrole["skipped"] == {"heteroatom": [3]}
    assert sorted(pyrrole["sites"] + pyrrole["skipped"]["heteroatom"]) == [0, 1, 2, 3, 4]


def test_a_symmetry_equivalent_second_position_is_tagged_pair_equivalent():
    """1,3,4-thiadiazole's C2 and C5 are equivalent: the shape the census found wrong."""
    ring = _ring("c1nncs1")
    cases, bad = sweep.build_cases(0, ring)
    assert not bad
    kinds = {(c["site"], c["other"]): c["variant"] for c in cases}
    assert kinds[(0, None)] == "single"
    assert "pair_equivalent" in kinds.values()


def test_every_built_case_is_an_acetamide_with_the_stated_extra_methyl():
    from rdkit import Chem

    cases, _ = sweep.build_cases(0, _ring("c1ccccc1"))
    assert cases
    pattern = Chem.MolFromSmarts("[NX3;H1]C(=O)[CH3]")
    for case in cases:
        mol = Chem.MolFromSmiles(case["smiles"])
        assert mol.HasSubstructMatch(pattern)
        assert mol.GetNumHeavyAtoms() == 6 + 4 + (1 if case["other"] is not None else 0)


def test_the_second_substituent_is_capped_per_site():
    cases, _ = sweep.build_cases(0, _ring("c1ccc2ccccc2c1"))
    per_site = [sum(1 for c in cases if c["site"] == s and c["other"] is not None) for s in range(8)]
    assert max(per_site) <= sweep.SECOND_SUBSTITUENT_CAP


def test_a_ring_with_no_attachable_site_builds_no_case():
    assert sweep.build_cases(0, _ring("c1ccsc1"))[0] and sweep.build_cases(0, {"smiles": "n1cccc1", "sites": []}) == ([], [])


def test_table_state_says_full_only_when_every_attachable_site_has_a_locant():
    site_ring = {"has_atom_locants": True, "sites": [0, 1], "locant_atoms": [0, 1, 5]}
    assert sweep.table_state(site_ring) == "full"
    assert sweep.table_state({**site_ring, "locant_atoms": [0]}) == "partial"
    assert sweep.table_state({"has_atom_locants": False, "sites": [0], "locant_atoms": []}) == "table_less"


def test_the_committed_population_matches_the_live_curated_table():
    """The denominator is frozen: a change to the curated table must show up as a regenerated, reviewed artifact."""
    stored = json.loads(sweep.POPULATION.read_text(encoding="utf-8"))
    assert stored["population_sha256"] == sweep.build_population()["population_sha256"]
    assert stored["n_rings"] == len(sweep.curated_rings())


def test_a_stale_population_is_refused(monkeypatch, tmp_path):
    stale = tmp_path / "p.json"
    stale.write_text(json.dumps({"population_sha256": "0" * 64}), encoding="utf-8")
    monkeypatch.setattr(sweep, "POPULATION", stale)
    with pytest.raises(SystemExit):
        sweep.load_population()


def test_the_report_separates_table_states_and_says_the_oracle_is_structural(monkeypatch):
    pop = {
        "second_substituent_cap": 3,
        "rings": [
            {"name": "A", "smiles": "a", "has_atom_locants": False, "sites": [0], "locant_atoms": [], "skipped": {}},
            {"name": "B", "smiles": "b", "has_atom_locants": True, "sites": [0], "locant_atoms": [0], "skipped": {"fusion_atom": [1, 2]}},
        ],
    }
    result = {
        "cases": [
            {"ring": 0, "variant": "pair_equivalent", "outcome": "wrong_structure"},
            {"ring": 0, "variant": "single", "outcome": "structurally_correct"},
            {"ring": 1, "variant": "single", "outcome": "structurally_correct"},
        ],
        "unbuildable": [], "timing_seconds": {"build": 0, "naming": 0, "read_back": 0, "total": 0},
    }
    text = "\n".join(sweep.summarise(pop, result))
    assert "table_less" in text and "full" in text and "fusion_atom 2" in text
    assert "pair_equivalent" in text and "STRUCTURAL" in text


def test_the_outcome_map_covers_every_census_scan_class():
    from naming_census_scan import CLASSES

    assert set(sweep.OUTCOME_OF) == set(CLASSES)


def test_run_names_real_structures_end_to_end_without_a_jre():
    pop = {"rings": [_ring("c1ccccc1")], "second_substituent_cap": 3}
    result = sweep.run(pop, names_only=True)
    names = {c["name"] for c in result["cases"] if c["variant"] == "single"}
    assert names == {"N-phenylacetamide"} or all("acetamide" in n or "acetanilide" in n or "acetamido" in n for n in names)
