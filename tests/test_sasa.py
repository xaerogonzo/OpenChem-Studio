"""The point-sampled accessible surface itself: its points, its closed forms and its convergence."""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.sasa import DEFAULT_POINTS, accessible_areas, sphere_points


def test_the_points_lie_on_the_unit_sphere_and_are_the_same_every_time():
    points = sphere_points(500)

    assert np.allclose(np.linalg.norm(points, axis=1), 1.0)
    assert np.array_equal(points, sphere_points(500))


def test_the_points_are_spread_evenly_not_bunched():
    points = sphere_points(2000)

    assert np.abs(points.mean(axis=0)).max() < 1e-3, "an even spread has its centre of mass at the origin"
    assert np.abs(points[:, 2].mean()) < 1e-9


def test_no_atoms_have_no_area():
    assert accessible_areas(np.zeros((0, 3)), np.zeros(0), 1.4).size == 0


@pytest.mark.parametrize("probe", [0.0, 1.4, 3.0])
def test_a_lone_atom_is_its_sphere_exactly(probe):
    area = accessible_areas(np.zeros((1, 3)), np.array([1.7]), probe)

    assert area[0] == pytest.approx(4 * math.pi * (1.7 + probe) ** 2, rel=1e-12)


def test_an_atom_buried_inside_another_has_no_surface_and_does_not_hurt_the_other():
    positions = np.array([[0.0, 0.0, 0.0], [0.1, 0.0, 0.0]])
    areas = accessible_areas(positions, np.array([3.0, 0.5]), 0.0)

    assert areas[1] == 0.0
    assert areas[0] == pytest.approx(4 * math.pi * 9, rel=0.02)


def test_two_atoms_far_apart_do_not_interact():
    areas = accessible_areas(np.array([[0.0, 0.0, 0.0], [50.0, 0.0, 0.0]]), np.array([1.7, 1.2]), 1.4)

    assert areas[0] == pytest.approx(4 * math.pi * 3.1**2, rel=1e-12)
    assert areas[1] == pytest.approx(4 * math.pi * 2.6**2, rel=1e-12)


def test_two_equal_atoms_match_the_closed_form():
    radius, distance = 1.8 + 1.4, 2.0
    areas = accessible_areas(np.array([[0.0, 0.0, 0.0], [distance, 0.0, 0.0]]), np.array([1.8, 1.8]), 1.4)

    assert areas.sum() == pytest.approx(4 * math.pi * radius**2 + 2 * math.pi * radius * distance, rel=0.01)


def test_the_default_point_count_is_within_half_a_percent_of_a_far_denser_sweep():
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    AllChem.MMFFOptimizeMolecule(mol)
    table = Chem.GetPeriodicTable()
    positions = np.array(mol.GetConformer().GetPositions())
    radii = np.array([table.GetRvdw(atom.GetAtomicNum()) for atom in mol.GetAtoms()])

    coarse = accessible_areas(positions, radii, 1.4, DEFAULT_POINTS).sum()
    dense = accessible_areas(positions, radii, 1.4, 40_000).sum()

    assert coarse == pytest.approx(dense, rel=0.005)


def test_the_areas_of_the_atoms_are_never_negative_nor_more_than_their_sphere():
    rng = np.random.default_rng(2)
    positions = rng.normal(scale=2.0, size=(30, 3))
    radii = rng.uniform(1.0, 2.0, 30)
    areas = accessible_areas(positions, radii, 1.4)

    assert (areas >= 0).all() and (areas <= 4 * math.pi * (radii + 1.4) ** 2 + 1e-9).all()
