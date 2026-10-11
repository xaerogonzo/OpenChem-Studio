"""Accessible surface area by Shrake-Rupley, with a deterministic point set.

**WHY THIS EXISTS RATHER THAN RDKIT'S `rdFreeSASA` OR ITS ANALYTIC `DoubleCubicLatticeVolume`.**
Measured on 2026-10-10 against a 200,000-point reference, at a 1.4 A probe:

    benzene (flat)      reference 243.7     rdFreeSASA Lee-Richards 234.4 (-3.8%)
                                            DoubleCubicLatticeVolume 254.6 (+4.5%)
    aspirin             reference 362.3     Lee-Richards 360.0 (-0.6%)   DCLV 365.6 (+0.9%)
    ethanol             reference 197.8     Lee-Richards 198.9 (+0.5%)   DCLV 198.4 (+0.3%)

and at probe 0 the analytic surface was 1.1% high for benzene and ethanol. The error is not
a constant: it depends on the molecule and, for slicing, on its orientation, which is a bad
property in a number whose job is to compare conformers. The same count of test points per atom,
on a Fibonacci spiral (the same points every call, so a repeat run agrees exactly), converges
smoothly:

    points per atom     300      960     2000    5000
    worst error        0.9%     0.4%     0.3%    0.13%      (four molecules, 1 to 285 ms)

so 2000 is the default, an accuracy of about 0.3%. A lone sphere is EXACT at any point count
(nothing occludes it), and two spheres match their closed form to that same 0.3%.

Each atom's sphere (its van der Waals radius plus the probe) is covered with points; the share of
them not inside any other atom's sphere, times the sphere's area, is the atom's accessible area.
"""

from __future__ import annotations

import math

import numpy as np

#: Test points per atom: the default accuracy, about 0.3% (the table above).
DEFAULT_POINTS = 2000

#: A point exactly on another sphere's surface is on the boundary, not inside it. Without this a
#: pair of identical radii touching at one point would hide a whole point of each sphere.
_BOUNDARY = 1e-12


def sphere_points(count: int) -> np.ndarray:
    """`count` points spread evenly over the unit sphere on a Fibonacci spiral, the same every call."""
    index = np.arange(count) + 0.5
    z = 1.0 - 2.0 * index / count
    ring = np.sqrt(np.clip(1.0 - z * z, 0.0, None))
    angle = index * math.pi * (3.0 - math.sqrt(5.0))
    return np.stack([ring * np.cos(angle), ring * np.sin(angle), z], axis=1)


def accessible_areas(
    positions: np.ndarray, radii: np.ndarray, probe: float, points: int = DEFAULT_POINTS
) -> np.ndarray:
    """The accessible surface area of each atom, in A^2, for a probe of radius `probe`.

    `probe` 0 is the van der Waals surface itself. The areas of all the atoms sum to the molecule's.
    """
    positions = np.asarray(positions, dtype=float)
    reach = np.asarray(radii, dtype=float) + float(probe)
    count = len(reach)
    areas = np.zeros(count)
    if count == 0:
        return areas
    unit = sphere_points(points)
    separation = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
    for index in range(count):
        near = np.nonzero((separation[index] < reach[index] + reach) & (np.arange(count) != index))[0]
        if len(near) == 0:
            areas[index] = 4.0 * math.pi * reach[index] ** 2
            continue
        surface = positions[index] + reach[index] * unit
        gap = np.linalg.norm(surface[:, None, :] - positions[near][None, :, :], axis=2)
        exposed = ~(gap < reach[near][None, :] - _BOUNDARY).any(axis=1)
        areas[index] = 4.0 * math.pi * reach[index] ** 2 * float(exposed.mean())
    return areas
