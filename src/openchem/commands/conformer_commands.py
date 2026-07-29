from __future__ import annotations

from openchem.commands.base import OpenChemCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformersChanged


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
