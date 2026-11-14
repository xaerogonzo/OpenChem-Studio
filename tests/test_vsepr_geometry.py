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
    ("Cl[Sb](Cl)(Cl)(Cl)Cl", "AX5", "trigonal bipyramidal", 2.338, 2.277),
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
        symbol = f"[{centre}{'-' if charge < 0 else '+' if charge > 0 else ''}{abs(charge) if abs(charge) > 1 else ''}]"
        if reference.slots or "=" in ligand:
            import re

            tokens = [t for t, _ in reference.slots] if reference.slots else re.findall(r"[A-Z][a-z]?=?", ligand)
            smiles = symbol + "".join(f"(={t[:-1]})" if t.endswith("=") else f"([H])" if t == "H" else f"({t})" for t in tokens)
        else:
            smiles = f"{ligand}{symbol}" + "".join(f"({ligand})" for _ in range(n - 1))
        # a core with a carbon or hydrogen ligand is grown by `chem.vsepr_graft` and needs a molecule RDKit reads (a methyl brings its own hydrogens)
        grown = any(t in ("C", "H") for t in (tokens if (reference.slots or "=" in ligand) else []))
        mol = Chem.MolFromSmiles(smiles) if grown else _mol(smiles)
        outcome = build_vsepr_geometry(mol)
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
    ["O=S(=O)(O)O", "O=[Xe](=O)(=O)=O", "[O-][Cl](=O)(=O)=O", "O=P(Cl)(Cl)Cl", "FS(F)(F)(F)(F)F"],
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


def test_xeo3_is_a_trigonal_pyramid_with_the_published_mean_distance_and_angle():
    """Templeton 1963: mean Xe-O 1.76 A and O-Xe-O 103 degrees; the three angles are equal by the template, a fact of the shape."""
    g = _built("O=[Xe](=O)=O")
    assert (g.classification, g.shape) == ("AX3E", "trigonal pyramidal")
    p, c = g.coordinates, g.centre_index
    for i in g.ligand_indices:
        assert _bond(p, c, i) == pytest.approx(1.76, abs=1e-6)
    assert _all_angles(g) == [103.0] * 3
    # the centre sits above the plane of the three oxygens (a pyramid, not a planar triangle): the oxygens are on one side of the centre
    points = np.array([p[i] for i in g.ligand_indices])
    assert np.all(np.dot(points - np.array(p[c]), np.mean(points, axis=0)) > 0.0)
    assert abs(np.linalg.det(np.array([points[1] - points[0], points[2] - points[0], np.array(p[c]) - points[0]]))) > 0.1, "not coplanar with the centre"


def test_bro2f_is_a_pyramid_with_the_adducts_separate_double_and_single_bond_lengths():
    """Seppelt 2019 (3 BrO2F.4 acetone, 100 K), Table S4 of the Supporting Information: Br=O 1.587 to 1.620 and Br-F 1.781 to 1.822 A, each inside its printed range, O-Br-O 107.4 and
    O-Br-F 99.8 and 100.3; the mean distance is the 1.674 A that the disordered pure crystal (Hwang 1997) could only give as one average, an independent check of the pair."""
    smiles = "FBr(=O)=O"
    g = _built(smiles)
    assert (g.classification, g.shape) == ("AX3E", "trigonal pyramidal")
    p, c = g.coordinates, g.centre_index
    oxygens = _by_element(g, smiles, "O")
    fluorine = _by_element(g, smiles, "F")
    assert len(oxygens) == 2 and len(fluorine) == 1
    assert all(1.587 <= _bond(p, c, i) <= 1.620 for i in oxygens)
    assert 1.781 <= _bond(p, c, fluorine[0]) <= 1.822
    mean = sum(_bond(p, c, i) for i in g.ligand_indices) / 3
    assert mean == pytest.approx(1.674, abs=0.0075), "the disordered crystal's one measured mean (167.4 (0.6) pm)"
    o1, o2 = oxygens
    assert _angle(p, o1, c, o2) == pytest.approx(107.4, abs=1e-6)
    assert _angle(p, o1, c, fluorine[0]) == pytest.approx(100.05, abs=1e-6)
    assert _angle(p, o2, c, fluorine[0]) == pytest.approx(100.05, abs=1e-6)
    assert 99.8 <= _angle(p, o1, c, fluorine[0]) <= 100.3, "inside the two printed O-Br-F angles"


def test_a_pyramid_the_table_lacks_is_still_left_to_the_ordinary_path():
    """Sulfite, chlorate, bromate and a trioxide have oxo ligands and no recorded geometry: not this module's."""
    for smiles in ("O=S(=O)=O", "[O-]Cl(=O)=O", "O=Cl(=O)F"):
        outcome = build_vsepr_geometry(_mol(smiles))
        assert outcome.kind in (Kind.NOT_APPLICABLE, Kind.UNSUPPORTED), smiles
        assert outcome.kind is not Kind.BUILT


def test_pcl2f3_has_the_chlorines_equatorial_and_the_three_published_lengths():
    """French et al. 1985: rg P-F axial 1.593, P-F equatorial 1.546, P-Cl 2.004 A; the chlorines sit in the equatorial plane."""
    smiles = "FP(F)(F)(Cl)Cl"
    g = _built(smiles)
    p, c = g.coordinates, g.centre_index
    chlorines = _by_element(g, smiles, "Cl")
    assert len(chlorines) == 2 and all(i in g.equatorial_indices for i in chlorines)
    assert all(_bond(p, c, i) == pytest.approx(2.004, abs=1e-6) for i in chlorines)
    fluorines = _by_element(g, smiles, "F")
    assert sorted(round(_bond(p, c, i), 3) for i in fluorines) == [1.546, 1.593, 1.593]
    axial_fluorines = [i for i in fluorines if i in g.axial_indices]
    assert len(axial_fluorines) == 2 and _angle(p, axial_fluorines[0], c, axial_fluorines[1]) == pytest.approx(180.0, abs=1e-6)


def test_xef6_model_reproduces_the_papers_nonbonded_distances_it_was_not_given():
    """Bartell and Gavin 1968, Table II, Model C (C3v), Analysis I: the F...F distances are NOT inputs; the bond lengths and the two triple angles are.

    Long triple mutual 2.939, short triple mutual 2.652, adjacent long-short 2.525 and the three trans pairs 3.765 A (rg; shrinkage 0.002 to 0.003 A).
    """
    g = _built("F[Xe](F)(F)(F)(F)F")
    assert (g.classification, g.shape) == ("AX6E", "C3v distorted octahedron")
    p, c = g.coordinates, g.centre_index
    long_triple, short_triple = g.axial_indices, g.equatorial_indices
    assert all(_bond(p, c, i) == pytest.approx(1.912, abs=1e-6) for i in long_triple)
    assert all(_bond(p, c, i) == pytest.approx(1.862, abs=1e-6) for i in short_triple)
    aa = [_bond(p, i, j) for i, j in itertools.combinations(long_triple, 2)]
    bb = [_bond(p, i, j) for i, j in itertools.combinations(short_triple, 2)]
    cross = sorted(_bond(p, i, j) for i in long_triple for j in short_triple)
    assert aa == pytest.approx([2.939] * 3, abs=0.01)
    assert bb == pytest.approx([2.652] * 3, abs=0.01)
    assert cross[:6] == pytest.approx([2.525] * 6, abs=0.02), "the six adjacent long-short contacts"
    assert cross[6:] == pytest.approx([3.765] * 3, abs=0.02), "each long bond has a short one trans to it"
    # the long bonds are the ones around the lone pair's side: that triple is the more open one
    assert _angle(p, long_triple[0], c, long_triple[1]) > _angle(p, short_triple[0], c, short_triple[1])
    assert "MODEL" in g.reference.method


# --- the evidence tier: an estimate is never presented as a measurement ----------------------------------------


def test_every_row_has_a_known_evidence_tier_and_the_unmeasured_ones_say_so_in_their_method():
    from openchem.chem.vsepr_geometry import EVIDENCE_PHRASES

    tiers = {r.key: r.evidence for r in REFERENCES.values()}
    assert set(tiers.values()) <= set(EVIDENCE_PHRASES)
    for reference in REFERENCES.values():
        if reference.evidence != "measured":
            assert reference.evidence.upper() in reference.method.upper() or reference.method.startswith(("MODEL", "CALCULATED", "ESTIMATED")), reference.key
    assert {k: v for k, v in tiers.items() if v != "measured"} == {
        ("Xe", "F", 6, 0): "model",
        ("Cl", "F", 5, 0): "estimated",
        ("I", "F", 5, -2): "calculated",
    }


@pytest.mark.parametrize(
    ("smiles", "phrase"),
    [
        ("F[Xe](F)(F)(F)(F)F", "MODEL"),
        ("F[I-2](F)(F)(F)F", "CALCULATED"),
        ("FP(F)(Cl)(Cl)Cl", "measured"),
        ("FCl(F)(F)(F)F", "ESTIMATED"),
        ("FS(F)(F)(F)(F)F", "measured"),
    ],
)
def test_the_geometry_and_the_conformer_note_state_how_well_the_numbers_are_known(smiles, phrase):
    outcome = build_vsepr_geometry(_mol(smiles))
    assert outcome.kind is Kind.BUILT, outcome.reason
    assert phrase in outcome.geometry.provenance
    from openchem.chem.conformer_providers import _template_search

    assert phrase in _template_search(_mol(smiles)).geometry_note


def test_tef7_anion_is_a_pentagonal_bipyramid_with_the_axial_bonds_shorter():
    g = _built("F[Te-](F)(F)(F)(F)(F)F")
    assert (g.classification, g.shape) == ("AX7", "pentagonal bipyramidal")
    p, c = g.coordinates, g.centre_index
    assert all(_bond(p, c, i) == pytest.approx(1.8276, abs=1e-6) for i in g.axial_indices), "the two axial lengths of the labelled CIF (ROLSOA), 1.8249 and 1.8303"
    assert all(_bond(p, c, i) == pytest.approx(1.8820, abs=1e-6) for i in g.equatorial_indices), "the five equatorial lengths of the CIF, 1.8705 to 1.8975"
    assert _angle(p, *g.axial_indices[:1], c, g.axial_indices[1]) == pytest.approx(180.0, abs=1e-6)
    equatorial_angles = sorted(round(_angle(p, i, c, j), 1) for i, j in itertools.combinations(g.equatorial_indices, 2))
    assert equatorial_angles == [72.0] * 5 + [144.0] * 5


def test_if5_dianion_is_a_regular_planar_pentagon_at_the_calculated_length():
    g = _built("F[I-2](F)(F)(F)F")
    assert (g.classification, g.shape) == ("AX5E2", "pentagonal planar")
    assert _all_angles(g) == sorted([72.0] * 5 + [144.0] * 5)
    assert all(_bond(g.coordinates, g.centre_index, i) == pytest.approx(2.11, abs=1e-6) for i in g.ligand_indices)
    assert g.reference.evidence == "calculated"


def test_pcl3f2_has_the_fluorines_axial_and_the_measured_lengths():
    """Macho et al. 1986 Table VIII (gas electron diffraction): P-F axial 1.596 (2), P-Cl equatorial 2.005 (3) A, D3h."""
    smiles = "FP(F)(Cl)(Cl)Cl"
    g = _built(smiles)
    p, c = g.coordinates, g.centre_index
    fluorines = _by_element(g, smiles, "F")
    assert all(i in g.axial_indices for i in fluorines)
    assert all(_bond(p, c, i) == pytest.approx(1.596, abs=1e-6) for i in fluorines)
    assert all(_bond(p, c, i) == pytest.approx(2.005, abs=1e-6) for i in _by_element(g, smiles, "Cl"))
    assert _all_angles(g) == [90.0] * 6 + [120.0] * 3 + [180.0]
    assert g.reference.evidence == "measured"



# --- an organic group on a hypervalent centre: the core from the table, the groups grown on it (`chem.vsepr_graft`) -------------------------------


def _grafted(smiles: str):
    outcome = build_vsepr_geometry(Chem.MolFromSmiles(smiles))
    assert outcome.kind is Kind.BUILT, outcome.reason
    return outcome


def _implausible_bonds(outcome) -> list[tuple[int, int, float]]:
    """Bonds that are not a plausible length: the graft must not stretch or crush what it grows."""
    points = np.array(outcome.geometry.coordinates)
    bad = []
    for b in outcome.molecule.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        if outcome.geometry.centre_index in (i, j):
            continue  # the core's own bonds are the table's (an iodine bond is 2.1 to 2.5 A) and are checked against it
        d = float(np.linalg.norm(points[i] - points[j]))
        if not 0.95 <= d <= 1.95:
            bad.append((i, j, round(d, 2)))
    return bad


def test_ph3pf2_core_is_the_crystals_and_every_atom_is_there():
    outcome = _grafted("FP(F)(c1ccccc1)(c1ccccc1)c1ccccc1")
    g, mol = outcome.geometry, outcome.molecule
    assert mol.GetNumAtoms() == 36, "1 P, 2 F, 18 ring carbons and 15 hydrogens: none missing"
    assert [a.GetSymbol() for a in mol.GetAtoms()].count("H") == 15
    p, c = g.coordinates, g.centre_index
    fluorines = [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == "F"]
    carbons = [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == "C"]
    assert all(_bond(p, c, i) == pytest.approx(1.664, abs=1e-6) for i in fluorines)
    assert all(_bond(p, c, i) == pytest.approx(1.8225, abs=1e-6) for i in carbons)
    assert _angle(p, fluorines[0], c, fluorines[1]) == pytest.approx(180.0, abs=1e-6)
    assert sorted(round(_angle(p, i, c, j), 1) for i, j in itertools.combinations(carbons, 2)) == [120.0] * 3
    assert all(round(_angle(p, f, c, k), 1) == 90.0 for f in fluorines for k in carbons)
    assert g.reference.evidence == "measured"


def test_the_grown_phenyl_rings_are_real_rings_and_do_not_clash():
    outcome = _grafted("FP(F)(c1ccccc1)(c1ccccc1)c1ccccc1")
    points = np.array(outcome.geometry.coordinates)
    mol = outcome.molecule
    assert _implausible_bonds(outcome) == []
    for ring in mol.GetRingInfo().AtomRings():
        centre = points[list(ring)].mean(axis=0)
        normal = np.linalg.svd(points[list(ring)] - centre)[2][2]
        assert max(abs(float(np.dot(points[i] - centre, normal))) for i in ring) < 0.05, "each ring is planar"
        assert all(1.33 < _bond(points, ring[k], ring[(k + 1) % 6]) < 1.45 for k in range(6))
    topological = Chem.GetDistanceMatrix(mol)
    distances = np.linalg.norm(points[:, None] - points[None], axis=2)
    assert distances[(topological > 2)].min() > 1.8, "no two atoms that are not near neighbours are on top of each other"


def test_the_grown_conformers_differ_and_keep_the_core_exactly():
    outcome = _grafted("FP(F)(c1ccccc1)(c1ccccc1)c1ccccc1")
    assert outcome.alternatives, "the three rings can turn: more than one conformer"
    first = np.array(outcome.geometry.coordinates)
    assert any(np.abs(np.array(other) - first).max() > 0.5 for other in outcome.alternatives)
    core = [outcome.geometry.centre_index, *outcome.geometry.ligand_indices]
    for other in outcome.alternatives:
        assert np.allclose(np.array(other)[core], first[core], atol=1e-9), "the core is the table's in every conformer"


@pytest.mark.parametrize(
    ("smiles", "atoms"),
    [("CP(C)(F)(F)F", 12), ("CP(F)(F)(F)F", 9), ("FP(F)([H])([H])[H]", 6)],
)
def test_methyl_and_hydrogen_ligands_get_their_hydrogens_and_are_measured(smiles, atoms):
    """(CH3)2PF3 and CH3PF4 (gas electron diffraction) and PH3F2 (rotation-vibration spectra)."""
    outcome = _grafted(smiles)
    assert outcome.molecule.GetNumAtoms() == atoms
    assert outcome.geometry.reference.evidence == "measured"
    assert _implausible_bonds(outcome) == []


def test_a_methyl_ligand_on_the_phenyl_row_or_a_phenyl_on_the_methyl_row_is_an_estimate():
    """The CCCFF row was measured for phenyls: trimethyldifluorophosphorane takes it by transfer and says so; so does the CCFFF row for a phenyl."""
    outcome = _grafted("CP(C)(C)(F)F")
    assert outcome.geometry.reference.evidence == "estimated" and "ESTIMATED" in outcome.geometry.provenance
    assert "ESTIMATED" in outcome.geometry.reference.method


def test_methylphosphorane_core_reproduces_the_published_gas_phase_lengths():
    outcome = _grafted("CP(C)(F)(F)F")
    g, mol = outcome.geometry, outcome.molecule
    p, c = g.coordinates, g.centre_index
    carbons = [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == "C"]
    fluorines = [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == "F"]
    assert all(_bond(p, c, i) == pytest.approx(1.798, abs=1e-6) for i in carbons)
    assert sorted(round(_bond(p, c, i), 4) for i in fluorines) == [1.553, 1.643, 1.643]
    assert all(i in g.equatorial_indices for i in carbons), "the methyls are equatorial, as the electron diffraction found"


def test_a_hypervalent_organic_with_no_row_keeps_the_ordinary_path():
    """Ordinary molecules, a phosphine, a sulfoxide and a sulfonamide are not hypervalent organics with a core: unchanged behaviour, not a refusal."""
    for smiles in ("CCO", "c1ccccc1P(c1ccccc1)c1ccccc1", "CS(C)=O", "O=S(=O)(c1ccccc1)N"):
        assert build_vsepr_geometry(Chem.MolFromSmiles(smiles)).kind is Kind.NOT_APPLICABLE, smiles



def _core_ligands(outcome, symbol):
    mol = outcome.molecule
    return [i for i in outcome.geometry.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == symbol]


def test_phenyliodine_diacetate_core_reproduces_the_crystals_angles_and_has_every_atom():
    """Alcock 1979 (-60 C): I-O 2.156 (mean), I-C 2.090 A, O-I-O 164.0 and O-I-C 81.4 and 82.6; the angles are the published ones."""
    smiles = "CC(=O)OI(OC(C)=O)c1ccccc1"
    outcome = _grafted(smiles)
    g, mol = outcome.geometry, outcome.molecule
    p, c = g.coordinates, g.centre_index
    assert mol.GetNumAtoms() == 26, "C10H11IO4: every hydrogen is there"
    oxygens, carbon = _core_ligands(outcome, "O"), _core_ligands(outcome, "C")[0]
    assert all(_bond(p, c, i) == pytest.approx(2.156, abs=1e-6) for i in oxygens)
    assert _bond(p, c, carbon) == pytest.approx(2.090, abs=1e-6)
    assert _angle(p, oxygens[0], c, oxygens[1]) == pytest.approx(164.0, abs=1e-6)
    assert all(81.4 - 0.01 <= _angle(p, o, c, carbon) <= 82.6 + 0.01 for o in oxygens), "inside the two published O-I-C angles"
    assert g.reference.evidence == "measured" and _implausible_bonds(outcome) == []
    assert all(i in g.axial_indices for i in oxygens) and carbon in g.equatorial_indices


def test_phenyliodine_dichloride_core_reproduces_the_crystals_lengths_and_angle():
    """Poynder 2021 CIF (100 K): I-Cl 2.5059 and 2.4832, I-C 2.0977 A, Cl-I-Cl 176.701 and C-I-Cl 88.900 and 88.035 degrees."""
    outcome = _grafted("ClI(Cl)c1ccccc1")
    g, mol = outcome.geometry, outcome.molecule
    p, c = g.coordinates, g.centre_index
    assert mol.GetNumAtoms() == 14
    chlorines, carbon = _core_ligands(outcome, "Cl"), _core_ligands(outcome, "C")[0]
    assert all(_bond(p, c, i) == pytest.approx(2.4946, abs=1e-6) for i in chlorines)
    assert _bond(p, c, carbon) == pytest.approx(2.0977, abs=1e-6)
    assert _angle(p, chlorines[0], c, chlorines[1]) == pytest.approx(176.701, abs=0.3), "implied by the mean 88.47 each; the crystal's 176.701 is inside 0.3"
    assert all(88.035 - 0.01 <= _angle(p, i, c, carbon) <= 88.900 + 0.01 for i in chlorines)


def test_aryl_sf5_core_is_an_umbrella_octahedron_inside_the_published_ranges():
    """Du 2016 (the nine deposited crystals' own means) and Espiet 2020: S-F axial 1.568 to 1.607, S-F equatorial 1.572 to 1.618, S-C 1.785 to 1.823 A, C-S-F equatorial 91.3 to 93.5, C-S-F axial 178.9 to 180."""
    outcome = _grafted("FS(F)(F)(F)(F)c1ccccc1")
    g, mol = outcome.geometry, outcome.molecule
    p, c = g.coordinates, g.centre_index
    assert mol.GetNumAtoms() == 17
    carbon = _core_ligands(outcome, "C")[0]
    fluorines = _core_ligands(outcome, "F")
    assert _bond(p, c, carbon) == pytest.approx(1.8036, abs=1e-6) and 1.785 <= _bond(p, c, carbon) <= 1.823
    lengths = sorted(round(_bond(p, c, i), 4) for i in fluorines)
    assert lengths == [1.5859, 1.5859, 1.5859, 1.5859, 1.5868] and all(1.568 <= x <= 1.618 for x in lengths)
    angles = sorted(round(_angle(p, carbon, c, i), 1) for i in fluorines)
    assert angles[-1] == 180.0 and all(a == pytest.approx(92.35, abs=0.06) for a in angles[:4]) and 91.3 <= 92.35 <= 93.5
    assert g.reference.evidence == "measured" and _implausible_bonds(outcome) == []


@pytest.mark.parametrize(
    ("smiles", "tier"),
    [
        ("FS(F)(F)(F)(F)c1ccccc1", "measured"),
        ("CS(F)(F)(F)(F)F", "estimated"),
        ("CC(=O)OI(OC(C)=O)c1ccccc1", "measured"),
        ("CC(=O)OI(OC(C)=O)C", "estimated"),
        ("OI(O)c1ccccc1", "estimated"),
        ("ClI(Cl)c1ccccc1", "measured"),
        ("ClI(Cl)C", "estimated"),
        ("FI(F)c1ccccc1", "measured"),
        ("FI(F)C", "estimated"),
        ("FI(F)(F)(F)c1ccc(F)cc1", "measured"),
    ],
)
def test_the_reagent_cores_are_measured_only_for_the_kind_of_ligand_that_was_measured(smiles, tier):
    assert _grafted(smiles).geometry.reference.evidence == tier



def test_ph3f2_drawn_with_explicit_hydrogens_is_built_too():
    """A drawing carries a hydrogen on phosphorus only as an atom: written that way the molecule is a bare five-ligand star and takes the table's PH3F2 row directly."""
    params = Chem.SmilesParserParams()
    params.removeHs = False
    mol = Chem.MolFromSmiles("FP(F)([H])([H])[H]", params)
    assert mol.GetNumAtoms() == 6
    outcome = build_vsepr_geometry(mol)
    assert outcome.kind is Kind.BUILT, outcome.reason
    g = outcome.geometry
    p, c = g.coordinates, g.centre_index
    hydrogens = [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == "H"]
    fluorines = [i for i in g.ligand_indices if mol.GetAtomWithIdx(i).GetSymbol() == "F"]
    assert all(_bond(p, c, i) == pytest.approx(1.394, abs=1e-6) for i in hydrogens)
    assert all(_bond(p, c, i) == pytest.approx(1.6468, abs=1e-6) for i in fluorines)
    assert _angle(p, fluorines[0], c, fluorines[1]) == pytest.approx(180.0, abs=1e-6)


def test_aryl_iodine_difluoride_core_is_a_t_with_the_fluorines_axial_and_bent_toward_the_carbon():
    """Ye 2005, Sarie 2017, Haefliger 2019, Bailly 2000 and Floerke 2013 (twelve free molecules, six crystals): I-F 2.0052, I-C 2.0846 A, F-I-F 172.1 (169.0 to 174.4), C-I-F 86.1 (83.3 to 88.2)."""
    outcome = _grafted("FI(F)c1ccccc1")
    g, mol = outcome.geometry, outcome.molecule
    p, c = g.coordinates, g.centre_index
    assert mol.GetNumAtoms() == 14, "C6H5F2I: every hydrogen is there"
    fluorines, carbon = _core_ligands(outcome, "F"), _core_ligands(outcome, "C")[0]
    assert all(_bond(p, c, i) == pytest.approx(2.0052, abs=1e-6) for i in fluorines)
    assert _bond(p, c, carbon) == pytest.approx(2.0846, abs=1e-6)
    assert 169.0 <= _angle(p, fluorines[0], c, fluorines[1]) <= 174.4
    assert all(83.3 <= _angle(p, f, c, carbon) <= 88.2 for f in fluorines)
    assert g.reference.evidence == "measured" and _implausible_bonds(outcome) == []
    assert all(i in g.axial_indices for i in fluorines) and carbon in g.equatorial_indices


def test_aryl_iodine_tetrafluoride_core_is_a_square_pyramid_with_the_carbon_apical():
    """Haefliger 2019, Hoyer 2004 and Frohn 1995 (four molecules, three crystals): I-C 2.0821 apical, I-F 1.9270 basal, C-I-F 84.77."""
    outcome = _grafted("FI(F)(F)(F)c1ccc(F)cc1")
    g, mol = outcome.geometry, outcome.molecule
    p, c = g.coordinates, g.centre_index
    assert mol.GetNumAtoms() == 16, "C6H4F5I"
    carbon = _core_ligands(outcome, "C")[0]
    fluorines = [i for i in _core_ligands(outcome, "F") if i in g.ligand_indices and i != carbon and _bond(p, c, i) < 2.2]
    assert len(fluorines) == 4
    assert _bond(p, c, carbon) == pytest.approx(2.0821, abs=1e-6)
    assert all(_bond(p, c, i) == pytest.approx(1.9270, abs=1e-6) for i in fluorines)
    assert all(_angle(p, carbon, c, i) == pytest.approx(84.77, abs=0.01) for i in fluorines)
    assert g.reference.evidence == "measured" and carbon in g.axial_indices and _implausible_bonds(outcome) == []
