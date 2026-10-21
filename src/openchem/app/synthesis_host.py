"""The window's side of `context.synthesis` (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 8): the selected molecule, the planning service, the planner's setting and the drawing of a step, as the plain calls
`plugins/synthesis_access.py` describes.

It decides nothing. A plan is started only through `SynthesisPlanningService.request_plan`, where the regulatory gate runs first, so no path through here can start a planner process the gate has not
allowed; this object adds no check of its own and has no way round that one. It holds no state of its own either: every answer is read from the session, the service or the settings as they are now.

THE CHOICES ARE THE EXTERNAL TOOLS SETTINGS (`aizynthfinder/expansion`, `/stock`, `/filter`), not a second copy of them: choosing in the panel writes the key the planning service's provider reads on its next
request, and a person who sets one by hand sees the panel follow it. A plan under way keeps the setup it was captured with (`SynthesisPlanningService` freezes it before the worker starts).
"""

from __future__ import annotations

from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.chem.reaction_depiction import render_step_svg
from openchem.domain.molecule import MoleculeModel
from openchem.domain.synthesis_route import RouteStep
from openchem.plugins.synthesis_access import CHOICES, SynthesisTarget
from openchem.services.container import ServiceContainer
from openchem.services.synthesis_planner_setup import EXPANSION_KEY, FILTER_KEY, NO_FILTER, STOCK_KEY, PlannerOptions
from openchem.services.synthesis_planning_service import BoundResult, RequestOutcome

#: The settings key each choice is stored under.
_KEYS = {"expansion": EXPANSION_KEY, "stock": STOCK_KEY, "filter": FILTER_KEY}

#: What `options` answers when this build has no planner setting at all (a container built without one).
_NOT_BUILT = PlannerOptions(ok=False, problem="This build has no synthesis planner.")


class SynthesisHost:
    """See the module docstring. Satisfies `plugins.synthesis_access.SynthesisHost`."""

    def __init__(self, services: ServiceContainer, session: SessionManager, settings: Settings) -> None:
        self._services = services
        self._session = session
        self._settings = settings

    def _molecule(self, molecule_uuid: str) -> MoleculeModel | None:
        project = self._session.project
        return project.find_molecule(molecule_uuid) if project is not None else None

    def target(self) -> SynthesisTarget | None:
        uuid = self._session.selected_molecule_uuid
        return self.structure_of(uuid) if uuid else None

    def structure_of(self, molecule_uuid: str) -> SynthesisTarget | None:
        molecule = self._molecule(molecule_uuid)
        if molecule is None or not (molecule.canonical_smiles or "").strip():
            return None
        return SynthesisTarget(molecule_uuid=molecule.uuid, display_name=molecule.display_name, canonical_smiles=molecule.canonical_smiles)

    def result_for(self, molecule_uuid: str) -> BoundResult | None:
        service = self._services.synthesis_planning_service
        molecule = self._molecule(molecule_uuid)
        if service is None or molecule is None:
            return None
        return service.result_for(molecule)

    def is_planning(self, molecule_uuid: str) -> bool:
        service = self._services.synthesis_planning_service
        return service is not None and service.is_planning(molecule_uuid)

    def setup_is_warm(self) -> bool:
        setup = self._services.synthesis_setup
        return setup is not None and setup.is_warm()

    def options(self) -> PlannerOptions:
        setup = self._services.synthesis_setup
        return setup.options() if setup is not None else _NOT_BUILT

    def depict(self, step: RouteStep) -> str:
        return render_step_svg(step)

    def request_plan(self, molecule_uuid: str, requested_by: str) -> RequestOutcome:
        service = self._services.synthesis_planning_service
        molecule = self._molecule(molecule_uuid)
        if service is None or molecule is None:
            return RequestOutcome.REJECTED
        return service.request_plan(molecule, requested_by=requested_by)

    def cancel(self, molecule_uuid: str) -> bool:
        service = self._services.synthesis_planning_service
        return service is not None and service.cancel(molecule_uuid)

    def choose(self, section: str, name: str | None) -> None:
        if section not in CHOICES:
            raise ValueError(f"there is nothing to choose in {section!r}")
        self._settings.set(_KEYS[section], NO_FILTER if section == "filter" and not name else name)
