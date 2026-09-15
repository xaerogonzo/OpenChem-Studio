"""TRIAGE.md 2.7: the Nistor SQE instrument, tested before any corpus SQE charge exists.

The references here transcribe the supplement again (Slater n and zeta, the parameters a toy uses)
rather than read them from `nistor_sqe_check`, so a transcription or unit error shared by both
would not pass. The kernel reference is a Fourier-space integral with the exact transform of an ns
Slater density, which shares nothing with `charge_equilibration`'s gamma-function closed form.
"""

from __future__ import annotations

import copy
import importlib.util
import itertools
import math
import pathlib
import random
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("nistor_sqe_check", ROOT / "benchmarks" / "charges" / "models" / "nistor_sqe_check.py")
ns = importlib.util.module_from_spec(_spec)
sys.modules["nistor_sqe_check"] = ns
_spec.loader.exec_module(ns)

HARTREE_EV = 27.211386
BOHR = 0.529177210903
#: Supplement p. 8, transcribed again: (n, zeta in 1/angstrom).
SLATER = {"H": (1, 2.315), "C": (2, 1.618), "O": (2, 1.842), "Si": (3, 1.818)}


def _fourier_transform(n: int, zeta_bohr: float, k: np.ndarray) -> np.ndarray:
    """rho(k) of |phi|^2 for phi = A r^(n-1) exp(-zeta r), normalised: 4 pi A^2 (2n-1)! Im[(a - ik)^-2n] / k."""
    a = 2.0 * zeta_bohr
    a_squared = a ** (2 * n + 1) / (4.0 * math.pi * math.factorial(2 * n))
    return 4.0 * math.pi * a_squared * math.factorial(2 * n - 1) * ((a - 1j * k) ** (-2 * n)).imag / k


def fourier_j_ev(element_a: str, element_b: str, r_angstrom: float) -> float:
    """J(R) = (2/pi) int rho_a(k) rho_b(k) sin(kR)/(kR) dk, panelled Gauss-Legendre to 400 a.

    Beyond that the integrand is below k^-9 of its scale, under 1e-15 eV."""
    n_a, zeta_a = SLATER[element_a]
    n_b, zeta_b = SLATER[element_b]
    zeta_a, zeta_b, r = zeta_a * BOHR, zeta_b * BOHR, r_angstrom / BOHR
    k_max = 400.0 * max(zeta_a, zeta_b)
    x, w = np.polynomial.legendre.leggauss(24)
    edges = np.linspace(0.0, k_max, 4001)
    mid, half = (edges[:-1] + edges[1:]) / 2, (edges[1:] - edges[:-1]) / 2
    k = (mid[:, None] + half[:, None] * x[None, :]).ravel()
    weights = (half[:, None] * w[None, :]).ravel()
    integrand = _fourier_transform(n_a, zeta_a, k) * _fourier_transform(n_b, zeta_b, k) * np.sin(k * r) / (k * r)
    return 2.0 / math.pi * float(weights @ integrand) * HARTREE_EV


# --- kernel ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("pair", [("H", "H"), ("C", "O"), ("Si", "Si")])
def test_kernel_equals_an_independent_fourier_integral_to_1e_9_ev(pair):
    for r in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.5, 6.0):
        assert ns.slater_j_ev(*pair, r) == pytest.approx(fourier_j_ev(*pair, r), abs=1e-9), (pair, r)


def test_kernel_reproduces_the_supplement_figure_intercepts_to_plotting_precision():
    # Supplement p. 8's figure: about 21 (H-H), 9 (C-O) and 6.8 (Si-Si) eV at R = 0. A sanity check, not a gate.
    assert ns.slater_j_ev("H", "H", 0.0) == pytest.approx(21, abs=0.5)
    assert ns.slater_j_ev("C", "O", 0.0) == pytest.approx(9, abs=0.3)
    assert ns.slater_j_ev("Si", "Si", 0.0) == pytest.approx(6.8, abs=0.2)


def test_printed_normalisations_are_consistent_with_zeta_to_its_printed_precision():
    """A checksum on the (n, zeta) transcription. Carbon's A computes to 1.0847 against a printed 1.084:
    zeta = 1.6175, still printed 1.618, gives 1.0839, so the printed A is inside zeta's rounding."""
    for element, (n, zeta, printed) in ns.SLATER.items():
        values = [math.sqrt((2 * z) ** (2 * n + 1) / (4 * math.pi * math.factorial(2 * n))) for z in (zeta - 5e-4, zeta + 5e-4)]
        assert min(values) - 5e-4 <= printed <= max(values) + 5e-4, element
        assert (n, zeta) == SLATER[element]


# --- method ii ------------------------------------------------------------------------------------


def test_method_ii_reproduces_ch3oh_by_hand_and_its_printed_column():
    # Hand values: C = 3(-0.0908) + 0.2918 = 0.0194, O = -0.2918 - 0.3775 = -0.6693, H(C) 0.0908, H(O) 0.3775.
    elements = ["C", "O", "H", "H", "H", "H"]
    bonds = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 5)]
    q = ns.method_ii_charges(elements, bonds, ns.PARAMETER_SETS["all41"]["ii"])
    assert q == pytest.approx([0.0194, -0.6693, 0.0908, 0.0908, 0.0908, 0.3775], abs=1e-12)
    molecule = ns.molecules()[34]
    assert molecule["name"] == "CH3OH"
    recovered = ns.recover(molecule, ns.PARAMETER_SETS["all41"]["ii"])
    assert recovered["class"] == "RECOVERED-BY-ROTATION"
    assert ns.method_ii_charges(molecule["elements"], recovered["bonds"], ns.PARAMETER_SETS["all41"]["ii"]) == pytest.approx(
        molecule["charges"]["ii"], abs=5e-5)


def test_parameter_set_rows_have_the_supplement_shape():
    counts = {name: (len(ps["i"]), len(ps["ii"]), len(ps["iii"][1]), len(ps["iv"][2])) for name, ps in ns.PARAMETER_SETS.items()}
    assert counts == {"all41": (4, 8, 8, 14), "SiOH": (3, 4, 4, 7), "COH": (3, 4, 4, 7), "ESP": (4, 8, 8, 14), "Mulliken": (4, 8, 8, 14)}
    # Hydrogen's chi is the reference (5.0780) in every set and method, as printed.
    for ps in ns.PARAMETER_SETS.values():
        assert {ps["i"]["H"][1], ps["iii"][0]["H"][1], ps["iv"][0]["H"][1]} == {5.078}


# --- the split-charge solve -----------------------------------------------------------------------

TOY_ELEMENTS = ["H", "O", "Si", "H"]
TOY_BONDS = [(0, 1), (1, 2), (2, 3)]
TOY_COORDS = [(0.0, 0.0, 0.0), (0.96, 0.0, 0.0), (1.52, 1.54, 0.0), (1.20, 2.10, 1.30)]
#: all-41, method iv, transcribed again: atomic (kappa, chi), kappa_s, and ORDERED deltas.
TOY_IV_ATOMS = {"H": (17.4830, 5.0780), "O": (14.5976, 8.9139), "Si": (7.0924, 4.6577)}
TOY_IV_KS = {frozenset(("H", "O")): 0.0030, frozenset(("O", "Si")): 4.0068, frozenset(("H", "Si")): 1.2460}
TOY_IV_DELTA = {("H", "O"): (-0.4915, -0.4921), ("O", "H"): (-0.0365, 0.4035), ("O", "Si"): (-0.4035, 0.4553),
                ("Si", "O"): (0.1689, -0.2514), ("Si", "H"): (-0.0601, 0.0380), ("H", "Si"): (0.0826, 0.3885)}
TOY_III_ATOMS = {"H": (16.1954, 5.0780), "O": (12.4062, 8.5220), "Si": (6.7348, 4.3850)}
TOY_III_KS = {frozenset(("H", "O")): 0.0627, frozenset(("O", "Si")): 4.0194, frozenset(("H", "Si")): 2.1629}
TOY_I_ATOMS = {"H": (17.3351, 5.0780), "O": (14.1631, 8.3440), "Si": (7.8226, 4.4264)}


def reference_energy(split, method: str, coefficient: float) -> float:
    """Eq 4 with the QE rules, in explicit loops: one split charge per bond, +q on its first atom."""
    n = len(TOY_ELEMENTS)
    charge = [0.0] * n
    for (i, j), q in zip(TOY_BONDS, split):
        charge[i] += q
        charge[j] -= q
    atoms = {"i": TOY_I_ATOMS, "iii": TOY_III_ATOMS, "iv": TOY_IV_ATOMS}[method]
    energy = 0.0
    for a in range(n):
        kappa, chi = atoms[TOY_ELEMENTS[a]]
        if method == "iv":
            for i, j in TOY_BONDS:
                if a in (i, j):
                    other = j if a == i else i
                    d_kappa, d_chi = TOY_IV_DELTA[(TOY_ELEMENTS[a], TOY_ELEMENTS[other])]
                    kappa, chi = kappa + d_kappa, chi + d_chi
        energy += 0.5 * kappa * charge[a] ** 2 + chi * charge[a]
    if method in ("iii", "iv"):
        table = TOY_III_KS if method == "iii" else TOY_IV_KS
        for (i, j), q in zip(TOY_BONDS, split):
            energy += coefficient * table[frozenset((TOY_ELEMENTS[i], TOY_ELEMENTS[j]))] * q ** 2
    for a, b in itertools.combinations(range(n), 2):
        energy += charge[a] * charge[b] * ns.slater_j_ev(TOY_ELEMENTS[a], TOY_ELEMENTS[b], math.dist(TOY_COORDS[a], TOY_COORDS[b]))
    return energy


def brute_force_charges(method: str, coefficient: float) -> np.ndarray:
    """Minimise the reference energy with no matrix from the module: V is quadratic, so its gradient and
    Hessian by central differences are exact up to rounding, and one Newton step lands on the minimum."""
    m = len(TOY_BONDS)
    h = 0.1  # V is exactly quadratic, so a large step only reduces rounding
    zero = np.zeros(m)
    grad = np.array([(reference_energy(zero + h * e, method, coefficient) - reference_energy(zero - h * e, method, coefficient)) / (2 * h)
                     for e in np.eye(m)])
    hess = np.empty((m, m))
    for a, b in itertools.product(range(m), repeat=2):
        ea, eb = np.eye(m)[a] * h, np.eye(m)[b] * h
        hess[a, b] = (reference_energy(ea + eb, method, coefficient) - reference_energy(ea - eb, method, coefficient)
                      - reference_energy(-ea + eb, method, coefficient) + reference_energy(-ea - eb, method, coefficient)) / (4 * h * h)
    split = np.linalg.solve(hess, -grad)
    charge = np.zeros(len(TOY_ELEMENTS))
    for (i, j), q in zip(TOY_BONDS, split):
        charge[i] += q
        charge[j] -= q
    return charge


@pytest.mark.parametrize(("method", "reading"), [("i", "R_eq10"), ("iii", "R_eq10"), ("iii", "R_eq14"), ("iv", "R_eq10"), ("iv", "R_eq14")])
def test_split_charge_solve_equals_brute_force_minimisation_of_eq_4(method, reading):
    expected = brute_force_charges(method, {"R_eq10": 1.0, "R_eq14": 0.5}[reading])
    got = ns.solve(TOY_ELEMENTS, TOY_COORDS, TOY_BONDS, ns.PARAMETER_SETS["all41"], method, reading)
    assert got == pytest.approx(expected, abs=1e-8)
    assert sum(got) == pytest.approx(0.0, abs=1e-12)


def test_the_two_bond_hardness_readings_differ_on_the_toy():
    a = ns.solve(TOY_ELEMENTS, TOY_COORDS, TOY_BONDS, ns.PARAMETER_SETS["all41"], "iii", "R_eq10")
    b = ns.solve(TOY_ELEMENTS, TOY_COORDS, TOY_BONDS, ns.PARAMETER_SETS["all41"], "iii", "R_eq14")
    assert np.max(np.abs(a - b)) > 1e-3


def test_method_i_equals_an_atomic_qe_solve_on_a_connected_molecule():
    """Eq 4's isomorphism: on a tree the split charges span every neutral charge vector."""
    n = len(TOY_ELEMENTS)
    hardness = np.zeros((n, n))
    for a, b in itertools.product(range(n), repeat=2):
        hardness[a, b] = TOY_I_ATOMS[TOY_ELEMENTS[a]][0] if a == b else ns.slater_j_ev(
            TOY_ELEMENTS[a], TOY_ELEMENTS[b], math.dist(TOY_COORDS[a], TOY_COORDS[b]))
    system = np.block([[hardness, np.ones((n, 1))], [np.ones((1, n)), np.zeros((1, 1))]])
    rhs = np.concatenate([-np.array([TOY_I_ATOMS[e][1] for e in TOY_ELEMENTS]), [0.0]])
    atomic = np.linalg.solve(system, rhs)[:n]
    assert ns.solve(TOY_ELEMENTS, TOY_COORDS, TOY_BONDS, ns.PARAMETER_SETS["all41"], "i") == pytest.approx(atomic, abs=1e-10)


def test_method_iv_reads_an_unknown_ordered_pair_as_an_error_never_a_zero():
    params = copy.deepcopy(ns.PARAMETER_SETS["all41"])
    del params["iv"][2]["Si-O"]
    with pytest.raises(KeyError):
        ns.solve(TOY_ELEMENTS, TOY_COORDS, TOY_BONDS, params, "iv")


# --- recovery -------------------------------------------------------------------------------------


def _with_printed(molecule: dict, coords) -> dict:
    out = copy.deepcopy(molecule)
    out["printed_coords"] = list(coords)
    return out


def test_recovery_undoes_a_one_row_displacement_and_nothing_else():
    truth = ns.molecules()[34]
    true_coords = ns.recover(truth, ns.PARAMETER_SETS["all41"]["ii"])["coords"]
    displaced = true_coords[1:] + true_coords[:1]  # rotating this down one row restores the truth
    result = ns.recover(_with_printed(truth, displaced), ns.PARAMETER_SETS["all41"]["ii"])
    assert result["class"] == "RECOVERED-BY-ROTATION"
    assert result["coords"] == true_coords
    two_rows = true_coords[2:] + true_coords[:2]  # needs a two-row rotation: registered as BLOCKED
    assert ns.recover(_with_printed(truth, two_rows), ns.PARAMETER_SETS["all41"]["ii"])["class"] == "BLOCKED"


def test_recovery_blocks_scrambled_coordinates():
    truth = ns.molecules()[38]
    coords = list(truth["printed_coords"])
    random.Random(20260915).shuffle(coords)
    assert ns.recover(_with_printed(truth, coords), ns.PARAMETER_SETS["all41"]["ii"])["class"] == "BLOCKED"


def test_a_second_rotation_within_a_symmetry_class_is_not_ambiguity_but_across_classes_it_is():
    ch4 = ns.molecules()[35]
    assert ch4["name"] == "CH4"
    assert ns.recover(ch4, ns.PARAMETER_SETS["all41"]["ii"])["class"] == "RECOVERED-BY-ROTATION"
    assert ns.recover(ch4, ns.PARAMETER_SETS["all41"]["ii"], symmetry_classes=False)["class"] == "AMBIGUOUS"
    split = copy.deepcopy(ch4)
    split["raw"]["esp"][1] = "9.9999"  # one hydrogen differs in the ESP column only: the classes now differ
    assert ns.recover(split, ns.PARAMETER_SETS["all41"]["ii"])["class"] == "AMBIGUOUS"


def test_recovery_classes_on_the_corpus_are_the_amended_counts():
    """Recovery uses coordinates, elements and method ii only, so its counts are instrument state, not a result."""
    mols = ns.molecules()
    classes = {i: ns.recover(m, ns.PARAMETER_SETS["all41"]["ii"])["class"] for i, m in mols.items()}
    assert sorted(i for i, c in classes.items() if c == "RECOVERED-BY-ROTATION") == [6, 26, 33, 34, 35, 38]
    assert sorted(i for i, c in classes.items() if c == "AMBIGUOUS") == [29, 32, 41]
    assert list(classes.values()).count("BLOCKED") == 32
