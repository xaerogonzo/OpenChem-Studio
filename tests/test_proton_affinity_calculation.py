"""`openchem.chem.proton_affinity`: the chemistry of the PA/GB calculation, held to the benchmark that measured it.

The library is a port of `benchmarks/proton_affinity/` (PASS on 2026-10-20), so the tests compare it with the benchmark's own runner and with the benchmark's committed job records instead of restating expected numbers:
the structures it builds, the ORCA input it writes, what it reads from an output, and the PA and GB it selects from the 77 recorded jobs must be the benchmark's, to the digit.
"""
from __future__ import annotations

import functools
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from openchem.chem import proton_affinity as pa

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "proton_affinity"
_FIXTURES = Path(__file__).parent / "fixtures" / "orca"


def _load_runner():
    # run_pa imports `judge` and `pa_core` by their plain names from its own directory
    sys.path.insert(0, str(_DIRECTORY))
    try:
        spec = importlib.util.spec_from_file_location("proton_affinity_run_for_library", _DIRECTORY / "run_pa.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["proton_affinity_run_for_library"] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_DIRECTORY))
    return module


run = _load_runner()
RECORDS = [json.loads(line) for line in (_DIRECTORY / "artifacts" / "primary" / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
WATER = (_FIXTURES / "pa_water_optfreq.out").read_text(encoding="utf-8")
HYDRONIUM = (_FIXTURES / "pa_h3o_optfreq.out").read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _benchmark_structures() -> list[dict]:
    return run.build_structures()


# --- the same protocol ------------------------------------------------------------------------------------------------------


def test_the_keywords_and_limits_are_the_benchmarks():
    assert pa.HEADER == run.HEADER
    for name in ("SEED", "CONFORMERS", "DEDUPE_RMSD", "KEEP", "KEEP_WINDOW_KCAL", "IMAGINARY_CM"):
        assert getattr(pa, name) == getattr(run, name), name


@pytest.mark.parametrize("name", ["water", "ammonia", "pyrimidine", "aniline", "formamide", "carbon monoxide", "benzene", "acetic acid", "tetrahydrofuran"])
def test_the_structures_are_the_benchmarks_for_the_same_base(name):
    mine = pa.build_structures(pa.base_from_smiles(run.BASES[name]), key=name)
    theirs = [s for s in _benchmark_structures() if s["base"] == name]
    assert [s["id"] for s in mine] == [s["id"] for s in theirs]
    for a, b in zip(mine, theirs):
        assert a["symbols"] == b["symbols"] and a["charge"] == b["charge"]
        assert np.allclose(a["coordinates"], b["coordinates"], atol=1e-9)


def test_the_orca_input_is_the_benchmarks_with_and_without_the_retry():
    structure = pa.build_structures(pa.base_from_smiles("O"), key="water")[1]
    for retry in (False, True):
        assert pa.orca_input(structure, 4, retry) == run.orca_input(structure, 4, retry)
    assert "Calc_Hess true" in pa.orca_input(structure, 4, True) and "Calc_Hess" not in pa.orca_input(structure, 4, False)


@pytest.mark.parametrize("text", [WATER, HYDRONIUM], ids=["water", "hydronium"])
def test_an_output_is_read_as_the_benchmark_reads_it(text):
    assert pa.parse_output(text) == run.parse_output(text)


def test_the_proton_terms_are_the_derived_ones():
    h, s, g = pa.proton_terms()
    assert h * pa.HARTREE_TO_KCAL == pytest.approx(1.4812, abs=1e-3)
    assert s * pa.HARTREE_TO_KCAL * 1000 == pytest.approx(26.012, abs=1e-3)  # cal/(mol K)
    assert g * pa.HARTREE_TO_KCAL == pytest.approx(-6.274, abs=1e-3)


def test_orcas_symmetry_number_for_h3o_plus_is_overridden_by_the_true_one():
    parsed = pa.parse_output(HYDRONIUM)
    structure = {"role": "ion", "base": "water"}
    done = pa.finish(structure, parsed, pa.base_from_smiles("O"))
    assert done["sigma_orca"] == 1 and done["sigma_true"] == 3  # ORCA called the C3v ion Cs; the proper rotations are the identity and the two turns
    assert done["symmetry_correction"] * pa.HARTREE_TO_KCAL == pytest.approx(0.0019872 * 298.15 * math.log(3), abs=1e-4)  # RT ln 3 with R = 1.9872 cal/(mol K): 0.651 kcal/mol
    assert done["site_assigned"] == 0  # the oxygen gained the hydrogen


# --- the benchmark's own records give the benchmark's numbers ------------------------------------------------------------------


def _records_of(name: str) -> list[dict]:
    return [r for r in RECORDS if r["base"] == name]


@pytest.mark.parametrize("name", sorted(run.BASES))
def test_selecting_from_the_recorded_jobs_gives_the_benchmarks_pa_and_gb(name):
    result = pa.resolve(pa.base_from_smiles(run.BASES[name]), _records_of(name))
    for quantity, mine in (("pa", result.pa_kcal), ("gb", result.gb_kcal)):
        theirs = run.select(run.accepted(_records_of(name)), name, quantity)
        if theirs is None:
            assert mine is None
        else:
            assert mine == pytest.approx(theirs["value_eh"] * pa.HARTREE_TO_KCAL, abs=1e-9), (name, quantity)
    if result.pa_kcal is not None:
        assert result.pa_site == run.select(run.accepted(_records_of(name)), name, "pa")["site_atom"]


def test_the_values_in_the_benchmark_report_are_reproduced_in_kilojoules():
    # report.txt of the committed run: ammonia PA 844.5 and GB 810.1 kJ/mol, benzene 741.3 and 717.1
    ammonia = pa.resolve(pa.base_from_smiles("N"), _records_of("ammonia"))
    benzene = pa.resolve(pa.base_from_smiles("c1ccccc1"), _records_of("benzene"))
    assert (ammonia.pa_kj, ammonia.gb_kj) == (pytest.approx(844.5, abs=0.05), pytest.approx(810.1, abs=0.05))
    assert (benzene.pa_kj, benzene.gb_kj) == (pytest.approx(741.3, abs=0.05), pytest.approx(717.1, abs=0.05))


def test_water_has_no_value_because_its_ion_kept_an_imaginary_mode_and_the_reason_is_named():
    result = pa.resolve(pa.base_from_smiles("O"), _records_of("water"))
    assert result.pa_kcal is None and result.gb_kcal is None
    assert "water|ion|lone_pair0|0" in result.dropped  # the planar H3O+ saddle point, -601.6 cm-1 after the Calc_Hess re-run


def test_a_base_with_several_sites_gets_a_site_table_whose_winner_is_the_reported_site():
    result = pa.resolve(pa.base_from_smiles("Nc1ccccc1"), _records_of("aniline"))
    assert len(result.sites) >= 2
    chosen = [row for row in result.sites if row.chosen_pa]
    assert len(chosen) == 1 and chosen[0].atom == result.pa_site and chosen[0].element == "N"
    assert chosen[0].pa_kcal == pytest.approx(result.pa_kcal, abs=1e-9)
    assert all(row.pa_kcal <= chosen[0].pa_kcal + 1e-9 for row in result.sites)


# --- what it will not compute ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smiles, reason",
    [
        ("CC[NH3+]", "charged"),
        ("[CH3]", "radical"),
        ("CCl", "Cl"),
        ("O.O", "more than one component"),
        ("CCCCCCCCCCCO", "heavy atoms"),
        ("[H][H]", "no heavy atom"),
        ("C", "no protonation site"),
        ("[O-]C(=O)C", "charged"),
    ],
)
def test_a_base_outside_what_the_benchmark_measured_is_refused_with_its_reason(smiles, reason):
    with pytest.raises(pa.OutOfScope, match=reason):
        pa.base_from_smiles(smiles)


def test_carbon_monoxide_is_the_one_charge_separated_structure_that_is_allowed():
    assert pa.base_from_smiles("[C-]#[O+]") is not None


def test_unreadable_smiles_is_refused_not_raised_as_a_parser_error():
    with pytest.raises(pa.OutOfScope, match="could not be read"):
        pa.base_from_smiles("not a molecule (")
