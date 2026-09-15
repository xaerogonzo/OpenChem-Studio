"""Amendment A10's hydrogen refit, run exactly as frozen.

    uv run --no-sync python benchmarks/charges/rappe_goddard/hydrogen_refit.py [--workers N] [--variants V0,H-b]

Repeats Rappé & Goddard's own hydrogen fit (section IV; weights from their
ref 20) under each pre-registered reading, with a rounding-recovery control,
and writes beside this file:

- hydrogen_refit.csv          one row per variant x column, printed pair first
- hydrogen_refit_basins.csv   every grid basin and Nelder-Mead endpoint
- hydrogen_refit_control.csv  every control draw's refit
- hydrogen_refit_traces.csv   H-a's iterates at the printed pairs

Changes nothing in the solver and ships nothing. The instrument's matrices are
the shipped build's, with only hydrogen's chi entry and diagonal set from the
trial pair; `tests/test_charge_equilibration.py` holds them equal.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from openchem.chem import charge_equilibration as ce  # noqa: E402
import qeq_geometries as geo  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "charges"

MOLECULES = ("HF", "H2O", "NH3", "CH4", "LiH")
DIATOMICS = {"HF", "LiH"}
#: Ref 20: "In this fit we weighted CH4 as 5, LiH as 0.2, and the others as 1."
#: The weights themselves multiply the squared residuals -- never their roots.
WEIGHTS = {"HF": 1.0, "H2O": 1.0, "NH3": 1.0, "CH4": 5.0, "LiH": 0.2}
COLUMNS = ("experimental", "hf")
PRINTED = {"experimental": (4.5280, 13.8904), "hf": (4.7174, 13.4725)}
TARGET_COLUMN = {"experimental": "exptl", "hf": "HF"}
PROGRAM_COLUMN = {"experimental": "QEq", "hf": "QEqHF"}

BOX = ((4.0, 5.5), (12.0, 15.0))
GRID_Q = np.linspace(-1.0, 1.0, 2001)
SYMMETRY_TOLERANCE = 1e-10
ROOT_RESIDUAL = 1e-11
CONTROL_DRAWS = 200
CONTROL_SEED = 20260915


@dataclass(frozen=True)
class Variant:
    name: str
    readings: ce.QEqReadings
    #: None: Q_H is the self-consistent root. k: Q_H = F^k(0).
    iterations: int | None = None
    #: H-d: the Q entering hydrogen's diagonal is clamped to +-clamp.
    clamp: float | None = None

    @property
    def self_factor(self) -> float:
        # Mirrors `_QEqSystem.build`: eq 21's 1, or eq 23's gradient's 1.5.
        return 1.0 if self.readings.hydrogen_self_term == "eq21" else 1.5


VARIANTS = (
    Variant("V0", ce.ADOPTED),
    *(Variant(f"H-a{k}", ce.ADOPTED, iterations=k) for k in (6, 7, 8, 9, 10)),
    Variant("H-b", replace(ce.ADOPTED, hydrogen_self_term="eq23_gradient")),
    Variant("H-c", replace(ce.ADOPTED, zeta_h_in_pairs=False)),
    Variant("H-d", replace(ce.ADOPTED, zeta_h_in_pairs=False), clamp=0.95),
)
VARIANTS_BY_NAME = {v.name: v for v in VARIANTS}


def _rows(name: str) -> list[dict[str, str]]:
    lines = [line for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    return list(csv.DictReader(lines))


def table_iii() -> dict[str, dict[str, float]]:
    return {r["molecule"]: {k: float(v) for k, v in r.items() if k != "molecule"} for r in _rows("rappe1991_table3.csv")}


def structure(name: str) -> tuple[list[str], np.ndarray]:
    """O4's geometries: Huber r_e for the diatomics, A4's builders otherwise."""
    if name in DIATOMICS:
        r_e = next(float(r["r_e_A"]) for r in _rows("geometries.csv") if r["molecule"] == name)
        elements = ["H", "F"] if name == "HF" else ["Li", "H"]
        return elements, np.array([[0.0, 0.0, 0.0], [0.0, 0.0, r_e]])
    elements, coords, _, _ = geo.build(name)
    return list(elements), np.asarray(coords, dtype=float)


class Molecule:
    """One fit molecule under one variant's pair rule. Pair integrals over A7's
    Q grid do not depend on chi or J, so they are computed once here."""

    def __init__(self, name: str, variant: Variant):
        self.name = name
        self.variant = variant
        self.elements, self.coords = structure(name)
        n = self.n = len(self.elements)
        self.hydrogens = [i for i, e in enumerate(self.elements) if e == "H"]
        bounds = [ce.charge_bounds(e) for e in self.elements]
        self.lower = np.array([b[0] for b in bounds])
        self.upper = np.array([b[1] for b in bounds])
        readings = variant.readings
        diff = self.coords[:, None, :] - self.coords[None, :, :]
        distance = np.sqrt(np.sum(diff * diff, axis=-1)) / ce.QEQ_BOHR_ANGSTROM
        shells = [ce.QEQ_TABLE_I[e][0] for e in self.elements]
        zetas = [ce.valence_zeta(e, readings) for e in self.elements]
        self.base = np.zeros((n, n))
        self.chi_heavy = np.zeros(n)
        for i, e in enumerate(self.elements):
            if e != "H":
                self.base[i, i] = ce.QEQ_TABLE_I[e][2]
                self.chi_heavy[i] = ce.QEQ_TABLE_I[e][1]
        # Pairs with no hydrogen never move.
        self.pairs: list[tuple[int, int, int]] = []  # (i, j, unique index)
        unique: dict[tuple, int] = {}
        self.unique_spec: list[tuple[int, int, float, float, float, bool, bool]] = []
        for i in range(n):
            for j in range(i + 1, n):
                hi, hj = i in self.hydrogens, j in self.hydrogens
                if not (hi or hj):
                    value = ce.coulomb_pair_integrals(shells[i], shells[j], np.array([zetas[i]]), np.array([zetas[j]]), np.array([distance[i, j]]))[0] * ce.HARTREE_EV
                    self.base[i, j] = self.base[j, i] = value
                    continue
                # Symmetry-identical integrals (same shells, same exponent rule,
                # distance equal to 1e-12 A) are computed once.
                key = (shells[i], shells[j], hi, hj, zetas[i], zetas[j], round(distance[i, j] * ce.QEQ_BOHR_ANGSTROM * 1e12))
                if key not in unique:
                    unique[key] = len(self.unique_spec)
                    self.unique_spec.append((shells[i], shells[j], zetas[i], zetas[j], distance[i, j], hi, hj))
                self.pairs.append((i, j, unique[key]))
        self.moving = readings.zeta_h_in_pairs
        self.grid_pairs = self.pair_values(GRID_Q)
        self.fixed_pairs = None if self.moving else self.pair_values(np.zeros(1))[0]

    def pair_values(self, q: np.ndarray) -> np.ndarray:
        """(len(q), unique pairs) in eV: eq 20's zeta_H = zeta0 + Q in every
        hydrogen-involving pair, or the reading's fixed hydrogen zeta."""
        q = np.atleast_1d(np.asarray(q, dtype=float))
        out = np.empty((len(q), len(self.unique_spec)))
        for u, (na, nb, za, zb, r, hi, hj) in enumerate(self.unique_spec):
            zeta_a = ce.ZETA_H0 + q if (hi and self.moving) else np.full(len(q), za)
            zeta_b = ce.ZETA_H0 + q if (hj and self.moving) else np.full(len(q), zb)
            out[:, u] = ce.coulomb_pair_integrals(na, nb, zeta_a, zeta_b, np.full(len(q), r)) * ce.HARTREE_EV
        return out

    def system(self, q: np.ndarray, chi_h: float, j_h: float, pair_rows: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Stacked C (m, n, n) and chi (n,) at every hydrogen set to each q."""
        q = np.atleast_1d(np.asarray(q, dtype=float))
        if pair_rows is None:
            pair_rows = np.broadcast_to(self.fixed_pairs, (len(q), len(self.unique_spec))) if not self.moving else self.pair_values(q)
        C = np.broadcast_to(self.base, (len(q), self.n, self.n)).copy()
        for i, j, u in self.pairs:
            C[:, i, j] = pair_rows[:, u]
            C[:, j, i] = pair_rows[:, u]
        entering = np.clip(q, -self.variant.clamp, self.variant.clamp) if self.variant.clamp is not None else q
        diagonal = j_h * (1.0 + self.variant.self_factor * entering / ce.ZETA_H0)
        for h in self.hydrogens:
            C[:, h, h] = diagonal
        chi = self.chi_heavy.copy()
        chi[self.hydrogens] = chi_h
        return C, chi

    def image(self, q: np.ndarray, chi_h: float, j_h: float, pair_rows: np.ndarray | None = None) -> np.ndarray:
        """F(Q): hydrogen's charge after one build and bounded solve at every H = Q."""
        C, chi = self.system(q, chi_h, j_h, pair_rows)
        m, n = C.shape[0], self.n
        M = np.zeros((m, n + 1, n + 1))
        M[:, :n, :n] = C
        M[:, :n, n] = -1.0
        M[:, n, :n] = 1.0
        rhs = np.zeros((m, n + 1))
        rhs[:, :n] = -chi
        charges = np.linalg.solve(M, rhs[..., None])[:, :n, 0]
        crossed = np.any((charges > self.upper) | (charges < self.lower), axis=1)
        for row in np.flatnonzero(crossed):
            charges[row] = ce.solve_bounded(C[row], chi, 0.0, self.lower, self.upper).charges
        h = charges[:, self.hydrogens]
        spread = np.max(h, axis=1) - np.min(h, axis=1)
        assert np.all(spread <= SYMMETRY_TOLERANCE), (self.name, float(spread.max()))
        return h[:, 0]

    def residual(self, q, chi_h, j_h, pair_rows=None) -> np.ndarray:
        q = np.atleast_1d(np.asarray(q, dtype=float))
        return self.image(q, chi_h, j_h, pair_rows) - q

    def charge(self, chi_h: float, j_h: float) -> float | None:
        """Q_H under this variant, or None where A10 makes S infinite."""
        if self.variant.iterations is not None:
            q = 0.0
            for _ in range(self.variant.iterations):
                q = float(self.image(np.array([q]), chi_h, j_h)[0])
            return q
        return self.root(chi_h, j_h)

    def trace(self, chi_h: float, j_h: float) -> list[float]:
        q, out = 0.0, [0.0]
        for _ in range(self.variant.iterations or 0):
            q = float(self.image(np.array([q]), chi_h, j_h)[0])
            out.append(q)
        return out

    def bound_free(self, q: float, chi_h: float, j_h: float) -> bool:
        C, chi = self.system(np.array([q]), chi_h, j_h)
        return not ce.solve_bounded(C[0], chi, 0.0, self.lower, self.upper).passes[-1]

    def fixed_points(self, chi_h: float, j_h: float) -> tuple[list[float], list[float]]:
        """(bound-free roots, bound-pinned roots) of g on [-1, +1], A10 as corrected.

        The bounded solve makes F discontinuous where its active set switches,
        so a sign change of g is not a root: each is refined, and kept only if
        |g| <= 1e-11 at the refined point. A jump never passes that."""
        pair_rows = self.grid_pairs if self.moving else None
        g = self.residual(GRID_Q, chi_h, j_h, pair_rows)
        found: list[float] = [float(GRID_Q[i]) for i in np.flatnonzero(g == 0.0)]
        for i in np.flatnonzero(g[:-1] * g[1:] < 0):
            q = self._refine(float(GRID_Q[i]), float(GRID_Q[i + 1]), chi_h, j_h)
            if q is not None:
                found.append(q)
        free, pinned = [], []
        for q in sorted(found):
            if abs(float(self.residual(q, chi_h, j_h)[0])) > ROOT_RESIDUAL:
                continue
            bucket = free if self.bound_free(q, chi_h, j_h) else pinned
            if not any(abs(q - p) <= 1e-9 for p in bucket):
                bucket.append(q)
        return free, pinned

    def _refine(self, a: float, b: float, chi_h: float, j_h: float) -> float | None:
        for _ in range(2):
            points = np.linspace(a, b, 9)
            values = self.residual(points, chi_h, j_h)
            hit = np.flatnonzero(values == 0.0)
            if len(hit):
                return float(points[hit[0]])
            inside = np.flatnonzero(values[:-1] * values[1:] < 0)
            if len(inside) != 1:
                return None
            k = int(inside[0])
            a, b = float(points[k]), float(points[k + 1])
        # A cubic through the four points nearest the sign change.
        lo = min(max(k - 1, 0), len(points) - 4)
        x, y = points[lo:lo + 4], values[lo:lo + 4]
        scale = points[1] - points[0]
        coefficients = np.polyfit((x - a) / scale, y, 3)
        candidates = [a + r.real * scale for r in np.roots(coefficients) if abs(r.imag) < 1e-9 and -1e-9 <= r.real <= 1.0 + 1e-9]
        return float(candidates[0]) if len(candidates) == 1 else None

    def root(self, chi_h: float, j_h: float) -> float | None:
        """The unique bound-free self-consistent charge, or None (S = +inf)."""
        free, _ = self.fixed_points(chi_h, j_h)
        return free[0] if len(free) == 1 else None


class Fit:
    """S(chi, J) for one variant against one column's targets."""

    def __init__(self, variant: Variant, targets: dict[str, float], weights: dict[str, float] = WEIGHTS):
        self.variant = variant
        self.targets = dict(targets)
        self.weights = dict(weights)
        self.molecules = {name: Molecule(name, variant) for name in MOLECULES}
        self.evaluations = 0
        self.infinite = 0

    def charges(self, chi_h: float, j_h: float) -> dict[str, float | None]:
        return {name: m.charge(chi_h, j_h) for name, m in self.molecules.items()}

    def objective(self, x, targets: dict[str, float] | None = None) -> float:
        chi_h, j_h = float(x[0]), float(x[1])
        self.evaluations += 1
        if not (BOX[0][0] <= chi_h <= BOX[0][1] and BOX[1][0] <= j_h <= BOX[1][1]):
            return math.inf
        targets = targets or self.targets
        total = 0.0
        for name, m in self.molecules.items():
            q = m.charge(chi_h, j_h)
            if q is None:
                self.infinite += 1
                return math.inf
            total += self.weights[name] * (q - targets[name]) ** 2
        return total


def objective_from_charges(charges: dict[str, float], targets: dict[str, float], weights: dict[str, float] = WEIGHTS) -> float:
    return sum(weights[name] * (charges[name] - targets[name]) ** 2 for name in MOLECULES)


def nelder_mead(f, x0, step: float = 0.05, xatol: float = 1e-6, fatol: float = 1e-10, maxiter: int = 4000):
    """Standard Nelder-Mead (reflection 1, expansion 2, contraction 1/2,
    shrink 1/2), written here because scipy is not in the environment (A10)."""
    x0 = np.asarray(x0, dtype=float)
    simplex = [x0, x0 + np.array([step, 0.0]), x0 + np.array([0.0, step])]
    values = [f(x) for x in simplex]
    iterations = 0
    while True:
        order = np.argsort(values)
        simplex = [simplex[i] for i in order]
        values = [values[i] for i in order]
        if not math.isfinite(values[0]):
            return simplex[0], values[0], iterations, False
        spread_x = max(float(np.max(np.abs(s - simplex[0]))) for s in simplex[1:])
        spread_f = max(abs(v - values[0]) if math.isfinite(v) else math.inf for v in values[1:])
        if spread_x <= xatol and spread_f <= fatol:
            return simplex[0], values[0], iterations, True
        if iterations >= maxiter:
            return simplex[0], values[0], iterations, False
        iterations += 1
        centroid = (simplex[0] + simplex[1]) / 2.0
        worst = simplex[2]
        xr = centroid + (centroid - worst)
        fr = f(xr)
        if fr < values[0]:
            xe = centroid + 2.0 * (centroid - worst)
            fe = f(xe)
            simplex[2], values[2] = (xe, fe) if fe < fr else (xr, fr)
            continue
        if fr < values[1]:
            simplex[2], values[2] = xr, fr
            continue
        if fr < values[2]:
            xc = centroid + 0.5 * (xr - centroid)
            fc = f(xc)
            if fc <= fr:
                simplex[2], values[2] = xc, fc
                continue
        else:
            xc = centroid + 0.5 * (worst - centroid)
            fc = f(xc)
            if fc < values[2]:
                simplex[2], values[2] = xc, fc
                continue
        for i in (1, 2):
            simplex[i] = simplex[0] + 0.5 * (simplex[i] - simplex[0])
            values[i] = f(simplex[i])


def group_basins(points: list[tuple[np.ndarray, float]], radius: float = 1e-3) -> list[tuple[np.ndarray, float, int]]:
    basins: list[list] = []
    for x, s in sorted((p for p in points if math.isfinite(p[1])), key=lambda p: p[1]):
        for basin in basins:
            if float(np.max(np.abs(x - basin[0]))) <= radius:
                basin[2] += 1
                break
        else:
            basins.append([x, s, 1])
    return [(b[0], b[1], b[2]) for b in basins]


def grid_basins(surface: np.ndarray, chis: np.ndarray, js: np.ndarray) -> list[tuple[np.ndarray, float]]:
    found = []
    rows, cols = surface.shape
    for a in range(rows):
        for b in range(cols):
            s = surface[a, b]
            if not math.isfinite(s):
                continue
            neighbours = [surface[a + da, b + db] for da in (-1, 0, 1) for db in (-1, 0, 1)
                          if (da or db) and 0 <= a + da < rows and 0 <= b + db < cols]
            if all(s <= t for t in neighbours):
                found.append((np.array([chis[a], js[b]]), float(s)))
    return found


def residual_summary(charges: dict[str, float | None], targets: dict[str, float]) -> dict[str, float]:
    if any(v is None for v in charges.values()):
        return {"max_abs": math.nan, "lih": math.nan, "non_lih_rms": math.nan, "non_lih_max": math.nan}
    res = {name: charges[name] - targets[name] for name in MOLECULES}
    non = [res[n] for n in MOLECULES if n != "LiH"]
    return {
        "max_abs": max(abs(v) for v in res.values()),
        "lih": res["LiH"],
        "non_lih_rms": math.sqrt(sum(v * v for v in non) / len(non)),
        "non_lih_max": max(abs(v) for v in non),
    }


def elongation(surface: np.ndarray, chis: np.ndarray, js: np.ndarray, centre: np.ndarray) -> float:
    xs, ys, zs = [], [], []
    for a, c in enumerate(chis):
        for b, j in enumerate(js):
            if math.isfinite(surface[a, b]):
                xs.append(c - centre[0]); ys.append(j - centre[1]); zs.append(surface[a, b])
    xs, ys, zs = map(np.array, (xs, ys, zs))
    design = np.column_stack([np.ones_like(xs), xs, ys, xs * xs, xs * ys, ys * ys])
    coefficients, *_ = np.linalg.lstsq(design, zs, rcond=None)
    hessian = np.array([[2 * coefficients[3], coefficients[4]], [coefficients[4], 2 * coefficients[5]]])
    eig = np.linalg.eigvalsh(hessian)
    return math.sqrt(eig[1] / eig[0]) if eig[0] > 0 else math.inf


def run_job(variant_name: str, column: str, draws: int = CONTROL_DRAWS) -> dict:
    """Everything A10 reports for one variant and column, in its order."""
    started = time.perf_counter()
    variant = VARIANTS_BY_NAME[variant_name]
    table = table_iii()
    targets = {m: table[m][TARGET_COLUMN[column]] for m in MOLECULES}
    fit = Fit(variant, targets)
    printed = np.array(PRINTED[column])
    out: dict = {"variant": variant_name, "column": column}

    # 1. At the printed pair, first.
    q_printed = fit.charges(*printed)
    out["q_printed"] = q_printed
    out["S_printed"] = fit.objective(printed)
    h = 1e-4
    out["dS_dchi"] = (fit.objective(printed + [h, 0]) - fit.objective(printed - [h, 0])) / (2 * h)
    out["dS_dJ"] = (fit.objective(printed + [0, h]) - fit.objective(printed - [0, h])) / (2 * h)
    out["res_printed"] = residual_summary(q_printed, targets)
    program = {m: table[m][PROGRAM_COLUMN[column]] for m in MOLECULES}
    out["program_diff"] = {m: (q_printed[m] - program[m]) if q_printed[m] is not None else math.nan for m in MOLECULES}
    out["program_pass"] = all(
        q_printed[m] is not None and abs(q_printed[m] - program[m]) <= (0.001 if m in DIATOMICS else 0.002)
        for m in MOLECULES
    )
    if variant.iterations is not None:
        out["traces"] = {m: fit.molecules[m].trace(*printed) for m in MOLECULES}
        out["roots_printed"] = ""
    else:
        counts = {m: fit.molecules[m].fixed_points(*printed) for m in MOLECULES}
        out["roots_printed"] = ";".join(f"{m}:{len(f)}/{len(p)}" for m, (f, p) in counts.items())

    # 2. Rounding recovery control, before the real refit.
    rng = np.random.default_rng(CONTROL_SEED)
    control = []
    excluded = 0
    for draw in range(draws):
        dp = rng.uniform(-5e-5, 5e-5, 2)
        dq = rng.uniform(-5e-4, 5e-4, len(MOLECULES))
        generated = fit.charges(*(printed + dp))
        if any(v is None for v in generated.values()):
            excluded += 1
            control.append((draw, math.nan, math.nan, math.inf))
            continue
        noisy = {m: generated[m] + dq[k] for k, m in enumerate(MOLECULES)}
        x, s, _, _ = nelder_mead(lambda x: fit.objective(x, noisy), printed)
        if not math.isfinite(s):
            excluded += 1
        control.append((draw, float(x[0]), float(x[1]), s))
    finite = [c for c in control if math.isfinite(c[3])]
    out["control"] = control
    out["control_excluded"] = excluded
    out["env_chi"] = float(np.percentile([abs(c[1] - printed[0]) for c in finite], 95)) if finite else math.nan
    out["env_J"] = float(np.percentile([abs(c[2] - printed[1]) for c in finite], 95)) if finite else math.nan

    # 3. Global structure.
    chis = np.linspace(*BOX[0], 61)
    js = np.linspace(*BOX[1], 61)
    surface = np.array([[fit.objective((c, j)) for j in js] for c in chis])
    grid = grid_basins(surface, chis, js)
    out["grid_basins"] = grid

    # 4. Nelder-Mead from the 5 x 5 starts and the printed pair.
    starts = [np.array([c, j]) for c in np.linspace(*BOX[0], 5) for j in np.linspace(*BOX[1], 5)] + [printed]
    endpoints = []
    for start in starts:
        x, s, iterations, converged = nelder_mead(fit.objective, start)
        endpoints.append((start, x, s, iterations, converged))
    out["endpoints"] = endpoints
    basins = group_basins([(e[1], e[2]) for e in endpoints])
    out["nm_basins"] = basins
    if basins:
        best_x, best_s, _ = basins[0]
        out["ambiguous"] = [b for b in basins[1:] if b[1] - best_s < 1e-8]
        out["fit"] = best_x
        out["S_fit"] = best_s
        out["delta_S"] = out["S_printed"] - best_s
        q_fit = fit.charges(*best_x)
        out["q_fit"] = q_fit
        out["res_fit"] = residual_summary(q_fit, targets)
        # 5. The no-optimiser check.
        fc = np.linspace(best_x[0] - 0.05, best_x[0] + 0.05, 41)
        fj = np.linspace(best_x[1] - 0.05, best_x[1] + 0.05, 41)
        fine = np.array([[fit.objective((c, j)) for j in fj] for c in fc])
        a, b = np.unravel_index(np.argmin(np.where(np.isfinite(fine), fine, np.inf)), fine.shape)
        out["fine_min"] = (float(fc[a]), float(fj[b]), float(fine[a, b]))
        out["fine_ok"] = max(abs(fc[a] - best_x[0]), abs(fj[b] - best_x[1])) <= 0.0025 + 1e-12
        out["elongation"] = elongation(fine, fc, fj, best_x)
        out["within_envelope"] = (not out["ambiguous"]) and abs(best_x[0] - printed[0]) <= out["env_chi"] and abs(best_x[1] - printed[1]) <= out["env_J"]
    else:
        out.update(fit=None, S_fit=math.inf, delta_S=math.nan, ambiguous=[], q_fit=None, res_fit=None,
                   fine_min=None, fine_ok=False, elongation=math.nan, within_envelope=False)
    out["evaluations"] = fit.evaluations
    out["infinite_evaluations"] = fit.infinite
    out["seconds"] = time.perf_counter() - started
    return out


def classify(results: dict[tuple[str, str], dict], variant: str) -> str:
    met = [results[(variant, c)]["within_envelope"] and results[(variant, c)]["program_pass"] for c in COLUMNS]
    return "FIT-REPRODUCED" if all(met) else "PARTIAL" if any(met) else "UNEXPLAINED"


def ordering_inverted(results: dict[tuple[str, str], dict], variant: str) -> int | None:
    table = table_iii()
    count = 0
    for m in MOLECULES:
        a, b = results[(variant, "experimental")]["q_printed"][m], results[(variant, "hf")]["q_printed"][m]
        if a is None or b is None:
            return None
        if np.sign(a - b) != np.sign(table[m]["QEq"] - table[m]["QEqHF"]):
            count += 1
    return count


def _f(value, digits: int = 6) -> str:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    value = float(value)
    return "nan" if math.isnan(value) else ("inf" if math.isinf(value) else f"{value:.{digits}g}")


def write(results: dict[tuple[str, str], dict]) -> None:
    variants = sorted({v for v, _ in results}, key=lambda v: [x.name for x in VARIANTS].index(v))
    with open(HERE / "hydrogen_refit.csv", "w", newline="", encoding="utf-8") as handle:
        handle.write("# Amendment A10: Rappé–Goddard's hydrogen fit repeated per variant and column. Printed-pair columns first.\n")
        writer = csv.writer(handle, lineterminator="\n")
        header = ["variant", "column", "printed_chi", "printed_J", "S_printed", "dS_dchi", "dS_dJ", "max_abs_res_printed",
                  "lih_res_printed", "non_lih_rms_printed", "non_lih_max_printed"]
        header += [f"Q_{m}_printed" for m in MOLECULES] + ["roots_free_pinned_printed"] + [f"program_diff_{m}" for m in MOLECULES] + ["program_pass"]
        header += ["fit_chi", "fit_J", "S_fit", "delta_S", "max_abs_res_fit", "lih_res_fit", "non_lih_rms_fit", "non_lih_max_fit",
                   "grid_basins", "nm_basins", "ambiguous_basins", "fine_grid_ok", "elongation", "env_chi", "env_J",
                   "control_excluded", "within_envelope", "infinite_evaluations", "evaluations", "ordering_inverted", "verdict"]
        writer.writerow(header)
        for v in variants:
            verdict = classify(results, v)
            inverted = ordering_inverted(results, v)
            for c in COLUMNS:
                r = results[(v, c)]
                rp, rf = r["res_printed"], r["res_fit"] or {}
                fit = r["fit"] if r["fit"] is not None else (math.nan, math.nan)
                writer.writerow([v, c, *PRINTED[c], _f(r["S_printed"], 10), _f(r["dS_dchi"]), _f(r["dS_dJ"]), _f(rp["max_abs"]),
                                 _f(rp["lih"]), _f(rp["non_lih_rms"]), _f(rp["non_lih_max"]),
                                 *[_f(r["q_printed"][m], 8) for m in MOLECULES], r["roots_printed"],
                                 *[_f(r["program_diff"][m]) for m in MOLECULES],
                                 _f(r["program_pass"]), _f(fit[0], 8), _f(fit[1], 8), _f(r["S_fit"], 10), _f(r["delta_S"]),
                                 _f(rf.get("max_abs")), _f(rf.get("lih")), _f(rf.get("non_lih_rms")), _f(rf.get("non_lih_max")),
                                 len(r["grid_basins"]), len(r["nm_basins"]), len(r["ambiguous"]), _f(r["fine_ok"]), _f(r["elongation"]),
                                 _f(r["env_chi"]), _f(r["env_J"]), r["control_excluded"], _f(r["within_envelope"]),
                                 r["infinite_evaluations"], r["evaluations"], "" if inverted is None else inverted, verdict])
    with open(HERE / "hydrogen_refit_basins.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["variant", "column", "source", "start_chi", "start_J", "chi", "J", "S", "iterations", "converged", "members"])
        for (v, c), r in sorted(results.items()):
            for x, s in r["grid_basins"]:
                writer.writerow([v, c, "grid", "", "", _f(x[0], 8), _f(x[1], 8), _f(s, 10), "", "", ""])
            for start, x, s, it, ok in r["endpoints"]:
                writer.writerow([v, c, "nelder_mead", _f(start[0]), _f(start[1]), _f(x[0], 8), _f(x[1], 8), _f(s, 10), it, ok, ""])
            for x, s, members in r["nm_basins"]:
                writer.writerow([v, c, "nm_basin", "", "", _f(x[0], 8), _f(x[1], 8), _f(s, 10), "", "", members])
    with open(HERE / "hydrogen_refit_control.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["variant", "column", "draw", "fit_chi", "fit_J", "S"])
        for (v, c), r in sorted(results.items()):
            for draw, x, y, s in r["control"]:
                writer.writerow([v, c, draw, _f(x, 8), _f(y, 8), _f(s, 6)])
    traced = [(k, r) for k, r in sorted(results.items()) if "traces" in r]
    if traced:
        with open(HERE / "hydrogen_refit_traces.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["variant", "column", "molecule", "k", "Q_H"])
            for (v, c), r in traced:
                for m in MOLECULES:
                    for k, q in enumerate(r["traces"][m]):
                        writer.writerow([v, c, m, k, _f(q, 10)])


def _job(args):
    return run_job(*args)


def main() -> None:
    # Inherited by the spawned workers before they import numpy.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=min(18, os.cpu_count() or 1))
    parser.add_argument("--variants", default=",".join(v.name for v in VARIANTS))
    args = parser.parse_args()
    names = args.variants.split(",")
    jobs = [(v, c) for v in names for c in COLUMNS]
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for (v, c), result in zip(jobs, pool.map(_job, jobs)):
            results[(v, c)] = result
            print(f"{v:6} {c:12} done in {result['seconds']:.0f} s", flush=True)
    write(results)
    for v in names:
        print(f"{v:6} {classify(results, v)}")


if __name__ == "__main__":
    main()
