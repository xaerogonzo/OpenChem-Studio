"""The Gaussian cube reader.

The two fixtures are REAL `orca_plot` output from a real ORCA 6.1.1 job on
water (`! B3LYP def2-SVP Opt`), regenerated at 12 grid points so they fit
in the repository -- `water_esp.cube` is plot type 43, `water_homo.cube` is
the HOMO, which is what supplies a negative atom count and an
orbital-index line to parse.

The convention tests below use hand-built cubes instead, because they need
every value to be known rather than merely plausible: an axis-ordering bug
produces a field that is entirely reasonable-looking and wrong, and only a
grid whose value at each point encodes its own index can catch it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from openchem.chem.cube import (
    BOHR_TO_ANGSTROM,
    CubeFormatError,
    parse_cube,
    read_cube,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "orca"

#: The optimised oxygen z-coordinate ORCA reported in `job.xyz`, in
#: Angstrom. The same job's cube states 0.240430 for the same nucleus;
#: the ratio is the Bohr conversion, and that is the measurement the
#: module docstring cites.
_WATER_OXYGEN_Z_ANGSTROM = 0.12723


def _cube(
    values,
    counts=(2, 3, 4),
    origin=(0.0, 0.0, 0.0),
    steps=((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)),
    atoms=((8, 8.0, (0.0, 0.0, 0.0)),),
    orbital_line: str | None = None,
) -> str:
    """A hand-built cube. `counts` may carry negative entries to select the
    Angstrom convention, and `atoms` a negative length is expressed by
    passing `orbital_line`."""
    atom_count = -len(atoms) if orbital_line is not None else len(atoms)
    lines = [
        "hand-built",
        "test cube",
        f"{atom_count} {origin[0]} {origin[1]} {origin[2]}",
    ]
    for count, step in zip(counts, steps):
        lines.append(f"{count} {step[0]} {step[1]} {step[2]}")
    for number, charge, position in atoms:
        lines.append(f"{number} {charge} {position[0]} {position[1]} {position[2]}")
    if orbital_line is not None:
        lines.append(orbital_line)
    lines.extend(" ".join(f"{value:.6e}" for value in values[i : i + 6]) for i in range(0, len(values), 6))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Conventions, against hand-built cubes where every value is known
# --------------------------------------------------------------------------


def test_values_are_laid_out_with_z_fastest_and_x_slowest():
    """THE bug this file exists to prevent. A transposed field renders as a
    perfectly plausible surface in the wrong orientation, so the value at
    each point encodes its own index and the assertion checks all of them.

    This is also the ordering `scalar_field.to_dx` writes, so a field read
    here survives a round trip through the viewer's format."""
    values = [100 * i + 10 * j + k for i in range(2) for j in range(3) for k in range(4)]

    field = parse_cube(_cube(values)).field

    assert field.values.shape == (2, 3, 4)
    for i in range(2):
        for j in range(3):
            for k in range(4):
                assert field.values[i, j, k] == 100 * i + 10 * j + k


def test_a_positive_voxel_count_means_bohr():
    """Positive counts: the grid is in Bohr and everything converts."""
    field = parse_cube(_cube([0.0] * 24, origin=(1.0, 2.0, 3.0))).field

    assert field.origin[0] == pytest.approx(1.0 * BOHR_TO_ANGSTROM)
    assert field.spacing[0] == pytest.approx(1.0 * BOHR_TO_ANGSTROM)


def test_a_negative_voxel_count_means_angstrom():
    """The other half of the voxel sign convention -- and the reason the
    origin is scaled from the VOXEL sign rather than its own line."""
    field = parse_cube(
        _cube([0.0] * 24, counts=(-2, -3, -4), origin=(1.0, 2.0, 3.0))
    ).field

    assert field.origin[0] == pytest.approx(1.0)
    assert field.spacing[0] == pytest.approx(1.0)


def test_a_negative_atom_count_signals_an_orbital_index_line():
    """Miss this line and the first orbital's values are read as grid
    data, shifting the entire field by one line."""
    values = [float(n) for n in range(24)]

    cube = parse_cube(_cube(values, orbital_line="1 7"))

    assert cube.orbital_indices == (7,)
    assert len(cube.atoms) == 1
    assert cube.field.values[0, 0, 0] == 0.0
    assert cube.field.values[1, 2, 3] == 23.0


def test_the_two_sign_conventions_are_independent():
    """An MO cube in Bohr -- which is exactly what orca_plot writes -- has
    a negative atom count AND positive voxel counts. Conflating them
    would make every orbital file Angstrom."""
    cube = parse_cube(_cube([0.0] * 24, origin=(1.0, 0.0, 0.0), orbital_line="1 4"))

    assert cube.orbital_indices == (4,)
    assert cube.field.origin[0] == pytest.approx(1.0 * BOHR_TO_ANGSTROM)


def test_an_ecp_nuclear_charge_is_not_read_as_an_element():
    """Bromine under a 28-electron core prints 7.0 as its nuclear charge.
    Reading that field as the element would produce nitrogen."""
    cube = parse_cube(_cube([0.0] * 24, atoms=((35, 7.0, (0.0, 0.0, 0.0)),)))

    assert cube.atoms[0].atomic_number == 35
    assert cube.atoms[0].nuclear_charge == pytest.approx(7.0)


def test_a_truncated_grid_is_refused_rather_than_reshaped():
    """A partial grid would raise on reshape anyway for most sizes, but
    not all -- and a silently wrong shape is worse than an error."""
    with pytest.raises(CubeFormatError, match="refusing to reshape"):
        parse_cube(_cube([0.0] * 20))


def test_a_non_axis_aligned_grid_is_refused():
    """The viewer ignores off-diagonal terms, so accepting one would
    misplace every value while rendering perfectly happily."""
    skewed = ((1.0, 0.4, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    with pytest.raises(CubeFormatError, match="axis-aligned"):
        parse_cube(_cube([0.0] * 24, steps=skewed))


def test_a_header_too_short_to_be_a_cube_is_refused():
    with pytest.raises(CubeFormatError, match="at least 6 header lines"):
        parse_cube("not\na\ncube\n")


# --------------------------------------------------------------------------
# Real orca_plot output
# --------------------------------------------------------------------------


def test_a_real_esp_cube_parses():
    cube = read_cube(_FIXTURES / "water_esp.cube", units="Hartree/e")

    assert cube.field.values.shape == (12, 12, 12)
    assert cube.orbital_indices == ()
    assert len(cube.atoms) == 3
    assert [atom.atomic_number for atom in cube.atoms] == [8, 1, 1]
    assert "Electrostatic Potential" in cube.comment
    assert cube.field.units == "Hartree/e"


def test_a_real_esp_cube_lands_its_atoms_in_angstrom():
    """The measurement the module docstring cites: ORCA reported this
    oxygen at 0.12723 A in `job.xyz` and wrote 0.240430 into the cube from
    the same job. Reading the cube must recover the Angstrom value."""
    cube = read_cube(_FIXTURES / "water_esp.cube")

    assert cube.atoms[0].position[2] == pytest.approx(_WATER_OXYGEN_Z_ANGSTROM, abs=1e-4)
    # ...and the hydrogens, which is what catches a conversion applied to
    # the origin but not the atom block.
    assert cube.atoms[1].position[1] == pytest.approx(0.75714, abs=1e-4)


def test_a_real_mo_cube_carries_its_orbital_index():
    """`water_homo.cube` is ORCA's own HOMO for this molecule, and its
    header really does begin with -3."""
    cube = read_cube(_FIXTURES / "water_homo.cube")

    assert cube.orbital_indices == (4,)
    assert len(cube.atoms) == 3
    assert cube.field.values.shape == (12, 12, 12)
    assert "Molecular orbital 4" in cube.comment


def test_a_real_mo_cube_has_both_signs_as_an_orbital_must():
    """A molecular orbital is a wavefunction: it changes sign. A parser
    that dropped the orbital-index line would shift every value by one
    position and still produce a signed field, so this is a sanity check
    rather than the structural one above -- but a field that came back
    all-positive would mean a density was read instead."""
    values = read_cube(_FIXTURES / "water_homo.cube").field.values

    assert values.min() < 0.0 < values.max()


def test_a_real_esp_cube_survives_the_viewers_own_format():
    """The whole point of targeting `ScalarField`: a cube read here goes
    through the existing, already-validated OpenDX render path unchanged."""
    from openchem.chem.scalar_field import symmetric_range, to_dx

    field = read_cube(_FIXTURES / "water_esp.cube").field
    text = to_dx(field)

    assert "object 1 class gridpositions counts 12 12 12" in text
    low, high = symmetric_range(field)
    assert low < 0.0 < high


def test_the_esp_maximum_sits_on_the_oxygen_nucleus():
    """An orientation check that does not depend on knowing the values:
    near a nucleus the nuclear term dominates the electrostatic potential
    and scales with Z, so the maximum must land on the heaviest atom.

    Coarse here (12 points is a 0.67 A grid); the decisive version of this
    check runs at full resolution on bromobenzene in `benchmarks/esp/`,
    where the maximum lands 0.097 A from the bromine."""
    cube = read_cube(_FIXTURES / "water_esp.cube")
    field = cube.field

    index = np.unravel_index(np.argmax(field.values), field.values.shape)
    point = np.array(field.origin) + np.array(index) * np.array(field.spacing)
    distances = sorted(
        (float(np.linalg.norm(point - np.array(atom.position))), atom.atomic_number)
        for atom in cube.atoms
    )

    assert distances[0][1] == 8
