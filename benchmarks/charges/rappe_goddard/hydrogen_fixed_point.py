"""Amendment A7's diagnostics, run exactly as frozen.

    uv run --no-sync python benchmarks/charges/rappe_goddard/hydrogen_fixed_point.py

Prints Q-A/Q-B/Q-C for LiH, the mixing invariant, Ramachandran 1996's water,
and SiH4's geometry sweep, and writes `lih_g_scan.csv` beside this file.
Changes nothing in the solver and selects nothing.
"""

from __future__ import annotations

import csv
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from openchem.chem import charge_equilibration as ce  # noqa: E402
import qeq_fixed_point as fp  # noqa: E402
import qeq_geometries as geo  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "charges"
PRINTED_LIH = {"experimental": -0.767, "hf": -0.679}
ALPHAS = (1.0, 0.75, 0.5, 0.25, 0.1, 0.05)


def r_e(molecule: str) -> float:
    lines = [l for l in (FIXTURES / "geometries.csv").read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    return next(float(r["r_e_A"]) for r in csv.DictReader(lines) if r["molecule"] == molecule)


def lih_map(hydrogen: str) -> fp.HydrogenMap:
    return fp.HydrogenMap(["Li", "H"], np.array([[0.0, 0.0, 0.0], [0.0, 0.0, r_e("LiH")]]), hydrogen)


def lih() -> None:
    print("== LiH under ADOPTED (A7)")
    rows = []
    for hydrogen in ("experimental", "hf"):
        F = lih_map(hydrogen)
        grid, values = fp.scan(F)
        rows.append((hydrogen, grid, values))
        found = fp.roots(F, grid, values)
        print(f"-- {hydrogen}")
        print(f"   Q-A: {len([r for r in found if r.kind == 'root'])} root(s), {len([r for r in found if r.kind == 'tangency'])} tangency candidate(s)")
        slope = None
        for r in found:
            print(f"      {r.kind}: Q* = {r.q:+.6f}, |g| = {abs(r.residual):.1e}")
            if r.kind != "root":
                continue
            solved = F.solve(r.q)
            sets = fp.active_sets_near(F, r.q)
            charges = solved.charges
            print(f"      active set at Q*: {dict(solved.passes[-1]) or 'none'}; distinct sets within +-1e-3: {len(sets)}")
            for i, e in enumerate(F.elements):
                print(f"      {e}: q = {charges[i]:+.6f}, to lower {charges[i] - F.lower[i]:.4f}, to upper {F.upper[i] - charges[i]:.4f}")
            s = fp.slopes(F, r.q)
            spread = max(s.values()) - min(s.values())
            print("      slope by h: " + ", ".join(f"{h:.0e}: {v:+.4f}" for h, v in s.items()) + f"; spread {spread:.4f} ({'stable' if spread <= 0.05 else 'UNSTABLE'})")
            slope = s[1e-5]
        printed = PRINTED_LIH[hydrogen]
        print(f"   Q-B: g({printed}) = {fp.g(F, printed):+.4f}")
        print("   Q-C: alpha  predicted  observed  bin            iterations  final Q_H   |step|    |F(Q)-Q|")
        for alpha in ALPHAS:
            it = fp.iterate(F, alpha)
            predicted = fp.predicted_to_converge(alpha, slope) if slope is not None else None
            print(f"        {alpha:<5}  {str(predicted):9}  {str(it.converged):8}  {fp.iteration_bin(it):14} {it.iterations:10}  {it.q[0]:+.6f}  {it.step:.1e}  {it.residual:.1e}")
    with open(HERE / "lih_g_scan.csv", "w", newline="", encoding="utf-8") as handle:
        handle.write("# g(Q) = F(Q) - Q for LiH under ADOPTED, Huber-Herzberg r_e; amendment A7's frozen 2001-point grid.\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Q_H", "g_experimental", "g_hf"])
        for k, q in enumerate(rows[0][1]):
            writer.writerow([f"{q:.3f}", f"{rows[0][2][k]:.10f}", f"{rows[1][2][k]:.10f}"])


def invariant() -> None:
    print("\n== Mixing invariant: alpha = 1 vs alpha = 0.5, each converged independently")
    cases = {"HF": (["H", "F"], np.array([[0, 0, 0], [0, 0, r_e("HF")]], dtype=float))}
    for name in ("H2O", "NH3", "CH4"):
        elements, coords, _, _ = geo.build(name)
        cases[name] = (elements, coords)
    for name, (elements, coords) in cases.items():
        for hydrogen in ("experimental", "hf"):
            F = fp.HydrogenMap(elements, coords, hydrogen)
            plain, mixed = fp.iterate(F, 1.0), fp.iterate(F, 0.5)
            stored = ce.qeq_charges(elements, coords, hydrogen=hydrogen)
            gap = float(np.max(np.abs(plain.q - mixed.q)))
            regression = float(np.max(np.abs(plain.q - stored.charges[F.hydrogens])))
            print(f"   {name:4} {hydrogen:12} converged {plain.converged}/{mixed.converged} in {plain.iterations}/{mixed.iterations}; "
                  f"max|plain - mixed| {gap:.1e} ({'held' if gap <= 1e-7 else 'FAILED'}); vs stored {regression:.1e}")


def water() -> None:
    print("\n== Ramachandran 1996 water: 0.9572 A, 104.52 deg, experimental set, printed 0.353 +- 0.001")
    half = math.radians(104.52 / 2)
    coords = np.array([[0, 0, 0], [0.9572 * math.sin(half), 0, 0.9572 * math.cos(half)], [-0.9572 * math.sin(half), 0, 0.9572 * math.cos(half)]])
    result = ce.qeq_charges(["O", "H", "H"], coords, hydrogen="experimental")
    q = result.charges[1:]
    print(f"   {result.status}: H = {q[0]:+.4f}, {q[1]:+.4f} ({'held' if all(abs(v - 0.353) <= 0.001 for v in q) else 'FAILED'})")


def silane() -> None:
    print("\n== SiH4 geometry sensitivity (D2d), printed +0.13 experimental / +0.11 hf")
    for hydrogen, printed in (("experimental", 0.13), ("hf", 0.11)):
        values = []
        for bond in (1.45, 1.48, 1.51):
            for delta in (-5.0, -2.5, 0.0, 2.5, 5.0):
                theta = math.radians(109.4712206 + delta)
                a, c = bond * math.sin(theta / 2), bond * math.cos(theta / 2)
                coords = np.array([[0, 0, 0], [a, 0, c], [-a, 0, c], [0, a, -c], [0, -a, -c]])
                result = ce.qeq_charges(["Si", "H", "H", "H", "H"], coords, hydrogen=hydrogen)
                values.extend(result.charges[1:].tolist())
        print(f"   {hydrogen:12} Q_H from {min(values):+.4f} to {max(values):+.4f}; reaches {printed:+.2f}: {max(values) >= printed}")


if __name__ == "__main__":
    lih()
    invariant()
    water()
    silane()
