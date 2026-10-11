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


# --- the volume of the same surface (divergence theorem), and its independent grid check ---------------------------------


def test_a_lone_sphere_has_exactly_the_volume_of_its_sphere_wherever_it_is():
    from openchem.chem.sasa import enclosed_volume

    for centre in ([0.0, 0.0, 0.0], [3.0, -2.0, 1.0]):
        assert enclosed_volume(np.array([centre]), np.array([1.7])) == pytest.approx(4 / 3 * math.pi * 1.7**3, rel=1e-9)
    assert enclosed_volume(np.array([[0.0, 0.0, 0.0]]), np.array([1.4]), probe=1.4) == pytest.approx(
        4 / 3 * math.pi * 2.8**3, rel=1e-9
    )


@pytest.mark.parametrize("distance", [1.0, 2.0, 2.9])
def test_two_spheres_match_their_closed_form_lens_formula(distance):
    from openchem.chem.sasa import enclosed_volume, grid_volume

    r1, r2 = 1.7, 1.2
    lens = math.pi * (r1 + r2 - distance) ** 2 * (distance**2 + 2 * distance * (r1 + r2) - 3 * (r1 - r2) ** 2) / (12 * distance)
    closed = 4 / 3 * math.pi * (r1**3 + r2**3) - lens
    positions = np.array([[0.0, 0.0, 0.0], [distance, 0.0, 0.0]])
    radii = np.array([r1, r2])

    assert enclosed_volume(positions, radii) == pytest.approx(closed, rel=0.005)
    # the grid is the CHECK, at 0.1 angstrom: about 1% off for a small body (a lone helium is 0.7% low)
    assert grid_volume(positions, radii) == pytest.approx(closed, rel=0.015)


def test_the_two_volume_methods_agree_on_a_molecule():
    from rdkit.Chem import AllChem

    from openchem.chem.sasa import enclosed_volume, grid_volume
    from openchem.chem.vdw_radii import bondi_radius

    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    AllChem.MMFFOptimizeMolecule(mol)
    positions = mol.GetConformer().GetPositions()
    radii = np.array([bondi_radius(a.GetAtomicNum()) for a in mol.GetAtoms()])

    assert enclosed_volume(positions, radii) == pytest.approx(grid_volume(positions, radii, 0.05), rel=0.005)
