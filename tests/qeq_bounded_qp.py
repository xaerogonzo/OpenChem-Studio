"""The constrained QEq minimum at fixed hydrogen parameters (amendment A9).

Not a test module: `tests/test_charge_equilibration.py` and
`benchmarks/charges/rappe_goddard/o9_study.py` both use it.

RESEARCH ONLY. The production solver keeps the paper's never-release fixing
(eq 13), and the shipped calculator refuses any solution with an active bound
(A8). This module answers how far that procedure is from the true minimum of

    E(q) = chi . q + 1/2 q^T C q   subject to  sum q = Q,  l <= q <= u,

the QEq energy whose stationarity is exactly the linear system `solve_bounded`
builds (C q - mu 1 = -chi, 1^T q = Q).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def energy(hardness: np.ndarray, chi: np.ndarray, q: np.ndarray) -> float:
    return float(chi @ q + 0.5 * q @ hardness @ q)


def tangent_min_eigenvalue(hardness: np.ndarray) -> float:
    """Smallest eigenvalue of C on {d : sum d = 0}: positive means the QP is
    strictly convex and its minimum unique."""
    n = len(hardness)
    if n < 2:
        return float("inf")
    basis = np.linalg.qr(np.vstack([np.ones(n), np.eye(n)[:-1]]).T)[0][:, 1:]
    return float(np.linalg.eigvalsh(basis.T @ hardness @ basis).min())


def _equality_solve(hardness, chi, net, fixed: dict[int, float], n: int) -> tuple[np.ndarray, float]:
    """Minimise E with the atoms in `fixed` held at their values and sum q = net."""
    q = np.zeros(n)
    for i, v in fixed.items():
        q[i] = v
    free = [i for i in range(n) if i not in fixed]
    idx = np.array(sorted(fixed), dtype=int)
    size = len(free)
    system = np.zeros((size + 1, size + 1))
    system[:size, :size] = hardness[np.ix_(free, free)]
    system[:size, size] = -1.0
    system[size, :size] = 1.0
    shifted = chi[free] + (hardness[np.ix_(free, idx)] @ q[idx] if len(idx) else 0.0)
    solution = np.linalg.solve(system, np.concatenate([-shifted, [net - q[idx].sum()]]))
    q[free] = solution[:size]
    return q, float(solution[size])


def kkt_violation(hardness, chi, net, lower, upper, q, tolerance: float = 1e-9) -> float:
    """The largest violation of the KKT conditions at q: bounds, the charge sum,
    stationarity of the free atoms, and the sign of every bound's multiplier."""
    gradient = chi + hardness @ q
    at_lower = q <= lower + tolerance
    at_upper = q >= upper - tolerance
    free = ~(at_lower | at_upper)
    violation = max(float(np.max(lower - q, initial=0.0)), float(np.max(q - upper, initial=0.0)), abs(float(q.sum()) - net))
    if np.any(free):
        mu = float(np.mean(gradient[free]))
        violation = max(violation, float(np.max(np.abs(gradient[free] - mu))))
    else:
        mu = float(np.median(gradient))
    # At a lower bound, raising q_i must not lower E: g_i - mu >= 0; at an upper bound, g_i - mu <= 0.
    if np.any(at_lower & ~at_upper):
        violation = max(violation, float(np.max(-(gradient[at_lower & ~at_upper] - mu), initial=0.0)))
    if np.any(at_upper & ~at_lower):
        violation = max(violation, float(np.max(gradient[at_upper & ~at_lower] - mu, initial=0.0)))
    return violation


@dataclass
class QPResult:
    charges: np.ndarray
    active: dict[int, float]
    iterations: int
    released: int


def constrained_minimum(hardness, chi, net, lower, upper, max_iterations: int = 500) -> QPResult:
    """Primal active-set method (Nocedal & Wright, algorithm 16.3) for the
    bounded QEq QP. Unlike eq 13 it RELEASES an atom whose bound multiplier
    has the wrong sign."""
    hardness = np.asarray(hardness, dtype=float)
    chi = np.asarray(chi, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    n = len(chi)
    # A feasible start: the net charge spread evenly, then pushed inside each box
    # while keeping the sum.
    q = np.clip(np.full(n, net / n), lower, upper)
    for _ in range(n):
        gap = net - q.sum()
        if abs(gap) < 1e-14:
            break
        room = (upper - q) if gap > 0 else (q - lower)
        movable = room > 1e-14
        if not np.any(movable):
            raise ValueError("no feasible charge set inside the bounds")
        share = gap / np.count_nonzero(movable)
        q[movable] = np.clip(q[movable] + share, lower[movable], upper[movable])
    # No working set at the start; a bound joins it only when a step hits it.
    active: dict[int, float] = {}
    released = 0
    for iteration in range(1, max_iterations + 1):
        if len(active) == n:
            active.pop(next(iter(active)))
        target, mu = _equality_solve(hardness, chi, net, active, n)
        step = target - q
        if np.max(np.abs(step)) <= 1e-13:
            gradient = chi + hardness @ q
            multipliers = {i: (gradient[i] - mu if v == lower[i] else mu - gradient[i]) for i, v in active.items()}
            if not multipliers or min(multipliers.values()) >= -1e-12:
                return QPResult(q, dict(active), iteration, released)
            worst = min(multipliers, key=multipliers.get)
            active.pop(worst)
            released += 1
            continue
        alpha, blocking = 1.0, None
        for i in range(n):
            if i in active or step[i] == 0:
                continue
            bound = upper[i] if step[i] > 0 else lower[i]
            ratio = (bound - q[i]) / step[i]
            if ratio < alpha:
                alpha, blocking = ratio, (i, bound)
        q = q + alpha * step
        if blocking is not None:
            i, bound = blocking
            q[i] = bound
            active[i] = float(bound)
    raise RuntimeError(f"active-set QP did not finish in {max_iterations} iterations")
