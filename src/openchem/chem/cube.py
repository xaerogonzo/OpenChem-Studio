"""Gaussian cube files, read into the existing `ScalarField`.

WHY THIS EXISTS. `scalar_field.py` builds a point-charge electrostatic
potential and writes OpenDX for the 3D viewer, and its docstring is blunt
that a point charge "cannot represent a lone pair's directionality or a
sigma hole". `orca_plot` emits real ab initio fields -- density, ESP,
orbitals -- and it emits them as Gaussian cube. This is the adapter, and
it deliberately produces the SAME `ScalarField` the point-charge path
does, so `to_dx()`, `symmetric_range()` and the whole validated render
path are reused rather than reimplemented.

TWO SIGN CONVENTIONS, AND THEY MEAN DIFFERENT THINGS. This is the format's
famous trap and the reason `scalar_field.py` chose OpenDX for its own
output rather than cube:

  * A NEGATIVE ATOM COUNT (line 3) means the file holds one or more
    molecular orbitals, and an extra line listing them follows the atom
    block. Miss it and the first orbital's values are read as coordinates.
  * A NEGATIVE VOXEL COUNT (lines 4-6) means that axis is in ANGSTROM.
    Positive means BOHR.

They are independent. A file can be an MO cube in Bohr (which is exactly
what `orca_plot` writes), and the two negatives have nothing to do with
each other.

UNITS, MEASURED RATHER THAN ASSUMED. `ScalarField` is Angstrom throughout
-- `electrostatic_potential_for_conformer` builds it from RDKit conformer
coordinates, which are Angstrom -- so everything here converts on the way
in. That ORCA writes Bohr was confirmed against a real run rather than
taken from the format spec: for the optimised water geometry ORCA reported
the oxygen at z = 0.12723 Angstrom in `job.xyz` and at z = 0.240430 in the
cube it wrote from the same job, and 0.240430 / 0.12723 = 1.8897, the
Bohr-per-Angstrom conversion to five figures.

The VALUES are NOT converted. A cube's units are whatever the producer
chose -- ORCA writes ESP in Hartree/e and density in e/Bohr^3 -- and there
is no field in the format that says which. Rescaling would mean guessing;
the unit string is carried through as text instead and the caller labels
the surface with it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from openchem.chem.scalar_field import ScalarField

#: Angstrom per Bohr (CODATA). The reciprocal of the 1.8897 measured above.
BOHR_TO_ANGSTROM = 0.529177210903


@dataclass(frozen=True)
class CubeAtom:
    """One nucleus from a cube's atom block, in ANGSTROM.

    `nuclear_charge` is the format's own float field, which is the atomic
    number for a normal calculation but differs under an ECP -- kept
    separate from `atomic_number` rather than assumed equal, since a
    bromine with a 28-electron core prints 7.0 here and reading that as an
    element would produce nitrogen.
    """

    atomic_number: int
    nuclear_charge: float
    position: tuple[float, float, float]


@dataclass(frozen=True)
class CubeFile:
    """A parsed cube: the field, the nuclei it was computed around, and
    which orbitals it holds (empty for a density or potential)."""

    field: ScalarField
    atoms: tuple[CubeAtom, ...]
    #: The MO indices from the extra line a negative atom count signals.
    orbital_indices: tuple[int, ...] = ()
    #: The cube's two free-text header lines, verbatim. ORCA puts a real
    #: description in the second ("Electrostatic Potential", "Molecular
    #: orbital 4 of operator 0"), which is the only thing in the file that
    #: says what the numbers are.
    comment: str = ""


class CubeFormatError(ValueError):
    """Raised when the text is not a readable cube.

    A dedicated type because the caller's response differs from a generic
    ValueError's: a malformed cube means the `orca_plot` invocation was
    wrong, not that the user's input was.
    """


def _axis(tokens: list[str]) -> tuple[int, np.ndarray]:
    """One of the three voxel-axis lines: a count and a step vector.

    Returns the count as a POSITIVE number along with the step already
    converted to Angstrom, folding the sign convention away here so no
    caller has to remember it.
    """
    count = int(tokens[0])
    step = np.array([float(value) for value in tokens[1:4]], dtype=float)
    if count < 0:
        # Negative count: this axis is already in Angstrom.
        return -count, step
    return count, step * BOHR_TO_ANGSTROM


def parse_cube(text: str, name: str = "", units: str = "") -> CubeFile:
    """Parse Gaussian cube text.

    `name` and `units` are what `ScalarField` will carry, since the format
    records neither in a machine-readable way -- see the module docstring
    on why the values are not rescaled. When `name` is empty the cube's
    own second header line is used, which for `orca_plot` output is a real
    description rather than a placeholder.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 6:
        raise CubeFormatError(
            f"a cube needs at least 6 header lines, got {len(lines)} non-blank lines"
        )

    comment = f"{lines[0].strip()} {lines[1].strip()}".strip()

    try:
        origin_tokens = lines[2].split()
        raw_atom_count = int(origin_tokens[0])
        origin = np.array([float(value) for value in origin_tokens[1:4]], dtype=float)
        counts_and_steps = [_axis(lines[3 + axis].split()) for axis in range(3)]
    except (ValueError, IndexError) as exc:
        raise CubeFormatError(f"malformed cube header: {exc}") from exc

    # NEGATIVE ATOM COUNT = orbital file. See the module docstring; this is
    # the convention that costs an off-by-one-line if missed.
    is_orbital_file = raw_atom_count < 0
    atom_count = abs(raw_atom_count)

    counts = [count for count, _ in counts_and_steps]
    steps = [step for _, step in counts_and_steps]

    # The origin follows the VOXEL sign convention, not its own: a file
    # whose axes are in Angstrom states its origin in Angstrom too. Cube
    # files mixing units across those lines are not a thing that exists.
    if any(int(lines[3 + axis].split()[0]) < 0 for axis in range(3)):
        origin_angstrom = origin
        atom_scale = 1.0
    else:
        origin_angstrom = origin * BOHR_TO_ANGSTROM
        atom_scale = BOHR_TO_ANGSTROM

    atoms = []
    for index in range(atom_count):
        tokens = lines[6 + index].split()
        if len(tokens) < 5:
            raise CubeFormatError(f"malformed atom line {index}: {lines[6 + index]!r}")
        position = np.array([float(value) for value in tokens[2:5]], dtype=float) * atom_scale
        atoms.append(
            CubeAtom(
                atomic_number=int(tokens[0]),
                nuclear_charge=float(tokens[1]),
                position=(float(position[0]), float(position[1]), float(position[2])),
            )
        )

    body_start = 6 + atom_count
    orbital_indices: tuple[int, ...] = ()
    if is_orbital_file:
        # The line is "<how many> <index> [<index> ...]". Reading the count
        # rather than taking every integer on the line matters: ORCA wraps
        # this line for a file holding many orbitals.
        orbital_tokens = lines[body_start].split()
        try:
            declared = int(orbital_tokens[0])
        except (ValueError, IndexError) as exc:
            raise CubeFormatError(f"malformed orbital-index line: {exc}") from exc
        collected = [int(value) for value in orbital_tokens[1:]]
        body_start += 1
        while len(collected) < declared:
            collected.extend(int(value) for value in lines[body_start].split())
            body_start += 1
        orbital_indices = tuple(collected[:declared])

    values: list[float] = []
    for line in lines[body_start:]:
        values.extend(float(token) for token in line.split())

    expected = counts[0] * counts[1] * counts[2] * max(len(orbital_indices), 1)
    if len(values) != expected:
        raise CubeFormatError(
            f"expected {expected} values for a "
            f"{counts[0]}x{counts[1]}x{counts[2]} grid"
            + (f" of {len(orbital_indices)} orbitals" if len(orbital_indices) > 1 else "")
            + f", found {len(values)} -- refusing to reshape a partial grid"
        )

    array = np.asarray(values, dtype=float)
    if len(orbital_indices) > 1:
        # Multiple orbitals interleave with the ORBITAL index fastest of
        # all, inside z. Only the first is returned, because `ScalarField`
        # holds one field; callers wanting the rest ask orca_plot for one
        # file each, which is what the driver does.
        array = array.reshape(counts[0], counts[1], counts[2], len(orbital_indices))[..., 0]
    else:
        # x is the OUTER loop and z the inner -- the cube convention, and
        # identical to C order for a [i, j, k] array, so `reshape` is the
        # whole conversion. `to_dx` relies on exactly the same ordering in
        # the other direction, so a field read here round-trips.
        array = array.reshape(counts[0], counts[1], counts[2])

    # Only the diagonal of the step matrix survives. `ScalarField` is
    # axis-aligned by construction (`to_dx` documents that 3Dmol warns on
    # a non-orthogonal grid and then ignores the off-diagonal terms), and
    # orca_plot writes axis-aligned grids. Refusing is better than
    # silently placing every value in the wrong place.
    for axis, step in enumerate(steps):
        off_axis = [abs(step[other]) for other in range(3) if other != axis]
        if max(off_axis) > 1e-8:
            raise CubeFormatError(
                "cube grid is not axis-aligned -- the 3D viewer ignores the "
                "off-diagonal terms, which would misplace every value"
            )

    field = ScalarField(
        values=array,
        origin=(
            float(origin_angstrom[0]),
            float(origin_angstrom[1]),
            float(origin_angstrom[2]),
        ),
        spacing=(float(steps[0][0]), float(steps[1][1]), float(steps[2][2])),
        units=units,
        name=name or (lines[1].strip() or "Cube data"),
    )
    return CubeFile(
        field=field,
        atoms=tuple(atoms),
        orbital_indices=orbital_indices,
        comment=comment,
    )


def read_cube(path, name: str = "", units: str = "") -> CubeFile:
    """`parse_cube` on a file. Latin-1 rather than UTF-8 deliberately:
    cube files are pure ASCII numerics, and a stray high byte in a
    comment line should not fail the whole parse."""
    from pathlib import Path

    return parse_cube(Path(path).read_text(encoding="latin-1"), name=name, units=units)
