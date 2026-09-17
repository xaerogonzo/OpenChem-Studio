"""The Schindler SQE / Geidl EEM instrument (schindler_sqe_preregistration.md, part A).

The synthetic tests re-transcribe the equations by hand rather than calling the module's own matrix
builder, so an error shared by both cannot pass. The dataset tests need the supplement in Sci Downloads
and skip, naming why, when it is absent.
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

import numpy as np
import pytest
from scipy.special import erf

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("schindler_sqe_check", ROOT / "benchmarks" / "charges" / "models" / "schindler_sqe_check.py")
sq = importlib.util.module_from_spec(_spec)
sys.modules["schindler_sqe_check"] = sq
_spec.loader.exec_module(sq)

needs_si = pytest.mark.skipif(not sq.SI.exists(), reason="the Schindler 2021 supplement is not in Sci Downloads on this machine")

ATOMS = {"C/2": (-0.3, 1.1, 0.5), "O/2": (0.7, 1.6, 0.3), "H/1": (-1.1, 3.0, 0.8), "C/1": (-0.7, 0.9, 0.7)}
BONDS = {"C/2-O/2-2": 1.7, "C/1-C/2-1": 1.9, "C/2-H/1-1": -2.0, "C/1-H/1-1": -2.5}


def _mol(elements, coords, bonds, formal=None):
    return sq.Molecule("m", list(elements), np.array(coords, dtype=float), list(bonds), formal or [0] * len(elements))


def test_two_atoms_match_the_split_charge_solution_by_hand():
    """One bond: (eta1 + eta2 - 2 H12 + kappa) p = c1 - c2, q1 = p, q2 = -p, with c = chi under R_plus."""
    mol = _mol(["C", "O"], [[0, 0, 0], [1.21, 0, 0]], [(0, 1, 2)])
    chi_c, eta_c, w_c = ATOMS["C/2"]
    chi_o, eta_o, w_o = ATOMS["O/2"]
    r = 1.21
    h12 = math.erf(r / math.sqrt(2 * w_c ** 2 + 2 * w_o ** 2)) / r
    p = (chi_c - chi_o) / (eta_c + eta_o - 2 * h12 + BONDS["C/2-O/2-2"])
    for reading, sign in (("R_plus", 1.0), ("R_minus", -1.0)):
        q = sq.sqe_charges(mol, ATOMS, BONDS, reading)
        assert q[0] == pytest.approx(sign * p, abs=1e-12) and q[1] == pytest.approx(-sign * p, abs=1e-12)


def _formaldehyde():
    coords = [[0, 0, 0], [1.21, 0, 0], [-0.55, 0.94, 0], [-0.55, -0.94, 0]]
    return _mol(["C", "O", "H", "H"], coords, [(0, 1, 2), (0, 2, 1), (0, 3, 1)])


def test_sqe_charges_sum_to_zero_even_on_a_charged_molecule():
    mol = _formaldehyde()
    mol.formal = [1, 0, 0, 0]
    for reading in sq.READINGS:
        assert abs(sq.sqe_charges(mol, ATOMS, BONDS, reading).sum()) < 1e-12


def test_charges_follow_their_atoms_under_renumbering():
    mol = _formaldehyde()
    base = sq.sqe_charges(mol, ATOMS, BONDS, "R_minus")
    order = [2, 0, 3, 1]  # new position k holds old atom order[k]
    old_to_new = {old: new for new, old in enumerate(order)}
    moved = _mol([mol.elements[o] for o in order], mol.coords[order],
                 [(old_to_new[i], old_to_new[j], b) for i, j, b in reversed(mol.bonds)])
    q = sq.sqe_charges(moved, ATOMS, BONDS, "R_minus")
    assert np.allclose(q, base[order], atol=1e-12)


def test_flipping_a_bond_orientation_changes_nothing():
    mol = _formaldehyde()
    flipped = _mol(mol.elements, mol.coords, [(j, i, b) for i, j, b in mol.bonds])
    assert np.allclose(sq.sqe_charges(mol, ATOMS, BONDS, "R_plus"), sq.sqe_charges(flipped, ATOMS, BONDS, "R_plus"), atol=1e-12)


def test_hbo_typing_takes_each_atoms_highest_bond_order():
    # H-C#C-C(=O)-H : acetylenic carbons are /3, the carbonyl carbon /2, oxygen /2, hydrogens /1
    mol = _mol(["H", "C", "C", "C", "O", "H"], np.zeros((6, 3)), [(0, 1, 1), (1, 2, 3), (2, 3, 1), (3, 4, 2), (3, 5, 1)])
    assert sq.hbo_types(mol) == ["H/1", "C/3", "C/3", "C/2", "O/2", "H/1"]


def test_an_unbonded_atom_or_a_missing_type_is_refused():
    lone = _mol(["C"], [[0, 0, 0]], [])
    assert isinstance(sq.sqe_charges(lone, ATOMS, BONDS, "R_plus"), str)
    missing_bond = _mol(["O", "H"], [[0, 0, 0], [0.96, 0, 0]], [(0, 1, 1)])
    assert "not parameterised" in sq.sqe_charges(missing_bond, {**ATOMS, "O/1": (0.5, 1.5, 0.3)}, BONDS, "R_plus")


def test_eem_matches_a_hand_solved_diatomic_with_total_charge():
    """B1 q1 + k/r q2 + X = -A1, k/r q1 + B2 q2 + X = -A2, q1 + q2 = Q (the bordered column is +1, as in eem.cpp)."""
    params = {"C/1": (2.5, 0.3), "O/1": (2.6, 0.4)}
    kappa, r, Q = 0.25, 1.4, -1
    mol = _mol(["C", "O"], [[0, 0, 0], [r, 0, 0]], [(0, 1, 1)], [0, -1])
    q = sq.eem_charges(mol, kappa, params)
    M = np.array([[0.3, kappa / r, 1.0], [kappa / r, 0.4, 1.0], [1.0, 1.0, 0.0]])
    expected = np.linalg.solve(M, [-2.5, -2.6, Q])[:2]
    assert np.allclose(q, expected, atol=1e-12) and abs(q.sum() - Q) < 1e-12


def test_the_published_parameter_files_load_with_their_documented_shapes():
    atoms, bonds = sq.load_sqe_parameters()
    assert len(atoms) == 15 and len(bonds) == 66
    assert atoms["CL/1"][1] == pytest.approx(73.95200479863837)
    kappa, geidl = sq.load_geidl()
    assert kappa == 0.2509 and len(geidl) == 17 and min(b for _, b in geidl.values()) > 0


def test_the_chargefw2_parameter_file_round_trips_every_published_value(tmp_path):
    import json

    atoms, bonds = sq.load_sqe_parameters()
    payload = json.loads(sq.chargefw2_parameter_file(atoms, bonds, tmp_path / "p.json").read_text(encoding="utf-8"))
    back_atoms = {f"{r['key'][0].upper()}/{r['key'][2]}": tuple(r["value"]) for r in payload["atom"]["data"]}
    back_bonds = {f"{r['key'][0].upper()}/{r['key'][2]}-{r['key'][3].upper()}/{r['key'][5]}-{r['key'][7]}": r["value"][0]
                  for r in payload["bond"]["data"]}
    assert back_atoms == atoms and back_bonds == bonds


def test_the_sdf_parser_reads_bond_orders_and_charges_without_perception():
    block = "\n".join([
        "ACE", "  test", "",
        "  3  2  0  0  0  0  0  0  0  0999 V2000",
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0",
        "    1.2500    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0",
        "   -0.7000    1.1000    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0",
        "  1  2  2  0",
        "  1  3  1  0",
        "M  CHG  1   3  -1",
        "M  END", "$$$$", ""])
    (mol,) = sq.parse_sdf(block)
    assert mol.name == "ACE" and mol.bonds == [(0, 1, 2), (0, 2, 1)] and mol.formal == [0, 0, -1] and mol.total_charge == -1


@needs_si
def test_every_deposited_molecule_pairs_with_its_charges_and_the_split_resolves():
    split = sq.load_split()
    for name, (train, test) in {"CCD_gen": (3554, 889), "DTP_small": (1564, 392)}.items():
        data = sq.load_dataset(name)
        names = {m.name for m, _ in data}
        assert len(data) == train + test == len(names)
        assert len(split[f"{name} training set"]) == train and len(split[f"{name} test set"]) == test
        assert set(split[f"{name} training set"]) | set(split[f"{name} test set"]) == names
