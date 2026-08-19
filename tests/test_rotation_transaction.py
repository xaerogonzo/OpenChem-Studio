"""What a rotation in the 2D editor is allowed to change, and what it is not.

`tests/test_editor_rotation_mode.py` measures the PREVIEW against the real
Ketcher bundle -- that a drag moves atoms rigidly, fires no `change` event
and grows no history. This file measures the COMMIT: what reaches the undo
stack, the model and the conformer set once the user lets go.

**The two halves fail in opposite directions and neither sees the other.**
A preview that is perfect can still be committed as a structure edit that
clears the conformers (which is what the first version of the adopt path
did, measured 1 -> 0); and a commit that is perfect is worthless if the
canvas was showing a shape Ketcher's model did not hold.

The transaction, drawn because the boundary is the part that is easy to
get subtly wrong:

                  2D structure
                       | enter rotation
                       v
    (optional) generate --> conformer RETAINED, OUTSIDE the transaction
                       |
                    preview
                    /     \\
               cancel     commit
                  |          |
         zero structural   exactly ONE
         edits, geometry   structural edit
         restored

Generation sits deliberately outside it: cancelling a rotation must not
delete a conformer somebody legitimately generated on the way in.
"""

from __future__ import annotations

import math

import pytest
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QWidget
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import rdMolTransforms  # noqa: F401  (imported for parity with engine)

from openchem.chem.camera_orientation import determinant, rotate, rotation_from_degrees
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.ui.editor_backend import EditorBackend
from openchem.ui.widgets.molecule_editor_widget import MoleculeEditorWidget

#: An asymmetric molecule with ONE assigned stereocentre. Chirality is the
#: only property a reflection changes -- every distance survives one -- so a
#: fixture without a stereocentre cannot tell a rotation from a mirror.
ALANINE = "C[C@H](N)C(=O)O"


def _embedded(smiles: str) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.MolToMolBlock(mol)


#: What Ketcher's `getMolfile` does to a structure's scale, measured
#: against the real vendored bundle: cyclohexane loaded with C-C at 1.5301
#: A comes back at 1.0702. Every molblock these tests stage carries it,
#: because the version of them that did not was green while the shipped
#: path shrank every bond by 30%.
#: `tests/test_editor_rotation_mode.py::`
#: `test_a_round_trip_through_ketcher_preserves_the_BOND_LENGTHS` is where
#: the number comes from and is what fails if Ketcher ever changes it.
KETCHER_SCALE = 1.0702 / 1.5301


def _rotated(
    molblock: str, x_degrees: float, y_degrees: float, scale: float = KETCHER_SCALE
) -> str:
    """The molblock a drag would hand back: the same structure, turned,
    AT THE EDITOR'S SCALE.

    Through `chem/camera_orientation.py` rather than a hand-written matrix,
    because that is what the page applies -- a test with its own rotation
    maths would be checking two implementations against each other.
    """
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conformer = mol.GetConformer()
    points = [tuple(conformer.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]
    centre = [sum(axis) / len(points) for axis in zip(*points)]
    centred = [(p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]) for p in points]
    for i, (x, y, z) in enumerate(rotate(centred, rotation_from_degrees(x_degrees, y_degrees))):
        conformer.SetAtomPosition(
            i, (x * scale + centre[0], y * scale + centre[1], z * scale + centre[2])
        )
    return Chem.MolToMolBlock(mol)


class _RotatingBackend(EditorBackend):
    """Stands in for Ketcher: hands back whatever geometry is staged.

    `end_rotation` is recorded rather than acted on, because the restore
    happens on the page and the question here is whether the widget ASKS
    for it.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._widget = QWidget(parent)
        self.staged: str | None = None
        self.loaded: list[str] = []
        self.rotation_starts = 0
        self.rotation_ends: list[bool] = []
        #: What the real backend answers while its page is still loading.
        self.can_rotate = True

    def load_molblock(self, molblock: str) -> None:
        self.loaded.append(molblock)

    def get_molblock(self, callback):
        callback(self.staged)

    def set_render_option(self, name, value):
        pass

    def trigger_toolbar_action(self, action_id):
        pass

    def set_atom_tool(self, symbol, mass_number=None):
        pass

    def start_rotation(self) -> bool:
        self.rotation_starts += 1
        return self.can_rotate

    def end_rotation(self, restore: bool) -> None:
        self.rotation_ends.append(restore)

    def widget(self):
        return self._widget


@pytest.fixture(autouse=True)
def refusals(monkeypatch) -> list[str]:
    """Every refusal message, and NO modal dialog anywhere in this module.

    Not politeness: `_commit_rotation` answers a `StereochemistryConflict`
    with `QMessageBox.warning`, which blocks forever with nobody to press
    OK. A mutation run found this the hard way -- an arm that made the
    rotation improper turned four unrelated guards into a hang rather than
    a failure, and a hung arm reports nothing at all.
    """
    said: list[str] = []
    monkeypatch.setattr(
        "openchem.ui.widgets.molecule_editor_widget.QMessageBox.warning",
        lambda parent, title, text, *args, **kwargs: said.append(text),
    )
    return said


def _bond_lengths(molblock: str) -> list[float]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conformer = mol.GetConformer()
    return [
        math.dist(
            tuple(conformer.GetAtomPosition(bond.GetBeginAtomIdx())),
            tuple(conformer.GetAtomPosition(bond.GetEndAtomIdx())),
        )
        for bond in mol.GetBonds()
    ]


def _widget_with(molblock: str, conformers: list[ConformerModel] | None = None):
    engine = ChemistryEngine()
    bus = EventBus()
    stack = QUndoStack()
    backend = _RotatingBackend()
    widget = MoleculeEditorWidget(engine, bus, stack, backend=backend)
    molecule = MoleculeModel(display_name="fixture", molblock=molblock)
    engine.canonicalize(molecule)
    if conformers:
        molecule.conformers = list(conformers)
    widget.set_molecule(molecule)
    return widget, backend, molecule, stack


def _drag(widget, backend, molecule, x_degrees=35.0, y_degrees=55.0) -> None:
    """Enter the mode, stage a rotated geometry, and let go."""
    widget._rotate_button.setChecked(True)
    backend.staged = _rotated(molecule.molblock, x_degrees, y_degrees)
    backend.rotation_finished.emit()


# --- the transaction ---------------------------------------------------------


def test_a_drag_is_exactly_one_undo_step(qapp):
    """Sixty frames of preview, one entry on the stack.

    A command per frame would make undo mean "back up 1/60th of a turn",
    and the preview deliberately costs nothing -- see the `change`-event
    and history measurements in `test_editor_rotation_mode.py`.
    """
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    assert stack.count() == 0

    _drag(widget, backend, molecule)

    assert stack.count() == 1
    assert "Rotate" in stack.command(0).text()


def test_a_zero_distance_drag_is_zero_undo_steps(qapp):
    """A click that moved nothing must not leave an undo entry that
    restores what is already there -- that is worse than no entry, because
    Ctrl+Z then appears not to work.

    **STAGED AT KETCHER'S SCALE**, which is what makes this a test of the
    shipped path. The first version compared the incoming molblock with
    the model's as TEXT and staged the model's own bytes, so it passed
    against a check that in the running app is never true.
    """
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))

    widget._rotate_button.setChecked(True)
    backend.staged = _rotated(molecule.molblock, 0.0, 0.0)
    backend.rotation_finished.emit()

    assert stack.count() == 0


def test_the_editors_scale_is_restored_rather_than_committed(qapp):
    """**KETCHER NORMALISES BOND LENGTHS TO ITS OWN UNIT**, measured
    x0.6994 against the real bundle -- so a rotation committed verbatim
    shrinks every bond by 30%.

    Invisible to everything else this file checks: a uniform scale keeps
    the atom order, the fingerprint, the CIP labels and the SIGN of the
    oriented volume. Only a length or an energy sees one, which is why
    both are asserted rather than one.
    """
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    before = _bond_lengths(molecule.molblock)
    assert max(before) > 1.2, "fixture is not in Angstrom to begin with"

    _drag(widget, backend, molecule)

    after = _bond_lengths(molecule.molblock)
    assert after == pytest.approx(before, abs=0.01)


def test_cancelling_is_zero_undo_steps_and_asks_for_the_geometry_back(qapp):
    """The preview was never an edit, so there is nothing to undo -- and
    the page is told to put the entry geometry back, because leaving it
    turned would be a silent commit of the thing that was cancelled."""
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    before = molecule.molblock
    widget._rotate_button.setChecked(True)

    widget._cancel_rotation()

    assert stack.count() == 0
    assert backend.rotation_ends == [True]
    assert molecule.molblock == before
    assert not widget._rotate_button.isChecked()


def test_cancelling_keeps_a_conformer_generated_on_the_way_in(qapp):
    """**GENERATION SITS OUTSIDE THE ROLLBACK BOUNDARY.** Entering the
    mode on a flat drawing offers to generate one; cancelling the rotation
    afterwards must not throw that away. Two operations, and only one of
    them was cancelled."""
    conformer = ConformerModel(molblock=_embedded(ALANINE), energy=-12.5, method="ETKDG")
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE), [conformer])

    widget._rotate_button.setChecked(True)
    widget._cancel_rotation()

    assert [c.conformer_id for c in molecule.conformers] == [conformer.conformer_id]


def test_committing_keeps_the_conformer_set_untouched(qapp):
    """A rotation edits no structure, so the conformers are still valid --
    which is why this is not an `EditStructureCommand`. That command clears
    them on redo, correctly, and the first version of the adopt path used
    it and took the count 1 -> 0 in the running app.

    The RETAINED conformer is compared byte for byte: it is the geometry
    every `GEOMETRY` calculator reads, and rotating the drawing must not
    move it.
    """
    conformer = ConformerModel(molblock=_embedded(ALANINE), energy=-12.5, method="ETKDG")
    retained = conformer.molblock
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE), [conformer])

    _drag(widget, backend, molecule)

    assert len(molecule.conformers) == 1
    assert molecule.conformers[0].molblock == retained


def test_undo_puts_the_original_drawing_back_and_reloads_the_canvas(qapp):
    """Coordinates only, which is exactly the change
    `_on_molecule_changed` declines to reload for -- so the command has to
    say so itself, on undo as well as redo."""
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    before = molecule.molblock
    _drag(widget, backend, molecule)
    rotated = molecule.molblock
    loads_after_commit = len(backend.loaded)

    stack.undo()

    assert molecule.molblock == before != rotated
    assert len(backend.loaded) > loads_after_commit
    assert backend.loaded[-1] == before


# --- what a rotation may change ---------------------------------------------


def _fingerprint(molblock: str) -> list[tuple]:
    """Everything about a structure except where its atoms are.

    Per atom AND IN ORDER, because a permutation would look perfectly
    right on screen while attaching every coordinate to the wrong atom --
    the failure this project already hit once, when a Ketcher pool id was
    read as a molfile position.
    """
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    atoms = [
        (
            atom.GetSymbol(),
            atom.GetFormalCharge(),
            atom.GetIsotope(),
            atom.GetIsAromatic(),
            atom.GetTotalNumHs(),
            tuple(sorted(n.GetIdx() for n in atom.GetNeighbors())),
        )
        for atom in mol.GetAtoms()
    ]
    bonds = sorted(
        (bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), str(bond.GetBondType()))
        for bond in mol.GetBonds()
    )
    return [tuple(atoms), tuple(bonds)]


def test_rotation_changes_coordinates_and_nothing_else(qapp):
    """Same atoms, bonds, orders, charges, isotopes, aromaticity -- and
    the same ATOM ORDER."""
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    before = _fingerprint(molecule.molblock)
    before_coordinates = molecule.molblock

    _drag(widget, backend, molecule)

    assert molecule.molblock != before_coordinates, "nothing moved"
    assert _fingerprint(molecule.molblock) == before


def _oriented_volume(molblock: str, centre: int) -> float:
    """The signed volume of the tetrahedron at a stereocentre.

    Positive or negative is the handedness. **A reflection preserves every
    interatomic distance**, so nothing measuring geometry can see one --
    this sign is what can.
    """
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conformer = mol.GetConformer()
    atom = mol.GetAtomWithIdx(centre)
    neighbours = [n.GetIdx() for n in atom.GetNeighbors()][:4]
    assert len(neighbours) == 4, "not a tetrahedral centre"
    origin = conformer.GetAtomPosition(neighbours[0])
    vectors = [
        [
            conformer.GetAtomPosition(i).x - origin.x,
            conformer.GetAtomPosition(i).y - origin.y,
            conformer.GetAtomPosition(i).z - origin.z,
        ]
        for i in neighbours[1:]
    ]
    (a, b, c), (d, e, f), (g, h, i) = vectors
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _cip_labels(molblock: str) -> list[tuple[int, str]]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    Chem.AssignStereochemistryFrom3D(mol)
    return sorted(Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False))


def test_chirality_survives_the_rotation_on_the_molecule(qapp):
    """Three ways, because each is blind to something:

    `det(R) = +1` says the transform is a proper rotation; the oriented
    volume says THIS molecule's tetrahedron did not turn inside out; and
    the CIP label says the answer chemistry gives is unchanged. A mirrored
    transform passes every distance check ever written.
    """
    assert determinant(rotation_from_degrees(35.0, 55.0)) == pytest.approx(1.0, abs=1e-12)

    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    centre = _cip_labels(molecule.molblock)[0][0]
    before_volume = _oriented_volume(molecule.molblock, centre)
    before_labels = _cip_labels(molecule.molblock)

    _drag(widget, backend, molecule)

    after_volume = _oriented_volume(molecule.molblock, centre)
    assert math.copysign(1.0, after_volume) == math.copysign(1.0, before_volume)
    assert abs(after_volume) == pytest.approx(abs(before_volume), rel=1e-3)
    assert _cip_labels(molecule.molblock) == before_labels
    assert before_labels[0][1] in ("R", "S"), before_labels


def test_the_reflected_geometry_is_refused_out_loud(qapp, refusals):
    """The control for the test above: a transform that is NOT a rotation
    must not sail through. Mirroring z preserves every bond length and
    every angle, so only the stereochemistry check can see it -- and the
    command refuses in its constructor, before anything reaches the stack.

    **AND IT SAYS SO.** A refusal that silently drops the drag would leave
    the canvas turned and the model not, which is the worst of the three
    outcomes: the user sees a rotation that did not happen. The message is
    asserted, and the page is told to put the geometry back.
    """
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    mol = Chem.MolFromMolBlock(molecule.molblock, removeHs=False)
    conformer = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        position = conformer.GetAtomPosition(i)
        conformer.SetAtomPosition(i, (position.x, position.y, -position.z))
    before = molecule.molblock

    widget._rotate_button.setChecked(True)
    backend.staged = Chem.MolToMolBlock(mol)
    backend.rotation_finished.emit()

    assert stack.count() == 0
    assert molecule.molblock == before
    assert len(refusals) == 1, refusals
    assert "left as it was" in refusals[0], refusals[0]
    assert backend.rotation_ends == [True]


def test_a_sheared_geometry_is_refused_out_loud(qapp, refusals):
    """The other thing a wrong matrix generically is.

    **A UNIMODULAR SHEAR IS THE HARD CASE**, harder than a reflection: its
    determinant is exactly 1, so the oriented volume, every CIP label, the
    atom order and the fingerprint all survive it untouched. Nothing this
    file checks about a structure can see one -- only the distances can,
    which is what `RIGID_TOLERANCE` is for.
    """
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    mol = Chem.MolFromMolBlock(molecule.molblock, removeHs=False)
    conformer = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        position = conformer.GetAtomPosition(i)
        conformer.SetAtomPosition(
            i, (position.x + 0.05 * position.y, position.y, position.z)
        )
    before = molecule.molblock

    widget._rotate_button.setChecked(True)
    backend.staged = Chem.MolToMolBlock(mol)
    backend.rotation_finished.emit()

    assert stack.count() == 0
    assert molecule.molblock == before
    assert len(refusals) == 1, refusals
    assert "not a rotation" in refusals[0], refusals[0]


def _mmff_energy(molblock: str) -> float:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    properties = AllChem.MMFFGetMoleculeProperties(mol)
    return AllChem.MMFFGetMoleculeForceField(mol, properties).CalcEnergy()


def test_the_mmff_energy_is_unchanged_by_a_rotation(qapp):
    """A rigid motion is not a chemical operation. The tolerance is
    serialisation, not physics: a molblock holds four decimal places, so
    the coordinates that come back are not the ones that went in."""
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    before = _mmff_energy(molecule.molblock)

    _drag(widget, backend, molecule)

    assert _mmff_energy(molecule.molblock) == pytest.approx(before, abs=0.05)


# --- the mode is a mode ------------------------------------------------------


def test_with_the_mode_off_nothing_intercepts_a_drawing_edit(qapp):
    """The mode steals the drag gesture, so it must be off until asked
    for: an ordinary edit still goes through `EditStructureCommand`, and
    the page is never told to start rotating."""
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))

    backend.staged = _rotated(molecule.molblock, 20.0, 0.0)
    backend.edited.emit()

    assert backend.rotation_starts == 0
    assert stack.count() == 1
    assert "Rotate" not in stack.command(0).text()


def test_entering_the_mode_on_a_flat_drawing_asks_for_a_geometry(qapp):
    """**ROTATING A FLAT DRAWING IS NOT ROTATION** -- with every z at zero
    a turn about the vertical axis only squashes the picture. The mode
    declines to pretend, and nothing is mutated: the window is asked, and
    the button comes back up while it waits."""
    flat = Chem.MolToMolBlock(Chem.MolFromSmiles(ALANINE))
    widget, backend, molecule, stack = _widget_with(flat)
    asked: list[int] = []
    widget.geometry_requested.connect(lambda: asked.append(1))

    widget._rotate_button.setChecked(True)

    assert asked == [1]
    assert backend.rotation_starts == 0
    assert not widget._rotate_button.isChecked()
    assert stack.count() == 0


def test_a_geometry_that_arrives_lets_the_mode_be_entered(qapp):
    """**GENERATING CONFORMERS DOES NOT MAKE THE DRAWING 3D**, and this is
    the guard on the loop that fact caused.

    The conformers live beside the drawing, so a window that answered
    `geometry_requested` by generating and nothing else left the drawing
    flat -- and the next press asked exactly the same question, forever.
    Here the answer puts a geometry INTO the drawing, and the mode can
    then be entered on the same molecule that had just refused it.
    """
    widget, backend, molecule, stack = _widget_with(
        Chem.MolToMolBlock(Chem.MolFromSmiles(ALANINE))
    )
    assert not widget.has_geometry()

    # What the window does with a conformer in hand.
    widget.set_molecule(molecule)
    molecule.molblock = _embedded(ALANINE)
    widget.set_molecule(molecule)

    assert widget.has_geometry()
    widget.begin_rotation()
    assert backend.rotation_starts == 1
    assert widget._rotate_button.isChecked()


def test_an_editor_that_could_not_enter_leaves_the_button_up(qapp):
    """**A BANNER OVER A CANVAS THAT IS STILL DRAWING BONDS.**

    `window.openchemRotation` does not exist until Ketcher's page reports
    ready, so pressing the button in that window would run nothing at all
    -- while the checked button, the rulers, the live readout and the
    Cancel button all said the mode was on. A control claiming something
    the editor is not doing is the failure this whole line of work keeps
    finding, so the backend answers whether it entered and the button
    follows the answer.
    """
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    backend.can_rotate = False

    widget._rotate_button.setChecked(True)

    assert backend.rotation_starts == 1, "it should still have tried"
    assert not widget._rotate_button.isChecked()
    # `isHidden`, never `isVisible`: every child of a window nobody showed
    # reports `isVisible() == False`, so that spelling passes whatever the
    # widget does. This project has been bitten by it twice.
    assert widget._rotate_readout.isHidden()
    assert widget._rotate_cancel.isHidden()


def test_entering_the_mode_with_a_3d_drawing_starts_rotating(qapp):
    """The other half of the test above, so that a widget which asked for
    a geometry every time would fail one of them."""
    widget, backend, molecule, stack = _widget_with(_embedded(ALANINE))
    asked: list[int] = []
    widget.geometry_requested.connect(lambda: asked.append(1))

    widget._rotate_button.setChecked(True)

    assert asked == []
    assert backend.rotation_starts == 1
    assert widget._rotate_button.isChecked()
