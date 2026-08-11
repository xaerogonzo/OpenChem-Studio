from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from openchem.chem.engine import ChemistryEngine
from openchem.chem.stereochemistry import (
    StereochemistryConflict,
    compare_stereochemistry,
)
from openchem.commands.base import OpenChemCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged, MoleculeChanged


class AdoptConformerCommand(OpenChemCommand):
    """Redraw a molecule from one of its conformers.

    The way back. Structures went one way -- "Send to 3D Viewer Tab"
    exists and nothing returned -- so a conformer you had generated and
    chosen could not become the structure you were drawing on.

    **NOT `EditStructureCommand`, and the difference is the conformers.**
    That command clears them on `redo`, on the correct grounds that a
    structure edit invalidates geometries computed for the old structure.
    Adopting a conformer edits no structure: the connectivity is
    identical by construction (the conformer came from this molecule),
    so the whole set is still valid. Measured on the first version of
    this feature, which did use `EditStructureCommand`: pressing the
    button in the 3D viewer took the conformer count 1 -> 0, and
    `_refresh_view` answers an empty list by clearing the backend and
    disabling the button -- so the control blanked the very viewer it
    was pressed in and threw away the set the user had just generated.

    **What this does NOT do is change which geometry anything computes
    with.** `canonical_conformer` picks the LOWEST MMFF energy, not a
    position in the list, and export and every `GEOMETRY` calculator go
    through it -- so they already used a conformer before this command
    existed and use the same one after it. This changes the drawing.
    Saying so here because "adopt" reads like it should mean more, and a
    reader who assumes it does would be wrong in a way nothing else
    would correct.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        conformer_molblock: str,
        event_bus: EventBus,
        on_applied: Callable[[MoleculeModel], None] | None = None,
        view: Sequence[float] | None = None,
    ) -> None:
        super().__init__(f"Use conformer as the drawing for '{molecule.display_name}'")
        self._engine = engine
        self._molecule = molecule
        self._event_bus = event_bus
        self._on_applied = on_applied
        self._old_molblock = molecule.molblock
        # The geometry rather than a `ConformerModel` or an index: the
        # viewer is what knows which conformer is on screen, and an index
        # travelling to a receiver that re-reads the list is a second
        # place for the two to disagree. Same reason `FactLink` carries
        # its parameters.
        #
        # Built once, in the constructor, so a redo after an undo cannot
        # produce a DIFFERENT drawing from the one the user accepted.
        # Intent rather than a guarded property: RDKit's depiction is
        # deterministic, so deriving it in `redo` FROM THE CONFORMER is
        # an equivalent mutation and no test can catch it. Deriving it
        # from `self._molecule.molblock` -- which after an undo is the
        # original drawing -- is a real bug and is caught.
        # The molecule's own drawing goes in as the reference, so the
        # command can see what this geometry did to its stereochemistry.
        drawing = engine.drawing_from_conformer(
            conformer_molblock, view=view, reference=molecule.molblock
        )
        # **REFUSED IN THE CONSTRUCTOR, so nothing reaches the undo
        # stack.** An explicitly drawn R that embeds as S is a different
        # compound; there is no status line that makes committing it
        # acceptable. Perception going backwards -- assigned to
        # unspecified -- is refused too, because after a rigid transform
        # that is a bug rather than a result.
        if drawing.stereo is not None and not drawing.stereo.safe:
            raise StereochemistryConflict(
                f"This geometry {drawing.stereo.describe()}."
            )
        self._new_molblock = drawing.molblock
        #: False when this molecule's geometry cannot be drawn flat
        #: without atoms overlapping, so the drawing is a plain layout
        #: that says nothing about which conformer was chosen. The caller
        #: is expected to SAY so -- see `ConformerDrawing`.
        self.follows_geometry = drawing.follows_geometry
        #: True when atoms are drawn close enough to be hard to tell
        #: apart at the angle asked for. Also for the caller to say.
        self.crowded = drawing.crowded
        #: What the geometry did to the structure's stereochemistry.
        #: Safe by construction -- an unsafe one raised above -- but
        #: not necessarily quiet, and the caller is expected to say so.
        self.stereo = drawing.stereo

    def redo(self) -> None:
        self._engine.set_structure_from_molblock(self._molecule, self._new_molblock)
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))
        self._redraw()

    def undo(self) -> None:
        if self._old_molblock:
            self._engine.set_structure_from_molblock(self._molecule, self._old_molblock)
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))
        self._redraw()

    def _redraw(self) -> None:
        """Tell the canvas, because publishing does not reach it.

        `MoleculeEditorWidget._on_molecule_changed` reloads on a change of
        CONSTITUTION and deliberately ignores one of coordinates, so that
        a layout tweak is never undone by a refresh. This command changes
        coordinates and nothing else -- that is the entire design -- so it
        falls exactly into the case that subscriber declines.

        **ON REDO AND UNDO BOTH, which is why this is here rather than at
        the call site.** Measured in the running app with the reload done
        once, where the button was pressed: adopting redrew the canvas,
        and Ctrl+Z then reverted the model while the canvas went on
        showing the adopted drawing -- first atom at 17.6739, -6.2560 in
        both states. An undo that visibly does nothing is worse than the
        change it failed to reverse.
        """
        if self._on_applied is not None:
            self._on_applied(self._molecule)


class SetConformersCommand(OpenChemCommand):
    """Replaces a molecule's conformer set wholesale.

    Regenerating conformers replaces the previous set rather than appending
    to it — keeping old and new side by side is a fast-follow feature, not
    part of this command. Undo restores the previous set exactly.
    """

    def __init__(
        self,
        molecule: MoleculeModel,
        new_conformers: list[ConformerModel],
        event_bus: EventBus,
    ) -> None:
        super().__init__(f"Generate {len(new_conformers)} conformer(s) for '{molecule.display_name}'")
        self._molecule = molecule
        self._new_conformers = list(new_conformers)
        self._old_conformers = list(molecule.conformers)
        self._event_bus = event_bus

    def redo(self) -> None:
        self._molecule.conformers = list(self._new_conformers)
        self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))

    def undo(self) -> None:
        self._molecule.conformers = list(self._old_conformers)
        self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))


class AddConformerCommand(OpenChemCommand):
    """Appends a single conformer without touching the existing set —
    unlike `SetConformersCommand`, which replaces the whole list wholesale.
    Needed for ORCA (6.5): an optimized geometry should be added alongside
    whatever RDKit-generated conformers already exist, not wipe them.
    """

    def __init__(self, molecule: MoleculeModel, new_conformer: ConformerModel, event_bus: EventBus) -> None:
        super().__init__(f"Add conformer ({new_conformer.method}) to '{molecule.display_name}'")
        self._molecule = molecule
        self._new_conformer = new_conformer
        self._event_bus = event_bus

    def redo(self) -> None:
        self._molecule.conformers.append(self._new_conformer)
        self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))

    def undo(self) -> None:
        self._molecule.conformers.remove(self._new_conformer)
        self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))


class RotateStructureCommand(OpenChemCommand):
    """A drag in the editor's 3D rotation mode, as ONE undoable step.

    **The preview is not undoable and this is.** Mutating Ketcher's atom
    positions and redrawing fires no `change` event and leaves Ketcher's
    own history alone -- measured, seven ways, before any of this was
    written -- so sixty frames of a drag cost nothing, and only the
    geometry the user let go of becomes an edit.

    **Not `EditStructureCommand`**, which clears the conformer set: a
    rotation edits no structure, so the conformers are still valid. Same
    reasoning as `AdoptConformerCommand`, and the same `on_applied`
    callback, because the editor declines a coordinates-only change and
    has to be told explicitly.

    **THE EDITOR'S SCALE IS NOT ANGSTROMS, and this is where that is put
    right.** Ketcher normalises bond lengths to its own unit, so a
    cyclohexane loaded at C-C 1.5301 A comes back from `getMolfile` at
    1.0702 -- measured against the real bundle in
    `tests/test_editor_rotation_mode.py`. Harmless for as long as the
    editor only held layouts; a 30% error in every bond the moment it
    holds a geometry. `ChemistryEngine.rescale_like` restores it, and the
    residual it returns is what says the motion was rigid at all.

    **A rigid motion must not touch stereochemistry either.** It is
    checked anyway and refused if it did, because a rotation that changed
    a stereocentre would mean the coordinates and the graph had come
    apart -- and that is a bug worth failing loudly rather than
    committing.
    """

    #: How far a distance may still be out after the scale is restored,
    #: in Angstrom. A molblock holds four decimal places at Ketcher's ~0.70
    #: scale, so restoring it multiplies the rounding error by ~1.43 -- of
    #: the order of 1e-3 across a whole structure. This sits an order of
    #: magnitude above that and an order of magnitude below the smallest
    #: chemically meaningful change to a bond (~0.02 A).
    RIGID_TOLERANCE = 0.01

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        rotated_molblock: str,
        event_bus: EventBus,
        on_applied: Callable[[MoleculeModel], None] | None = None,
    ) -> None:
        super().__init__(f"Rotate '{molecule.display_name}'")
        self._engine = engine
        self._molecule = molecule
        self._event_bus = event_bus
        self._on_applied = on_applied
        self._old_molblock = molecule.molblock
        self._new_molblock = rotated_molblock

        if self._old_molblock:
            self._new_molblock, residual = engine.rescale_like(
                rotated_molblock, self._old_molblock
            )
            if not residual <= self.RIGID_TOLERANCE:
                raise StereochemistryConflict(
                    f"That is not a rotation -- a distance changed by "
                    f"{residual:.3f} A, and a rigid motion changes none. "
                    f"The drawing has been left as it was."
                )
            change = compare_stereochemistry(
                engine.mol_from_molblock(self._old_molblock),
                engine.mol_from_molblock(self._new_molblock),
            )
            if not change.quiet:
                raise StereochemistryConflict(
                    f"Rotating the structure {change.describe()}, which a rigid "
                    f"motion cannot do. The drawing has been left as it was."
                )

    @property
    def moved(self) -> bool:
        """Did the drag actually turn anything?

        **The caller cannot answer this by comparing molblock text**, and
        that is the whole reason this is here. The editor's copy is at
        Ketcher's scale, so the strings differ on every single drag
        including one that moved nothing -- a comparison that looks
        obviously correct and is never true. Asked after the scale has
        been restored, on the geometry rather than on the bytes.

        The threshold is `RIGID_TOLERANCE`: a drag that moved no atom
        further than the serialisation noise is not a rotation anybody
        asked for, and an undo entry that restores what is already there
        is worse than no entry at all -- Ctrl+Z then appears not to work.
        """
        if not self._old_molblock:
            return True
        before = self._engine.mol_from_molblock(self._old_molblock)
        after = self._engine.mol_from_molblock(self._new_molblock)
        if before.GetNumAtoms() != after.GetNumAtoms():
            return True
        old, new = before.GetConformer(), after.GetConformer()
        return any(
            math.dist(tuple(old.GetAtomPosition(i)), tuple(new.GetAtomPosition(i)))
            > self.RIGID_TOLERANCE
            for i in range(before.GetNumAtoms())
        )

    def redo(self) -> None:
        self._engine.set_structure_from_molblock(self._molecule, self._new_molblock)
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))
        self._redraw()

    def undo(self) -> None:
        if self._old_molblock:
            self._engine.set_structure_from_molblock(self._molecule, self._old_molblock)
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))
        self._redraw()

    def _redraw(self) -> None:
        if self._on_applied is not None:
            self._on_applied(self._molecule)
