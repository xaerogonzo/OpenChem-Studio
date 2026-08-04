"""Electrostatic potential, checked against the closed form.

A point-charge potential has an exact answer, so nothing here needs to
settle for "looks plausible": a unit charge at 1 A is 332.0637
kcal/(mol*e) and anything else is a bug. That matters more than usual
because the output is a coloured picture, and a picture is very good at
looking right while being wrong by a constant factor or a sign.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from openchem.chem.scalar_field import (
    COULOMB_CONSTANT,
    ScalarField,
    electrostatic_potential,
    electrostatic_potential_for_conformer,
    symmetric_range,
    to_dx,
)


def _value_at(field: ScalarField, point) -> float:
    """Nearest grid sample to a position, for comparing against theory."""
    indices = [
        int(round((point[d] - field.origin[d]) / field.spacing[d])) for d in range(3)
    ]
    return float(field.values[tuple(indices)])


def test_a_single_positive_charge_matches_coulombs_law():
    """The whole formula in one assertion. One electron-charge at the
    origin, sampled 1 A away, must be exactly the Coulomb constant."""
    field = electrostatic_potential(
        [(0.0, 0.0, 0.0)], [1.0], resolution=101, padding=5.0
    )

    # 101 points across [-5, 5] puts a sample exactly on 1.0 A.
    assert _value_at(field, (1.0, 0.0, 0.0)) == pytest.approx(COULOMB_CONSTANT, rel=1e-9)


def test_the_potential_falls_off_as_one_over_r():
    field = electrostatic_potential(
        [(0.0, 0.0, 0.0)], [1.0], resolution=101, padding=5.0
    )

    for distance in (1.0, 2.0, 4.0):
        expected = COULOMB_CONSTANT / distance
        assert _value_at(field, (distance, 0.0, 0.0)) == pytest.approx(expected, rel=1e-9)


def test_a_negative_charge_gives_a_negative_potential():
    """Sign is the entire message of a red/blue map -- inverting it would
    label every electron-rich region as electron-poor."""
    field = electrostatic_potential([(0.0, 0.0, 0.0)], [-1.0], resolution=51, padding=5.0)

    assert _value_at(field, (2.0, 0.0, 0.0)) < 0


def test_a_dipole_is_antisymmetric_about_its_centre():
    """Two opposite charges either side of the origin. Equal and opposite
    samples must cancel, which catches a sign or distance error that a
    single charge cannot."""
    field = electrostatic_potential(
        [(-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [1.0, -1.0], resolution=101, padding=5.0
    )

    positive_side = _value_at(field, (3.0, 0.0, 0.0))
    negative_side = _value_at(field, (-3.0, 0.0, 0.0))
    assert positive_side == pytest.approx(-negative_side, rel=1e-9)
    assert positive_side < 0, "the -1 charge sits on the +x side"


def test_charges_superpose():
    """Two charges at one point must equal one charge of twice the size --
    the linearity the sum depends on."""
    single = electrostatic_potential([(0.0, 0.0, 0.0)], [2.0], resolution=51, padding=5.0)
    doubled = electrostatic_potential(
        [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)], [1.0, 1.0], resolution=51, padding=5.0
    )

    assert np.allclose(single.values, doubled.values)


def test_a_neutral_molecule_decays_faster_than_a_charged_one():
    """Physics, not arithmetic: a net-neutral pair's potential falls off as
    1/r^2 while a net charge falls off as 1/r, so the neutral one is far
    weaker far away."""
    dipole = electrostatic_potential(
        [(-0.5, 0.0, 0.0), (0.5, 0.0, 0.0)], [1.0, -1.0], resolution=101, padding=10.0
    )
    monopole = electrostatic_potential(
        [(-0.5, 0.0, 0.0), (0.5, 0.0, 0.0)], [1.0, 1.0], resolution=101, padding=10.0
    )

    far = (9.0, 0.0, 0.0)
    assert abs(_value_at(dipole, far)) < abs(_value_at(monopole, far)) / 10


def test_the_grid_encloses_the_molecule_with_padding():
    field = electrostatic_potential(
        [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0)], [1.0, -1.0], resolution=21, padding=4.0
    )

    assert field.origin[0] == pytest.approx(-4.0)
    assert field.values.shape == (21, 21, 21)
    # Far corner reaches the other atom plus its padding.
    assert field.origin[0] + 20 * field.spacing[0] == pytest.approx(7.0)


def test_the_singularity_is_clamped_rather_than_infinite():
    """A grid point can land on a nucleus. Without a floor the value is
    inf, which poisons the colour range for the entire surface."""
    field = electrostatic_potential([(0.0, 0.0, 0.0)], [1.0], resolution=11, padding=5.0)

    assert np.isfinite(field.values).all()


def test_mismatched_inputs_are_refused():
    """A charge list out of step with the atoms yields a plausible field
    for the wrong molecule -- the worst kind of wrong."""
    with pytest.raises(ValueError, match="same atoms"):
        electrostatic_potential([(0.0, 0.0, 0.0)], [1.0, -1.0])
    with pytest.raises(ValueError, match="no atoms"):
        electrostatic_potential([], [])


# --- reading the geometry off an RDKit conformer --------------------------


def _ethanol():
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    return mol


def test_the_conformer_helper_agrees_with_the_explicit_call():
    """Same physics, one just reads the positions off the molecule. If the
    two ever diverge, the helper is transposing coordinates."""
    mol = _ethanol()
    conformer = mol.GetConformer()
    positions = [
        (
            conformer.GetAtomPosition(i).x,
            conformer.GetAtomPosition(i).y,
            conformer.GetAtomPosition(i).z,
        )
        for i in range(mol.GetNumAtoms())
    ]
    charges = {i: 0.1 * (-1) ** i for i in range(mol.GetNumAtoms())}

    from_helper = electrostatic_potential_for_conformer(mol, charges, resolution=12)
    explicit = electrostatic_potential(
        positions, [charges[i] for i in range(mol.GetNumAtoms())], resolution=12
    )

    assert np.allclose(from_helper.values, explicit.values)


def test_an_atom_missing_from_the_charge_map_contributes_nothing():
    """A partial dataset is a weaker field, not a different molecule --
    and it must not silently shift the remaining charges onto the wrong
    atoms by falling back to positional order."""
    mol = _ethanol()
    only_oxygen = {2: -0.4}

    partial = electrostatic_potential_for_conformer(mol, only_oxygen, resolution=12)

    assert partial.values.min() < 0
    assert partial.values.max() <= 0, "one negative charge cannot make a positive region"


def test_the_grid_still_surrounds_every_atom_including_uncharged_ones():
    """The box comes from the geometry, not the charge map -- otherwise a
    sparse dataset would produce a surface the grid doesn't cover."""
    mol = _ethanol()
    conformer = mol.GetConformer()
    highest_x = max(conformer.GetAtomPosition(i).x for i in range(mol.GetNumAtoms()))

    field = electrostatic_potential_for_conformer(mol, {0: 1.0}, resolution=12)

    span = field.origin[0] + 11 * field.spacing[0]
    assert span >= highest_x


# --- the OpenDX serialisation the viewer parses --------------------------


def _parse_dx(text: str) -> tuple[tuple[int, int, int], list[float], list[float], list[float]]:
    """A reader mirroring the regexes in the vendored 3Dmol parser, so the
    test checks what the viewer will actually match rather than what the
    format's documentation says."""
    import re

    counts = re.search(r"gridpositions\s+counts\s+(\d+)\s+(\d+)\s+(\d+)", text)
    origin = re.search(r"^origin\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M)
    deltas = re.findall(r"^delta\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M)
    body = text.split("data follows", 1)[1]
    values = [float(token) for token in body.split() if _is_number(token)]
    return (
        tuple(int(counts.group(i)) for i in (1, 2, 3)),
        [float(origin.group(i)) for i in (1, 2, 3)],
        [float(d[i]) for i, d in enumerate(deltas)],
        values,
    )


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def test_the_dx_header_matches_what_the_viewer_parses():
    field = electrostatic_potential(
        [(0.0, 0.0, 0.0)], [1.0], resolution=8, padding=3.0
    )

    counts, origin, deltas, values = _parse_dx(to_dx(field))

    assert counts == (8, 8, 8)
    assert origin == pytest.approx([-3.0, -3.0, -3.0])
    assert deltas == pytest.approx(list(field.spacing))
    assert len(values) == 8 ** 3


def test_dx_values_run_with_z_fastest():
    """The ordering convention. Getting it wrong transposes the field --
    which still renders, still looks like a molecule, and is wrong."""
    field = ScalarField(
        values=np.arange(2 * 2 * 2, dtype=float).reshape(2, 2, 2),
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        units="test",
        name="ordering",
    )

    _counts, _origin, _deltas, values = _parse_dx(to_dx(field))

    assert values == pytest.approx([0, 1, 2, 3, 4, 5, 6, 7])


def test_the_deltas_are_diagonal():
    """3Dmol warns about and ignores off-diagonal terms, so the grid must
    genuinely be axis-aligned rather than relying on that."""
    import re

    field = electrostatic_potential([(0.0, 0.0, 0.0)], [1.0], resolution=4, padding=2.0)

    rows = re.findall(r"^delta\s+(\S+)\s+(\S+)\s+(\S+)", to_dx(field), re.M)
    for index, row in enumerate(rows):
        for position, value in enumerate(row):
            if position != index:
                assert float(value) == 0.0


# --- the colour range ------------------------------------------------------


def test_the_colour_range_is_centred_on_zero():
    """With an asymmetric range, zero potential lands off-centre on a
    red/white/blue scale and neutral regions read as charged."""
    field = electrostatic_potential(
        [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0)], [1.0, -0.2], resolution=31, padding=4.0
    )

    low, high = symmetric_range(field)

    assert low == pytest.approx(-high)
    assert high > 0


def test_the_colour_range_ignores_the_near_nucleus_extremes():
    """Values nearest an atom are the largest and the least meaningful for
    a point-charge model. Scaling to them washes the surface out."""
    field = electrostatic_potential([(0.0, 0.0, 0.0)], [1.0], resolution=41, padding=5.0)

    _low, clipped = symmetric_range(field, percentile=95.0)

    assert clipped < abs(field.values).max()


def test_a_flat_field_still_yields_a_usable_range():
    """An all-zero field (no charges anywhere) must not produce a
    zero-width colour range and a division by zero downstream."""
    field = ScalarField(
        values=np.zeros((4, 4, 4)),
        origin=(0.0, 0.0, 0.0),
        spacing=(1.0, 1.0, 1.0),
        units="test",
        name="flat",
    )

    low, high = symmetric_range(field)

    assert high > low
