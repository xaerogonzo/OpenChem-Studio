from __future__ import annotations

from openchem.chem.engine import ChemistryEngine
from openchem.commands.base import OpenChemCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged, ConformersInvalidated, MoleculeChanged


class AddMoleculeCommand(OpenChemCommand):
    def __init__(self, project: ProjectModel, molecule: MoleculeModel, event_bus: EventBus) -> None:
        super().__init__(f"Add molecule '{molecule.display_name}'")
        self._project = project
        self._molecule = molecule
        self._event_bus = event_bus

    def redo(self) -> None:
        self._project.molecules.append(self._molecule)
        self._project.record_history(f"Added molecule {self._molecule.uuid}")
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))

    def undo(self) -> None:
        self._project.molecules.remove(self._molecule)
        self._project.record_history(f"Removed molecule {self._molecule.uuid}")
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))


class DeleteMoleculeCommand(OpenChemCommand):
    """Delete a molecule, and put it back WHERE IT WAS on undo.

    The position is recorded because `undo` used to `append`, so undoing
    the deletion of a molecule from the middle of a project moved it to the
    bottom of the Project Explorer. Undo has to be a true inverse: a user
    who deletes the wrong row and presses Ctrl+Z is asking for the state
    they had, not for a similar one, and quietly reordering a project is
    also a diff in every saved file and a reordering of every batch table
    built from it.

    Unlike the add-shaped commands around it, where appending on redo IS
    the original position.
    """

    def __init__(self, project: ProjectModel, molecule: MoleculeModel, event_bus: EventBus) -> None:
        super().__init__(f"Delete molecule '{molecule.display_name}'")
        self._project = project
        self._molecule = molecule
        self._event_bus = event_bus
        #: Captured in `redo` rather than here, because a command can be
        #: pushed, undone and redone repeatedly and the index at push time
        #: is not necessarily the index at the next redo.
        self._index: int | None = None

    def redo(self) -> None:
        try:
            self._index = self._project.molecules.index(self._molecule)
        except ValueError:
            self._index = None
        self._project.molecules.remove(self._molecule)
        self._project.record_history(f"Removed molecule {self._molecule.uuid}")
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))

    def undo(self) -> None:
        if self._index is None:
            self._project.molecules.append(self._molecule)
        else:
            # `insert` clamps a too-large index to the end, so a project
            # that shrank while this was undone still restores rather than
            # raising.
            self._project.molecules.insert(self._index, self._molecule)
        self._project.record_history(f"Restored molecule {self._molecule.uuid}")
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))


class RenameMoleculeCommand(OpenChemCommand):
    def __init__(self, molecule: MoleculeModel, new_name: str, event_bus: EventBus) -> None:
        super().__init__(f"Rename molecule to '{new_name}'")
        self._molecule = molecule
        self._old_name = molecule.display_name
        self._new_name = new_name
        self._event_bus = event_bus

    def redo(self) -> None:
        self._molecule.display_name = self._new_name
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))

    def undo(self) -> None:
        self._molecule.display_name = self._old_name
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))


class EditStructureCommand(OpenChemCommand):
    """Wraps a whole-structure edit (e.g. from Ketcher) as an undoable command.

    Ketcher reports a full new molblock rather than fine-grained atom/bond
    operations, so the command captures old/new molblock snapshots — the
    normal shape for integrating an external structure editor behind
    `EditorBackend`.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        molecule: MoleculeModel,
        new_molblock: str,
        event_bus: EventBus,
    ) -> None:
        super().__init__(f"Edit structure '{molecule.display_name}'")
        self._engine = engine
        self._molecule = molecule
        self._old_molblock = molecule.molblock
        self._new_molblock = new_molblock
        self._event_bus = event_bus
        # Snapshotted so undo can restore the conformers that matched the
        # old structure, not just the old molblock -- they describe the
        # same structure the undo is reverting to, so they're still valid.
        self._old_conformers: list[ConformerModel] = list(molecule.conformers)

    def redo(self) -> None:
        self._engine.set_structure_from_molblock(self._molecule, self._new_molblock)
        self._invalidate_stale_conformers()
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))

    def undo(self) -> None:
        if self._old_molblock is not None:
            self._engine.set_structure_from_molblock(self._molecule, self._old_molblock)
        else:
            self._molecule.molblock = None
            self._molecule.canonical_smiles = None
            self._molecule.inchi = None
            self._molecule.inchikey = None
        if self._molecule.conformers != self._old_conformers:
            self._molecule.conformers = list(self._old_conformers)
            self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))
        self._event_bus.publish(MoleculeChanged(molecule_uuid=self._molecule.uuid))

    def _invalidate_stale_conformers(self) -> None:
        # A structure edit invalidates whatever conformers existed before
        # it -- they described the old structure, not this one. Published
        # before MoleculeChanged so MainWindow's snapshot (conformer_count,
        # lowest_conformer_energy) already reflects the cleared state.
        if not self._molecule.conformers:
            return
        self._molecule.conformers = []
        self._event_bus.publish(ConformersInvalidated(molecule_uuid=self._molecule.uuid))
        self._event_bus.publish(ConformersChanged(molecule_uuid=self._molecule.uuid))
