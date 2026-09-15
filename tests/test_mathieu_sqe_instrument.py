"""TRIAGE.md 2.4e: the SQE instrument, tested before any Table I metric exists.

`energy_eq8` below is the reference: it transcribes Mathieu 2007 eqs 2, 6, 7
and 8 with explicit loops and literal Table II numbers, and calls nothing in
`mathieu_sqe_check` -- a pair-rule or sign bug shared by both would otherwise
pass. Every test is synthetic apart from one fixture geometry (test 7).
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("mathieu_sqe_check", ROOT / "benchmarks" / "charges" / "models" / "mathieu_sqe_check.py")
sq = importlib.util.module_from_spec(_spec)
sys.modules["mathieu_sqe_check"] = sq
_spec.loader.exec_module(sq)

from openchem.chem import charge_equilibration as ce  # noqa: E402

HARTREE_EV = 27.211386
BOHR = 0.529177210903
# Transcribed again here, on purpose, rather than read from the module.
CHI = {"H": 1.00, "C": 5.25, "N": 8.80, "O": 14.72, "F": 15.00}
ETA = {"H": 17.95, "C": 9.00, "N": 9.39, "O": 14.34, "F": 19.77}
RC = {"C": 0.77, "H": 0.37, "N": 0.75, "O": 0.73, "F": 0.71}
RW = {"C": 1.70, "H": 1.20, "N": 1.55, "O": 1.52, "F": 1.47}
C_EV, LAM = 115.0, 0.816

NITRAMIDE_ELEMENTS = ["N", "N", "O", "O", "H", "H"]
NITRAMIDE = np.array([[0.1014, 1.2402, 0.0], [0.0295, -0.0869, 0.0], [-0.0323, -0.5995, 1.1112],
                      [-0.0323, -0.5995, -1.1112], [-0.3964, 1.5016, -0.8390], [-0.3964, 1.5016, 0.8390]])
CH2F2_ELEMENTS = ["C", "F", "F", "H", "H"]
CH2F2 = np.array([[0.0, 0.0, 0.0], [0.0, 1.10, 0.80], [0.0, -1.10, 0.80], [0.90, 0.0, -0.63], [-0.90, 0.0, -0.63]])


def reference_pairs(elements, coords):
    out = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            r = math.dist(coords[i], coords[j])
            if r < RW[elements[i]] + RW[elements[j]]:
                out.append((i, j, r))
    return out


def charges_eq6(q, n, pair_list):
    """Eq 6: Q_k = sum_{i<k} q_ik - sum_{j>k} q_kj."""
    big_q = [0.0] * n
    for value, (i, j, _) in zip(q, pair_list):
        big_q[j] += value
        big_q[i] -= value
    return big_q


def energy_eq8(q, elements, coords, *, with_penalty=True):
    """Eq 8 in Hartree: sum_i (chi Q + eta Q^2) + sum_{i<j} Q_i Q_j / R + sum E^p (eq 7)."""
    pair_list = reference_pairs(elements, coords)
    n = len(elements)
    big_q = charges_eq6(q, n, pair_list)
    energy = sum((CHI[e] * big_q[a] + ETA[e] * big_q[a] ** 2) / HARTREE_EV for a, e in enumerate(elements))
    for a in range(n):
        for b in range(a + 1, n):
            energy += big_q[a] * big_q[b] / (math.dist(coords[a], coords[b]) / BOHR)
    if with_penalty:
        for value, (i, j, r) in zip(q, pair_list):
            onset = LAM * (RC[elements[i]] + RC[elements[j]])
            limit = RW[elements[i]] + RW[elements[j]]
            if r > onset:
                energy += C_EV * ((r - onset) / (r - limit)) ** 2 * value ** 2 / HARTREE_EV
    return energy


def fd_gradient(f, q, h):
    return np.array([(f(q + h * e) - f(q - h * e)) / (2 * h) for e in np.eye(len(q))])


def fd_hessian(f, q, h):
    size = len(q)
    out = np.zeros((size, size))
    basis = np.eye(size)
    for a in range(size):
        for b in range(size):
            ea, eb = h * basis[a], h * basis[b]
            out[a, b] = (f(q + ea + eb) - f(q + ea - eb) - f(q - ea + eb) + f(q - ea - eb)) / (4 * h * h)
    return out


def test_the_module_parameters_are_table_ii_model_b():
    for e in sq.ELEMENTS:
        assert ce.EEM_BULTINCK2002_PART1[e][0] - ce.EEM_BULTINCK2002_PART1["H"][0] == pytest.approx(sq.TABLE_II_CHI_RELATIVE[e], abs=1e-12)
        assert ce.EEM_BULTINCK2002_PART1[e][1] == sq.TABLE_II_ETA[e]
    assert (sq.C_EV, sq.LAMBDA, sq.R_COVALENT, sq.R_VDW) == (C_EV, LAM, RC, RW)


# 1 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("elements,coords", [(NITRAMIDE_ELEMENTS, NITRAMIDE), (CH2F2_ELEMENTS, CH2F2)], ids=["nitramide", "CH2F2"])
def test_1_eq8_finite_differences_equal_the_assembled_system(elements, coords):
    system = sq.assemble(elements, coords)
    assert [p[:2] for p in system["pairs"]] == [p[:2] for p in reference_pairs(elements, coords)]
    a, b = system["A"], system["b"]
    size = len(b)
    rng = np.random.default_rng(20260915)
    nonzero = rng.choice([-1, 1], size) * rng.uniform(0.05, 0.2, size)
    f = lambda v: energy_eq8(v, elements, coords)  # noqa: E731
    for q in (np.zeros(size), nonzero):
        analytic_gradient = a @ q - b
        for h in (1e-3, 1e-4, 1e-5):
            # E is exactly quadratic in q, so a central difference has no truncation error at any h;
            # what remains is roundoff, growing as h shrinks. Agreement at all three steps is the test.
            assert np.allclose(fd_gradient(f, q, h), analytic_gradient, rtol=1e-6, atol=1e-8), h
        for h in (1e-3, 1e-4):
            assert np.allclose(fd_hessian(f, q, h), a, rtol=1e-6, atol=1e-7), h


def test_1_the_literal_eq13_is_not_eq8s_hessian_and_its_b_is_the_gradient_not_minus_it():
    literal = sq.literal_eq13_diagnostic(NITRAMIDE_ELEMENTS, NITRAMIDE)
    f = lambda v: energy_eq8(v, NITRAMIDE_ELEMENTS, NITRAMIDE)  # noqa: E731
    size = len(literal["B"])
    hessian = fd_hessian(f, np.zeros(size), 1e-4)
    assert not np.allclose(literal["matrix"], hessian, rtol=1e-3, atol=1e-4)
    gradient_at_zero = fd_gradient(f, np.zeros(size), 1e-4)
    assert np.allclose(literal["B"], gradient_at_zero, rtol=1e-6, atol=1e-9)
    # The derivation, checked numerically: eq 13 = -(Hessian) + 2 diag(K).
    k = sq.assemble(NITRAMIDE_ELEMENTS, NITRAMIDE)["K"]
    assert np.allclose(literal["matrix"], -hessian + 2 * np.diag(k), rtol=1e-6, atol=1e-7)


# 2 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("r,expect_penalty", [(0.92, True), (0.85, False)])
def test_2_two_atoms_equal_the_closed_form(r, expect_penalty):
    elements, coords = ["H", "F"], np.array([[0.0, 0.0, 0.0], [r, 0.0, 0.0]])
    system = sq.assemble(elements, coords)
    assert system["M"].tolist() == [[-1.0], [1.0]]
    k = float(system["K"][0])
    assert (k > 0) is expect_penalty
    j = 1.0 / (r / BOHR)
    closed = (CHI["H"] - CHI["F"]) / HARTREE_EV / ((2 * ETA["H"] + 2 * ETA["F"]) / HARTREE_EV - 2 * j + k)
    solution = sq.solve(elements, coords)
    assert solution.q[0] == pytest.approx(closed, abs=1e-14)
    assert solution.charges.tolist() == pytest.approx([-closed, closed], abs=1e-14)
    if not expect_penalty:
        assert ce.eem_charges(elements, coords).charges.tolist() == pytest.approx(solution.charges.tolist(), abs=1e-12)


# 3 ---------------------------------------------------------------------------------------------


def _energy_in_charges(big_q, elements, coords):
    energy = sum((CHI[e] * big_q[a] + ETA[e] * big_q[a] ** 2) / HARTREE_EV for a, e in enumerate(elements))
    for a in range(len(elements)):
        for b in range(a + 1, len(elements)):
            energy += big_q[a] * big_q[b] / (math.dist(coords[a], coords[b]) / BOHR)
    return energy


@pytest.mark.parametrize("elements,coords", [(NITRAMIDE_ELEMENTS, NITRAMIDE), (CH2F2_ELEMENTS, CH2F2)], ids=["nitramide", "CH2F2"])
def test_3_the_eem_limit_is_the_shipped_eem(elements, coords):
    solution = sq.solve(elements, coords, use_penalty=False)
    eem = ce.eem_charges(elements, coords).charges
    assert np.allclose(solution.charges, eem, atol=1e-10)
    assert _energy_in_charges(solution.charges, elements, coords) == pytest.approx(_energy_in_charges(eem, elements, coords), abs=1e-12)
    assert not np.all(sq.assemble(elements, coords, use_penalty=False)["K"])


# 4 ---------------------------------------------------------------------------------------------

TRIANGLE_ELEMENTS = ["C", "C", "C"]
TRIANGLE = np.array([[0.0, 0.0, 0.0], [1.20, 0.0, 0.0], [0.60, 1.20 * math.sqrt(3) / 2, 0.0]])


def test_4_k_zero_cycle_unique_atomic_charges_not_bond_charges():
    system = sq.assemble(TRIANGLE_ELEMENTS, TRIANGLE)
    assert len(system["pairs"]) == 3 and not system["K"].any()  # 1.20 A < lambda r^C = 1.2566 A
    solution = sq.solve(TRIANGLE_ELEMENTS, TRIANGLE)
    assert solution.diagnostics["discarded"] == 1 and solution.diagnostics["cycle_dimension"] == 1 and solution.valid
    z = np.array([1.0, -1.0, 1.0])  # pairs (0,1), (0,2), (1,2): a circulation
    assert np.allclose(system["M"] @ z, 0.0)
    pair_list = reference_pairs(TRIANGLE_ELEMENTS, TRIANGLE)
    q = solution.q
    assert charges_eq6(q + 0.37 * z, 3, pair_list) == pytest.approx(charges_eq6(q, 3, pair_list), abs=1e-15)
    assert energy_eq8(q + 0.37 * z, TRIANGLE_ELEMENTS, TRIANGLE) == pytest.approx(energy_eq8(q, TRIANGLE_ELEMENTS, TRIANGLE), abs=1e-15)


# 5 ---------------------------------------------------------------------------------------------


def test_5_the_pair_graph_of_four_hydrogens_with_one_pair_just_beyond_the_cutoff():
    elements = ["H"] * 4
    coords = np.array([[0.0, 0, 0], [1.0, 0, 0], [3.5, 0, 0], [4.5, 0, 0]])  # (1,2) at 2.5 A > 2.4 A
    system = sq.assemble(elements, coords)
    assert [p[:2] for p in system["pairs"]] == [(0, 1), (2, 3)]
    assert sq.components(4, system["pairs"]) == [[0, 1], [2, 3]]
    onset, limit = LAM * 0.74, 2.40
    expected = 2 * C_EV * ((1.0 - onset) / (1.0 - limit)) ** 2 / HARTREE_EV
    assert system["K"].tolist() == pytest.approx([expected, expected], rel=1e-12)


# 6 ---------------------------------------------------------------------------------------------


def _pair(r, elements=("H", "H")):
    return list(elements), np.array([[0.0, 0.0, 0.0], [r, 0.0, 0.0]])


def test_6_k_diverges_monotonically_approaching_the_cutoff_from_below_and_stays_finite():
    limit = RW["H"] + RW["H"]
    values = []
    for gap in (1e-2, 1e-3, 1e-4, 1e-5):
        elements, coords = _pair(limit - gap)
        system = sq.assemble(elements, coords)
        assert len(system["pairs"]) == 1
        values.append(float(system["K"][0]))
        assert math.isfinite(values[-1])
        assert sq.solve(elements, coords).valid
    assert values == sorted(values) and values[-1] > 1e5 * values[0]  # K ~ 1/gap^2


@pytest.mark.parametrize("offset", [0.0, 1e-6])
def test_6_at_and_beyond_the_cutoff_the_pair_does_not_exist(offset):
    elements, coords = _pair(RW["H"] + RW["H"] + offset)
    system = sq.assemble(elements, coords)
    assert system["pairs"] == [] and sq.components(2, system["pairs"]) == [[0], [1]]
    solution = sq.solve(elements, coords)
    assert solution.charges.tolist() == [0.0, 0.0] and solution.diagnostics["components"] == 2


def test_6_the_penalty_switches_on_strictly_above_lambda_r_covalent():
    onset = LAM * (RC["H"] + RC["H"])
    ks = [float(sq.assemble(*_pair(onset + d))["K"][0]) for d in (-1e-9, 0.0, 1e-9)]
    assert ks[0] == 0.0 and ks[1] == 0.0 and ks[2] > 0.0


# 7 ---------------------------------------------------------------------------------------------


def test_7_nitramide_dissociates_into_neutral_fragments_under_sqe_and_not_under_eem():
    """The EQ set has no methanol (the plan's example); nitramide H2N-NO2 is used instead,
    and the NO2 fragment (atoms 2, 3, 4 in source numbering) moves along the N-N bond."""
    population = {s["file"]: s for s in sq.population(sq.SETS["EQ"])}
    structure = population["H2N-NO2"]
    assert structure["elements"] == NITRAMIDE_ELEMENTS
    amine, nitro = [0, 4, 5], [1, 2, 3]
    assert [structure["elements"][i] for i in amine] == ["N", "H", "H"]
    assert [structure["elements"][i] for i in nitro] == ["N", "O", "O"]
    base = structure["coords"]
    direction = (base[1] - base[0]) / np.linalg.norm(base[1] - base[0])
    sweep = []
    step = 0
    while True:
        coords = base.copy()
        coords[nitro] += step * direction
        solution = sq.solve(structure["elements"], coords)
        sweep.append((step, float(solution.charges[nitro].sum())))
        margin = min(math.dist(coords[i], coords[j]) - RW[structure["elements"][i]] - RW[structure["elements"][j]]
                     for i in amine for j in nitro)
        if margin > 1.0:
            break
        step += 1
    assert solution.valid and solution.diagnostics["components"] == 2
    assert all(abs(s) <= 1e-12 for s in solution.diagnostics["component_sums"])
    eem_fragment = float(ce.eem_charges(structure["elements"], coords).charges[nitro].sum())
    assert abs(eem_fragment) > 0.01, "EEM violates fragment neutrality at the separated geometry"
    assert len(sweep) >= 2 and abs(sweep[0][1]) > 1e-3


# 8 ---------------------------------------------------------------------------------------------


def test_8_r_squared_is_the_intercept_regression_r_squared_and_a_hand_computed_value():
    x, y = [1.0, 2.0, 3.0, 4.0, 5.0], [2.0, 4.0, 5.0, 4.0, 5.0]
    assert sq.r_squared(x, y) == pytest.approx(0.6, abs=1e-15)  # Sxy^2/(Sxx Syy) = 36/60
    slope, intercept = np.polyfit(x, y, 1)
    sse = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    sst = sum((yi - np.mean(y)) ** 2 for yi in y)
    assert sq.r_squared(x, y) == pytest.approx(1 - sse / sst, abs=1e-14)
    rng = np.random.default_rng(7)
    a, b = rng.normal(size=40), rng.normal(size=40)
    slope, intercept = np.polyfit(a, b, 1)
    assert sq.r_squared(a, b) == pytest.approx(1 - np.sum((b - slope * a - intercept) ** 2) / np.sum((b - b.mean()) ** 2), abs=1e-12)


# 9-12 ------------------------------------------------------------------------------------------


def test_9_a_uniform_chi_shift_changes_nothing():
    params = sq.Parameters()
    shifted = sq.Parameters(chi_ev={e: v + 3.7 for e, v in params.chi_ev.items()})
    one, two = sq.solve(NITRAMIDE_ELEMENTS, NITRAMIDE, params), sq.solve(NITRAMIDE_ELEMENTS, NITRAMIDE, shifted)
    assert np.allclose(one.charges, two.charges, atol=1e-12) and np.allclose(one.q, two.q, atol=1e-12)
    assert np.allclose(sq.assemble(NITRAMIDE_ELEMENTS, NITRAMIDE, params)["A"], sq.assemble(NITRAMIDE_ELEMENTS, NITRAMIDE, shifted)["A"], atol=0)


@pytest.mark.parametrize("elements,coords", [(NITRAMIDE_ELEMENTS, NITRAMIDE), (TRIANGLE_ELEMENTS, TRIANGLE)], ids=["nitramide", "cycle"])
def test_10_charges_do_not_depend_on_the_rcond_policy(elements, coords):
    reference = sq.solve(elements, coords).charges
    for rcond in (1e-8, 1e-10, 1e-12, 1e-14):
        assert np.allclose(sq.solve(elements, coords, rcond=rcond).charges, reference, atol=1e-12), rcond


def test_11_permuting_atoms_permutes_the_charges():
    reference = sq.solve(NITRAMIDE_ELEMENTS, NITRAMIDE).charges
    for perm in ([5, 3, 1, 0, 2, 4], [2, 0, 4, 1, 5, 3]):
        moved = sq.solve([NITRAMIDE_ELEMENTS[p] for p in perm], NITRAMIDE[perm]).charges
        assert np.allclose(moved, reference[perm], atol=1e-12), perm


def test_12_two_molecules_in_one_input_are_each_neutral():
    elements = NITRAMIDE_ELEMENTS + CH2F2_ELEMENTS
    coords = np.vstack([NITRAMIDE, CH2F2 + np.array([20.0, 0.0, 0.0])])
    solution = sq.solve(elements, coords)
    assert solution.valid and solution.diagnostics["components"] == 2
    assert abs(solution.charges[:6].sum()) <= 1e-12 and abs(solution.charges[6:].sum()) <= 1e-12
    assert np.abs(solution.charges).max() > 0.05
