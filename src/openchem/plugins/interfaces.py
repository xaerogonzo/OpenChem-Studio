from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from rdkit import Chem

from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel

"""Plugin contract interfaces.

Only the interfaces exist in Phase 1/2 — there is no discovery or loading
yet (that's the Phase 4 plugin loader). Defining them now, and having the
built-in RDKit-backed implementations (`openchem.chem.descriptor_providers`,
`openchem.chem.io_backends`) implement these *same* ABCs rather than
private copies, means Phase 4 only has to add discovery — not redesign
what a plugin looks like.

These interfaces reference `rdkit.Chem.Mol` because a descriptor/import/
export plugin necessarily does real chemistry. That's distinct from the
"UI never imports RDKit" rule, which is about the UI/widget layer, not
plugin implementations — a plugin is expected to sit alongside `chem/`.
"""


class Plugin(ABC):
    plugin_id: str
    display_name: str

    @abstractmethod
    def activate(self) -> None: ...

    @abstractmethod
    def deactivate(self) -> None: ...


class DescriptorProvider(ABC):
    provider_id: str

    @abstractmethod
    def descriptor_ids(self) -> list[str]:
        """Descriptor ids this provider can compute."""

    @abstractmethod
    def compute(self, mol: Chem.Mol, molecule_uuid: str) -> list[DescriptorValue]:
        """Compute this provider's descriptors for a parsed RDKit Mol."""


class PanelProvider(ABC):
    panel_id: str

    @abstractmethod
    def create_panel(self) -> Any:
        """Return a QWidget for a new dock panel."""


class MenuProvider(ABC):
    @abstractmethod
    def menu_entries(self) -> list[tuple[str, str]]:
        """Return (menu_path, action_id) pairs to insert into the main menu."""


class Importer(ABC):
    @abstractmethod
    def supported_formats(self) -> set[str]: ...

    @abstractmethod
    def import_file(self, path: Path) -> list[MoleculeModel]: ...


class Exporter(ABC):
    @abstractmethod
    def supported_formats(self) -> set[str]: ...

    @abstractmethod
    def export_file(self, model: MoleculeModel, path: Path, fmt: str) -> None: ...
