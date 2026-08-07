"""The analytic gradient, against a central difference.

**This file exists because the first version of the torsion derivative
was wrong and nothing else would have caught it.** It was
self-consistent, summed to zero as translation invariance requires, and
produced an optimiser that converged smoothly -- to a geometry that was
quietly not a stationary point of the energy. The barrier it gave was
plausible.

So the derivative is checked term by term as well as in total: a total
that matches can still hide two terms wrong in opposite directions.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dreiding import energy as terms
from openchem.chem.dreiding import gradient as derivatives
from openchem.chem.dreiding.typer import assign_types

#: Molecules chosen to reach every term: an sp3 chain, a conjugated
#: system, an aromatic ring, a heteroatom, a halogen, the oxygen column,
#: and a three-coordinate centre that switches the inversion term on.
MOLECULES = ["CC", "CCC", "CCO", "C=CC=C", "c1ccccc1", "CC(=O)N", "CCF", "OO", "CC(C)(C)C"]


def _prepared(smiles: str):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    positions = np.array(mol.GetConformer().GetPositions(), dtype=float)
    return mol, assign_types(mol), positions


def _central_difference(function, positions, mol, types, step=1e-5):
    numeric = np.zeros_like(positions)
    for atom in range(mol.GetNumAtoms()):
        for axis in range(3):
            shifted = positions.copy()
            shifted[atom, axis] += step
            forward = function(shifted, mol, types)
            shifted[atom, axis] -= 2 * step
            backward = function(shifted, mol, types)
            numeric[atom, axis] = (forward - backward) / (2 * step)
    return numeric


@pytest.mark.parametrize("smiles", MOLECULES)
def test_the_total_gradient_matches_a_central_difference(smiles):
    mol, types, positions = _prepared(smiles)

    def total(p, m, t):
        return (
            terms.bond_energy(p, m, t)
            + terms.angle_energy(p, m, t)
            + terms.torsion_energy(p, m, t)
            + terms.van_der_waals_energy(p, m, t)
            + terms.inversion_energy(p, m, t)
        )

    _energy, analytic = derivatives.energy_and_gradient(positions, mol, types)
    numeric = _central_difference(total, positions, mol, types)

    scale = max(1.0, float(np.abs(numeric).max()))
    assert float(np.abs(analytic - numeric).max()) / scale < 1e-5


@pytest.mark.parametrize(
    ("name", "energy_term", "gradient_term"),
    [
        ("bond", terms.bond_energy, derivatives._bond_gradient),
        ("angle", terms.angle_energy, derivatives._angle_gradient),
        ("torsion", terms.torsion_energy, derivatives._torsion_gradient),
        ("van der Waals", terms.van_der_waals_energy, derivatives._van_der_waals_gradient),
    ],
)
def test_each_term_separately(name, energy_term, gradient_term):
    """Term by term, because a total that matches can hide two errors
    cancelling. When the torsion derivative was wrong, bond, angle and
    van der Waals were all exact to 1e-8 and only this split said so."""
    mol, types, positions = _prepared("CCC")

    analytic = np.zeros_like(positions)
    gradient_term(positions, mol, types, analytic)
    numeric = _central_difference(energy_term, positions, mol, types)

    assert float(np.abs(analytic - numeric).max()) < 1e-3, name


def test_the_dihedral_derivative_itself():
    """Checked directly, since it is where the error was.

    Textbook statements of this derivative differ by the direction
    convention of b1 and by the argument order of `atan2`, so a formula
    taken from one source into another's convention is self-consistent
    and wrong. These coefficients were solved for against this very
    difference rather than recalled.
    """
    rng = np.random.default_rng(11)
    positions = rng.normal(size=(4, 3)) * 1.5

    _phi, analytic = derivatives.dihedral_and_derivatives(positions, 0, 1, 2, 3)

    step = 1e-6
    numeric = np.zeros((4, 3))
    for atom in range(4):
        for axis in range(3):
            shifted = positions.copy()
            shifted[atom, axis] += step
            forward, _ = derivatives.dihedral_and_derivatives(shifted, 0, 1, 2, 3)
            shifted[atom, axis] -= 2 * step
            backward, _ = derivatives.dihedral_and_derivatives(shifted, 0, 1, 2, 3)
            difference = (forward - backward + math.pi) % (2 * math.pi) - math.pi
            numeric[atom, axis] = difference / (2 * step)

    assert float(np.abs(analytic - numeric).max()) < 1e-4


def test_the_dihedral_derivative_sums_to_zero():
    """Translation invariance. **Necessary and NOT sufficient** -- the
    wrong version satisfied this too, which is exactly why it survived
    inspection and needed a numerical check."""
    rng = np.random.default_rng(5)
    positions = rng.normal(size=(4, 3)) * 1.5

    _phi, analytic = derivatives.dihedral_and_derivatives(positions, 0, 1, 2, 3)

    assert float(np.abs(analytic.sum(axis=0)).max()) < 1e-12


def test_the_dihedral_matches_the_energy_modules_own():
    """Two implementations of the same angle, in two modules. If they
    ever disagreed, the gradient would be the derivative of a different
    function from the one being minimised."""
    rng = np.random.default_rng(3)
    positions = rng.normal(size=(4, 3)) * 1.5

    from_gradient, _ = derivatives.dihedral_and_derivatives(positions, 0, 1, 2, 3)
    from_energy = math.radians(terms._dihedral(positions, 0, 1, 2, 3))

    assert from_gradient == pytest.approx(from_energy, abs=1e-12)


def test_a_minimisation_reaches_a_real_stationary_point():
    """The end-to-end statement: the optimiser stops where the gradient
    is genuinely small, measured independently of the optimiser's own
    convergence flag."""
    from openchem.chem.dreiding.optimise import minimise

    mol, types, _positions = _prepared("CCO")
    result = minimise(mol, types=types)

    _energy, gradient = derivatives.energy_and_gradient(result.positions, mol, types)

    assert result.converged
    assert float(np.linalg.norm(gradient)) < 1e-3
