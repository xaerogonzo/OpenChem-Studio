from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from rdkit import Chem

from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.docking import DockingBox, DockingPoseModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.scientific_result import AlertResult, PerAtomDataset, SpectrumResult
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

    def descriptor_categories(self) -> dict[str, str]:
        """Optional: descriptor_id -> category, known up front without
        computing anything. Lets callers (DescriptorService's QUEUED/RUNNING
        placeholders) publish the real category immediately instead of an
        empty one that the UI would have to correct later. Not abstract:
        defaults to empty, so a provider that only ever categorizes on the
        computed DescriptorValue itself still works, just without the
        up-front placeholder benefit."""
        return {}

    def compute_alerts(self, mol: Chem.Mol, molecule_uuid: str) -> list[AlertResult]:
        """Optional: structural-alert catalog results (e.g. PAINS) this
        provider can flag — a molecule either matches zero or more named
        alerts, which doesn't fit a single `DescriptorValue`. Not abstract:
        most providers have no alert-shaped output, so the default is none
        rather than forcing every implementer (including plugin-supplied
        ones) to override it."""
        return []

    def compute_per_atom(self, mol: Chem.Mol, molecule_uuid: str) -> list[PerAtomDataset]:
        """Optional: per-atom scientific data (partial charges, LogP
        contributions) this provider can produce — one value per atom
        index, which doesn't fit a single `DescriptorValue` either. Not
        abstract, same reasoning as `compute_alerts`."""
        return []


class ConformerProvider(ABC):
    provider_id: str

    @abstractmethod
    def generate_conformers(
        self,
        mol: Chem.Mol,
        num_conformers: int,
        optimize: bool,
        on_progress: Callable[[int, int], bool | None] | None = None,
    ) -> list[tuple[Chem.Mol, float | None]]:
        """Return up to `num_conformers` (conformer_mol, energy) pairs.

        `energy` (kcal/mol) is None when `optimize` is False. `on_progress`,
        if given, is called as `on_progress(done, total)` after each
        conformer so callers can report incremental progress. If it
        returns `False`, the provider should stop before generating the
        next conformer (best-effort cancellation, checked between
        conformers — a `None` return, the common case, means "keep
        going")."""


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
        receptor_prep_options: dict[str, Any] | None = None,
    ) -> list[DockingPoseModel]:
        """Dock `ligand_mol` against a receptor (raw structure text, same
        shape as `MacromoleculeModel.structure_text`/`.source_format`)
        within `box`. The provider is responsible for its own receptor/
        ligand preparation (PDBQT conversion, etc.) — callers pass raw
        structure data, not pre-converted files. Reports phase-labeled
        progress via `progress.report(...)` (e.g. "Preparing receptor",
        "Docking", "Scoring").

        `receptor_prep_options` (all optional, provider-defined keys —
        `VinaDockingProvider` recognizes `ph: float`, `strip_waters: bool`,
        `strip_cofactors: bool`) controls receptor preparation. `None`
        means "use the provider's own defaults," same as an empty dict."""


class QuantumEngineProvider(ABC):
    """Which quantum-chemistry engine runs a calculation — `OrcaQuantumEngineProvider`
    (chem/orca_engine.py) is the only implementation today, but quantum-
    chemistry engines are a well-established, obviously-multi-implementation
    category regardless (xTB, Psi4, NWChem, Gaussian, MOPAC, CREST are all
    real, commonly-used alternatives) — matching a known scientific
    taxonomy at near-zero extra cost, not premature generality.

    Deliberately three pure, synchronous methods rather than one blocking
    `run()`: `QuantumChemistryService` runs the actual engine via `QProcess`
    **on the GUI thread** (unlike every other async service in this
    codebase, which uses `QRunnable`/`QThreadPool` — see
    `services/quantum_chemistry_service.py`'s docstring for why), so the
    provider itself must never own subprocess/thread lifecycle — only
    input-building and output-parsing, both trivially unit-testable without
    any process involved.
    """

    provider_id: str

    @abstractmethod
    def build_input(
        self, mol: Chem.Mol, charge: int, multiplicity: int, method_basis: str, calc_type: str
    ) -> str:
        """Returns the engine's own input-file text. `calc_type` is "sp",
        "opt", or "opt_freq".

        Note on `parse_output`'s descriptors: emit the converged total
        energy as `"<provider_id>.scf_energy"` in Hartree. Boltzmann
        conformer averaging (`chem/boltzmann.py`) looks it up by that
        convention to weight each conformer's spectrum, and silently
        skips a run that doesn't provide it.
        """

    @abstractmethod
    def command_args(self, executable_path: str, input_path: Path) -> list[str]:
        """How to invoke this engine's executable for `input_path` — e.g.
        `["orca", str(input_path)]`. A different future engine may have a
        different CLI convention (a separate output-file argument, etc.),
        hence this being part of the provider, not hardcoded in the
        service."""

    @abstractmethod
    def parse_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> tuple[list[DescriptorValue], ConformerModel | None]:
        """Parses the engine's own captured stdout into results. `mol` (the
        same one passed to `build_input`) is needed to reconstruct an
        optimized-geometry conformer onto the original connectivity — the
        engine's output gives element symbols + coordinates, not bonds.
        `molecule_uuid` only stamps the returned `DescriptorValue`s (same
        convention as `DescriptorProvider.compute`), not used for lookup.
        Returns however many `DescriptorValue`s the output actually yields
        (SCF energy always; thermochemistry only for "opt_freq") plus an
        optimized-geometry `ConformerModel` for "opt"/"opt_freq" (`None`
        for "sp")."""

    def parse_spectrum_output(
        self, output_text: str, mol: Chem.Mol, molecule_uuid: str, calc_type: str
    ) -> SpectrumResult | None:
        """Optional: a spectroscopic result (NMR shielding today) this
        engine's output can yield for `calc_type` — per-nucleus data,
        which doesn't fit `DescriptorValue`'s one-scalar shape (see
        `SpectrumResult`). Not abstract: most calc_types (`"sp"`/`"opt"`/
        `"opt_freq"`) have no spectrum to report, so the default is `None`
        rather than forcing every implementer to override it."""
        return None

    def parse_spin_spin_coupling(
        self, output_text: str, calc_type: str
    ) -> dict[tuple[int, int], float] | None:
        """Optional (Phase 22): real ab initio spin-spin coupling
        constants (Hz) between atom-index pairs, for engines/calc_types
        that compute them. Default `None` — most calc_types have no
        coupling data, same optional-capability shape as
        `parse_spectrum_output`."""
        return None


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
