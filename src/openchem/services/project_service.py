from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, NamedTuple

from openchem.domain.project import SCHEMA_VERSION, ProjectModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRunStore
from openchem.domain.recipe_run import RecipeRunStore
from openchem.domain.result_store import SessionResultStore
from openchem.domain.score_definition_store import ScoreDefinitionStore
from openchem.domain.synthesis_plan_store import SynthesisPlanStore
from openchem.events.base import EventBus
from openchem.events.events import ProjectClosed, ProjectLoaded

logger = logging.getLogger("openchem.project")

#: The key the retained calculation results are written under.
RESULTS_KEY = "calculation_results"
#: The key the durable QC run history is written under -- a separate block
#: from RESULTS_KEY because it is a separate collection with different
#: retention semantics; see `domain/quantum_chemistry_run.py`.
QC_RUNS_KEY = "quantum_chemistry_runs"
#: The key the recipe run history is written under -- a block of its own, for the reason the QC runs have one:
#: a recipe's answer must survive exactly the edit that makes it stale; see `domain/recipe_run.py`.
RECIPE_RUNS_KEY = "recipe_runs"
#: The key the user's derived-score definitions are written under. Written only when there is something to write (`ScoreDefinitionStore.is_empty`), so a project that
#: never used scores is the file it always was; see `domain/score_definition_store.py` for what happens to definitions a build cannot read.
DERIVED_SCORES_KEY = "derived_scores"
#: The key the synthesis plans (routes found, or none found) are written under. Written only when there is a plan to write, so a project that never planned a synthesis is the file it always was; see
#: `domain/synthesis_plan_store.py` for what happens to an entry a build cannot read.
SYNTHESIS_PLANS_KEY = "synthesis_plans"


class ProjectDocument(NamedTuple):
    """Everything one read of a project file yields.

    A tuple, so the unpacking callers already do keeps working, but one that grows by NAME: the fourth block
    (`recipe_runs`) broke every three-way unpack, and the next one should break none that reads by attribute.
    """

    project: ProjectModel
    results: SessionResultStore
    qc_runs: QuantumChemistryRunStore
    recipe_runs: RecipeRunStore
    derived_scores: ScoreDefinitionStore
    synthesis_plans: SynthesisPlanStore


class ProjectService:
    """Load/save ProjectModel as `.ocsproj` JSON.

    `_migrate` is the seam for schema changes: because ProjectModel already
    carries `schema_version`, a future on-disk format change is a new branch
    here, not a breaking change to every project file ever saved.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def save(
        self,
        project: ProjectModel,
        path: Path,
        results: SessionResultStore | None = None,
        current_fingerprints: dict[str, dict[str, str]] | None = None,
        qc_runs: QuantumChemistryRunStore | None = None,
        recipe_runs: RecipeRunStore | None = None,
        derived_scores: ScoreDefinitionStore | None = None,
        synthesis_plans: SynthesisPlanStore | None = None,
    ) -> None:
        path.write_text(
            self.serialise(project, results, current_fingerprints, qc_runs, recipe_runs, derived_scores, synthesis_plans),
            encoding="utf-8",
        )
        logger.info("Saved project %s to %s", project.uuid, path)

    def serialise(
        self,
        project: ProjectModel,
        results: SessionResultStore | None = None,
        current_fingerprints: dict[str, dict[str, str]] | None = None,
        qc_runs: QuantumChemistryRunStore | None = None,
        recipe_runs: RecipeRunStore | None = None,
        derived_scores: ScoreDefinitionStore | None = None,
        synthesis_plans: SynthesisPlanStore | None = None,
    ) -> str:
        """The file's text. Shared by Save and the recovery writer.

        **THE RESULTS ARE AN ENVELOPE BESIDE THE DOCUMENT, NOT PART OF IT.**
        `ProjectModel` stays what it was -- structures, notes, history --
        and `calculation_results` is written next to its fields by this
        service. A file without the block is an ordinary project; an older
        build reading a file with one ignores a key it does not know.

        `qc_runs` is a SEPARATE envelope from `results` -- unlike `results`,
        it is written unconditionally (no `current_fingerprints` pruning);
        see `domain/quantum_chemistry_run.py` for why. `recipe_runs` is the same kind of envelope, for the same
        reason (`domain/recipe_run.py`).
        """
        # Explicit UTF-8 on both sides: a project file is meant to move
        # between machines, and Python's default is the PLATFORM encoding
        # (cp1252 on Windows). This is safe today only because
        # json.dumps defaults to ensure_ascii=True; the day anything
        # non-ASCII reaches the file it would break silently and
        # asymmetrically depending on who saved it.
        data = project.to_dict()
        if results is not None:
            data[RESULTS_KEY] = results.to_dict(current_fingerprints)
        if qc_runs is not None:
            data[QC_RUNS_KEY] = qc_runs.to_dict()
        if recipe_runs is not None:
            data[RECIPE_RUNS_KEY] = recipe_runs.to_dict()
        if derived_scores is not None and not derived_scores.is_empty:
            data[DERIVED_SCORES_KEY] = derived_scores.to_dict()
        if synthesis_plans is not None and not synthesis_plans.is_empty:
            data[SYNTHESIS_PLANS_KEY] = synthesis_plans.to_dict()
        return json.dumps(data, indent=2)

    def load(self, path: Path) -> ProjectModel:
        return self.load_document(path)[0]

    def load_document(self, path: Path) -> ProjectDocument:
        """The project AND its saved results, from one read of the file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        document = self.parse(data)
        self._event_bus.publish(ProjectLoaded(project_uuid=document.project.uuid))
        logger.info("Loaded project %s from %s", document.project.uuid, path)
        if document.results.load_problems:
            logger.warning("Saved results not restored: %s", dict(document.results.load_problems))
        if document.recipe_runs.load_problems:
            logger.warning("Saved recipe runs not restored: %s", document.recipe_runs.load_problems)
        if document.derived_scores.load_problems:
            logger.warning("Saved score definitions kept but not used: %s", document.derived_scores.load_problems)
        if document.synthesis_plans.load_problems:
            logger.warning("Saved synthesis plans not restored: %s", document.synthesis_plans.load_problems)
        return document

    def parse(self, data: dict[str, Any]) -> ProjectDocument:
        data = self._migrate(data)
        project = ProjectModel.from_dict(data)
        # `.get` with no default block, like `crystals`: a project saved
        # before results were kept loads with an empty store.
        results = SessionResultStore.from_dict(data.get(RESULTS_KEY), project.uuid)
        qc_runs = QuantumChemistryRunStore.from_dict(data.get(QC_RUNS_KEY), project.uuid)
        recipe_runs = RecipeRunStore.from_dict(data.get(RECIPE_RUNS_KEY), project.uuid)
        derived_scores = ScoreDefinitionStore.from_dict(data.get(DERIVED_SCORES_KEY), project.uuid)
        synthesis_plans = SynthesisPlanStore.from_dict(data.get(SYNTHESIS_PLANS_KEY), project.uuid)
        return ProjectDocument(project, results, qc_runs, recipe_runs, derived_scores, synthesis_plans)

    def close(self, project: ProjectModel) -> None:
        self._event_bus.publish(ProjectClosed(project_uuid=project.uuid))

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        schema_version = data.get("schema_version", SCHEMA_VERSION)
        if schema_version > SCHEMA_VERSION:
            raise ValueError(
                f"Project schema version {schema_version} is newer than this "
                f"application supports ({SCHEMA_VERSION})"
            )
        # No migrations exist yet — this is where a schema_version 1 -> 2
        # transform would be added once the on-disk format actually changes.
        return data
