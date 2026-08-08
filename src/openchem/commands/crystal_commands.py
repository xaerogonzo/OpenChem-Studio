"""Undoable edits to the crystals in a project.

Separate from `molecule_commands.py` for the reason `domain/crystal.py`
gives at length: a crystal is not a molecule, and every path that treats
one as the other has produced a bug in this project -- a crystal click
reaching the molecular distance measurement, a crystal uuid handed to
`find_molecule`, 27 molecular calculators offered to a periodic solid.

The shapes mirror the molecule commands deliberately, including the
position-restoring undo, which is a lesson learned there and not worth
learning twice.
"""

from __future__ import annotations

from openchem.commands.base import OpenChemCommand
from openchem.domain.crystal import CrystalModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import CrystalChanged


class RenameCrystalCommand(OpenChemCommand):
    """Rename a crystal.

    A crystal takes its name from the CIF (`_chemical_name_mineral` and
    friends) or from the filename, and neither is always what somebody
    wants to see in a project holding four polymorphs.
    """

    def __init__(self, crystal: CrystalModel, new_name: str, event_bus: EventBus) -> None:
        super().__init__(f"Rename crystal to '{new_name}'")
        self._crystal = crystal
        self._old_name = crystal.display_name
        self._new_name = new_name
        self._event_bus = event_bus

    def redo(self) -> None:
        self._crystal.display_name = self._new_name
        self._event_bus.publish(CrystalChanged(crystal_uuid=self._crystal.uuid))

    def undo(self) -> None:
        self._crystal.display_name = self._old_name
        self._event_bus.publish(CrystalChanged(crystal_uuid=self._crystal.uuid))


class DeleteCrystalCommand(OpenChemCommand):
    """Delete a crystal, and put it back WHERE IT WAS on undo.

    **The position is recorded**, for the same reason `DeleteMoleculeCommand`
    records it: undo has to be a true inverse. A user who deletes the
    wrong row and presses Ctrl+Z is asking for the state they had, not a
    similar one -- and quietly reordering is also a diff in every saved
    project file.

    The index is captured in `redo` rather than in `__init__`, because a
    command can be pushed, undone and redone repeatedly and the index at
    push time is not necessarily the index at the next redo.
    """

    def __init__(
        self, project: ProjectModel, crystal: CrystalModel, event_bus: EventBus
    ) -> None:
        super().__init__(f"Delete crystal '{crystal.display_name}'")
        self._project = project
        self._crystal = crystal
        self._event_bus = event_bus
        self._index: int | None = None

    def redo(self) -> None:
        try:
            self._index = self._project.crystals.index(self._crystal)
        except ValueError:
            return
        self._project.crystals.pop(self._index)
        self._event_bus.publish(CrystalChanged(crystal_uuid=self._crystal.uuid))

    def undo(self) -> None:
        if self._index is None:
            return
        self._project.crystals.insert(self._index, self._crystal)
        self._event_bus.publish(CrystalChanged(crystal_uuid=self._crystal.uuid))
