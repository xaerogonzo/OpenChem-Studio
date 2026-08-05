"""Getting a structure in and out of the clipboard.

There was previously no way to copy a drawn structure into another
molecule at all -- the reported workflow was "I drew aziridine and wanted
to make azirine from it, and had to redraw it".
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_clipboard import MAX_CLIPBOARD_CHARS, parse_structure_text
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel


def _smiles_of(molblock: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromMolBlock(molblock))


@pytest.mark.parametrize(
    ("label", "text", "expected_format", "expected_smiles"),
    [
        ("bare smiles", "CCO", "SMILES", "CCO"),
        ("smiles with surrounding space", "  C1CN1  ", "SMILES", "C1CN1"),
        # The .smi convention is "SMILES<whitespace>name", so a line copied
        # out of one must not be rejected for having a name on it.
        ("smiles then a name", "CCO ethanol", "SMILES", "CCO"),
        ("stereochemistry survives", "C[C@H](N)C(=O)O", "SMILES", "C[C@H](N)C(=O)O"),
        ("inchi", "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3", "InChI", "CCO"),
    ],
)
def test_recognises(label, text, expected_format, expected_smiles):
    parsed = parse_structure_text(text)
    assert parsed is not None, label
    assert parsed.source_format == expected_format
    assert _smiles_of(parsed.molblock) == expected_smiles


def test_recognises_a_molfile():
    molblock = Chem.MolToMolBlock(Chem.MolFromSmiles("c1ccccc1"))
    parsed = parse_structure_text(molblock)
    assert parsed is not None
    assert parsed.source_format == "molfile"
    assert _smiles_of(parsed.molblock) == "c1ccccc1"


@pytest.mark.parametrize(
    ("label", "text"),
    [
        ("empty", ""),
        ("whitespace", "   \n  "),
        ("prose", "Please find the compound attached to this email."),
        ("junk", "!!! not a molecule !!!"),
    ],
)
def test_refuses(label, text):
    assert parse_structure_text(text) is None, label


def test_refuses_something_far_too_long_to_be_one_structure():
    """Guards against handing a pasted document to three parsers in turn,
    which is a way to freeze the window rather than a paste.

    NOT a parametrize case: pytest builds the test id out of the argument,
    and a 100,000-character id overruns the Windows path limit when it is
    used for the cache directory -- the run errors before the test itself
    is reached.
    """
    assert parse_structure_text("C" * (MAX_CLIPBOARD_CHARS + 1)) is None


def test_pasted_structures_are_laid_out():
    """A structure with no coordinates must not paste as a heap on the origin.

    Asserted as "no two atoms share a position", which is the property a
    layout actually has. Counting atoms away from the origin was tried
    first and is wrong twice over: the first atom line reads
    `0.0000 0.0000 0.0000` in a perfectly good layout (something has to be
    at the origin), and RDKit does not guarantee that exactly one atom
    lands there.
    """
    parsed = parse_structure_text("CC(=O)Oc1ccccc1C(=O)O")
    assert parsed is not None
    mol = Chem.MolFromMolBlock(parsed.molblock)
    conformer = mol.GetConformer()
    positions = [
        (round(conformer.GetAtomPosition(i).x, 4), round(conformer.GetAtomPosition(i).y, 4))
        for i in range(mol.GetNumAtoms())
    ]
    assert len(set(positions)) == len(positions)


def test_a_molfile_of_all_zero_coordinates_is_laid_out():
    """The case `_has_usable_coordinates` actually exists for.

    Found by mutation testing: deleting the `Compute2DCoords` call did not
    fail a single test, because `MolToMolBlock` computes coordinates
    itself when a molecule has NO conformer -- so every from-SMILES path
    was covered by RDKit rather than by us. It does not do so when a
    conformer is present but zeroed, which some SDF exports produce, and
    that is the only input where this code does any work at all.
    """
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    from rdkit.Chem import AllChem

    AllChem.Compute2DCoords(mol)
    conformer = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        conformer.SetAtomPosition(i, (0.0, 0.0, 0.0))
    flattened = Chem.MolToMolBlock(mol)

    parsed = parse_structure_text(flattened)
    assert parsed is not None
    result = Chem.MolFromMolBlock(parsed.molblock)
    result_conformer = result.GetConformer()
    positions = {
        (round(result_conformer.GetAtomPosition(i).x, 4), round(result_conformer.GetAtomPosition(i).y, 4))
        for i in range(result.GetNumAtoms())
    }
    assert len(positions) == result.GetNumAtoms()


def test_a_molfile_keeps_the_coordinates_it_arrived_with():
    """Someone else's layout is not ours to recompute."""
    mol = Chem.MolFromSmiles("CCO")
    from rdkit.Chem import AllChem

    AllChem.Compute2DCoords(mol)
    original = Chem.MolToMolBlock(mol)
    parsed = parse_structure_text(original)
    assert parsed is not None
    assert parsed.molblock.splitlines()[4:7] == original.splitlines()[4:7]


def test_unique_molecule_name_only_numbers_on_collision():
    project = ProjectModel(name="p")
    assert project.unique_molecule_name("New molecule") == "New molecule"
    project.molecules.append(MoleculeModel(display_name="New molecule"))
    assert project.unique_molecule_name("New molecule") == "New molecule 2"
    project.molecules.append(MoleculeModel(display_name="New molecule 2"))
    assert project.unique_molecule_name("New molecule") == "New molecule 3"
    # An unrelated name is untouched -- this only prevents the application
    # from generating collisions, it does not police what users type.
    assert project.unique_molecule_name("Aziridine") == "Aziridine"


def test_a_duplicated_structure_is_independent_of_its_original():
    """Editing the copy must not reach back into the molecule it came from."""
    engine = ChemistryEngine()
    original = MoleculeModel(display_name="Aziridine")
    engine.set_structure_from_smiles(original, "C1CN1")

    copy = MoleculeModel(display_name="Aziridine copy")
    engine.set_structure_from_molblock(copy, original.molblock)
    engine.set_structure_from_smiles(copy, "C1=NC1")

    assert original.canonical_smiles == "C1CN1"
    assert copy.canonical_smiles == "C1=NC1"
