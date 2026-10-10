"""The minimum and maximum shadow over every orientation.

The references are shapes with a CLOSED FORM, which is the only kind of anchor available:
ChemAxon documents no formula and no radii table for its own projection figures, so nothing it
prints could be asserted against. A sphere casts pi r^2 from anywhere; two spheres side by
side are seen end-on as one circle and side-on as a lens-shaped union; a rod of spheres is
the same, repeated. A real molecule is held to a much denser sweep of orientations than the
search itself uses.
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.projection_search import (
    _area,
    _hemisphere,
    enclosing_radius,
    projection_at,
    projection_extremes,
)
from tests.test_disc_union import _lens

R = 1.7


def _dumbbell(separation: float = 2.0, radius: float = R):
    positions = np.array([[0.0, 0.0, -separation / 2], [0.0, 0.0, separation / 2]])
    return positions, np.full(2, radius)


def _rotated(positions: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return positions @ q.T + rng.normal(size=3)


# --- a sphere, from anywhere ----------------------------------------------------------------


def test_one_sphere_casts_the_same_circle_whichever_way_it_is_viewed():
    extremes = projection_extremes(np.zeros((1, 3)), np.array([R]))

    for projection in (extremes.minimum, extremes.maximum):
        assert projection.area == pytest.approx(math.pi * R * R, rel=1e-12)
        assert projection.radius == pytest.approx(R, rel=1e-9)
        assert projection.size == pytest.approx(2 * R, rel=1e-12)


def test_no_atoms_is_refused_rather_than_answered():
    with pytest.raises(ValueError):
        projection_extremes(np.zeros((0, 3)), np.zeros(0))


# --- two spheres: end-on is one circle, side-on is the lens-shaped union --------------------------


@pytest.mark.parametrize("separation", [1.0, 2.0, 3.0])
def test_a_dumbbell_is_smallest_end_on_and_largest_side_on(separation):
    positions, radii = _dumbbell(separation)
    extremes = projection_extremes(positions, radii)
    side_on = 2 * math.pi * R * R - _lens(separation, R, R)

    # The end-on minimum is a CUSP (see `_REFINE_TOLERANCE`), so it is found to about 1e-4 of the area,
    # not to rounding; the maximum is smooth and is.
    assert extremes.minimum.area == pytest.approx(math.pi * R * R, rel=1e-4)
    assert extremes.minimum.radius == pytest.approx(R, rel=1e-3)
    assert extremes.minimum.size == pytest.approx(separation + 2 * R, rel=1e-6)
    assert extremes.maximum.area == pytest.approx(side_on, rel=1e-6)
    assert extremes.maximum.radius == pytest.approx(separation / 2 + R, rel=1e-6)
    assert extremes.maximum.size == pytest.approx(2 * R, rel=1e-6)


def test_the_dumbbells_directions_are_along_and_across_its_axis():
    positions, radii = _dumbbell(2.0)
    extremes = projection_extremes(positions, radii)

    assert abs(extremes.minimum.direction[2]) == pytest.approx(1.0, abs=1e-3)
    assert abs(extremes.maximum.direction[2]) == pytest.approx(0.0, abs=2e-3)


def test_a_dumbbell_is_found_however_it_is_turned():
    positions, radii = _dumbbell(2.0)
    want = projection_extremes(positions, radii)

    for seed in range(4):
        got = projection_extremes(_rotated(positions, seed), radii)

        assert got.minimum.area == pytest.approx(want.minimum.area, rel=2e-4)
        assert got.maximum.area == pytest.approx(want.maximum.area, rel=1e-6)


# --- a rod -----------------------------------------------------------------------------------------


def test_a_rod_of_spheres_seen_side_on_is_the_sum_less_each_neighbouring_lens():
    n, d, r = 6, 2.0, 1.2
    positions = np.array([[0.0, 0.0, i * d] for i in range(n)])
    extremes = projection_extremes(positions, np.full(n, r))
    want = n * math.pi * r * r - (n - 1) * _lens(d, r, r)

    assert extremes.maximum.area == pytest.approx(want, rel=1e-6)
    assert extremes.minimum.area == pytest.approx(math.pi * r * r, rel=2e-4)
    assert extremes.minimum.size == pytest.approx((n - 1) * d + 2 * r, rel=1e-6)


# --- the enclosing circle -----------------------------------------------------------------------------


def test_the_circle_round_two_equal_discs_is_half_their_separation_plus_a_radius():
    got = enclosing_radius(np.array([[0.0, 0.0], [3.0, 0.0]]), np.array([1.2, 1.2]))

    assert got == pytest.approx(1.5 + 1.2, rel=1e-9)


def test_the_circle_round_an_equilateral_triangle_of_discs_is_the_circumradius_plus_a_radius():
    side = 3.0
    centres = np.array([[0.0, 0.0], [side, 0.0], [side / 2, side * math.sqrt(3) / 2]])

    assert enclosing_radius(centres, np.full(3, 1.0)) == pytest.approx(side / math.sqrt(3) + 1.0, rel=1e-9)


def test_a_small_disc_inside_a_big_one_does_not_change_the_circle():
    got = enclosing_radius(np.array([[0.0, 0.0], [0.5, 0.0]]), np.array([3.0, 0.5]))

    assert got == pytest.approx(3.0, rel=1e-9)


def test_the_circle_contains_every_disc_and_no_smaller_one_does():
    rng = np.random.default_rng(5)
    centres = rng.normal(scale=2.0, size=(15, 2))
    radii = rng.uniform(0.8, 1.8, 15)
    got = enclosing_radius(centres, radii)
    # Brute force over a fine grid of centres: nothing beats it, and the best of them reaches it.
    xs = np.linspace(centres[:, 0].min(), centres[:, 0].max(), 241)
    ys = np.linspace(centres[:, 1].min(), centres[:, 1].max(), 241)
    needed = min(
        float((np.hypot(centres[:, 0] - x, centres[:, 1] - y) + radii).max()) for x in xs for y in ys
    )

    assert got <= needed + 1e-9
    assert got == pytest.approx(needed, abs=0.01)


# --- one orientation --------------------------------------------------------------------------------------


def test_the_size_is_the_extent_along_the_direction_from_surface_to_surface():
    positions = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 4.0]])

    got = projection_at(positions, np.array([1.0, 2.0]), (0.0, 0.0, 1.0))

    assert got.size == pytest.approx(4.0 + 1.0 + 2.0)


def test_the_direction_is_normalised():
    positions, radii = _dumbbell(2.0)

    assert projection_at(positions, radii, (0.0, 0.0, 7.0)).direction == pytest.approx((0.0, 0.0, 1.0))


def test_a_larger_radius_scale_scales_every_figure_consistently():
    positions, radii = _dumbbell(2.0)
    base = projection_extremes(positions, radii)
    doubled = projection_extremes(positions, radii * 2.0)

    # Scaling the radii alone is not a similarity (the separation stays), so only the end-on circle
    # and the sizes have a closed form here.
    assert doubled.minimum.area == pytest.approx(4 * base.minimum.area, rel=2e-4)
    assert doubled.minimum.radius == pytest.approx(2 * base.minimum.radius, rel=1e-3)


# --- a real molecule --------------------------------------------------------------------------------------


def _embedded(smiles: str):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    table = Chem.GetPeriodicTable()
    positions = np.array(mol.GetConformer().GetPositions())
    radii = np.array([table.GetRvdw(atom.GetAtomicNum()) for atom in mol.GetAtoms()])
    return positions, radii


@pytest.mark.parametrize("smiles", ["c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "CCCCCCCCCC"])
def test_the_search_is_at_least_as_good_as_a_sweep_four_times_denser(smiles):
    positions, radii = _embedded(smiles)
    extremes = projection_extremes(positions, radii)
    sweep = np.array([_area(positions, radii, d) for d in _hemisphere(1000)])

    assert extremes.minimum.area <= sweep.min() + 1e-6
    assert extremes.maximum.area >= sweep.max() - 1e-6


def test_the_extremes_do_not_depend_on_where_or_how_a_molecule_is_held():
    positions, radii = _embedded("CC(=O)Oc1ccccc1C(=O)O")
    want = projection_extremes(positions, radii)

    for seed in range(3):
        got = projection_extremes(_rotated(positions, seed), radii)

        assert got.minimum.area == pytest.approx(want.minimum.area, rel=2e-4)
        assert got.maximum.area == pytest.approx(want.maximum.area, rel=2e-4)


def test_the_true_minimum_is_below_the_smallest_principal_plane_for_a_flat_molecule():
    """The reason this exists: benzene read 20.07 A^2 on the principal planes and is 18.76 off them."""
    from openchem.chem.projection_geometry import _principal_axes

    positions, radii = _embedded("c1ccccc1")
    principal = min(_area(positions, radii, axis) for axis in _principal_axes(positions))

    assert projection_extremes(positions, radii).minimum.area < principal - 0.5


def test_the_search_reports_how_many_orientations_it_looked_at():
    positions, radii = _embedded("c1ccccc1")

    assert projection_extremes(positions, radii).orientations > 200


def test_a_medium_molecule_is_searched_in_a_couple_of_seconds():
    positions, radii = _embedded("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    started = time.perf_counter()
    projection_extremes(positions, radii)

    assert time.perf_counter() - started < 5.0
