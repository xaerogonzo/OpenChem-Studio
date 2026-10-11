"""The torsion table: which bonds, which four atoms, which angle.

What is guarded:

* **the bonds are exactly the ones the Rotatable Bonds count counts.** The table's definition is written
  out as a SMARTS pattern because RDKit exposes no list of the bonds it counts; the parity test below
  is what holds the two together, over a corpus and in both the drawing's form (implicit hydrogens)
  and a conformer's (explicit ones), which change every atom's degree;
* **the angle is the angle**, against shapes whose dihedral is known: anti-butane is 180, a planar
  biphenyl-free arrangement is 0 or 180, a constructed geometry is whatever it was built with;
* **the four atoms are named and chosen by a rule that does not depend on atom order.**
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors

from openchem.chem.torsions import Torsion, compute_torsion_table, rotatable_bonds, torsions

_PANEL = Path(__file__).parent / "fixtures" / "census_panel.toml"

_CORPUS = re.findall(r'smiles\s*=\s*"([^"]+)"', _PANEL.read_text(encoding="utf-8")) + """
CCCCCCCC CC(C)Cc1ccc(cc1)C(C)C(=O)O CC(=O)Oc1ccccc1C(=O)O CC(=O)Nc1ccc(O)cc1 CN1C=NC2=C1C(=O)N(C)C(=O)N2C
c1ccc(cc1)-c1ccccc1 CC#CC CCC#CCC C#CCC FC(F)(F)CC ClC(Cl)(Cl)CC CC(C)(C)CC CC(C)(C)c1ccccc1 O=C(N)CCC NC(=O)NCC CNC(=O)OCC
CC(=O)N(C)CC NC(=N)NCC CC(=[NH2+])NCC CS(=O)(=O)NCC CCS(=O)(=O)CC OCCOCCO CC(C)Oc1ccccc1 COc1ccc(cc1)C=CC(=O)O
CCN(CC)CC c1ccccc1C(=O)NC c1ccccc1NC(=O)C C1CCCCC1CC C1CCC(CC1)C2CCCCC2 O=C1CCCN1CC CC(=O)OCC CCOC(=O)CCC(=O)OCC
CCc1ccc2ccccc2c1 CN(C)C(=O)c1ccccc1 CCSCC CCSSCC C=CCC C=CC=CC CC(=O)C(C)=O NCCN OCCO CCCl CCBr
CC(C)CC(C)C CN1CCC23C4C1CC5=C2C(=C(C=C5)O)OC3C(C=C4)O Clc1ccc(cc1)C(c1ccccc1)N1CCN(CC1)CCOCCO
O=C(O)c1ccccc1O CC1=CC(=O)C=CC1=O N#CCC [O-][N+](=O)CC [NH3+]CC(=O)[O-] CC(C)(C)OC(=O)NCC
c1ccc2c(c1)[nH]c1ccccc12 CCOc1ccc(NC(C)=O)cc1 CC(N)C(=O)NC(C)C(=O)O C[N+](C)(C)CC""".split()


def _conformer(smiles: str, seed: int = 7) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _built(positions: list[tuple[float, float, float]], symbols: str = "CCCC") -> Chem.Mol:
    """A chain of atoms at exact coordinates, so a dihedral has an exact answer."""
    editable = Chem.RWMol()
    for symbol in symbols:
        editable.AddAtom(Chem.Atom(symbol))
    for index in range(len(symbols) - 1):
        editable.AddBond(index, index + 1, Chem.BondType.SINGLE)
    conformer = Chem.Conformer(len(symbols))
    for index, position in enumerate(positions):
        conformer.SetAtomPosition(index, position)
    conformer.Set3D(True)
    editable.AddConformer(conformer)
    mol = editable.GetMol()
    Chem.SanitizeMol(mol)
    return mol


# --- which bonds: held to RDKit's own count ----------------------------------------------------------


def test_the_corpus_is_large_enough_to_mean_something():
    assert len(_CORPUS) >= 80


@pytest.mark.parametrize("smiles", _CORPUS)
def test_the_listed_bonds_are_exactly_as_many_as_the_rotatable_bonds_count(smiles):
    drawing = Chem.MolFromSmiles(smiles)
    assert drawing is not None
    want = rdMolDescriptors.CalcNumRotatableBonds(drawing)

    assert len(rotatable_bonds(drawing)) == want, "on the drawing (implicit hydrogens)"
    assert len(rotatable_bonds(Chem.AddHs(drawing))) == want, "on a conformer (explicit hydrogens)"


def test_the_bonds_are_the_same_atoms_in_both_forms():
    """The count could agree by accident; the atoms must too, once the hydrogens are numbered past the heavy ones."""
    drawing = Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O")

    assert rotatable_bonds(Chem.AddHs(drawing)) == rotatable_bonds(drawing)


def test_a_terminal_methyl_is_not_rotatable_though_a_conformer_gives_it_four_neighbours():
    assert rotatable_bonds(Chem.AddHs(Chem.MolFromSmiles("CC"))) == []
    assert len(rotatable_bonds(Chem.AddHs(Chem.MolFromSmiles("CCC")))) == 0
    assert len(rotatable_bonds(Chem.AddHs(Chem.MolFromSmiles("CCCC")))) == 1


@pytest.mark.parametrize(
    "smiles, expected",
    [
        ("C1CCCCC1", 0),  # a ring bond is never rotatable
        ("CC#CC", 0),  # a triple bond's neighbours are collinear
        ("CC(=O)NC", 0),  # the amide C-N, which RDKit treats as rigid
        ("FC(F)(F)CC", 0),  # trifluoromethyl
        ("c1ccccc1-c1ccccc1", 1),  # the biaryl bond
    ],
)
def test_the_named_exclusions_and_inclusions(smiles, expected):
    assert len(rotatable_bonds(Chem.AddHs(Chem.MolFromSmiles(smiles)))) == expected


# --- the angle -------------------------------------------------------------------------------------------


def test_anti_butane_is_180():
    (only,) = torsions(_conformer("CCCC", seed=3))
    assert -180.0 < only.angle <= 180.0, "a real conformer has some dihedral in range"
    anti = _built([(0, 1, 0), (0, 0, 0), (1.5, 0, 0), (1.5, -1, 0)])
    assert torsions(anti)[0].angle == pytest.approx(180.0, abs=1e-6)


@pytest.mark.parametrize("degrees", [0.0, 60.0, 90.0, 120.0, -60.0, -120.0, 179.0])
def test_a_built_dihedral_is_read_back(degrees):
    radians = math.radians(degrees)
    mol = _built([(0, 1, 0), (0, 0, 0), (1.5, 0, 0), (1.5, math.cos(radians), math.sin(radians))])

    assert torsions(mol)[0].angle == pytest.approx(degrees, abs=1e-6)


def test_syn_is_zero_and_the_range_is_minus_180_exclusive_to_180_inclusive():
    syn = _built([(0, 1, 0), (0, 0, 0), (1.5, 0, 0), (1.5, 1, 0)])

    assert torsions(syn)[0].angle == pytest.approx(0.0, abs=1e-9)
    for found in (torsions(_conformer(smiles)) for smiles in ("CCCCCC", "CCOCCO", "CC(C)Cc1ccc(cc1)C(C)C(=O)O")):
        assert all(-180.0 < t.angle <= 180.0 for t in found)


def test_the_angle_does_not_depend_on_how_the_molecule_is_turned_or_moved():
    mol = _conformer("CCCCO")
    want = [t.angle for t in torsions(mol)]
    rng = np.random.default_rng(4)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    moved = Chem.Mol(mol)
    positions = np.array(moved.GetConformer().GetPositions()) @ q.T + np.array([3.0, -2.0, 7.0])
    for index, position in enumerate(positions):
        moved.GetConformer().SetAtomPosition(index, position.tolist())

    assert [t.angle for t in torsions(moved)] == pytest.approx(want, abs=1e-6)


def test_the_mirror_image_has_the_opposite_sign():
    mol = _conformer("CC(F)(Cl)CCO")
    mirrored = Chem.Mol(mol)
    for index, position in enumerate(mirrored.GetConformer().GetPositions()):
        mirrored.GetConformer().SetAtomPosition(index, (-position[0], position[1], position[2]))

    for original, reflected in zip(torsions(mol), torsions(mirrored)):
        assert reflected.angle == pytest.approx(-original.angle if abs(original.angle) != 180.0 else 180.0, abs=1e-6)


# --- which four atoms -------------------------------------------------------------------------------------------


def test_the_atoms_are_a_chain_bonded_end_to_end():
    mol = _conformer("CC(C)Cc1ccc(cc1)C(C)C(=O)O")

    for torsion in torsions(mol):
        a, b, c, d = torsion.atoms
        assert mol.GetBondBetweenAtoms(a, b) and mol.GetBondBetweenAtoms(b, c) and mol.GetBondBetweenAtoms(c, d)
        assert len({a, b, c, d}) == 4


def test_the_outer_atoms_are_the_heaviest_neighbours_not_hydrogens():
    mol = _conformer("CCCO")

    for torsion in torsions(mol):
        a, _b, _c, d = torsion.atoms
        assert mol.GetAtomWithIdx(a).GetAtomicNum() > 1 and mol.GetAtomWithIdx(d).GetAtomicNum() > 1


def test_the_choice_does_not_change_when_the_atoms_are_renumbered():
    base = Chem.MolFromSmiles("OCC(C)CCl")
    shuffled = Chem.RenumberAtoms(base, [4, 0, 5, 2, 1, 3])
    results = []
    for mol in (base, shuffled):
        conformed = _conformer(Chem.MolToSmiles(mol), seed=11)
        results.append(sorted(tuple(sorted(conformed.GetAtomWithIdx(i).GetSymbol() for i in t.atoms)) for t in torsions(conformed)))

    assert results[0] == results[1]


# --- refusals ----------------------------------------------------------------------------------------------------------


def test_a_structure_with_no_conformer_is_refused_with_the_way_out():
    report = compute_torsion_table(Chem.MolFromSmiles("CCCC"), "m", {})

    assert report.cache_state.name == "FAILED"
    assert "3D conformer" in report.error and "Generate Conformers" in report.error


def test_flat_two_d_coordinates_are_refused_too():
    flat = Chem.MolFromSmiles("CCCC")
    AllChem.Compute2DCoords(flat)

    assert compute_torsion_table(flat, "m", {}).cache_state.name == "FAILED"


# --- the report -----------------------------------------------------------------------------------------------------------


def test_the_report_has_a_count_and_one_fact_per_bond_with_units():
    mol = _conformer("CC(C)Cc1ccc(cc1)C(C)C(=O)O")
    report = compute_torsion_table(mol, "m", {})
    count, *rows = report.facts

    assert count.label == "Rotatable bonds" and int(count.value) == len(rows)
    assert len(rows) == rdMolDescriptors.CalcNumRotatableBonds(Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O")) == 4
    assert all(row.units == "deg" and row.label.startswith("Torsion ") for row in rows)


def test_each_row_names_its_four_atoms_by_the_numbers_on_the_canvas():
    mol = _conformer("CCCC")
    (row,) = compute_torsion_table(mol, "m", {}).facts[1:]

    assert row.label == "Torsion C1-C2-C3-C4"


def test_the_decimal_places_are_honoured_and_the_value_keeps_full_precision():
    mol = _conformer("CCCC")
    value = compute_torsion_table(mol, "m", {"decimal_places": 4}).facts[1]
    short = compute_torsion_table(mol, "m", {"decimal_places": 0}).facts[1]

    assert len(value.display_value.split(".")[1]) == 4 and "." not in short.display_value
    assert value.value == pytest.approx(float(value.display_value), abs=1e-4)


def test_every_row_says_how_it_was_measured_and_that_it_is_one_conformer():
    row = compute_torsion_table(_conformer("CCCC"), "m", {}).facts[1]
    text = " ".join(row.limitations)

    assert "heaviest neighbour" in text and "not a scan" in text


def test_a_molecule_with_nothing_rotatable_still_answers():
    report = compute_torsion_table(_conformer("c1ccccc1"), "m", {})

    assert report.cache_state.name != "FAILED"
    assert [f.label for f in report.facts] == ["Rotatable bonds"] and report.facts[0].display_value == "0"
