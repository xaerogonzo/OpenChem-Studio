"""The QEq side-by-side report the pre-registration requires when P fails.

    uv run --no-sync python benchmarks/charges/rappe_goddard/oracle.py

Prints, for every literature row that can run without Harmony 1979:
the printed value, P (the primary reading), and each one-at-a-time alternate
(R1-R4), for both hydrogen parameter sets. Then two diagnostics that change
nothing in the solver:

- LiH's self-consistency residual g(Q) = Q_solved(Q) - Q on a grid of trial
  hydrogen charges: whether a self-consistent charge EXISTS where the plain
  iteration fails to converge.
- O9's synthetic bounded systems: how often the paper's never-release fixing
  misses the constrained optimum, and whether a fixed atom wants back inside.

Nothing here selects a reading. See preregistration.md section 8.
"""

from __future__ import annotations

import csv
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from openchem.chem import charge_equilibration as ce  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "charges"


def rows(name):
    lines = [l for l in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return list(csv.DictReader(lines))


def r_e(molecule):
    return next(float(r["r_e_A"]) for r in rows("geometries.csv") if r["molecule"] == molecule)


def diatomic(a, b, d):
    return [a, b], np.array([[0.0, 0.0, 0.0], [0.0, 0.0, d]])


READINGS = [("P", ce.PRIMARY)] + list(ce.ALTERNATES.items())


def table_ii():
    print("== Table II (O3): max |computed - printed| over 20 halides, no hydrogen")
    for label, readings, column in (("P  vs Q_QEq", ce.PRIMARY, "Q_QEq"), ("R4 vs Q_lambda=0.5", ce.ALTERNATES["R4"], "Q_lambda_0_5")):
        worst = max(
            (abs(ce.qeq_charges(*diatomic(r["metal"], r["halogen"], r_e(r["molecule"])), readings=readings).charges[0] - float(r[column])), r["molecule"])
            for r in rows("rappe1991_table2.csv")
        )
        print(f"   {label:22} worst {worst[0]:.4f} e ({worst[1]})")


def hydrides():
    cases = [("Table III", "HF", ("H", "F"), "HF", 0.001), ("Table III", "LiH", ("Li", "H"), "LiH", 0.001)]
    printed3 = {r["molecule"]: r for r in rows("rappe1991_table3.csv")}
    printed4 = {(r["molecule"]): r for r in rows("rappe1991_table4.csv") if r["status"] == "printed" and r["molecule"] in ("HF", "ClH")}
    print("\n== Diatomic hydrides (O4 tol 0.001, O5 tol 0.01): Q_H by reading")
    print(f"   {'row':18} {'set':12} {'printed':>8}  " + "  ".join(f"{name:>16}" for name, _ in READINGS))
    table = [(f"III {m}", g, e, printed3[m]) for _t, m, e, g, _tol in cases] + [
        ("IV HF", "HF", ("H", "F"), printed4["HF"]), ("IV ClH", "HCl", ("H", "Cl"), printed4["ClH"])]
    for label, geometry, elements, printed in table:
        for column, hydrogen in (("QEq", "experimental"), ("QEqHF", "hf")):
            cells = []
            for _name, readings in READINGS:
                result = ce.qeq_charges(*diatomic(*elements, r_e(geometry)), hydrogen=hydrogen, readings=readings)
                if result.charges is None:
                    cells.append(f"{'no conv (' + result.trace_class[:4] + ')':>16}")
                else:
                    q = result.charges[elements.index("H")]
                    cells.append(f"{q:+.4f} ({q - float(printed[column]):+.4f})")
            print(f"   {label:18} {column:12} {float(printed[column]):>+8.3f}  " + "  ".join(cells))


def lih_fixed_points():
    print("\n== LiH: does a self-consistent Q_H exist? g(Q) = Q_solved(Q) - Q on trial charges")
    elements, coords = diatomic("Li", "H", r_e("LiH"))
    lower, upper = np.array([-7.0, -1.0]), np.array([1.0, 1.0])
    for hydrogen in ("experimental", "hf"):
        for name, readings in READINGS:
            trial = np.linspace(-0.99, 0.0, 199)
            residual = []
            for q in trial:
                hardness, chi, _ = ce.qeq_hardness_matrix(elements, coords, {1: float(q)}, hydrogen, readings)
                solved = ce.solve_bounded(hardness, chi, 0.0, lower, upper).charges[1]
                residual.append(solved - q)
            residual = np.array(residual)
            roots = []
            for i in range(len(trial) - 1):
                if residual[i] == 0 or residual[i] * residual[i + 1] < 0:
                    a, b = trial[i], trial[i + 1]
                    ga, gb = residual[i], residual[i + 1]
                    roots.append(a - ga * (b - a) / (gb - ga))
            # slope of the iteration map at the root: |1 + g'| > 1 means plain iteration cannot converge there
            slopes = []
            for root in roots:
                h = 1e-5
                values = []
                for q in (root - h, root + h):
                    hardness, chi, _ = ce.qeq_hardness_matrix(elements, coords, {1: float(q)}, hydrogen, readings)
                    values.append(ce.solve_bounded(hardness, chi, 0.0, lower, upper).charges[1])
                slopes.append((values[1] - values[0]) / (2 * h))
            shown = ", ".join(f"Q_H={r:+.4f} (map slope {s:+.2f})" for r, s in zip(roots, slopes)) or "none in [-0.99, 0]"
            print(f"   {hydrogen:12} {name:3} {shown}")


def o9_summary():
    import test_charge_equilibration as t

    print("\n== O9: never-release fixing against the constrained optimum (200 synthetic systems)")
    missed = wanting = 0
    worst = 0.0
    for C, chi, net, lo, up in t.SYNTHETIC:
        solved = ce.solve_bounded(C, chi, net, lo, up)
        optimum = t._kkt_optimum(C, chi, net, lo, up)
        gap = float(np.max(np.abs(solved.charges - optimum)))
        if gap <= 1e-10:
            continue
        missed += 1
        worst = max(worst, gap)
        fixed = solved.passes[-1]
        free = [i for i in range(len(chi)) if i not in fixed]
        if free:
            mu = float(np.mean((chi + C @ solved.charges)[free]))
            g = chi + C @ solved.charges - mu
            if any((v == lo[i] and g[i] < -1e-9) or (v == up[i] and g[i] > 1e-9) for i, v in fixed.items()):
                wanting += 1
    print(f"   missed the optimum: {missed} of 200 (worst max|dq| {worst:.3f} e); a fixed atom wants back inside in {wanting}")


if __name__ == "__main__":
    table_ii()
    hydrides()
    lih_fixed_points()
    o9_summary()
