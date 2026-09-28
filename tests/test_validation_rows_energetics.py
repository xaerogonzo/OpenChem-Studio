"""benchmarks/thermophysical/validation_rows_energetics.py -- the first real ValidationRow instances
built in this project (previously only tools/validation_rows.py's own synthetic-row tests exercised the
schema). Guards the two things that matter for this data: every row is admissible to the common
evaluation set it claims, and the leakage machinery correctly separates orca_atom_equivalents's fit
population from the compounds it was actually checked against.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vr():
    return _load("validation_rows", ROOT / "tools" / "validation_rows.py")


@pytest.fixture(scope="module")
def vre(vr):
    return _load("validation_rows_energetics", ROOT / "benchmarks" / "thermophysical" / "validation_rows_energetics.py")


def test_eight_melting_point_rows_built(vre):
    """RDX/HMX/TNT/PETN (development) plus tetryl/nitroguanidine/ammonium_nitrate/nitroglycerin
    (selection) -- TATB (unreached estimate) and dinitrodiazetidine (no value found) correctly excluded."""
    ids = {row.row_id for row in vre.TM_ROWS}
    assert ids == {
        "tm_rdx", "tm_hmx", "tm_tnt", "tm_petn",
        "tm_tetryl", "tm_nitroguanidine", "tm_ammonium_nitrate", "tm_nitroglycerin",
    }
    assert "tm_tatb" not in ids
    assert "tm_dinitrodiazetidine" not in ids


def test_every_tm_row_is_admissible_to_both_the_common_and_melting_point_sets(vr, vre):
    for row in vre.TM_ROWS:
        assert vr.admit_to_common_set(row) is None, row.row_id
        assert vr.admit_to_melting_point_set(row) is None, row.row_id


def test_every_hf_row_is_admissible_to_the_common_set(vr, vre):
    for row in vre.HF_ROWS:
        assert vr.admit_to_common_set(row) is None, row.row_id


def test_rdx_carries_two_independent_klapotke_readings(vre):
    """Not a bug -- Klapoetke states RDX's condensed DfH twice (p.232 prose, Table 9.6), and both are
    kept rather than silently picking one; see docs/research/literature.toml's mathieu2018_apc entry
    for why the two are close once read in consistent units, not a real contradiction."""
    rdx_rows = [row for row in vre.HF_ROWS if row.smiles.startswith("O=[N+]([O-])N1CN(CN(C1)")]
    assert {row.row_id for row in rdx_rows} == {"hf_rdx_solid_prose", "hf_rdx_solid_table96"}
    values = sorted(row.value for row in rdx_rows)
    assert values == [66.6, 85.0]


def test_development_rows_are_exactly_the_seven_orca_calibration_compounds(vre):
    development_hf = {row.row_id for row in vre.HF_ROWS if row.partition == "development"}
    assert development_hf == {
        "hf_dimethylnitramine_gas", "hf_methane_gas", "hf_ammonia_gas", "hf_benzene_gas",
        "hf_methanol_gas", "hf_nitromethane_gas", "hf_methyl_nitrate_gas",
    }


def test_exclude_leaked_separates_the_fit_population_from_what_was_checked(vr, vre):
    """The concrete exercise of exclude_leaked this project has been missing: RDX/HMX/PETN/TNT (checked
    against orca_atom_equivalents's combined route) must NOT be excluded, and the seven compounds that
    fit its atom equivalents (dimethylnitramine included) MUST be -- proving the population built from
    HF_ROWS's own partition field, not a hand-copied list, actually discriminates the two groups."""
    populations = {("orca_atom_equivalents", "enthalpy_formation_gas"): vre.orca_atom_equivalents_fit_population()}
    gas_rows = [row for row in vre.HF_ROWS if row.property == "enthalpy_formation_gas"]
    kept, excluded = vr.exclude_leaked(gas_rows, "orca_atom_equivalents", populations)

    assert {row.row_id for row in excluded} == {row.row_id for row in gas_rows}
    assert kept == []


def test_exclude_leaked_raises_for_a_solid_phase_property_no_population_was_ever_recorded_for(vr, vre):
    """orca_atom_equivalents was never fitted on ANY solid-phase value (the combined route only checks
    against them) -- exclude_leaked must refuse to guess, not silently call them clean."""
    populations = {("orca_atom_equivalents", "enthalpy_formation_gas"): vre.orca_atom_equivalents_fit_population()}
    solid_rows = [row for row in vre.HF_ROWS if row.property == "enthalpy_formation_solid"]
    with pytest.raises(vr.UnknownFitPopulation):
        vr.exclude_leaked(solid_rows, "orca_atom_equivalents", populations)
