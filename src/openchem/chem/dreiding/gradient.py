"""Analytic first derivatives of the DREIDING energy.

Written because the alternative was not fast enough to be worth having.
Measured on this energy expression, a numerical gradient costs
2 x 3N evaluations -- **252 ms for neopentane** -- so a few hundred
optimisation steps is a minute per structure and the Table XI barriers
would take an hour. The analytic form is one evaluation's work.

**Every derivative here is checked against a central difference** in
`tests/test_dreiding_gradient.py`. That is not belt-and-braces: a sign
error in the torsion derivative produces an optimiser that converges
smoothly to the wrong geometry, which looks like a working program.

The inversion term is deliberately differentiated NUMERICALLY. It applies
only to three-coordinate sp2 and resonant centres, contributes nothing to
any alkane, and its analytic derivative is longer than the other four put
together -- so it is the one place where the trade goes the other way.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
from rdkit import Chem

from openchem.chem.dreiding.energy import (
    _angle_triples,
    _equilibrium_length,
    _excluded_pairs,
    inversion_energy,
    torsion_for,
)
from openchem.chem.dreiding.parameters import (
    ANGLE_FORCE_CONSTANT,
    SINGLE_BOND_FORCE_CONSTANT,
    VALENCE,
    VAN_DER_WAALS,
    element_of,
)


def _bond_gradient(positions, mol, types, gradient) -> float:
    """E = 1/2 k (r - r0)^2, so dE/dr_i = k (r - r0) * (r_i - r_j)/r."""
    total = 0.0
    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        force = SINGLE_BOND_FORCE_CONSTANT * bond.GetBondTypeAsDouble()
        rest = _equilibrium_length(types[i], types[j])
        delta = positions[i] - positions[j]
        length = float(np.linalg.norm(delta))
        if length == 0:
            continue
        total += 0.5 * force * (length - rest) ** 2
        pull = force * (length - rest) * delta / length
        gradient[i] += pull
        gradient[j] -= pull
    return total


def _cosine_derivatives(u: np.ndarray, v: np.ndarray):
    """d(cos theta)/du and d(cos theta)/dv for the angle between u and v."""
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 0.0, np.zeros(3), np.zeros(3)
    cosine = float(np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0))
    d_du = v / (nu * nv) - cosine * u / (nu * nu)
    d_dv = u / (nu * nv) - cosine * v / (nv * nv)
    return cosine, d_du, d_dv


def _angle_gradient(positions, mol, types, gradient) -> float:
    """Equation 10a in cos(theta), so the chain rule stops at the cosine.

    That is the practical advantage of DREIDING's harmonic-cosine form
    over a harmonic-theta one: no `arccos`, and therefore no derivative
    blowing up as the angle approaches 0 or 180.
    """
    total = 0.0
    for i, j, k in _angle_triples(mol):
        rest = VALENCE[types[j]].bond_angle
        u, v = positions[i] - positions[j], positions[k] - positions[j]
        cosine, d_du, d_dv = _cosine_derivatives(u, v)
        if isinstance(cosine, float) and np.all(d_du == 0) and np.all(d_dv == 0):
            continue

        if abs(rest - 180.0) < 1e-9:
            total += ANGLE_FORCE_CONSTANT * (1.0 + cosine)
            scale = ANGLE_FORCE_CONSTANT
        else:
            rest_cosine = math.cos(math.radians(rest))
            constant = ANGLE_FORCE_CONSTANT / math.sin(math.radians(rest)) ** 2
            total += 0.5 * constant * (cosine - rest_cosine) ** 2
            scale = constant * (cosine - rest_cosine)

        gradient[i] += scale * d_du
        gradient[k] += scale * d_dv
        gradient[j] -= scale * (d_du + d_dv)
    return total


def dihedral_and_derivatives(positions: np.ndarray, i: int, j: int, k: int, l: int):
    """The IJKL dihedral in radians, with d(phi)/dr for all four atoms.

    **The coefficients below were SOLVED FOR against a central difference,
    not recalled.** Textbook statements of this derivative differ by the
    direction convention of b1 and by which `atan2` argument order defines
    phi, so a formula copied from one source into another's convention is
    self-consistent, translation-invariant, and wrong -- which is what
    happened here first, and what an optimiser would have hidden by
    converging smoothly to a slightly wrong geometry.

    In THESE conventions -- b1 = r_j - r_i, and phi from
    `atan2(m . n2, n1 . n2)` -- with

        A = |b2| n1 / |n1|^2      p = (b1 . b2) / |b2|^2
        B = |b2| n2 / |n2|^2      q = (b3 . b2) / |b2|^2

    the answer is

        dphi/dr_i =  A
        dphi/dr_j = -(1 + p) A - q B
        dphi/dr_k =  p A + (1 + q) B
        dphi/dr_l = -B

    which sums to zero identically, as translation invariance requires.
    """
    b1 = positions[j] - positions[i]
    b2 = positions[k] - positions[j]
    b3 = positions[l] - positions[k]
    n1, n2 = np.cross(b1, b2), np.cross(b2, b3)
    n1_sq, n2_sq = float(np.dot(n1, n1)), float(np.dot(n2, n2))
    b2_len = float(np.linalg.norm(b2))
    if n1_sq == 0 or n2_sq == 0 or b2_len == 0:
        return 0.0, np.zeros((4, 3))

    m = np.cross(n1, b2 / b2_len)
    phi = math.atan2(float(np.dot(m, n2)), float(np.dot(n1, n2)))

    a = b2_len / n1_sq * n1
    b = b2_len / n2_sq * n2
    p = float(np.dot(b1, b2)) / (b2_len * b2_len)
    q = float(np.dot(b3, b2)) / (b2_len * b2_len)
    return phi, np.array([a, -(1.0 + p) * a - q * b, p * a + (1.0 + q) * b, -b])


def _torsion_gradient(positions, mol, types, gradient) -> float:
    """Equation 13, differentiated through the dihedral.

        E  = 1/2 V {1 - cos[n (phi - phi0)]}
        dE = 1/2 V n sin[n (phi - phi0)] dphi

    `V` is still the per-dihedral SHARE, not the bond total -- the same
    renormalisation the energy applies, and forgetting it here while
    keeping it there would give an optimiser that fights its own energy.
    """
    total = 0.0
    for bond in mol.GetBonds():
        j, k = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        left = [n.GetIdx() for n in mol.GetAtomWithIdx(j).GetNeighbors() if n.GetIdx() != k]
        right = [n.GetIdx() for n in mol.GetAtomWithIdx(k).GetNeighbors() if n.GetIdx() != j]
        if not left or not right:
            continue
        parameters = torsion_for(types[j], types[k], bond, mol)
        if parameters.periodicity == 0 or parameters.barrier == 0.0:
            continue

        share = parameters.barrier / (len(left) * len(right))
        phase = math.radians(parameters.phase)
        n = parameters.periodicity
        for i in left:
            for l in right:
                phi, derivatives = dihedral_and_derivatives(positions, i, j, k, l)
                total += 0.5 * share * (1.0 - math.cos(n * (phi - phase)))
                scale = 0.5 * share * n * math.sin(n * (phi - phase))
                for atom, derivative in zip((i, j, k, l), derivatives):
                    gradient[atom] += scale * derivative
    return total


def _van_der_waals_gradient(positions, mol, types, gradient) -> float:
    """E = D0 (rho^12 - 2 rho^6) with rho = R0/r, so

        dE/dr = 12 D0 (rho^6 - rho^12) / r
    """
    excluded = _excluded_pairs(mol)
    wells = [VAN_DER_WAALS[element_of(t)] for t in types]
    total = 0.0
    for i, j in itertools.combinations(range(mol.GetNumAtoms()), 2):
        if (i, j) in excluded:
            continue
        radius = 0.5 * (wells[i].radius + wells[j].radius)
        depth = math.sqrt(wells[i].well_depth * wells[j].well_depth)
        delta = positions[i] - positions[j]
        distance = float(np.linalg.norm(delta))
        if distance == 0:
            continue
        rho6 = (radius / distance) ** 6
        rho12 = rho6 * rho6
        total += depth * (rho12 - 2.0 * rho6)
        pull = 12.0 * depth * (rho6 - rho12) / distance * (delta / distance)
        gradient[i] += pull
        gradient[j] -= pull
    return total


def _inversion_gradient(positions, mol, types, gradient) -> float:
    """Differentiated numerically, and only when it applies at all.

    Zero for every alkane, so the Table XI barriers never pay for it. See
    the module docstring for why this one term goes the other way.
    """
    base = inversion_energy(positions, mol, types)
    if base == 0.0:
        return 0.0
    step = 1e-6
    for atom in range(mol.GetNumAtoms()):
        for axis in range(3):
            shifted = positions.copy()
            shifted[atom, axis] += step
            forward = inversion_energy(shifted, mol, types)
            shifted[atom, axis] -= 2 * step
            backward = inversion_energy(shifted, mol, types)
            gradient[atom, axis] += (forward - backward) / (2 * step)
    return base


def energy_and_gradient(
    positions: np.ndarray, mol: Chem.Mol, types: list[str]
) -> tuple[float, np.ndarray]:
    """The DREIDING energy and its Cartesian gradient, in kcal/mol and /A."""
    gradient = np.zeros_like(positions)
    total = (
        _bond_gradient(positions, mol, types, gradient)
        + _angle_gradient(positions, mol, types, gradient)
        + _torsion_gradient(positions, mol, types, gradient)
        + _van_der_waals_gradient(positions, mol, types, gradient)
        + _inversion_gradient(positions, mol, types, gradient)
    )
    return total, gradient
