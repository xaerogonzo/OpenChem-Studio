from __future__ import annotations

from PySide6.QtGui import QUndoCommand


class OpenChemCommand(QUndoCommand):
    """Base for all undoable OpenChem operations.

    Structure-modifying and project-modifying user actions go through a
    command rather than mutating MoleculeModel/ProjectModel directly from UI
    code, so undo/redo stays correct and every action is a discrete,
    nameable unit — the same shape a future scripting/AI-automation surface
    would want to drive.
    """
