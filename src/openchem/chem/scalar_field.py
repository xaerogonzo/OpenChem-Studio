"""Scalar fields on a grid, and the OpenDX text a viewer can colour by.

WHAT THIS IS FOR. A molecular surface coloured by a continuous property
is how a chemist reads charge distribution at a glance -- the red/blue
electrostatic potential map every package draws. Colouring per ATOM
cannot express it: the property is defined everywhere in space, and the
surface samples it between atoms as much as on them.

WHAT THE POTENTIAL HERE IS, AND IS NOT. It is a sum of point-charge
Coulomb terms over the atoms, evaluated on a grid:

    V(r) = 332.0637 * SUM_i  q_i / |r - r_i|      kcal/(mol*e)

with `q_i` the partial charges the caller supplies. That is a real,
standard approximation and it is the one most viewers show -- but it is
NOT an ab initio molecular electrostatic potential. A point charge has no
shape: it cannot represent a lone pair's directionality or a sigma hole,
so a halogen bond donor looks uniformly positive here when the real
potential has a positive cap along the C-X axis and a negative belt
around it. Read it for gross polarity, not for subtle features.

The constant is exact rather than fitted: 332.0637 kcal*A/(mol*e^2) is
e^2/(4*pi*epsilon_0) expressed in those units, so a unit charge at 1 A
gives exactly 332.0637 -- which is what `tests/test_scalar_field.py`
checks, because a formula worth shipping has a closed form worth
checking against.

OpenDX rather than Gaussian CUBE, deliberately. CUBE's unit convention
is famously ambiguous (Bohr or Angstrom, signalled by the sign of a
count), and the vendored 3Dmol build applies no conversion to DX at all
-- confirmed by reading its parser. Everything here is Angstroms, and
there is no factor of 1.889 waiting to silently misplace a grid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: e^2 / (4 pi epsilon_0), in kcal * Angstrom / (mol * e^2). Exact by
#: definition of the units, not a fitted parameter.
COULOMB_CONSTANT = 332.0637

#: Grid points per axis. 48 keeps a 30-atom molecule's field under half a
#: megabyte of DX text while staying smooth across a surface; the cost is
#: cubic, so this is the parameter to think about before any other.
DEFAULT_RESOLUTION = 48

#: How far the grid extends beyond the atoms, in Angstrom. It has to clear
#: the molecular surface itself -- a solvent-excluded surface sits roughly
#: 1.4 A outside the van der Waals radius, and a grid that stops short
#: leaves the surface's outer reaches uncoloured.
DEFAULT_PADDING = 4.0

#: Distance floor when evaluating 1/r, in Angstrom. The potential diverges
#: at a nucleus, and a grid point can land arbitrarily close to one.
#: Clamping is safe here BECAUSE the consumer is a molecular surface,
#: which never passes through a nucleus -- the clamped points exist in the
#: grid but are not sampled by anything that gets drawn.
_MIN_DISTANCE = 0.4


@dataclass(frozen=True)
class ScalarField:
    """Values sampled on a regular axis-aligned grid.

    `values` is indexed `[i, j, k]` along x, y, z. Kept as a real array
    rather than a flat list because every consumer either writes it out or
    takes statistics over it, and both are one call on an ndarray.
    """

    values: np.ndarray
    origin: tuple[float, float, float]
    spacing: tuple[float, float, float]
    units: str
    name: str

    @property
    def extremes(self) -> tuple[float, float]:
        """Min and max, which is what a colour scale needs."""
        return float(self.values.min()), float(self.values.max())


def electrostatic_potential(
    positions: list[tuple[float, float, float]],
    charges: list[float],
    resolution: int = DEFAULT_RESOLUTION,
    padding: float = DEFAULT_PADDING,
) -> ScalarField:
    """Point-charge electrostatic potential on a grid around the atoms.

    See the module docstring for what this approximation can and cannot
    represent. Raises `ValueError` rather than guessing when the inputs
    disagree, since a silently mismatched charge list would produce a
    plausible-looking field for the wrong molecule.
    """
    if len(positions) != len(charges):
        raise ValueError(
            f"{len(positions)} positions but {len(charges)} charges -- "
            "they must describe the same atoms"
        )
    if not positions:
        raise ValueError("no atoms to compute a potential around")

    coordinates = np.asarray(positions, dtype=float)
    charge_array = np.asarray(charges, dtype=float)

    lower = coordinates.min(axis=0) - padding
    upper = coordinates.max(axis=0) + padding
    axes = [np.linspace(lower[d], upper[d], resolution) for d in range(3)]
    spacing = tuple(
        float(axis[1] - axis[0]) if resolution > 1 else 1.0 for axis in axes
    )

    # One (points, 3) array rather than a triple loop: 48^3 points against
    # 30 atoms is 3.3 million distances, which is a fraction of a second
    # vectorised and several seconds in Python.
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    potential = np.zeros(grid.shape[0], dtype=float)
    for centre, charge in zip(coordinates, charge_array, strict=True):
        distance = np.linalg.norm(grid - centre, axis=1)
        np.maximum(distance, _MIN_DISTANCE, out=distance)
        potential += charge / distance
    potential *= COULOMB_CONSTANT

    return ScalarField(
        values=potential.reshape(resolution, resolution, resolution),
        origin=(float(lower[0]), float(lower[1]), float(lower[2])),
        spacing=spacing,
        units="kcal/(mol*e)",
        name="Electrostatic potential",
    )


def electrostatic_potential_for_conformer(
    mol,
    charges: dict[int, float],
    resolution: int = DEFAULT_RESOLUTION,
    padding: float = DEFAULT_PADDING,
) -> ScalarField:
    """The potential around an RDKit conformer, given per-atom charges.

    Takes the charges as a dict keyed by atom index rather than reading
    them off the molecule, because the caller already has them as a
    computed `PerAtomDataset` -- and because recomputing would risk
    charging a DIFFERENT protonation state than the one on screen.

    Atoms missing from `charges` contribute nothing (charge 0) rather
    than raising: a dataset can legitimately cover a subset, and a hole
    in the map is a weaker field, not a wrong molecule.
    """
    conformer = mol.GetConformer()
    positions = []
    values = []
    for index in range(mol.GetNumAtoms()):
        point = conformer.GetAtomPosition(index)
        positions.append((point.x, point.y, point.z))
        values.append(float(charges.get(index, 0.0)))
    return electrostatic_potential(positions, values, resolution, padding)


def to_dx(field: ScalarField) -> str:
    """Serialise as OpenDX, the format the 3D viewer parses.

    The three `delta` lines form a diagonal matrix. 3Dmol warns on a
    non-orthogonal one and ignores the off-diagonal terms, so the grid is
    kept axis-aligned rather than relying on that.

    Values run with **z fastest**, then y, then x -- which is both the DX
    convention and C order for a `[i, j, k]` array, so `ravel` is the
    whole conversion.
    """
    nx, ny, nz = field.values.shape
    ox, oy, oz = field.origin
    hx, hy, hz = field.spacing
    flat = field.values.ravel(order="C")

    lines = [
        f"# {field.name} in {field.units}",
        f"object 1 class gridpositions counts {nx} {ny} {nz}",
        f"origin {ox:.6f} {oy:.6f} {oz:.6f}",
        f"delta {hx:.6f} 0.000000 0.000000",
        f"delta 0.000000 {hy:.6f} 0.000000",
        f"delta 0.000000 0.000000 {hz:.6f}",
        f"object 2 class gridconnections counts {nx} {ny} {nz}",
        f"object 3 class array type double rank 0 items {flat.size} data follows",
    ]
    lines.extend(
        " ".join(f"{value:.5e}" for value in flat[start : start + 3])
        for start in range(0, flat.size, 3)
    )
    lines.append('object "regular positions regular connections" class field')
    return "\n".join(lines) + "\n"


def symmetric_range(field: ScalarField, percentile: float = 95.0) -> tuple[float, float]:
    """A colour range centred on zero, clipped to a percentile.

    Centred because the sign is the whole point: with an asymmetric range,
    zero potential lands somewhere other than the middle of a red/white/
    blue scale and neutral regions read as charged.

    Clipped because the raw extremes are set by grid points nearest the
    nuclei, where a point-charge model is least meaningful and largest --
    scaling to them washes the entire surface out to white. The percentile
    is over magnitude, so both signs are treated alike.
    """
    limit = float(np.percentile(np.abs(field.values), percentile))
    if limit <= 0.0:
        limit = float(np.abs(field.values).max()) or 1.0
    return -limit, limit
