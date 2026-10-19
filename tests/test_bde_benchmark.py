"""The arithmetic, the judge and the reference data of the bond-dissociation benchmark (`benchmarks/bde/`, `docs/BDE_DESIGN.md`), on synthetic data. Nothing here runs ORCA: the rule is tested before any job exists, so it cannot be bent to a result."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from rdkit import Chem

_DIRECTORY = Path(__file__).parent.parent / "benchmarks" / "bde"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _DIRECTORY / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("bde_core", "bde_core.py")
judge = _load("bde_judge", "judge.py")
REFERENCE = json.loads((_DIRECTORY / "reference_values.json").read_text(encoding="utf-8"))["bonds"]


# --- the arithmetic ---------------------------------------------------------------------------------------------------------


def test_the_hydrogen_atoms_enthalpy_adds_five_halves_kt_to_its_energy():
    assert (core.hydrogen_atom_enthalpy(-0.5) + 0.5) * core.HARTREE_TO_KCAL == pytest.approx(1.4812, abs=1e-3)  # (5/2) RT at 298.15 K
    assert (core.hydrogen_atom_enthalpy(-0.5, temperature=0.0) + 0.5) == 0.0


def test_the_bond_dissociation_enthalpy_is_radical_plus_atom_minus_parent():
    dh = core.bond_dissociation_enthalpy(h_parent=-40.4, h_radical=-39.7, h_hydrogen=-0.49)

    assert dh == pytest.approx(0.21)
    assert dh * core.HARTREE_TO_KCAL == pytest.approx(131.78, abs=0.01)
    # swapping the parent and the radical flips the sign: a bond that costs energy to break must come out positive
    assert core.bond_dissociation_enthalpy(-39.7, -40.4, -0.49) == pytest.approx(-1.19)


@pytest.mark.parametrize("s2, flagged", [(0.75, False), (0.79, False), (0.81, True), (1.2, True)])
def test_a_doublet_is_flagged_when_its_spin_exceeds_the_clean_value_by_more_than_the_limit(s2, flagged):
    assert core.spin_contaminated(s2) is flagged


def test_a_radical_start_is_the_parent_with_one_hydrogen_removed_and_nothing_moved():
    mol = Chem.AddHs(Chem.MolFromSmiles("CO"))
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    xyz = np.arange(len(symbols) * 3, dtype=float).reshape(-1, 3)
    carbon = 0
    neighbors = [n.GetIdx() for n in mol.GetAtomWithIdx(carbon).GetNeighbors()]
    dropped = min(i for i in neighbors if symbols[i] == "H")

    out_symbols, out_xyz = core.radical_start(symbols, xyz, carbon, neighbors)

    assert len(out_symbols) == len(symbols) - 1 and out_symbols.count("H") == symbols.count("H") - 1
    assert np.array_equal(out_xyz, np.delete(xyz, dropped, axis=0))  # every other atom keeps its coordinates and order


def test_a_radical_start_needs_a_hydrogen_on_the_atom():
    with pytest.raises(ValueError, match="no hydrogen"):
        core.radical_start(["C", "O"], np.zeros((2, 3)), 0, [1])


# --- the reading rule -------------------------------------------------------------------------------------------------------


def _records(errors, uncertainty=0.5, missing=0):
    rows = [{"name": f"b{i}", "dh_ref": 100.0, "uncertainty": uncertainty, "dh_kcal": 100.0 + e} for i, e in enumerate(errors)]
    rows += [{"name": f"m{i}", "dh_ref": 100.0, "uncertainty": uncertainty, "dh_kcal": None} for i in range(missing)]
    return rows


def test_the_mse_limit_blocks_a_pass_with_a_good_mae():
    assert judge.judge(_records([2.5] * 4), "primary")["verdict"] == judge.PARTIAL  # MAE 2.5 but every error is +2.5, so MSE 2.5 > 1.5


def test_a_balanced_set_exactly_at_the_limits_passes_and_just_beyond_each_does_not():
    at = [2.5, -2.5, 2.5, -2.5]  # MAE 2.5, MSE 0, max 2.5
    assert judge.judge(_records(at), "primary")["verdict"] == judge.PASS
    assert judge.judge(_records([2.51, -2.51, 2.51, -2.51]), "primary")["verdict"] == judge.PARTIAL  # MAE just above 2.5

    five = [5.0, -5.0, 0.0, 0.0, 0.0, 0.0]  # max error exactly 5.0, MAE 1.67: only the maximum can fail it
    assert judge.judge(_records(five), "primary")["verdict"] == judge.PASS
    assert judge.judge(_records([5.01, -5.01, 0.0, 0.0, 0.0, 0.0]), "primary")["verdict"] == judge.PARTIAL  # one error above 5

    bias = [1.5, 1.5, 1.5, 1.5]  # MSE exactly 1.5
    assert judge.judge(_records(bias), "primary")["verdict"] == judge.PASS
    assert judge.judge(_records([1.51] * 4), "primary")["verdict"] == judge.PARTIAL


def test_partial_ends_at_a_mean_absolute_error_of_three_and_a_half():
    assert judge.judge(_records([3.5, -3.5]), "primary")["verdict"] == judge.PARTIAL
    assert judge.judge(_records([3.51, -3.51]), "primary")["verdict"] == judge.FAIL


def test_the_error_is_computed_minus_reference_so_an_overestimate_is_positive():
    result = judge.stats(_records([3.0, 1.0]))

    assert (result.mse, result.mae, result.max_abs) == (2.0, 2.0, 3.0)
    assert judge.stats(_records([-3.0, -1.0])).mse == -2.0


def test_the_secondary_arm_passes_only_at_two():
    assert judge.judge(_records([2.0, -2.0]), "secondary")["verdict"] == judge.PASS
    assert judge.judge(_records([2.01, -2.01]), "secondary")["verdict"] == judge.PARTIAL


def test_three_missing_deciding_bonds_are_allowed_and_four_are_not_evaluable():
    assert judge.judge(_records([0.5, -0.5] * 11, missing=3), "primary")["verdict"] == judge.PASS
    assert judge.judge(_records([0.5, -0.5] * 10, missing=4), "primary")["verdict"] == judge.NOT_EVALUABLE
    assert judge.judge(_records([], missing=0), "primary")["verdict"] == judge.NOT_EVALUABLE  # nothing computed at all


def test_the_loose_reference_stratum_is_reported_and_never_decides():
    good = _records([0.5, -0.5] * 10)
    wild = _records([20.0] * 8, uncertainty=3.0)
    result = judge.judge(good + wild, "primary")

    assert result["verdict"] == judge.PASS
    assert result["low"].count == 8 and result["low"].mae == pytest.approx(20.0)
    assert result["all"].count == 28


def test_a_stated_uncertainty_of_exactly_one_decides_and_just_above_does_not():
    assert not judge.is_low({"uncertainty": 1.0})
    assert judge.is_low({"uncertainty": 1.01})


# --- the reference data -----------------------------------------------------------------------------------------------------


def test_the_reference_has_thirty_three_bonds_and_twenty_five_decide():
    assert len(REFERENCE) == 33
    assert sum(1 for r in REFERENCE if not judge.is_low(r)) == 25
    assert len({r["name"] for r in REFERENCE}) == 33


@pytest.mark.parametrize(
    "name, value, uncertainty",
    [("methane C-H", 104.99, 0.03), ("ethyne C-H", 133.32, 0.07), ("water O-H", 118.82, 0.07), ("hydrogen peroxide O-H", 87.8, 0.5), ("benzene C-H", 112.9, 0.5),
     ("phenol O-H", 90.0, 3.0), ("formaldehyde C-H", 88.144, 0.008), ("ethanol O-H", 104.7, 0.8)],
)
def test_the_values_are_those_printed_in_the_paper_table(name, value, uncertainty):
    row = next(r for r in REFERENCE if r["name"] == name)
    assert (row["dh298"], row["uncertainty"]) == (value, uncertainty)  # Blanksby and Ellison 2003, Table 1


def test_every_bond_names_a_hydrogen_bearing_atom_of_the_element_its_label_says():
    for row in REFERENCE:
        mol = Chem.AddHs(Chem.MolFromSmiles(row["smiles"]))
        atom = mol.GetAtomWithIdx(row["atom"])
        element = row["name"].split()[-1].split("-")[0]
        assert atom.GetSymbol() == element, row["name"]
        assert any(n.GetSymbol() == "H" for n in atom.GetNeighbors()), row["name"]
