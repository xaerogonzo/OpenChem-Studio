from __future__ import annotations

from typing import Any

from rdkit import Chem

from openchem.chem import components
from openchem.domain.calculator import CalculationRefusal, CalculatorDefinition, RegistryExecution, active_parameters
from openchem.domain.calculator_taxonomy import assign_plugin_category_group
from openchem.domain.common import ScientificResult
from openchem.domain.refusal_kinds import RefusalKind
from openchem.domain.structure_coverage import Coverage, CoverageKind, as_coverage


class CalculatorRegistry:
    """Metadata + dispatch lookup for registered calculators (Charge,
    LogP, Molar Refractivity, pKa, plus Docking/QuantumChemistry as
    discovery-only entries since Phase 21) -- pure bookkeeping, it never
    runs anything itself or touches threads/events. `DescriptorService`
    does that (`run_calculator`), the same way it already does for the
    eager descriptor batch.

    Deliberately standalone (constructor-injected, same composition-root
    pattern `JobManager` already follows) rather than nested inside
    `DescriptorService`, so other consumers (menus, a future AI assistant,
    a scripting API) can query "what calculators exist" independently of
    how descriptors happen to be computed today.

    Not every registered calculator is runnable through `compute()` --
    `CalculatorDefinition.execution` says how each one actually runs
    (`RegistryExecution`, dispatchable here, or `ServiceExecution`, owned
    by its own service/panel and registered for discovery only). See
    `domain/calculator.py`.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, CalculatorDefinition] = {}

    def register(self, definition: CalculatorDefinition) -> None:
        self._definitions[definition.calculator_id] = definition
        # A plugin may say which task group its NEW category is browsed under;
        # one this application already files, or an unknown group, is ignored.
        assign_plugin_category_group(definition.category, definition.task_group)

    def get(self, calculator_id: str) -> CalculatorDefinition | None:
        return self._definitions.get(calculator_id)

    def definitions(self) -> list[CalculatorDefinition]:
        """Every registered calculator, in registration order -- a copy, safe to iterate from a
        thread while a plugin registers another."""
        return list(self._definitions.values())

    def compute(
        self, calculator_id: str, mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any]
    ) -> ScientificResult:
        """Raises KeyError if `calculator_id` isn't registered, or
        ValueError if it's registered but not `RegistryExecution`-backed
        (e.g. Docking/QuantumChemistry, owned by their own services) --
        callers (`DescriptorService.run_calculator`) are expected to check
        `get()` first and report a clear failure rather than let either
        reach the GUI thread. `molecule_uuid` is threaded through
        explicitly (not stamped onto the result afterward) to match the
        existing `DescriptorProvider.compute(mol, molecule_uuid)`
        convention every other provider already follows."""
        definition = self._definitions[calculator_id]
        execution = definition.execution
        if not isinstance(execution, RegistryExecution):
            raise ValueError(
                f"Calculator {calculator_id!r} is service-executed "
                f"({execution.service_name}) -- not dispatchable via "
                f"CalculatorRegistry.compute(); run it through its own "
                f"service/panel ({execution.panel_name}) instead."
            )
        # A greyed-out parameter never reaches the calculator, whichever route asked.
        active = active_parameters(definition, parameters)
        if definition.scope is None:
            # Unscoped: today's behaviour, the whole drawing. The registry
            # guard (tests/test_multicomponent_scope.py) keeps every shipped
            # definition out of this branch; a test double may still use it.
            return execution.compute(mol, molecule_uuid, active)
        # WHICH COMPONENTS, decided HERE and nowhere else, so Properties,
        # Batch and the 3D overlay cannot select differently. A refusal
        # raises `CalculationRefusal` with its code, which each caller
        # already catches as a calculator failure.
        selection = components.select(mol, definition.scope, definition.display_name)
        result = execution.compute(selection.mol, molecule_uuid, active)
        return components.read_back(result, definition.scope, selection)

    def coverage(
        self, calculator_id: str, mol: Chem.Mol, *, shared: dict | None = None
    ) -> Coverage | None:
        """Whether this calculator takes `mol`: covered, covered with a limit, certain to refuse, or None (no claim).

        **THE SCOPE IS APPLIED FIRST, BY THE VERY CALL A RUN MAKES** (`components.select`), so a salt handed to
        a pure-substance method, a structure with no carbon handed to an organic one, or a metal complex handed
        to a parent-compound one reads REFUSES here with the refusal's own sentence, for every calculator that
        declares such a scope and with no rule written for any of them. A scope that lets the structure
        through says nothing, because the calculator may still refuse for its own reasons; only a declared
        hook can say COVERED, and it is handed the component the run would be.

        `shared` is one pass's memory of the scope step, handed to every calculator asked about the same
        `mol`: about twenty calculators take ChEMBL's parent of a salt or refuse a metal complex the same way,
        and that was nearly all of the 141 and 208 ms a salt and ferrocene cost across all of them. A refusal
        is kept with the name it was raised for and reworded for the next calculator, because its sentence
        opens with that name and is otherwise identical.

        Never raises: a check that cannot be made is not a claim.
        """
        definition = self._definitions.get(calculator_id)
        if definition is None:
            return None
        try:
            target = mol
            if definition.scope is not None:
                # The note is in the key because a refusal's sentence ends with it.
                key = (definition.scope.selection, definition.scope.domain, definition.scope.note)
                if shared is None or key not in shared:
                    try:
                        outcome: Any = components.select(mol, definition.scope, definition.display_name)
                    except CalculationRefusal as refusal:
                        outcome = (refusal, definition.display_name)
                    if shared is not None:
                        shared[key] = outcome
                else:
                    outcome = shared[key]
                if isinstance(outcome, tuple):
                    refusal, raised_for = outcome
                    if refusal.kind is not RefusalKind.LIMIT:
                        return None
                    sentence = refusal.detail or refusal.summary
                    return Coverage.refuses(sentence.replace(raised_for, definition.display_name))
                target = outcome.mol
                chosen = outcome.note
            else:
                chosen = ""
            if definition.preflight is None:
                return None
            # A copy: `target` may be shared with the next calculator asked, and a hook that edited it would answer for them.
            answer = as_coverage(definition.preflight(Chem.Mol(target)))
            if answer is None or not chosen or answer.kind is CoverageKind.REFUSES:
                return answer
            # The hook accepted the component that was CHOSEN for the drawing, so the row says so rather than "Can run".
            return Coverage.caveat(chosen if answer.kind is CoverageKind.COVERED else f"{answer.reason} {chosen}")
        except Exception:  # noqa: BLE001 - see the docstring
            return None

    def preflight(self, calculator_id: str, mol: Chem.Mol) -> str:
        """Why this calculator is certain to refuse `mol`, or "" when nothing is known to.

        The refusal half of `coverage`, kept for the callers that only ask that question.
        """
        coverage = self.coverage(calculator_id, mol)
        return coverage.reason if coverage is not None and coverage.kind is CoverageKind.REFUSES else ""

    def by_category(self, category: str) -> list[CalculatorDefinition]:
        return [d for d in self._definitions.values() if d.category == category]

    def display_order(self, calculator_id: str) -> int | None:
        """Where this calculator sits among the registered ones, or None.

        **REGISTRATION ORDER IS THE RESULTS ORDER INSIDE A SECTION -- NOT THE
        PROPERTIES ORDER ANY MORE.** Properties browses A-Z within a category
        (`calculator_taxonomy.calculator_browse_sort_key`); this editorial
        order stays what the Results reader sorts by, so a result list does not
        silently reorder when the launcher was alphabetised. `by_category`
        still returns dict values in registration order. It makes that order
        askable, so Results can sort by it instead of inventing a second answer.

        That order carries real editorial judgement rather than being an
        accident of import: within a section, Solubility is registered ahead
        of Hansen Solubility Parameters and Lewis Sites ahead of Lewis Adduct,
        both of which alphabetical order inverts. See
        `domain/result_ordering.py`, which measures what dropping it costs.

        None for an id nothing registers -- a plugin report, or a retired id
        read back from a saved project. That is a real answer rather than a
        failure, and the ordering key has two further terms for exactly it.
        """
        for position, definition in enumerate(self._definitions.values()):
            if definition.calculator_id == calculator_id:
                return position
        return None

    def categories(self) -> list[str]:
        """Every distinct category with at least one registered calculator
        -- lets a consumer (the Property Panel, eagerly creating a section
        per category at construction time) discover which sections need an
        "Open [Calculator]..." row without hardcoding category names, even
        for a category with no matching scalar descriptor to otherwise
        trigger section creation (pKa today)."""
        return sorted({d.category for d in self._definitions.values()})
