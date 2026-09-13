"""The session's retained results: fed by dispatchers, read by selection.

**WHAT THIS STOPS.** Selecting a molecule cleared the Properties panel and
ran the always-on set again, every time -- so moving between two molecules
recomputed both, and a calculator somebody had run by hand was gone the
moment they looked at another structure. This service keeps every recorded
result for the life of the project and replays whatever still describes the
structure, and it is also what the project file's `calculation_results`
block is written from.

**IT LISTENS TO THE ENVELOPES ONLY** (`ResultRecorded`,
`AutomaticPartFinished`). The result events carry no identity, and a store
that inferred one from them is the store this design exists not to be.

**REPLAY IS THE SAME EVENTS, NOT A PANEL BRANCH.** `replay` publishes each
stored result as the event it originally arrived as, so every renderer
handles a restored result through the handler it already has, and nothing
here knows any panel exists.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from openchem.chem.calculation_input import input_fingerprint
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import ReportResult, StructureReport
from openchem.domain.result_store import BundleState, ResultIdentity, SessionResultStore, StoredResult
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.events.base import EventBus
from openchem.services.result_identity import application_version
from openchem.events.events import (
    AlertComputed,
    AutomaticPartFinished,
    DescriptorComputed,
    PerAtomDataComputed,
    PhCurveComputed,
    ReportComputed,
    ResultRecorded,
    SpectrumComputed,
    StructureSetComputed,
    TrajectoryComputed,
)

logger = logging.getLogger("openchem.result_store")

#: The one calculator in the always-on set. See
#: `PropertyPanel._request_substance_perception`.
SUBSTANCE_PART = "substance_analysis"


def event_for(result: object, structure_version: int = 0, identity: ResultIdentity | None = None):
    """The event `result` originally arrived as, ready to publish again.

    **AND THE INPUT IT DESCRIBES**, for the two events that carry one. The
    stored `identity` is the only record of which structure a per-atom
    dataset's indices refer to; replaying the dataset without it would hand
    the Atom Inspector values it has to treat as unverifiable.

    **A `StructureReport` IS RE-STAMPED WITH THE CURRENT VERSION**, forcibly.
    `status_of` reads staleness off the result, and the version it carries
    is a counter from whichever session computed it -- meaningless now. A
    replay only happens after the input fingerprint has matched, which is
    the claim the stamp stands for, so the stamp is true. (Not
    `descriptor_service._with_structure_version`: it deliberately leaves a
    non-zero stamp alone, and every restored report has one.)
    """
    if isinstance(result, StructureReport):
        result = replace(result, structure_version=structure_version)
    if isinstance(result, DescriptorValue):
        return DescriptorComputed(descriptor=result)
    if isinstance(result, ReportResult):
        return ReportComputed(report=result)
    if isinstance(result, AlertResult):
        return AlertComputed(alert=result)
    fingerprint = identity.input_fingerprint if identity is not None else ""
    calculation_input = identity.calculation_input if identity is not None else ""
    if isinstance(result, PerAtomDataset):
        return PerAtomDataComputed(
            dataset=result, input_fingerprint=fingerprint, calculation_input=calculation_input
        )
    if isinstance(result, SpectrumResult):
        return SpectrumComputed(
            spectrum=result, input_fingerprint=fingerprint, calculation_input=calculation_input
        )
    if isinstance(result, StructureSetResult):
        return StructureSetComputed(structure_set=result)
    if isinstance(result, PhCurveResult):
        return PhCurveComputed(curve=result)
    if isinstance(result, TrajectoryResult):
        return TrajectoryComputed(trajectory=result)
    raise TypeError(f"No event for {type(result).__name__}")


class ResultStoreService:
    def __init__(self, event_bus: EventBus, engine: ChemistryEngine) -> None:
        self._event_bus = event_bus
        self._engine = engine
        self._project: ProjectModel | None = None
        self.store = SessionResultStore("")
        #: Called with the molecule uuid whenever a NEW result is retained --
        #: how the session learns it has something unsaved. Plain callables
        #: held here, not Qt connections.
        self._on_recorded: list[Callable[[str], None]] = []
        event_bus.subscribe(ResultRecorded, self._on_result_recorded)
        event_bus.subscribe(AutomaticPartFinished, self._on_part_finished)

    # --- lifecycle ----------------------------------------------------------

    def set_project(self, project: ProjectModel | None, store: SessionResultStore | None = None) -> None:
        """Start a new project's store -- the lifecycle boundary.

        A result still in flight from the previous project arrives after
        this, for a molecule this project does not have, and is ignored.
        """
        self._project = project
        uuid = project.uuid if project is not None else ""
        if store is not None and store.project_uuid == uuid:
            self.store = store
        else:
            if store is not None:
                logger.warning("Ignoring a result store for project %s", store.project_uuid)
            self.store = SessionResultStore(uuid)

    def add_recorded_listener(self, callback: Callable[[str], None]) -> None:
        self._on_recorded.append(callback)

    def _belongs(self, molecule_uuid: str) -> bool:
        return self._project is not None and self._project.find_molecule(molecule_uuid) is not None

    def _on_result_recorded(self, event: ResultRecorded) -> None:
        molecule_uuid = event.stored.identity.molecule_uuid
        if not self._belongs(molecule_uuid):
            return
        self.store.put(event.stored)
        for callback in list(self._on_recorded):
            callback(molecule_uuid)

    def _on_part_finished(self, event: AutomaticPartFinished) -> None:
        if not self._belongs(event.molecule_uuid):
            return
        self.store.record_part(event.molecule_uuid, event.part)

    # --- asking -------------------------------------------------------------

    def fingerprints_for(self, model: MoleculeModel) -> dict[str, str]:
        """The molecule's CURRENT fingerprint for each calculation input.

        GEOMETRY is left out when it cannot be worked out, rather than
        guessed: a result nothing can vouch for is simply not replayed.
        """
        fingerprints = {DRAWING: input_fingerprint(self._engine, model, DRAWING)}
        try:
            fingerprints[GEOMETRY] = input_fingerprint(self._engine, model, GEOMETRY)
        except Exception:  # noqa: BLE001 - an unreadable structure replays nothing
            logger.debug("No geometry fingerprint for %s", model.uuid, exc_info=True)
        return fingerprints

    def project_fingerprints(self) -> dict[str, dict[str, str]]:
        """Every molecule's current fingerprints, for writing a file."""
        if self._project is None:
            return {}
        found: dict[str, dict[str, str]] = {}
        for molecule in self._project.molecules:
            try:
                found[molecule.uuid] = self.fingerprints_for(molecule)
            except Exception:  # noqa: BLE001 - one bad molecule must not block a save
                logger.exception("Could not fingerprint %s; its results will not be saved", molecule.uuid)
        return found

    def automatic_state(self, model: MoleculeModel, expected_parts: set[str]) -> tuple[BundleState, set[str]]:
        return self.store.bundle_state(
            model.uuid,
            input_fingerprint(self._engine, model, DRAWING),
            expected_parts,
            application_version(),
        )

    def replay(self, model: MoleculeModel, structure_version: int = 0) -> list[StoredResult]:
        """Publish every still-fresh result for `model`. Returns what was sent."""
        fresh = self.store.fresh_results(model.uuid, self.fingerprints_for(model))
        sent: list[StoredResult] = []
        for stored in fresh:
            try:
                event = event_for(stored.result, structure_version, stored.identity)
            except TypeError:
                logger.warning("Cannot replay %s", stored.identity.result_id)
                continue
            self._event_bus.publish(event)
            sent.append(stored)
        return sent
