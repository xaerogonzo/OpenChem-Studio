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

Polyatomic rows of Tables III and IV need Harmony et al. 1979, which is not
held; they skip and say so.
"""

from __future__ import annotations

import csv
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

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "charges"
PREREGISTRATION = pathlib.Path(__file__).parent.parent / "benchmarks" / "charges" / "rappe_goddard" / "preregistration.md"
HARMONY = "needs Harmony et al., J. Phys. Chem. Ref. Data 1979, 8, 619 (the paper's polyatomic geometries), which is not held"


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
    assert len(hashed) == 6
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
    table = ce.qeq_charges(elements, coords, 0.0)
    eq17_prime = ce.qeq_charges(elements, coords, 0.0, readings=ce.ALTERNATES["R4"])
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
    solver = ce.qeq_charges(elements, coords, 0.0)
    assert abs(solver.charges[0] - eq18) <= 1e-8
    assert abs(solver.charges[0] + solver.charges[1]) < 1e-12  # eq 18: Q_X = -Q_M


# =============================================================================
# O4 / O5: Tables III and IV -- the diatomics now, the polyatomics after Harmony
# =============================================================================

DIATOMIC_HYDRIDES = {"HF": ("H", "F"), "LiH": ("Li", "H"), "ClH": ("H", "Cl")}
GEOMETRY_NAME = {"HF": "HF", "LiH": "LiH", "ClH": "HCl"}


O4_STOP = {
    "HF": "STOP RECORD (pre-registration section 8): P gives Q_H 0.4568 against QEq 0.462 and 0.4613 against QEqHF 0.457; no one-at-a-time alternate passes both columns",
    "LiH": "STOP RECORD: no reading converges; near the printed -0.767 the 2x2 system's J_Li + J_HH(Q) - 2 J_LiH is 0.28 eV under P, where the printed charge needs about 1.98 eV",
}


def _o4_params():
    return [
        pytest.param(row, marks=pytest.mark.xfail(strict=True, reason=O4_STOP[row["molecule"]])) if row["molecule"] in O4_STOP else row
        for row in _rows("rappe1991_table3.csv")
    ]


@pytest.mark.parametrize("row", _o4_params(), ids=lambda r: r["molecule"])
def test_o4_table_iii_hydrogen_charges(row):
    if row["molecule"] not in DIATOMIC_HYDRIDES:
        pytest.skip(HARMONY)
    elements, coords = _diatomic(*DIATOMIC_HYDRIDES[row["molecule"]], _r_e(GEOMETRY_NAME[row["molecule"]]))
    hydrogen = elements.index("H")
    for column, parameters in (("QEq", "experimental"), ("QEqHF", "hf")):
        result = ce.qeq_charges(elements, coords, 0.0, hydrogen=parameters)
        assert result.status == "converged"
        assert not result.bound_extension_used
        assert abs(result.charges[hydrogen] - float(row[column])) <= 0.001, (column, result.charges[hydrogen], row[column])


@pytest.mark.parametrize("row", [r for r in _rows("rappe1991_table4.csv") if r["status"] == "printed"],
                         ids=lambda r: f"{r['molecule']}-{r['printed_order']}")
def test_o5_table_iv_charges(row):
    if row["molecule"] not in DIATOMIC_HYDRIDES:
        pytest.skip(HARMONY)
    elements, coords = _diatomic(*DIATOMIC_HYDRIDES[row["molecule"]], _r_e(GEOMETRY_NAME[row["molecule"]]))
    atom = elements.index(row["atom"])
    for column, parameters in (("QEq", "experimental"), ("QEqHF", "hf")):
        result = ce.qeq_charges(elements, coords, 0.0, hydrogen=parameters)
        assert abs(result.charges[atom] - float(row[column])) <= 0.01, (column, result.charges[atom], row[column])


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
    primary, _, _ = ce.qeq_hardness_matrix(elements, coords, charges, readings=ce.PRIMARY)
    alternate, _, _ = ce.qeq_hardness_matrix(elements, coords, charges, readings=ce.ALTERNATES["R1"])
    for i, j in itertools.product(range(4), repeat=2):
        involves_h = i != j and (elements[i] == "H" or elements[j] == "H")
        if involves_h:
            assert primary[i, j] != alternate[i, j]
        else:
            assert primary[i, j] == alternate[i, j]
    at_zero_p, _, _ = ce.qeq_hardness_matrix(elements, coords, {}, readings=ce.PRIMARY)
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
