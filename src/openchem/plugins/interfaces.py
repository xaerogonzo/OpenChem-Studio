from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from rdkit import Chem

from openchem.domain.descriptor import DescriptorValue
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.domain.molecule import MoleculeModel
from openchem.services.progress import ProgressHandle

if TYPE_CHECKING:
    from openchem.plugins.context import PluginContext

# Bumped whenever Plugin/PluginContext's own contract changes in a way that
# could break existing plugins. Compared against each plugin's declared
# `api_version` in manifest.toml before it's ever imported.
PLUGIN_API_VERSION = 1

"""Plugin contract interfaces.

Discovery/loading lives in `openchem.plugins.manager` (Phase 4). Defining
these ABCs early, and having the built-in RDKit-backed implementations
(`openchem.chem.descriptor_providers`, `openchem.chem.conformer_providers`,
`openchem.chem.io_backends`) implement these *same* ABCs rather than
private copies, meant Phase 4 only had to add discovery — not redesign
what a plugin looks like.

These interfaces reference `rdkit.Chem.Mol` because a descriptor/import/
export plugin necessarily does real chemistry. That's distinct from the
"UI never imports RDKit" rule, which is about the UI/widget layer, not
plugin implementations — a plugin is expected to sit alongside `chem/`.

`Plugin` itself carries no metadata (no `plugin_id`/`display_name`/
`api_version` attributes) — that all lives in each plugin's `manifest.toml`
(see `plugins/manifest.py`), read by the loader *without* importing any
plugin code. `Plugin` is purely the lifecycle contract.
"""


class Plugin(ABC):
    @abstractmethod
    def activate(self, context: "PluginContext") -> None:
        """Register everything this plugin provides, via `context`.

        If this raises, the loader rolls back anything already registered
        through `context` before the exception — see `PluginManager`.
        """

    @abstractmethod
    def deactivate(self) -> None:
        """Best-effort cleanup hook for anything `context`'s tracked
        unregistration doesn't cover (e.g. an open file handle). The loader
        already reverses every `context.*.register`/`context.events.subscribe`
        call on its own; this is not the primary unload mechanism.
        """


class DescriptorProvider(ABC):
    provider_id: str

    @abstractmethod
    def descriptor_ids(self) -> list[str]:
        """Descriptor ids this provider can compute."""

    @abstractmethod
    def compute(self, mol: Chem.Mol, molecule_uuid: str) -> list[DescriptorValue]:
        """Compute this provider's descriptors for a parsed RDKit Mol."""


class ConformerProvider(ABC):
    provider_id: str

    @abstractmethod
    def generate_conformers(
        self,
        mol: Chem.Mol,
        num_conformers: int,
        optimize: bool,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[Chem.Mol, float | None]]:
        """Return up to `num_conformers` (conformer_mol, energy) pairs.

        `energy` (kcal/mol) is None when `optimize` is False. `on_progress`,
        if given, is called as `on_progress(done, total)` after each
        conformer so callers can report incremental progress.
        """


class DockingProvider(ABC):
    """Which docking *algorithm* runs — deliberately separate from
    `chem.vina_engine.VinaEngine`, which is about how AutoDock Vina itself
    gets invoked (Python binding vs. CLI executable). A future alternative
    docking algorithm (not just an alternative way to run Vina) registers
    a second `DockingProvider`, the same extensibility shape as
    `ConformerProvider`/`DescriptorProvider`.
    """

    provider_id: str

    @abstractmethod
    def dock(
        self,
        receptor_structure_text: str,
        receptor_source_format: str,
        ligand_mol: Chem.Mol,
        box: DockingBox,
        num_poses: int,
        progress: ProgressHandle,
    ) -> list[DockingPoseModel]:
        """Dock `ligand_mol` against a receptor (raw structure text, same
        shape as `MacromoleculeModel.structure_text`/`.source_format`)
        within `box`. The provider is responsible for its own receptor/
        ligand preparation (PDBQT conversion, etc.) — callers pass raw
        structure data, not pre-converted files. Reports phase-labeled
        progress via `progress.report(...)` (e.g. "Preparing receptor",
        "Docking", "Scoring")."""


class PanelProvider(ABC):
    panel_id: str

    @abstractmethod
    def create_panel(self) -> Any:
        """Return a QWidget for a new dock panel."""


class MenuProvider(ABC):
    @abstractmethod
    def menu_entries(self) -> list[tuple[str, str]]:
        """Return (menu_path, action_id) pairs to insert into the main menu."""

    @abstractmethod
    def handle_menu_action(self, action_id: str) -> None:
        """Called when the user triggers one of this provider's menu entries."""


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
