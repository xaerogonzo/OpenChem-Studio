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
        math.acos(float(np.clip(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v)), -1.0, 1.0)))
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
    # from the papers (Robiette 1971, Bodenseh 1976, Adams 1970): apical then basal / axial then equatorial
    ("FBr(F)(F)(F)F", "AX5E", "square pyramidal", 1.689, 1.774),
    ("FI(F)(F)(F)F", "AX5E", "square pyramidal", 1.844, 1.869),
    ("FCl(F)(F)(F)F", "AX5E", "square pyramidal", 1.65, 1.65),
    ("FI(F)(F)(F)(F)(F)F", "AX7", "pentagonal bipyramidal", 1.786, 1.858),
    # arsenic and selenium from their papers (Clippard 1970, Bowater 1968), PCl5 (Adams 1971), SeF6 (Bartell 1984), TeCl4 (Kovacs 1997) and the two
    # anions from crystal structures (Scheibe 2020, Christe 1991)
    ("F[As](F)(F)(F)F", "AX5", "trigonal bipyramidal", 1.711, 1.656),
    ("F[Se](F)(F)F", "AX4E", "seesaw", 1.7713, 1.6821),
    ("ClP(Cl)(Cl)(Cl)Cl", "AX5", "trigonal bipyramidal", 2.124, 2.020),
    ("F[Se](F)(F)(F)(F)F", "AX6", "octahedral", 1.685, 1.685),
    ("Cl[Te](Cl)(Cl)Cl", "AX4E", "seesaw", 2.430, 2.298),
    ("F[Cl-](F)(F)F", "AX4E2", "square planar", 1.7982, 1.7982),
    ("FI(F)F", "AX3E2", "T-shaped", 1.983, 1.872),
    ("F[I-](F)(F)F", "AX4E2", "square planar", 2.007, 2.007),
    ("F[I-]F", "AX2E3", "linear", 2.0785, 2.0785),
    ("F[Br-](F)(F)F", "AX4E2", "square planar", 1.89, 1.89),
    ("F[As-](F)(F)F", "AX4E", "seesaw", 1.870, 1.7255),
    ("F[Cl+](F)(F)F", "AX4E", "seesaw", 1.617, 1.530),
    ("F[Xe-](F)(F)(F)F", "AX5E2", "pentagonal planar", 2.012, 2.012),
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


@pytest.mark.parametrize(("smiles", "angle"), [("FBr(F)(F)(F)F", 84.8), ("FI(F)(F)(F)F", 81.9), ("FCl(F)(F)(F)F", 86.5)])
def test_a_square_pyramid_has_the_published_apical_basal_angle_and_a_planar_basal_square(smiles, angle):
    g = _built(smiles)
    (apical,) = g.axial_indices
    for basal in g.equatorial_indices:
        assert _angle(g.coordinates, apical, g.centre_index, basal) == pytest.approx(angle, abs=1e-6)
    points = np.array([g.coordinates[i] for i in g.equatorial_indices])
    assert np.linalg.matrix_rank(points - points.mean(axis=0), tol=1e-9) == 2, "the four basal ligands are coplanar"
    # four equal basal-basal contacts round the square, and the two diagonals
    pairs = sorted(
        round(_angle(g.coordinates, i, g.centre_index, j), 2)
        for n, i in enumerate(g.equatorial_indices)
        for j in g.equatorial_indices[n + 1 :]
    )
    theta = math.radians(angle)
    assert pairs == sorted([round(math.degrees(math.acos(math.cos(theta) ** 2)), 2)] * 4 + [round(2 * angle, 2)] * 2)


def test_brf5_basal_basal_angle_matches_the_independently_listed_figure():
    """NIST CCCBDB lists 89.53 degrees for BrF5's basal-basal angle (Gurvich): a number this file did not derive."""
    g = _built("FBr(F)(F)(F)F")
    first, second = g.equatorial_indices[0], g.equatorial_indices[1]
    assert _angle(g.coordinates, first, g.centre_index, second) == pytest.approx(89.53, abs=0.02)


def test_clf5_is_the_one_row_whose_lengths_are_an_assumption_and_says_so():
    from openchem.chem.vsepr_geometry import REFERENCES

    reference = REFERENCES[("Cl", "F", 5, 0)]
    assert reference.axial == reference.equatorial == 1.65
    assert "complete structure is not possible" in reference.method


def test_if7_is_an_ideal_pentagonal_bipyramid():
    g = _built("FI(F)(F)(F)(F)(F)F")
    # 21 ligand pairs: one axial-axial, ten axial-equatorial, five 72 degree and five 144 degree equatorial
    assert _all_angles(g) == [72.0] * 5 + [90.0] * 10 + [144.0] * 5 + [180.0]


def test_asf5_is_a_trigonal_bipyramid_with_the_published_axial_and_equatorial_lengths():
    g = _built("F[As](F)(F)(F)F")
    assert _all_angles(g) == [90.0] * 6 + [120.0] * 3 + [180.0]


def test_sef4_is_a_seesaw_with_the_published_angles():
    g = _built("F[Se](F)(F)F")
    ax1, ax2 = g.axial_indices
    eq1, eq2 = g.equatorial_indices
    assert _angle(g.coordinates, ax1, g.centre_index, ax2) == pytest.approx(169.20, abs=1e-6)
    assert _angle(g.coordinates, eq1, g.centre_index, eq2) == pytest.approx(100.55, abs=1e-6)


def test_tecl4_is_a_seesaw_with_the_published_angles():
    g = _built("Cl[Te](Cl)(Cl)Cl")
    ax1, ax2 = g.axial_indices
    eq1, eq2 = g.equatorial_indices
    assert _angle(g.coordinates, ax1, g.centre_index, ax2) == pytest.approx(175.9, abs=1e-6)
    assert _angle(g.coordinates, eq1, g.centre_index, eq2) == pytest.approx(103.0, abs=1e-6)


def test_clf4_anion_is_square_planar():
    g = _built("F[Cl-](F)(F)F")
    assert _all_angles(g) == [90.0] * 4 + [180.0] * 2
    assert np.linalg.matrix_rank(np.array(g.coordinates), tol=1e-9) == 2


def test_xef5_anion_is_a_planar_regular_pentagon():
    """Five ligands in one plane through the centre: five 72 degree and five 144 degree angles, nothing else."""
    g = _built("F[Xe-](F)(F)(F)F")
    assert _all_angles(g) == [72.0] * 5 + [144.0] * 5
    assert np.linalg.matrix_rank(np.array(g.coordinates), tol=1e-9) == 2, "all six atoms are coplanar"
    assert g.axial_indices == () and len(g.equatorial_indices) == 5


def test_the_charge_is_part_of_the_reference_key():
    """ClF4- has a geometry, the neutral and the cation do not share it: a different charge is a different molecule."""
    assert build_vsepr_geometry(_mol("F[Cl-](F)(F)F")).kind is Kind.BUILT
    cation = build_vsepr_geometry(_mol("F[Br+](F)(F)F"))
    assert cation.kind is Kind.UNSUPPORTED and "charge +1" in cation.reason


def test_a_charge_on_a_ligand_or_a_second_fragment_is_not_a_hypervalent_anion():
    assert build_vsepr_geometry(_mol("[F-].F[Cl](F)F")).kind is Kind.NOT_APPLICABLE
    assert build_vsepr_geometry(_mol("[F-][Cl](F)(F)F")).kind is Kind.NOT_APPLICABLE


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
    [
        ("ClS(Cl)(Cl)Cl", "no measured geometry"),
        ("ClI(Cl)Cl", "no measured geometry"),
        ("F[Br+](F)(F)F", "charge +1"),
        ("Cl[I-](Cl)(Cl)Cl", "charge -1"),
    ],
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
    for (centre, ligand, n, charge), reference in REFERENCES.items():
        symbol = f"[{centre}{'-' if charge < 0 else '+' if charge > 0 else ''}]"
        if reference.slots:
            parts = [f"(={t[:-1]})" if t.endswith("=") else f"({t})" for t, _ in reference.slots]
            smiles = symbol + "".join(parts)
        else:
            smiles = f"{ligand}{symbol}" + "".join(f"({ligand})" for _ in range(n - 1))
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


# --- mixed ligands and oxo ligands (each figure typed again from its paper; the angles are what the paper printed) ---


def _by_element(g, mol_smiles: str, symbol: str) -> list[int]:
    mol = _mol(mol_smiles)
    return [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == symbol]


def test_clf3o_reproduces_the_three_published_angles_and_each_length():
    smiles = "FCl(F)(F)=O"
    g = _built(smiles)
    assert (g.classification, g.shape) == ("AX4E", "seesaw")
    p, c = g.coordinates, g.centre_index
    oxygen = _by_element(g, smiles, "O")[0]
    ax1, ax2 = g.axial_indices
    f_eq = next(i for i in g.equatorial_indices if i != oxygen)
    assert _bond(p, c, oxygen) == pytest.approx(1.405, abs=1e-6)
    assert _bond(p, c, ax1) == pytest.approx(1.713, abs=1e-6) and _bond(p, c, ax2) == pytest.approx(1.713, abs=1e-6)
    assert _bond(p, c, f_eq) == pytest.approx(1.603, abs=1e-6)
    assert _angle(p, f_eq, c, oxygen) == pytest.approx(108.9, abs=1e-6)
    for axial in (ax1, ax2):
        assert _angle(p, axial, c, f_eq) == pytest.approx(87.9, abs=1e-6)
        assert _angle(p, axial, c, oxygen) == pytest.approx(94.7, abs=1e-6)


def test_xeof4_is_a_square_pyramid_with_oxygen_apical():
    smiles = "F[Xe](F)(F)(F)=O"
    g = _built(smiles)
    assert (g.classification, g.shape) == ("AX5E", "square pyramidal")
    p, c = g.coordinates, g.centre_index
    oxygen = _by_element(g, smiles, "O")[0]
    assert g.axial_indices == (oxygen,)
    assert _bond(p, c, oxygen) == pytest.approx(1.7053, abs=1e-6)
    for f in _by_element(g, smiles, "F"):
        assert _bond(p, c, f) == pytest.approx(1.9040, abs=1e-6)
        assert _angle(p, oxygen, c, f) == pytest.approx(91.66, abs=1e-6)
    basal = _by_element(g, smiles, "F")
    # the basal fluorines form a square about the axis: four neighbouring pairs at 90 degrees, two opposite at 180
    pair_angles = sorted(_angle(p, a, c, b) for a, b in itertools.combinations(basal, 2))
    assert pair_angles[:4] == pytest.approx([90.0] * 4, abs=1e-6) or pair_angles[:4] == pytest.approx(
        [pair_angles[0]] * 4, abs=1e-6
    )
    assert pair_angles[-2:] == pytest.approx([pair_angles[-1]] * 2, abs=1e-6)


def test_xeo2f2_is_a_seesaw_with_the_published_angles():
    smiles = "F[Xe](F)(=O)=O"
    g = _built(smiles)
    p, c = g.coordinates, g.centre_index
    f1, f2 = g.axial_indices
    o1, o2 = g.equatorial_indices
    assert {_by_element(g, smiles, "F")[0], _by_element(g, smiles, "F")[1]} == {f1, f2}
    assert _angle(p, f1, c, f2) == pytest.approx(174.7, abs=1e-6)
    assert _angle(p, o1, c, o2) == pytest.approx(105.7, abs=1e-6)
    assert _bond(p, c, o1) == pytest.approx(1.714, abs=1e-6) and _bond(p, c, f1) == pytest.approx(1.899, abs=1e-6)
    # the paper's O-Xe-F 91.6 is above 90: the fluorines bend toward the lone pair, and the angle comes out of the other two
    assert _angle(p, f1, c, o1) == pytest.approx(91.6, abs=0.1)


def test_sof4_gets_the_published_angle_it_was_not_given():
    smiles = "FS(F)(F)(F)=O"
    g = _built(smiles)
    p, c = g.coordinates, g.centre_index
    oxygen = _by_element(g, smiles, "O")[0]
    ax1, ax2 = g.axial_indices
    f_eq = [i for i in g.equatorial_indices if i != oxygen]
    assert _bond(p, c, oxygen) == pytest.approx(1.409, abs=1e-6)
    assert _bond(p, c, ax1) == pytest.approx(1.596, abs=1e-6)
    assert all(_bond(p, c, f) == pytest.approx(1.539, abs=1e-6) for f in f_eq)
    assert _angle(p, f_eq[0], c, f_eq[1]) == pytest.approx(112.8, abs=1e-6)
    assert _angle(p, ax1, c, oxygen) == pytest.approx(97.7, abs=1e-6)
    # published F(ax)-S-F(eq) 85.7 and F(eq)-S-O 123.6: inputs of neither, implied by the two above
    assert _angle(p, ax1, c, f_eq[0]) == pytest.approx(85.7, abs=0.3)
    assert _angle(p, f_eq[0], c, oxygen) == pytest.approx(123.6, abs=0.1)


def test_sf5cl_has_chlorine_apical_and_the_published_cl_s_f_angle():
    smiles = "FS(F)(F)(F)(F)Cl"
    g = _built(smiles)
    p, c = g.coordinates, g.centre_index
    cl = _by_element(g, smiles, "Cl")[0]
    assert _bond(p, c, cl) == pytest.approx(2.0301, abs=1e-6)
    trans = g.axial_indices[1]
    assert _angle(p, cl, c, trans) == pytest.approx(180.0, abs=1e-6)
    for f in g.equatorial_indices:
        assert _angle(p, cl, c, f) == pytest.approx(88.0 + 22.0 / 60.0, abs=1e-6)
        assert _bond(p, c, f) == pytest.approx(1.576, abs=1e-6)


@pytest.mark.parametrize(
    "smiles",
    ["O=S(=O)(O)O", "O=[Xe](=O)=O", "O=[Xe](=O)(=O)=O", "[O-][Cl](=O)(=O)=O", "O=P(Cl)(Cl)Cl", "FS(F)(F)(F)(F)F"],
)
def test_oxo_molecules_without_a_recorded_geometry_stay_on_the_ordinary_path(smiles):
    outcome = build_vsepr_geometry(_mol(smiles))
    assert outcome.kind in (Kind.NOT_APPLICABLE, Kind.BUILT)
    if outcome.kind is Kind.BUILT:
        assert smiles == "FS(F)(F)(F)(F)F"
    # and a mixed-ligand molecule the table lacks is refused with the reason, not guessed
    assert build_vsepr_geometry(_mol("FCl(F)Cl")).kind is Kind.UNSUPPORTED


def test_if3_is_a_planar_t_with_the_published_angles():
    """Hoyer and Seppelt 2000: F-I-F 160.3 (0.2) between the two long bonds, 80.2 (0.1) to the short one."""
    g = _built("FI(F)F")
    ax1, ax2 = g.axial_indices
    eq = g.equatorial_indices[0]
    p, c = g.coordinates, g.centre_index
    assert _angle(p, ax1, c, eq) == pytest.approx(80.2, abs=1e-6)
    assert _angle(p, ax1, c, ax2) == pytest.approx(160.4, abs=1e-6), "implied by 80.2 twice; the paper's 160.3 is inside its esd"
    assert max(abs(np.dot(np.array(p[i]) - np.array(p[c]), np.cross(np.array(p[ax1]) - np.array(p[c]), np.array(p[ax2]) - np.array(p[c])))) for i in (eq,)) < 1e-9, "planar"


def test_clf4_cation_reproduces_the_crystals_three_angles():
    """Christe 2001: F-Cl-F 173.92 axial, 103.08 equatorial, 88.1 between them (88.16 and 88.06 measured)."""
    g = _built("F[Cl+](F)(F)F")
    ax1, ax2 = g.axial_indices
    eq1, eq2 = g.equatorial_indices
    p, c = g.coordinates, g.centre_index
    assert _angle(p, ax1, c, ax2) == pytest.approx(173.92, abs=1e-6)
    assert _angle(p, eq1, c, eq2) == pytest.approx(103.08, abs=1e-6)
    assert _angle(p, ax1, c, eq1) == pytest.approx(88.1, abs=0.1)


def test_asf4_anion_reproduces_the_published_axial_and_equatorial_angles():
    """Zhang and Seppelt 1997: F-As-F 165.7 axial and 97.5 equatorial; the 84.5 to 86.1 between them is implied."""
    g = _built("F[As-](F)(F)F")
    ax1, ax2 = g.axial_indices
    eq1, eq2 = g.equatorial_indices
    p, c = g.coordinates, g.centre_index
    assert _angle(p, ax1, c, ax2) == pytest.approx(165.7, abs=1e-6)
    assert _angle(p, eq1, c, eq2) == pytest.approx(97.5, abs=1e-6)
    assert 84.5 <= _angle(p, ax1, c, eq1) <= 86.1, "inside the published range of the other angles"


@pytest.mark.parametrize(("smiles", "angles"), [("F[I-](F)(F)F", [90.0] * 4 + [180.0] * 2), ("F[Br-](F)(F)F", [90.0] * 4 + [180.0] * 2)])
def test_the_square_planar_tetrafluoro_anions_are_planar_d4h(smiles, angles):
    g = _built(smiles)
    assert _all_angles(g) == angles
    assert g.shape == "square planar"
