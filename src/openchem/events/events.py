from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.docking import DockingResultModel
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.events.base import Event


@dataclass(frozen=True)
class MoleculeChanged(Event):
    molecule_uuid: str


@dataclass(frozen=True)
class MoleculeSelected(Event):
    molecule_uuid: str | None


@dataclass(frozen=True)
class MoleculeSnapshotUpdated(Event):
    """A lightweight, read-only snapshot of a molecule's identity fields.

    Plugins have no access to SessionManager/ProjectModel (that would break
    the same UI decoupling `UIRegistry` was built to preserve), so this is
    the one place they can learn a molecule's canonical SMILES/InChI/name —
    MoleculeSelected/MoleculeChanged only carry a UUID, and DescriptorComputed
    only carries numeric values, not identity fields.
    """

    molecule_uuid: str
    display_name: str
    canonical_smiles: str | None
    inchi: str | None
    inchikey: str | None
    conformer_count: int
    lowest_conformer_energy: float | None


@dataclass(frozen=True)
class ProjectLoaded(Event):
    project_uuid: str


@dataclass(frozen=True)
class ProjectClosed(Event):
    project_uuid: str


@dataclass(frozen=True)
class DescriptorInvalidated(Event):
    molecule_uuid: str
    descriptor_id: str


@dataclass(frozen=True)
class DescriptorComputed(Event):
    descriptor: DescriptorValue


@dataclass(frozen=True)
class AlertComputed(Event):
    alert: AlertResult


@dataclass(frozen=True)
class PerAtomDataComputed(Event):
    dataset: PerAtomDataset


@dataclass(frozen=True)
class ConformerJobStateChanged(Event):
    molecule_uuid: str
    state: CacheState
    message: str = ""


@dataclass(frozen=True)
class ConformersReady(Event):
    molecule_uuid: str
    conformers: list[ConformerModel]


@dataclass(frozen=True)
class ConformersChanged(Event):
    molecule_uuid: str


@dataclass(frozen=True)
class ConformersInvalidated(Event):
    """A molecule's conformers were cleared because its 2D structure
    changed underneath them -- distinct from ConformersChanged (which also
    fires on a legitimate regeneration/undo) so a future consumer can react
    specifically to "these are gone because they're stale," not just "the
    list changed." Always accompanied by a ConformersChanged for the same
    molecule_uuid, published immediately after this one.
    """

    molecule_uuid: str


@dataclass(frozen=True)
class ConformerSelected(Event):
    molecule_uuid: str
    conformer_id: str | None


@dataclass(frozen=True)
class PluginLoaded(Event):
    plugin_id: str


@dataclass(frozen=True)
class PluginUnloaded(Event):
    plugin_id: str


@dataclass(frozen=True)
class PluginLoadFailed(Event):
    plugin_id: str
    error: str


@dataclass(frozen=True)
class SettingsChanged(Event):
    key: str


@dataclass(frozen=True)
class DockingJobStateChanged(Event):
    ligand_molecule_uuid: str
    receptor_macromolecule_uuid: str
    state: CacheState
    message: str = ""


@dataclass(frozen=True)
class DockingResultReady(Event):
    result: DockingResultModel


@dataclass(frozen=True)
class QuantumChemistryJobStateChanged(Event):
    molecule_uuid: str
    state: CacheState
    message: str = ""


@dataclass(frozen=True)
class QuantumChemistryResultReady(Event):
    molecule_uuid: str
    descriptors: list[DescriptorValue]
    conformer: ConformerModel | None


@dataclass(frozen=True)
class SpectrumComputed(Event):
    spectrum: SpectrumResult


@dataclass(frozen=True)
class PhCurveComputed(Event):
    """Published when a calculator produces a property-vs-pH curve
    (Phase 28) -- pKa speciation, isoelectric point, logD, H-bonding."""

    curve: PhCurveResult


@dataclass(frozen=True)
class TrajectoryComputed(Event):
    """Published when a calculator produces a time-ordered set of
    frames (Phase 30) -- molecular dynamics today."""

    trajectory: TrajectoryResult


@dataclass(frozen=True)
class StructureSetComputed(Event):
    """Published when a calculator produces a SET of structures (Phase 27)
    -- stereoisomers, tautomers, resonance forms, a Markush library."""

    structure_set: StructureSetResult


@dataclass(frozen=True)
class NmrReferenceCalibrated(Event):
    """Published when a TMS reference-shielding calibration job
    (`QuantumChemistryService.request_reference_calibration`, Phase 22)
    finishes — `values` maps element symbol ("H"/"C") to its averaged
    reference shielding, empty with `error` set on failure/cancellation.
    """

    method_basis: str
    provider_id: str
    values: dict[str, float]
    error: str | None = None


@dataclass(frozen=True)
class AlignmentJobStateChanged(Event):
    """Progress for an ensemble 3D-alignment run (`AlignmentService`).

    Keyed on the REFERENCE molecule's uuid, since that is what identifies
    the run -- an ensemble alignment has no single subject molecule the
    way conformer generation or docking does.
    """

    reference_uuid: str
    state: CacheState
    message: str = ""


@dataclass(frozen=True)
class EnsembleAlignmentReady(Event):
    """One finished ensemble alignment: the reference first, then every
    probe in the order requested. Entries that could not be aligned carry
    an `error` instead of scores, so a single bad structure is reported
    rather than discarding the rest of the run."""

    reference_uuid: str
    entries: list[EnsembleEntry]
    method: str
    accuracy: str
