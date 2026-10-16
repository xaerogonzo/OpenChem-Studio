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
    with.** `canonical_conformer` picks the newest ORCA-optimized geometry
    if there is one and otherwise the LOWEST MMFF energy, not a
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


class RedrawFlatCommand(OpenChemCommand):
    """Lay the drawing out flat again, keeping the structure and the
    conformers.

    **THE OTHER HALF OF "Use in 2D Editor".** That button brings a
    conformer across as a 3D projection, deliberately -- the drawing keeps
    its z and the canvas draws the x/y, which is what makes it look like
    the geometry. What was missing was the way back: reported as "we don't
    have an easy way to convert the structure back to a two d form. I tried
    hitting the cleanup button. but it did not convert it back".

    **CLEAN UP IS NOT THAT, AND MEASURING SAID SO.** It zeroes the z column
    and keeps the projected x/y, so the picture stays the overlapping mess
    it was -- 7 structure warnings on the reported cage. Ketcher's Layout
    does redraw it properly and is the one that changed the compound; see
    `ChemistryEngine.flat_drawing`.

    **NOT `EditStructureCommand`**, for the reason `AdoptConformerCommand`
    is not: that one clears the conformer set on redo, correctly, because a
    structure edit invalidates it. This changes coordinates and nothing
    else, so the conformers still describe this structure and must survive.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        event_bus: EventBus,
        on_applied: Callable[[MoleculeModel], None] | None = None,
    ) -> None:
        super().__init__(f"Redraw '{molecule.display_name}' in 2D")
        self._engine = engine
        self._molecule = molecule
        self._event_bus = event_bus
        self._on_applied = on_applied
        self._old_molblock = molecule.molblock
        # Built in the constructor and refused here, so nothing reaches the
        # undo stack -- the rule `AdoptConformerCommand` states and the
        # reason a redo cannot produce a different drawing from the one
        # that was accepted.
        drawing = engine.flat_drawing(molecule.molblock or "", reference=molecule.molblock)
        if drawing.stereo is not None and not drawing.stereo.safe:
            raise StereochemistryConflict(
                f"Redrawing this flat {drawing.stereo.describe()}."
            )
        self._new_molblock = drawing.molblock
        #: What laying it out flat did to the stereochemistry. Safe by
        #: construction; the caller is still expected to say so when it is
        #: not quiet, exactly as the adopt path does.
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
        """The canvas does not follow a coordinates-only change on its own
        -- see `AdoptConformerCommand._redraw` for the measurement."""
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
        kept: int = 0,
    ) -> None:
        # `kept` = how many of `new_conformers` are earlier ORCA-optimized ones carried over, so the Undo menu
        # counts what was generated and says what was kept.
        generated = len(new_conformers) - kept
        note = f", keeping {kept} ORCA-optimized" if kept else ""
        super().__init__(f"Generate {generated} conformer(s){note} for '{molecule.display_name}'")
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

    **IT ALSO CHANGES WHICH GEOMETRY EVERYTHING COMPUTES WITH**, when the
    conformer is an ORCA optimization: `canonical_conformer` prefers it to
    every force-field conformer. `ConformersChanged` already makes the window
    recompute the 3D calculators, and undo removes the conformer, so the
    previous choice comes back with it.
    """

    def __init__(
        self,
        molecule: MoleculeModel,
        new_conformer: ConformerModel,
        event_bus: EventBus,
        show: bool = False,
    ) -> None:
        super().__init__(f"Add conformer ({new_conformer.method}) to '{molecule.display_name}'")
        self._molecule = molecule
        self._new_conformer = new_conformer
        self._event_bus = event_bus
        #: True = the 3D viewer lands on the appended conformer instead of returning to the first one.
        #: Used for a geometry the user just asked ORCA for; undo removes it and the viewer returns.
        self._show = show

    def redo(self) -> None:
        self._molecule.conformers.append(self._new_conformer)
        self._event_bus.publish(
            ConformersChanged(
                molecule_uuid=self._molecule.uuid,
                show_conformer_id=self._new_conformer.conformer_id if self._show else "",
            )
        )

    def undo(self) -> None:
        self._molecule.conformers.remove(self._new_conformer)
        self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))


class ReplaceConformerCommand(OpenChemCommand):
    """Swaps one conformer for another IN ITS SLOT, so 7 of 20 stays 7 of 20.

    **Why this exists.** An ORCA geometry optimization starts from one
    conformer and ends with that same conformer, relaxed. Appending the
    result (`AddConformerCommand`) made it conformer 21 of 21, so the
    conformer the user had been looking at went on showing its force-field
    geometry while every later calculation ran on the optimized one.

    **The source is found by IDENTITY at redo, and never mutated.** The
    command holds the object it was built to replace; the list may have
    been regenerated between the job's start and its landing, and an index
    taken earlier would then name a different conformer. The original object
    is left exactly as it was, so undo can put the very same object back.

    **It records what redo ACTUALLY did, because undo must reverse that and
    nothing else.** If the source is gone at redo the replacement is appended
    (the geometry is still the user's, and dropping it silently would lose a
    finished job); undo of that removes the appended object. Undo of a real
    replacement restores the original at the slot it occupied.

    **Every outcome shows the geometry that is now current**, via
    `ConformersChanged.show_conformer_id`: the replacement on redo, the
    restored original on undo of a replacement, nothing in particular after an
    appended one is removed.
    """

    def __init__(
        self,
        molecule: MoleculeModel,
        source: ConformerModel,
        replacement: ConformerModel,
        event_bus: EventBus,
    ) -> None:
        super().__init__(f"Replace conformer with {replacement.method} geometry for '{molecule.display_name}'")
        self._molecule = molecule
        self._source = source
        self._replacement = replacement
        self._event_bus = event_bus
        #: Set by `redo`: the slot the replacement took, or None when it was appended instead.
        self._replaced_index: int | None = None

    def redo(self) -> None:
        conformers = self._molecule.conformers
        index = next((i for i, c in enumerate(conformers) if c is self._source), None)
        if index is None:
            conformers.append(self._replacement)
            self._replaced_index = None
        else:
            conformers[index] = self._replacement
            self._replaced_index = index
        self._event_bus.publish(
            ConformersChanged(molecule_uuid=self._molecule.uuid, show_conformer_id=self._replacement.conformer_id)
        )

    def undo(self) -> None:
        conformers = self._molecule.conformers
        # By identity again: the list may have been rebuilt since redo, and a stored index is only a hint.
        current = next((i for i, c in enumerate(conformers) if c is self._replacement), None)
        if current is None:
            # Nothing of ours is in the list any more (a later regeneration replaced it wholesale); restoring
            # the original would put a stale conformer into a list it was never part of.
            self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))
            return
        if self._replaced_index is None:
            del conformers[current]
            self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))
            return
        conformers[current] = self._source
        self._event_bus.publish(
            ConformersChanged(molecule_uuid=self._molecule.uuid, show_conformer_id=self._source.conformer_id)
        )


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
