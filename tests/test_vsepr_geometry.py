"""The VSEPR starting geometries, held to published shapes and to properties the generator did not write.

The oracle is NOT the generator's own output: each case states the published figures it expects (NIST CCCBDB, 2026-11-13) in this
file (the same numbers, typed again, so a changed table fails here) AND the symmetry facts of the shape
(ClF3 has two equal axial bonds and a planar T; XeF4 is planar with 90 and 180 degree angles; PF5 has
90/120/180). Neither the table nor the symmetry says the other is right; a change to either breaks a test.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.vsepr_geometry import (
    REFERENCES,
    Kind,
    build_vsepr_geometry,
    validate,
)


def _mol(smiles: str) -> Chem.Mol:
    """As the engine's opt-in path returns it: unsanitised, no implicit hydrogens."""
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    for atom in mol.GetAtoms():
        atom.SetNoImplicit(True)
    mol.UpdatePropertyCache(strict=False)
    return mol


def _built(smiles: str):
    outcome = build_vsepr_geometry(_mol(smiles))
    assert outcome.kind is Kind.BUILT, outcome.reason
    return outcome.geometry


def _angle(points, a: int, b: int, c: int) -> float:
    u, v = (
        np.array(points[a]) - np.array(points[b]),
        np.array(points[c]) - np.array(points[b]),
    )
    return math.degrees(
        math.acos(float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))))
    )


def _bond(points, a: int, b: int) -> float:
    return float(np.linalg.norm(np.array(points[a]) - np.array(points[b])))


def _all_angles(geometry):
    return sorted(
        round(_angle(geometry.coordinates, i, geometry.centre_index, j), 1)
        for i, j in itertools.combinations(geometry.ligand_indices, 2)
    )


# (smiles, classification, shape, published axial and equatorial lengths in Angstrom)
CASES = [
    ("FCl(F)F", "AX3E2", "T-shaped", 1.697, 1.597),
    ("FBr(F)F", "AX3E2", "T-shaped", 1.810, 1.721),
    ("F[Xe]F", "AX2E3", "linear", 1.974, 1.974),
    ("F[Xe](F)(F)F", "AX4E2", "square planar", 1.935, 1.935),
    ("FS(F)(F)F", "AX4E", "seesaw", 1.646, 1.545),
    ("FS(F)(F)(F)(F)F", "AX6", "octahedral", 1.561, 1.561),
    ("FP(F)(F)(F)F", "AX5", "trigonal bipyramidal", 1.577, 1.534),
]


@pytest.mark.parametrize(
    ("smiles", "classification", "shape", "axial", "equatorial"), CASES
)
def test_class_shape_and_published_bond_lengths(
    smiles, classification, shape, axial, equatorial
):
    geometry = _built(smiles)
    assert (geometry.classification, geometry.shape) == (classification, shape)
    points = geometry.coordinates
    for index in geometry.axial_indices:
        assert _bond(points, geometry.centre_index, index) == pytest.approx(
            axial, abs=1e-6
        )
    for index in geometry.equatorial_indices:
        assert _bond(points, geometry.centre_index, index) == pytest.approx(
            equatorial, abs=1e-6
        )
    assert np.allclose(points[geometry.centre_index], 0.0)


def test_clf3_is_a_planar_t_with_the_published_angle():
    g = _built("FCl(F)F")
    ax1, ax2 = g.axial_indices
    (eq,) = g.equatorial_indices
    for axial in (ax1, ax2):
        assert _angle(g.coordinates, axial, g.centre_index, eq) == pytest.approx(
            87.45, abs=1e-6
        )
    assert _angle(g.coordinates, ax1, g.centre_index, ax2) == pytest.approx(
        174.9, abs=1e-6
    )
    # all four atoms in one plane
    assert (
        np.linalg.matrix_rank(
            np.array(g.coordinates) - np.array(g.coordinates)[0], tol=1e-9
        )
        == 2
    )


def test_brf3_published_angle():
    g = _built("FBr(F)F")
    assert _angle(
        g.coordinates, g.axial_indices[0], g.centre_index, g.equatorial_indices[0]
    ) == pytest.approx(86.21, abs=1e-6)


def test_xef2_is_linear():
    g = _built("F[Xe]F")
    assert _angle(g.coordinates, 0, 1, 2) == pytest.approx(180.0, abs=1e-6)


def test_xef4_is_square_planar():
    g = _built("F[Xe](F)(F)F")
    assert _all_angles(g) == [90.0] * 4 + [180.0] * 2
    assert (
        np.linalg.matrix_rank(np.array(g.coordinates), tol=1e-9) == 2
    )  # planar through the origin


def test_sf4_is_a_seesaw_with_the_published_angles():
    g = _built("FS(F)(F)F")
    ax1, ax2 = g.axial_indices
    eq1, eq2 = g.equatorial_indices
    assert _angle(g.coordinates, ax1, g.centre_index, ax2) == pytest.approx(
        173.07, abs=1e-6
    )
    assert _angle(g.coordinates, eq1, g.centre_index, eq2) == pytest.approx(
        101.55, abs=1e-6
    )
    # the axial pair lies in the plane perpendicular to the equatorial plane
    assert _all_angles(g).count(173.1) == 1  # rounded to 0.1 by _all_angles


def test_sf6_is_octahedral():
    g = _built("FS(F)(F)(F)(F)F")
    assert _all_angles(g) == [90.0] * 12 + [180.0] * 3


def test_pf5_is_a_trigonal_bipyramid():
    g = _built("FP(F)(F)(F)F")
    assert _all_angles(g) == [90.0] * 6 + [120.0] * 3 + [180.0]


def test_atom_order_is_the_molecules_own():
    """The centre need not be first: its coordinates stay at its own index, ligands fill in atom order."""
    mol = _mol("F[Cl](F)F")
    centre = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == "Cl")
    g = build_vsepr_geometry(mol).geometry
    assert g.centre_index == centre
    assert g.coordinates[centre] == (0.0, 0.0, 0.0)
    assert g.ligand_indices == tuple(i for i in range(4) if i != centre)


def test_the_build_is_deterministic():
    a = _built("FCl(F)F")
    b = _built("FCl(F)F")
    assert a.coordinates == b.coordinates


def test_the_input_molecule_is_not_modified():
    mol = _mol("FCl(F)F")
    before = Chem.MolToMolBlock(mol)
    build_vsepr_geometry(mol)
    assert Chem.MolToMolBlock(mol) == before


@pytest.mark.parametrize(
    ("smiles", "fragment"),
    [("FCl(F)(F)(F)F", "no template"), ("FI(F)F", "no measured geometry")],
)
def test_a_recognised_molecule_without_a_reference_is_refused_not_guessed(
    smiles, fragment
):
    outcome = build_vsepr_geometry(_mol(smiles))
    assert outcome.kind is Kind.UNSUPPORTED
    assert outcome.geometry is None
    assert fragment in outcome.reason


def test_mixed_ligands_are_refused():
    outcome = build_vsepr_geometry(_mol("FS(F)(F)Cl"))
    assert outcome.kind is Kind.UNSUPPORTED
    assert "mixed ligands" in outcome.reason


@pytest.mark.parametrize(
    "smiles",
    [
        "C",
        "O",
        "CC",
        "c1ccccc1",
        "[O-]S(=O)(=O)[O-]",
        "O=Cl(=O)(=O)[O-]",
        "FCl",
        "F[Xe]",
        "[F-].[Na+]",
        "N",
    ],
)
def test_ordinary_molecules_are_left_to_the_normal_path(smiles):
    """Sulfate, perchlorate, water, benzene: correct from distance geometry, so NOT_APPLICABLE and never refused."""
    mol = Chem.MolFromSmiles(smiles)
    assert build_vsepr_geometry(mol).kind is Kind.NOT_APPLICABLE


def test_every_reference_has_a_template_and_builds():
    """No entry is dead: each key reaches a built geometry (guards a table row nothing can use)."""
    for centre, ligand, n in REFERENCES:
        smiles = f"{ligand}[{centre}]" + "".join(f"({ligand})" for _ in range(n - 1))
        outcome = build_vsepr_geometry(_mol(smiles))
        assert outcome.kind is Kind.BUILT, (smiles, outcome.reason)


def test_validate_catches_a_wrong_length_and_a_bad_number():
    g = _built("FCl(F)F")
    bad = list(g.coordinates)
    bad[g.axial_indices[0]] = (9.0, 0.0, 0.0)
    broken = type(g)(**{**g.__dict__, "coordinates": tuple(bad)})
    assert any("from the centre" in p for p in validate(broken))
    nan = type(g)(
        **{
            **g.__dict__,
            "coordinates": tuple([(float("nan"), 0.0, 0.0)] + list(g.coordinates[1:])),
        }
    )
    assert validate(nan) == ["a coordinate is not finite"]


def test_it_agrees_with_what_the_engines_opt_in_path_returns():
    """The Mol the builder will really receive (engine opt-in path) is accepted as is."""
    from tests.test_chem_engine import _hypervalent_molblock

    mol = ChemistryEngine().hypervalent_mol_from_molblock(
        _hypervalent_molblock("Cl", "F", 3)
    )
    assert build_vsepr_geometry(mol).kind is Kind.BUILT
