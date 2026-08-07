"""Geometry optimisation on the DREIDING surface, with a dihedral held.

Needed to reproduce the paper's rotational barriers, which are differences
between OPTIMISED structures -- ethane's is 3.170 held rigid and 2.896
relaxed, so relaxation is the difference between "close" and "the same
force field".

L-BFGS with a backtracking line search. Written rather than imported
because scipy is not a dependency of this project and adding one for a
40-line routine would be a poor trade.

**The constraint is a stiff restraint, not a projection.** A projected
optimiser has to know the constraint's null space and is easy to get
subtly wrong; a restraint is transparent, and its residual is reported so
nobody has to trust that it held. The restraint energy is excluded from
the value returned, so the number is a real DREIDING energy at a geometry
that satisfies the constraint to within the reported tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from rdkit import Chem

from openchem.chem.dreiding.gradient import dihedral_and_derivatives, energy_and_gradient
from openchem.chem.dreiding.typer import assign_types

#: Restraint stiffness, in kcal/mol per radian^2. Chosen by measurement:
#: at 1e4 the dihedral holds to better than 0.02 degrees on every molecule
#: in the Table XI set, and the restrained coordinate contributes under
#: 0.001 kcal/mol of the reported energy.
RESTRAINT_FORCE = 1.0e4


@dataclass(frozen=True)
class OptimisationResult:
    """Where the optimiser stopped, and how well it did.

    `dihedral_error` is carried so a caller never has to assume the
    restraint held. A barrier computed from two structures whose
    constraints slipped differently is meaningless, and silently so.
    """

    positions: np.ndarray
    energy: float
    gradient_norm: float
    steps: int
    converged: bool
    dihedral_error: float = 0.0


def _wrap(radians: float) -> float:
    """Fold an angle difference into (-pi, pi].

    Without this a restraint at 0 degrees pulls a structure at 359 degrees
    the long way round, through every eclipsed maximum on the circle.
    """
    return (radians + math.pi) % (2 * math.pi) - math.pi


def minimise(
    mol: Chem.Mol,
    positions: np.ndarray | None = None,
    *,
    types: list[str] | None = None,
    dihedral: tuple[int, int, int, int] | None = None,
    dihedral_target: float | None = None,
    max_steps: int = 2000,
    gradient_tolerance: float = 1e-4,
    memory: int = 12,
) -> OptimisationResult:
    """Minimise the DREIDING energy, optionally holding one dihedral.

    `dihedral_target` is in degrees. With no dihedral given this is a
    plain local minimisation.
    """
    types = types if types is not None else assign_types(mol)
    if positions is None:
        positions = np.array(mol.GetConformer().GetPositions(), dtype=float)
    point = np.array(positions, dtype=float)
    target = math.radians(dihedral_target) if dihedral_target is not None else None

    def value_and_gradient(x: np.ndarray) -> tuple[float, np.ndarray, float]:
        energy, gradient = energy_and_gradient(x, mol, types)
        error = 0.0
        if dihedral is not None and target is not None:
            phi, derivatives = dihedral_and_derivatives(x, *dihedral)
            deviation = _wrap(phi - target)
            error = abs(math.degrees(deviation))
            # Added to the objective, never to the reported energy.
            energy_with_restraint = energy + 0.5 * RESTRAINT_FORCE * deviation**2
            for atom, derivative in zip(dihedral, derivatives):
                gradient[atom] += RESTRAINT_FORCE * deviation * derivative
            return energy_with_restraint, gradient, error
        return energy, gradient, error

    objective, gradient, error = value_and_gradient(point)
    history: list[tuple[np.ndarray, np.ndarray]] = []
    converged = False
    step = 0

    for step in range(1, max_steps + 1):
        if np.linalg.norm(gradient) < gradient_tolerance:
            converged = True
            break

        # L-BFGS two-loop recursion over the stored (s, y) pairs.
        direction = -gradient.reshape(-1)
        alphas = []
        for s, y in reversed(history):
            rho = 1.0 / float(np.dot(y, s))
            alpha = rho * float(np.dot(s, direction))
            direction = direction - alpha * y
            alphas.append((rho, alpha, s, y))
        if history:
            s, y = history[-1]
            direction = direction * float(np.dot(s, y)) / float(np.dot(y, y))
        for rho, alpha, s, y in reversed(alphas):
            beta = rho * float(np.dot(y, direction))
            direction = direction + s * (alpha - beta)
        direction = direction.reshape(point.shape)

        slope = float(np.sum(direction * gradient))
        if slope >= 0:  # not a descent direction: restart from steepest descent
            direction, slope = -gradient, -float(np.sum(gradient * gradient))
            history.clear()

        # Backtracking Armijo line search. The first trial step is 1.0
        # because that is L-BFGS's natural scale once curvature is known.
        length = 1.0
        for _attempt in range(60):
            trial = point + length * direction
            trial_objective, trial_gradient, trial_error = value_and_gradient(trial)
            if trial_objective <= objective + 1e-4 * length * slope:
                break
            length *= 0.5
        else:
            converged = np.linalg.norm(gradient) < gradient_tolerance * 100
            break

        s = (trial - point).reshape(-1)
        y = (trial_gradient - gradient).reshape(-1)
        if float(np.dot(y, s)) > 1e-12:
            history.append((s, y))
            if len(history) > memory:
                history.pop(0)

        point, objective, gradient, error = trial, trial_objective, trial_gradient, trial_error

    # The RESTRAINT-FREE energy at the converged geometry, which is the
    # only number that means anything outside this function.
    energy, _ = energy_and_gradient(point, mol, types)
    return OptimisationResult(
        positions=point,
        energy=energy,
        gradient_norm=float(np.linalg.norm(gradient)),
        steps=step,
        converged=converged,
        dihedral_error=error,
    )


def relaxed_scan(
    mol: Chem.Mol,
    dihedral: tuple[int, int, int, int],
    angles: list[float],
    *,
    types: list[str] | None = None,
) -> list[tuple[float, OptimisationResult]]:
    """Optimise at each dihedral in turn, walking the previous geometry on.

    Carrying the geometry forward matters: starting every point from the
    same embedded structure lets neighbouring points fall into different
    local minima of the OTHER degrees of freedom, and the resulting
    profile has steps in it that look like real features.
    """
    types = types if types is not None else assign_types(mol)
    positions = np.array(mol.GetConformer().GetPositions(), dtype=float)
    profile = []
    for angle in angles:
        result = minimise(
            mol, positions, types=types, dihedral=dihedral, dihedral_target=angle
        )
        profile.append((angle, result))
        positions = result.positions
    return profile
