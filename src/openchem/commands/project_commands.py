from __future__ import annotations

from pathlib import Path

from openchem.commands.base import OpenChemCommand
from openchem.domain.project import ProjectModel
from openchem.domain.quantum_chemistry_run import QuantumChemistryRunStore
from openchem.domain.recipe_run import RecipeRunStore
from openchem.domain.score_definition_store import ScoreDefinitionStore
from openchem.domain.result_store import SessionResultStore
from openchem.domain.synthesis_plan_store import SynthesisPlanStore
from openchem.services.project_service import ProjectService


class SaveProjectCommand(OpenChemCommand):
    """Saving to disk isn't meaningfully reversible; still expressed as a
    command so it appears wherever OpenChemCommands are logged or scripted.

    `results`, `current_fingerprints`, `qc_runs` and `recipe_runs` are optional so a caller
    with no result store saves exactly the file it always did.
    """

    def __init__(
        self,
        project_service: ProjectService,
        project: ProjectModel,
        path: Path,
        results: SessionResultStore | None = None,
        current_fingerprints: dict[str, dict[str, str]] | None = None,
        qc_runs: QuantumChemistryRunStore | None = None,
        recipe_runs: RecipeRunStore | None = None,
        derived_scores: ScoreDefinitionStore | None = None,
        synthesis_plans: SynthesisPlanStore | None = None,
    ) -> None:
        super().__init__(f"Save project '{project.name}'")
        self._project_service = project_service
        self._project = project
        self._path = path
        self._results = results
        self._current_fingerprints = current_fingerprints
        self._qc_runs = qc_runs
        self._recipe_runs = recipe_runs
        self._derived_scores = derived_scores
        self._synthesis_plans = synthesis_plans

    def redo(self) -> None:
        self._project_service.save(
            self._project, self._path, self._results, self._current_fingerprints, self._qc_runs,
            self._recipe_runs, self._derived_scores, self._synthesis_plans,
        )

    def undo(self) -> None:
        pass


class OpenProjectCommand(OpenChemCommand):
    """The loaded project is available on `.loaded_project` after push(),
    since QUndoStack.push() calls redo() synchronously -- its saved results
    on `.loaded_results`, its saved QC run history on `.loaded_qc_runs` and its recipe runs on
    `.loaded_recipe_runs`, all from the same read of the file.
    """

    def __init__(self, project_service: ProjectService, path: Path) -> None:
        super().__init__(f"Open project '{path.name}'")
        self._project_service = project_service
        self._path = path
        self.loaded_project: ProjectModel | None = None
        self.loaded_results: SessionResultStore | None = None
        self.loaded_qc_runs: QuantumChemistryRunStore | None = None
        self.loaded_recipe_runs: RecipeRunStore | None = None
        self.loaded_derived_scores: ScoreDefinitionStore | None = None
        self.loaded_synthesis_plans: SynthesisPlanStore | None = None

    def redo(self) -> None:
        document = self._project_service.load_document(self._path)
        self.loaded_project = document.project
        self.loaded_results = document.results
        self.loaded_qc_runs = document.qc_runs
        self.loaded_recipe_runs = document.recipe_runs
        self.loaded_derived_scores = document.derived_scores
        self.loaded_synthesis_plans = document.synthesis_plans

    def undo(self) -> None:
        if self.loaded_project is not None:
            self._project_service.close(self.loaded_project)
