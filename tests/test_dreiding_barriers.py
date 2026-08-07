"""Table XI in full: every rotational barrier the paper computed.

Eight molecules, and the numbers asserted are **DREIDING's own** rather
than experiment. That is what makes this a test of the implementation:
against experiment a disagreement is ambiguous between a bad
implementation and a bad force field, and there is nothing to do about
the second.

A barrier is a far stronger test than a single-point energy. It is a
difference between two OPTIMISED structures, so it exercises the bond
radii, the angle term, the torsion barrier with its renormalisation, the
van der Waals term with its combination rules, AND the gradient of every
one of them -- a sign error anywhere shows up as a converged geometry
that is quietly wrong.

Mayo, Olafson & Goddard, J. Phys. Chem. 1990, 94, 8897-8909, Table XI.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import rdMolTransforms as transforms

from openchem.chem.dreiding.optimise import minimise
from openchem.chem.dreiding.typer import assign_types

#: How far a computed barrier may sit from the paper's. 0.02 kcal/mol is
#: about six times the worst deviation measured (0.008, propane) and far
#: below the 0.1 the paper itself prints to.
TOLERANCE = 0.02


def _prepared(smiles: str, anti_backbone: tuple[int, int, int, int] | None = None):
    """An embedded, MMFF-relaxed starting structure.

    `anti_backbone` forces a backbone dihedral to 180 first. **Butane
    needs it and that is not a detail**: from this seed the embedder lands
    in the GAUCHE well at -65 degrees, and the terminal-methyl barrier
    measured there is 3.171 against the paper's 3.410. The barrier is a
    property of the global minimum conformer, so starting anywhere else
    answers a different question -- and answers it plausibly, which is
    why it was worth chasing rather than widening the tolerance.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(mol)
    if anti_backbone is not None:
        transforms.SetDihedralDeg(mol.GetConformer(), *anti_backbone, 180.0)
        AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _first_hydrogen(mol: Chem.Mol, carbon: int) -> int:
    return next(n.GetIdx() for n in mol.GetAtomWithIdx(carbon).GetNeighbors() if n.GetSymbol() == "H")


def _barrier(mol: Chem.Mol, dihedral, top: float, bottom: float) -> float:
    """Optimise at the maximum and the minimum, and subtract.

    The extrema of these rotations sit at symmetry positions -- eclipsed
    at 0, staggered at 60 or 180 -- so both are optimised directly rather
    than located on a scan grid, which would carry the grid's own error
    into the answer.
    """
    types = assign_types(mol)
    high = minimise(mol, types=types, dihedral=dihedral, dihedral_target=top)
    low = minimise(mol, types=types, dihedral=dihedral, dihedral_target=bottom)

    assert high.converged and low.converged, (high.converged, low.converged)
    assert max(high.dihedral_error, low.dihedral_error) < 0.05
    return high.energy - low.energy


def _methyl_barrier(smiles: str, far: int, anti_backbone=None) -> float:
    """Rotate the methyl on atom 0 about the 0-1 bond."""
    mol = _prepared(smiles, anti_backbone)
    dihedral = (_first_hydrogen(mol, 0), 0, 1, far)
    return _barrier(mol, dihedral, 0.0, 180.0)


# --- Table XI, row by row ----------------------------------------------------


def test_ethane():
    """The gate, reached here through the GENERAL optimiser rather than
    through ethane's three symmetry parameters. The two agree to five
    decimals (3.84155 and 0.94569 for the two stationary points), which
    is an independent check of the optimiser itself."""
    mol = _prepared("CC")
    dihedral = (_first_hydrogen(mol, 0), 0, 1, _first_hydrogen(mol, 1))

    assert _barrier(mol, dihedral, 0.0, 60.0) == pytest.approx(2.896, abs=TOLERANCE)


def test_propane():
    assert _methyl_barrier("CCC", far=2) == pytest.approx(3.376, abs=TOLERANCE)


def test_butane_terminal_methyl():
    """Measured on the ANTI conformer. See `_prepared` -- the gauche well
    gives 3.171, which is both wrong and believable."""
    barrier = _methyl_barrier("CCCC", far=2, anti_backbone=(0, 1, 2, 3))

    assert barrier == pytest.approx(3.410, abs=TOLERANCE)


def test_butane_central_bond():
    """The one row that is not a methyl rotation: anti to the eclipsed
    maximum at 120 degrees. The syn maximum at 0 is a different and much
    higher barrier (5.81 here), so which extremum is meant matters."""
    mol = _prepared("CCCC", anti_backbone=(0, 1, 2, 3))

    assert _barrier(mol, (0, 1, 2, 3), 120.0, 180.0) == pytest.approx(3.822, abs=TOLERANCE)


def test_isobutane():
    assert _methyl_barrier("CC(C)C", far=2) == pytest.approx(3.995, abs=TOLERANCE)


def test_neopentane():
    """The largest barrier in the table, and the one where DREIDING
    departs furthest from experiment (5.071 against 4.7) -- which is the
    force field's business, not this implementation's."""
    assert _methyl_barrier("CC(C)(C)C", far=2) == pytest.approx(5.071, abs=TOLERANCE)


def test_fluoroethane():
    assert _methyl_barrier("CCF", far=2) == pytest.approx(3.172, abs=TOLERANCE)


def test_chloroethane():
    assert _methyl_barrier("CCCl", far=2) == pytest.approx(3.487, abs=TOLERANCE)


# --- what the set says as a whole --------------------------------------------


def test_the_barrier_ordering_matches_the_paper():
    """Not just the values but their ORDER, which is what a chemist reads
    off the table: more substitution at the far carbon raises the methyl's
    barrier, ethane < propane < isobutane < neopentane."""
    ethane_mol = _prepared("CC")
    ethane = _barrier(
        ethane_mol,
        (_first_hydrogen(ethane_mol, 0), 0, 1, _first_hydrogen(ethane_mol, 1)),
        0.0,
        60.0,
    )
    propane = _methyl_barrier("CCC", far=2)
    isobutane = _methyl_barrier("CC(C)C", far=2)
    neopentane = _methyl_barrier("CC(C)(C)C", far=2)

    assert ethane < propane < isobutane < neopentane
