"""The host's side of the derived scores: it knows the open project, the definitions it holds, and the stored results they are read from.

`docs/DERIVED_SCORES_DESIGN.md` sections 5, 7 and 8. The pure parts (`domain/score_definition.py`, `score_definition_store.py`, `score_value.py`) are
handed everything they know; this builds it from the project as it is now, and nothing else.

**IT EVALUATES; IT NEVER STARTS A CALCULATION.** A score reads the molecule's current results and refuses when one is missing. Making the missing result is a
person's decision, taken where calculations are started, with their execution policy; a score has none to decide, which is also why it is not a registered
calculator and does not appear in the calculator reference, the launcher or the assistant's calculator search.

**THE DEFINITIONS BELONG TO THE PROJECT, NOT TO THE RESULT STORE.** They are authored, they are saved in a block of their own, and they must survive exactly the edit
that makes a result stale. `ResultStoreService` is the lifecycle boundary for results; this is the one for definitions, swapped on the same call (`set_project`).

Changing a definition publishes `ScoreDefinitionsChanged`, which the window turns into "this project has unsaved work": a definition is never also a result, so
nothing else would tell it.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace

from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.score_answer import ScoreAnswer, project_score_answers
from openchem.domain.score_constants import Constant
from openchem.domain.score_definition import (
    ScoreDefinition,
    check_score_definition,
    new_score_id,
)
from openchem.domain.score_definition_store import ScoreDefinitionStore
from openchem.domain.score_formula import Formula
from openchem.domain.score_value import ScoreValue, evaluate_score
from openchem.domain.turn_snapshot import classify_results
from openchem.events.base import EventBus
from openchem.events.events import ScoreDefinitionsChanged
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.result_store_service import ResultStoreService

logger = logging.getLogger("openchem.scores")


class ScoreService:
    def __init__(
        self,
        event_bus: EventBus,
        result_store: ResultStoreService,
        calculator_registry: CalculatorRegistry,
        today: Callable[[], datetime.date] = datetime.date.today,
    ) -> None:
        self._event_bus = event_bus
        self._results = result_store
        self._registry = calculator_registry
        self._today = today
        self._project: ProjectModel | None = None
        self.store = ScoreDefinitionStore("")

    # --- lifecycle ----------------------------------------------------------

    def set_project(self, project: ProjectModel | None, store: ScoreDefinitionStore | None = None) -> None:
        """Start a project's definitions -- the lifecycle boundary, swapped with the result store's.

        A store read from a file for another project is ignored, as a result store is (`ResultStoreService.set_project`).
        """
        self._project = project
        uuid = project.uuid if project is not None else ""
        if store is not None and store.project_uuid == uuid:
            self.store = store
        else:
            if store is not None:
                logger.warning("Ignoring score definitions for project %s", store.project_uuid)
            self.store = ScoreDefinitionStore(uuid)

    @property
    def project(self) -> ProjectModel | None:
        return self._project

    # --- the rules ----------------------------------------------------------

    def reserved_names(self) -> tuple[str, ...]:
        """The names a label may not be close to: every registered calculator's id and display name, read now (the approved outputs' are added by the check)."""
        names: list[str] = []
        for definition in self._registry.definitions():
            names.extend((definition.calculator_id, definition.display_name))
        return tuple(names)

    def check(self, definition: ScoreDefinition) -> Formula:
        """The parsed formula, or a `FormulaError`: what the definition dialog shows as the person types."""
        return check_score_definition(definition, self.reserved_names())

    # --- making, changing and removing ----------------------------------------

    def _require_project(self) -> None:
        if self._project is None:
            raise ValueError("there is no open project to hold a score")

    def create(
        self,
        *,
        label: str,
        formula: str,
        result_unit: str,
        inputs: Sequence[tuple[str, str]],
        constants: Sequence[Constant] = (),
        owner: str = "",
        note: str = "",
    ) -> ScoreDefinition:
        """A new score in the open project. Raises `FormulaError` for a definition that does not check and `ValueError` for no project or no room."""
        self._require_project()
        definition = ScoreDefinition(
            score_id=new_score_id(label, self.store.score_ids()),
            label=label,
            formula=formula,
            result_unit=result_unit,
            inputs=tuple((str(name), str(output_id)) for name, output_id in inputs),
            constants=tuple(constants),
            owner=owner,
            created=self._today().isoformat(),
            note=note,
        )
        self.check(definition)
        self.store.add(definition)
        self._event_bus.publish(ScoreDefinitionsChanged(project_uuid=self._project.uuid, score_ids=(definition.score_id,)))
        return definition

    def update(self, score_id: str, **fields) -> ScoreDefinition:
        """A changed definition under the same id: any of the fields `ScoreDefinition` has except the format version and the date made.

        `created` keeps its date. Raises `KeyError` for a score that is not in the project (a kept one is not), `FormulaError` for a result that does not check.
        """
        self._require_project()
        current = self.store.get(score_id)
        if current is None:
            raise KeyError(score_id)
        for forbidden in ("schema_version", "created"):
            if forbidden in fields:
                raise ValueError(f"{forbidden} cannot be changed")
        changed = replace(current, **fields)
        self.check(changed)
        self.store.replace(changed)
        self._event_bus.publish(ScoreDefinitionsChanged(project_uuid=self._project.uuid, score_ids=(score_id,)))
        return changed

    def remove(self, score_id: str) -> bool:
        self._require_project()
        if not self.store.remove(score_id):
            return False
        self._event_bus.publish(ScoreDefinitionsChanged(project_uuid=self._project.uuid, score_ids=(score_id,)))
        return True

    # --- reading --------------------------------------------------------------

    def answers_for(self, molecule_uuid: str, structure_version: int) -> tuple[ScoreAnswer, ...]:
        """The reader entries for the scores of `molecule_uuid`: what the Results reader is handed each time it refreshes.

        `structure_version` is the molecule's current one; a score is evaluated against the structure as it is now, so it is never stamped with another.
        A molecule that is not in the open project has none.
        """
        if self._project is None:
            return ()
        model = self._project.find_molecule(molecule_uuid)
        if model is None:
            return ()
        return project_score_answers(self.values_for(model), viewing=molecule_uuid, structure_version=structure_version)

    def values_for(self, model: MoleculeModel) -> tuple[ScoreValue, ...]:
        """Every definition's value for `model`, from its stored results as they are now. Nothing is calculated and nothing is stored.

        A molecule with nothing drawn has no fingerprints, so every record reads as unverifiable and every score refuses, which is the truth.
        """
        definitions = self.store.definitions()
        if not definitions:
            return ()
        entries = self._classified_results(model)
        return tuple(evaluate_score(definition, entries) for definition in definitions)

    def preview(self, definition: ScoreDefinition, model: MoleculeModel) -> ScoreValue:
        """The value `definition` WOULD have for `model`, for a definition that is not in the project (a draft being typed). Nothing is stored and nothing is
        calculated; it is the same reading and the same refusals as a saved score gets."""
        return evaluate_score(definition, self._classified_results(model))

    def _classified_results(self, model: MoleculeModel):
        """`model`'s stored results, each classified as current, historical or unverifiable and as computed, refused or failed."""
        fingerprints: dict[str, str] = {}
        if model.molblock:
            try:
                fingerprints = self._results.fingerprints_for(model)
            except Exception:  # noqa: BLE001 - nothing can be vouched for without a fingerprint
                logger.debug("No fingerprints for %s", model.uuid, exc_info=True)
        records = self._results.store.all_results(model.uuid)
        fresh = self._results.store.fresh_results(model.uuid, fingerprints)
        return classify_results(records, fresh, fingerprints)
