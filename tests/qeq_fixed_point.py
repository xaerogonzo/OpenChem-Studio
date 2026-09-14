"""The hydrogen fixed-point map of Rappé–Goddard QEq, and the diagnostics
amendment A7 freezes around it.

Not a test module: `tests/test_charge_equilibration.py` and
`benchmarks/charges/rappe_goddard/hydrogen_fixed_point.py` both use it, so the
suite and the report cannot disagree about what F is.

DIAGNOSTIC ONLY. Nothing here is, or may become, part of the solver: mixing
exists to show which fixed point an iteration reaches, never to rescue one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from openchem.chem import charge_equilibration as ce


class HydrogenMap:
    """F(q_H): one outer iteration of `ce.qeq_charges`, in its order (A7)."""

    def __init__(self, elements, coords, hydrogen="experimental", readings=ce.ADOPTED, net_charge=0.0):
        self.elements = list(elements)
        self.coords = np.asarray(coords, dtype=float)
        self.hydrogen = hydrogen
        self.readings = readings
        self.net_charge = net_charge
        self.hydrogens = [i for i, e in enumerate(self.elements) if e == "H"]
        bounds = [ce.charge_bounds(e) for e in self.elements]
        self.lower = np.array([b[0] for b in bounds])
        self.upper = np.array([b[1] for b in bounds])

    def solve(self, q_h) -> ce.BoundedSolve:
        q_h = np.atleast_1d(np.asarray(q_h, dtype=float))
        trial = {i: float(q) for i, q in zip(self.hydrogens, q_h)}
        hardness, chi, _ = ce.qeq_hardness_matrix(self.elements, self.coords, trial, self.hydrogen, self.readings)
        return ce.solve_bounded(hardness, chi, self.net_charge, self.lower, self.upper)

    def __call__(self, q_h) -> np.ndarray:
        return self.solve(q_h).charges[self.hydrogens]


def g(F: HydrogenMap, q: float) -> float:
    """The scalar residual F(Q) - Q, for a molecule with one hydrogen."""
    return float(F(q)[0] - q)


@dataclass
class Root:
    q: float
    residual: float
    kind: str  # "root" or "tangency"


def scan(F: HydrogenMap, points: int = 2001) -> tuple[np.ndarray, np.ndarray]:
    grid = np.linspace(-1.0, 1.0, points)
    return grid, np.array([g(F, float(q)) for q in grid])


def roots(F: HydrogenMap, grid: np.ndarray, values: np.ndarray) -> list[Root]:
    """A7's frozen procedure: bisect every sign change to 1e-10 and accept only
    |g| <= 1e-8 at the midpoint; golden-section every sub-1e-3 local minimum of
    |g| that has no sign change beside it, reporting whatever it reaches."""
    found: list[Root] = []
    for i in range(len(grid) - 1):
        a, b, ga, gb = float(grid[i]), float(grid[i + 1]), float(values[i]), float(values[i + 1])
        if ga == 0.0:
            found.append(Root(a, 0.0, "root"))
            continue
        if ga * gb < 0:
            while b - a > 1e-10:
                m = 0.5 * (a + b)
                gm = g(F, m)
                if gm == 0.0:
                    a = b = m
                    break
                if ga * gm < 0:
                    b, gb = m, gm
                else:
                    a, ga = m, gm
            mid = 0.5 * (a + b)
            residual = g(F, mid)
            if abs(residual) <= 1e-8:
                found.append(Root(mid, residual, "root"))
    magnitude = np.abs(values)
    for i in range(1, len(grid) - 1):
        if magnitude[i] < 1e-3 and magnitude[i] <= magnitude[i - 1] and magnitude[i] <= magnitude[i + 1]:
            if values[i - 1] * values[i] < 0 or values[i] * values[i + 1] < 0 or values[i] == 0:
                continue
            lo, hi = float(grid[i]) - 0.002, float(grid[i]) + 0.002
            ratio = (math.sqrt(5) - 1) / 2
            for _ in range(60):
                c, d = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
                if abs(g(F, c)) < abs(g(F, d)):
                    hi = d
                else:
                    lo = c
            q = 0.5 * (lo + hi)
            found.append(Root(q, g(F, q), "tangency"))
    return found


STEPS = (1e-3, 1e-4, 1e-5, 1e-6)


def slopes(F: HydrogenMap, q: float) -> dict[float, float]:
    """Centred differences of F at q, one per frozen step (A7)."""
    return {h: float((F(q + h)[0] - F(q - h)[0]) / (2 * h)) for h in STEPS}


def active_sets_near(F: HydrogenMap, q: float, half_width: float = 1e-3, points: int = 21) -> set:
    return {frozenset(F.solve(x).passes[-1].items()) for x in np.linspace(q - half_width, q + half_width, points)}


@dataclass
class Iteration:
    converged: bool
    iterations: int
    q: np.ndarray
    step: float
    residual: float
    history: list[np.ndarray]


def iterate(F: HydrogenMap, alpha: float, max_iterations: int = 500, tolerance: float = 1e-8) -> Iteration:
    """Q <- (1 - alpha) Q + alpha F(Q) from Q = 0. Converged needs BOTH the step
    and the fixed-point residual within tolerance (A7)."""
    q = np.zeros(len(F.hydrogens))
    history = [q.copy()]
    step = residual = math.inf
    for k in range(1, max_iterations + 1):
        image = F(q)
        new = (1.0 - alpha) * q + alpha * image
        step = float(np.max(np.abs(new - q))) if len(q) else 0.0
        q = new
        history.append(q.copy())
        residual = float(np.max(np.abs(F(q) - q))) if len(q) else 0.0
        if step <= tolerance and residual <= tolerance:
            return Iteration(True, k, q, step, residual, history)
    return Iteration(False, max_iterations, q, step, residual, history)


def iteration_bin(result: Iteration) -> str:
    if not result.converged:
        return "not converged"
    return next(label for limit, label in ((50, "<=50"), (100, "<=100"), (250, "<=250"), (500, "<=500")) if result.iterations <= limit)


def predicted_to_converge(alpha: float, slope: float) -> bool:
    return abs(1.0 - alpha * (1.0 - slope)) < 1.0
