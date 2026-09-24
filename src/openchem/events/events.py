from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.alignment import EnsembleEntry
from openchem.domain.common import CacheState
from openchem.domain.nmr import ScalingFactors
from openchem.domain.conformer import ConformerModel
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.docking import DockingResultModel
from openchem.domain.structure_issue import CheckerResult
from openchem.domain.report import ReportResult
from openchem.domain.result_store import BundlePart, StoredResult
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
    """A molecule's structure or identity changed.

    `during_edit` is True for a CANVAS EDIT in progress -- the person is drawing and
    more edits may follow within moments -- and only for that. Everything that wants
    to recompute because of it waits for `RecalculationDue` instead of acting on this
    event; everything that only has to KNOW the structure moved (the version bump, the
    explorer's label, the results going stale) acts on it at once. An undo, a redo, an
    import, a rename and a conformer command are deliberate single actions and publish
    it False, so they recompute immediately as they always did.
    """

    molecule_uuid: str
    during_edit: bool = False


@dataclass(frozen=True)
class RecalculationDue(Event):
    """The quiet period after a canvas edit has passed: recompute `molecule_uuid` now.

    Published by `RecalcScheduler`, and by its "recalculate now" for a person who asked
    for results only on request. It names the molecule and nothing else: a consumer
    reads the CURRENT structure when it runs, so a run that fires after a further edit
    or an undo is redundant rather than wrong.
    """

    molecule_uuid: str


@dataclass(frozen=True)
class MoleculeSelected(Event):
    molecule_uuid: str | None


@dataclass(frozen=True)
class CrystalSelected(Event):
    """A crystal was picked in the project tree.

    **Its own event, not `MoleculeSelected` with a crystal's uuid.** A
    crystal is not a molecule (see `domain/crystal.py`), and every panel
    that subscribes to `MoleculeSelected` would look the uuid up in
    `project.molecules`, find nothing, and quietly show the previous
    molecule's results beside a crystal's name. That is the same
    index-space confusion a crystal click in the 3D viewer already had.
    """

    crystal_uuid: str | None


@dataclass(frozen=True)
class CrystalChanged(Event):
    """A crystal was renamed, added or removed.

    Its own event rather than `MoleculeChanged`, on the same reasoning as
    `CrystalSelected`: a panel refreshing on a molecule change should not
    be woken by a crystal, and a crystal uuid must never be looked up in
    `project.molecules`.
    """

    crystal_uuid: str | None


@dataclass(frozen=True)
class FormulationSelected(Event):
    """An energetic formulation was picked in the project tree.

    **Its own event, on exactly the reasoning `CrystalSelected` records.**
    A formulation is not a molecule (see `domain/formulation.py`), so
    every panel subscribing to `MoleculeSelected` would look this uuid up
    in `project.molecules`, find nothing, and go on showing the previous
    molecule's results beside a mixture's name. That is the same
    index-space confusion twice already paid for here.
    """

    formulation_uuid: str | None


@dataclass(frozen=True)
class FormulationChanged(Event):
    """A formulation was added, edited or removed.

    Its own event rather than `MoleculeChanged`, on the same reasoning as
    `FormulationSelected`: a panel refreshing on a molecule change should
    not be woken by a recipe, and a formulation uuid must never be looked
    up in `project.molecules`.
    """

    formulation_uuid: str | None


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
    """One descriptor's state changed (queued, running, completed or failed).

    `structure_version` is the version the run was dispatched against, for the reason
    `AlertComputed.structure_version` gives. None means the producer did not say (a
    replayed result, an ORCA-derived value, a test double).
    """

    descriptor: DescriptorValue
    structure_version: int | None = None


@dataclass(frozen=True)
class AlertComputed(Event):
    """An alert catalogue finished.

    `structure_version` is the version the run was DISPATCHED against, read on the
    calling thread before the worker started. An `AlertResult` has no field to carry it,
    so it travels here; a consumer that stamped arrival time instead made an alert
    computed for structure A read as current for B whenever an edit landed mid-run --
    which a pause-then-refresh recompute makes routine. None means the producer did not
    say (a replayed result, a test double), and the consumer falls back to the version
    now.
    """

    alert: AlertResult
    structure_version: int | None = None


@dataclass(frozen=True)
class SpatialAnnotationsReady(Event):
    """Shape-valued geometry recomputed for ONE displayed conformer.

    Carries everything needed to decide whether it is still wanted:
    `token` is the requesting cell's own counter, and `structure_key` and
    `conformer_index` say which geometry it describes. A consumer checks
    all of it before drawing -- the producers cannot be interrupted, so a
    superseded job still finishes and still publishes, and rejecting it
    on arrival is what stops one conformer's geometry appearing on
    another.

    `diagnostics` says what could NOT be drawn and why (an unresolvable
    calculator, missing recorded parameters, a producer that declined
    this conformer), because an arrow silently absent and an arrow that
    was never possible are different states.
    """

    molecule_uuid: str
    structure_key: str
    conformer_index: int
    cell_index: int
    token: int
    annotations: tuple = ()
    diagnostics: tuple = ()


@dataclass(frozen=True)
class ReportComputed(Event):
    """A calculator produced a fact-based report.

    Separate from `AlertComputed` rather than replacing it: an alert
    catalog and a report are different claims, and one event carrying both
    would put the distinction back into a field that consumers have to
    remember to read. See `domain/report.ReportResult`.
    """

    report: ReportResult


@dataclass(frozen=True)
class PerAtomDataComputed(Event):
    """A per-atom dataset, and WHICH INPUT its atom indices describe.

    **THE DISPATCHER KNOWS THE INPUT; THE DATASET DOES NOT.** A dataset is a
    dict of atom index -> value, and an index means nothing without the
    structure it indexes. The Atom Inspector used to hold these by property
    id alone and lay them over whatever was drawn NOW, so after an edit it
    showed an earlier structure's charges beside the current atoms.

    `input_fingerprint` is `chem.calculation_input`'s fingerprint of the
    exact input the calculator was handed, set by the code that resolved it
    (`descriptor_service`) or restored from the stored identity on replay.
    Empty means nobody said, and a structure-bound consumer must treat that
    as unverifiable rather than as current.
    """

    dataset: PerAtomDataset
    input_fingerprint: str = ""
    #: `domain.calculator.DRAWING` or `GEOMETRY` -- which input the
    #: fingerprint is OF, so a consumer can ask for the current one to
    #: compare with. Empty exactly when the fingerprint is.
    calculation_input: str = ""


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
    """A spectrum, with the identity of the input its atom indices describe.

    Same two fields as `PerAtomDataComputed`. Both producers stamp them: the
    descriptor service from the resolved calculation input, and the QC
    service from what each job was SUBMITTED with -- GEOMETRY for a single
    conformer, ENSEMBLE for a Boltzmann average over a conformer set. An
    empty identity therefore means a producer that could not vouch for its
    indices, and the Atom Inspector withholds it rather than assuming it
    current.
    """

    spectrum: SpectrumResult
    input_fingerprint: str = ""
    calculation_input: str = ""


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
class CalculationFinished(Event):
    """A dispatched calculator has stopped running, whatever it produced.

    **Carries the CALCULATOR's id, which no result event can.** A result
    is named after itself and the two are not always the same:
    `nmr_database` publishes a spectrum called `nmr_13c`, and
    `gasteiger_charge_at_ph` publishes `gasteiger_charge`. Anything
    tracking "what did I dispatch, and is it still going" therefore
    cannot use the result's id, which is why `_finish_batch_run` in the
    Properties panel had to describe itself as best-effort.

    Published in a `finally`, so it fires for a calculator that failed,
    raised, or returned an unpublishable type -- those are exactly the
    runs whose indicator would otherwise stick on screen forever.
    """

    calculator_id: str
    molecule_uuid: str


@dataclass(frozen=True)
class StructureSetComputed(Event):
    """Published when a calculator produces a SET of structures (Phase 27)
    -- stereoisomers, tautomers, resonance forms, a Markush library."""

    structure_set: StructureSetResult


@dataclass(frozen=True)
class QmSurfaceComputed(Event):
    """Published when `orca_plot` has produced a QM volumetric surface --
    an ab initio ESP, electron density, spin density or molecular orbital.

    Carries the failure inline (`field is None` with `error` set) rather
    than as a separate event type, because every consumer that shows the
    surface is also the one that must show why it is missing, and the two
    arrive on the same subscription.
    """

    molecule_uuid: str
    surface_id: str
    field: object | None
    error: str = ""


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


@dataclass(frozen=True)
class NmrScalingCalibrated(Event):
    """Published when an empirical shift-scaling calibration
    (`QuantumChemistryService.request_scaling_calibration`) finishes.

    `factors` maps element symbol to its fitted line; empty with `error`
    set on failure, cancellation, or a fit too poor to trust. An element
    whose fit was refused is simply absent rather than present with a bad
    slope -- a partial calibration is a real, usable outcome (carbon often
    fits when hydrogen does not, and vice versa).
    """

    method_basis: str
    provider_id: str
    factors: dict[str, ScalingFactors]
    error: str | None = None


@dataclass(frozen=True)
class StructureChecked(Event):
    """A structure-analysis pass finished for one molecule.

    Carries the whole `CheckerResult` rather than a summary, so the panel,
    the status-bar indicator and any plugin listening all read the same
    object instead of three consumers re-deriving counts from each other.

    `result.structure_version` is what makes this safe to act on: a
    listener that has since seen a newer edit must discard this rather than
    display it. Editing is faster than checking, and a highlight pointing
    at the previous structure is at its most confusing exactly while
    somebody is drawing.
    """

    result: CheckerResult


@dataclass(frozen=True)
class ResultRecorded(Event):
    """A result, WITH the identity only its dispatcher knew.

    **AN ENVELOPE, PUBLISHED BESIDE THE RESULT EVENTS AND NOT INSTEAD OF
    THEM.** `ReportComputed`, `PerAtomDataComputed` and the rest carry the
    result alone, and no result says which calculator made it or which
    structure it was computed on. Rather than teach a store to reconstruct
    that per result type, the one place that knows it says so once.

    Renderers keep listening to the result events; only the result store
    listens to this.
    """

    stored: StoredResult


@dataclass(frozen=True)
class AutomaticPartFinished(Event):
    """One producer of the always-on set has finished, and what it made.

    The manifest half of `ResultRecorded`: without it a lost result is an
    absence nobody can see. See `domain/result_store.BundlePart`.
    """

    molecule_uuid: str
    part: BundlePart
