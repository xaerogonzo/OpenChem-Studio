"""benchmarks/thermophysical/compare_enthalpies.py -- the consolidation Track 3's own modules never got:
every enthalpy model this session reproduced or built, run over one shared corpus, stratified. Locks in
one genuinely new finding this wiring surfaced: TNT's mathieu2018_apc + keshavarz2010 combined route
(-76.8 kJ/mol) was never computed standalone before -- it lands within 9.7 kJ/mol of measurement,
independently corroborating keshavarz_nitroaromatic2009's own direct-model result (-1.7 kJ/mol) via a
completely different computational route.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ce():
    path = ROOT / "benchmarks" / "thermophysical" / "compare_enthalpies.py"
    spec = importlib.util.spec_from_file_location("compare_enthalpies", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rows(ce):
    return {row["name"]: row for row in ce.compare()}


def test_five_compound_corpus(rows):
    assert set(rows) == {"RDX", "HMX", "PETN", "TNT", "TATB"}


def test_rdx_hmx_petn_combined_routes_match_this_sessions_recorded_values(rows):
    """Locks in the numbers recorded in literature.toml -- this module is a NEW wiring around the same
    computation, and must reproduce it exactly, not approximately. The APC-route numbers are unaffected
    by orca_atom_equivalents and unchanged from before. The ORCA-route numbers were RE-RUN fresh
    2026-09-29 after discovering the previous ones were computed at different, undocumented points in an
    RDKit-version drift across sessions -- see orca_atom_equivalents.py's module docstring RETRACTED
    note. They reflect the fresh, internally-consistent 9-point calibration set, not the old
    (drift-affected) one."""
    assert rows["RDX"]["combined_solid_hf_apc_kj_mol"] == pytest.approx(50.1, abs=0.2)
    assert rows["RDX"]["combined_solid_hf_orca_kj_mol"] == pytest.approx(123.3, abs=0.2)
    assert rows["HMX"]["combined_solid_hf_apc_kj_mol"] == pytest.approx(66.0, abs=0.2)
    assert rows["HMX"]["combined_solid_hf_orca_kj_mol"] == pytest.approx(161.3, abs=0.2)
    assert rows["PETN"]["combined_solid_hf_apc_kj_mol"] == pytest.approx(-482.0, abs=0.2)
    assert rows["PETN"]["combined_solid_hf_orca_kj_mol"] == pytest.approx(-451.4, abs=0.2)


def test_tnts_apc_combined_route_was_never_computed_standalone_before_this_module(rows):
    """The new finding this consolidation surfaced: TNT's mathieu2018_apc + keshavarz2010 combined
    route independently corroborates keshavarz_nitroaromatic2009's direct model, via unrelated
    computational paths that were never run against each other until this module existed."""
    apc_route = rows["TNT"]["combined_solid_hf_apc_kj_mol"]
    direct_model = rows["TNT"]["cond_hf_direct_kj_mol"]
    measured = rows["TNT"]["measured_solid_hf_kj_mol"][0]

    assert apc_route == pytest.approx(-76.8, abs=0.2)
    assert direct_model == pytest.approx(-68.8, abs=0.2)
    assert abs(apc_route - measured) <= 21.0
    assert abs(direct_model - measured) <= 21.0


def test_orca_route_coverage_is_limited_to_the_three_compounds_actually_run_through_orca(rows):
    """orca_atom_equivalents's combined route must not silently appear for TNT/TATB -- no ORCA job
    exists for either, and this module must say so rather than fabricate one."""
    assert rows["TNT"]["combined_solid_hf_orca_kj_mol"] is None
    assert rows["TATB"]["combined_solid_hf_orca_kj_mol"] is None
    assert rows["RDX"]["combined_solid_hf_orca_kj_mol"] is not None


def test_direct_model_coverage_is_limited_to_the_nitroaromatic_stratum(rows):
    """keshavarz_nitroaromatic2009 covers TNT and TATB only -- RDX/HMX/PETN must show None, not a
    fabricated number or a silently-wrong application outside the model's declared domain."""
    assert rows["TNT"]["cond_hf_direct_kj_mol"] is not None
    assert rows["TATB"]["cond_hf_direct_kj_mol"] is not None
    for name in ("RDX", "HMX", "PETN"):
        assert rows[name]["cond_hf_direct_kj_mol"] is None


def test_tatb_has_no_measured_comparator(rows):
    """No measured condensed Hf for TATB was ever found and verified this session -- the report must
    show an empty measured list, not silently omit the row or invent a value."""
    assert rows["TATB"]["measured_solid_hf_kj_mol"] == []


def test_stratified_report_keeps_coverage_and_accuracy_separate_per_model(ce, rows):
    report = ce.stratified_report(list(rows.values()))
    assert set(report) == {"nitramine", "nitrate_ester", "nitroaromatic"}
    # nitramine: RDX + HMX, both scored against their first (p.232 prose) measured reading
    assert report["nitramine"]["total"] == 2
    assert len(report["nitramine"]["apc_errors"]) == 2
    assert len(report["nitramine"]["direct_errors"]) == 0  # not a nitroaromatic-model stratum
    # nitroaromatic: TNT scored (measured value exists), TATB not (no measured value)
    assert report["nitroaromatic"]["total"] == 2
    assert len(report["nitroaromatic"]["apc_errors"]) == 1
    assert len(report["nitroaromatic"]["direct_errors"]) == 1
