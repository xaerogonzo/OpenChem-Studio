"""Oracle 2: the ns Slater Coulomb integrals at 30 digits, frozen to a table.

    python -m venv /scratch/mpenv && /scratch/mpenv/Scripts/pip install mpmath
    /scratch/mpenv/Scripts/python benchmarks/charges/rappe_goddard/integrals_mpmath.py \
        tests/fixtures/charges/slater_reference.csv --jobs 24

Deliberately NOT importable from the application, and deliberately written
without looking at `openchem.chem.charge_equilibration`: the production
integral uses spherical shells and closed-form incomplete-gamma sums, and
this uses mpmath's own `gammainc` inside a direct two-dimensional
integration of rho_b * V_a over space. Pre-registered in
`preregistration.md` section 5, which fixes the grid, the coordinates and the
agreement check below.

Density (eq 15 squared, normalised): rho(r) = a^(2n+1) r^(2n-2) e^(-a r) / (4 pi (2n)!),
a = 2 zeta. Its potential: V(r) = P(2n+1, a r)/r + (a / 2n) Q(2n, a r), with P and
Q the regularised lower and upper incomplete gamma functions. J = integral of
rho_b(r_B) V_a(r_A) over space, in hartree for R in bohr.

- R >= 0.05 bohr: prolate spheroidal coordinates, r_A = R(xi+eta)/2,
  r_B = R(xi-eta)/2, d^3r = 2 pi (R/2)^3 (xi^2 - eta^2) dxi deta.
- R < 0.05 bohr: spherical coordinates about A, split at r = R.
- R = 0: the one-centre radial integral.

Both 2D forms run at R = 0.05 and 0.2 bohr on every (n, zeta) combination and
must agree to 1e-14 hartree, or nothing is written.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import multiprocessing
import pathlib
import platform
import sys

import mpmath as mp

DPS = 30
A0_ANGSTROM = "0.52917"
R_ANGSTROM = ["0.2", "0.2961", "0.4385", "0.6492", "0.9613", "1.4234", "2.1076",
              "3.1207", "4.6207", "6.8418", "10.1305", "15.0"]
NEAR_ZERO_BOHR = ["0", "1e-6", "1e-4", "5e-4", "9.99e-4", "1.001e-3", "2e-3", "1e-2"]
OVERLAP_BOHR = ["0.05", "0.2"]
AGREEMENT = mp.mpf("1e-14")


def density(n, zeta, r):
    a = 2 * zeta
    return a ** (2 * n + 1) * r ** (2 * n - 2) * mp.e ** (-a * r) / (4 * mp.pi * mp.factorial(2 * n))


def potential(n, zeta, r):
    a = 2 * zeta
    if r == 0:
        # lim P(2n+1, ar)/r = 0; the second term is the whole potential at the centre.
        return a / (2 * n)
    lower = mp.gammainc(2 * n + 1, 0, a * r, regularized=True)
    upper = mp.gammainc(2 * n, a * r, mp.inf, regularized=True)
    return lower / r + (a / (2 * n)) * upper


def prolate(n_a, z_a, n_b, z_b, R):
    def integrand(xi, eta):
        r_a = R * (xi + eta) / 2
        r_b = R * (xi - eta) / 2
        return density(n_b, z_b, r_b) * potential(n_a, z_a, r_a) * (xi * xi - eta * eta)

    decay = 2 / (min(z_a, z_b) * R)  # xi length scale of the slowest exponential
    breaks = [1, 1 + decay / 4, 1 + decay, 1 + 4 * decay, 1 + 16 * decay, mp.inf]
    return 2 * mp.pi * (R / 2) ** 3 * mp.quad(integrand, breaks, [-1, 0, 1])


def spherical(n_a, z_a, n_b, z_b, R):
    def integrand(r, mu):
        r_b = mp.sqrt(r * r + R * R - 2 * r * R * mu)
        return r * r * potential(n_a, z_a, r) * density(n_b, z_b, r_b)

    scale = 1 / min(z_a, z_b)
    breaks = [0, R, R + scale / 4, R + scale, R + 4 * scale, R + 16 * scale, mp.inf]
    return 2 * mp.pi * mp.quad(integrand, breaks, [-1, 1])


def one_centre(n_a, z_a, n_b, z_b):
    scale = 1 / min(z_a, z_b)
    return mp.quad(lambda r: 4 * mp.pi * r * r * density(n_b, z_b, r) * potential(n_a, z_a, r),
                   [0, scale / 4, scale, 4 * scale, 16 * scale, mp.inf])


def evaluate(point):
    mp.mp.dps = DPS
    kind, n_a, z_a, n_b, z_b, R = point
    z_a, z_b, R = mp.mpf(z_a), mp.mpf(z_b), mp.mpf(R)
    if kind == "check":
        p, s = prolate(n_a, z_a, n_b, z_b, R), spherical(n_a, z_a, n_b, z_b, R)
        return point, p, s
    if R == 0:
        value = one_centre(n_a, z_a, n_b, z_b)
    elif R < mp.mpf("0.05"):
        value = spherical(n_a, z_a, n_b, z_b, R)
    else:
        value = prolate(n_a, z_a, n_b, z_b, R)
    return point, value, None


def grid():
    mp.mp.dps = DPS
    bohr = [mp.nstr(mp.mpf(r) / mp.mpf(A0_ANGSTROM), 25) for r in R_ANGSTROM]
    pairs = [(a, b) for a in range(1, 7) for b in range(a, 7)]
    combos = [("1.0", "1.0"), ("0.4174", "1.0726"), ("1.0726", "0.4174")]
    points = []
    for (n_a, n_b), (z_a, z_b) in itertools.product(pairs, combos):
        points += [("main", n_a, z_a, n_b, z_b, R) for R in bohr]
    zeta_h = ["0.0698", "0.5698", "1.0698", "1.5698", "2.0698"]
    for z_a in zeta_h:
        for n_b, z_b in [(2, "0.8563"), (2, "0.9745"), (1, "1.0698"), (1, z_a)]:
            points += [("hydrogen", 1, z_a, n_b, z_b, R) for R in bohr]
    for (n_a, n_b), (z_a, z_b) in itertools.product([(1, 1), (1, 2), (2, 2), (3, 5), (6, 6)], combos[:2]):
        points += [("near_zero", n_a, z_a, n_b, z_b, R) for R in NEAR_ZERO_BOHR]
    checks = [("check", n_a, z_a, n_b, z_b, R)
              for (n_a, n_b), (z_a, z_b) in itertools.product(pairs, combos) for R in OVERLAP_BOHR]
    return points, checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="timing runs only; writes nothing")
    args = parser.parse_args()
    points, checks = grid()
    if args.limit:
        points, checks = points[: args.limit], checks[: max(1, args.limit // 4)]
    with multiprocessing.Pool(args.jobs) as pool:
        checked = pool.map(evaluate, checks, chunksize=1)
        worst = max(abs(p - s) for _, p, s in checked)
        print(f"prolate vs spherical, {len(checked)} checks: worst {mp.nstr(worst, 3)} Ha")
        if worst > AGREEMENT:
            sys.exit("the two coordinate systems disagree; nothing written")
        results = pool.map(evaluate, points, chunksize=1)
    if args.limit:
        print(f"{len(results)} points computed; --limit writes nothing")
        return
    script = hashlib.sha256(pathlib.Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    lines = [
        "# ns Slater Coulomb integrals, oracle 2 of benchmarks/charges/rappe_goddard/preregistration.md.",
        f"# generated {datetime.date.today().isoformat()} by integrals_mpmath.py (SHA-256, LF: {script})",
        f"# python {platform.python_version()}, mpmath {mp.__version__}, dps {DPS}",
        f"# prolate vs spherical agreement over {len(checked)} checks: worst {mp.nstr(worst, 3)} Ha",
        "# J in hartree, R in bohr; R_bohr is R_angstrom / 0.52917 for the main and hydrogen rows.",
        "# NEVER regenerated by the tests. Regenerate by hand and review the diff.",
        "set,n_a,zeta_a,n_b,zeta_b,R_bohr,J_hartree",
    ]
    for (kind, n_a, z_a, n_b, z_b, R), value, _ in results:
        lines.append(f"{kind},{n_a},{z_a},{n_b},{z_b},{R},{mp.nstr(value, 22, min_fixed=-30, max_fixed=30)}")
    pathlib.Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(results)} rows to {args.output}")


if __name__ == "__main__":
    main()
