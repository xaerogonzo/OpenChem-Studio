from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.nmr_correlation import compute_cosy_pairs, compute_hmbc_pairs, compute_hsqc_pairs


def _propanal() -> Chem.Mol:
    # CH3(0)-CH2(1)-CHO(2)=O(3), H4-6 on C0, H7-8 on C1, H9 (aldehyde) on C2.
    mol = Chem.AddHs(Chem.MolFromSmiles("CCC=O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    return mol


def _pairs(cross_peaks):
    return {(cp.atom_a, cp.atom_b) for cp in cross_peaks}


def test_hsqc_is_only_one_bond_h_c_pairs():
    mol = _propanal()
    shifts = {atom.GetIdx(): float(atom.GetIdx()) for atom in mol.GetAtoms()}

    pairs = _pairs(compute_hsqc_pairs(mol, shifts))

    assert pairs == {(4, 0), (5, 0), (6, 0), (7, 1), (8, 1), (9, 2)}


def test_hmbc_excludes_the_directly_bonded_carbon_the_aldehyde_h_is_verified_against():
    """Regression test for the specific distinction HMBC exists to make:
    the aldehyde proton (9, on C2) must correlate to C1 and C0 (2-3 bonds
    away) but NOT to C2 (1 bond -- that's HSQC's territory)."""
    mol = _propanal()
    shifts = {atom.GetIdx(): float(atom.GetIdx()) for atom in mol.GetAtoms()}

    pairs = _pairs(compute_hmbc_pairs(mol, shifts))

    aldehyde_h_correlations = {b for a, b in pairs if a == 9}
    assert aldehyde_h_correlations == {0, 1}
    assert (9, 2) not in pairs


def test_cosy_covers_geminal_and_vicinal_h_h_pairs():
    mol = _propanal()
    shifts = {atom.GetIdx(): float(atom.GetIdx()) for atom in mol.GetAtoms()}

    pairs = _pairs(compute_cosy_pairs(mol, shifts))

    # Geminal (2-bond): the 3 CH3 protons pairwise, and the 2 CH2 protons.
    assert (4, 5) in pairs and (4, 6) in pairs and (5, 6) in pairs
    assert (7, 8) in pairs
    # Vicinal (3-bond): CH3<->CH2, and CH2<->aldehyde H.
    assert (4, 7) in pairs and (5, 8) in pairs
    assert (7, 9) in pairs and (8, 9) in pairs
    # 4+ bonds apart (CH3 to aldehyde H) must NOT appear.
    assert (4, 9) not in pairs and (5, 9) not in pairs and (6, 9) not in pairs


def test_correlations_only_include_atoms_with_a_shift():
    mol = _propanal()
    # Only the aldehyde H (9) and its carbon (2) have a shift -- nothing
    # else should be considered even though it's bonded correctly.
    shifts = {9: 10.0, 2: 200.0}

    assert _pairs(compute_hsqc_pairs(mol, shifts)) == {(9, 2)}
