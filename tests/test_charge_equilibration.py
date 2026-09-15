"""Rappé–Goddard QEq and Bultinck EEM, against their papers and independent maths.

EVERY TOLERANCE AND EVERY READING HERE WAS FIXED BEFORE THE SOLVER EXISTED:
`benchmarks/charges/rappe_goddard/preregistration.md`, committed first. The
oracles are numbered as it numbers them. Reading this file without that one
invites the one mistake the pre-registration exists to prevent: "fixing" a
tolerance or a reading after seeing which one passes.

Layers, kept apart on purpose:

    O1      the Slater Coulomb integral, against a momentum-space integral
            written here (no production import) and a 30-digit mpmath table
    O2      the transcription of Table I, against eq 17
    O3-O5   literature: the paper's own Tables II-IV at Huber & Herzberg's r_e
    O6      Open Babel's EEM arithmetic -- compatibility only, never authority
    O7-O9   EEM's convention, EEM's matrix, and the bound algorithm
    invariants  shift, conservation, net charge, permutation, reading isolation

Polyatomic rows of Tables III and IV run at Harmony et al. 1979's geometries,
built by `qeq_geometries.py` under amendment A4; ethane, which Harmony lacks,
at Iijima 1973's structure from the 1998 Kuchitsu digest under amendment A5.
"""

from __future__ import annotations

import csv
import functools
import hashlib
import itertools
import json
import math
import pathlib
import subprocess
import sys
import tempfile

import numpy as np
import pytest

from openchem.chem import charge_equilibration as ce

import qeq_geometries

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "charges"
PREREGISTRATION = pathlib.Path(__file__).parent.parent / "benchmarks" / "charges" / "rappe_goddard" / "preregistration.md"


def _rows(name: str) -> list[dict[str, str]]:
    lines = [line for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines))


def _r_e(molecule: str) -> float:
    return next(float(row["r_e_A"]) for row in _rows("geometries.csv") if row["molecule"] == molecule)


def _diatomic(first: str, second: str, distance: float) -> tuple[list[str], np.ndarray]:
    return [first, second], np.array([[0.0, 0.0, 0.0], [0.0, 0.0, distance]])


# =============================================================================
# The fixtures are the ones the pre-registration hashed
# =============================================================================


def test_every_fixture_matches_the_hash_the_preregistration_recorded():
    """A transcription fix is allowed -- with the hash updated in the same
    commit and a CHANGELOG line. A silent edit to make an oracle pass is not."""
    text = PREREGISTRATION.read_text(encoding="utf-8")
    fixtures = sorted(FIXTURES.glob("*.csv"))
    hashed = [f for f in fixtures if f.name != "slater_reference.csv"]
    assert len(hashed) == 16
    for fixture in hashed:
        digest = hashlib.sha256(fixture.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert f"`{fixture.name}`" in text and digest in text, fixture.name


def test_the_module_tables_are_the_transcribed_tables():
    for row in _rows("rappe1991_table1.csv"):
        n, chi, j, radius, zeta = ce.QEQ_TABLE_I[row["element"]]
        assert (n, chi, j, radius, zeta) == (
            int(row["n"]), float(row["chi_eV"]), float(row["J_eV"]), float(row["R_A"]), float(row["zeta_au"])
        ), row["element"]
    assert len(ce.QEQ_TABLE_I) == len(_rows("rappe1991_table1.csv")) == 16
    for row in _rows("bultinck2002a_table1.csv"):
        assert ce.EEM_BULTINCK2002_PART1[row["element"]] == (float(row["chi_star_eV"]), float(row["eta_star_eV"]))
    assert len(ce.EEM_BULTINCK2002_PART1) == 5
    assert ce.HYDROGEN_SETS["experimental"] == (4.5280, 13.8904)
    assert ce.HYDROGEN_SETS["hf"] == (4.7174, 13.4725)


# =============================================================================
# O2: eq 17 regenerates Table I's zeta -- except oxygen, recorded in advance
# =============================================================================


O2_ROUNDING = "STOP RECORD: N misses the pre-registered +-0.0001 by 2.5e-5 (0.90903 vs 0.9089). The tolerance ignored that R is printed to 0.001 A, which alone moves zeta by up to 6.4e-4 -- see the rounding-bound test below and amendment A3"


def _o2_params():
    return [
        pytest.param(row, marks=pytest.mark.xfail(strict=True, reason=O2_ROUNDING)) if row["element"] == "N" else row
        for row in _rows("rappe1991_table1.csv")
    ]


@pytest.mark.parametrize("row", _o2_params(), ids=lambda r: r["element"])
def test_o2_eq17_regenerates_the_printed_zeta(row):
    n, radius, printed = int(row["n"]), float(row["R_A"]), float(row["zeta_au"])
    lam = ce.LAMBDA_HYDROGEN if row["element"] == "H" else ce.LAMBDA_HEAVY
    regenerated = lam * (2 * n + 1) / (2 * radius / ce.QEQ_BOHR_ANGSTROM)
    if row["element"] == "O":
        # Pre-registered exception (section 1): the printed 0.9745 follows from
        # neither lambda. Asserted, so the record cannot quietly change.
        assert row["lambda_printed"] == "none"
        assert abs(regenerated - printed) > 0.002
        assert round(regenerated, 4) == 0.9715
    else:
        assert abs(regenerated - printed) <= 0.0001 + 1e-12, (row["element"], regenerated)


def test_o2_every_zeta_but_oxygen_is_inside_the_rounding_of_its_printed_radius():
    """Amendment A3, written AFTER N failed the pre-registered +-0.0001: the
    bound that the table's own rounding allows. R is printed to 0.001 A and zeta
    to 0.0001, so |eq17(R) - zeta| may reach zeta * 0.0005 / R + 0.00005.
    Oxygen's 0.0030 is four times its bound, so its exception is not rounding."""
    for row in _rows("rappe1991_table1.csv"):
        n, radius, printed = int(row["n"]), float(row["R_A"]), float(row["zeta_au"])
        lam = ce.LAMBDA_HYDROGEN if row["element"] == "H" else ce.LAMBDA_HEAVY
        regenerated = lam * (2 * n + 1) / (2 * radius / ce.QEQ_BOHR_ANGSTROM)
        bound = printed * 0.0005 / radius + 0.00005
        if row["element"] == "O":
            assert abs(regenerated - printed) > 3 * bound
        else:
            assert abs(regenerated - printed) <= bound, row["element"]


def test_the_derived_bounds_reproduce_the_three_eq5_prints():
    assert ce.charge_bounds("Li") == (-7.0, 1.0)
    assert ce.charge_bounds("C") == (-4.0, 4.0)
    assert ce.charge_bounds("O") == (-2.0, 6.0)
    assert ce.charge_bounds("H") == (-1.0, 1.0)
    assert set(ce.VALENCE_ELECTRONS) | {"H"} == set(ce.QEQ_TABLE_I)


# =============================================================================
# O1: the Slater Coulomb integral
# =============================================================================
#
# Oracle 1, momentum space, written here and importing nothing from production:
#   F(k) = a^(2n+1) sin(2n theta) / (2n k (a^2 + k^2)^n),  theta = atan(k/a), a = 2 zeta
#   J(R) = (2/pi) integral_0^inf F_a(k) F_b(k) sin(kR)/(kR) dk        (hartree, bohr)

A0 = 0.52917
R_ANGSTROM = [0.2, 0.2961, 0.4385, 0.6492, 0.9613, 1.4234, 2.1076, 3.1207, 4.6207, 6.8418, 10.1305, 15.0]
NEAR_ZERO_BOHR = [0.0, 1e-6, 1e-4, 5e-4, 9.99e-4, 1.001e-3, 2e-3, 1e-2]
GL32 = np.polynomial.legendre.leggauss(32)


def form_factor(n: int, zeta: float, k: np.ndarray) -> np.ndarray:
    a = 2.0 * zeta
    k = np.asarray(k, dtype=float)
    theta = np.arctan2(k, a)
    safe = np.where(k > 0, k, 1.0)
    value = a ** (2 * n + 1) * np.sin(2 * n * theta) / (2 * n * safe * (a * a + k * k) ** n)
    return np.where(k > 0, value, 1.0)


def _envelope(n: int, zeta: float, k: np.ndarray) -> np.ndarray:
    a = 2.0 * zeta
    return a ** (2 * n + 1) / (2 * n * k * (a * a + k * k) ** n)


def momentum_integral(n_a: int, z_a: float, n_b: int, z_b: float, R: float) -> tuple[float, float]:
    """Returns (J, remainder bound)."""
    width = min(2.0 * min(z_a, z_b) / 4.0, math.pi / R if R > 0 else math.inf)
    x, w = GL32
    total, start = 0.0, 0.0
    while True:
        edges = start + width * np.arange(0, 4097)
        half, mid = width / 2.0, (edges[1:] + edges[:-1]) / 2.0
        k = (mid[:, None] + half * x[None, :]).ravel()
        weight = np.tile(half * w, len(mid))
        sinc = np.sinc(k * R / math.pi) if R > 0 else np.ones_like(k)
        chunk = weight * form_factor(n_a, z_a, k) * form_factor(n_b, z_b, k) * sinc
        ends = edges[1:]
        env = _envelope(n_a, z_a, ends) * _envelope(n_b, z_b, ends) / ((ends * R) if R > 0 else 1.0)
        below = np.nonzero(env < 1e-15)[0]
        if len(below):
            stop = below[0] + 1
            total += float(np.sum(chunk[: stop * len(x)]))
            return (2.0 / math.pi) * total, (2.0 / math.pi) * float(env[below[0]]) * width
        total += float(np.sum(chunk))
        start = edges[-1]


def test_o1_the_form_factor_is_normalised_and_matches_a_direct_transform():
    """k = 0.1, 1, 3, 10, 30 as pre-registered. The direct transform uses
    panels no wider than a quarter of both the density's and the sine's scale,
    because a Gauss-Laguerre rule cannot integrate the oscillation."""
    x, w = GL32
    for n, zeta in itertools.product(range(1, 7), [0.0698, 0.4174, 1.0, 2.0698]):
        assert abs(form_factor(n, zeta, np.array([0.0]))[0] - 1.0) < 1e-14
        assert abs(form_factor(n, zeta, np.array([1e-9]))[0] - 1.0) < 1e-12
        a = 2 * zeta
        extent = (2 * n + 90) / a
        for k in (0.1, 1.0, 3.0, 10.0, 30.0):
            width = min(1.0 / a, math.pi / (2 * k)) / 4
            edges = np.arange(0.0, extent + width, width)
            mid, half = (edges[1:] + edges[:-1]) / 2.0, width / 2.0
            r = (mid[:, None] + half * x[None, :]).ravel()
            rho = a ** (2 * n + 1) * r ** (2 * n - 2) * np.exp(-a * r) / (4 * math.pi * math.factorial(2 * n))
            direct = float(np.sum(np.tile(half * w, len(mid)) * 4 * math.pi * r * r * rho * np.sinc(k * r / math.pi)))
            assert abs(direct - form_factor(n, zeta, np.array([k]))[0]) < 1e-12, (n, zeta, k, direct)


def test_o1_the_momentum_integral_of_point_charges_is_one_over_r():
    """F = 1 must give 1/R, or the oracle's own normalisation is off."""
    for R in (0.5, 3.0, 20.0):
        width = math.pi / R
        x, w = GL32
        edges = width * np.arange(0, 200001)
        mid, half = (edges[1:] + edges[:-1]) / 2.0, width / 2.0
        k = (mid[:, None] + half * x[None, :]).ravel()
        value = (2 / math.pi) * float(np.sum(np.tile(half * w, len(mid)) * np.sinc(k * R / math.pi)))
        # Truncated at K = 200000 half-periods: the sine-integral tail is
        # bounded by 1/(K R^2), times the 2/pi in front.
        assert abs(value - 1.0 / R) < 2.0 / (math.pi * edges[-1] * R * R) + 1e-12


def _o1_grid():
    bohr = [r / A0 for r in R_ANGSTROM]
    pairs = [(a, b) for a in range(1, 7) for b in range(a, 7)]
    combos = [(1.0, 1.0), (0.4174, 1.0726), (1.0726, 0.4174)]
    points = [("main", na, za, nb, zb, R) for (na, nb), (za, zb) in itertools.product(pairs, combos) for R in bohr]
    for za in [0.0698, 0.5698, 1.0698, 1.5698, 2.0698]:
        for nb, zb in [(2, 0.8563), (2, 0.9745), (1, 1.0698), (1, za)]:
            points += [("hydrogen", 1, za, nb, zb, R) for R in bohr]
    for (na, nb), (za, zb) in itertools.product([(1, 1), (1, 2), (2, 2), (3, 5), (6, 6)], combos[:2]):
        points += [("near_zero", na, za, nb, zb, R) for R in NEAR_ZERO_BOHR]
    return points


O1_GRID = _o1_grid()


def test_o1_production_against_the_momentum_space_oracle_over_the_whole_grid():
    """<= 1e-9 in EV, the stricter of the two readings of the pre-registration."""
    worst = (0.0, None)
    for _set, n_a, z_a, n_b, z_b, R in O1_GRID:
        oracle, remainder = momentum_integral(n_a, z_a, n_b, z_b, R)
        production = ce.coulomb_pair_integral(n_a, z_a, n_b, z_b, R)
        assert remainder < 1e-12, (n_a, z_a, n_b, z_b, R, remainder)
        difference = abs(production - oracle) * ce.HARTREE_EV
        if difference > worst[0]:
            worst = (difference, (n_a, z_a, n_b, z_b, R))
    assert worst[0] <= 1e-9, worst


def test_o1_production_against_the_frozen_mpmath_table():
    table = FIXTURES / "slater_reference.csv"
    header = [line for line in table.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
    assert any("mpmath" in line and "dps 30" in line for line in header)
    rows = _rows("slater_reference.csv")
    assert len(rows) == len(O1_GRID)
    worst = (0.0, None)
    for row in rows:
        reference = float(row["J_hartree"])
        production = ce.coulomb_pair_integral(int(row["n_a"]), float(row["zeta_a"]), int(row["n_b"]), float(row["zeta_b"]), float(row["R_bohr"]))
        difference = abs(production - reference) * ce.HARTREE_EV
        if difference > worst[0]:
            worst = (difference, row)
    assert worst[0] <= 1e-9, worst


def test_o1_the_near_zero_branch_is_really_reached_and_not_everywhere():
    for n_a, n_b in [(1, 1), (3, 5)]:
        ce.NEAR_ZERO_BRANCH_USES["count"] = 0
        ce.coulomb_pair_integral(n_a, 1.0, n_b, 1.0, 5e-4)
        assert ce.NEAR_ZERO_BRANCH_USES["count"] > 0
        ce.NEAR_ZERO_BRANCH_USES["count"] = 0
        ce.coulomb_pair_integral(n_a, 1.0, n_b, 1.0, 2e-3)
        hits = ce.NEAR_ZERO_BRANCH_USES["count"]
        assert hits < 32 + 64, "every node took the branch at R >= 1e-3"


def test_o1_roothaan_closed_form_for_equal_1s_exponents():
    for zeta in (0.5, 1.0, 1.0698, 2.0):
        assert abs(ce.coulomb_pair_integral(1, zeta, 1, zeta, 0.0) - 5 * zeta / 8) < 1e-12
        for R in (0.01, 0.3, 1.0, 2.5, 7.0, 20.0):
            closed = 1 / R - math.exp(-2 * zeta * R) * (1 / R + 11 * zeta / 8 + 3 * zeta**2 * R / 4 + zeta**3 * R**2 / 6)
            assert abs(ce.coulomb_pair_integral(1, zeta, 1, zeta, R) - closed) < 1e-12, (zeta, R)


def test_o1_symmetric_in_its_two_densities_and_coulombic_far_apart():
    for (n_a, z_a), (n_b, z_b) in itertools.combinations([(1, 1.0698), (2, 0.8563), (3, 0.9154), (6, 0.5663), (5, 1.0726)], 2):
        for R in (0.4, 2.0, 6.0):
            assert abs(ce.coulomb_pair_integral(n_a, z_a, n_b, z_b, R) - ce.coulomb_pair_integral(n_b, z_b, n_a, z_a, R)) < 1e-12
        far = 15.0 / A0 * 3
        assert abs(ce.coulomb_pair_integral(n_a, z_a, n_b, z_b, far) * far - 1.0) < 1e-9


# =============================================================================
# O3: Table II, the alkali-metal halides -- no hydrogen, no bounds, n up to 6
# =============================================================================


@pytest.mark.parametrize("row", _rows("rappe1991_table2.csv"), ids=lambda r: r["molecule"])
def test_o3_table_ii_at_huber_herzberg_distances(row):
    elements, coords = _diatomic(row["metal"], row["halogen"], _r_e(row["molecule"]))
    # Table II prints both readings side by side, so each column is held to its own.
    table = ce.qeq_charges(elements, coords, 0.0, readings=ce.PREREGISTERED)
    eq17_prime = ce.qeq_charges(elements, coords, 0.0, readings=ce.ADOPTED)
    assert table.status == eq17_prime.status == "converged"
    assert not table.clamped and not table.bound_extension_used
    assert abs(table.charges[0] - float(row["Q_QEq"])) <= 0.001, (table.charges[0], row["Q_QEq"])
    assert abs(eq17_prime.charges[0] - float(row["Q_lambda_0_5"])) <= 0.001, (eq17_prime.charges[0], row["Q_lambda_0_5"])


@pytest.mark.parametrize("row", _rows("rappe1991_table2.csv"), ids=lambda r: r["molecule"])
def test_o3_eq18_from_the_fixture_with_the_oracle_integral_agrees_with_the_general_solver(row):
    metal, halogen = row["metal"], row["halogen"]
    table = {r["element"]: r for r in _rows("rappe1991_table1.csv")}
    m, x = table[metal], table[halogen]
    distance = _r_e(row["molecule"]) / A0
    j_mx, _ = momentum_integral(int(m["n"]), float(m["zeta_au"]), int(x["n"]), float(x["zeta_au"]), distance)
    eq18 = (float(x["chi_eV"]) - float(m["chi_eV"])) / (float(m["J_eV"]) + float(x["J_eV"]) - 2 * j_mx * 27.211386)
    elements, coords = _diatomic(metal, halogen, _r_e(row["molecule"]))
    solver = ce.qeq_charges(elements, coords, 0.0, readings=ce.PREREGISTERED)  # the fixture's printed zeta
    assert abs(solver.charges[0] - eq18) <= 1e-8
    assert abs(solver.charges[0] + solver.charges[1]) < 1e-12  # eq 18: Q_X = -Q_M


# =============================================================================
# O4 / O5: Tables III and IV -- the diatomics now, the polyatomics after Harmony
# =============================================================================

DIATOMIC_HYDRIDES = {"HF": ("H", "F"), "LiH": ("Li", "H"), "ClH": ("H", "Cl")}
GEOMETRY_NAME = {"HF": "HF", "LiH": "LiH", "ClH": "HCl"}
COLUMNS = (("QEq", "experimental"), ("QEqHF", "hf"))


@functools.lru_cache(maxsize=None)
def _solved(molecule: str, hydrogen: str):
    """(charges, Table IV printed_order -> atom indices) under ADOPTED, at the geometry
    amendment A4 builds. Diatomics use Huber & Herzberg's r_e."""
    if molecule in DIATOMIC_HYDRIDES:
        elements, coords = _diatomic(*DIATOMIC_HYDRIDES[molecule], _r_e(GEOMETRY_NAME[molecule]))
        mapping = {1: [elements.index("H")]}
    else:
        elements, coords, mapping, _types = qeq_geometries.build(qeq_geometries.TABLE_NAMES[molecule])
    result = ce.qeq_charges(elements, coords, 0.0, hydrogen=hydrogen)
    return result, mapping


#: STOP RECORD (pre-registration section 8, amendment A6): the Table III and IV
#: cells ADOPTED (lambda = 1/2, eq 17') misses, with its value. Measured
#: 2026-09-14. The pre-registered reading missed 43 of these test cells (9 in
#: Table III, 34 in Table IV); its values are in
#: benchmarks/charges/rappe_goddard/README.md and oracle.py still prints them.
ADOPTED_MISSES_III = {
    ("HF", "QEqHF"): 0.4671, ("LiH", "QEq"): None, ("LiH", "QEqHF"): None,
    ("H2O", "QEqHF"): 0.3536, ("NH3", "QEqHF"): 0.2354, ("CH4", "QEqHF"): 0.1292,
}
ADOPTED_MISSES_IV = {
    ("H3COH", 1, "QEqHF"): 0.3561, ("H3COH", 3, "QEqHF"): -0.104, ("H3COH", 5, "QEqHF"): 0.1737,
    ("H2NC(O)H", 2, "QEq"): 0.4011, ("H2NC(O)H", 3, "QEqHF"): -0.6233,
    ("SiH4", 1, "QEq"): -0.0454, ("SiH4", 1, "QEqHF"): -0.0758,
}


def _o4_params():
    params = []
    for row in _rows("rappe1991_table3.csv"):
        for column, hydrogen in COLUMNS:
            key = (row["molecule"], column)
            marks = [pytest.mark.xfail(strict=True, reason=f"STOP RECORD: ADOPTED gives {ADOPTED_MISSES_III[key]} against {row[column]}" if ADOPTED_MISSES_III[key] is not None
                                       else "STOP RECORD: no reading converges; near the printed -0.767 J_Li + J_HH(Q) - 2 J_LiH is 0.28 eV under P, where 1.98 would be needed")] if key in ADOPTED_MISSES_III else []
            params.append(pytest.param(row, column, hydrogen, marks=marks, id=f"{row['molecule']}-{column}"))
    return params


@pytest.mark.parametrize("row,column,hydrogen", _o4_params())
def test_o4_table_iii_hydrogen_charges(row, column, hydrogen):
    tolerance = 0.001 if row["molecule"] in DIATOMIC_HYDRIDES else 0.002
    result, mapping = _solved(row["molecule"], hydrogen)
    assert result.status == "converged"
    assert not result.bound_extension_used
    for atom in mapping[1]:
        assert abs(result.charges[atom] - float(row[column])) <= tolerance, (result.charges[atom], row[column])


def _o5_params():
    params = []
    for row in _rows("rappe1991_table4.csv"):
        if row["status"] != "printed":
            continue
        for column, hydrogen in COLUMNS:
            key = (row["molecule"], int(row["printed_order"]), column)
            marks = [pytest.mark.xfail(strict=True, reason=f"STOP RECORD: ADOPTED gives {ADOPTED_MISSES_IV[key]} against {row[column]}")] if key in ADOPTED_MISSES_IV else []
            params.append(pytest.param(row, column, hydrogen, marks=marks, id=f"{row['molecule']}-{row['printed_order']}-{column}"))
    return params


@pytest.mark.parametrize("row,column,hydrogen", _o5_params())
def test_o5_table_iv_charges(row, column, hydrogen):
    """Every atom a printed label covers must match (amendment A4)."""
    result, mapping = _solved(row["molecule"], hydrogen)
    assert result.status == "converged"
    assert not result.bound_extension_used
    for atom in mapping[int(row["printed_order"])]:
        assert abs(result.charges[atom] - float(row[column])) <= 0.01, (atom, result.charges[atom], row[column])


def test_ethane_is_iijima_1973_rz_staggered():
    elements, coords, _mapping, types = qeq_geometries.build("C2H6")
    assert types == {"CC": "rz", "CH": "rz", "HCH": "theta_z"}
    assert abs(np.linalg.norm(coords[1] - coords[0]) - 1.5323) < 1e-12
    assert all(abs(np.linalg.norm(coords[h] - coords[0 if h < 5 else 1]) - 1.1017) < 1e-12 for h in range(2, 8))
    u, v = coords[2] - coords[0], coords[3] - coords[0]
    assert abs(math.degrees(math.acos(u @ v / np.linalg.norm(u) / np.linalg.norm(v))) - 107.30) < 1e-9
    # staggered: an upper H sits 60 degrees round from each lower one, seen down C-C
    lower, upper = math.atan2(coords[2][1], coords[2][0]), math.atan2(coords[5][1], coords[5][0])
    assert abs(math.degrees((upper - lower) % (2 * math.pi / 3)) - 60.0) < 1e-9


def test_every_polyatomic_geometry_reproduces_its_harmony_parameters():
    """The builder is held to the fixture: every bond it builds is the chosen
    printed length, so a construction slip cannot pose as a QEq result."""
    for name in qeq_geometries.TABLE_NAMES.values():
        if name == "C2H6":
            continue  # its own fixture; held by the ethane test below
        elements, coords, _mapping, _types = qeq_geometries.build(name)
        chosen, _ = qeq_geometries.parameters(name)
        lengths = {round(float(v), 6) for k, v in chosen.items() if k not in ("HOH", "HNH", "HPH", "HCH", "OCO", "HCO", "COH", "H1NH2", "H1NC", "NCO", "NCH", "HCC", "phi")}
        built = {round(float(np.linalg.norm(coords[i] - coords[j])), 6) for i, j in itertools.combinations(range(len(elements)), 2)}
        assert lengths <= built, (name, lengths - built)


# =============================================================================
# O6: Open Babel's EEM -- COMPATIBILITY ONLY
# =============================================================================

CHILD = pathlib.Path(__file__).parent.parent / "benchmarks" / "charges" / "openbabel_child.py"


def test_o6_open_babel_eem_given_table_1_computes_the_same_arithmetic():
    """This says OpenChem and Open Babel build the same linear system from the
    same numbers. It says NOTHING about Bultinck: O7 and O8 do that."""
    openbabel = pytest.importorskip("openbabel")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    data = pathlib.Path(openbabel.__file__).parent / "bin" / "data"
    if not (data / "eem.txt").exists():
        pytest.skip("this Open Babel install keeps no eem.txt where the child looks")
    with tempfile.TemporaryDirectory() as scratch:
        scratch = pathlib.Path(scratch)
        for item in data.iterdir():
            if item.is_file():
                (scratch / item.name).write_bytes(item.read_bytes())
        lines = [f"kappa\t{ce.EEM_BOHR_ANGSTROM}"]
        for element, (chi, eta) in ce.EEM_BULTINCK2002_PART1.items():
            lines.append(f"{element}\t*\t{chi / ce.HARTREE_EV:.12f}\t{2 * eta / ce.HARTREE_EV:.12f}")
        (scratch / "eem.txt").write_text("\n".join(lines) + "\n")
        child = scratch / "child.py"
        child.write_text(CHILD.read_text().replace('pathlib.Path(ob.__file__).parent / "bin" / "data"', f"pathlib.Path(r'{scratch}')"))
        worst = 0.0
        for smiles in ("CO", "CC(=O)O", "c1ccncc1", "[NH3+]CC(=O)[O-]", "Fc1ccccc1", "NC=O", "CC(=O)[O-]"):
            molecule = Chem.AddHs(Chem.MolFromSmiles(smiles))
            AllChem.EmbedMolecule(molecule, randomSeed=11)
            block = Chem.MolToMolBlock(molecule)
            (scratch / "in.mol").write_text(block)
            run = subprocess.run([sys.executable, str(child), "python_after_import_win", "eem", str(scratch / "in.mol")],
                                 capture_output=True, text=True, timeout=120)
            line = next(l for l in run.stdout.splitlines() if l.startswith("RESULT "))
            seen = json.loads(line[7:])["atoms"]
            elements = [Chem.GetPeriodicTable().GetElementSymbol(a["z"]) for a in seen]
            coords = np.array([a["xyz"] for a in seen])
            ours = ce.eem_charges(elements, coords, float(sum(a["fc"] for a in seen)))
            worst = max(worst, float(np.max(np.abs(ours.charges - np.array([a["q"] for a in seen])))))
    assert worst <= 1e-6, worst


# =============================================================================
# O7 / O8: EEM's convention and its matrix
# =============================================================================


def _eem_diatomic_closed_form(first, second, distance_angstrom, net, diagonal_factor=2.0):
    """q1 from Bultinck part I eq 3 for two atoms, atomic units, with the
    diagonal coefficient as a parameter so the wrong convention can be built."""
    chi1, eta1 = (v / 27.211386 for v in ce.EEM_BULTINCK2002_PART1[first])
    chi2, eta2 = (v / 27.211386 for v in ce.EEM_BULTINCK2002_PART1[second])
    inv_r = ce.EEM_BOHR_ANGSTROM / distance_angstrom
    d1, d2 = diagonal_factor * eta1, diagonal_factor * eta2
    return (chi2 - chi1 + (d2 - inv_r) * net) / (d1 + d2 - 2 * inv_r)


@pytest.mark.parametrize("pair,distance,net", [(("H", "F"), 0.9168, 0.0), (("C", "O"), 1.128, 0.0), (("N", "H"), 1.03, 1.0), (("O", "H"), 0.97, -1.0)])
def test_o7_eq3_diatomic_closed_form_and_the_wrong_convention_fails(pair, distance, net):
    elements, coords = _diatomic(*pair, distance)
    matrix, _ = ce.eem_system(elements, coords, net)
    assert np.linalg.cond(matrix) < 1e3
    ours = ce.eem_charges(elements, coords, net).charges[0]
    assert abs(ours - _eem_diatomic_closed_form(*pair, distance, net)) <= 1e-12
    assert abs(ours - _eem_diatomic_closed_form(*pair, distance, net, diagonal_factor=1.0)) > 1e-3


def test_o8_the_eem_matrix_is_eq3_entry_by_entry():
    elements = ["O", "H", "H"]
    coords = np.array([[0.0, 0.0, 0.0], [0.9572, 0.0, 0.0], [-0.24, 0.9266, 0.0]])
    matrix, rhs = ce.eem_system(elements, coords, -1.0)
    assert matrix.shape == (4, 4) and rhs.shape == (4,)
    assert np.linalg.cond(matrix) < 1e3
    bohr = 0.529177210903
    for i, element in enumerate(elements):
        chi, eta = ce.EEM_BULTINCK2002_PART1[element]
        assert matrix[i, i] == pytest.approx(2 * eta / 27.211386, abs=1e-15)
        assert rhs[i] == pytest.approx(-chi / 27.211386, abs=1e-15)
        for j in range(3):
            if j != i:
                assert matrix[i, j] == pytest.approx(bohr / float(np.linalg.norm(coords[i] - coords[j])), abs=1e-15)
    assert list(matrix[:3, 3]) == [-1.0, -1.0, -1.0]  # multiplier COLUMN
    assert list(matrix[3, :3]) == [1.0, 1.0, 1.0]  # constraint ROW
    assert matrix[3, 3] == 0.0 and rhs[3] == -1.0
    expected = np.linalg.solve(matrix, rhs)[:3]
    assert np.max(np.abs(ce.eem_charges(elements, coords, -1.0).charges - expected)) <= 1e-12
    # A transposed build (row and column swapped) is a different system.
    transposed = matrix.copy()
    transposed[:3, 3], transposed[3, :3] = matrix[3, :3], matrix[:3, 3]
    assert np.max(np.abs(np.linalg.solve(transposed, rhs)[:3] - expected)) > 1e-3


# =============================================================================
# O9: the bound algorithm against brute-force KKT
# =============================================================================


def _synthetic_bounded_systems():
    """200 systems, seed 20260914, BUILT so a bound binds: a random SPD C, and
    chi scaled up until the unconstrained optimum leaves its box."""
    rng = np.random.default_rng(20260914)
    boxes = [(-1.0, 1.0), (-2.0, 6.0), (-4.0, 4.0), (-7.0, 1.0)]
    systems = []
    while len(systems) < 200:
        count = int(rng.integers(3, 7))
        m = rng.normal(size=(count, count))
        hardness = m @ m.T + count * np.eye(count)
        chi = rng.normal(size=count)
        net = float(rng.integers(-1, 2))
        box = [boxes[int(b)] for b in rng.integers(0, len(boxes), size=count)]
        lower, upper = np.array([b[0] for b in box]), np.array([b[1] for b in box])
        for scale in (5.0, 10.0, 20.0, 40.0, 80.0):
            q = ce.solve_bounded(hardness, chi * scale, net, np.full(count, -1e9), np.full(count, 1e9)).charges
            if np.any(q < lower) or np.any(q > upper):
                systems.append((hardness, chi * scale, net, lower, upper))
                break
    return systems


def _kkt_optimum(hardness, chi, net, lower, upper):
    count = len(chi)
    best = None
    for assignment in itertools.product((0, 1, 2), repeat=count):  # free, lower, upper
        fixed = {i: (lower[i] if a == 1 else upper[i]) for i, a in enumerate(assignment) if a}
        free = [i for i in range(count) if i not in fixed]
        if not free:
            continue
        q = np.zeros(count)
        for i, v in fixed.items():
            q[i] = v
        size = len(free)
        system = np.zeros((size + 1, size + 1))
        system[:size, :size] = hardness[np.ix_(free, free)]
        system[:size, size] = -1.0
        system[size, :size] = 1.0
        shifted = chi[free] + (hardness[np.ix_(free, list(fixed))] @ np.array(list(fixed.values())) if fixed else 0.0)
        rhs = np.concatenate([-shifted, [net - sum(fixed.values())]])
        solution = np.linalg.solve(system, rhs)
        q[free] = solution[:size]
        mu = solution[size]
        if np.any(q[free] < lower[free] - 1e-12) or np.any(q[free] > upper[free] + 1e-12):
            continue
        gradient = chi + hardness @ q - mu
        if any(gradient[i] < -1e-9 for i, a in enumerate(assignment) if a == 1):
            continue
        if any(gradient[i] > 1e-9 for i, a in enumerate(assignment) if a == 2):
            continue
        energy = float(chi @ q + 0.5 * q @ hardness @ q)
        if best is None or energy < best[0] - 1e-12:
            best = (energy, q)
    return best[1]


SYNTHETIC = _synthetic_bounded_systems()


@pytest.mark.xfail(strict=True, reason="STOP RECORD (pre-registration section 8): the never-release fixing misses the constrained optimum in 28 of 200 synthetic systems, and in 26 of them an atom it fixed wants back inside. The algorithm is not swapped silently; it goes to Alex")
def test_o9_fix_and_re_solve_reaches_the_constrained_optimum_on_every_synthetic_case():
    disagreements = []
    for index, (hardness, chi, net, lower, upper) in enumerate(SYNTHETIC):
        ours = ce.solve_bounded(hardness, chi, net, lower, upper).charges
        optimum = _kkt_optimum(hardness, chi, net, lower, upper)
        if np.max(np.abs(ours - optimum)) > 1e-10:
            disagreements.append((index, float(np.max(np.abs(ours - optimum)))))
    assert not disagreements, f"{len(disagreements)} of {len(SYNTHETIC)}: {disagreements[:5]}"


def test_o9_where_fixing_reaches_the_optimum_clipping_does_not_stand_in_for_it():
    """The guard a clip-and-renormalise mutation must trip. The strict xfail
    above cannot: it already fails. So on the cases where the paper's fixing
    DOES reach the constrained optimum, production must match that optimum,
    and clipping must miss it at least once."""
    agreeing = clip_misses = 0
    for hardness, chi, net, lower, upper in SYNTHETIC:
        optimum = _kkt_optimum(hardness, chi, net, lower, upper)
        ours = ce.solve_bounded(hardness, chi, net, lower, upper).charges
        if np.max(np.abs(ours - optimum)) > 1e-10:
            continue
        agreeing += 1
        free = np.linalg.solve(
            np.block([[hardness, -np.ones((len(chi), 1))], [np.ones((1, len(chi))), np.zeros((1, 1))]]),
            np.concatenate([-chi, [net]]),
        )[:-1]
        clipped = np.clip(free, lower, upper)
        inside = (clipped > lower) & (clipped < upper)
        if np.any(inside):
            clipped[inside] += (net - clipped.sum()) / np.count_nonzero(inside)
        clip_misses += int(np.max(np.abs(clipped - optimum)) > 1e-3)
    assert agreeing >= 150 and clip_misses > 0, (agreeing, clip_misses)


def test_o9_clip_and_renormalise_is_a_different_answer():
    differences = []
    for hardness, chi, net, lower, upper in SYNTHETIC:
        free = ce.solve_bounded(hardness, chi, net, np.full(len(chi), -1e9), np.full(len(chi), 1e9)).charges
        clipped = np.clip(free, lower, upper)
        inside = (clipped > lower) & (clipped < upper)
        if np.any(inside):
            clipped[inside] += (net - clipped.sum()) / np.count_nonzero(inside)
        differences.append(float(np.max(np.abs(clipped - _kkt_optimum(hardness, chi, net, lower, upper)))))
    assert max(differences) > 1e-3


# =============================================================================
# Invariants
# =============================================================================

WATER = (["O", "H", "H"], np.array([[0.0, 0.0, 0.0], [0.9572, 0.0, 0.0], [-0.2400, 0.9266, 0.0]]))
FORMALDEHYDE = (["C", "O", "H", "H"], np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.208], [0.0, 0.943, -0.587], [0.0, -0.943, -0.587]]))


def test_shift_invariance_eem_and_qeq_without_bounds():
    elements, coords = FORMALDEHYDE
    matrix, rhs = ce.eem_system(elements, coords, 0.0)
    shifted = rhs.copy()
    shifted[:-1] -= 0.37
    base, moved = np.linalg.solve(matrix, rhs), np.linalg.solve(matrix, shifted)
    assert np.max(np.abs(base[:-1] - moved[:-1])) < 1e-12 and abs(base[-1] - moved[-1]) > 0.3
    hardness, chi, _ = ce.qeq_hardness_matrix(elements, coords, {})
    wide = np.full(4, -1e9), np.full(4, 1e9)
    a = ce.solve_bounded(hardness, chi, 0.0, *wide).charges
    b = ce.solve_bounded(hardness, chi + 2.5, 0.0, *wide).charges
    assert np.max(np.abs(a - b)) < 1e-12


@pytest.mark.parametrize("net", [0.0, 1.0, -1.0])
def test_conservation_and_the_net_charge_is_not_ignored(net):
    elements, coords = FORMALDEHYDE
    for result in (ce.qeq_charges(elements, coords, net), ce.eem_charges(elements, coords, net)):
        assert result.status == "converged"
        assert abs(result.charges.sum() - net) < 1e-10  # necessary, never sufficient
    if net:
        neutral = ce.qeq_charges(elements, coords, 0.0).charges
        assert np.max(np.abs(ce.qeq_charges(elements, coords, net).charges - neutral)) > 0.05


def test_both_solvers_are_permutation_equivariant():
    elements, coords = FORMALDEHYDE
    order = [2, 0, 3, 1]
    for solve in (ce.qeq_charges, ce.eem_charges):
        base = solve(elements, coords, 0.0).charges
        permuted = solve([elements[i] for i in order], coords[order], 0.0).charges
        for new, old in enumerate(order):
            assert abs(permuted[new] - base[old]) < 1e-12


def test_the_r1_alternate_changes_only_hydrogen_off_diagonal_entries():
    elements, coords = FORMALDEHYDE
    charges = {2: 0.11, 3: 0.12}
    primary, _, _ = ce.qeq_hardness_matrix(elements, coords, charges, readings=ce.PREREGISTERED)
    alternate, _, _ = ce.qeq_hardness_matrix(elements, coords, charges, readings=ce.ALTERNATES["R1"])
    for i, j in itertools.product(range(4), repeat=2):
        involves_h = i != j and (elements[i] == "H" or elements[j] == "H")
        if involves_h:
            assert primary[i, j] != alternate[i, j]
        else:
            assert primary[i, j] == alternate[i, j]
    at_zero_p, _, _ = ce.qeq_hardness_matrix(elements, coords, {}, readings=ce.PREREGISTERED)
    at_zero_a, _, _ = ce.qeq_hardness_matrix(elements, coords, {}, readings=ce.ALTERNATES["R1"])
    assert np.array_equal(at_zero_p, at_zero_a)


def test_the_two_hydrogen_sets_are_different_calculations():
    elements, coords = _diatomic("H", "F", _r_e("HF"))
    experimental = ce.qeq_charges(elements, coords, hydrogen="experimental")
    hf = ce.qeq_charges(elements, coords, hydrogen="hf")
    assert experimental.status == hf.status == "converged"
    difference = abs(experimental.charges[0] - hf.charges[0])
    print(f"HF: Q_H experimental {experimental.charges[0]:.6f}, hf {hf.charges[0]:.6f}, difference {difference:.2e} e")
    assert difference > 1e-6


def test_refusals_name_what_they_refuse():
    boron = ce.qeq_charges(["B", "H"], np.array([[0, 0, 0], [0, 0, 1.2]]))
    assert boron.status == ce.REFUSE_ELEMENT_NOT_PARAMETERISED and "B" in boron.message and boron.charges is None
    silicon = (["Si", "H"], np.array([[0, 0, 0], [0, 0, 1.48]]))
    assert ce.qeq_charges(*silicon).status == "converged"
    assert ce.eem_charges(*silicon).status == ce.REFUSE_ELEMENT_NOT_PARAMETERISED
    overlap = ce.qeq_charges(["C", "O"], np.array([[0, 0, 0], [0, 0, 0.05]]))
    assert overlap.status == ce.REFUSE_OVERLAPPING_ATOMS and overlap.charges is None
    capped = ce.qeq_charges(*WATER, max_outer=2)
    assert capped.status == ce.REFUSE_NOT_CONVERGED and capped.charges is None and capped.trace_class


def test_every_trace_row_names_its_iteration_and_pass():
    result = ce.qeq_charges(*WATER)
    assert result.status == "converged"
    assert result.iterations >= 2
    assert all({"hydrogen_iteration", "active_set_pass", "dQ_H", "dzeta_H", "dhardness_diag_H"} <= set(row) for row in result.trace)
    assert result.solver_to_source == [0, 1, 2]


# =============================================================================
# Amendment A7: diagnostics of the open problems -- nothing here changes a result
# =============================================================================

import qeq_fixed_point as fp  # noqa: E402


@functools.lru_cache(maxsize=None)
def _lih_map(hydrogen: str) -> fp.HydrogenMap:
    return fp.HydrogenMap(*_diatomic("Li", "H", _r_e("LiH")), hydrogen)


@functools.lru_cache(maxsize=None)
def _lih_root(hydrogen: str) -> float:
    F = _lih_map(hydrogen)
    found = fp.roots(F, *fp.scan(F))
    assert [r.kind for r in found] == ["root"], found  # one root, no tangency candidate
    return found[0].q


def test_F_is_the_production_step():
    """Iterating A7's map from zero IS the production solver's sequence: its
    n-th iterate is the charge `qeq_charges` returns after n iterations."""
    for elements, coords in (_diatomic("H", "F", _r_e("HF")), WATER):
        F = fp.HydrogenMap(elements, coords)
        production = ce.qeq_charges(elements, coords)
        assert production.status == "converged"
        # tolerance 0: run exactly as many steps as production took
        run = fp.iterate(F, 1.0, max_iterations=production.iterations, tolerance=0.0)
        assert len(run.history) == production.iterations + 1
        assert np.max(np.abs(run.history[production.iterations] - production.charges[F.hydrogens])) <= 1e-12


@pytest.mark.parametrize("hydrogen,expected", [("experimental", -0.973), ("hf", -0.982)])
def test_lih_self_consistent_charge_exists(hydrogen, expected):
    """Q-A. Measured 2026-09-14: -0.973740 and -0.982743, exactly one root on
    [-1, +1] each, no tangency candidate, and no bound active near Q*."""
    F = _lih_map(hydrogen)
    q = _lih_root(hydrogen)
    assert abs(fp.g(F, q)) <= 1e-8
    assert abs(q - expected) <= 0.002
    assert F.solve(q).passes[-1] == {}
    assert fp.active_sets_near(F, q) == {frozenset()}


@pytest.mark.parametrize("hydrogen,printed", [("experimental", -0.767), ("hf", -0.679)])
def test_lih_printed_charge_is_not_self_consistent(hydrogen, printed):
    """Q-B. g(-0.767) = -0.233 and g(-0.679) = -0.321 under ADOPTED."""
    assert abs(fp.g(_lih_map(hydrogen), printed)) >= 0.05


@pytest.mark.parametrize("hydrogen,measured", [("experimental", -14.0606), ("hf", -14.1175)])
def test_lih_plain_iteration_is_locally_unstable(hydrogen, measured):
    """Q-C's cause. A7 PREDICTED -14.24 and -14.36 +- 0.1, from an earlier
    unregistered estimate taken at a coarser root, and that prediction FAILED:
    the frozen difference gives the values here. The instability (|s| > 1)
    holds either way; the value and the property are both asserted."""
    s = fp.slopes(_lih_map(hydrogen), _lih_root(hydrogen))
    assert max(s.values()) - min(s.values()) <= 0.05
    assert abs(s[1e-5] - measured) <= 0.01
    assert abs(s[1e-5]) > 1


@pytest.mark.parametrize("hydrogen", ["experimental", "hf"])
def test_mixing_stability_matches_its_prediction(hydrogen):
    """Numeric slope -> analytic |1 - alpha(1 - s)| < 1 -> observed trajectory.
    Where mixing converges it reaches Q*, never the printed charge."""
    F = _lih_map(hydrogen)
    q_star = _lih_root(hydrogen)
    slope = fp.slopes(F, q_star)[1e-5]
    for alpha in (1.0, 0.75, 0.5, 0.25, 0.1, 0.05):
        run = fp.iterate(F, alpha)
        assert run.converged == fp.predicted_to_converge(alpha, slope), alpha
        if run.converged:
            assert abs(run.q[0] - q_star) <= 1e-7 and run.residual <= 1e-8


def test_mixing_moves_the_path_not_the_fixed_point():
    """Independently converged at alpha = 1 and 0.5. The stored solver is a
    separate, third comparison."""
    cases = [_diatomic("H", "F", _r_e("HF"))] + [qeq_geometries.build(name)[:2] for name in ("H2O", "NH3", "CH4")]
    for elements, coords in cases:
        for hydrogen in ("experimental", "hf"):
            F = fp.HydrogenMap(elements, coords, hydrogen)
            plain, mixed = fp.iterate(F, 1.0), fp.iterate(F, 0.5)
            assert plain.converged and mixed.converged
            assert np.max(np.abs(plain.q - mixed.q)) <= 1e-7
            assert np.max(np.abs(plain.q - ce.qeq_charges(elements, coords, hydrogen=hydrogen).charges[F.hydrogens])) <= 1e-7


def test_a_non_fixed_point_keeps_its_residual():
    """Mixing cannot validate a target: the printed LiH charge, or any other
    charge that is not Q*, keeps its residual, and no converging alpha lands
    near the printed value."""
    F = _lih_map("experimental")
    for fake in (-0.767, -0.9, -0.5):
        assert abs(fp.g(F, fake)) >= 1e-3
    for alpha in (0.1, 0.05):
        assert abs(fp.iterate(F, alpha).q[0] - (-0.767)) > 0.2


def test_the_convergence_test_needs_the_residual_as_well_as_the_step():
    """A tiny step alone is not a fixed point: with a vanishing alpha the step
    is under 1e-8 at Q = 0, where F(Q) - Q is still large."""
    run = fp.iterate(_lih_map("experimental"), 1e-9, max_iterations=3)
    assert run.step <= 1e-8 and run.residual > 1e-3 and not run.converged


def test_ramachandran_1996_water_at_its_stated_geometry():
    """Their Table 8: QEq H = 0.353 at O-H 0.9572 A and H-O-H 104.52 deg,
    stated in their section VIII. Measured 0.3532."""
    half = math.radians(104.52 / 2)
    coords = np.array([[0, 0, 0], [0.9572 * math.sin(half), 0, 0.9572 * math.cos(half)], [-0.9572 * math.sin(half), 0, 0.9572 * math.cos(half)]])
    result = ce.qeq_charges(["O", "H", "H"], coords, hydrogen="experimental")
    assert result.status == "converged"
    assert all(abs(q - 0.353) <= 0.001 for q in result.charges[1:])


def test_no_silane_geometry_in_the_a7_sweep_reaches_the_printed_charge():
    """Diagnostic, not fitting: Si-H 1.45-1.51 A with a D2d distortion of +-5
    deg gives Q_H -0.046 to -0.045 (experimental) and -0.077 to -0.074 (hf).
    Geometry cannot reach the printed +0.13 / +0.11, nor change the sign."""
    for hydrogen in ("experimental", "hf"):
        values = []
        for bond in (1.45, 1.48, 1.51):
            for delta in (-5.0, -2.5, 0.0, 2.5, 5.0):
                theta = math.radians(109.4712206 + delta)
                a, c = bond * math.sin(theta / 2), bond * math.cos(theta / 2)
                coords = np.array([[0, 0, 0], [a, 0, c], [-a, 0, c], [0, a, -c], [0, -a, -c]])
                values.extend(ce.qeq_charges(["Si", "H", "H", "H", "H"], coords, hydrogen=hydrogen).charges[1:])
        assert max(values) < 0


#: The polyatomic cells each lambda reading misses, as oracle.py counts them.
PREREGISTERED_POLYATOMIC_MISSES = {
    ("III", "H2O", 1, "QEq"), ("III", "NH3", 1, "QEq"), ("III", "NH3", 1, "QEqHF"), ("III", "CH4", 1, "QEq"), ("III", "CH4", 1, "QEqHF"),
    *{("IV", m, o, c) for m, o, c in [
        ("NH3", 1, "QEq"), ("CH4", 1, "QEq"), ("CH4", 1, "QEqHF"), ("CO2", 1, "QEq"), ("CO2", 1, "QEqHF"), ("H2CO", 1, "QEqHF"),
        ("H2CO", 2, "QEqHF"), ("H3COH", 5, "QEqHF"), ("H2NC(O)H", 1, "QEqHF"), ("H2NC(O)H", 2, "QEq"), ("H2NC(O)H", 2, "QEqHF"),
        ("H2NC(O)H", 3, "QEq"), ("H2NC(O)H", 3, "QEqHF"), ("H2NC(O)H", 4, "QEq"), ("HOC(O)H", 2, "QEq"), ("HOC(O)H", 2, "QEqHF"),
        ("HOC(O)H", 3, "QEqHF"), ("HOC(O)H", 4, "QEq"), ("HOC(O)H", 4, "QEqHF"), ("HOC(O)H", 5, "QEq"), ("H3CCN", 1, "QEqHF"),
        ("H3CCN", 2, "QEq"), ("H3CCN", 2, "QEqHF"), ("H3CCN", 3, "QEq"), ("H3CCN", 3, "QEqHF"), ("H2C=C=O", 1, "QEq"),
        ("H2C=C=O", 1, "QEqHF"), ("H2C=C=O", 2, "QEq"), ("H2C=C=O", 2, "QEqHF"), ("H2C=C=O", 3, "QEq"), ("H2C=C=O", 3, "QEqHF"),
        ("SiH4", 1, "QEq"), ("SiH4", 1, "QEqHF"), ("C2H6", 1, "QEq")]},
}
ADOPTED_POLYATOMIC_MISSES = {
    ("III", "H2O", 1, "QEqHF"), ("III", "NH3", 1, "QEqHF"), ("III", "CH4", 1, "QEqHF"),
    ("IV", "H3COH", 1, "QEqHF"), ("IV", "H3COH", 3, "QEqHF"), ("IV", "H3COH", 5, "QEqHF"), ("IV", "H2NC(O)H", 2, "QEq"),
    ("IV", "H2NC(O)H", 3, "QEqHF"), ("IV", "SiH4", 1, "QEq"), ("IV", "SiH4", 1, "QEqHF"),
}


@functools.lru_cache(maxsize=None)
def _polyatomic(molecule: str, hydrogen: str, reading: str):
    elements, coords, mapping, _ = qeq_geometries.build(qeq_geometries.TABLE_NAMES[molecule])
    readings = ce.PREREGISTERED if reading == "PREREGISTERED" else ce.ADOPTED
    return ce.qeq_charges(elements, coords, 0.0, hydrogen=hydrogen, readings=readings), mapping


@pytest.mark.parametrize("reading,expected", [("PREREGISTERED", PREREGISTERED_POLYATOMIC_MISSES), ("ADOPTED", ADOPTED_POLYATOMIC_MISSES)])
def test_both_lambda_readings_reproduce_their_historical_miss_sets(reading, expected):
    """A6 keeps both readings runnable; this keeps both RESULTS -- 39 of 76 and
    10 of 76, cell for cell, through the same solver path."""
    cells = [("III", r["molecule"], 1, r) for r in _rows("rappe1991_table3.csv") if r["molecule"] in ("H2O", "NH3", "CH4")]
    cells += [("IV", r["molecule"], int(r["printed_order"]), r) for r in _rows("rappe1991_table4.csv")
              if r["status"] == "printed" and r["molecule"] in qeq_geometries.TABLE_NAMES]
    misses = set()
    for table, molecule, order, row in cells:
        tolerance = 0.002 if table == "III" else 0.01
        for column, hydrogen in COLUMNS:
            result, mapping = _polyatomic(molecule, hydrogen, reading)
            if result.charges is None or any(abs(result.charges[i] - float(row[column])) > tolerance for i in mapping[order]):
                misses.add((table, molecule, order, column))
    assert 2 * len(cells) == 76
    assert misses == expected


def test_bakowies_1996_reprints_rappe_goddard_table_i_as_we_transcribed_it():
    """A parameter mismatch would mean a transcription or source-version
    problem, and is kept apart from the charge comparison below."""
    ours = {row["element"]: row for row in _rows("rappe1991_table1.csv")}
    reprint = _rows("bakowies1996_table8_parameters.csv")
    assert [row["element"] for row in reprint] == ["H", "C", "N", "O"]
    for row in reprint:
        if row["element"] == "H":
            assert (float(row["chi_eV"]), float(row["J_eV"])) == ce.HYDROGEN_SETS["experimental"]
        assert (float(row["chi_eV"]), float(row["J_eV"])) == (float(ours[row["element"]]["chi_eV"]), float(ours[row["element"]]["J_eV"]))


def test_bakowies_1996_reprints_rappe_goddard_table_iv_qeqhf_as_we_transcribed_it():
    """Only cells that name their Table IV rows are compared; an averaged cell
    (footnote b) is compared with the mean, at the reprint's two decimals."""
    table4 = {(row["molecule"], row["printed_order"]): row for row in _rows("rappe1991_table4.csv") if row["status"] == "printed"}
    compared = 0
    for row in _rows("bakowies1996_table10_charges.csv"):
        assert (row["geometry_class"], row["hydrogen_set"], row["column"]) == ("exp", "hf", "QEqHF")
        if row["relation"] == "not_in_table4":
            continue
        orders = row["table4_orders"].split(";")
        values = [float(table4[(row["table4_molecule"], order)][row["column"]]) for order in orders]
        assert (row["relation"] == "same") == (len(orders) == 1)
        assert abs(sum(values) / len(values) - float(row["value"])) <= 0.005 + 1e-12, row
        compared += 1
    assert compared == 23


def test_ramachandran_1996_table_3_qeq_column_does_not_conserve_charge():
    """The source audit. Every reference column of both tables sums to zero
    within rounding, and so does Table 2's QEq column; Table 3's QEq column --
    Table 2's numbers again -- sums to -2.208 e. Recorded as internally
    inconsistent with charge conservation, not as a known misprint."""
    totals: dict[tuple[str, str], float] = {}
    for row in _rows("ramachandran1996_tables.csv"):
        key = (row["table"], row["method"])
        totals[key] = totals.get(key, 0.0) + int(row["multiplicity"]) * float(row["value"])
    for (table, method), total in totals.items():
        if (table, method) == ("3", "QEq"):
            assert abs(total - (-2.208)) < 1e-9
        else:
            assert abs(total) <= 0.005, (table, method, total)
    assert len(totals) == 11


def test_ramachandran_1996_gives_silyl_hydrogen_the_sign_we_compute_for_silane():
    """Independent evidence from the Rappé group's own program, five years on:
    every silyl H in O(SiH3)2 is negative. That its silicon parameters are
    1991 Table I's is an inference -- the paper's parameter citation (ref 6)
    points at a catalysis paper."""
    qeq = [row for row in _rows("ramachandran1996_tables.csv") if row["table"] == "2" and row["method"] == "QEq"]
    assert all(float(row["value"]) < 0 for row in qeq if row["atom"].startswith("H"))
    assert float(next(row["value"] for row in qeq if row["atom"] == "Si")) > 0


def test_the_disiloxane_builder_reproduces_almenningen_1963():
    """Every printed parameter, the C3v checksum (H-Si-H 109.04 against the
    printed 109.1 +- 1.29), C2 symmetry, and the in-plane hydrogen as the one
    nearest the 2-fold axis, as the authors' non-firm interpretation says."""
    p = qeq_geometries.disiloxane_parameters()
    elements, coords, groups = qeq_geometries.build_disiloxane()
    assert elements.count("H") == 6 and len(groups["H1"]) == 2 and len(groups["H2"]) == 4

    def angle(a, b, c):
        u, v = coords[a] - coords[b], coords[c] - coords[b]
        return math.degrees(math.acos(u @ v / np.linalg.norm(u) / np.linalg.norm(v)))

    assert all(abs(np.linalg.norm(coords[si] - coords[0]) - p["SiO"]) < 1e-12 for si in (1, 2))
    assert abs(angle(1, 0, 2) - p["SiOSi"]) < 1e-9
    for si, hs in ((1, (3, 4, 5)), (2, (6, 7, 8))):
        assert all(abs(np.linalg.norm(coords[h] - coords[si]) - p["SiH"]) < 1e-12 for h in hs)
        assert all(abs(angle(0, si, h) - p["OSiH"]) < 1e-9 for h in hs)
        assert all(abs(angle(a, si, b) - p["HSiH"]) < 0.1 for a, b in itertools.combinations(hs, 2))
    mirrored = coords * np.array([-1.0, -1.0, 1.0])
    assert max(np.min(np.linalg.norm(coords - m, axis=1)) for m in mirrored) < 1e-12
    # a twisted torsion must keep the C2 axis: +t on one silyl is -t on the other
    for torsion in (30.0, 45.0):
        _, twisted, _ = qeq_geometries.build_disiloxane(torsion=torsion)
        rotated = twisted * np.array([-1.0, -1.0, 1.0])
        assert max(np.min(np.linalg.norm(twisted - m, axis=1)) for m in rotated) < 1e-9, torsion
    axis_distance = lambda i: math.hypot(coords[i][0], coords[i][1])
    assert max(axis_distance(i) for i in groups["H1"]) < min(axis_distance(i) for i in groups["H2"])


RAMACHANDRAN_TABLE_2_QEQ = {"O": -0.636, "Si": 0.420, "H1": -0.021, "H2": -0.040}
DISILOXANE_TOLERANCE = {"O": 0.03, "Si": 0.02, "H1": 0.02, "H2": 0.02}


def _disiloxane(readings=ce.ADOPTED, **geometry):
    elements, coords, groups = qeq_geometries.build_disiloxane(**geometry)
    result = ce.qeq_charges(elements, coords, hydrogen="experimental", readings=readings)
    assert result.status == "converged" and not result.clamped
    return result.charges, coords, groups


def test_disiloxane_signs_match_ramachandran_1996_in_every_a7_geometry():
    """A7's first test, sign before magnitude: every H negative and both Si
    positive at the reference structure, across Si-O-Si 140-180 deg, Si-O
    +-0.02 A, and silyl torsion 0/30/60 deg. HELD."""
    geometries = [{}] + [{"si_o_si": a} for a in (140, 150, 160, 170, 180)] + [{"si_o": 1.614}, {"si_o": 1.654}] + [{"torsion": t} for t in (0, 30, 60)]
    for geometry in geometries:
        charges, _, groups = _disiloxane(**geometry)
        assert all(charges[i] < 0 for i in groups["H1"] + groups["H2"]), geometry
        assert all(charges[i] > 0 for i in groups["Si"]), geometry


@pytest.mark.parametrize("label", ["O", "Si", "H2"])
def test_disiloxane_magnitudes_at_the_reference_conformation(label):
    """A7's second test, at the authors' non-firm conformation (in-plane H
    nearest the 2-fold axis). Measured: O -0.6362, Si +0.4218, H2 -0.0283."""
    charges, _, groups = _disiloxane()
    assert all(abs(charges[i] - RAMACHANDRAN_TABLE_2_QEQ[label]) <= DISILOXANE_TOLERANCE[label] for i in groups[label])


@pytest.mark.xfail(strict=True, reason="STOP RECORD (A7): at the reference conformation the in-plane H is -0.0472 against H1's -0.021, outside +-0.02")
def test_disiloxane_h1_at_the_reference_conformation():
    charges, _, groups = _disiloxane()
    assert all(abs(charges[i] - RAMACHANDRAN_TABLE_2_QEQ["H1"]) <= DISILOXANE_TOLERANCE["H1"] for i in groups["H1"])


def test_post_hoc_the_other_c2v_conformation_reproduces_all_of_table_2():
    """NOT PRE-REGISTERED -- found after H1 failed, and recorded as such. With
    the in-plane hydrogen anti (torsion 60: pointing away from the other Si,
    the other C2v conformation), the two in-plane H give -0.0228 (H1 -0.021)
    and the four others -0.0406 (H2 -0.040), with O -0.6361 and Si +0.4219:
    all four within 0.002 e. Almenningen's data do not fix the conformation."""
    charges, coords, _ = _disiloxane(torsion=60)
    in_plane = [charges[h] for h in range(3, 9) if abs(coords[h][1]) < 1e-9]
    out_of_plane = [charges[h] for h in range(3, 9) if abs(coords[h][1]) >= 1e-9]
    assert len(in_plane) == 2 and len(out_of_plane) == 4
    computed = {"O": charges[0], "Si": charges[1], "H1": float(np.mean(in_plane)), "H2": float(np.mean(out_of_plane))}
    assert np.ptp(in_plane) < 1e-9 and np.ptp(out_of_plane) < 1e-9
    assert all(abs(computed[k] - RAMACHANDRAN_TABLE_2_QEQ[k]) <= 0.002 for k in computed)


def test_post_hoc_disiloxane_oxygen_and_silicon_separate_the_two_lambda_readings():
    """NOT PRE-REGISTERED, and not used to choose anything (A6 was already
    decided). O and Si barely move with conformation (< 0.001 e over torsion
    0-60 deg), so they compare readings without the conformation question.
    ADOPTED (lambda = 1/2) gives -0.636 / +0.422 against the printed -0.636 /
    +0.420; PREREGISTERED gives -0.624 / +0.388, 0.032 e off on Si."""
    for torsion in (0, 30, 60):
        adopted, _, _ = _disiloxane(torsion=torsion)
        preregistered, _, _ = _disiloxane(readings=ce.PREREGISTERED, torsion=torsion)
        assert abs(adopted[0] - RAMACHANDRAN_TABLE_2_QEQ["O"]) <= 0.002 and abs(adopted[1] - RAMACHANDRAN_TABLE_2_QEQ["Si"]) <= 0.003
        assert abs(preregistered[1] - RAMACHANDRAN_TABLE_2_QEQ["Si"]) >= 0.025


# =============================================================================
# Amendment A8: the fast integrals are the same integrals
# =============================================================================


def _grid_rows():
    return _rows("slater_reference.csv")


def test_batched_integrals_equal_the_scalar_routine_pair_by_pair_on_the_o1_grid():
    """A8, authority (3): every one of the 1076 frozen points, each pair compared
    with its own scalar value, never a sum. Measured 9.8e-15 Ha."""
    rows = _grid_rows()
    groups: dict[tuple[int, int], list[int]] = {}
    for k, row in enumerate(rows):
        groups.setdefault((int(row["n_a"]), int(row["n_b"])), []).append(k)
    batch = np.empty(len(rows))
    for (n_a, n_b), idx in groups.items():
        batch[idx] = ce.coulomb_pair_integrals(
            n_a, n_b, [float(rows[k]["zeta_a"]) for k in idx], [float(rows[k]["zeta_b"]) for k in idx], [float(rows[k]["R_bohr"]) for k in idx]
        )
    for k, row in enumerate(rows):
        scalar = ce.coulomb_pair_integral(int(row["n_a"]), float(row["zeta_a"]), int(row["n_b"]), float(row["zeta_b"]), float(row["R_bohr"]))
        assert abs(batch[k] - scalar) <= 1e-11, row
        assert abs(batch[k] - float(row["J_hartree"])) <= 1e-9, row


def test_batched_integrals_take_the_near_zero_branch_where_the_scalar_routine_does():
    rows = [r for r in _grid_rows() if 0 < float(r["R_bohr"]) < 0.01]
    assert rows
    before = ce.NEAR_ZERO_BRANCH_USES["count"]
    for row in rows:
        ce.coulomb_pair_integrals(int(row["n_a"]), int(row["n_b"]), [float(row["zeta_a"])], [float(row["zeta_b"])], [float(row["R_bohr"])])
    assert ce.NEAR_ZERO_BRANCH_USES["count"] > before


def test_batched_integrals_keep_each_pair_on_its_own_row():
    """Shuffling the pairs shuffles the answers and nothing else: no pair's R,
    zeta or panel count leaks into another's."""
    rng = np.random.default_rng(20260914)
    zeta_a = rng.uniform(0.3, 2.0, 40)
    zeta_b = rng.uniform(0.3, 2.0, 40)
    R = rng.uniform(0.2, 25.0, 40)
    order = rng.permutation(40)
    straight = ce.coulomb_pair_integrals(2, 1, zeta_a, zeta_b, R)
    shuffled = ce.coulomb_pair_integrals(2, 1, zeta_a[order], zeta_b[order], R[order])
    assert np.max(np.abs(shuffled - straight[order])) <= 1e-15
    for k in (0, 17, 39):
        assert abs(straight[k] - ce.coulomb_pair_integral(2, zeta_a[k], 1, zeta_b[k], R[k])) <= 1e-11


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6])
def test_the_fused_gamma_values_equal_the_scalar_gammas(n):
    """Tested apart from the integral, so an off-by-one shows as itself: tiny
    x, both sides of each series switch (m + 1 and m + 2), and large x."""
    m = 2 * n + 1
    x = np.concatenate([np.geomspace(1e-12, 1e-3, 40), np.linspace(0.1, m + 3, 400), np.array([m + 1 - 1e-9, m + 1, m + 2 - 1e-9, m + 2]), np.linspace(m + 3, 200, 60)])
    p_m, q_2n, p_m1 = ce._primitive_gammas(n, x)
    for fused, scalar in ((p_m, ce._lower_gamma(m, x)), (q_2n, ce._upper_gamma(2 * n, x)), (p_m1, ce._lower_gamma(m + 1, x))):
        relative = np.abs(fused - scalar) / np.maximum(np.abs(scalar), 1e-300)
        assert np.all((relative <= 1e-12) | (np.abs(fused - scalar) <= 1e-15)), (n, x[np.argmax(relative)])


def test_the_fixed_pairs_are_computed_once_and_the_hydrogen_pairs_every_iteration(monkeypatch):
    """A8: only pairs whose zeta never moves may be reused. Every build must
    re-evaluate every hydrogen-involving pair; none may re-evaluate a fixed one."""
    elements, coords = WATER[0] + ["C"], np.vstack([WATER[1], [[0.0, 0.0, 2.5]]])
    seen: list[int] = []
    real = ce.coulomb_pair_integrals

    def counting(n_a, n_b, zeta_a, zeta_b, R, *args, **kwargs):
        seen.append(len(np.atleast_1d(R)))
        return real(n_a, n_b, zeta_a, zeta_b, R, *args, **kwargs)

    monkeypatch.setattr(ce, "coulomb_pair_integrals", counting)
    system = ce._QEqSystem(elements, coords, "experimental", ce.ADOPTED)
    fixed_pairs = sum(seen)
    assert fixed_pairs == 1  # O-C, the one pair without a hydrogen
    seen.clear()
    system.build({1: 0.1, 2: 0.1})
    assert sum(seen) == 5  # O-H, O-H, H-H, H-C, H-C
    seen.clear()
    system.build({1: 0.2, 2: 0.2})
    assert sum(seen) == 5


def test_final_active_atoms_and_ever_clamped_are_different_facts():
    """A8's result contract. On a system that clamps mid-loop and ends bound-free,
    ever_clamped is true while final_active_atoms is empty; `clamped` is the
    final set under its old name."""
    result = ce.qeq_charges(*WATER)
    assert result.final_active_atoms == {} and result.clamped is result.final_active_atoms
    early = ce.qeq_charges(*_diatomic("Li", "H", _r_e("LiH")), max_outer=6)
    assert early.status == ce.REFUSE_NOT_CONVERGED and not early.ever_clamped and early.final_active_atoms == {}
    # Measured: LiH's undamped trajectory reaches H = -1 only later in its 50 iterations (A7).
    lih = ce.qeq_charges(*_diatomic("Li", "H", _r_e("LiH")))
    assert lih.status == ce.REFUSE_NOT_CONVERGED and lih.ever_clamped and lih.final_active_atoms == {}


def test_hydrogen_pair_entries_use_the_charge_dependent_zeta():
    """Each hydrogen-involving entry of the built matrix is the scalar integral
    at zeta_H(Q) = zeta0 + Q (eq 20), not at zeta0: a cache that froze them
    would pass every test that builds both sides through the same code."""
    elements, coords = WATER
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1) / ce.QEQ_BOHR_ANGSTROM
    system = ce._QEqSystem(elements, coords, "experimental", ce.ADOPTED)
    for q in (0.0, 0.3, -0.4):
        hardness, _, _ = system.build({1: q, 2: q})
        zeta_o = ce.valence_zeta("O", ce.ADOPTED)
        zeta_h = ce.ZETA_H0 + q
        o_h = ce.coulomb_pair_integral(2, zeta_o, 1, zeta_h, float(distance[0, 1])) * ce.HARTREE_EV
        h_h = ce.coulomb_pair_integral(1, zeta_h, 1, zeta_h, float(distance[1, 2])) * ce.HARTREE_EV
        assert abs(hardness[0, 1] - o_h) <= 1e-9 and abs(hardness[1, 2] - h_h) <= 1e-9, q


# =============================================================================
# A8 Stage 2: the closed form, its one switch and its one fallback
# =============================================================================


def test_both_stage_2_branches_run_on_the_o1_grid_and_both_kummer_signs_occur():
    """The frozen grid reaches the fallback (its near-zero R) and the closed
    form, and its unequal exponents give z of both signs."""
    rows = _grid_rows()
    before = dict(ce.CLOSED_FORM_USES)
    for row in rows:
        ce.coulomb_pair_integrals(int(row["n_a"]), int(row["n_b"]), [float(row["zeta_a"])], [float(row["zeta_b"])], [float(row["R_bohr"])])
    used = {key: ce.CLOSED_FORM_USES[key] - before[key] for key in before}
    assert used["closed"] > 0 and used["fallback"] > 0 and used["kummer_negative"] > 0
    z = [-(float(r["zeta_b"]) - float(r["zeta_a"])) * 2 * float(r["R_bohr"]) for r in rows]
    assert any(v > 0 for v in z) and any(v == 0 for v in z)


def test_the_real_molecules_take_the_closed_form():
    """Measured on the four timing structures: every pair past the fallback
    threshold, so the closed form is what a user's result comes from."""
    elements, coords = _perf_structure("aspirin")
    before = dict(ce.CLOSED_FORM_USES)
    ce.qeq_charges(elements, coords)
    assert ce.CLOSED_FORM_USES["closed"] - before["closed"] > 0
    assert ce.CLOSED_FORM_USES["series_cap"] == before["series_cap"]


@pytest.mark.parametrize("n_a,n_b", [(1, 1), (2, 1), (3, 2), (6, 5)])
def test_the_closed_form_is_continuous_across_its_kummer_switch(n_a, n_b):
    """z = -(b - a) R changes sign when the exponents cross. At z = 0 and
    z = +-1e-12, +-1e-6 the closed form equals the scalar quadrature to 1e-12
    Ha, and the two sides of z = 0 differ by no more than the exponent change."""
    R = 3.0
    base = 0.9
    values = {}
    for dz in (-1e-6, -1e-12, 0.0, 1e-12, 1e-6):
        zeta_b = base - dz / (2 * R)  # z = -(2 zeta_b - 2 zeta_a) R = dz
        closed = ce.coulomb_pair_integrals(n_a, n_b, [base], [zeta_b], [R])[0]
        scalar = ce.coulomb_pair_integral(n_a, base, n_b, zeta_b, R)
        assert abs(closed - scalar) <= 1e-12, (dz, closed - scalar)
        values[dz] = closed
    assert abs(values[1e-12] - values[-1e-12]) <= 1e-12 * abs(values[0.0])


def test_a_series_that_hits_its_cap_falls_back_and_is_still_right(monkeypatch):
    monkeypatch.setattr(ce, "_KUMMER_TERM_CAP", 1)
    before = dict(ce.CLOSED_FORM_USES)
    R = np.array([3.0, 8.0, 15.0])
    values = ce.coulomb_pair_integrals(2, 1, [0.9, 0.9, 0.9], [1.3, 0.6, 1.1], R)
    assert ce.CLOSED_FORM_USES["series_cap"] - before["series_cap"] == 3
    for k, zeta_b in enumerate((1.3, 0.6, 1.1)):
        assert abs(values[k] - ce.coulomb_pair_integral(2, 0.9, 1, zeta_b, float(R[k]))) <= 1e-11


def _perf_structure(name: str):
    rows = [r for r in _rows("qeq_perf_conformers.csv") if r["molecule"] == name]
    rows.sort(key=lambda r: int(r["index"]))
    return [r["element"] for r in rows], np.array([[float(r["x"]), float(r["y"]), float(r["z"])] for r in rows])


@pytest.mark.parametrize("name", ["aspirin", "n-hexadecane"])
def test_stage_2_charges_equal_a_fresh_scalar_matrix_solve(name, monkeypatch):
    """End to end against a matrix built from the SCALAR integral: the same
    hydrogen loop, every pair through `coulomb_pair_integral`. Full vectors."""
    elements, coords = _perf_structure(name)
    fast = ce.qeq_charges(elements, coords)

    def scalar_batch(n_a, n_b, zeta_a, zeta_b, R, *args, **kwargs):
        return np.array([ce.coulomb_pair_integral(n_a, za, n_b, zb, r) for za, zb, r in zip(np.atleast_1d(zeta_a), np.atleast_1d(zeta_b), np.atleast_1d(R))])

    monkeypatch.setattr(ce, "coulomb_pair_integrals", scalar_batch)
    slow = ce.qeq_charges(elements, coords)
    assert fast.status == slow.status == "converged" and fast.iterations == slow.iterations
    assert np.max(np.abs(fast.charges - slow.charges)) <= 1e-9
# Amendment A9: the constrained minimum the paper's bound procedure is judged by
# =============================================================================

import qeq_bounded_qp as qp  # noqa: E402


def test_a9_check_1_with_no_bound_active_the_qp_is_the_unconstrained_solve():
    """On ordinary QEq matrices (no bound binds) the QP, the KKT solve and the
    paper's procedure are one answer."""
    cases = [_diatomic("Na", "Cl", _r_e("NaCl")), WATER, qeq_geometries.build("H3COH")[:2]]
    for elements, coords in cases:
        result = ce.qeq_charges(elements, coords)
        assert result.status == "converged" and result.clamped == {}
        q_h = {i: float(result.charges[i]) for i, e in enumerate(elements) if e == "H"}
        hardness, chi, _ = ce.qeq_hardness_matrix(elements, coords, q_h)
        bounds = [ce.charge_bounds(e) for e in elements]
        lower, upper = np.array([b[0] for b in bounds]), np.array([b[1] for b in bounds])
        assert qp.tangent_min_eigenvalue(hardness) > 0
        minimum = qp.constrained_minimum(hardness, chi, 0.0, lower, upper)
        unconstrained = ce.solve_bounded(hardness, chi, 0.0, np.full(len(chi), -1e9), np.full(len(chi), 1e9)).charges
        assert minimum.active == {}
        assert np.max(np.abs(minimum.charges - unconstrained)) <= 1e-10


def test_a9_check_2_the_qp_is_the_brute_force_optimum_on_every_synthetic_system():
    """Measured 3.6e-15 e worst over O9's 200 systems."""
    for hardness, chi, net, lower, upper in SYNTHETIC:
        minimum = qp.constrained_minimum(hardness, chi, net, lower, upper)
        assert np.max(np.abs(minimum.charges - _kkt_optimum(hardness, chi, net, lower, upper))) <= 1e-10
        assert qp.kkt_violation(hardness, chi, net, lower, upper, minimum.charges) <= 1e-9


def test_a9_check_3_where_the_paper_procedure_is_optimal_it_is_the_qp():
    """172 of the 200 synthetic systems: the paper's fixing already satisfies
    KKT, and there it equals the QP. The other 28 are O9's recorded misses."""
    optimal = 0
    for hardness, chi, net, lower, upper in SYNTHETIC:
        paper = ce.solve_bounded(hardness, chi, net, lower, upper).charges
        if qp.kkt_violation(hardness, chi, net, lower, upper, paper) <= 1e-9:
            optimal += 1
            assert np.max(np.abs(paper - qp.constrained_minimum(hardness, chi, net, lower, upper).charges)) <= 1e-10
    assert optimal == 172


def test_a9_the_qp_releases_what_the_paper_procedure_keeps_fixed():
    """The one behaviour that separates them: on some synthetic system the QP
    releases an atom, and its energy is below the paper's."""
    released = 0
    for hardness, chi, net, lower, upper in SYNTHETIC:
        minimum = qp.constrained_minimum(hardness, chi, net, lower, upper)
        paper = ce.solve_bounded(hardness, chi, net, lower, upper).charges
        if minimum.released:
            released += 1
        assert qp.energy(hardness, chi, minimum.charges) <= qp.energy(hardness, chi, paper) + 1e-9
    assert released > 0


def _o9_corpus_molecule(name: str):
    rows = [r for r in csv.DictReader(line for line in (FIXTURES / "o9_corpus_conformers.csv").read_text(encoding="utf-8").splitlines() if not line.startswith("#")) if r["molecule"] == name]
    rows.sort(key=lambda r: int(r["index"]))
    return [r["element"] for r in rows], np.array([[float(r["x"]), float(r["y"]), float(r["z"])] for r in rows]), float(rows[0]["net_charge"])


def test_a9_the_one_bound_active_corpus_molecule_has_a_unique_kkt_point_the_paper_finds():
    """Measured on the 174-molecule corpus: propane-1,3-diide is the only
    converged molecule with a final active bound (two H at -1), and the only
    one whose QEq matrix is not convex on sum q = Q (tangent eigenvalue -0.24).
    Brute force over all 3^9 assignments finds exactly one KKT point, so it is
    the global constrained minimum, and the paper's procedure and the QP both
    reach it."""
    elements, coords, net = _o9_corpus_molecule("propane-1,3-diide")
    result = ce.qeq_charges(elements, coords, net)
    assert result.status == "converged" and set(result.clamped) == {3, 7}
    q_h = {i: float(result.charges[i]) for i, e in enumerate(elements) if e == "H"}
    hardness, chi, _ = ce.qeq_hardness_matrix(elements, coords, q_h)
    assert qp.tangent_min_eigenvalue(hardness) < 0
    bounds = [ce.charge_bounds(e) for e in elements]
    lower, upper = np.array([b[0] for b in bounds]), np.array([b[1] for b in bounds])
    paper = ce.solve_bounded(hardness, chi, net, lower, upper).charges
    minimum = qp.constrained_minimum(hardness, chi, net, lower, upper).charges
    kkt_points = []
    for assignment in itertools.product((0, 1, 2), repeat=len(chi)):
        fixed = {i: (lower[i] if a == 1 else upper[i]) for i, a in enumerate(assignment) if a}
        if len(fixed) == len(chi):
            continue
        q, _ = qp._equality_solve(hardness, chi, net, fixed, len(chi))
        if np.all(q >= lower - 1e-9) and np.all(q <= upper + 1e-9) and qp.kkt_violation(hardness, chi, net, lower, upper, q) <= 1e-9:
            if not any(np.max(np.abs(q - k)) < 1e-8 for k in kkt_points):
                kkt_points.append(q)
    assert len(kkt_points) == 1
    assert np.max(np.abs(paper - kkt_points[0])) <= 1e-10 and np.max(np.abs(minimum - kkt_points[0])) <= 1e-10


def test_a9_the_one_corpus_molecule_that_does_not_converge_is_the_dication_methanediylium():
    elements, coords, net = _o9_corpus_molecule("methanediylium")
    assert ce.qeq_charges(elements, coords, net).status == ce.REFUSE_NOT_CONVERGED


# =============================================================================
# A10: the hydrogen refit instrument, checked before it judges anything
# =============================================================================

import importlib.util  # noqa: E402

_REFIT_PATH = pathlib.Path(__file__).parent.parent / "benchmarks" / "charges" / "rappe_goddard" / "hydrogen_refit.py"
_spec = importlib.util.spec_from_file_location("hydrogen_refit", _REFIT_PATH)
hr = importlib.util.module_from_spec(_spec)
sys.modules["hydrogen_refit"] = hr
_spec.loader.exec_module(hr)


@functools.lru_cache(maxsize=None)
def _refit_molecule(name: str, variant: str):
    return hr.Molecule(name, hr.VARIANTS_BY_NAME[variant])


@pytest.mark.parametrize("variant", ["V0", "H-b", "H-c"])
def test_a10_instrument_matrices_are_the_shipped_build_at_both_printed_pairs(variant):
    """The refit sets only hydrogen's chi and diagonal; everything else must be
    the shipped `qeq_hardness_matrix`, or the refit is of a different model."""
    readings = hr.VARIANTS_BY_NAME[variant].readings
    for name in hr.MOLECULES:
        m = _refit_molecule(name, variant)
        for column in hr.COLUMNS:
            for q in (-0.9, -0.3, 0.0, 0.4):
                C, chi = m.system(np.array([q]), *hr.PRINTED[column])
                ref_C, ref_chi, _ = ce.qeq_hardness_matrix(m.elements, m.coords, {h: q for h in m.hydrogens}, column, readings)
                assert np.max(np.abs(C[0] - ref_C)) <= 1e-12
                assert np.max(np.abs(chi - ref_chi)) <= 1e-12


@pytest.mark.parametrize("column", ["experimental", "hf"])
def test_a10_v0_root_is_the_production_charge_and_a7s_lih_root(column):
    for name in hr.MOLECULES:
        m = _refit_molecule(name, "V0")
        root = m.root(*hr.PRINTED[column])
        if name == "LiH":
            expected = {"experimental": -0.973740, "hf": -0.982743}[column]
            assert abs(root - expected) <= 5e-7
        else:
            production = ce.qeq_charges(m.elements, m.coords, hydrogen=column)
            assert abs(root - production.charges[m.hydrogens[0]]) <= 1e-9


def test_a10_h_a_iterates_are_plain_iteration_from_zero():
    for name in ("LiH", "CH4"):
        m = _refit_molecule(name, "H-a8")
        F = fp.HydrogenMap(m.elements, m.coords, "experimental")
        history = fp.iterate(F, 1.0, max_iterations=8, tolerance=0.0).history
        trace = m.trace(*hr.PRINTED["experimental"])
        assert len(trace) == 9
        assert max(abs(a - float(b[0])) for a, b in zip(trace, history)) <= 1e-12


def test_a10_h_b_diagonal_is_eq_23s_gradient_and_differs_from_v0_only_there():
    q, j_h = 0.3, 13.8904
    hb, _ = _refit_molecule("HF", "H-b").system(np.array([q]), 4.528, j_h)
    v0, _ = _refit_molecule("HF", "V0").system(np.array([q]), 4.528, j_h)
    assert hb[0, 0, 0] == pytest.approx(j_h * (1.0 + 0.45 / 1.0698), abs=1e-12)
    assert v0[0, 0, 0] == pytest.approx(j_h * (1.0 + 0.3 / 1.0698), abs=1e-12)
    difference = hb[0] - v0[0]
    difference[0, 0] = 0.0
    assert np.max(np.abs(difference)) == 0.0


def test_a10_h_d_clamps_only_the_charge_entering_hydrogens_diagonal():
    hc, hd = _refit_molecule("LiH", "H-c"), _refit_molecule("LiH", "H-d")
    inside = np.array([-0.9, 0.0, 0.9])
    assert np.array_equal(hc.system(inside, 4.528, 13.8904)[0], hd.system(inside, 4.528, 13.8904)[0])
    C, _ = hd.system(np.array([-0.97]), 4.528, 13.8904)
    assert C[0, 1, 1] == pytest.approx(13.8904 * (1.0 - 0.95 / 1.0698), abs=1e-12)
    ref, _ = hc.system(np.array([-0.97]), 4.528, 13.8904)
    assert C[0, 0, 1] == ref[0, 0, 1]
    # The solved charge itself is never clamped: F can return below -0.95.
    loose = hr.Variant("H-d-wide", hd.variant.readings, clamp=10.0)
    assert hr.Molecule("LiH", loose).system(np.array([-0.97]), 4.528, 13.8904)[0][0, 1, 1] == pytest.approx(ref[0, 1, 1])


def test_a10_nelder_mead_finds_a_quadratic_and_rosenbrock():
    x, s, _, converged = hr.nelder_mead(lambda x: (1 - x[0]) ** 2 + 100 * (x[1] - x[0] ** 2) ** 2, (-1.2, 1.0))
    assert converged and np.max(np.abs(x - [1.0, 1.0])) <= 1e-6
    x, s, _, converged = hr.nelder_mead(lambda x: (x[0] - 4.7) ** 2 + 3 * (x[1] - 13.2) ** 2 + (x[0] - 4.7) * (x[1] - 13.2), (4.0, 12.0))
    assert converged and np.max(np.abs(x - [4.7, 13.2])) <= 1e-6


def test_a10_the_box_rejects_rather_than_clips(monkeypatch):
    """With every charge finite, only the box can make S infinite -- an earlier
    version of this test passed a clipping box because the point it probed had
    no unique root anyway."""
    fit = hr.Fit(hr.VARIANTS_BY_NAME["H-c"], {m: 0.0 for m in hr.MOLECULES})
    for molecule in fit.molecules.values():
        monkeypatch.setattr(molecule, "charge", lambda chi_h, j_h: 0.1)
    assert math.isfinite(fit.objective((4.0, 12.0))) and math.isfinite(fit.objective((5.5, 15.0)))
    for outside in ((3.999, 13.0), (5.501, 13.0), (4.6, 11.999), (4.6, 15.001)):
        assert fit.objective(outside) == math.inf


def test_a10_nelder_mead_shrinks_when_contraction_fails_against_a_wall():
    """Rosenbrock and a quadratic never reach the shrink step; a minimum in a
    corner whose outside is infinite does, and without it the simplex sticks."""
    walled = lambda x: (x[0] - 1) ** 2 + (x[1] - 1) ** 2 if (x[0] <= 1.0 and x[1] <= 1.0) else math.inf
    x, _, _, converged = hr.nelder_mead(walled, (0.98, 0.98))
    assert converged and np.max(np.abs(x - [1.0, 1.0])) <= 1e-5


def test_a10_a_sign_change_across_a_bound_switch_is_not_a_root():
    """H-c's HF at the experimental printed pair: g changes sign three times on
    A7's grid, but one is a jump where the bounded solve switches active set and
    one is a fixed point pinned at a bound. Exactly one bound-free root remains."""
    m = _refit_molecule("HF", "H-c")
    g = m.residual(hr.GRID_Q, *hr.PRINTED["experimental"])
    assert int(np.sum(g == 0.0)) + len(np.flatnonzero(g[:-1] * g[1:] < 0)) >= 3
    free, pinned = m.fixed_points(*hr.PRINTED["experimental"])
    assert len(free) == 1 and free[0] > 0 and len(pinned) == 1
    for q in free + pinned:
        assert abs(float(m.residual(q, *hr.PRINTED["experimental"])[0])) <= hr.ROOT_RESIDUAL
    assert m.root(*hr.PRINTED["experimental"]) == free[0]


def test_a10_several_bound_free_roots_make_the_charge_undefined():
    """V0's LiH at (4.528, 15.0): three bound-free fixed points, so no Q_H."""
    m = _refit_molecule("LiH", "V0")
    free, _ = m.fixed_points(4.528, 15.0)
    assert len(free) == 3 and m.root(4.528, 15.0) is None


def test_a10_weights_are_the_papers_and_multiply_squared_residuals():
    assert hr.WEIGHTS == {"HF": 1.0, "H2O": 1.0, "NH3": 1.0, "CH4": 5.0, "LiH": 0.2}
    charges = {m: 0.1 for m in hr.MOLECULES}
    targets = {"HF": 0.0, "H2O": 0.0, "NH3": 0.0, "CH4": 0.2, "LiH": -0.9}
    assert hr.objective_from_charges(charges, targets) == pytest.approx(0.01 * 3 + 5 * 0.01 + 0.2 * 1.0)
    assert hr.objective_from_charges(charges, targets, {m: 1.0 for m in hr.MOLECULES}) != hr.objective_from_charges(charges, targets)
    assert hr.objective_from_charges(charges, targets, {m: w * w for m, w in hr.WEIGHTS.items()}) != hr.objective_from_charges(charges, targets)


# A10 correction 3: the harness that crashed, repaired without touching the science


def test_a10_a_symmetry_spread_is_recorded_and_never_makes_s_infinite(monkeypatch):
    """The first run died on a 2.05e-10 CH4 spread asserted INSIDE the optimised
    function. A spread is data: S stays finite, Q_H is the group mean."""
    fit = hr.Fit(hr.VARIANTS_BY_NAME["V0"], {m: 0.0 for m in hr.MOLECULES})
    ch4 = fit.molecules["CH4"]
    q = np.array([0.15])
    clean = float(ch4.image(q, *hr.PRINTED["experimental"])[0])
    original = hr.Molecule._solve

    def lopsided(self, C, chi):
        charges = original(self, C, chi)
        if len(self.group) > 1:
            charges[:, self.group[0]] += 2e-10
        return charges

    monkeypatch.setattr(hr.Molecule, "_solve", lopsided)
    fit.recorder.phase = "control"
    assert math.isfinite(fit.objective(hr.PRINTED["experimental"]))
    assert fit.recorder.phases["control"]["max"] >= 1.9e-10
    shifted = float(ch4.image(q, *hr.PRINTED["experimental"])[0])
    assert shifted - clean == pytest.approx(2e-10 / 4, abs=1e-13)


def test_a10_the_symmetry_check_applies_at_reported_points_and_blocks_the_verdict():
    recorder = hr.SpreadRecorder()
    recorder.phase = "control"
    recorder.add(np.full(990, 2e-9))
    recorder.add(np.full(10, 1e-6))
    # The 99th percentile lands in the [1e-8.7, 1e-8.6) bin; its upper edge, times 10.
    assert hr.symmetry_threshold(recorder) == pytest.approx(10 * 10 ** -8.6)
    floored = hr.SpreadRecorder()
    floored.phase = "control"
    floored.add(np.full(100, 1e-13))
    assert hr.symmetry_threshold(floored) == 1e-10
    assert hr.symmetry_threshold(hr.SpreadRecorder()) == 1e-10
    assert hr.symmetry_status(5e-11, 5e-11, 1e-10) == "PASSED"
    assert hr.symmetry_status(2e-10, math.nan, 1e-10) == "SYMMETRY-CHECK-FAILED"
    results = {("V0", c): _fake_refit_result("V0", c) for c in hr.COLUMNS}
    assert hr.classify(results, "V0") == "UNEXPLAINED"
    results[("V0", "hf")]["symmetry_check"] = "SYMMETRY-CHECK-FAILED"
    assert hr.classify(results, "V0") is None


def _fake_refit_result(variant: str, column: str) -> dict:
    q = {m: 0.1 for m in hr.MOLECULES}
    residuals = {"max_abs": 0.1, "lih": 0.1, "non_lih_rms": 0.1, "non_lih_max": 0.1}
    return {
        "variant": variant, "column": column, "status": "COMPLETE", "q_printed": q, "spread_printed": 0.0,
        "S_printed": 1.0, "dS_dchi": 0.0, "dS_dJ": 0.0, "res_printed": residuals, "program_diff": q, "program_pass": False,
        "roots_printed": "", "control": [[0, 4.5, 13.9, 0.1]], "control_excluded": 0, "env_chi": 0.01, "env_J": 0.01,
        "symmetry_threshold": 1e-10, "grid_basins": [[4.5, 13.9, 0.1]], "endpoints": [[4.0, 12.0, 4.5, 13.9, 0.1, 10, True]],
        "nm_basins": [[4.5, 13.9, 0.1, 1]], "ambiguous": [], "fit": [4.5, 13.9], "S_fit": 0.1, "delta_S": 0.9, "q_fit": q,
        "spread_fit": 0.0, "res_fit": residuals, "fine_min": [4.5, 13.9, 0.1], "fine_ok": True, "elongation": 2.0,
        "within_envelope": False, "symmetry_check": "PASSED", "evaluations": 1, "infinite_evaluations": 0,
    }


def _failing_runner(variant, column):
    if variant == "H-b":
        raise RuntimeError("an ill-conditioned evaluation")
    return _fake_refit_result(variant, column)


def test_a10_a_failed_job_is_recorded_and_the_others_still_finish(tmp_path):
    jobs = [("V0", "experimental"), ("H-b", "experimental"), ("H-c", "experimental")]
    states = hr.run_jobs(jobs, tmp_path, workers=1, runner=_failing_runner)
    assert states == {("V0", "experimental"): "COMPLETE", ("H-b", "experimental"): "FAILED", ("H-c", "experimental"): "COMPLETE"}
    failed = json.loads(hr.job_path(tmp_path, "H-b", "experimental").read_text(encoding="utf-8"))
    assert "an ill-conditioned evaluation" in failed["traceback"]
    assert failed["settings"]["sha256"]["preregistration.md"]


def test_a10_a_missing_job_is_not_run_and_gets_no_verdict(tmp_path):
    hr.run_jobs([("V0", "experimental")], tmp_path, workers=1, runner=_failing_runner)
    results, states = hr.collect(tmp_path, ["V0"])
    assert states == {("V0", "experimental"): "COMPLETE", ("V0", "hf"): "NOT_RUN"}
    assert hr.classify(results, "V0") is None
    assert hr.summary_line(states) == "2 expected / 1 complete / 0 failed / 1 not run"


def test_a10_the_summary_does_not_depend_on_completion_order(tmp_path):
    keys = [(v, c) for v in ("V0", "H-a6", "H-b") for c in hr.COLUMNS]
    results = {k: _fake_refit_result(*k) for k in keys}
    states = {k: "COMPLETE" for k in keys}
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    hr.write(results, states, tmp_path / "a")
    hr.write(dict(reversed(list(results.items()))), dict(reversed(list(states.items()))), tmp_path / "b")
    for name in ("hydrogen_refit.csv", "hydrogen_refit_basins.csv", "hydrogen_refit_control.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    lines = (tmp_path / "a" / "hydrogen_refit.csv").read_text(encoding="utf-8").splitlines()
    assert [line.split(",")[0] for line in lines[3:]] == ["V0", "V0", "H-a6", "H-a6", "H-b", "H-b"]


# A10: the complete run's results, pinned and re-derived

_REFIT_CSV = _REFIT_PATH.parent / "hydrogen_refit.csv"


def _refit_rows() -> dict[tuple[str, str], dict[str, str]]:
    lines = [l for l in _REFIT_CSV.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return {(r["variant"], r["column"]): r for r in csv.DictReader(lines)}


def test_a10_the_run_is_complete_and_every_reading_is_unexplained():
    header = _REFIT_CSV.read_text(encoding="utf-8").splitlines()[1]
    assert header == "# 18 expected / 18 complete / 0 failed / 0 not run"
    rows = _refit_rows()
    assert len(rows) == 18 and all(r["job_status"] == "COMPLETE" and r["symmetry_check"] == "PASSED" for r in rows.values())
    assert {r["verdict"] for r in rows.values()} == {"UNEXPLAINED"}


def test_a10_verdicts_follow_from_the_recorded_fields():
    """Re-derive each verdict from the CSV rather than trusting the column."""
    rows = _refit_rows()
    for variant in {v for v, _ in rows}:
        met = [rows[(variant, c)]["within_envelope"] == "True" and rows[(variant, c)]["program_pass"] == "True" for c in hr.COLUMNS]
        expected = "FIT-REPRODUCED" if all(met) else "PARTIAL" if any(met) else "UNEXPLAINED"
        assert rows[(variant, "experimental")]["verdict"] == expected


@pytest.mark.parametrize("column", ["experimental", "hf"])
def test_a10_v0_objective_recomputes_at_the_printed_and_refit_pairs(column):
    """S recomputed now, from the fixtures, at both pairs the CSV records."""
    row = _refit_rows()[("V0", column)]
    table = hr.table_iii()
    fit = hr.Fit(hr.VARIANTS_BY_NAME["V0"], {m: table[m][hr.TARGET_COLUMN[column]] for m in hr.MOLECULES})
    assert fit.objective(hr.PRINTED[column]) == pytest.approx(float(row["S_printed"]), rel=1e-9)
    job = json.loads((_REFIT_PATH.parent / "hydrogen_refit_jobs" / f"V0_{column}.json").read_text(encoding="utf-8"))
    refit = tuple(job["result"]["fit"])  # full precision: the CSV's 8 digits can cross the uniqueness boundary
    assert fit.objective(refit) == pytest.approx(float(row["S_fit"]), rel=1e-6)
    pinned = {"experimental": (4.4845, 14.2602), "hf": (4.8644, 12.3662)}[column]
    assert refit == pytest.approx(pinned, abs=1e-4)
    assert abs(refit[1] - hr.PRINTED[column][1]) > 10 * float(row["env_J"])


def test_a10_h_b_h_c_h_d_have_no_bound_free_lih_charge_at_the_printed_pairs():
    for variant in ("H-b", "H-c", "H-d"):
        for column in hr.COLUMNS:
            assert _refit_molecule("LiH", variant).root(*hr.PRINTED[column]) is None


def test_a10_the_v0_experimental_refit_stops_at_the_lih_uniqueness_boundary():
    """Measured after the run: one small step up in J or down in chi gives LiH
    two more bound-free fixed points, so A10's rule makes S infinite there.
    The HF-column refit is interior."""
    lih = _refit_molecule("LiH", "V0")
    for column, crosses in (("experimental", True), ("hf", False)):
        job = json.loads((_REFIT_PATH.parent / "hydrogen_refit_jobs" / f"V0_{column}.json").read_text(encoding="utf-8"))
        chi, j = job["result"]["fit"]
        assert len(lih.fixed_points(chi, j)[0]) == 1
        assert (len(lih.fixed_points(chi, j + 1e-3)[0]) == 3) is crosses
        assert (len(lih.fixed_points(chi - 1e-4, j)[0]) == 3) is crosses


# A11: Cioslowski's LiH APT charge (experiment B: spherical, ORCA; gates nothing)

_apt_spec = importlib.util.spec_from_file_location("cioslowski_apt", _REFIT_PATH.parent / "cioslowski_apt.py")
capt = importlib.util.module_from_spec(_apt_spec)
sys.modules["cioslowski_apt"] = capt
_apt_spec.loader.exec_module(capt)


def test_a11_apt_charge_is_the_trace_of_the_dipole_derivatives():
    """A synthetic polar tensor diag(a, a, b): eq 9 gives (2a + b)/3, not b."""
    a, b, h = 0.78, 0.48, 0.001
    hb = h / capt.BOHR
    dipoles = {}
    for p, slope in enumerate((a, a, b)):
        for sign in (+1, -1):
            mu = [0.0, 0.0, -2.4]
            mu[p] += sign * slope * hb
            dipoles["xyz"[p] + ("+" if sign > 0 else "-")] = tuple(mu)
    assert capt.apt_charge(dipoles, h) == pytest.approx((2 * a + b) / 3, abs=1e-12)


def test_a11_experiment_b_is_converged_stable_and_pinned():
    report = capt.analyse()["6-31++G(d,p)"]
    assert report["all_converged"]
    assert report["r"] == pytest.approx(1.63279, abs=1e-5)
    assert report["stable"] == [0.0005, 0.001, 0.002, 0.004] and report["h"] == 0.004
    assert report["Q_Li"] == pytest.approx(0.68215, abs=5e-6)
    assert report["within"]  # 0.00025 from Cioslowski's 0.6819 -- a diagnostic, never a gate


def test_a11_the_axial_derivative_alone_is_not_the_charge():
    rows = capt.rows()
    d = {r["displacement"]: tuple(float(r[f"dipole_{k}_au"]) for k in "xyz")
         for r in rows if r["kind"] == "displaced" and math.isclose(float(r["h_angstrom"]), 0.004)}
    hb = 0.004 / capt.BOHR
    axial = (d["z+"][2] - d["z-"][2]) / (2 * hb)
    perpendicular = (d["x+"][0] - d["x-"][0]) / (2 * hb)
    assert axial == pytest.approx(0.4801, abs=1e-4) and perpendicular == pytest.approx(0.7832, abs=1e-4)


# A12: Table IV geometry sensitivity (diagnostic only; nothing adopted)

_geo_spec = importlib.util.spec_from_file_location("table_iv_geometry", _REFIT_PATH.parent / "table_iv_geometry.py")
tivg = importlib.util.module_from_spec(_geo_spec)
sys.modules["table_iv_geometry"] = tivg
_geo_spec.loader.exec_module(tivg)

A12_PINNED = {
    # (molecule, order, column, base): (nominal, min, max, class)
    ("H2NC(O)H", 2, "QEq", "substitution"): (0.401066, 0.399414, 0.402691, "geometry-compatible"),
    ("H2NC(O)H", 3, "QEqHF", "substitution"): (-0.623290, -0.624599, -0.621960, "geometry-insensitive"),
    ("H3COH", 1, "QEqHF", "substitution"): (0.356053, 0.353544, 0.358571, "geometry-insensitive"),
    ("H3COH", 3, "QEqHF", "substitution"): (-0.104011, -0.108017, -0.100011, "geometry-insensitive"),
    ("H3COH", 5, "QEqHF", "substitution"): (0.173731, 0.170883, 0.176599, "geometry-insensitive"),
    ("H3COH", 1, "QEqHF", "effective"): (0.360809, 0.358286, 0.363340, "geometry-insensitive"),
    ("H3COH", 3, "QEqHF", "effective"): (-0.106525, -0.110529, -0.102528, "geometry-insensitive"),
    ("H3COH", 5, "QEqHF", "effective"): (0.174676, 0.171826, 0.177547, "geometry-insensitive"),
}


def test_a12_the_committed_summary_holds_the_pinned_classes():
    lines = [l for l in (_REFIT_PATH.parent / "table_iv_geometry_summary.csv").read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    rows = list(csv.reader(lines))[1:]
    got = {(r[0], int(r[1]), r[2], r[3]): (float(r[6]), float(r[7]), float(r[8]), r[13]) for r in rows}
    assert set(got) == set(A12_PINNED)
    for key, (nominal, lo, hi, klass) in A12_PINNED.items():
        assert got[key][:3] == pytest.approx((nominal, lo, hi), abs=2e-6), key
        assert got[key][3] == klass, key


def test_a12_a_bond_move_translates_one_fragment_and_changes_nothing_else():
    elements, coords, _, _ = qeq_geometries.build("H3COH")
    coords = np.asarray(coords, dtype=float)
    bond_list = tivg.bonds(elements, coords)
    before = tivg.internal_coordinates(bond_list, coords)
    for label, step, new in tivg.perturbations("H3COH", elements, coords):
        if label == "r1-2" and step == 0.010:
            after = tivg.internal_coordinates(bond_list, new)
            assert after["r1-2"] - before["r1-2"] == pytest.approx(0.010, abs=1e-12)
            assert all(abs(after[k] - before[k]) <= 1e-9 for k in before if k != "r1-2")
            break
    else:
        raise AssertionError("r1-2 +0.010 not generated")


def test_a12_formamide_recomputes_to_the_committed_values():
    """The two formamide cells, recomputed live (the methanol ones take ~30 s)."""
    evaluations, summary = tivg.run(tuple(c for c in tivg.CELLS if c[0] == "H2NC(O)H"))
    assert all(row[6] == "converged" for row in evaluations)
    for r in summary:
        nominal, lo, hi, klass = A12_PINNED[(r[0], r[1], r[2], r[3])]
        assert (float(r[6]), float(r[7]), float(r[8])) == pytest.approx((nominal, lo, hi), abs=2e-6)
        assert r[13] == klass


def test_a11_experiment_a_cartesian_d_reproduces_cioslowski_and_accepts_the_geometry():
    """Psi4, puream false: the historical basis. Gates H-e, and passes."""
    report = capt.analyse(capt.FIXTURE_A)["6-31++G(d,p)"]
    assert report["all_converged"]
    assert report["r"] == pytest.approx(1.632817, abs=2e-6)
    assert report["stable"] == [0.0005, 0.001, 0.002, 0.004] and report["h"] == 0.004
    assert report["Q_Li"] == pytest.approx(0.681845, abs=5e-6)
    assert report["within"] and report["bound"] == 0.0005

