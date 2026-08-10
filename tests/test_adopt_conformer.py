"""The way back from the 3D viewer to the 2D editor.

Structures only ever went one way -- "Send to 3D Viewer Tab" has existed
since the viewer did, and nothing came back. Reported as "there doesn't
seem to be an easy way to directly copy a conformer from our 3d viewer
back into the 2d editor still".

**Every test here is aimed at a defect that was MEASURED in a working
first version of the feature, not at restating the code.** The first
version pushed the conformer's molblock through `EditStructureCommand`,
which is the obvious implementation and is wrong three separate ways:

    aspirin as drawn                 13 atoms   CC(=O)Oc1ccccc1C(=O)O
    a conformer                      21 atoms   (embedded after AddHs)
    after adopting it naively        21 atoms   [H]OC(=O)c1c([H])c([H])...

    cholesterol, closest heavy-atom approach in the drawing
      proper depiction                1.500
      the conformer's own x,y         0.219     <- atoms on top of each other

    conformer count, pressing the button        1 -> 0
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import canonical_conformer
from openchem.commands.conformer_commands import AdoptConformerCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus

#: Deliberately NOT flat. A planar molecule projects to a usable drawing
#: by accident, so a test built on aspirin alone passes against the naive
#: implementation and proves nothing about the one that shipped.
CHOLESTEROL = "CC(C)CCCC(C)C1CCC2C1(C)CCC1C2CC=C2CC(O)CCC12C"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"

#: The molecule this was reported broken on -- a benzobicyclo[2.2.2]
#: octane, C17H25NO2. Its two -CH2CH2- bridges superimpose exactly when
#: the drawing follows the 3D orientation.
REPORTED = "COc1cc(C[C@@H](C)N)c2c(c1OC)C1CCC2CC1"


@pytest.fixture(scope="module")
def engine():
    return build_service_container().chemistry_engine


def _molecule(engine, smiles: str) -> MoleculeModel:
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, smiles)
    return molecule


def _conformer_molblock(engine, molecule: MoleculeModel) -> str:
    """A real embedded conformer, with the explicit hydrogens it carries.

    Through the real provider rather than a fixture string, because the
    explicit hydrogens ARE the thing under test -- a hand-written
    heavy-atom molblock would quietly remove the defect.
    """
    from openchem.chem.conformer_providers import RDKitConformerProvider

    provider = RDKitConformerProvider(random_seed=0xC0FFEE)
    mol = engine.mol_from_molblock(molecule.molblock)
    results = provider.generate_conformers(mol, num_conformers=1, optimize=True)
    return engine.mol_to_molblock(results[0][0])


def _atom_count(molblock: str) -> int:
    return int(molblock.splitlines()[3][:3])


def _closest_approach(molblock: str) -> float:
    """Smallest x,y gap between any two atoms -- how readable the drawing is."""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conf = mol.GetConformer()
    points = [conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
    return min(
        math.hypot(points[i].x - points[j].x, points[i].y - points[j].y)
        for i in range(len(points))
        for j in range(i + 1, len(points))
    )


# --- the drawing the conformer becomes ---------------------------------------


def test_the_drawing_does_not_gain_the_conformers_explicit_hydrogens(engine):
    """THE FIRST DEFECT. A conformer is embedded after `Chem.AddHs`, so
    aspirin's carries 21 atoms against the 13 that were drawn.

    Adopting those makes the drawing a different structure to everything
    that compares one -- and `select_calculation_input` records that
    eight of the 49 registered calculators return a different number for
    a molecule carrying explicit hydrogens.
    """
    molecule = _molecule(engine, ASPIRIN)
    conformer = _conformer_molblock(engine, molecule)
    assert _atom_count(conformer) == 21, "the fixture stopped carrying explicit hydrogens"

    drawing = engine.drawing_from_conformer(conformer)

    assert _atom_count(drawing.molblock) == 13


def test_the_canonical_smiles_survives_being_redrawn(engine):
    """The consequence of the above, stated as the thing that actually
    matters: the molecule must still be the same molecule.

    Asserted separately from the atom count because they can come apart
    -- a drawing could keep 13 atoms and still lose a bond order.
    """
    molecule = _molecule(engine, ASPIRIN)
    before = molecule.canonical_smiles

    drawing = engine.drawing_from_conformer(_conformer_molblock(engine, molecule))

    assert engine.molblock_to_smiles(drawing.molblock) == before


def test_the_drawing_is_laid_out_rather_than_projected(engine):
    """THE SECOND DEFECT, and the reason a flat molecule cannot test it.

    Taking the conformer's own x and y puts two of cholesterol's heavy
    atoms 0.219 units apart where a real depiction has 1.500 -- on top of
    each other, so the canvas is unusable for exactly the molecules whose
    3D geometry is worth having.

    The assertion is against the molecule's OWN ordinary depiction rather
    than a constant: "as readable as RDKit would have drawn it anyway" is
    the claim, and a fixed threshold would silently encode aspirin's
    bond length instead.
    """
    molecule = _molecule(engine, CHOLESTEROL)
    conformer = _conformer_molblock(engine, molecule)

    projected = _closest_approach(Chem.MolToMolBlock(Chem.RemoveHs(
        Chem.MolFromMolBlock(conformer, removeHs=False)
    )))
    drawn = engine.drawing_from_conformer(conformer)

    assert projected < 0.5, "cholesterol's projection stopped overlapping -- re-derive this"
    assert _closest_approach(drawn.molblock) >= _closest_approach(molecule.molblock) * 0.75
    assert drawn.follows_geometry


# --- the shape that has no flat orientation ----------------------------------


def test_a_symmetric_bridge_falls_back_to_a_readable_layout(engine):
    """THE DEFECT REPORTED FROM THE RUNNING APP, as "it didn't really do
    anything" on a benzobicyclo[2.2.2]octane.

    Viewed down the bridgehead-to-bridgehead axis of a bicyclo[2.2.2]
    system the two bridges superimpose EXACTLY, so a depiction that
    follows the 3D orientation draws the bridge underneath itself. The
    structure then reads as a plain fused bicyclic, and RDKit logs
    "ambiguous stereochemistry - overlapping neighbors" -- which is what
    named this in the user's log.

    Measured closest approach of the oriented layout: **0.000**. Two
    atoms at identical coordinates.
    """
    molecule = _molecule(engine, REPORTED)
    conformer = _conformer_molblock(engine, molecule)

    drawing = engine.drawing_from_conformer(conformer)

    assert not drawing.follows_geometry, "the degenerate layout was accepted"
    # And what came back is genuinely readable, not merely flagged.
    assert _closest_approach(drawing.molblock) > 0.5


def test_the_degenerate_layout_really_is_degenerate(engine):
    """Asserts the DEFECT, so this stops being a workaround if RDKit ever
    starts laying these out sensibly -- the same reason the Open Babel
    element test asserts Open Babel's own bug.

    Without it, the guard above would keep passing on a fallback that had
    become unnecessary, and nobody would know.
    """
    from rdkit.Chem import AllChem

    molecule = _molecule(engine, REPORTED)
    heavy = Chem.RemoveHs(
        Chem.MolFromMolBlock(_conformer_molblock(engine, molecule), removeHs=False)
    )
    oriented = Chem.Mol(heavy)
    AllChem.GenerateDepictionMatching3DStructure(oriented, heavy)

    assert _closest_approach(Chem.MolToMolBlock(oriented)) < 0.01


def test_the_readable_layout_threshold_sits_between_the_two_populations(engine):
    """A constant with two measured bounds is not a taste question.

    Across 29 molecules the ratio is sharply bimodal: five symmetric
    bridges at 0.000, then tropinone 0.239 and morphine 0.392, then a
    0.41-wide gap, then camphor 0.799 and twenty at 1.000. Any value in
    [0.40, 0.79] separates them identically, so leaving that window is a
    decision rather than a tweak -- and this fails naming it.
    """
    from openchem.chem.engine import READABLE_LAYOUT_FRACTION

    assert 0.40 <= READABLE_LAYOUT_FRACTION <= 0.79


def test_a_fused_polycycle_still_keeps_its_orientation(engine):
    """The fallback must not swallow the feature.

    A test that only checked the bridged case would pass just as happily
    against a `drawing_from_conformer` that had given up and always
    returned a plain layout -- which is the whole feature gone. Morphine
    and strychnine are polycyclic and NOT degenerate; cholesterol keeps
    its orientation at ratio 1.000.
    """
    molecule = _molecule(engine, CHOLESTEROL)

    drawing = engine.drawing_from_conformer(_conformer_molblock(engine, molecule))

    assert drawing.follows_geometry


# --- the command -------------------------------------------------------------


def test_adopting_keeps_the_conformers(engine):
    """THE THIRD DEFECT, and the one that was visible in the running app.

    `EditStructureCommand` clears the conformer set on redo, correctly,
    because a structure edit invalidates geometries computed for the old
    structure. Adopting edits no structure. Measured on the first
    version, which used it: the count went 1 -> 0, and
    `MoleculeViewer3DWidget._refresh_view` answers an empty list by
    clearing the backend and disabling the button -- so the control
    blanked the viewer it lives in and discarded the set the user had
    just generated.
    """
    molecule = _molecule(engine, ASPIRIN)
    conformer = ConformerModel(molblock=_conformer_molblock(engine, molecule), energy=1.0)
    molecule.conformers = [conformer]

    AdoptConformerCommand(engine, molecule, conformer.molblock, EventBus()).redo()

    assert molecule.conformers == [conformer]


def test_adopting_is_undoable_back_to_the_original_drawing(engine):
    molecule = _molecule(engine, ASPIRIN)
    before = molecule.molblock
    command = AdoptConformerCommand(
        engine, molecule, _conformer_molblock(engine, molecule), EventBus()
    )

    command.redo()
    changed = molecule.molblock
    command.undo()

    assert changed != before, "redo did not change the drawing at all"
    assert molecule.molblock == before


def test_redo_after_undo_restores_the_same_drawing(engine):
    """An undo/redo pair must not hand back a different layout from the
    one the user accepted -- a change nobody asked for, arriving through
    the undo stack of all places.

    **What this catches is the SOURCE, not the timing**, and the
    difference was established by mutation rather than assumed. Deriving
    the drawing inside `redo` from `self._molecule.molblock` -- i.e. from
    whatever is current, which after an undo is the ORIGINAL drawing --
    is caught here. Deriving it inside `redo` from the conformer is an
    equivalent mutation: RDKit's depiction is deterministic for a fixed
    input, so it produces the identical bytes and no test can tell the
    two apart. Building it in the constructor is therefore a statement
    of intent rather than something this guards.
    """
    molecule = _molecule(engine, ASPIRIN)
    command = AdoptConformerCommand(
        engine, molecule, _conformer_molblock(engine, molecule), EventBus()
    )

    command.redo()
    first = molecule.molblock
    command.undo()
    command.redo()

    assert molecule.molblock == first


def test_adopting_does_not_change_which_geometry_a_calculation_uses(engine):
    """Stated as a test because "adopt" reads like it should mean more.

    `canonical_conformer` picks the LOWEST MMFF energy, not a position in
    the list, and export and every `GEOMETRY` calculator go through it.
    So the answer is the same before and after -- and if that ever stops
    being true, it is a policy change that should be made deliberately
    rather than discovered.
    """
    molecule = _molecule(engine, ASPIRIN)
    conformer_molblock = _conformer_molblock(engine, molecule)
    low = ConformerModel(molblock=conformer_molblock, energy=1.0)
    high = ConformerModel(molblock=conformer_molblock, energy=99.0)
    molecule.conformers = [low, high]

    # Adopt the one that is NOT the lowest, which is the case that could
    # tell a position-based policy from an energy-based one.
    AdoptConformerCommand(engine, molecule, high.molblock, EventBus()).redo()

    assert canonical_conformer(molecule) is low
