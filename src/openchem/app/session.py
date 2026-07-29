from __future__ import annotations

from openchem.domain.project import ProjectModel


class SessionManager:
    """Holds the active project, the selected molecule, and the dirty flag.

    Thin session state — not persisted itself; the ProjectModel it wraps is
    what actually gets saved (via ProjectService).
    """

    def __init__(self) -> None:
        self._project: ProjectModel | None = None
        self._selected_molecule_uuid: str | None = None
        self._dirty: bool = False

    @property
    def project(self) -> ProjectModel | None:
        return self._project

    def set_project(self, project: ProjectModel | None) -> None:
        self._project = project
        self._selected_molecule_uuid = None
        self._dirty = False

    @property
    def selected_molecule_uuid(self) -> str | None:
        return self._selected_molecule_uuid

    def select_molecule(self, molecule_uuid: str | None) -> None:
        self._selected_molecule_uuid = molecule_uuid

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def mark_clean(self) -> None:
        self._dirty = False
