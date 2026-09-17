"""QTPIE and QEq(-H) in Chen's Gaussian atom-space form, written from the thesis's equations.

    uv run --no-sync python benchmarks/charges/models/qtpie_cleanroom_check.py

Frozen by `qtpie_cleanroom_preregistration.md`. A CLEAN-ROOM implementation: the equations are the
thesis's eqs 2.14, 3.21 and 3.25 and the normalised s-Gaussian overlap; the parameter values, unit
constants, exponents and expected charges are facts read from the thesis. No part of the author's code is
reproduced here (the thesis is under arXiv's non-exclusive licence).
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.optimize import brentq, least_squares
from scipy.special import erf

HERE = pathlib.Path(__file__).resolve().parent
EV = 3.67493245e-2               # hartree per eV (thesis, conversion-factor module)
BOHR_PER_ANGSTROM = 1.0 / 0.529177249
#: (chi, J) in eV, as printed; equal to Rappe-Goddard Table I for these four elements.
PARAMETERS = {"H": (4.528, 13.890), "O": (8.741, 13.364), "Na": (2.843, 4.592), "Cl": (8.564, 9.892)}
EXPONENTS = {
    "E_app": {"H": 0.534337523756312, "O": 0.223967308625516, "Na": 0.095892938712585, "Cl": 0.113714050615107},
    "E_tab": {"H": 0.5434, "O": 0.2240, "Na": 0.0959, "Cl": 0.1137},
}
KERNELS = ("K_code", "K_print")
#: The test program's printed charges and its own tolerance.
ORACLE = {
    "NaCl": {"QEq": 1.3895802392931755, "QTPIE": 0.72522900679059155},
    "H2O": {"QEq_O": -0.98965172663781498, "QEq_H2": 0.49438117990925540,
            "QTPIE_O": -0.81213640965, "QTPIE_H2": 0.40556679590604666},
}
TOLERANCE = 1e-6


def coulomb_kernel(a: float, b: float, r_bohr: float, kernel: str) -> float:
    """Two-centre Coulomb integral between s-Gaussians, hartree. K_print is eq 2.14 generalised (ours)."""
    reduced = a * b / (a + b)
    p = math.sqrt(reduced if kernel == "K_code" else 2.0 * reduced)
    return math.erf(p * r_bohr) / r_bohr


def overlap(a: float, b: float, r_bohr: float) -> float:
    """Normalised s-Gaussian overlap; 1 at r = 0 for equal exponents."""
    return (4.0 * a * b / (a + b) ** 2) ** 0.75 * math.exp(-a * b / (a + b) * r_bohr ** 2)


def charges(elements: list[str], coords_angstrom, model: str, exponents: dict, kernel: str) -> np.ndarray:
    """Solve [[J, 1], [1^T, 0]] (q, mu) = (-v, 0): v = chi for QEq(-H), eq 3.25 for QTPIE."""
    xyz = np.asarray(coords_angstrom, dtype=float) * BOHR_PER_ANGSTROM
    n = len(elements)
    chi = np.array([PARAMETERS[e][0] * EV for e in elements])
    alpha = [exponents[e] for e in elements]
    A = np.zeros((n + 1, n + 1))
    S = np.eye(n)
    for i in range(n):
        A[i, i] = PARAMETERS[elements[i]][1] * EV
        for j in range(i + 1, n):
            r = float(np.linalg.norm(xyz[i] - xyz[j]))
            A[i, j] = A[j, i] = coulomb_kernel(alpha[i], alpha[j], r, kernel)
            S[i, j] = S[j, i] = overlap(alpha[i], alpha[j], r)
    A[:n, n] = 1.0
    A[n, :n] = 1.0
    if model == "QEq":
        v = chi
    elif model == "QTPIE":
        v = ((chi[:, None] - chi[None, :]) * S).sum(axis=1) / S.sum(axis=1)
    else:
        raise ValueError(model)
    rhs = np.concatenate([-v, [0.0]])
    return np.linalg.solve(A, rhs)[:n]


def nacl(r_angstrom: float, model: str, exponents: dict, kernel: str) -> float:
    return float(charges(["Na", "Cl"], [[0, 0, 0], [r_angstrom, 0, 0]], model, exponents, kernel)[0])


def water_coords(r1: float, r2: float, theta_deg: float) -> list[list[float]]:
    t = math.radians(theta_deg)
    return [[0.0, 0.0, 0.0], [r1, 0.0, 0.0], [r2 * math.cos(t), r2 * math.sin(t), 0.0]]


def recover_nacl(exponents: dict, kernel: str) -> dict:
    grid = np.round(np.arange(1.5, 4.0 + 1e-9, 0.001), 6)
    f = [nacl(r, "QEq", exponents, kernel) - ORACLE["NaCl"]["QEq"] for r in grid]
    roots = []
    for k in range(len(grid) - 1):
        if f[k] == 0.0:
            roots.append(float(grid[k]))
        elif f[k] * f[k + 1] < 0:
            roots.append(brentq(lambda r: nacl(r, "QEq", exponents, kernel) - ORACLE["NaCl"]["QEq"], grid[k], grid[k + 1], xtol=1e-12, rtol=1e-15))
    out = {"roots_angstrom": roots}
    if len(roots) == 1:
        predicted = nacl(roots[0], "QTPIE", exponents, kernel)
        out.update(predicted_QTPIE_Na=predicted, printed=ORACLE["NaCl"]["QTPIE"],
                   abs_diff=abs(predicted - ORACLE["NaCl"]["QTPIE"]),
                   status="PASS" if abs(predicted - ORACLE["NaCl"]["QTPIE"]) <= TOLERANCE else "FAIL")
    else:
        out["status"] = "UNDETERMINED"
    return out


def recover_water(exponents: dict, kernel: str) -> dict:
    def residual(x):
        coords = water_coords(*x)
        qeq = charges(["O", "H", "H"], coords, "QEq", exponents, kernel)
        qtpie = charges(["O", "H", "H"], coords, "QTPIE", exponents, kernel)
        return [qeq[0] - ORACLE["H2O"]["QEq_O"], qeq[1] - ORACLE["H2O"]["QEq_H2"], qtpie[0] - ORACLE["H2O"]["QTPIE_O"]]

    solutions = []
    for r1 in np.linspace(0.8, 1.2, 5):
        for r2 in np.linspace(0.8, 1.2, 5):
            for theta in np.linspace(90.0, 120.0, 5):
                fit = least_squares(residual, [r1, r2, theta], bounds=([0.5, 0.5, 60.0], [2.0, 2.0, 180.0]),
                                    xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=2000)
                if np.max(np.abs(fit.fun)) <= 1e-10 and 0.8 <= fit.x[0] <= 1.2 and 0.8 <= fit.x[1] <= 1.2 and 90 <= fit.x[2] <= 120:
                    if not any(abs(fit.x[0] - s[0]) <= 1e-6 and abs(fit.x[1] - s[1]) <= 1e-6 and abs(fit.x[2] - s[2]) <= 1e-4 for s in solutions):
                        solutions.append([float(v) for v in fit.x])
    predictions = [float(charges(["O", "H", "H"], water_coords(*s), "QTPIE", exponents, kernel)[1]) for s in solutions]
    out = {"solutions_r1_r2_theta": solutions, "predicted_QTPIE_H2": predictions, "printed": ORACLE["H2O"]["QTPIE_H2"]}
    if not solutions or (max(predictions) - min(predictions) > TOLERANCE):
        out["status"] = "UNDETERMINED"
    else:
        diffs = [abs(p - ORACLE["H2O"]["QTPIE_H2"]) for p in predictions]
        out["abs_diff_max"] = max(diffs)
        out["status"] = "PASS" if max(diffs) <= TOLERANCE else "FAIL"
    return out


def verdict(nacl_status: str, water_status: str) -> str:
    statuses = (nacl_status, water_status)
    if statuses == ("PASS", "PASS"):
        return "REPRODUCED"
    if "UNDETERMINED" in statuses:
        return "UNDETERMINED"
    if "PASS" in statuses:
        return "PARTIAL"
    return "NOT-REPRODUCED"


def main() -> None:
    results = {}
    for exp_name, exponents in EXPONENTS.items():
        for kernel in KERNELS:
            arm = f"{exp_name}/{kernel}"
            n = recover_nacl(exponents, kernel)
            w = recover_water(exponents, kernel)
            results[arm] = {"NaCl": n, "H2O": w, "verdict": verdict(n["status"], w["status"])}
            print(arm, results[arm]["verdict"], "NaCl", n["status"], n.get("abs_diff"), "H2O", w["status"], w.get("abs_diff_max"))
    path = HERE / "qtpie_cleanroom_results.json"
    path.write_bytes((json.dumps(results, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    import hashlib
    print("wrote", path.name, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    sys.exit(main())
