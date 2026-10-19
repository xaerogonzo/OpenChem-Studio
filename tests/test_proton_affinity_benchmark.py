"""The arithmetic and the judge of the proton-affinity benchmark (`benchmarks/proton_affinity/`, `PREREGISTRATION.md`), on synthetic data. Nothing here runs ORCA: the rule is tested before any job exists, so it cannot be bent to a result."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "proton_affinity"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("proton_affinity_core", "pa_core.py")
judge = _load("proton_affinity_judge", "judge.py")


# --- the proton's terms ------------------------------------------------------------------------------------------------------


def test_the_protons_terms_are_derived_from_the_ideal_gas_and_agree_with_the_published_ones():
    h, s, g = core.proton_terms()

    assert h * core.HARTREE_TO_KCAL == pytest.approx(1.4812, abs=1e-3)  # (5/2) RT
    assert s * core.HARTREE_J * core.N_A / 4.184 == pytest.approx(26.012, abs=2e-3)  # cal/(mol K)
    assert g * core.HARTREE_TO_KCAL == pytest.approx(-6.274, abs=2e-3)
    # Moser, Range and York 2010 print 1.48, 26.02 and -6.28 for the same standard state
    assert abs(h * core.HARTREE_TO_KCAL - 1.48) < 0.01 and abs(g * core.HARTREE_TO_KCAL + 6.28) < 0.01


def test_the_entropy_of_the_proton_depends_on_the_pressure_and_the_temperature_the_way_sackur_tetrode_says():
    _h1, s1, _g1 = core.proton_terms(pressure=core.ATM_PA)
    _h2, s2, _g2 = core.proton_terms(pressure=core.ATM_PA / 10.0)
    assert (s2 - s1) * core.HARTREE_J == pytest.approx(core.K_B * math.log(10.0), rel=1e-9)  # ten times lower pressure: R ln 10 more entropy
    h_hot, _s, _g = core.proton_terms(temperature=596.3)
    assert h_hot == pytest.approx(2.0 * core.proton_terms()[0], rel=1e-9)


def test_pa_and_gb_are_the_sums_the_definitions_say():
    h_p, _s, g_p = core.proton_terms()
    # a base with H = -100.0 and an acid with H = -100.26 Eh
    assert core.proton_affinity(-100.0, -100.26) == pytest.approx(0.26 + h_p)
    assert core.gas_basicity(-100.0, -100.25) == pytest.approx(0.25 + g_p)
    # water's smoke run (M062X/def2-TZVPD): H = -76.40397512, H3O+ = -76.66319385 -> 686.8 kJ/mol
    assert core.proton_affinity(-76.40397512, -76.66319385) * core.HARTREE_TO_KCAL * core.KCAL_TO_KJ == pytest.approx(686.78, abs=0.05)


def test_the_symmetry_correction_is_rt_ln_of_the_ratio_and_zero_when_they_agree():
    assert core.symmetry_correction_eh(3, 3) == 0.0
    assert core.symmetry_correction_eh(3, 1) * core.HARTREE_TO_KCAL == pytest.approx(0.5925 * math.log(3.0), abs=2e-3)  # RT = 0.5925 kcal/mol at 298.15 K
    assert core.symmetry_correction_eh(2, 4) == pytest.approx(-core.symmetry_correction_eh(4, 2))
    with pytest.raises(ValueError):
        core.symmetry_correction_eh(0, 1)


# --- the symmetry number ---------------------------------------------------------------------------------------------------


def _molecule(smiles: str, seed: int = 7):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol, maxIters=5000)
    return mol, mol.GetConformer().GetPositions()


def _ideal(smiles: str, coordinates: list[list[float]]):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    return mol, np.array(coordinates, dtype=float)


def test_the_symmetry_number_of_small_molecules():
    water = _ideal("O", [[0, 0, 0.117], [0, 0.757, -0.469], [0, -0.757, -0.469]])
    ammonia = _ideal("N", [[0, 0, 0.116], [0, 0.940, -0.272], [0.814, -0.470, -0.272], [-0.814, -0.470, -0.272]])
    hydronium = _ideal("[OH3+]", [[0, 0, 0.0], [0, 0.95, -0.30], [0.8227, -0.475, -0.30], [-0.8227, -0.475, -0.30]])
    assert core.rotational_symmetry_number(*water) == 2
    assert core.rotational_symmetry_number(*ammonia) == 3
    assert core.rotational_symmetry_number(*hydronium) == 3


def test_a_slightly_distorted_hydronium_still_counts_as_c3v_which_is_the_orca_defect_this_corrects():
    """ORCA called a H3O+ that was C3v within 0.001 A 'Cs, symmetry number 1': the geometry here is its printed one (O-H 0.9807 A, three equal)."""
    mol = Chem.AddHs(Chem.MolFromSmiles("[OH3+]"))
    xyz = np.array([[-0.000000, 0.002340, -0.000228], [-0.000000, 0.946369, -0.266117], [0.817489, -0.469355, -0.266828], [-0.817489, -0.469355, -0.266828]])

    assert core.rotational_symmetry_number(mol, xyz) == 3


@pytest.mark.parametrize(
    "smiles, expected",
    [("C", 12), ("c1ccccc1", 12), ("CO", 1), ("C=C", 4), ("C=O", 2), ("CC(C)=O", 2), ("c1ccncc1", 2), ("[C-]#[O+]", 1), ("C#N", 1), ("CC#N", 3)],
)
def test_the_symmetry_number_of_relaxed_molecules(smiles, expected):
    mol, xyz = _molecule(smiles)

    assert core.rotational_symmetry_number(mol, xyz, tolerance=0.1) == expected


def test_a_reflection_is_not_a_rotation():
    """CHFClBr's graph has no automorphism but identity; a molecule whose graph symmetry needs a mirror (the H atoms of a bent chiral-free case) must not count it."""
    mol, xyz = _molecule("CC(F)(Cl)Br")
    assert core.rotational_symmetry_number(mol, xyz, tolerance=0.1) == 1


def test_coordinates_that_do_not_match_the_molecule_are_refused():
    mol, xyz = _molecule("O")
    with pytest.raises(ValueError):
        core.rotational_symmetry_number(mol, xyz[:2])


# --- the dataset -------------------------------------------------------------------------------------------------------------


def test_the_nist_file_holds_the_twenty_eight_chosen_bases_with_both_values():
    data = json.loads((_DIRECTORY / "nist_values.json").read_text(encoding="utf-8"))["bases"]

    assert len(data) == 28 and all(b["pa_kj"] and b["gb_kj"] for b in data)
    records = [{"name": b["name"], "pa_ref_kj": b["pa_kj"], "gb_ref_kj": b["gb_kj"]} for b in data]
    low = sorted(r["name"] for r in judge.stratum(records, low=True))
    assert low == ["benzene", "carbon monoxide", "ethene", "formaldehyde", "hydrogen cyanide", "hydrogen sulfide", "water"]  # the seven below propene, by the REFERENCE PA (methanol: PA 754.3, GB 724.5, is above)
    assert len(judge.stratum(records, low=False)) == 21


# --- the judge ---------------------------------------------------------------------------------------------------------------


def _bases(n_high=21, n_low=7, error=0.0):
    """21 bases above propene and 7 below, each computed value off by `error` kcal/mol from the reference."""
    records = []
    for i in range(n_high + n_low):
        ref_kj = 800.0 + i if i < n_high else 700.0 - i
        records.append({"name": f"b{i}", "pa_ref_kj": ref_kj, "gb_ref_kj": ref_kj - 30.0,
                        "pa_kcal": ref_kj / 4.184 + error, "gb_kcal": (ref_kj - 30.0) / 4.184 + error})
    return records


def test_a_perfect_calculation_passes_both_arms_for_both_quantities():
    for arm in ("primary", "secondary"):
        result = judge.judge(_bases(), arm)
        assert result["pa"]["verdict"] == judge.PASS and result["gb"]["verdict"] == judge.PASS


def test_the_arms_have_different_mean_error_limits():
    records = _bases(error=2.2)  # a steady +2.2 kcal/mol: inside the primary limit (2.5), outside the secondary's (2.0) and the signed limit (1.5)
    assert judge.judge(records, "primary")["pa"]["verdict"] == judge.PARTIAL  # MSE 2.2 exceeds 1.5: not a PASS, MAE 2.2 <= 4: PARTIAL
    zero_bias = [dict(r, pa_kcal=r["pa_kcal"] + (2.2 if i % 2 else -2.2)) for i, r in enumerate(_bases())]  # alternating +-2.2 around zero: MAE 2.2, MSE ~0
    assert judge.judge(zero_bias, "primary")["pa"]["verdict"] == judge.PASS
    assert judge.judge(zero_bias, "secondary")["pa"]["verdict"] == judge.PARTIAL


def test_one_large_error_stops_a_pass_a_large_mean_fails_and_a_large_signed_mean_is_partial():
    one_big = _bases()
    one_big[3]["pa_kcal"] += 5.5
    assert judge.judge(one_big, "primary")["pa"]["verdict"] == judge.PARTIAL  # MAE small but one error above 5
    assert judge.judge(_bases(error=4.5), "primary")["pa"]["verdict"] == judge.FAIL  # MAE 4.5 > 4
    assert judge.judge(_bases(error=3.0), "primary")["pa"]["verdict"] == judge.PARTIAL


def test_the_low_basicity_stratum_is_reported_and_can_never_decide():
    records = _bases()
    for r in records[21:]:
        r["pa_kcal"] += 40.0  # the seven low bases are wildly wrong
        r["gb_kcal"] += 40.0
    result = judge.judge(records, "primary")

    assert result["pa"]["verdict"] == judge.PASS and result["gb"]["verdict"] == judge.PASS
    assert result["pa"]["low"].mae == pytest.approx(40.0) and result["pa"]["all"].count == 28 and result["pa"]["deciding"].count == 21


def test_more_than_two_missing_in_the_deciding_stratum_is_not_evaluable_and_two_is_not():
    records = _bases()
    for r in records[:2]:
        r["pa_kcal"] = None
    assert judge.judge(records, "primary")["pa"]["verdict"] == judge.PASS and judge.judge(records, "primary")["pa"]["deciding"].missing == 2
    records[2]["pa_kcal"] = None
    assert judge.judge(records, "primary")["pa"]["verdict"] == judge.NOT_EVALUABLE
    assert judge.judge(records, "primary")["gb"]["verdict"] == judge.PASS, "PA missing does not take GB with it"


def test_missing_low_bases_do_not_matter_and_pa_and_gb_are_judged_apart():
    records = _bases()
    for r in records[21:]:
        r["pa_kcal"] = None
    records_gb = [dict(r, gb_kcal=r["gb_kcal"] + 6.0) for r in records]  # GB off by 6 everywhere
    result = judge.judge(records_gb, "primary")

    assert result["pa"]["verdict"] == judge.PASS
    assert result["gb"]["verdict"] == judge.FAIL


def test_the_thresholds_are_the_approved_literals():
    assert (judge.MAE_PASS, judge.MAX_ERROR, judge.MSE_LIMIT, judge.MAE_PARTIAL, judge.MISSING_ALLOWED, judge.LOW_BASICITY_KJ) == (
        {"primary": 2.5, "secondary": 2.0}, 5.0, 1.5, 4.0, 2, 751.6)
