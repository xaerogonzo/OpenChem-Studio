from __future__ import annotations

from typing import Any

from rdkit import Chem

from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.common import ScientificResult


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

    def get(self, calculator_id: str) -> CalculatorDefinition | None:
        return self._definitions.get(calculator_id)

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
        return execution.compute(mol, molecule_uuid, parameters)

    def by_category(self, category: str) -> list[CalculatorDefinition]:
        return [d for d in self._definitions.values() if d.category == category]

    def categories(self) -> list[str]:
        """Every distinct category with at least one registered calculator
        -- lets a consumer (the Property Panel, eagerly creating a section
        per category at construction time) discover which sections need an
        "Open [Calculator]..." row without hardcoding category names, even
        for a category with no matching scalar descriptor to otherwise
        trigger section creation (pKa today)."""
        return sorted({d.category for d in self._definitions.values()})
