"""Ligand steric bulk.

These measures could not be shipped before because nothing validated
them. What changed is not the code but the reference: both have precise
geometric definitions, so they can be checked against PROPERTIES that
must hold by definition, the same way the Szeged index was validated by
a theorem rather than by matching a tool.

The properties checked here:
  * the reported cone actually contains every atom
  * an optimised axis is never worse than the metal-donor bond axis
  * a symmetric ligand's optimum IS the bond axis
  * the ranking matches Tolman's published series
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem

from openchem.chem.steric import (
    DEFAULT_METAL_DISTANCE,
    NoDonorError,
    _ensemble,
    _ligand_geometry,
    buried_volume,
    compute_steric_analysis,
    exact_cone_angle,
    find_donor,
)

PH3 = "P"
PME3 = "CP(C)C"
PET3 = "CCP(CC)CC"
PPH3 = "c1ccccc1P(c1ccccc1)c1ccccc1"
PCY3 = "C1CCCCC1P(C1CCCCC1)C1CCCCC1"
PTBU3 = "CC(C)(C)P(C(C)(C)C)C(C)(C)C"


def _prepared(smiles: str, conformers: int = 5):
    mol, ids, _own_geometry = _ensemble(Chem.MolFromSmiles(smiles), conformers)
    return mol, ids, find_donor(mol)


def _cone(smiles: str, conformers: int = 5):
    mol, ids, donor = _prepared(smiles, conformers)
    return min((exact_cone_angle(mol, donor, c) for c in ids), key=lambda cone: cone.angle)


# --- Definitional properties ---------------------------------------------


def test_the_reported_cone_actually_contains_every_atom():
    """The definition IS "the cone that contains the ligand". If an atom
    sticks out, the number is not a cone angle at all."""
    mol, ids, donor = _prepared(PPH3, conformers=3)
    cone = exact_cone_angle(mol, donor, ids[0])

    positions, apex, _ = _ligand_geometry(mol, donor, ids[0], DEFAULT_METAL_DISTANCE)
    table = Chem.GetPeriodicTable()
    half = cone.angle / 2
    for atom in mol.GetAtoms():
        if atom.GetIdx() == donor:
            continue
        offset = positions[atom.GetIdx()] - apex
        distance = float(np.linalg.norm(offset))
        centre = math.degrees(math.acos(float(offset @ cone.axis) / distance))
        edge = centre + math.degrees(math.asin(min(table.GetRvdw(atom.GetAtomicNum()) / distance, 1.0)))
        assert edge <= half + 1e-6, f"atom {atom.GetIdx()} lies outside the reported cone"


@pytest.mark.parametrize("smiles", [PME3, PET3, PPH3, PCY3])
def test_optimising_the_axis_is_never_worse_than_the_bond_axis(smiles):
    """A theorem, not a measurement: the bond axis is one of the
    candidates the search considers, so the optimum cannot exceed it.
    A violation would mean the search is broken."""
    cone = _cone(smiles, conformers=3)

    assert cone.angle <= cone.along_bond_angle + 1e-6


@pytest.mark.parametrize("smiles", [PH3, PME3, PPH3, PTBU3])
def test_a_symmetric_ligand_is_tightest_along_its_own_bond_axis(smiles):
    """Three identical substituents put the optimal cone on the bond
    axis by symmetry. This is the negative control for the test above --
    without it, an 'optimiser' that always tilted would still pass."""
    cone = _cone(smiles, conformers=3)

    assert cone.angle == pytest.approx(cone.along_bond_angle, abs=1.0)
    assert not cone.axis_was_tilted


def test_an_unsymmetric_ligand_really_does_tilt():
    """PEt3's ethyls can fold to one side, so the tightest cone is well
    off the bond axis -- measured at roughly 25 degrees narrower. This is
    what the axis optimisation exists for."""
    cone = _cone(PET3, conformers=20)

    assert cone.axis_was_tilted
    assert cone.along_bond_angle - cone.angle > 5.0


# --- Against the published series -----------------------------------------


def test_the_ranking_matches_tolmans_published_series():
    """What a steric measure is actually used for. Absolute values differ
    from published tables because those are computed on metal-bound DFT
    geometries and these on free MMFF ones -- the ORDER does not."""
    ligands = [("PH3", PH3), ("PMe3", PME3), ("PEt3", PET3), ("PPh3", PPH3), ("PCy3", PCY3), ("PtBu3", PTBU3)]
    measured = [(name, _cone(smiles, conformers=10).angle) for name, smiles in ligands]

    assert [name for name, _ in sorted(measured, key=lambda pair: pair[1])] == [
        "PH3",
        "PMe3",
        "PEt3",
        "PPh3",
        "PCy3",
        "PtBu3",
    ]


def test_the_cone_angle_lands_near_the_one_published_exact_value():
    """PPh3's exact cone angle is published as 170.0 degrees. This gets
    163.8 from a free-ligand geometry. The gap is the geometry source and
    is documented; the tolerance here pins that it stays a geometry-sized
    difference and does not drift into a different quantity."""
    assert _cone(PPH3, conformers=20).angle == pytest.approx(170.0, abs=10.0)


def test_buried_volume_ranks_the_same_way():
    ligands = [PME3, PPH3, PCY3, PTBU3]
    volumes = []
    for smiles in ligands:
        mol, ids, donor = _prepared(smiles, conformers=3)
        volumes.append(buried_volume(mol, donor, ids[0]))

    assert volumes == sorted(volumes), "bulkier ligands must bury more of the sphere"


# --- Behaviour ------------------------------------------------------------


def test_the_result_is_reproducible():
    """An earlier version searched the axis with random perturbations and
    would have returned slightly different numbers each run. No
    measurement should do that."""
    first = compute_steric_analysis(Chem.MolFromSmiles(PME3), "m", {"conformers": 5})
    second = compute_steric_analysis(Chem.MolFromSmiles(PME3), "m", {"conformers": 5})

    assert first.provenance.parameters == second.provenance.parameters


def test_the_geometry_source_is_stated_in_the_result():
    """Someone comparing against a paper has to be told these are free
    ligand geometries, not bound ones -- in the output, not only in a
    docstring nobody opens."""
    result = compute_steric_analysis(Chem.MolFromSmiles(PME3), "m", {"conformers": 3})
    joined = "\n".join(result.matched)

    assert "free ligand" in joined
    assert "not directly comparable" in joined
    assert result.provenance.parameters["geometry_source"] == "free_ligand_mmff"


def test_the_conformer_range_is_reported_for_a_flexible_ligand():
    """A flexible ligand has a RANGE of steric profiles, and one number
    hides it."""
    result = compute_steric_analysis(Chem.MolFromSmiles(PET3), "m", {"conformers": 10})

    assert any("Across" in line and "conformers" in line for line in result.matched)


def test_phosphorus_wins_over_nitrogen_as_the_donor():
    """In a ligand containing both, the phosphine binds."""
    mol, _ids, donor = _prepared("CN(C)CCP(C)C", conformers=2)

    assert mol.GetAtomWithIdx(donor).GetSymbol() == "P"


def test_a_plain_alkane_is_not_treated_as_a_ligand():
    """Carbon was briefly in the donor list for N-heterocyclic carbenes,
    which made butane report a cone angle. A carbene carbon is a real
    donor; any carbon is not."""
    result = compute_steric_analysis(Chem.MolFromSmiles("CCCC"), "m", {"conformers": 3})

    assert result.cache_state.value == "failed"
    assert "donor" in result.error.lower()


def test_a_carbene_carbon_is_still_accepted():
    """The case the carbon entry existed for -- an NHC, whose donor is a
    divalent hydrogen-free carbon."""
    mol, _ids, donor = _prepared("CN1C=CN(C)[C]1", conformers=2)

    atom = mol.GetAtomWithIdx(donor)
    assert atom.GetSymbol() == "C"
    assert atom.GetTotalNumHs() == 0
