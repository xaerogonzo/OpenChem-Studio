"""Molblock counts and charges: unavailable values are None, never zero."""

from __future__ import annotations

from openchem.chem.engine import ChemistryEngine
from openchem.chem.molblock_summary import summarize_molblock
from openchem.domain.molecule import MoleculeModel


def test_absent_molblock_is_not_an_empty_neutral_molecule():
    engine = ChemistryEngine()
    summary = summarize_molblock(engine, None, with_coordinates=True)
    assert summary["present"] is False
    assert summary["parse_ok"] is None
    assert summary["atom_count"] is None
    assert summary["heavy_atom_count"] is None
    assert summary["net_formal_charge"] is None
    assert summary["has_3d_coordinates"] is None
    assert summary["z_span_angstrom"] is None


def test_unparsable_molblock_does_not_look_neutral():
    engine = ChemistryEngine()
    summary = summarize_molblock(engine, "not a molfile")
    assert summary["present"] is True
    assert summary["parse_ok"] is False
    assert summary["atom_count"] is None
    assert summary["net_formal_charge"] is None


def test_drawing_counts_include_explicit_hydrogens_separately_from_heavy_atoms():
    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="water")
    engine.set_structure_from_smiles(molecule, "O")
    summary = summarize_molblock(engine, molecule.molblock)
    assert summary["parse_ok"] is True
    assert summary["heavy_atom_count"] == 1
    assert summary["atom_count"] == summary["heavy_atom_count"] + summary["explicit_hydrogen_count"]
    assert summary["net_formal_charge"] == 0
