"""The host's side of the recipes: it knows the open project, its stored runs and the chemistry engine.

`docs/RECIPES_DESIGN.md` sections 5 and 8. The pure parts (`domain/recipe_run.py`, `domain/lewis_binder.py`,
`chem/lewis_pairing_eval.py`) are handed everything they know; this builds it, from the project as it is now, and
nothing else. It keeps no state of its own: the project and the runs belong to `ResultStoreService`.

**IT EVALUATES; IT DOES NOT RECORD OR START ANYTHING.** `evaluate_lewis_pairing` returns a `RecipeRun`; whoever
asked records it (`ResultStoreService.record_recipe_run`), so evaluating to LOOK at a pairing does not change the
project and does not mark it unsaved. And nothing here starts ORCA: the jobs a gap needs are run where they are run
today, which is Stage A of the design.
"""

from __future__ import annotations

from collections.abc import Mapping

from openchem.chem.calculation_input import resolve_calculation_input
from openchem.chem.engine import ChemistryEngine
from openchem.chem.lewis_pairing_eval import PairMember, evaluate_lewis_pairing
from openchem.chem.recipe_host import constitution_key, formal_charge, run_describes
from openchem.domain.calculator import DRAWING
from openchem.domain.lewis import ROLE_AUTO
from openchem.domain.lewis_binder import MoleculeFacts
from openchem.domain.recipe_run import Assessment, ProjectView, RecipeRun, assess
from openchem.services.result_store_service import ResultStoreService


class RecipeService:
    def __init__(self, result_store: ResultStoreService, engine: ChemistryEngine) -> None:
        self._store = result_store
        self._engine = engine

    def evaluate_lewis_pairing(
        self,
        first_uuid: str,
        second_uuid: str,
        *,
        method_basis: str,
        solvent: str = "",
        role: str = ROLE_AUTO,
        picks: Mapping[str, Mapping[str, str]] | None = None,
    ) -> RecipeRun:
        """The pairing of two project molecules at one level of theory, from their stored runs.

        `picks` is `{"first": {"sp": run_id}, "second": {"delta_scf": run_id}}`: a run the person CHOSE by id where
        several could be meant (an earlier geometry, two spin states). Raises `ValueError` for a molecule that is not
        in the open project, or an argument that is not one of the recipe's choices.
        """
        picks = picks or {}
        return evaluate_lewis_pairing(
            self._member(first_uuid, picks.get("first", {})),
            self._member(second_uuid, picks.get("second", {})),
            method_basis=method_basis,
            solvent=solvent,
            role=role,
        )

    def project_view(self) -> ProjectView:
        """The project as `recipe_run.assess` needs it, read now. A molecule whose drawing cannot be read has a key of
        None, which `assess` reports as unverifiable and never as unchanged."""
        project = self._store.project
        keys: dict[str, str | None] = {}
        for molecule in project.molecules if project is not None else ():
            try:
                keys[molecule.uuid] = constitution_key(resolve_calculation_input(self._engine, molecule, DRAWING).mol)
            except Exception:  # noqa: BLE001 - one unreadable molecule must not stop the others being compared
                keys[molecule.uuid] = None
        return ProjectView(constitution_keys=keys, qc_run_ids=self._store.qc_runs.run_ids())

    def assess(self, run: RecipeRun) -> Assessment:
        """Whether `run` still describes the project, and if not, every reason. Read now, never stored."""
        return assess(run, self.project_view())

    def _member(self, molecule_uuid: str, picks: Mapping[str, str]) -> PairMember:
        project = self._store.project
        if project is None:
            raise ValueError("no project is open")
        model = project.find_molecule(molecule_uuid)
        if model is None:
            raise ValueError(f"molecule {molecule_uuid} is not in the open project")
        mol = resolve_calculation_input(self._engine, model, DRAWING).mol
        runs = tuple(self._store.qc_runs.runs_for(molecule_uuid))
        facts = MoleculeFacts(
            molecule_uuid=molecule_uuid,
            label=model.display_name,
            runs=runs,
            fingerprints=self._store.fingerprints_for(model),
            describes={run.run_id: run_describes(run.input_molblock, mol) for run in runs},
            formal_charge=formal_charge(mol),
            picks=dict(picks),
        )
        return PairMember(facts=facts, mol=mol, constitution_key=constitution_key(mol))
