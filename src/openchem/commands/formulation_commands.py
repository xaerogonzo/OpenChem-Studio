"""Undoable edits to the formulations in a project.

Its own module beside `crystal_commands.py`, for the reason
`domain/formulation.py` gives at length: a recipe is not a molecule, and
a formulation uuid handed to `find_molecule` finds nothing while every
path after it acts on whatever was selected before.

## ONE SAVE COMMAND, BECAUSE THE MODEL IS FROZEN

`CrystalModel` is mutable, so renaming one is a field assignment and
`RenameCrystalCommand` is the natural shape. `FormulationModel` is a
FROZEN dataclass, so there is no edit-in-place to make undoable -- an
edit produces a new value, and the operation on the project is
*replace the entry with this one*. `SaveFormulationCommand` is therefore
add-or-replace rather than an add command beside a rename command, and
that is the model's shape showing through rather than a shortcut.

## FOUND BY UUID, NEVER BY VALUE

`DeleteCrystalCommand` locates its subject with `list.index(...)`, which
is identity-free equality. That is safe for a mutable model, whose
instances are distinct objects. For a frozen dataclass it is not: two
formulations stating the same recipe compare EQUAL, so `index()` would
find the first of them and delete the wrong row. Every lookup here is by
`uuid`, which is what `ProjectModel.find_formulation` already keys on.
"""

from __future__ import annotations

from openchem.commands.base import OpenChemCommand
from openchem.domain.formulation import FormulationModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import FormulationChanged


def _index_of(project: ProjectModel, formulation_uuid: str) -> int | None:
    for index, existing in enumerate(project.formulations):
        if existing.uuid == formulation_uuid:
            return index
    return None


class SaveFormulationCommand(OpenChemCommand):
    """Add a formulation, or replace the one carrying the same uuid.

    Undo restores exactly what was there before -- nothing, for an add,
    or the previous version at its own position for a replace. The index
    is read in `redo` rather than in `__init__` for the reason
    `DeleteCrystalCommand` records: a command can be pushed, undone and
    redone repeatedly, and the index at push time is not the index at the
    next redo.
    """

    def __init__(
        self,
        project: ProjectModel,
        formulation: FormulationModel,
        event_bus: EventBus,
    ) -> None:
        existing = project.find_formulation(formulation.uuid)
        verb = "Edit" if existing is not None else "Add"
        super().__init__(f"{verb} formulation '{formulation.display_name}'")
        self._project = project
        self._formulation = formulation
        self._event_bus = event_bus
        self._index: int | None = None
        self._replaced: FormulationModel | None = None

    def redo(self) -> None:
        self._index = _index_of(self._project, self._formulation.uuid)
        if self._index is None:
            self._replaced = None
            self._index = len(self._project.formulations)
            self._project.formulations.append(self._formulation)
        else:
            self._replaced = self._project.formulations[self._index]
            self._project.formulations[self._index] = self._formulation
        self._event_bus.publish(
            FormulationChanged(formulation_uuid=self._formulation.uuid)
        )

    def undo(self) -> None:
        if self._index is None:
            return
        if self._replaced is None:
            self._project.formulations.pop(self._index)
        else:
            self._project.formulations[self._index] = self._replaced
        self._event_bus.publish(
            FormulationChanged(formulation_uuid=self._formulation.uuid)
        )


class DeleteFormulationCommand(OpenChemCommand):
    """Delete a formulation, and put it back WHERE IT WAS on undo.

    The position is recorded for the reason `DeleteMoleculeCommand`
    records it: undo has to be a true inverse. Somebody who deletes the
    wrong row and presses Ctrl+Z is asking for the state they had, not a
    similar one -- and quietly reordering is a diff in every saved
    project file as well.
    """

    def __init__(
        self,
        project: ProjectModel,
        formulation: FormulationModel,
        event_bus: EventBus,
    ) -> None:
        super().__init__(f"Delete formulation '{formulation.display_name}'")
        self._project = project
        self._formulation = formulation
        self._event_bus = event_bus
        self._index: int | None = None

    def redo(self) -> None:
        self._index = _index_of(self._project, self._formulation.uuid)
        if self._index is None:
            return
        self._project.formulations.pop(self._index)
        self._event_bus.publish(
            FormulationChanged(formulation_uuid=self._formulation.uuid)
        )

    def undo(self) -> None:
        if self._index is None:
            return
        self._project.formulations.insert(self._index, self._formulation)
        self._event_bus.publish(
            FormulationChanged(formulation_uuid=self._formulation.uuid)
        )
