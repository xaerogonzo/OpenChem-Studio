"""A geometry can define stereochemistry a drawing left open. Say so, or refuse.

Reported as two separate things that turned out to be one: adopting a
conformer changed what molecule the project held, and the naming panel
then withheld a name that had not changed.

    as drawn         [(6, 'R'), (14, '?'), (17, '?')]
    after adopting   [(6, 'R'), (14, 'S'), (17, 'S')]

**The nomenclature engine was innocent** -- it derives the same name for
both, that name cannot express bridgehead stereo, and only the round-trip
comparison changed its mind.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.engine import ChemistryEngine
from openchem.chem.stereochemistry import (
    StereochemistryConflict,
    compare_stereochemistry,
)

#: The reported molecule: a benzobicyclo[2.2.2]octane whose bridgeheads
#: are unspecified flat and assignable in 3D.
REPORTED = "COc1cc(C[C@@H](C)N)c2c(c1OC)C1CCC2CC1"
R_ALANINE = "C[C@@H](N)C(=O)O"
S_ALANINE = "C[C@H](N)C(=O)O"


@pytest.fixture(scope="module")
def engine():
    return ChemistryEngine()


def _drawn(engine, smiles: str) -> Chem.Mol:
    return engine.mol_from_molblock(engine.mol_to_molblock(engine.mol_from_smiles(smiles)))


def _embedded(engine, mol: Chem.Mol) -> Chem.Mol:
    working = Chem.AddHs(Chem.Mol(mol))
    AllChem.EmbedMolecule(working, randomSeed=42)
    AllChem.MMFFOptimizeMolecule(working)
    stripped = Chem.RemoveHs(working)
    Chem.AssignStereochemistryFrom3D(stripped)
    return stripped


# --- the four outcomes -------------------------------------------------------


def test_a_geometry_that_defines_open_centres_is_safe_but_not_quiet(engine):
    """THE REPORTED CASE. Committing is right -- the geometry is real --
    but doing it silently is not, because the molecule became more
    specific than the user drew it."""
    drawn = _drawn(engine, REPORTED)

    change = compare_stereochemistry(drawn, _embedded(engine, drawn))

    assert [entry[1] for entry in change.newly_assigned] == [14, 17]
    assert change.safe, "a geometry defining open centres must not be refused"
    assert not change.quiet, "it must not be committed silently either"
    assert "2 stereocentres" in change.describe()


def test_changing_an_assigned_centre_is_NEVER_safe(engine):
    """**The important one.** An explicitly drawn R that comes back S is a
    different compound, and no status line makes committing it
    acceptable."""
    change = compare_stereochemistry(
        engine.mol_from_smiles(R_ALANINE), engine.mol_from_smiles(S_ALANINE)
    )

    assert change.reassigned == (("atom", 1, "R", "S"),)
    assert not change.safe
    assert "CHANGE" in change.describe()


def test_losing_an_assigned_centre_is_never_safe(engine):
    """Perception going BACKWARDS after a transform is a bug, not a
    result -- so it is refused rather than reported as 'unchanged'."""
    resolved = engine.mol_from_smiles(R_ALANINE)
    flattened = Chem.Mol(resolved)
    Chem.RemoveStereochemistry(flattened)

    change = compare_stereochemistry(resolved, flattened)

    assert change.lost == (("atom", 1, "R"),)
    assert not change.safe


def test_an_unchanged_structure_is_quiet(engine):
    """However far the atoms moved. A rigid motion is not a chemical
    event and must not produce a message."""
    change = compare_stereochemistry(
        engine.mol_from_smiles(R_ALANINE), engine.mol_from_smiles(R_ALANINE)
    )

    assert change.quiet
    assert change.describe() == ""


def test_two_different_molecules_are_not_comparable_and_not_safe(engine):
    """A per-index comparison across different graphs would produce a
    confident, wrong verdict. Incomparable counts as unsafe, because it
    means something larger than coordinates moved."""
    change = compare_stereochemistry(
        engine.mol_from_smiles(R_ALANINE), engine.mol_from_smiles("CCO")
    )

    assert not change.comparable
    assert not change.safe
    assert change.newly_assigned == ()


def test_double_bond_geometry_counts_too(engine):
    """E/Z is stereochemistry a geometry can define just as an sp3 centre
    is, and it reads differently to a chemist -- so it is counted
    separately rather than folded into 'stereocentres'."""
    change = compare_stereochemistry(
        engine.mol_from_smiles("CC=CC"), engine.mol_from_smiles("C/C=C/C")
    )

    assert change.newly_assigned and change.newly_assigned[0][0] == "bond"
    assert "double bond" in change.describe()


# --- the command refuses, rather than the window apologising -----------------


def test_adopting_a_conformer_that_would_flip_a_centre_is_REFUSED(engine):
    """Refused in the CONSTRUCTOR, so nothing reaches the undo stack.

    Built by handing the command a conformer of the opposite enantiomer,
    which is the shape of the failure even though the real path cannot
    normally produce it -- the guard has to hold whatever produced the
    geometry.
    """
    from openchem.commands.conformer_commands import AdoptConformerCommand
    from openchem.domain.molecule import MoleculeModel
    from openchem.events.base import EventBus

    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, R_ALANINE)
    wrong_hand = _embedded(engine, engine.mol_from_smiles(S_ALANINE))

    with pytest.raises(StereochemistryConflict, match="CHANGE"):
        AdoptConformerCommand(
            engine, molecule, engine.mol_to_molblock(wrong_hand), EventBus()
        )


def test_adopting_a_conformer_of_the_same_molecule_is_allowed(engine):
    """The other direction, so a refusal that always fires cannot pass."""
    from openchem.commands.conformer_commands import AdoptConformerCommand
    from openchem.domain.molecule import MoleculeModel
    from openchem.events.base import EventBus

    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, REPORTED)
    conformer = _embedded(engine, engine.mol_from_molblock(molecule.molblock))

    command = AdoptConformerCommand(
        engine, molecule, engine.mol_to_molblock(conformer), EventBus()
    )

    assert command.stereo is not None
    assert command.stereo.safe
    assert not command.stereo.quiet, "the reported case must still be reported"
