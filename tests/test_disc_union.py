"""The exact union-of-discs area that a projection's shadow is measured with.

References are CLOSED FORMS, never another numerical routine's output: one disc is pi r^2,
two overlapping discs are the lens formula's inclusion-exclusion, and a disc inside another
adds nothing. Random clouds are checked against a Monte Carlo estimate with a tolerance set by
that estimate's own sampling error, so they can catch a gross mistake but not a small one --
which is why the closed forms carry the precision claims.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from openchem.chem.disc_union import union_area


def _lens(d: float, r1: float, r2: float) -> float:
    """Area shared by two discs a distance `d` apart (the standard closed form)."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2
    a = r1 * r1 * math.acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    b = r2 * r2 * math.acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    c = 0.5 * math.sqrt((-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2))
    return a + b - c


def test_no_discs_cover_nothing():
    assert union_area(np.zeros((0, 2)), np.zeros(0)) == 0.0


def test_one_disc_is_pi_r_squared():
    assert union_area(np.array([[3.0, -2.0]]), np.array([1.7])) == pytest.approx(math.pi * 1.7**2, rel=1e-12)


@pytest.mark.parametrize(
    "distance, r1, r2",
    [(1.0, 1.7, 1.7), (2.5, 1.7, 1.2), (0.3, 2.0, 1.0), (4.0, 1.7, 1.7), (3.4, 1.7, 1.7), (1.5, 1.0, 2.2)],
)
def test_two_discs_are_inclusion_exclusion_to_rounding(distance, r1, r2):
    got = union_area(np.array([[0.0, 0.0], [distance, 0.0]]), np.array([r1, r2]))
    want = math.pi * r1 * r1 + math.pi * r2 * r2 - _lens(distance, r1, r2)

    assert got == pytest.approx(want, abs=1e-10)


def test_two_discs_in_any_direction_cover_the_same_area():
    """The area cannot depend on which way the pair points, which exercises every wrap of the arcs."""
    want = union_area(np.array([[0.0, 0.0], [1.4, 0.0]]), np.array([1.7, 1.2]))
    for angle in np.linspace(0, 2 * math.pi, 37):
        centres = np.array([[0.0, 0.0], [1.4 * math.cos(angle), 1.4 * math.sin(angle)]])
        assert union_area(centres, np.array([1.7, 1.2])) == pytest.approx(want, abs=1e-10)


def test_a_disc_inside_another_adds_nothing():
    assert union_area(np.array([[0.0, 0.0], [0.2, 0.0]]), np.array([3.0, 1.0])) == pytest.approx(9 * math.pi)


def test_identical_discs_count_once_however_many():
    assert union_area(np.zeros((4, 2)), np.full(4, 1.5)) == pytest.approx(math.pi * 1.5**2)


def test_a_disc_touching_another_from_outside_adds_its_whole_area():
    got = union_area(np.array([[0.0, 0.0], [3.4, 0.0]]), np.array([1.7, 1.7]))

    assert got == pytest.approx(2 * math.pi * 1.7**2)


def test_a_chain_of_equal_discs_is_the_sum_less_each_neighbouring_lens():
    """A rod of n discs spaced `d` apart, close enough that only neighbours overlap."""
    n, d, r = 6, 2.0, 1.2
    centres = np.array([[i * d, 0.0] for i in range(n)])
    want = n * math.pi * r * r - (n - 1) * _lens(d, r, r)

    assert union_area(centres, np.full(n, r)) == pytest.approx(want, abs=1e-9)


def test_the_order_of_the_discs_does_not_matter():
    rng = np.random.default_rng(3)
    centres = rng.normal(scale=2.0, size=(25, 2))
    radii = rng.uniform(1.0, 2.0, 25)
    order = rng.permutation(25)

    assert union_area(centres, radii) == pytest.approx(union_area(centres[order], radii[order]), abs=1e-9)


@pytest.mark.parametrize("count, seed", [(5, 1), (30, 2), (120, 3)])
def test_random_clouds_agree_with_a_monte_carlo_estimate(count, seed):
    rng = np.random.default_rng(seed)
    centres = rng.normal(scale=3.0, size=(count, 2))
    radii = rng.uniform(1.0, 2.0, count)
    low = (centres - radii[:, None]).min(axis=0)
    high = (centres + radii[:, None]).max(axis=0)
    points = rng.uniform(low, high, size=(400_000, 2))
    inside = np.zeros(len(points), dtype=bool)
    for centre, radius in zip(centres, radii):
        inside |= ((points - centre) ** 2).sum(axis=1) <= radius * radius
    box = float(np.prod(high - low))
    estimate = inside.mean() * box
    # Four standard errors of the estimate's own binomial noise.
    tolerance = 4 * box * math.sqrt(inside.mean() * (1 - inside.mean()) / len(points))

    assert union_area(centres, radii) == pytest.approx(estimate, abs=tolerance)


def test_the_union_is_never_more_than_the_sum_nor_less_than_the_largest_disc():
    rng = np.random.default_rng(9)
    centres = rng.normal(scale=1.5, size=(40, 2))
    radii = rng.uniform(1.0, 2.0, 40)

    area = union_area(centres, radii)

    assert math.pi * radii.max() ** 2 - 1e-9 <= area <= math.pi * float((radii**2).sum()) + 1e-9
