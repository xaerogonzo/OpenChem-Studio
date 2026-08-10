from __future__ import annotations

from collections.abc import Callable

from openchem.chem.engine import ChemistryEngine
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
        self._new_molblock = engine.drawing_from_conformer(conformer_molblock)

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
